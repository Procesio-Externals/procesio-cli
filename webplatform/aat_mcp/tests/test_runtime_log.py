"""The log writer and its JSON format (AAT_LOG_FORMAT=json).

Two things are held here. Every line the server writes in the JSON format is one JSON object with
the keys the .NET services of the product write, so one query reads all of them. And a line says
the same in both formats: the sentence of the text line is the `RenderedMessage` of the JSON line,
and what the text line keeps out - arguments, results, raw tool output - the JSON line keeps out.

Fakes throughout - no subprocess, no Web-Api. The HTTP tests bind an ephemeral loopback port.
"""
from __future__ import annotations

import base64
import http.client
import json
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import bridge
import http_server
import metrics
import pytest
import runtime_log
import turn_token

MSG = "0b7e6a52-3c1d-4f8e-9a2b-5d6c7e8f9a10"
TOP_LEVEL = ["Timestamp", "Level", "RenderedMessage", "Properties"]


@pytest.fixture
def as_json(monkeypatch):
    monkeypatch.setenv(runtime_log.FORMAT_ENV, "json")
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)


@pytest.fixture
def msg():
    token = bridge.set_message_id(MSG)
    yield MSG
    bridge.reset_message_id(token)


def _records(err: str) -> list[dict]:
    """Every line of stderr, each of which has to be one JSON object."""
    lines = err.splitlines()
    assert lines, "nothing was written"
    return [json.loads(line) for line in lines]


# --- the writer -------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "text", "TEXT", "anything else"])
def test_without_the_setting_a_line_is_text(monkeypatch, capsys, value):
    if value is None:
        monkeypatch.delenv(runtime_log.FORMAT_ENV, raising=False)
    else:
        monkeypatch.setenv(runtime_log.FORMAT_ENV, value)
    runtime_log.write("aat-mcp", "started", level=runtime_log.WARNING, fields={"Port": 8901})
    out, err = capsys.readouterr()
    assert out == "" and err == "[aat-mcp] started\n"


@pytest.mark.parametrize("value", ["json", "JSON", " Json "])
def test_a_json_line_has_the_keys_of_the_other_services(monkeypatch, capsys, value):
    monkeypatch.setenv(runtime_log.FORMAT_ENV, value)
    runtime_log.write("aat-mcp-http", "listening", level=runtime_log.WARNING,
                      fields={"Port": 8901, "Auth": True, "Absent": None})
    out, err = capsys.readouterr()
    assert out == ""  # stdout belongs to the JSON-RPC stream in stdio mode
    [record] = _records(err)
    assert list(record) == TOP_LEVEL
    assert record["Level"] == "Warning" and record["RenderedMessage"] == "listening"
    assert record["Properties"] == {"SourceContext": "aat-mcp-http", "Port": 8901, "Auth": True}
    stamp = datetime.fromisoformat(record["Timestamp"])
    assert stamp.utcoffset().total_seconds() == 0 and abs(time.time() - stamp.timestamp()) < 60


def test_a_json_line_stays_one_line_whatever_it_holds(as_json, capsys):
    runtime_log.write("aat-mcp", 'two\nlines, a "quote", a \\ and ș', category="Some.Category",
                      fields={"Path": Path("a/b"), "Set": {1}}, exception="Traceback\n  line 2\n")
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    [record] = _records(err)
    assert record["RenderedMessage"] == 'two\nlines, a "quote", a \\ and ș'
    assert record["Exception"] == "Traceback\n  line 2\n"
    assert record["Properties"]["SourceContext"] == "Some.Category"
    assert record["Properties"]["Path"] == str(Path("a/b"))  # no JSON word for it: its text
    assert "ș" in err  # written as it is, not as an escape


def test_a_line_that_cannot_be_written_is_dropped_without_an_error(as_json, monkeypatch):
    class Broken:
        def write(self, _):
            raise OSError("closed")

        def flush(self):
            raise OSError("closed")

    monkeypatch.setattr(runtime_log.sys, "stderr", Broken())
    runtime_log.write("aat-mcp", "text")  # does not raise


