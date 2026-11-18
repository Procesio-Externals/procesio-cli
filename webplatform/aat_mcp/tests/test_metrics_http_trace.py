"""Where a tool call is stuck: the per-action gauges and errors, and the HTTP requests a tool
noted in its trace file.

The trace file is written by the tool, so half of these tests feed it things a tool should never
write and assert that none of it reaches a label. The other half prove the bridge hands the file
to the subprocess, reads it back, and removes it - without changing what the call returns.

Fakes throughout - no subprocess, no Web-Api, no real registry scan.
"""
from __future__ import annotations

import itertools
import json
import os
import time

import bridge
import metrics
import pytest
from tools._lib import httptrace

P = "procesio_aat_runtime_"
GUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def _tool(name, actions):
    return {"name": name, "description": "", "ready": True, "args": [],
            "actions": [{"name": a, "description": "", "args": []} for a in actions]}


@pytest.fixture
def on(monkeypatch):
    """Recording on, from a clean slate, with the label index of a fake registry."""
    monkeypatch.setattr(bridge, "_scan_registry",
                        lambda: (_ for _ in ()).throw(AssertionError("a call scanned the registry")))
    monkeypatch.setattr(bridge, "_METRIC_NAMES", {})
    bridge._index_metric_names([_tool("bigtool", ["list-processes", "export"])], [])
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    monkeypatch.delenv(metrics.SLOW_LOG_ENV, raising=False)
    metrics.reset()
    metrics.enable()
    yield
    metrics.enable(False)
    metrics.reset()


def _samples() -> dict[str, float]:
    out = {}
    for line in metrics.render().splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.rpartition(" ")
            out[name] = float(value)
    return out


def _lines(*events) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _start(request_id, method="GET", path="/api/Projects", sent_at=None, pid=None):
    """A start line. Without `pid` it is the line of a tool that does not give its process."""
    event = {"e": "start", "id": request_id, "m": method, "p": path,
             "t": time.time() if sent_at is None else sent_at}
    return event if pid is None else {**event, "pid": pid}


def _end(request_id, seconds, status=200, pid=None):
    event = {"e": "end", "id": request_id, "s": status, "d": seconds}
    return event if pid is None else {**event, "pid": pid}


# Two processes of one call: the one the bridge started, and one that process started.
PID, CHILD_PID = 4711, 4712
COUNT = P + "http_request_duration_seconds_count"
SUM = P + "http_request_duration_seconds_sum"
UNFINISHED = P + "http_unfinished_total"


# --- routes ------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, route", [
    ("/api/Projects", "/api/projects"),
    (f"/api/Projects/{GUID}/Versions/12", "/api/projects/{id}/versions/{id}"),
    (f"/api/Projects/{GUID}?secret=1", "/api/projects/{id}"),
    ("/api/file/0123456789abcdef0123", "/api/file/{id}"),
    ("/api/store/my table/rows", "/api/store/{id}/rows"),
    ("/api/x/" + "a" * 41, "/api/x/{id}"),
    ("", "/"),
])
def test_a_route_keeps_the_words_and_drops_the_ids(path, route):
    assert metrics.http_route(path) == route


def test_a_route_is_cut_to_a_fixed_size_and_survives_any_input():
    assert len(metrics.http_route("/" + "/".join(f"s{i}" for i in range(200)))) <= 120
    assert metrics.http_route(None) == "unknown"
    assert metrics.http_route(["/api"]) == "unknown"


# --- the trace of one call ----------------------------------------------------------------------

