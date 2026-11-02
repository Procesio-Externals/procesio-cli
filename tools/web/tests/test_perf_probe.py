"""perf-probe: argument checks, the CDP sequence, and the arithmetic on a fake page."""
from __future__ import annotations

import json

import pytest

from tools.web import main
from tools.web.drivercontract import signature_mismatches
from tools.web.errors import UsageError
from tools.web.handlers import perf


class PerfFakeDriver:
    """Answers the probe's CDP calls and page reads with canned numbers."""

    def __init__(self, *, storage_state=None, headless=True, channel=None, **_kw):
        self.calls: list[tuple] = []
        self.metric_reads = 0
        self.closed = False

    def start(self):
        self.calls.append(("start",))
        return self

    def close(self):
        self.closed = True

    def goto(self, url, *, timeout=None):
        self.calls.append(("goto", url, timeout))

    def wait(self, ms):
        self.calls.append(("wait", ms))

    def cdp(self, method, params=None):
        self.calls.append(("cdp", method, params))
        if method == "Page.addScriptToEvaluateOnNewDocument":
            return {"identifier": str(len(self.calls))}
        if method == "Performance.getMetrics":
            self.metric_reads += 1
            k = 1 if self.metric_reads % 2 else 2   # before, after
            return {"metrics": [
                {"name": "TaskDuration", "value": 1.0 * k}, {"name": "ScriptDuration", "value": 0.2 * k},
                {"name": "LayoutDuration", "value": 0.05 * k}, {"name": "RecalcStyleDuration", "value": 0.1 * k},
                {"name": "LayoutCount", "value": 10 * k}, {"name": "RecalcStyleCount", "value": 40 * k},
                {"name": "Nodes", "value": 300}, {"name": "JSHeapUsedSize", "value": 20 * 1048576}]}
        return {}

    def eval_js(self, script, *, arg=None):
        self.calls.append(("eval", script[:40], arg))
        if script is perf.CALIBRATE_JS:
            return {"ms": 33.0}
        if script is perf.MEASURE_JS:
            return {"t0": 9000, "elapsed": 2000.0, "gaps": [16.7] * 90 + [40.0] * 10, "long": [[9100, 60], [9500, 80]]}
        if script is perf.BOOT_JS:
            return {"now": 11100, "marks": {"header": 1500}, "dcl": 600, "load": 700,
                    "shifts": [[1500, 0.5, [["div.form-builder--form", 120, 226, 900, 900]]], [1520, 0.25], [9200, 0.1]],
                    "long": [[800, 120], [1400, 70], [9100, 60]]}
        return {"perf": "counters"}


def _args(**over):
    parser = main._Parser(prog="web perf-probe")
    perf._perf_args(parser)
    argv = ["--url", "https://example.com/form#ws"]
    for k, v in over.items():
        flag = "--" + k.replace("_", "-")
        argv += [flag] if v is True else [flag, str(v)]
    return parser.parse_args(argv)


def test_fake_driver_matches_the_driver_contract():
    assert signature_mismatches(PerfFakeDriver) == []


def test_baseline_run_reads_frames_main_thread_and_boot():
    out = perf.perf_probe(PerfFakeDriver, _args(settle_ms=10, measure_ms=2000,
                                               expose_js="window.X && X.perf()"))
    (base,) = out["variants"]
    assert base["name"] == "baseline"
    w = base["window"]
    assert w["fps"] == 50.0 and w["frames"] == 100
    assert w["slow_frames_pct"] == 10.0 and w["frame_ms"]["p50"] == 16.7
    assert w["long_tasks"] == {"count": 2, "total_ms": 140, "max_ms": 80}
    mt = w["main_thread"]
    assert mt["task_ms"] == 1000.0 and mt["script_ms"] == 200.0 and mt["style_ms"] == 100.0
    assert mt["other_ms"] == 650.0 and mt["busy_pct"] == 50.0 and mt["layouts"] == 10
    # the boot keeps only what happened before the window started (t0 = 9000)
    b = base["boot"]
    assert b["layout_shift"]["count"] == 2 and b["layout_shift"]["cls"] == 0.75
    assert b["long_tasks"] == {"count": 2, "total_ms": 190, "max_ms": 120}
    assert b["marks"] == {"header": 1500}
    top = b["layout_shift"]["largest"]
    assert top[0]["moved"] == [{"node": "div.form-builder--form", "y": [120, 226], "height": [900, 900]}]
    assert "moved" not in top[1]
    assert base["calibration_ms"] == 33.0 and base["exposed"] == {"perf": "counters"}