# --- the line of a call and of a refusal ------------------------------------------------------------

def test_a_call_is_one_json_line_with_its_values_one_by_one(as_json, msg, monkeypatch, capsys):
    result = {"ok": True, "data": {"rows": ["RESULT-DATA-71c2"]}, "returncode": 0, "stderr": "STDERR-2d9f"}
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: result)
    assert bridge.run_tool("bigtool", "export", {"id": "ARG-VALUE-9e41"}) is result
    err = capsys.readouterr().err
    [record] = _records(err)
    assert list(record) == TOP_LEVEL and record["Level"] == "Information"
    assert re.fullmatch(rf"call msg={MSG} kind=tool tool=bigtool action=export outcome=ok code=- "
                        r"seconds=\d+\.\d{3} exit=0", record["RenderedMessage"])
    properties = record["Properties"]
    seconds = properties.pop("Seconds")
    assert isinstance(seconds, float) and 0 <= seconds < 5
    assert properties == {"SourceContext": "Procesio.Aat.Turn", "MessageId": MSG, "Event": "call",
                          "Kind": "tool", "Tool": "bigtool", "Action": "export", "Outcome": "ok",
                          "ExitCode": 0}
    for never in ("ARG-VALUE-9e41", "RESULT-DATA-71c2", "STDERR-2d9f"):
        assert never not in err


def test_a_failed_call_is_a_warning_and_never_holds_what_the_tool_printed(as_json, monkeypatch, capsys):
    raw = "Traceback: row={'cnp': 'CNP-MADE-UP-1800101'} for RECORD-MADE-UP-51c2"
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "data": None, "returncode": 1, "stderr": raw, "error": {"code": "no_json", "message": raw}})
    bridge.run_tool('odd "name"\\', "two\nlines", {})
    err = capsys.readouterr().err
    [record] = _records(err)
    properties = record["Properties"]
    assert record["Level"] == "Warning" and "MessageId" not in properties  # no id: the key is left out
    assert (properties["Outcome"], properties["Code"], properties["ExitCode"]) == ("error", "no_json", 1)
    assert properties["Message"] == "the tool ended without a JSON answer"
    # A name is kept as it was sent, on one line: JSON needs none of the text line's replacing.
    assert properties["Tool"] == 'odd "name"\\' and properties["Action"] == "two lines"
    assert "MADE-UP" not in err and "Traceback" not in err


def test_a_refusal_is_one_json_line(as_json, msg, capsys):
    bridge.log_refusal("approval_required", "bigtool", "delete", "the action cannot be undone")
    [record] = _records(capsys.readouterr().err)
    assert record["Level"] == "Warning"
    assert record["RenderedMessage"] == (f"refused msg={MSG} tool=bigtool action=delete "
                                         'code=approval_required reason="the action cannot be undone"')
    assert record["Properties"] == {"SourceContext": "Procesio.Aat.Turn", "MessageId": MSG, "Event": "refused",
                                    "Tool": "bigtool", "Action": "delete", "Code": "approval_required",
                                    "Reason": "the action cannot be undone"}


# --- the lines of the HTTP trace --------------------------------------------------------------------

