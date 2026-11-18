"""Runtime metrics: the exposition format, the label rules, the listener and the call sites.

Two things here are worth more than the rest. Label values: a tool name and an action arrive
from a model, so the tests send invented ones and assert they never reach the output. And
behaviour: recording must leave every result, exception and cache decision as it was, so each
call-site test also checks what the call returned.

Fakes throughout - no subprocess, no Web-Api, no real registry scan. The listener tests bind an
ephemeral loopback port.

A call must never scan the registry for its labels (a scan is seconds on a cold cache, and the
caller would pay for it), so the `on` fixture turns any scan into a failure.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import types
import urllib.error
from http.server import ThreadingHTTPServer

import bridge
import gate
import http_server
import metrics
import pytest
import server
import turn_credentials
from dashboard.server import runner
from tools._lib import accounting

P = "procesio_aat_runtime_"


def _tool(name, actions):
    return {"name": name, "description": "", "ready": True, "args": [],
            "actions": [{"name": a, "description": "", "args": []} for a in actions]}


FAKE_TOOLS = [_tool("bigtool", ["list-processes", "export"]), _tool("flat", [])]
FAKE_AGENTS = [_tool("orchestrator", ["intake", "drive"])]


@pytest.fixture
def on(monkeypatch):
    """Recording on, from a clean slate, with the label index of a fake registry; off and clean
    again afterwards. A registry scan fails the test."""
    monkeypatch.setattr(bridge, "_scan_registry",
                        lambda: (_ for _ in ()).throw(AssertionError("a call scanned the registry")))
    monkeypatch.setattr(bridge, "_METRIC_NAMES", {})
    bridge._index_metric_names(FAKE_TOOLS, FAKE_AGENTS)
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    metrics.reset()
    metrics.enable()
    yield
    metrics.enable(False)
    metrics.reset()


def _samples(text: str | None = None) -> dict[str, float]:
    """{sample name with its labels: value} of an exposition text (the live one by default)."""
    out = {}
    for line in (metrics.render() if text is None else text).splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.rpartition(" ")
            out[name] = float(value)
    return out


def _ok(*a, **k):
    return {"ok": True, "data": {}, "error": None}


# --- exposition format ----------------------------------------------------------------------

def test_each_family_has_help_and_type_before_its_samples():
    reg = metrics.Registry()
    hits = metrics.Counter(reg, "demo_hits_total", "Hits so far.", ("code",))
    level = metrics.Gauge(reg, "demo_level", "Level now.")
    hits.add(2, "ok")
    hits.add(1, "ok")
    level.set(4)
    level.add(-1.5)
    assert reg.render() == (
        "# HELP demo_hits_total Hits so far.\n"
        "# TYPE demo_hits_total counter\n"
        'demo_hits_total{code="ok"} 3\n'
        "# HELP demo_level Level now.\n"
        "# TYPE demo_level gauge\n"
        "demo_level 2.5\n")


def test_label_values_and_help_are_escaped():
    reg = metrics.Registry()
    c = metrics.Counter(reg, "demo_total", 'A "quoted" back\\slash\nand a line.', ("v",))
    c.add(1, 'a"b\\c\nd')
    text = reg.render()
    # HELP escapes backslash and newline only; a label value also escapes the quote.
    assert '# HELP demo_total A "quoted" back\\\\slash\\nand a line.\n' in text
    assert 'demo_total{v="a\\"b\\\\c\\nd"} 1\n' in text
    assert len(text.splitlines()) == 3  # the newline in the value did not break the line


def test_histogram_buckets_are_cumulative_inclusive_and_end_with_inf():
    reg = metrics.Registry()
    h = metrics.Histogram(reg, "demo_seconds", "Time.", ("k",), buckets=(0.1, 1, 5))
    for value in (0.05, 0.1, 0.5, 1, 4.9, 70):  # 0.1 and 1 sit exactly on a bound
        h.observe(value, "x")
    s = _samples(reg.render())
    assert s['demo_seconds_bucket{k="x",le="0.1"}'] == 2   # 0.05 and 0.1 itself: le is inclusive
    assert s['demo_seconds_bucket{k="x",le="1"}'] == 4     # + 0.5 and 1
    assert s['demo_seconds_bucket{k="x",le="5"}'] == 5     # + 4.9
    assert s['demo_seconds_bucket{k="x",le="+Inf"}'] == 6  # + 70, above every bound
    assert s['demo_seconds_count{k="x"}'] == 6
    assert s['demo_seconds_sum{k="x"}'] == pytest.approx(76.55)
    assert "# TYPE demo_seconds histogram" in reg.render()


def test_a_histogram_series_is_independent_of_the_other_label_sets():
    reg = metrics.Registry()
    h = metrics.Histogram(reg, "demo_seconds", "Time.", ("k",), buckets=(1,))
    h.observe(0.5, "a")
    h.observe(3, "b")
    s = _samples(reg.render())
    assert (s['demo_seconds_bucket{k="a",le="1"}'], s['demo_seconds_bucket{k="b",le="1"}']) == (1, 0)
    assert s['demo_seconds_bucket{k="b",le="+Inf"}'] == 1


def test_summary_has_sum_and_count_and_no_quantiles():
    reg = metrics.Registry()
    s = metrics.Summary(reg, "demo_seconds", "Time.", ("tool",))
    s.observe(1.5, "a")
    s.observe(2.5, "a")
    assert reg.render() == (
        "# HELP demo_seconds Time.\n"
        "# TYPE demo_seconds summary\n"
        'demo_seconds_sum{tool="a"} 4\n'
        'demo_seconds_count{tool="a"} 2\n')


def test_a_counter_cannot_go_down_and_a_wrong_label_count_is_refused():
    reg = metrics.Registry()
    c = metrics.Counter(reg, "demo_total", "x", ("a", "b"))
    with pytest.raises(ValueError):
        c.add(-1, "x", "y")
    with pytest.raises(ValueError):
        c.add(1, "only-one")


_SAMPLE = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{[a-zA-Z_][a-zA-Z0-9_]*="(?:[^"\\\n]|\\["\\n])*"'
                     r'(,[a-zA-Z_][a-zA-Z0-9_]*="(?:[^"\\\n]|\\["\\n])*")*\})? '
                     r'(-?[0-9.]+(e[+-]?[0-9]+)?|[+-]Inf|NaN)$')


def test_the_live_output_is_well_formed(on, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_tool", _ok)
    bridge.run_tool("bigtool", "export", {})
    metrics.refusal("approval_required")
    metrics.credential_cache(metrics.PROCESIO_KEY, True)
    text = metrics.render()
    assert text.endswith("\n") and "\n\n" not in text
    declared = {}
    for line in text.splitlines():
        if line.startswith("# TYPE "):
            _, _, name, kind = line.split(" ")
            declared[name] = kind
        elif not line.startswith("# HELP "):
            assert _SAMPLE.match(line), line
            name = line.split("{")[0].split(" ")[0]
            family = re.sub(r"_(bucket|sum|count)$", "", name)
            assert name in declared or family in declared, f"{name} has no TYPE line above it"
    assert declared == {
        P + "tool_call_duration_seconds": "histogram",
        P + "action_duration_seconds": "summary",
        P + "mcp_request_duration_seconds": "histogram",
        P + "credential_fetch_duration_seconds": "histogram",
        P + "credential_cache_total": "counter",
        P + "tool_calls_in_progress": "gauge",
        P + "tool_errors_total": "counter",
        P + "refusals_total": "counter",
        P + "action_errors_total": "counter",
        P + "action_in_progress": "gauge",
        P + "action_oldest_in_progress_age_seconds": "gauge",
        P + "http_request_duration_seconds": "histogram",
        P + "http_retries_total": "counter",
        P + "http_unfinished_total": "counter",
    }


def test_tool_and_mcp_histograms_reach_300_seconds_and_credential_fetch_stops_at_120():
    step = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
    assert metrics.CREDENTIAL_FETCH_DURATION.buckets == step
    assert metrics.TOOL_CALL_DURATION.buckets == step + (180, 300)
    assert metrics.MCP_REQUEST_DURATION.buckets == step + (180, 300)


def test_concurrent_updates_are_not_lost():
    reg = metrics.Registry()
    c = metrics.Counter(reg, "demo_total", "x", ("k",))
    h = metrics.Histogram(reg, "demo_seconds", "x", buckets=(1,))

    def work():
        for _ in range(2000):
            c.add(1, "a")
            h.observe(0.5)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    s = _samples(reg.render())
    assert s['demo_total{k="a"}'] == 16000
    assert s['demo_seconds_bucket{le="1"}'] == s["demo_seconds_count"] == 16000


# --- label capping ---------------------------------------------------------------------------

def test_a_full_capped_metric_sends_new_label_sets_to_the_overflow_row():
    reg = metrics.Registry()
    s = metrics.Summary(reg, "demo_seconds", "x", ("tool", "action"),
                        max_series=2, overflow=lambda key: (key[0], metrics.OTHER))
    s.observe(1, "t", "a")
    s.observe(1, "t", "b")
    s.observe(1, "t", "c")   # the third distinct set: over the cap
    s.observe(1, "t", "d")   # joins the same overflow row
    s.observe(1, "t", "a")   # a row that already exists keeps counting
    got = _samples(reg.render())
    assert got['demo_seconds_count{tool="t",action="a"}'] == 2
    assert got['demo_seconds_count{tool="t",action="b"}'] == 1
    assert got['demo_seconds_count{tool="t",action="other"}'] == 2
    assert not any('"c"' in k or '"d"' in k for k in got)


def test_the_action_metric_stops_growing_at_its_cap(on):
    assert metrics.ACTION_SERIES_CAP == 2000
    for i in range(metrics.ACTION_SERIES_CAP + 50):
        metrics.ACTION_DURATION.observe(0.1, "tool", "bigtool", f"a{i}")
    counts = [k for k in _samples() if k.startswith(P + "action_duration_seconds_count")]
    assert len(counts) == metrics.ACTION_SERIES_CAP + 1  # the cap, plus the one overflow row
    assert _samples()[P + 'action_duration_seconds_count{kind="tool",tool="bigtool",action="other"}'] == 50


def _failed_call(kind, tool, action, code="timeout"):
    """One failed call recorded straight in the metrics, with labels the test chose."""
    with metrics.tool_call(kind, lambda: (tool, action)) as seen:
        seen.result = {"ok": False, "error": {"code": code, "message": "x"}}


def test_past_the_cap_the_overflow_row_of_each_action_metric_keeps_kind_and_tool(on, monkeypatch):
    monkeypatch.setattr(metrics.ACTION_DURATION, "_max", 2)
    monkeypatch.setattr(metrics.ACTION_ERRORS, "_max", 2)
    _failed_call("tool", "bigtool", "a0")
    _failed_call("tool", "bigtool", "a1")           # both metrics are full now
    _failed_call("tool", "bigtool", "a2")
    _failed_call("tool", "bigtool", "a3")           # joins the row a2 opened
    _failed_call("agent", "bigtool", "a4")          # the same name as an agent: a row of its own
    _failed_call("agent", "orchestrator", "a5")
    _failed_call("tool", "bigtool", "a6", code="no_json")
    _failed_call("tool", "bigtool", "a0")           # a row that already exists keeps counting

    s = _samples()
    duration = P + "action_duration_seconds_count"
    assert s[duration + '{kind="tool",tool="bigtool",action="a0"}'] == 2
    assert s[duration + '{kind="tool",tool="bigtool",action="other"}'] == 3
    assert s[duration + '{kind="agent",tool="bigtool",action="other"}'] == 1
    assert s[duration + '{kind="agent",tool="orchestrator",action="other"}'] == 1
    assert len([k for k in s if k.startswith(duration)]) == 5  # a0, a1 and the three overflow rows
    errors = P + "action_errors_total"
    assert s[errors + '{kind="tool",tool="bigtool",action="a0",code="timeout"}'] == 2
    assert s[errors + '{kind="tool",tool="bigtool",action="other",code="timeout"}'] == 2
    assert s[errors + '{kind="tool",tool="bigtool",action="other",code="no_json"}'] == 1  # the code stays
    assert s[errors + '{kind="agent",tool="bigtool",action="other",code="timeout"}'] == 1
    assert s[errors + '{kind="agent",tool="orchestrator",action="other",code="timeout"}'] == 1
    assert len([k for k in s if k.startswith(errors)]) == 6
    assert not any(f'action="a{i}"' in k for k in s for i in range(2, 7))


# --- off by default --------------------------------------------------------------------------

def test_nothing_is_recorded_and_no_label_is_resolved_while_metrics_are_off(monkeypatch):
    assert metrics.enabled() is False
    metrics.reset()
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    monkeypatch.setattr(bridge, "_metric_labels",
                        lambda *a: (_ for _ in ()).throw(AssertionError("resolved a label")))
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": True, "data": {"x": 1}})
    assert bridge.run_tool("bigtool", "export", {}) == {"ok": True, "data": {"x": 1}}
    metrics.refusal("approval_required")
    metrics.credential_cache(metrics.PROCESIO_KEY, False)
    metrics.credential_fetch(metrics.PROCESIO_KEY, metrics.clock(), None)
    with metrics.mcp_request({"method": "tools/list"}, frozenset()) as seen:
        seen.response = {"result": {}}
    # Only the two in-progress rows a reset seeds; nothing else has a sample.
    assert _samples() == {P + 'tool_calls_in_progress{kind="agent"}': 0,
                          P + 'tool_calls_in_progress{kind="tool"}': 0}


# --- run_tool / run_agent --------------------------------------------------------------------

def test_run_tool_records_duration_outcome_and_action(on, monkeypatch):
    ticks = iter([100.0, 100.3])  # start, stop: the call "took" 0.3 s
    monkeypatch.setattr(metrics, "clock", lambda: next(ticks))
    during = {}

    def fake_run_tool(tool, argv, **k):
        during.update(_samples())
        return {"ok": True, "data": {"n": 1}, "error": None}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    assert bridge.run_tool("bigtool", "list-processes", {"top": 5}) == {
        "ok": True, "data": {"n": 1}, "error": None}

    s = _samples()
    labels = '{kind="tool",tool="bigtool",outcome="ok"'
    assert s[P + "tool_call_duration_seconds_count" + labels + "}"] == 1
    assert s[P + "tool_call_duration_seconds_sum" + labels + "}"] == pytest.approx(0.3)
    assert s[P + "tool_call_duration_seconds_bucket" + labels + ',le="0.25"}'] == 0
    assert s[P + "tool_call_duration_seconds_bucket" + labels + ',le="0.5"}'] == 1
    assert s[P + "tool_call_duration_seconds_bucket" + labels + ',le="+Inf"}'] == 1
    action = '{kind="tool",tool="bigtool",action="list-processes"}'
    assert s[P + "action_duration_seconds_count" + action] == 1
    assert s[P + "action_duration_seconds_sum" + action] == pytest.approx(0.3)
    assert during[P + 'tool_calls_in_progress{kind="tool"}'] == 1
    assert s[P + 'tool_calls_in_progress{kind="tool"}'] == 0
    assert not any(k.startswith(P + "tool_errors_total") for k in s)


def test_a_failed_call_is_an_error_with_the_runner_code(on, monkeypatch):
    failed = {"ok": False, "data": None, "error": {"code": "timeout", "message": "timeout after 180s"}}
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: failed)
    assert bridge.run_tool("bigtool", "export", {}) is failed
    s = _samples()
    assert s[P + 'tool_call_duration_seconds_count{kind="tool",tool="bigtool",outcome="error"}'] == 1
    assert s[P + 'tool_errors_total{kind="tool",tool="bigtool",code="timeout"}'] == 1


def test_a_code_a_tool_made_up_is_counted_as_other(on, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "error": {"code": "ws-7f3a-not-found", "message": "x"}})
    bridge.run_tool("bigtool", "export", {})
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {"ok": False, "error": "a string"})
    bridge.run_tool("bigtool", "export", {})
    text = metrics.render()
    assert _samples(text)[P + 'tool_errors_total{kind="tool",tool="bigtool",code="other"}'] == 2
    assert "ws-7f3a-not-found" not in text


@pytest.mark.parametrize("tool, action, want_tool, want_action", [
    ("bigtool", "export", "bigtool", "export"),
    ("bigtool", "drop-everything-9f1c", "bigtool", "unknown"),   # a real tool, an invented action
    ("bigtool", None, "bigtool", "none"),                        # no action given
    ("flat", None, "flat", "none"),                              # a flat tool has none to give
    ("invented-tool-51ab", "export", "unknown", "unknown"),      # an action means nothing without its tool
    ("orchestrator", "intake", "unknown", "unknown"),            # an agent's name is not a tool's
    ('x"}\nevil_total 1', "export", "unknown", "unknown"),       # an attempt to write a sample line
    (["bigtool"], {"a": 1}, "unknown", "unknown"),               # not even strings
])
def test_tool_and_action_labels_come_from_the_registry_only(on, monkeypatch, tool, action,
                                                           want_tool, want_action):
    monkeypatch.setattr(bridge.runner, "run_tool", _ok)
    assert bridge.run_tool(tool, action, {}) == _ok()
    text = metrics.render()
    s = _samples(text)
    assert s[P + 'action_duration_seconds_count'
                 f'{{kind="tool",tool="{want_tool}",action="{want_action}"}}'] == 1
    assert sum(v for k, v in s.items() if k.startswith(P + "tool_call_duration_seconds_count")) == 1
    assert f'tool="{want_tool}"' in text
    for sent in ("drop-everything-9f1c", "invented-tool-51ab", "evil_total"):
        assert sent not in text


def test_run_agent_is_recorded_as_kind_agent(on, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_agent", _ok)
    bridge.run_agent("orchestrator", "intake", {"request": "x"})
    s = _samples()
    assert s[P + 'tool_call_duration_seconds_count{kind="agent",tool="orchestrator",outcome="ok"}'] == 1
    assert s[P + 'action_duration_seconds_count{kind="agent",tool="orchestrator",action="intake"}'] == 1
    assert s[P + 'tool_calls_in_progress{kind="agent"}'] == 0


TWIN = [_tool("twin", ["status"])]  # one name that is both a tool and an agent, as several are


def test_a_tool_and_an_agent_with_the_same_name_are_timed_on_separate_rows(on, monkeypatch):
    bridge._index_metric_names(TWIN, TWIN)
    ticks = iter([100.0, 100.3, 200.0, 202.0])  # the tool call took 0.3 s, the agent call 2 s
    monkeypatch.setattr(metrics, "clock", lambda: next(ticks))
    monkeypatch.setattr(bridge.runner, "run_tool", _ok)
    monkeypatch.setattr(bridge.runner, "run_agent", _ok)
    assert bridge.run_tool("twin", "status", {}) == _ok()
    assert bridge.run_agent("twin", "status", {}) == _ok()

    s = _samples()
    tool = '{kind="tool",tool="twin",action="status"}'
    agent = '{kind="agent",tool="twin",action="status"}'
    assert s[P + "action_duration_seconds_count" + tool] == 1
    assert s[P + "action_duration_seconds_sum" + tool] == pytest.approx(0.3)
    assert s[P + "action_duration_seconds_count" + agent] == 1
    assert s[P + "action_duration_seconds_sum" + agent] == pytest.approx(2.0)
    assert len([k for k in s if k.startswith(P + "action_duration_seconds_count")]) == 2


def test_a_tool_and_an_agent_with_the_same_name_fail_on_separate_rows(on, monkeypatch):
    bridge._index_metric_names(TWIN, TWIN)
    failed = {"ok": False, "data": None, "error": {"code": "timeout", "message": "timeout after 180s"}}
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: failed)
    monkeypatch.setattr(bridge.runner, "run_agent", lambda *a, **k: failed)
    assert bridge.run_tool("twin", "status", {}) is failed
    assert bridge.run_tool("twin", "status", {}) is failed
    assert bridge.run_agent("twin", "status", {}) is failed

    s = _samples()
    # The same name, the same action, the same code: only `kind` tells the two apart.
    assert s[P + 'tool_errors_total{kind="tool",tool="twin",code="timeout"}'] == 2
    assert s[P + 'tool_errors_total{kind="agent",tool="twin",code="timeout"}'] == 1
    assert s[P + 'action_errors_total{kind="tool",tool="twin",action="status",code="timeout"}'] == 2
    assert s[P + 'action_errors_total{kind="agent",tool="twin",action="status",code="timeout"}'] == 1
    assert len([k for k in s if k.startswith(P + "tool_errors_total")]) == 2
    assert len([k for k in s if k.startswith(P + "action_errors_total")]) == 2


def test_a_call_that_raises_still_raises_and_is_counted(on, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no free tool uid")

    monkeypatch.setattr(bridge.runner, "run_tool", boom)
    with pytest.raises(RuntimeError, match="no free tool uid"):
        bridge.run_tool("bigtool", "export", {})
    s = _samples()
    assert s[P + 'tool_call_duration_seconds_count{kind="tool",tool="bigtool",outcome="error"}'] == 1
    assert s[P + 'tool_errors_total{kind="tool",tool="bigtool",code="exception"}'] == 1
    assert s[P + 'tool_calls_in_progress{kind="tool"}'] == 0


def test_a_failing_label_lookup_costs_the_label_not_the_call(on):
    with metrics.tool_call("tool", lambda: 1 / 0) as seen:
        seen.result = {"ok": True}
    assert _samples()[P + 'tool_call_duration_seconds_count{kind="tool",tool="unknown",outcome="ok"}'] == 1


def test_a_call_before_the_first_registry_scan_is_labelled_unknown(on, monkeypatch):
    monkeypatch.setattr(bridge, "_METRIC_NAMES", {})
    monkeypatch.setattr(bridge.runner, "run_tool", _ok)
    bridge.run_tool("bigtool", "export", {})
    assert _samples()[P + 'action_duration_seconds_count{kind="tool",tool="unknown",action="unknown"}'] == 1


# --- the label index ---------------------------------------------------------------------------

@pytest.fixture
def real_scan(monkeypatch):
    """The real _scan_registry over a fake registry module, with empty caches."""
    monkeypatch.setattr(bridge.registry, "list_tools", lambda: FAKE_TOOLS)
    monkeypatch.setattr(bridge.registry, "list_agents", lambda index=None: FAKE_AGENTS)
    monkeypatch.setattr(bridge.registry, "list_skills", lambda: [])
    monkeypatch.setattr(bridge, "_REG_CACHE", {})
    monkeypatch.setattr(bridge, "_METRIC_NAMES", {})
    yield
    metrics.enable(False)
    metrics.reset()


def test_a_registry_scan_refreshes_the_label_index_only_while_metrics_are_on(real_scan):
    assert bridge._scan_registry() == (FAKE_TOOLS, FAKE_AGENTS, [])
    assert bridge._METRIC_NAMES == {}  # off: the scan does nothing extra
    bridge._REG_CACHE.clear()
    metrics.enable()
    assert bridge._scan_registry() == (FAKE_TOOLS, FAKE_AGENTS, [])  # and answers the same
    assert bridge._METRIC_NAMES == {
        "tool": {"bigtool": {"list-processes", "export"}, "flat": frozenset()},
        "agent": {"orchestrator": {"intake", "drive"}}}
    assert bridge._metric_labels("tool", "bigtool", "export") == ("bigtool", "export")
    assert bridge._metric_labels("agent", "bigtool", "export") == ("unknown", "unknown")


def test_the_warm_up_scan_fills_the_index_in_the_background(real_scan):
    metrics.enable()
    thread = bridge.warm_metric_labels()
    thread.join(10)
    assert thread.daemon and not thread.is_alive()
    assert bridge._metric_labels("agent", "orchestrator", "drive") == ("orchestrator", "drive")


def test_a_failed_warm_up_scan_is_logged_and_nothing_else(real_scan, monkeypatch, capsys):
    monkeypatch.setattr(bridge.registry, "list_tools",
                        lambda: (_ for _ in ()).throw(OSError("manifest unreadable")))
    bridge.warm_metric_labels().join(10)
    assert "registry scan for the metric labels failed (OSError)" in capsys.readouterr().err
    assert bridge._METRIC_NAMES == {}


def test_no_workspace_or_user_id_reaches_the_output(on, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_tool", _ok)
    user, ws = bridge.set_user("user-4c1e"), bridge.set_workspace("workspace-9d2b")
    try:
        bridge.run_tool("bigtool", "export", {"workspace-id": "workspace-9d2b"})
    finally:
        bridge.reset_workspace(ws)
        bridge.reset_user(user)
    text = metrics.render()
    assert "user-4c1e" not in text and "workspace-9d2b" not in text


def test_the_wrapper_keeps_the_signature_callers_use(on, monkeypatch):
    seen = {}
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: seen.update(tool=tool, argv=argv) or _ok())
    # server._run passes credential by keyword, and only when the model named one.
    bridge.run_tool("bigtool", "export", {"id": "7"}, credential="mine")
    assert seen == {"tool": "bigtool", "argv": ["export", "--id", "7"]}
    # ...and a caller that names every argument is served, and labelled, the same way.
    monkeypatch.setattr(bridge.runner, "run_agent", _ok)
    assert bridge.run_tool(tool="bigtool", action="list-processes", args={}) == _ok()
    assert bridge.run_agent(agent="orchestrator", action="intake", args={}) == _ok()
    s = _samples()
    assert s[P + 'action_duration_seconds_count{kind="tool",tool="bigtool",action="list-processes"}'] == 1
    assert s[P + 'action_duration_seconds_count{kind="agent",tool="orchestrator",action="intake"}'] == 1
    assert bridge.run_tool.__name__ == "run_tool" and bridge.run_agent.__name__ == "run_agent"


# --- refusals --------------------------------------------------------------------------------

def _api_key_manifest(name="bigtool"):
    return types.SimpleNamespace(name=name, secrets=["api-key"],
                                 procesio_credential=types.SimpleNamespace(is_api_key=lambda: True))


def test_the_gate_refusals_are_counted_and_never_reach_the_bridge(on, monkeypatch):
    monkeypatch.setattr(server.bridge, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    payload, is_error = server._call_tool("run_tool", {"tool": "google-mail", "action": "send-message"})
    assert "approval_required" in payload and is_error is False
    monkeypatch.setattr(gate, "deny_irreversible_env", lambda: True)
    payload, is_error = server._call_tool("run_tool_confirmed",
                                          {"tool": "google-mail", "action": "send-message"})
    assert "refused" in payload and is_error is True
    s = _samples()
    assert s[P + 'refusals_total{code="approval_required"}'] == 1
    assert s[P + 'refusals_total{code="irreversible_denied"}'] == 1
    assert not any(k.startswith(P + "tool_call_duration_seconds") for k in s)


def test_a_managed_turn_refusal_is_counted(on, monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_agent",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    token = bridge.set_managed_turn(True)
    try:
        res = bridge.run_agent("orchestrator", "drive", {})
    finally:
        bridge.reset_managed_turn(token)
    assert res["refused"]["reason"] == "managed_turn"
    s = _samples()
    assert s[P + 'refusals_total{code="managed_turn"}'] == 1
    assert s[P + 'tool_errors_total{kind="agent",tool="orchestrator",code="managed_turn"}'] == 1


def test_a_workspace_refusal_is_counted(on, monkeypatch):
    monkeypatch.setattr(bridge, "_secret_manifests", lambda kind, name: [_api_key_manifest()])
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    token = bridge.set_turn_token("a-turn-token")
    try:
        res = bridge.run_tool("bigtool", "export", {"workspace-id": "11111111-2222-3333-4444-555555555555"})
    finally:
        bridge.reset_turn_token(token)
    assert res["error"]["code"] == "workspace_out_of_turn"
    text = metrics.render()
    s = _samples(text)
    assert s[P + 'refusals_total{code="workspace_out_of_turn"}'] == 1
    assert s[P + 'tool_errors_total{kind="tool",tool="bigtool",code="workspace_out_of_turn"}'] == 1
    assert "11111111-2222" not in text


def test_a_turn_without_a_key_is_refused_once_and_counted_once(on, monkeypatch):
    monkeypatch.setattr(bridge, "_secret_manifests", lambda kind, name: [_api_key_manifest()])
    monkeypatch.setattr(bridge.turn_credentials, "fetch_key",
                        lambda token: turn_credentials.ProcesioKey(message="No key."))
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    token = bridge.set_turn_token("a-turn-token")
    try:
        res = bridge.run_tool("bigtool", "export", {})
    finally:
        bridge.reset_turn_token(token)
    assert res["error"]["code"] == "procesio_key_unavailable"
    s = _samples()
    assert s[P + 'refusals_total{code="procesio_key_unavailable"}'] == 1
    assert s[P + 'tool_errors_total{kind="tool",tool="bigtool",code="procesio_key_unavailable"}'] == 1


def test_a_key_revoked_after_the_tool_ran_is_an_error_not_a_refusal(on, monkeypatch):
    """The tool was started, so nothing was refused before execution: the same code, but only
    on the error counter."""
    key = turn_credentials.ProcesioKey(key="k", value="v")
    monkeypatch.setattr(bridge, "_secret_manifests", lambda kind, name: [_api_key_manifest()])
    monkeypatch.setattr(bridge, "_procesio_profile", lambda manifest, key, secrets: None)
    monkeypatch.setattr(bridge.turn_credentials, "fetch_key", lambda token: key)
    monkeypatch.setattr(bridge.turn_credentials, "recheck_key",
                        lambda token: turn_credentials.ProcesioKey(message="Revoked."))
    monkeypatch.setattr(bridge.runner, "run_tool", lambda *a, **k: {
        "ok": False, "error": {"code": "unauthorized", "message": "401"}})
    token = bridge.set_turn_token("a-turn-token")
    try:
        res = bridge.run_tool("bigtool", "export", {})
    finally:
        bridge.reset_turn_token(token)
    assert res["error"]["code"] == "procesio_key_unavailable"
    s = _samples()
    assert s[P + 'tool_errors_total{kind="tool",tool="bigtool",code="procesio_key_unavailable"}'] == 1
    assert not any(k.startswith(P + "refusals_total") for k in s)


def test_an_unlisted_refusal_code_is_counted_as_other(on):
    metrics.refusal("something-new")
    metrics.refusal(["not", "a", "string"])
    assert _samples()[P + 'refusals_total{code="other"}'] == 2


# --- the codes the label is checked against ---------------------------------------------------

def test_every_code_this_server_produces_is_a_known_error_code():
    """The fixed set is written down in metrics.py; these are the places it is copied from.
    A code added there and not here would be reported as `other`."""
    assert bridge._AUTH_FAILURE_CODES <= metrics.ERROR_CODES
    base = {"returncode": 1, "stdout": "", "stderr": "x", "timed_out": False}
    produced = {runner._normalize({**base, "timed_out": True, "returncode": -1})["error"]["code"],
                runner._normalize(base)["error"]["code"],
                runner._normalize({**base, "stdout": '{"a": 1}'})["error"]["code"],
                bridge._no_key_refusal("x")["error"]["code"]}
    assert produced == {"timeout", "no_json", "nonzero_exit", "procesio_key_unavailable"}
    assert produced <= metrics.ERROR_CODES
    assert server._FINAL_REFUSAL_CODES <= metrics.REFUSAL_CODES


# --- MCP requests ----------------------------------------------------------------------------

NAMES = frozenset(t["name"] for t in server.TOOLS)


@pytest.mark.parametrize("message, response, want", [
    ({"method": "initialize"}, {"result": {}}, 'method="initialize",mcp_tool="none",outcome="ok"'),
    ({"method": "tools/list"}, {"result": {"tools": []}}, 'method="tools/list",mcp_tool="none",outcome="ok"'),
    ({"method": "tools/call", "params": {"name": "run_tool"}}, {"result": {"isError": False}},
     'method="tools/call",mcp_tool="run_tool",outcome="ok"'),
    ({"method": "tools/call", "params": {"name": "run_tool"}}, {"result": {"isError": True}},
     'method="tools/call",mcp_tool="run_tool",outcome="error"'),
    ({"method": "tools/call", "params": {"name": "rm -rf"}}, {"result": {"isError": True}},
     'method="tools/call",mcp_tool="unknown",outcome="error"'),
    ({"method": "tools/call", "params": "not an object"}, {"result": {"isError": True}},
     'method="tools/call",mcp_tool="unknown",outcome="error"'),
    ({"method": "resources/list-4e2a"}, {"error": {"code": -32601}},
     'method="other",mcp_tool="none",outcome="error"'),
    ({"method": "notifications/initialized"}, None, 'method="other",mcp_tool="none",outcome="ok"'),
    ({"method": ["a", "list"]}, {"error": {}}, 'method="other",mcp_tool="none",outcome="error"'),
])
def test_mcp_request_labels_are_a_closed_set(on, message, response, want):
    with metrics.mcp_request(message, NAMES) as seen:
        seen.response = response
    text = metrics.render()
    assert _samples(text)[P + "mcp_request_duration_seconds_count{" + want + "}"] == 1
    assert "rm -rf" not in text and "4e2a" not in text


def test_an_exception_during_dispatch_is_an_error_and_still_raised(on):
    with pytest.raises(AttributeError):
        with metrics.mcp_request({"method": "tools/list"}, NAMES):
            raise AttributeError("boom")
    assert _samples()[P + 'mcp_request_duration_seconds_count{method="tools/list",mcp_tool="none",outcome="error"}'] == 1


def test_the_mcp_tool_label_set_is_the_published_tools():
    assert http_server._MCP_TOOL_NAMES == {"capabilities", "run_tool", "run_tool_confirmed",
                                           "run_agent", "run_agent_confirmed", "get_skill"}


def _post(port, body, token=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        conn.request("POST", "/mcp", body=json.dumps(body), headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_the_http_server_records_each_request_and_answers_as_before(on):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), http_server._make_handler("s3cret"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        status, raw = _post(port, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="s3cret")
        assert status == 200
        assert {t["name"] for t in json.loads(raw)["result"]["tools"]} == NAMES
        status, raw = _post(port, {"jsonrpc": "2.0", "id": 2, "method": "nope"}, token="s3cret")
        assert status == 200 and json.loads(raw)["error"]["code"] == -32601
        # The bearer check is where it was: a request without the token is not dispatched.
        assert _post(port, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})[0] == 401
    finally:
        httpd.shutdown()
        httpd.server_close()
    s = _samples()
    assert s[P + 'mcp_request_duration_seconds_count{method="tools/list",mcp_tool="none",outcome="ok"}'] == 1
    assert s[P + 'mcp_request_duration_seconds_count{method="other",mcp_tool="none",outcome="error"}'] == 1


# --- credentials -----------------------------------------------------------------------------

@pytest.fixture
def webapi(on, monkeypatch):
    """Web-Api configured, an empty turn memory, and a `_get` whose answers a test queues."""
    monkeypatch.setenv("AAT_WEBAPI_URL", "http://webapi.invalid")
    monkeypatch.setenv("AAT_WEBAPI_SERVICE_CODE", "code")
    monkeypatch.delenv("AAT_TURN_CACHE_IDLE_SECONDS", raising=False)
    monkeypatch.setattr(turn_credentials, "_CACHE", {})
    answers, calls = [], []

    def fake_get(url, headers, empty):
        calls.append(url)
        return answers.pop(0)

    monkeypatch.setattr(turn_credentials, "_get", fake_get)
    return types.SimpleNamespace(answers=answers, calls=calls)


def _http_error(code):
    return urllib.error.HTTPError("http://webapi.invalid", code, "x", {}, None)


def test_a_key_is_fetched_once_per_turn_and_then_served_from_memory(webapi):
    webapi.answers.append(({"configured": True, "key": "k", "value": "v"}, None))
    assert turn_credentials.fetch_key("turn-1").key == "k"
    assert turn_credentials.fetch_key("turn-1").key == "k"
    assert turn_credentials.fetch_key("turn-1").key == "k"
    assert len(webapi.calls) == 1  # the cache decides exactly as before
    text = metrics.render()
    s = _samples(text)
    assert s[P + 'credential_cache_total{source="procesio_key",result="miss"}'] == 1
    assert s[P + 'credential_cache_total{source="procesio_key",result="hit"}'] == 2
    assert s[P + 'credential_fetch_duration_seconds_count{source="procesio_key",outcome="ok"}'] == 1
    assert "turn-1" not in text


@pytest.mark.parametrize("answer, outcome", [
    ((None, _http_error(404)), "refused"),            # Web-Api did not accept the turn token
    ((None, _http_error(500)), "error"),
    ((None, urllib.error.URLError("down")), "error"),
    (({"configured": False}, None), "ok"),            # it answered; the user just has no key
])
def test_key_fetch_outcomes(webapi, answer, outcome):
    webapi.answers.append(answer)
    assert turn_credentials.fetch_key("turn-2").key is None
    s = _samples()
    assert s[P + f'credential_fetch_duration_seconds_count{{source="procesio_key",outcome="{outcome}"}}'] == 1


def test_an_unconfigured_runtime_makes_no_request_and_records_no_fetch(webapi, monkeypatch):
    monkeypatch.delenv("AAT_WEBAPI_URL")
    assert turn_credentials.fetch_key("turn-3").key is None
    s = _samples()
    assert webapi.calls == []
    assert s[P + 'credential_cache_total{source="procesio_key",result="miss"}'] == 1
    assert not any(k.startswith(P + "credential_fetch_duration_seconds") for k in s)


def test_tool_credentials_are_fetched_once_per_turn_and_a_refusal_is_told_apart(webapi):
    key = turn_credentials.ProcesioKey(key="k", value="v")
    webapi.answers.append(({"configured": True, "key": "k", "value": "v"}, None))
    turn_credentials.fetch_key("turn-4")  # opens the turn's memory
    webapi.answers.append(([{"id": "1", "name": "mine", "values": {"token": "t"}}], None))
    first = turn_credentials.fetch_tool_credentials(key, "tpl", "api.example.com", "turn-4")
    again = turn_credentials.fetch_tool_credentials(key, "tpl", "api.example.com", "turn-4")
    assert again is first and len(webapi.calls) == 2

    webapi.answers.append((None, _http_error(403)))
    assert turn_credentials.fetch_tool_credentials(key, "tpl", None, None).refused is True
    webapi.answers.append((None, _http_error(502)))
    assert turn_credentials.fetch_tool_credentials(key, "tpl", None, None).refused is False

    text = metrics.render()
    s = _samples(text)
    assert s[P + 'credential_cache_total{source="tool_credentials",result="miss"}'] == 3
    assert s[P + 'credential_cache_total{source="tool_credentials",result="hit"}'] == 1
    fetch = P + "credential_fetch_duration_seconds_count"
    assert s[fetch + '{source="tool_credentials",outcome="ok"}'] == 1
    assert s[fetch + '{source="tool_credentials",outcome="refused"}'] == 1
    assert s[fetch + '{source="tool_credentials",outcome="error"}'] == 1
    assert "api.example.com" not in text and "tpl" not in text


# --- the listener ----------------------------------------------------------------------------

def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.getheader("Content-Type"), resp.read().decode("utf-8")
    finally:
        conn.close()


def test_the_listener_serves_metrics_and_nothing_else(on):
    metrics.refusal("approval_required")
    httpd = metrics.serve("127.0.0.1", 0)
    try:
        port = httpd.server_address[1]
        status, ctype, body = _get(port, "/metrics")
        assert status == 200
        assert ctype == "text/plain; version=0.0.4; charset=utf-8"
        assert body == metrics.render()
        assert P + 'refusals_total{code="approval_required"} 1\n' in body
        assert _get(port, "/metrics?name=x")[0] == 200
        for path in ("/", "/health", "/mcp", "/metrics/x", "/metricsx"):
            assert _get(port, path)[0] == 404, path
        for method in ("POST", "PUT", "DELETE", "HEAD"):  # GET only, even on the right path
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                conn.request(method, "/metrics", body=b"{}" if method != "HEAD" else None)
                assert conn.getresponse().status == 404, method
            finally:
                conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize("value", [None, "", "0", " 0 ", "-1", "abc"])
def test_the_listener_stays_off_without_a_port(monkeypatch, value):
    monkeypatch.setattr(metrics, "serve", lambda *a: (_ for _ in ()).throw(AssertionError("bound")))
    if value is None:
        monkeypatch.delenv(metrics.PORT_ENV, raising=False)
    else:
        monkeypatch.setenv(metrics.PORT_ENV, value)
    assert metrics.start_listener("127.0.0.1") is None
    assert metrics.enabled() is False


def test_a_port_that_cannot_be_bound_is_logged_and_does_not_raise(monkeypatch, capsys):
    def taken(host, port):
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(metrics, "serve", taken)
    monkeypatch.setenv(metrics.PORT_ENV, "9090")
    assert metrics.start_listener("0.0.0.0") is None
    assert metrics.enabled() is False
    assert "cannot listen on 0.0.0.0:9090" in capsys.readouterr().err


def test_the_listener_starts_on_the_configured_port_and_turns_recording_on(monkeypatch):
    with socket.socket() as probe:  # a port that was free a moment ago
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv(metrics.PORT_ENV, str(port))
    httpd = metrics.start_listener("127.0.0.1")
    try:
        assert httpd is not None and metrics.enabled() is True
        assert _get(port, "/metrics")[0] == 200
        assert any(t.name == "aat-metrics" and t.daemon for t in threading.enumerate())
    finally:
        metrics.enable(False)
        metrics.reset()
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


# --- accounting is left alone -----------------------------------------------------------------

def test_metrics_do_not_take_the_accounting_sink(on, monkeypatch):
    """The accounting seam has one sink slot, meant for the platform's. Metrics time the call
    themselves, so that slot stays free and AAT_ACCOUNTING_DEBUG still selects the debug sink."""
    assert accounting._sink is None
    monkeypatch.setenv("AAT_ACCOUNTING_DEBUG", "1")
    assert accounting._resolve_sink() is accounting._debug_sink
    events = []
    accounting.set_sink(events.append)
    try:
        monkeypatch.setattr(bridge.runner, "run_tool", _ok)
        bridge.run_tool("bigtool", "export", {})
    finally:
        accounting.set_sink(None)
    assert [e["event"] for e in events] == ["acquire", "consume"]
    assert set(events[1]) == {"kind", "ws", "user", "run_id", "multiplicator", "tool", "action",
                              "event", "execution_ms", "ts"}
