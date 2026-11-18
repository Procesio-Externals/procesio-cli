"""The troubleshooting log: one line per call and per refusal, the message id that names the turn
on them, and the health probe that no longer fills the access log.

Every line is checked twice. For what it says: the exact fields, in their order. And for what it
must never say: an argument, a result, a credential, an id of a user or a workspace, or anything
a caller could use to write a field of its own. Logging must also leave the call as it was, so
each call-site test checks what the call returned or raised.

Fakes throughout - no subprocess, no Web-Api, no real registry scan. The HTTP tests bind an
ephemeral loopback port.
"""
from __future__ import annotations

import base64
import http.client
import json
import re
import threading
import time
import types
from http.server import ThreadingHTTPServer

import bridge
import gate
import http_server
import metrics
import pytest
import server
import turn_credentials
import turn_token
from tools._lib import httptrace

P = "procesio_aat_runtime_"
MSG = "0b7e6a52-3c1d-4f8e-9a2b-5d6c7e8f9a10"
GUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
SECONDS = r"seconds=\d+\.\d{3}"


def _tool(name, actions):
    return {"name": name, "description": "", "ready": True, "args": [],
            "actions": [{"name": a, "description": "", "args": []} for a in actions]}


@pytest.fixture
def off(monkeypatch):
    """Metrics off, as in the stdio server and a local run."""
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    assert metrics.enabled() is False


@pytest.fixture
def on(monkeypatch):
    """Recording on, from a clean slate, with the label index of a fake registry."""
    monkeypatch.setattr(bridge, "_scan_registry",
                        lambda: (_ for _ in ()).throw(AssertionError("a call scanned the registry")))
    monkeypatch.setattr(bridge, "_METRIC_NAMES", {})
    bridge._index_metric_names([_tool("bigtool", ["list-processes", "export"])],
                               [_tool("orchestrator", ["intake", "drive"])])
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    monkeypatch.delenv(metrics.SLOW_LOG_ENV, raising=False)
    metrics.reset()
    metrics.enable()
    yield
    metrics.enable(False)
    metrics.reset()


@pytest.fixture
def msg():
    """The request carries a message id."""
    token = bridge.set_message_id(MSG)
    yield MSG
    bridge.reset_message_id(token)


def _log_lines(err: str) -> list[str]:
    """The lines this server wrote about calls and refusals, without their prefix."""
    return [line[len("[aat-mcp] "):] for line in err.splitlines() if line.startswith("[aat-mcp] ")]


def _trace(*events) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _start(request_id, method="GET", path="/api/Projects", sent_at=None):
    return {"e": "start", "id": request_id, "m": method, "p": path,
            "t": time.time() if sent_at is None else sent_at}


def _api_key_manifest(name="bigtool"):
    return types.SimpleNamespace(name=name, secrets=["api-key"],
                                 procesio_credential=types.SimpleNamespace(is_api_key=lambda: True))


# --- the message id -------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [MSG, MSG.upper(), "7", "a-b", "x" * 64])
def test_a_plain_id_is_kept(value):
    token = bridge.set_message_id(value)
    try:
        assert bridge.message_id() == value
    finally:
        bridge.reset_message_id(token)
    assert bridge.message_id() == "-"


@pytest.mark.parametrize("value", [
    None, "", "x" * 65, "two words", "id=1", f"{MSG}\n", f"{MSG} outcome=ok", "a_b", "a.b",
    "{id}", "id\ttab", '"quoted"', "ünïcode", 7, ["a"],
])
def test_anything_else_counts_as_absent(value):
    token = bridge.set_message_id(value)
    try:
        assert bridge.message_id() == "-"
    finally:
        bridge.reset_message_id(token)


def test_the_message_id_is_reset_to_what_it_was(msg):
    token = bridge.set_message_id("another-id")
    assert bridge.message_id() == "another-id"
    bridge.reset_message_id(token)
    assert bridge.message_id() == MSG


# --- the line of a call ---------------------------------------------------------------------------