def test_the_lines_about_slow_and_unanswered_requests_are_json(as_json, monkeypatch, capsys):
    monkeypatch.setenv(metrics.SLOW_LOG_ENV, "10")
    metrics.reset()
    metrics.enable()
    try:
        trace = "".join(json.dumps(event) + "\n" for event in (
            {"e": "start", "id": 1, "m": "GET", "p": "/api/Projects?token=QUERY-SECRET-1a", "t": time.time()},
            {"e": "end", "id": 1, "s": 200, "d": 12.5},
            {"e": "start", "id": 2, "m": "POST", "p": "/api/Run", "t": "not a time"}))
        metrics.http_trace(trace, "tool", "bigtool", "export", call_killed=True, msg=MSG)
    finally:
        metrics.enable(False)
        metrics.reset()
    err = capsys.readouterr().err
    slow, unanswered = _records(err)
    assert slow["Level"] == unanswered["Level"] == "Warning"
    assert slow["Properties"] == {
        "SourceContext": "aat-metrics", "Event": "slow_http_request", "MessageId": MSG, "Kind": "tool",
        "Tool": "bigtool", "Action": "export", "RequestMethod": "GET", "RequestPath": "/api/Projects",
        "Outcome": "200", "Seconds": 12.5}
    assert unanswered["Properties"] == {
        "SourceContext": "aat-metrics", "Event": "http_request_never_answered", "MessageId": MSG,
        "Kind": "tool", "Tool": "bigtool", "Action": "export", "RequestMethod": "POST",
        "RequestPath": "/api/Run", "Reason": "call_killed"}
    assert "QUERY-SECRET-1a" not in err


# --- the HTTP transport -----------------------------------------------------------------------------

@pytest.fixture
def httpd(monkeypatch):
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "data": {}, "returncode": 0})
    monkeypatch.setattr(bridge, "_turn_env", lambda *a, **k: {})
    httpd = http_server._Server(("127.0.0.1", 0), http_server._make_handler(None))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _call(request_id, name, arguments):
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}})


def _post(conn, body, headers=None):
    conn.request("POST", "/mcp", body=body, headers={"Content-Type": "application/json", **(headers or {})})
    resp = conn.getresponse()
    return resp.status, resp.read()


def _turn_token(message):
    payload = {"ws": "00000000-0000-0000-0000-000000000000", "u": "7a1c9e42-5b3d-4f60-8a7e-2c4d6f8b0a13",
               "m": message, "exp": int(time.time()) + 600}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{turn_token.PREFIX}.{body}.x.y"


def test_the_access_line_says_what_the_request_was_for(as_json, httpd, capsys):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    try:
        named = {turn_token.HEADER: _turn_token(MSG)}
        assert _post(conn, _call(1, "run_tool", {"tool": "bigtool", "action": "list-processes",
                                                 "args": {"filter": "ARG-VALUE-9e41"}}), named)[0] == 200
        assert _post(conn, _call(2, "capabilities", {"name": "bigtool", "action": "export",
                                                     "search": "SEARCH-TEXT-4c1e"}))[0] == 200
        assert _post(conn, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))[0] == 202
        assert _post(conn, _call(3, "made-up-tool", {"tool": 'x" injected=1', "action": ["a", "list"]}))[0] == 200
        conn.request("GET", "/health")  # answered, and not worth a line
        conn.getresponse().read()
        conn.request("GET", "/mcp")
        conn.getresponse().read()
    finally:
        conn.close()
    err = capsys.readouterr().err
    records = _records(err)
    access = [r for r in records if r["Properties"]["SourceContext"] == "aat-mcp-http"]
    assert [r["Properties"].get("StatusCode") for r in access] == [200, 200, 202, 200, 405]

    first = access[0]["Properties"]
    assert first.pop("Seconds") >= 0
    assert first == {"SourceContext": "aat-mcp-http", "RequestMethod": "POST", "RequestPath": "/mcp",
                     "StatusCode": 200, "MessageId": MSG, "McpMethod": "tools/call", "McpTool": "run_tool",
                     "Tool": "bigtool", "Action": "list-processes"}
    assert re.fullmatch(rf'"POST /mcp HTTP/1\.1" 200 - \d+\.\d{{3}}s msg={MSG} \| tools/call run_tool bigtool '
                        r"list-processes", access[0]["RenderedMessage"])

    second = access[1]["Properties"]
    assert (second["McpTool"], second["Tool"], second["Action"]) == ("capabilities", "bigtool", "export")
    assert "MessageId" not in second
    assert access[2]["Properties"]["McpMethod"] == "notifications/initialized"
    # A tool name that is not one of this server's is `other`; a name that is not text is its type.
    fourth = access[3]["Properties"]
    assert (fourth["McpTool"], fourth["Tool"], fourth["Action"]) == ("other", 'x" injected=1', "<list>")
    # A request that was never read as JSON-RPC has nothing to say beyond the request line.
    assert access[4]["Properties"] == {"SourceContext": "aat-mcp-http", "RequestMethod": "GET",
                                       "RequestPath": "/mcp", "StatusCode": 405}
    assert access[4]["Level"] == "Information"

    # The call itself wrote its own line, in the same format, for the same turn.
    [call] = [r for r in records if r["Properties"].get("Event") == "call"]
    assert call["Properties"]["MessageId"] == MSG and call["Properties"]["SourceContext"] == "Procesio.Aat.Turn"
    # Names only: an argument and a search text never reach the log.
    assert "ARG-VALUE-9e41" not in err and "SEARCH-TEXT-4c1e" not in err