def test_each_variant_gets_a_fresh_document_and_its_own_scripts():
    variants = [{"name": "no-bg", "css": ".bg{display:none!important}", "cpu_throttle": 6}]
    drv_holder = {}

    def factory(**kw):
        drv_holder["d"] = PerfFakeDriver(**kw)
        return drv_holder["d"]

    out = perf.perf_probe(factory, _args(variants=json.dumps(variants), settle_ms=1, measure_ms=2000))
    d = drv_holder["d"]
    assert [v["name"] for v in out["variants"]] == ["baseline", "no-bg"]
    gotos = [c[1] for c in d.calls if c[0] == "goto"]
    assert gotos == ["about:blank", "https://example.com/form#ws"] * 2
    rates = [c[2]["rate"] for c in d.calls if c[0] == "cdp" and c[1] == "Emulation.setCPUThrottlingRate"]
    assert rates == [4.0, 6.0]
    added = [c[2]["source"] for c in d.calls if c[0] == "cdp" and c[1] == "Page.addScriptToEvaluateOnNewDocument"]
    assert len(added) == 3 and ".bg{display:none!important}" in added[2]
    removed = [c for c in d.calls if c[0] == "cdp" and c[1] == "Page.removeScriptToEvaluateOnNewDocument"]
    assert len(removed) == 3
    assert out["variants"][1]["vs_baseline"]["fps"] == 0.0
    assert d.closed


def test_warmup_loads_the_page_once_before_the_measured_runs():
    holder = {}

    def factory(**kw):
        holder["d"] = PerfFakeDriver(**kw)
        return holder["d"]

    out = perf.perf_probe(factory, _args(warmup=True, settle_ms=1, measure_ms=2000))
    gotos = [c[1] for c in holder["d"].calls if c[0] == "goto"]
    assert gotos == ["about:blank", "https://example.com/form#ws"] * 2 and out["warmup"] is True


def test_repeat_reports_runs_and_a_median_summary():
    out = perf.perf_probe(PerfFakeDriver, _args(repeat=3, settle_ms=1, measure_ms=2000))
    base = out["variants"][0]
    assert len(base["runs"]) == 3 and base["summary"]["fps"] == 50.0


@pytest.mark.parametrize("over, msg", [
    ({"viewport": "wide"}, "--viewport"),
    ({"repeat": 0}, "--repeat"),
    ({"marks": "[1]"}, "--marks"),
    ({"variants": '[{"css":"x"}]'}, "name"),
    ({"variants": '[{"name":"baseline"}]'}, "baseline"),
    ({"no_baseline": True}, "nothing to measure"),
])
def test_bad_arguments_are_usage_errors(over, msg):
    with pytest.raises(UsageError, match=msg):
        perf.perf_probe(PerfFakeDriver, _args(**over))


def test_url_must_be_http():
    parser = main._Parser(prog="web perf-probe")
    perf._perf_args(parser)
    with pytest.raises(UsageError, match="http"):
        perf.perf_probe(PerfFakeDriver, parser.parse_args(["--url", "file:///etc/passwd"]))


def test_nav_timeout_scales_with_the_cpu_throttle():
    """A throttled load takes proportionally longer, so the default per-load budget scales by the
    rate - a heavy page under 4-6x is no longer cut off at the fixed 30s driver default."""
    holder = {}

    def factory(**kw):
        holder["d"] = PerfFakeDriver(**kw)
        return holder["d"]

    variants = [{"name": "slow", "cpu_throttle": 6}]
    perf.perf_probe(factory, _args(variants=json.dumps(variants), settle_ms=1, measure_ms=2000))
    url_timeouts = [c[2] for c in holder["d"].calls if c[0] == "goto" and c[1] != "about:blank"]
    assert url_timeouts == [120000, 180000]          # baseline at 4x, variant at 6x, base budget 30000


def test_explicit_nav_timeout_overrides_the_auto_scaling():
    holder = {}

    def factory(**kw):
        holder["d"] = PerfFakeDriver(**kw)
        return holder["d"]

    out = perf.perf_probe(factory, _args(nav_timeout=45000, settle_ms=1, measure_ms=2000))
    url_timeouts = [c[2] for c in holder["d"].calls if c[0] == "goto" and c[1] != "about:blank"]
    assert url_timeouts == [45000] and out["nav_timeout"] == 45000