def test_a_call_writes_one_line_when_it_ends_and_nothing_of_its_content(off, msg, monkeypatch, capsys):
    result = {"ok": True, "data": {"rows": ["RESULT-DATA-71c2"]}, "error": None,
              "returncode": 0, "stderr": "STDERR-TEXT-2d9f"}
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: result)
    user, ws = bridge.set_user("user-4c1e"), bridge.set_workspace("workspace-9d2b")
    try:
        got = bridge.run_tool("bigtool", "export", {"id": "ARG-VALUE-9e41"}, credential="CRED-NAME-5b7a")
    finally:
        bridge.reset_workspace(ws)
        bridge.reset_user(user)
    assert got is result  # the call is what it was

    out, err = capsys.readouterr()
    assert out == ""  # stdout belongs to the JSON-RPC stream in stdio mode
    [line] = _log_lines(err)
    assert re.fullmatch(
        rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=ok code=- {SECONDS} exit=0", line)
    for never in ("ARG-VALUE-9e41", "RESULT-DATA-71c2", "STDERR-TEXT-2d9f", "CRED-NAME-5b7a",
                  "user-4c1e", "workspace-9d2b"):
        assert never not in err


def test_without_a_message_id_an_action_or_an_exit_code_the_line_says_so(off, monkeypatch, capsys):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "data": {}})
    bridge.run_tool("flat", None, None)
    [line] = _log_lines(capsys.readouterr().err)
    assert re.fullmatch(rf"call msg=- kind=tool tool=flat action=- outcome=ok code=- {SECONDS}", line)


def test_the_seconds_are_the_time_the_call_took(off, monkeypatch, capsys):
    def slow(*a, **k):
        time.sleep(0.05)
        return {"ok": True}

    monkeypatch.setattr(bridge.runner, "run_tool", slow)
    bridge.run_tool("bigtool", "export", {})
    [line] = _log_lines(capsys.readouterr().err)
    assert 0.05 <= float(re.search(r"seconds=(\S+)", line).group(1)) < 5


def _own_error(code, message, returncode=1):
    """The result of a tool that answered with an error of its own: the runner hands the error
    object on next to the JSON answer it came from."""
    error = {"code": code, "message": message}
    return {"ok": False, "data": {"error": error}, "error": error, "returncode": returncode, "stderr": ""}


def test_a_failed_call_carries_its_code_its_exit_code_and_the_start_of_its_message(off, msg, monkeypatch,
                                                                                capsys):
    failed = _own_error("bad_flag", "usage: bigtool export\nerror: bad\tflag", returncode=2)
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: failed)
    assert bridge.run_tool("bigtool", "export", {}) is failed
    [line] = _log_lines(capsys.readouterr().err)
    assert re.fullmatch(
        rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=error code=bad_flag "
        rf'{SECONDS} exit=2 message="usage: bigtool export error: bad flag"', line)


def test_a_timeout_is_an_error_with_the_exit_code_of_a_stopped_process(off, monkeypatch, capsys):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "data": None, "returncode": -1, "stderr": "timeout after 180.0s",
        "error": {"code": "timeout", "message": "timeout after 180.0s"}})
    bridge.run_tool("bigtool", "export", {})
    [line] = _log_lines(capsys.readouterr().err)
    assert re.fullmatch(rf"call msg=- kind=tool tool=bigtool action=export outcome=error code=timeout "
                        rf'{SECONDS} exit=-1 message="the tool did not end in time and was stopped"', line)


# What a tool can print when it fails, as made-up data: a personal number, a bank account, a
# webhook address with its token, and a line of a record it was reading.
_RAW_OUTPUT = ("Traceback (most recent call last): row={'cnp': 'CNP-MADE-UP-1800101', "
               "'iban': 'IBAN-MADE-UP-RO00FAKE'} POST https://discord.example/api/webhooks/1/"
               "WEBHOOK-MADE-UP-7f3a failed for client RECORD-MADE-UP-51c2")
_RAW_VALUES = ("CNP-MADE-UP-1800101", "IBAN-MADE-UP-RO00FAKE", "WEBHOOK-MADE-UP-7f3a", "RECORD-MADE-UP-51c2",
               "Traceback", "discord.example")


@pytest.mark.parametrize("result, sentence", [
    # No JSON at all: the runner's message is the start of stderr, or of stdout.
    ({"ok": False, "data": None, "returncode": 1, "stderr": _RAW_OUTPUT,
      "error": {"code": "no_json", "message": _RAW_OUTPUT}},
     "the tool ended without a JSON answer"),
    # A JSON answer that is not an error, and an error exit code: the message is stderr.
    ({"ok": False, "data": {"rows": 3}, "returncode": 1, "stderr": _RAW_OUTPUT,
      "error": {"code": "nonzero_exit", "message": _RAW_OUTPUT}},
     "the tool ended with an error exit code and no error of its own"),
    # Stopped at the time limit: the message is what the runner was told about the stop, and
    # whatever it holds is not the tool's own error either.
    ({"ok": False, "data": None, "returncode": -1, "stderr": _RAW_OUTPUT,
      "error": {"code": "timeout", "message": _RAW_OUTPUT}},
     "the tool did not end in time and was stopped"),
])
def test_what_the_tool_printed_is_never_the_message_of_the_line(off, monkeypatch, capsys, result, sentence):
    """For these three codes the runner builds the message from the tool's raw output."""
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: result)
    assert bridge.run_tool("bigtool", "export", {}) is result  # the model still gets the whole answer
    err = capsys.readouterr().err
    [line] = _log_lines(err)
    assert line.endswith(f' exit={result["returncode"]} message="{sentence}"')
    for never in _RAW_VALUES:
        assert never not in err