def test_in_the_text_format_the_access_line_carries_the_same_context(httpd, monkeypatch, capsys):
    monkeypatch.delenv(runtime_log.FORMAT_ENV, raising=False)
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    try:
        _post(conn, _call(1, "run_tool", {"tool": "big tool", "action": "export"}),
              {turn_token.HEADER: _turn_token(MSG)})
    finally:
        conn.close()
    lines = capsys.readouterr().err.splitlines()
    [access] = [line for line in lines if line.startswith("[aat-mcp-http] ")]
    assert re.fullmatch(rf'\[aat-mcp-http\] "POST /mcp HTTP/1\.1" 200 - \d+\.\d{{3}}s msg={MSG} \| '
                        r'tools/call run_tool "big tool" export', access)


def test_a_request_that_ends_in_an_exception_is_one_line(as_json, capsys):
    class Failing(BaseHTTPRequestHandler):
        def do_GET(self):
            raise RuntimeError("boom at SECRET-PATH-77")

        def log_message(self, *args):
            pass

    httpd = http_server._Server(("127.0.0.1", 0), Failing)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
        conn.request("GET", "/x")
        with pytest.raises((http.client.HTTPException, ConnectionError)):
            conn.getresponse()
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
    err = capsys.readouterr().err
    assert err.count("\n") == 1  # the traceback is inside the line, not after it
    [record] = _records(err)
    assert record["Level"] == "Error"
    assert record["RenderedMessage"] == "request from 127.0.0.1 ended in RuntimeError"
    assert record["Properties"] == {"SourceContext": "aat-mcp-http", "ExceptionType": "RuntimeError"}
    assert record["Exception"].startswith("Traceback (most recent call last):")
    assert record["Exception"].rstrip().endswith("RuntimeError: boom at SECRET-PATH-77")


def test_what_nobody_caught_is_one_line(as_json, capsys):
    hook = http_server._log_uncaught("aat-mcp-http")
    try:
        raise ValueError("no")
    except ValueError as error:
        hook(type(error), error, error.__traceback__)                      # as sys.excepthook is called
        hook(threading.ExceptHookArgs((type(error), error, error.__traceback__, None)))  # as threading's is
    for record in _records(capsys.readouterr().err):
        assert record["Level"] == "Error" and record["RenderedMessage"] == "uncaught ValueError"
        assert record["Exception"].rstrip().endswith("ValueError: no")


@pytest.mark.parametrize("module", ["bridge.py", "http_server.py", "metrics.py", "server.py"])
def test_the_service_writes_to_stderr_through_the_writer_only(module):
    """One plain line among JSON lines is a line the log store cannot parse. The modules the
    HTTP service is made of have no other way to stderr than runtime_log.write."""
    source = (Path(__file__).resolve().parents[1] / module).read_text(encoding="utf-8")
    assert not re.search(r"sys\.stderr\.write|file\s*=\s*sys\.stderr|traceback\.print_", source)