def test_a_finished_request_is_recorded_by_route_and_status(on):
    metrics.http_trace(_lines(_start(1, "GET", f"/api/Projects/{GUID}"),
                              {"e": "end", "id": 1, "s": 200, "d": 0.3}),
                       "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    labels = '{kind="tool",tool="bigtool",method="GET",route="/api/projects/{id}",status="200"'
    assert s[P + "http_request_duration_seconds_count" + labels + "}"] == 1
    assert s[P + "http_request_duration_seconds_sum" + labels + "}"] == pytest.approx(0.3)
    assert s[P + "http_request_duration_seconds_bucket" + labels + ',le="0.25"}'] == 0
    assert s[P + "http_request_duration_seconds_bucket" + labels + ',le="0.5"}'] == 1
    assert not any(k.startswith(P + "http_unfinished_total") for k in s)


def test_a_request_that_failed_without_an_answer_has_its_error_as_status(on):
    metrics.http_trace(_lines(_start(1), {"e": "end", "id": 1, "x": "timeout", "d": 60.0},
                              _start(2), {"e": "end", "id": 2, "x": "made-up", "d": 1.0}),
                       "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    base = COUNT + '{kind="tool",tool="bigtool",method="GET",route="/api/projects",status='
    assert s[base + '"timeout"}'] == 1
    assert s[base + '"error"}'] == 1  # an error name outside the fixed ones


def test_a_request_with_no_end_in_a_killed_call_is_the_one_it_was_stuck_on(on):
    metrics.http_trace(_lines(_start(1, "GET", "/api/Workspaces"),
                              {"e": "end", "id": 1, "s": 200, "d": 0.1},
                              _start(2, "POST", f"/api/Projects/{GUID}/run", sent_at=time.time() - 170)),
                       "tool", "bigtool", "export", call_killed=True)
    s = _samples()
    assert s[P + 'http_unfinished_total{kind="tool",tool="bigtool",action="export",method="POST",'
                 'route="/api/projects/{id}/run",reason="call_killed"}'] == 1
    waited = P + ('http_request_duration_seconds_sum{kind="tool",tool="bigtool",method="POST",'
                  'route="/api/projects/{id}/run",status="unfinished"}')
    assert 169 <= s[waited] <= 180
    # The finished one is not counted as unfinished.
    assert sum(v for k, v in s.items() if k.startswith(P + "http_unfinished_total")) == 1


def test_a_request_the_tool_stopped_waiting_for_is_tool_gave_up(on):
    metrics.http_trace(_lines(_start(7)), "tool", "bigtool", "export", call_killed=False)
    assert _samples()[P + 'http_unfinished_total{kind="tool",tool="bigtool",action="export",method="GET",'
                          'route="/api/projects",reason="tool_gave_up"}'] == 1


def test_retries_are_counted_by_route(on):
    metrics.http_trace(_lines({"e": "retry", "m": "GET", "p": f"/api/Projects/{GUID}"},
                              {"e": "retry", "m": "GET", "p": f"/api/Projects/{GUID}"}),
                       "tool", "bigtool", "export", call_killed=False)
    assert _samples()[P + 'http_retries_total{kind="tool",tool="bigtool",method="GET",'
                          'route="/api/projects/{id}"}'] == 2


def test_nothing_a_tool_writes_reaches_a_label_unchecked(on):
    text = (
        "not json at all\n"
        '{"e":"start","id":1,"m":"GET","p":"/api/a\\"} 1\\nevil_metric 9"}\n'
        '{"e":"end","id":1,"s":200,"d":0.1}\n'
        + _lines(_start(2, "INVENTED", "/api/b"), {"e": "end", "id": 2, "s": 999, "d": 0.1},
                 _start(3, 7, ["/api/c"]), {"e": "end", "id": 3, "s": True, "d": 0.1},
                 {"e": "end", "id": 99, "s": 200, "d": 0.1},          # an end with no start
                 _start(4), {"e": "end", "id": 4, "s": 200, "d": -5},  # a negative time
                 _start(5), {"e": "end", "id": 5, "s": 200, "d": "soon"},
                 ["a", "list"], {"e": "unknown-event"})
        + '{"e":"start","id":6,"m":"GET","p":"/api/cut-off'            # the line the kill cut
    )
    metrics.http_trace(text, "tool", "bigtool", "export", call_killed=False)

    rendered = metrics.render()
    assert "evil_metric" not in [line.split("{")[0].split(" ")[0] for line in rendered.splitlines()]
    s = _samples()
    count = P + "http_request_duration_seconds_count"
    assert s[count + '{kind="tool",tool="bigtool",method="GET",route="/api/{id}",status="200"}'] == 1
    assert s[count + '{kind="tool",tool="bigtool",method="other",route="/api/b",status="error"}'] == 1
    assert s[count + '{kind="tool",tool="bigtool",method="other",route="unknown",status="error"}'] == 1
    for line in rendered.splitlines():
        assert "INVENTED" not in line and "999" not in line.split(" ")[0]


def test_past_the_cap_a_new_route_is_counted_as_other(on, monkeypatch):
    monkeypatch.setattr(metrics.HTTP_REQUEST_DURATION, "_max", 3)
    events = []
    for i in range(6):
        events += [_start(i, "GET", f"/api/route{'abcdef'[i]}"), {"e": "end", "id": i, "s": 200, "d": 0.1}]
    metrics.http_trace(_lines(*events), "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    count = P + "http_request_duration_seconds_count"
    assert s[count + '{kind="tool",tool="bigtool",method="GET",route="other",status="200"}'] == 3
    assert len([k for k in s if k.startswith(count)]) == 4  # three routes and the overflow row


def test_a_stuck_and_a_slow_request_are_logged_with_their_real_path(on, capsys, monkeypatch):
    monkeypatch.setenv(metrics.SLOW_LOG_ENV, "10")
    metrics.http_trace(_lines(_start(1, "GET", f"/api/Projects/{GUID}?token=SECRET"),
                              {"e": "end", "id": 1, "s": 200, "d": 12.5},
                              _start(2, "POST", f"/api/Projects/{GUID}/run"),
                              _start(3, "GET", "/api/fast"), {"e": "end", "id": 3, "s": 200, "d": 0.1}),
                       "tool", "bigtool", "export", call_killed=True)
    err = capsys.readouterr().err
    assert f"slow http request: bigtool export: GET /api/Projects/{GUID} -> 200 in 12.5s" in err
    assert f"never answered (call_killed): bigtool export: POST /api/Projects/{GUID}/run" in err
    assert "SECRET" not in err and "/api/fast" not in err


def test_log_lines_per_call_are_capped(on, capsys):
    metrics.http_trace(_lines(*[_start(i) for i in range(50)]), "tool", "bigtool", "export", call_killed=True)
    assert capsys.readouterr().err.count("never answered") == metrics.HTTP_LOG_LINES_PER_CALL
    assert _samples()[P + 'http_unfinished_total{kind="tool",tool="bigtool",action="export",method="GET",'
                          'route="/api/projects",reason="call_killed"}'] == 50


def test_off_records_nothing(on):
    metrics.enable(False)
    metrics.http_trace(_lines(_start(1), {"e": "end", "id": 1, "s": 200, "d": 0.1}),
                       "tool", "bigtool", "export", False)
    metrics.enable()
    assert not any(k.startswith(P + "http_") for k in _samples())


def test_past_the_cap_the_overflow_row_of_each_http_metric_keeps_kind_and_tool(on, monkeypatch):
    for capped in (metrics.HTTP_REQUEST_DURATION, metrics.HTTP_RETRIES, metrics.HTTP_UNFINISHED):
        monkeypatch.setattr(capped, "_max", 2)

    def call(kind, tool, action, routes):
        """One call that, on each route, got an answer, sent a request again and left one open."""
        events = []
        for n, letter in enumerate(routes):
            path = f"/api/route{letter}"
            events += [_start(n, "GET", path), _end(n, 0.1), {"e": "retry", "m": "GET", "p": path},
                       # Sent at no known time, so it is counted as unfinished and not timed.
                       {"e": "start", "id": 100 + n, "m": "POST", "p": path}]
        metrics.http_trace(_lines(*events), kind, tool, action, call_killed=True)

    call("tool", "bigtool", "export", "ab")           # the three metrics are full now
    call("tool", "bigtool", "export", "cd")
    call("agent", "bigtool", "export", "e")           # the same name as an agent: rows of its own
    call("agent", "orchestrator", "drive", "f")
    call("tool", "bigtool", "list-processes", "g")    # another action of the first tool

    s = _samples()
    for labels, calls in (('kind="tool",tool="bigtool"', 3), ('kind="agent",tool="bigtool"', 1),
                          ('kind="agent",tool="orchestrator"', 1)):
        assert s[COUNT + "{" + labels + ',method="GET",route="other",status="200"}'] == calls
        assert s[P + "http_retries_total{" + labels + ',method="GET",route="other"}'] == calls
        # Past the cap an unfinished request gives up its action as well as its route.
        assert s[UNFINISHED + "{" + labels + ',action="other",method="POST",route="other",'
                 'reason="call_killed"}'] == calls
    for name in (COUNT, P + "http_retries_total", UNFINISHED):
        assert len([k for k in s if k.startswith(name)]) == 5, name  # two routes, three overflow rows
    assert not any(f"/api/route{letter}" in k for k in s for letter in "cdefg")


# --- which start an end belongs to ----------------------------------------------------------------
#
# A request is named by the process that sent it and the number that process gave it. Every
# process counts from 1 and the processes of one call share the file, so the number alone names
# two requests at once.

@pytest.mark.parametrize("child_ends_first", [True, False])
def test_two_processes_that_use_the_same_number_at_once_are_two_requests(on, child_ends_first):
    ends = [_end(1, 0.2, 201, pid=CHILD_PID), _end(1, 3.0, 200, pid=PID)]
    metrics.http_trace(_lines(_start(1, "GET", f"/api/Projects/{GUID}", pid=PID),
                              _start(1, "POST", "/api/Workspaces", pid=CHILD_PID),
                              *(ends if child_ends_first else reversed(ends))),
                       "agent", "orchestrator", "drive", call_killed=False)
    s = _samples()
    parent = '{kind="agent",tool="orchestrator",method="GET",route="/api/projects/{id}",status="200"}'
    child = '{kind="agent",tool="orchestrator",method="POST",route="/api/workspaces",status="201"}'
    # Each request keeps its own route, its own status and its own time.
    assert s[COUNT + parent] == 1 and s[SUM + parent] == pytest.approx(3.0)
    assert s[COUNT + child] == 1 and s[SUM + child] == pytest.approx(0.2)
    assert len([k for k in s if k.startswith(COUNT)]) == 2
    assert not any(k.startswith(UNFINISHED) for k in s)


@pytest.mark.parametrize("stuck_one_started_first", [True, False])
def test_a_request_one_process_left_open_is_not_answered_by_another_process_with_its_number(
        on, stuck_one_started_first):
    starts = [_start(1, "POST", f"/api/Projects/{GUID}/run", sent_at=time.time() - 170, pid=PID),
              _start(1, "GET", "/api/Workspaces", pid=CHILD_PID)]
    metrics.http_trace(_lines(*(starts if stuck_one_started_first else reversed(starts)),
                              _end(1, 0.1, pid=CHILD_PID)),
                       "agent", "orchestrator", "drive", call_killed=True)
    s = _samples()
    # One never ended, and it is the first one's route that says where the call was stuck...
    assert s[UNFINISHED + '{kind="agent",tool="orchestrator",action="drive",method="POST",'
             'route="/api/projects/{id}/run",reason="call_killed"}'] == 1
    assert sum(v for k, v in s.items() if k.startswith(UNFINISHED)) == 1
    assert 169 <= s[SUM + '{kind="agent",tool="orchestrator",method="POST",'
                    'route="/api/projects/{id}/run",status="unfinished"}'] <= 180
    # ...and one was answered: the other process's.
    answered = '{kind="agent",tool="orchestrator",method="GET",route="/api/workspaces",status="200"}'
    assert s[COUNT + answered] == 1 and s[SUM + answered] == pytest.approx(0.1)
    assert len([k for k in s if k.startswith(COUNT)]) == 2


def test_lines_without_a_pid_are_paired_by_number(on):
    metrics.http_trace(_lines(_start(1, "GET", f"/api/Projects/{GUID}"), _start(2, "POST", "/api/Workspaces"),
                              _end(2, 0.2, 201), _end(1, 3.0)),
                       "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    first = '{kind="tool",tool="bigtool",method="GET",route="/api/projects/{id}",status="200"}'
    second = '{kind="tool",tool="bigtool",method="POST",route="/api/workspaces",status="201"}'
    assert s[COUNT + first] == 1 and s[SUM + first] == pytest.approx(3.0)
    assert s[COUNT + second] == 1 and s[SUM + second] == pytest.approx(0.2)
    assert not any(k.startswith(UNFINISHED) for k in s)


def test_a_process_that_gives_no_pid_is_told_apart_from_one_that_does(on):
    metrics.http_trace(_lines(_start(1, "GET", f"/api/Projects/{GUID}"),
                              _start(1, "POST", "/api/Workspaces", pid=CHILD_PID),
                              _end(1, 0.2, 201, pid=CHILD_PID), _end(1, 3.0)),
                       "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    without = '{kind="tool",tool="bigtool",method="GET",route="/api/projects/{id}",status="200"}'
    with_pid = '{kind="tool",tool="bigtool",method="POST",route="/api/workspaces",status="201"}'
    assert s[COUNT + without] == 1 and s[SUM + without] == pytest.approx(3.0)
    assert s[COUNT + with_pid] == 1 and s[SUM + with_pid] == pytest.approx(0.2)
    assert not any(k.startswith(UNFINISHED) for k in s)


@pytest.mark.parametrize("pid", [None, PID])
def test_a_second_start_under_the_same_key_keeps_the_first_as_a_request_that_never_ended(on, capsys, pid):
    metrics.http_trace(_lines(_start(1, "POST", f"/api/Projects/{GUID}/run", sent_at=time.time() - 170, pid=pid),
                              _start(1, "GET", "/api/Workspaces", pid=pid),
                              _end(1, 0.1, pid=pid)),
                       "tool", "bigtool", "export", call_killed=True)
    s = _samples()
    assert s[UNFINISHED + '{kind="tool",tool="bigtool",action="export",method="POST",'
             'route="/api/projects/{id}/run",reason="call_killed"}'] == 1
    assert sum(v for k, v in s.items() if k.startswith(UNFINISHED)) == 1
    assert 169 <= s[SUM + '{kind="tool",tool="bigtool",method="POST",'
                    'route="/api/projects/{id}/run",status="unfinished"}'] <= 180
    # The end belongs to the start that is still open: the second one.
    assert s[COUNT + '{kind="tool",tool="bigtool",method="GET",route="/api/workspaces",status="200"}'] == 1
    assert len([k for k in s if k.startswith(COUNT)]) == 2
    err = capsys.readouterr().err
    assert f"never answered (call_killed): bigtool export: POST /api/Projects/{GUID}/run" in err
    assert err.count("never answered") == 1


def test_two_starts_under_the_same_key_that_never_ended_are_both_counted(on):
    metrics.http_trace(_lines(_start(1, "POST", f"/api/Projects/{GUID}/run", pid=PID),
                              _start(1, "GET", "/api/Workspaces", pid=PID)),
                       "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    base = UNFINISHED + '{kind="tool",tool="bigtool",action="export",method='
    assert s[base + '"POST",route="/api/projects/{id}/run",reason="tool_gave_up"}'] == 1
    assert s[base + '"GET",route="/api/workspaces",reason="tool_gave_up"}'] == 1
    assert sum(v for k, v in s.items() if k.startswith(UNFINISHED)) == 2


NOT_A_PID = ["4711", "", True, False, 4711.0, None, [4711], {"n": 4711}]


@pytest.mark.parametrize("pid", NOT_A_PID)
def test_a_pid_that_is_not_an_integer_is_treated_as_absent(on, pid):
    """An odd pid on one line of a request and none on the other: still the same request. A pid
    that cannot be a dictionary key (a list) must not cost the rest of the trace either."""
    metrics.http_trace(_lines({**_start(1, "GET", "/api/Projects"), "pid": pid}, _end(1, 0.3),
                              _start(2, "POST", "/api/Workspaces"), {**_end(2, 0.2, 201), "pid": pid},
                              {**_start(3, "PUT", "/api/Forms"), "pid": pid}, {**_end(3, 0.1, 204), "pid": pid},
                              _start(4, "DELETE", "/api/Forms", pid=PID), _end(4, 0.4, 204, pid=PID)),
                       "tool", "bigtool", "export", call_killed=False)
    s = _samples()
    base = COUNT + '{kind="tool",tool="bigtool",method='
    assert s[base + '"GET",route="/api/projects",status="200"}'] == 1
    assert s[base + '"POST",route="/api/workspaces",status="201"}'] == 1
    assert s[base + '"PUT",route="/api/forms",status="204"}'] == 1
    assert s[base + '"DELETE",route="/api/forms",status="204"}'] == 1  # the lines after it are still read
    assert not any(k.startswith(UNFINISHED) for k in s)


@pytest.mark.parametrize("pid", NOT_A_PID)
def test_a_pid_that_is_not_an_integer_does_not_close_the_request_of_a_real_process(on, pid):
    metrics.http_trace(_lines(_start(1, "POST", f"/api/Projects/{GUID}/run", pid=1),
                              {**_end(1, 0.1), "pid": pid}),
                       "tool", "bigtool", "export", call_killed=True)
    s = _samples()
    assert s[UNFINISHED + '{kind="tool",tool="bigtool",action="export",method="POST",'
             'route="/api/projects/{id}/run",reason="call_killed"}'] == 1
    assert not any(k.startswith(COUNT) and 'status="200"' in k for k in s)


@pytest.mark.parametrize("event, key", [
    ({"pid": 4711, "id": 1}, (4711, 1)),
    ({"id": 1}, (None, 1)),
    ({"pid": None, "id": 1}, (None, 1)),
    ({"pid": "4711", "id": 1}, (None, 1)),
    ({"pid": True, "id": 1}, (None, 1)),
    ({"pid": 4711.0, "id": 1}, (None, 1)),
    ({"pid": [4711], "id": 1}, (None, 1)),
    ({"pid": {"n": 4711}, "id": 1}, (None, 1)),
    ({"pid": 4711}, None),                    # no number: nothing to pair
    ({"pid": 4711, "id": "1"}, None),
    ({"pid": 4711, "id": True}, None),
    ({"pid": 4711, "id": 1.0}, None),
    ({"pid": 4711, "id": [1]}, None),
])
def test_a_request_key_is_the_pid_and_the_number_and_any_input_gets_an_answer(event, key):
    got = metrics._request_key(event)
    assert got == key
    # 1 == True == 1.0 in Python, so the types are compared too: a bool must not pass for a pid.
    assert got is None or [type(part) for part in got] == [type(part) for part in key]
    hash(got)  # usable as a dictionary key, whatever the line held


# --- the bridge: handing the file to the subprocess and reading it back ---------------------------

def test_the_subprocess_gets_a_trace_file_and_what_it_wrote_is_recorded(on, monkeypatch):
    seen = {}

    def fake_run_tool(tool, argv, **k):
        path = k["env"][httptrace.ENV]
        seen["path"] = path
        seen["exists_during"] = os.path.isfile(path)
        with open(path, "a", encoding="utf-8") as f:   # what a traced tool would append
            f.write(_lines(_start(1, "GET", "/api/Workspaces", pid=PID), _end(1, 0.2, pid=PID)))
        return {"ok": True, "data": {"n": 1}, "error": None}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    assert bridge.run_tool("bigtool", "export", {}) == {"ok": True, "data": {"n": 1}, "error": None}

    assert seen["exists_during"] and not os.path.exists(seen["path"])  # read, then removed
    assert _samples()[P + 'http_request_duration_seconds_count{kind="tool",tool="bigtool",method="GET",'
                          'route="/api/workspaces",status="200"}'] == 1


def test_a_call_that_timed_out_reports_the_request_it_left_open(on, monkeypatch):
    def fake_run_tool(tool, argv, **k):
        with open(k["env"][httptrace.ENV], "a", encoding="utf-8") as f:
            f.write(_lines(_start(1, "POST", f"/api/Projects/{GUID}/run", pid=PID)))
        return {"ok": False, "data": None, "error": {"code": "timeout", "message": "timeout after 180s"}}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    bridge.run_tool("bigtool", "export", {})
    s = _samples()
    assert s[P + 'http_unfinished_total{kind="tool",tool="bigtool",action="export",method="POST",'
                 'route="/api/projects/{id}/run",reason="call_killed"}'] == 1
    assert s[P + 'action_errors_total{kind="tool",tool="bigtool",action="export",code="timeout"}'] == 1


def test_what_httptrace_writes_for_two_processes_is_read_back_as_two_requests(on, monkeypatch):
    """The lines are written here by the module a tool uses, not by hand: the writer and the
    reader have to agree on what names a request."""
    here = os.getpid()

    def fake_run_tool(tool, argv, **k):
        monkeypatch.setenv(httptrace.ENV, k["env"][httptrace.ENV])
        monkeypatch.setattr(httptrace, "_ids", itertools.count(1))
        waiting = httptrace.start("GET", f"https://h/api/Projects/{GUID}")
        # A process the tool started while it waits: its own pid, and its own count from 1.
        with monkeypatch.context() as child:
            child.setattr(httptrace.os, "getpid", lambda: here + 1)
            child.setattr(httptrace, "_ids", itertools.count(1))
            httptrace.end(httptrace.start("POST", "https://h/api/Workspaces"), status=201)
        httptrace.end(waiting, status=200)
        return {"ok": True, "data": {}, "error": None}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    bridge.run_tool("bigtool", "export", {})
    s = _samples()
    assert s[COUNT + '{kind="tool",tool="bigtool",method="GET",route="/api/projects/{id}",status="200"}'] == 1
    assert s[COUNT + '{kind="tool",tool="bigtool",method="POST",route="/api/workspaces",status="201"}'] == 1
    assert not any(k.startswith(UNFINISHED) for k in s)


def test_a_tool_and_an_agent_with_the_same_name_keep_their_http_requests_apart(on, monkeypatch):
    twin = [_tool("twin", ["status"])]  # one name that is both a tool and an agent
    bridge._index_metric_names(twin, twin)

    def traced(seconds):
        """A run that got one answer after `seconds`, sent one request again and left one open."""
        def fake(name, argv, **k):
            with open(k["env"][httptrace.ENV], "a", encoding="utf-8") as f:
                f.write(_lines(_start(1, pid=PID), _end(1, seconds, pid=PID),
                               {"e": "retry", "m": "GET", "p": "/api/Projects"},
                               {"e": "start", "pid": PID, "id": 2, "m": "POST", "p": f"/api/Projects/{GUID}/run"}))
            return {"ok": True, "data": {}, "error": None}
        return fake

    monkeypatch.setattr(bridge.runner, "run_tool", traced(0.3))
    monkeypatch.setattr(bridge.runner, "run_agent", traced(2.0))
    bridge.run_tool("twin", "status", {})
    bridge.run_tool("twin", "status", {})
    bridge.run_agent("twin", "status", {})

    s = _samples()
    # The same name, action, method, route and status: only `kind` tells the rows apart.
    for kind, calls, seconds in (("tool", 2, 0.6), ("agent", 1, 2.0)):
        answered = f'{{kind="{kind}",tool="twin",method="GET",route="/api/projects",status="200"}}'
        assert s[COUNT + answered] == calls
        assert s[SUM + answered] == pytest.approx(seconds)
        assert s[P + f'http_retries_total{{kind="{kind}",tool="twin",method="GET",'
                 'route="/api/projects"}'] == calls
        assert s[UNFINISHED + f'{{kind="{kind}",tool="twin",action="status",method="POST",'
                 'route="/api/projects/{id}/run",reason="tool_gave_up"}'] == calls
    for name in (COUNT, P + "http_retries_total", UNFINISHED):
        assert len([k for k in s if k.startswith(name)]) == 2, name


def test_with_metrics_off_the_subprocess_environment_is_untouched(on, monkeypatch):
    metrics.enable(False)
    seen = {}
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: seen.update(env=k.get("env")) or {"ok": True})
    bridge.run_tool("bigtool", "export", {})
    assert not (seen["env"] or {}).get(httptrace.ENV)


def test_a_trace_file_that_cannot_be_made_does_not_fail_the_call(on, monkeypatch):
    monkeypatch.setattr(bridge.tempfile, "mkstemp",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    seen = {}
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: seen.update(env=k.get("env")) or {"ok": True, "data": 1})
    assert bridge.run_tool("bigtool", "export", {}) == {"ok": True, "data": 1}
    assert not (seen["env"] or {}).get(httptrace.ENV)


def test_an_exception_in_the_call_still_removes_the_trace_file(on, monkeypatch):
    seen = {}

    def boom(tool, argv, **k):
        seen["path"] = k["env"][httptrace.ENV]
        raise RuntimeError("runner broke")

    monkeypatch.setattr(bridge.runner, "run_tool", boom)
    with pytest.raises(RuntimeError, match="runner broke"):
        bridge.run_tool("bigtool", "export", {})
    assert not os.path.exists(seen["path"])


# --- what is running now ------------------------------------------------------------------------

def test_a_running_call_shows_its_action_and_its_age_and_is_gone_when_it_ends(on, monkeypatch):
    during = {}

    def fake_run_tool(tool, argv, **k):
        time.sleep(0.05)
        during.update(_samples())
        return {"ok": True, "data": {}, "error": None}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    bridge.run_tool("bigtool", "export", {})

    assert during[P + 'action_in_progress{kind="tool",tool="bigtool",action="export"}'] == 1
    assert during[P + 'action_oldest_in_progress_age_seconds{kind="tool",tool="bigtool",action="export"}'] >= 0.05
    after = _samples()
    assert not any(k.startswith(P + "action_in_progress") for k in after)
    assert not any(k.startswith(P + "action_oldest_in_progress_age_seconds") for k in after)


def test_a_tool_and_an_agent_with_the_same_name_are_running_on_separate_rows(on, monkeypatch):
    twin = [_tool("twin", ["status"])]  # one name that is both a tool and an agent
    bridge._index_metric_names(twin, twin)
    during = {}

    def fake_run_agent(agent, argv, **k):
        time.sleep(0.05)
        during.update(_samples())
        return {"ok": True, "data": {}, "error": None}

    def fake_run_tool(tool, argv, **k):
        time.sleep(0.05)
        bridge.run_agent("twin", "status", {})  # the tool call is still running while this one is
        return {"ok": True, "data": {}, "error": None}

    monkeypatch.setattr(bridge.runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    bridge.run_tool("twin", "status", {})

    tool, agent = '{kind="tool",tool="twin",action="status"}', '{kind="agent",tool="twin",action="status"}'
    age = P + "action_oldest_in_progress_age_seconds"
    assert during[P + "action_in_progress" + tool] == 1
    assert during[P + "action_in_progress" + agent] == 1
    assert during[age + agent] >= 0.05
    assert during[age + tool] > during[age + agent]  # each row has the age of its own call
    assert len([k for k in during if k.startswith(P + "action_in_progress")]) == 2
    assert len([k for k in during if k.startswith(age)]) == 2
    after = _samples()
    assert not any(k.startswith(P + "action_in_progress") for k in after)
    assert not any(k.startswith(age) for k in after)


def test_an_invented_action_is_unknown_in_every_per_action_metric(on, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: {"ok": False, "error": {"code": "nonzero_exit", "message": "x"}})
    bridge.run_tool("bigtool", "drop-everything-" + GUID, {})
    s = _samples()
    assert s[P + 'action_errors_total{kind="tool",tool="bigtool",action="unknown",code="nonzero_exit"}'] == 1
    assert GUID not in metrics.render()