@pytest.mark.parametrize("code", ["timeout", "no_json", "nonzero_exit"])
def test_an_error_the_tool_wrote_itself_keeps_its_message_whatever_its_code(off, monkeypatch, capsys, code):
    """A tool may use one of the runner's codes for an error of its own, such as a request that
    timed out. That text is the tool's deliberate error message, not its raw output."""
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: _own_error(code, "PROCESIO did not answer in 30 s"))
    bridge.run_tool("bigtool", "export", {})
    [line] = _log_lines(capsys.readouterr().err)
    assert line.endswith(f' code={code} seconds={line.split("seconds=")[1].split(" ")[0]} exit=1 '
                         'message="PROCESIO did not answer in 30 s"')


def test_an_error_object_that_only_looks_like_the_tool_s_own_is_not_trusted(off, monkeypatch, capsys):
    """The answer holds an error, and the result's error is a different one: the runner's."""
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "data": {"error": {"code": "other", "message": "something else"}}, "returncode": 1,
        "error": {"code": "no_json", "message": _RAW_OUTPUT}})
    bridge.run_tool("bigtool", "export", {})
    err = capsys.readouterr().err
    assert _log_lines(err)[0].endswith('message="the tool ended without a JSON answer"')
    assert "MADE-UP" not in err


@pytest.mark.parametrize("result, tail", [
    ({"ok": False, "error": "a string"}, 'code=- {s} message="a string"'),
    ({"ok": False}, "code=- {s}"),
    ({"ok": False, "error": {"code": "made-up-by-the-tool", "message": 7}}, "code=made-up-by-the-tool {s}"),
    ({"ok": False, "error": {"code": ["a", "list"], "message": ""}}, 'code="<list>" {s}'),
    ("not a dict", "code=- {s}"),
    (None, "code=- {s}"),
])
def test_an_error_of_any_shape_gets_a_line(off, monkeypatch, capsys, result, tail):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: result)
    assert bridge.run_tool("bigtool", "export", {}) == result
    [line] = _log_lines(capsys.readouterr().err)
    assert re.fullmatch(r"call msg=- kind=tool tool=bigtool action=export outcome=error "
                        + re.escape(tail).replace(r"\{s\}", SECONDS), line)


def test_the_message_is_cut_put_on_one_line_and_loses_what_must_not_be_logged(off, monkeypatch, capsys):
    message = ('GET https://api.example.com/api/Projects?token=QUERY-SECRET-1a&x=2 failed:\r\n'
               '  Authorization: Bearer EXAMPLE-BEARER-2b3c4d\x00\x1b[31m said "no"\n' + "z" * 5000)
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: _own_error("request_failed", message))
    bridge.run_tool("bigtool", "export", {})
    err = capsys.readouterr().err
    [line] = _log_lines(err)
    text = re.search(r' message="(.*)"$', line).group(1)
    assert text.startswith("GET https://api.example.com/api/Projects failed: Authorization: Bearer "
                           "[removed] [31m said 'no' zzz")
    assert len(text) == 300
    assert "QUERY-SECRET-1a" not in err and "EXAMPLE-BEARER-2b3c4d" not in err
    assert '"' not in text and len(err.splitlines()) == 1


def _fields(line: str) -> dict:
    """A log line read the way a logfmt parser reads it: `key=value` pairs separated by spaces,
    a value in double quotes runs to the next quote that no backslash escapes."""
    fields, i = {}, line.index(" ") + 1  # after the word that opens the line
    while i < len(line):
        eq = line.index("=", i)
        key, i = line[i:eq], eq + 1
        if i < len(line) and line[i] == '"':
            j, value = i + 1, []
            while line[j] != '"':
                j += 2 if line[j] == "\\" else 1
            value, i = line[i + 1:j], j + 2
        else:
            end = line.find(" ", i)
            end = len(line) if end == -1 else end
            value, i = line[i:end], end + 1
        assert key not in fields, f"the field {key} is on the line twice"
        fields[key] = value
    return fields


@pytest.mark.parametrize("name, action", [
    ("bigtool\\", "export\\"),                              # the closing quote would be escaped
    ('x\\" outcome=ok code=- injected=1 y="', "export"),    # ...and what follows read as fields
    ("C:\\tools\\big tool", 'a\\\\" msg=other'),
])
def test_a_backslash_in_a_name_or_a_message_cannot_move_the_end_of_a_value(off, msg, monkeypatch, capsys,
                                                                         name, action):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: _own_error(
        "failed\\", 'could not open C:\\data\\in.csv\\" outcome=ok injected=2 z="\\', returncode=3))
    bridge.run_tool(name, action, {})
    err = capsys.readouterr().err
    [line] = _log_lines(err)
    assert "\\" not in line
    fields = _fields(line)
    assert list(fields) == ["msg", "kind", "tool", "action", "outcome", "code", "seconds", "exit", "message"]
    assert (fields["msg"], fields["kind"], fields["outcome"], fields["exit"]) == (MSG, "tool", "error", "3")
    assert fields["tool"] == name.replace("\\", "/").replace('"', "'")
    assert fields["action"] == action.replace("\\", "/").replace('"', "'")
    assert fields["code"] == "failed/"
    assert fields["message"] == "could not open C:/data/in.csv/' outcome=ok injected=2 z='/"


def test_a_call_that_raises_still_raises_and_the_line_names_only_the_exception_type(off, msg, monkeypatch,
                                                                                capsys):
    def boom(*a, **k):
        raise RuntimeError("could not start with --id ARG-VALUE-9e41")

    monkeypatch.setattr(bridge.runner, "run_tool", boom)
    with pytest.raises(RuntimeError, match="could not start"):
        bridge.run_tool("bigtool", "export", {"id": "ARG-VALUE-9e41"})
    err = capsys.readouterr().err
    [line] = _log_lines(err)
    assert re.fullmatch(rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=error "
                        rf'code=exception {SECONDS} message="RuntimeError"', line)
    assert "ARG-VALUE-9e41" not in err


def test_an_agent_call_is_kind_agent(off, msg, monkeypatch, capsys):
    monkeypatch.setattr(bridge.runner, "run_agent", lambda *a, **k: {"ok": True, "returncode": 0})
    bridge.run_agent(agent="orchestrator", action="intake", args={"request": "ARG-VALUE-9e41"})
    err = capsys.readouterr().err
    [line] = _log_lines(err)
    assert re.fullmatch(rf"call msg={MSG} kind=agent tool=orchestrator action=intake outcome=ok code=- "
                        rf"{SECONDS} exit=0", line)
    assert "ARG-VALUE-9e41" not in err


# --- names that arrive from the model ---------------------------------------------------------------

@pytest.mark.parametrize("value, written", [
    ("list-processes", "list-processes"),
    ("x" * 200, "x" * 80),
    ("two words", '"two words"'),
    ("a\r\nb\tc\x00d", '"a b c d"'),
    ("x outcome=ok code=- seconds=0.001", '"x outcome=ok code=- seconds=0.001"'),
    ('say "hi"', "\"say 'hi'\""),
    ("ends with a backslash\\", '"ends with a backslash/"'),
    ("bare\\", '"bare/"'),
    ('a\\"b', "\"a/'b\""),
    (" \n ", "-"),
    ("", "-"),
    (None, "-"),
    (["bigtool"], '"<list>"'),
    ({"a": 1}, '"<dict>"'),
])
def test_a_name_is_cut_to_80_put_on_one_line_and_cannot_write_a_field(value, written):
    assert bridge._log_name(value) == written


def test_the_line_keeps_the_name_the_model_sent_and_the_metrics_do_not(on, monkeypatch, capsys):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True})
    bridge.run_tool("invented-tool-51ab", "drop everything\noutcome=error", {})
    [line] = _log_lines(capsys.readouterr().err)
    assert line.startswith('call msg=- kind=tool tool=invented-tool-51ab '
                           'action="drop everything outcome=error" outcome=ok code=- seconds=')
    text = metrics.render()
    assert "invented-tool-51ab" not in text and "drop everything" not in text
    assert P + 'action_duration_seconds_count{kind="tool",tool="unknown",action="unknown"} 1' in text


# --- the HTTP summary on the line -------------------------------------------------------------------

def test_with_metrics_on_the_line_carries_the_http_requests_of_the_call(on, msg, monkeypatch, capsys):
    def fake_run_tool(tool, argv, **k):
        with open(k["env"][httptrace.ENV], "a", encoding="utf-8") as f:
            f.write(_trace(_start(1, "GET", "/api/Workspaces"), {"e": "end", "id": 1, "s": 200, "d": 0.2},
                           _start(2, "POST", f"/api/Projects/{GUID}/run?token=QUERY-SECRET-1a"),
                           {"e": "end", "id": 2, "s": 500, "d": 12.5},
                           _start(3, "GET", "/api/Slow")))
        return {"ok": False, "data": None, "returncode": -1, "stderr": "",
                "error": {"code": "timeout", "message": "timeout after 180s"}}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    bridge.run_tool("bigtool", "export", {})
    err = capsys.readouterr().err
    [line] = [x for x in _log_lines(err) if x.startswith("call ")]
    assert re.fullmatch(
        rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=error code=timeout {SECONDS} "
        r'exit=-1 http=3 slowest="POST /api/projects/\{id\}/run 12\.5s 500" unfinished=1 '
        r'message="the tool did not end in time and was stopped"', line)
    assert "QUERY-SECRET-1a" not in err and GUID not in line
    # The metrics module's own line about the request that never ended names the same turn.
    assert re.search(rf"\[aat-metrics\] http request never answered \(call_killed\): bigtool export: "
                     rf"GET /api/Slow after \d+\.\ds msg={MSG}\n", err)
    # The id is on log lines only.
    assert MSG not in metrics.render()


def test_a_call_that_noted_no_request_has_no_http_fields(on, monkeypatch, capsys):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "returncode": 0})
    bridge.run_tool("bigtool", "export", {})
    [line] = _log_lines(capsys.readouterr().err)
    assert re.fullmatch(rf"call msg=- kind=tool tool=bigtool action=export outcome=ok code=- {SECONDS} exit=0",
                        line)


def test_the_trace_summary_counts_requests_and_names_the_slowest_by_route(on):
    summary = metrics.http_trace(
        _trace(_start(1, "GET", f"/api/Projects/{GUID}"), {"e": "end", "id": 1, "s": 200, "d": 0.3},
               _start(2, "GET", "/api/Workspaces"), {"e": "end", "id": 2, "x": "timeout", "d": 60.0},
               {"e": "retry", "m": "GET", "p": "/api/Workspaces"},
               {"e": "end", "id": 99, "s": 200, "d": 500.0}),          # an end with no start
        "tool", "bigtool", "export", call_killed=False)
    assert summary == metrics.HttpSummary(2, ("GET", "/api/workspaces", 60.0, "timeout"), 0)


def test_a_request_that_never_ended_can_be_the_slowest_of_the_call(on):
    summary = metrics.http_trace(
        _trace(_start(1), {"e": "end", "id": 1, "s": 200, "d": 0.3},
               _start(2, "POST", f"/api/Projects/{GUID}/run", sent_at=time.time() - 170),
               _start(3, "GET", "/api/x", sent_at="not a time")),
        "tool", "bigtool", "export", call_killed=True)
    assert (summary.requests, summary.unfinished) == (3, 2)
    method, route, seconds, status = summary.slowest
    assert (method, route, status) == ("POST", "/api/projects/{id}/run", "unfinished")
    assert 169 <= seconds <= 180


@pytest.mark.parametrize("text, summary", [
    (None, None),                                                    # the file could not be read
    ("", None),                                                      # the tool noted nothing
    ("not json at all\n", metrics.HttpSummary(0, None, 0)),          # it wrote, and none of it fits
])
def test_a_trace_with_no_request_in_it_has_no_slowest_request(on, text, summary):
    assert metrics.http_trace(text, "tool", "bigtool", "export", call_killed=False) == summary


def test_with_metrics_off_a_trace_has_no_summary(on):
    metrics.enable(False)
    assert metrics.http_trace(_trace(_start(1)), "tool", "bigtool", "export", False) is None


def test_the_two_http_lines_end_with_the_message_id(on, capsys, monkeypatch):
    monkeypatch.setenv(metrics.SLOW_LOG_ENV, "10")
    trace = _trace(_start(1, "GET", "/api/Projects"), {"e": "end", "id": 1, "s": 200, "d": 12.5},
                   _start(2, "POST", "/api/Run", sent_at="not a time"))
    metrics.http_trace(trace, "tool", "bigtool", "export", call_killed=True, msg=MSG)
    err = capsys.readouterr().err
    assert f"slow http request: bigtool export: GET /api/Projects -> 200 in 12.5s msg={MSG}\n" in err
    assert f"never answered (call_killed): bigtool export: POST /api/Run msg={MSG}\n" in err
    metrics.http_trace(trace, "tool", "bigtool", "export", call_killed=True)
    err = capsys.readouterr().err
    assert "in 12.5s msg=-\n" in err and "POST /api/Run msg=-\n" in err


# --- the line of a refusal --------------------------------------------------------------------------

def test_the_gate_refusals_are_logged_without_the_arguments(off, msg, monkeypatch, capsys):
    monkeypatch.setattr(server.bridge, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    arguments = {"tool": "google-mail", "action": "send-message", "args": {"to": "ARG-VALUE-9e41"}}
    payload, is_error = server._call_tool("run_tool", arguments)
    assert "approval_required" in payload and is_error is False
    monkeypatch.setattr(gate, "deny_irreversible_env", lambda: True)
    payload, is_error = server._call_tool("run_tool_confirmed", arguments)
    assert "refused" in payload and is_error is True

    out, err = capsys.readouterr()
    assert out == ""
    assert _log_lines(err) == [
        f"refused msg={MSG} tool=google-mail action=send-message code=approval_required "
        'reason="an irreversible action was called on the tool that runs without approval"',
        f"refused msg={MSG} tool=google-mail action=send-message code=irreversible_denied "
        'reason="irreversible actions are denied on this server, confirmed or not"',
    ]
    assert "ARG-VALUE-9e41" not in err


def test_a_managed_turn_refusal_is_logged_and_ends_the_call(off, msg, monkeypatch, capsys):
    monkeypatch.setattr(bridge.runner, "run_agent",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    token = bridge.set_managed_turn(True)
    try:
        res = bridge.run_agent("orchestrator", "drive", {"goal": "ARG-VALUE-9e41"})
    finally:
        bridge.reset_managed_turn(token)
    assert res["refused"]["reason"] == "managed_turn"
    err = capsys.readouterr().err
    refused, call = _log_lines(err)
    assert refused == (f"refused msg={MSG} tool=orchestrator action=drive code=managed_turn "
                       'reason="the action starts a second orchestration loop inside a managed turn"')
    assert re.fullmatch(rf"call msg={MSG} kind=agent tool=orchestrator action=drive outcome=error "
                        rf"code=managed_turn {SECONDS}", call)
    assert "ARG-VALUE-9e41" not in err


def test_a_workspace_refusal_is_logged_without_either_workspace(off, msg, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "_secret_manifests", lambda kind, name: [_api_key_manifest()])
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    asked, turn_ws = "11111111-2222-3333-4444-555555555555", "99999999-8888-7777-6666-555555555555"
    token, ws = bridge.set_turn_token("TURN-TOKEN-6f1e"), bridge.set_workspace(turn_ws)
    try:
        res = bridge.run_tool("bigtool", "export", {"workspace-id": asked})
    finally:
        bridge.reset_workspace(ws)
        bridge.reset_turn_token(token)
    assert res["error"]["code"] == "workspace_out_of_turn" and asked in res["error"]["message"]
    err = capsys.readouterr().err
    refused, call = _log_lines(err)
    assert refused == (f"refused msg={MSG} tool=bigtool action=export code=workspace_out_of_turn "
                       'reason="the call names a workspace other than the one of the turn"')
    # The refusal's own text quotes the argument, so the call line stops at the code.
    assert re.fullmatch(rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=error "
                        rf"code=workspace_out_of_turn {SECONDS}", call)
    for never in (asked, turn_ws, "TURN-TOKEN-6f1e"):
        assert never not in err


def test_a_turn_without_a_key_is_logged_once(off, msg, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "_secret_manifests",
                        lambda kind, name: [_api_key_manifest(), _api_key_manifest("other")])
    monkeypatch.setattr(bridge.turn_credentials, "fetch_key",
                        lambda token: turn_credentials.ProcesioKey(message="PROCESIO answered 503."))
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    token = bridge.set_turn_token("TURN-TOKEN-6f1e")
    try:
        res = bridge.run_tool("bigtool", "export", {})
    finally:
        bridge.reset_turn_token(token)
    assert res["error"]["code"] == "procesio_key_unavailable"
    err = capsys.readouterr().err
    refused, call = _log_lines(err)
    assert refused == (f"refused msg={MSG} tool=bigtool action=export code=procesio_key_unavailable "
                       'reason="the turn has no usable PROCESIO API key"')
    # Why there is no key is the platform's own sentence, so it is on the call line.
    assert re.fullmatch(rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=error "
                        rf'code=procesio_key_unavailable {SECONDS} message="PROCESIO answered 503\. .*"', call)
    assert "TURN-TOKEN-6f1e" not in err


def test_a_key_revoked_after_the_tool_ran_is_logged_as_the_refusal_that_replaced_its_answer(
        off, msg, monkeypatch, capsys):
    key = turn_credentials.ProcesioKey(key="KEY-NAME-3a", value="KEY-VALUE-8c2d")
    monkeypatch.setattr(bridge, "_secret_manifests", lambda kind, name: [_api_key_manifest()])
    monkeypatch.setattr(bridge, "_procesio_profile", lambda manifest, key, secrets: None)
    monkeypatch.setattr(bridge.turn_credentials, "fetch_key", lambda token: key)
    monkeypatch.setattr(bridge.turn_credentials, "recheck_key",
                        lambda token: turn_credentials.ProcesioKey(message="Revoked."))
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "returncode": 1, "error": {"code": "unauthorized", "message": "401"}})
    token = bridge.set_turn_token("TURN-TOKEN-6f1e")
    try:
        res = bridge.run_tool("bigtool", "export", {})
    finally:
        bridge.reset_turn_token(token)
    assert res["error"]["code"] == "procesio_key_unavailable"
    err = capsys.readouterr().err
    refused, call = _log_lines(err)
    assert refused == (
        f"refused msg={MSG} tool=bigtool action=export code=procesio_key_unavailable "
        'reason="the PROCESIO API key of the turn stopped being valid after the tool ran"')
    assert call.startswith(f"call msg={MSG} kind=tool tool=bigtool action=export outcome=error "
                           "code=procesio_key_unavailable seconds=")
    for never in ("KEY-NAME-3a", "KEY-VALUE-8c2d", "TURN-TOKEN-6f1e"):
        assert never not in err


def test_a_plain_auth_failure_with_a_key_that_stands_is_not_a_refusal(off, monkeypatch, capsys):
    key = turn_credentials.ProcesioKey(key="k", value="v")
    monkeypatch.setattr(bridge, "_secret_manifests", lambda kind, name: [_api_key_manifest()])
    monkeypatch.setattr(bridge, "_procesio_profile", lambda manifest, key, secrets: None)
    monkeypatch.setattr(bridge.turn_credentials, "fetch_key", lambda token: key)
    monkeypatch.setattr(bridge.turn_credentials, "recheck_key", lambda token: key)
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "returncode": 1, "error": {"code": "forbidden", "message": "403"}})
    token = bridge.set_turn_token("a-turn-token")
    try:
        bridge.run_tool("bigtool", "export", {})
    finally:
        bridge.reset_turn_token(token)
    [line] = _log_lines(capsys.readouterr().err)
    assert line.startswith("call msg=- kind=tool tool=bigtool action=export outcome=error code=forbidden ")


# --- logging never changes the call -----------------------------------------------------------------

class _BrokenStream:
    def write(self, text):
        raise OSError("the stream is closed")

    def flush(self):
        raise OSError("the stream is closed")


def test_a_line_that_cannot_be_written_does_not_fail_the_call_or_the_refusal(off, msg, monkeypatch):
    monkeypatch.setattr(bridge.sys, "stderr", _BrokenStream())
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "data": 1})
    assert bridge.run_tool("bigtool", "export", {}) == {"ok": True, "data": 1}
    payload, is_error = server._call_tool("run_tool", {"tool": "google-mail", "action": "send-message"})
    assert "approval_required" in payload and is_error is False


def test_a_line_that_cannot_be_formatted_does_not_fail_the_call_or_the_refusal(off, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "_log_name", lambda value: 1 / 0)
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "data": 1})
    assert bridge.run_tool("bigtool", "export", {}) == {"ok": True, "data": 1}
    payload, is_error = server._call_tool("run_tool", {"tool": "google-mail", "action": "send-message"})
    assert "approval_required" in payload and is_error is False
    assert _log_lines(capsys.readouterr().err) == []


def test_the_message_id_changes_nothing_but_the_line(on, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: seen.append((tool, argv, sorted(k))) or {"ok": True})
    without = bridge.run_tool("bigtool", "export", {"id": "7"})
    samples_without = [line for line in metrics.render().splitlines() if "_count" in line]
    metrics.reset()
    token = bridge.set_message_id(MSG)
    try:
        with_id = bridge.run_tool("bigtool", "export", {"id": "7"})
    finally:
        bridge.reset_message_id(token)
    assert with_id == without and seen[0] == seen[1]
    assert [line for line in metrics.render().splitlines() if "_count" in line] == samples_without
    first, second = _log_lines(capsys.readouterr().err)
    assert first.startswith("call msg=- ") and second.startswith(f"call msg={MSG} ")


# --- the HTTP transport: the header and the access log ------------------------------------------------

@pytest.fixture
def httpd(off, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "data": {}, "returncode": 0})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), http_server._make_handler(None))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _run_tool_request(request_id, meta=None):
    params = {"name": "run_tool", "arguments": {"tool": "bigtool", "action": "list-processes", "args": {}}}
    if meta:
        params["_meta"] = meta
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": params})


def _post(conn, body, headers=None):
    conn.request("POST", "/mcp", body=body, headers={"Content-Type": "application/json", **(headers or {})})
    resp = conn.getresponse()
    return resp.status, resp.read()


def test_the_header_names_the_turn_for_that_request_only(httpd, capsys):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    try:
        # One connection, so every request is served by the same thread: what the first one
        # bound must be gone when the second one runs.
        assert _post(conn, _run_tool_request(1), {"X-AAT-Message-Id": f" {MSG} "})[0] == 200
        assert _post(conn, _run_tool_request(2))[0] == 200
        assert _post(conn, _run_tool_request(3), {"X-AAT-Message-Id": "not an id=1"})[0] == 200
        # Only the header counts: the JSON-RPC body is the model's side of the request.
        assert _post(conn, _run_tool_request(4, meta={"X-AAT-Message-Id": "from-the-body"}))[0] == 200
    finally:
        conn.close()
    err = capsys.readouterr().err
    assert [line.split(" ")[1] for line in _log_lines(err)] == [f"msg={MSG}", "msg=-", "msg=-", "msg=-"]
    assert "from-the-body" not in err and "not an id" not in err


def _turn_token(message):
    """A token in the shape Web-Api mints, for a turn in the personal workspace. Nothing verifies
    its signature here: this server only reads the payload."""
    payload = {"ws": "00000000-0000-0000-0000-000000000000", "u": "7a1c9e42-5b3d-4f60-8a7e-2c4d6f8b0a13",
               "m": message, "exp": int(time.time()) + 600}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{turn_token.PREFIX}.{body}.x.y"


def test_without_the_header_the_turn_token_names_the_turn(httpd, monkeypatch, capsys):
    # The tool of this test needs nothing from the turn, so the call starts without a lookup.
    monkeypatch.setattr(bridge, "_turn_env", lambda *a, **k: {})
    other = "5c1d2e3f-0a1b-4c2d-8e3f-9a0b1c2d3e4f"
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    try:
        token = {turn_token.HEADER: _turn_token(MSG)}
        assert _post(conn, _run_tool_request(1), token)[0] == 200
        # The header is what the worker wrote for this turn, so it is read first.
        assert _post(conn, _run_tool_request(2), {**token, "X-AAT-Message-Id": other})[0] == 200
    finally:
        conn.close()
    lines = [line for line in _log_lines(capsys.readouterr().err) if line.startswith("call ")]
    assert [line.split(" ")[1] for line in lines] == [f"msg={MSG}", f"msg={other}"]


@pytest.mark.parametrize("header", ["not an id=1", "x" * 65, f"{MSG} outcome=ok", "a_b", '"quoted"'])
def test_a_header_that_is_not_an_id_does_not_hide_the_id_of_the_turn_token(httpd, monkeypatch, capsys, header):
    monkeypatch.setattr(bridge, "_turn_env", lambda *a, **k: {})
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    try:
        headers = {turn_token.HEADER: _turn_token(MSG), "X-AAT-Message-Id": header}
        assert _post(conn, _run_tool_request(1), headers)[0] == 200
        # With no token to fall back on, and with a token whose id is not one either, the
        # turn has no name: nothing of the header is written.
        assert _post(conn, _run_tool_request(2), {"X-AAT-Message-Id": header})[0] == 200
        assert _post(conn, _run_tool_request(3), {turn_token.HEADER: _turn_token("no id=2"),
                                                  "X-AAT-Message-Id": header})[0] == 200
    finally:
        conn.close()
    err = capsys.readouterr().err
    lines = [line for line in _log_lines(err) if line.startswith("call ")]
    assert [line.split(" ")[1] for line in lines] == [f"msg={MSG}", "msg=-", "msg=-"]
    assert header not in err and "no id=2" not in err


@pytest.mark.parametrize("candidates, picked", [
    ((MSG, "other-id"), MSG),
    (("not an id", MSG), MSG),
    (("", None, MSG), MSG),
    (("not an id", None), None),
    ((), None),
    ((7, ["a"], "x" * 65), None),
])
def test_the_first_usable_id_is_the_one_taken(candidates, picked):
    assert bridge.first_message_id(*candidates) == picked


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_an_answered_health_probe_is_not_in_the_access_log_and_every_other_request_is(httpd, capsys):
    port = httpd.server_address[1]
    for path in ("/health", "/health/"):
        status, body = _get(port, path)
        assert status == 200 and json.loads(body)["ok"] is True  # answered as before
    assert capsys.readouterr().err == ""

    assert _get(port, "/healthz")[0] == 200
    assert _get(port, "/health/x")[0] == 405
    assert _get(port, "/mcp")[0] == 405
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        assert _post(conn, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))[0] == 200
        conn.request("POST", "/health")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 404
    finally:
        conn.close()
    lines = capsys.readouterr().err.splitlines()
    assert lines[:3] + lines[4:] == [
        '[aat-mcp-http] "GET /healthz HTTP/1.1" 200 -',
        '[aat-mcp-http] "GET /health/x HTTP/1.1" 405 -',
        '[aat-mcp-http] "GET /mcp HTTP/1.1" 405 -',
        '[aat-mcp-http] "POST /health HTTP/1.1" 404 -',
    ]
    # A request that was read says what it was for; one that was refused before that does not.
    assert re.fullmatch(r'\[aat-mcp-http\] "POST /mcp HTTP/1\.1" 200 - \d+\.\d{3}s msg=- \| tools/list', lines[3])
