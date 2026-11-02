"""perf-probe - what a page costs a slower machine, measured in a real browser.

Opens a URL in Chromium, slows the page's main thread with CDP CPU throttling (4x
is roughly a budget laptop next to a recent MacBook), lets the page boot, then
measures a window: frame rate and frame-time percentiles from requestAnimationFrame,
long tasks, and the main thread's script / layout / style time from CDP
Performance.getMetrics. The boot is measured too: when each --marks selector first
appeared, and every layout shift (the pop-in a viewer sees while a runtime
restyles a page that has already drawn).

Variants rerun the same measurement with CSS / JS injected from the first frame,
so one call answers "what does turning X off buy": the first run is always the
page as served (``baseline``), then each variant on a fresh navigation.

What it cannot see: GPU raster and compositing. Headless Chromium rasterizes in
software, so a heavy paint (a full-screen canvas, a backdrop blur) shows up as a
lower frame rate and busier frames, not as main-thread time.
"""
from __future__ import annotations

import argparse
import json
import statistics

from tools.web import api
from tools.web.actiondef import ActionDef
from tools.web.driver import DEFAULT_NAV_TIMEOUT_MS
from tools.web.errors import UsageError

# Installed before any page script runs: layout shifts and long tasks from the
# very start of the navigation, and the first time each marked selector shows.
COLLECTOR_JS = r"""
(() => {
  if (window.__perfProbe) { return; }
  const P = window.__perfProbe = { shifts: [], long: [], marks: {} };
  const marks = __MARKS__;
  // which element moved: tag#id[data-element-id].class.class, enough to find the rule that moved it
  const describe = (n) => {
    if (!n || !n.tagName) { return (n && n.nodeName) || '?'; }
    let d = n.tagName.toLowerCase();
    if (n.id) { d += '#' + n.id; }
    const de = n.getAttribute('data-element-id');
    if (de) { d += '[data-element-id=' + de.slice(0, 8) + ']'; }
    const cl = typeof n.className === 'string' ? n.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
    if (cl.length) { d += '.' + cl.join('.'); }
    return d;
  };
  try {
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) {
        if (e.hadRecentInput) { continue; }
        const src = (e.sources || []).slice(0, 3).map((x) => [describe(x.node), Math.round(x.previousRect.y),
          Math.round(x.currentRect.y), Math.round(x.previousRect.height), Math.round(x.currentRect.height)]);
        P.shifts.push([Math.round(e.startTime), e.value, src]);
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) { P.noShifts = true; }
  try {
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) { P.long.push([Math.round(e.startTime), Math.round(e.duration)]); }
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) { P.noLong = true; }
  const names = Object.keys(marks);
  if (!names.length) { return; }
  const poll = () => {
    for (const k of names) {
      if (k in P.marks) { continue; }
      try { if (document.querySelector(marks[k])) { P.marks[k] = Math.round(performance.now()); } } catch (e) { P.marks[k] = null; }
    }
    if (Object.keys(P.marks).length < names.length && performance.now() < 60000) { requestAnimationFrame(poll); }
  };
  requestAnimationFrame(poll);
})();
"""

# A variant's CSS lands as a <style> before the page's own sheets exist, so its
# rules need !important to win over the page's later ones.
VARIANT_JS = r"""
(() => {
  const css = __CSS__, js = __JS__;
  if (css) {
    const add = () => {
      const s = document.createElement('style');
      s.setAttribute('data-perf-probe', '');
      s.textContent = css;
      (document.head || document.documentElement).appendChild(s);
    };
    if (document.documentElement) { add(); } else { document.addEventListener('DOMContentLoaded', add); }
  }
  if (js) { try { (0, eval)(js); } catch (e) { window.__perfProbeVariantError = String(e); } }
})();
"""

BOOT_JS = r"""
() => {
  const P = window.__perfProbe || { shifts: [], long: [], marks: {} };
  const nav = (performance.getEntriesByType('navigation') || [])[0] || {};
  return {
    now: Math.round(performance.now()),
    marks: P.marks, shifts: P.shifts, long: P.long,
    dcl: Math.round(nav.domContentLoadedEventEnd || 0), load: Math.round(nav.loadEventEnd || 0),
    variantError: window.__perfProbeVariantError || null,
    observers: { shifts: !P.noShifts, long: !P.noLong }
  };
}
"""

# One fixed workload, timed in the page: proves the throttling took and gives a
# number to compare machines by (lower is faster).
CALIBRATE_JS = r"""
() => {
  const t0 = performance.now();
  let x = 0;
  for (let i = 0; i < 2e6; i++) { x = (x + i * 7) % 1000003; }
  return { ms: +(performance.now() - t0).toFixed(1), x: x };
}
"""

MEASURE_JS = r"""
async (o) => {
  const P = window.__perfProbe || { long: [] };
  if (o.during) { try { (0, eval)(o.during); } catch (e) { P.duringError = String(e); } }
  const t0 = performance.now();
  const gaps = [];
  await new Promise((done) => {
    let last = 0;
    const tick = (ts) => {
      if (last) { gaps.push(+(ts - last).toFixed(2)); }
      last = ts;
      if (performance.now() - t0 < o.ms) { requestAnimationFrame(tick); } else { done(); }
    };
    requestAnimationFrame(tick);
  });
  const t1 = performance.now();
  await new Promise((r) => setTimeout(r, 60));   // observer callbacks arrive after the task
  const long = P.long.filter((x) => x[0] >= t0 && x[0] <= t1);
  return { t0: Math.round(t0), elapsed: t1 - t0, gaps: gaps, long: long, duringError: P.duringError || null };
}
"""

# CDP Performance.getMetrics: cumulative seconds (durations) and counters.
_DURATIONS = {"TaskDuration": "task", "ScriptDuration": "script",
              "LayoutDuration": "layout", "RecalcStyleDuration": "style"}
_COUNTS = {"LayoutCount": "layouts", "RecalcStyleCount": "style_recalcs"}
_GAUGES = {"Nodes": "dom_nodes", "JSHeapUsedSize": "js_heap_mb",
           "JSEventListeners": "event_listeners", "Frames": "frames"}

SLOW_FRAME_MS = 34.0   # slower than 30 fps
JANK_FRAME_MS = 50.0   # a hitch a viewer notices


def _metrics(driver) -> dict:
    res = driver.cdp("Performance.getMetrics") or {}
    return {m["name"]: m["value"] for m in res.get("metrics", []) if "name" in m}


def _pct(sorted_vals: list, p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = min(len(sorted_vals) - 1, max(0, int(round(p / 100.0 * (len(sorted_vals) - 1)))))
    return round(sorted_vals[k], 1)


def frame_stats(gaps: list, elapsed_ms: float) -> dict:
    """Frame rate and frame-time distribution from requestAnimationFrame gaps."""
    s = sorted(float(g) for g in gaps)
    n = len(s)
    return {
        "fps": round(n / (elapsed_ms / 1000.0), 1) if elapsed_ms else 0.0,
        "frames": n,
        "frame_ms": {"p50": _pct(s, 50), "p95": _pct(s, 95), "p99": _pct(s, 99),
                     "max": round(s[-1], 1) if s else 0.0},
        "slow_frames_pct": round(100.0 * sum(1 for g in s if g > SLOW_FRAME_MS) / n, 1) if n else 0.0,
        "janky_frames": sum(1 for g in s if g > JANK_FRAME_MS),
    }


def main_thread(m0: dict, m1: dict, elapsed_ms: float) -> dict:
    """Main-thread time spent in the window, split by kind (CDP deltas)."""
    out: dict = {}
    for key, name in _DURATIONS.items():
        out[name + "_ms"] = round((m1.get(key, 0) - m0.get(key, 0)) * 1000.0, 1)
    out["other_ms"] = round(max(0.0, out["task_ms"] - out["script_ms"] - out["layout_ms"] - out["style_ms"]), 1)
    out["busy_pct"] = round(100.0 * out["task_ms"] / elapsed_ms, 1) if elapsed_ms else 0.0
    for key, name in _COUNTS.items():
        out[name] = int(m1.get(key, 0) - m0.get(key, 0))
    for key, name in _GAUGES.items():
        v = m1.get(key)
        if v is not None:
            out[name] = round(v / 1048576.0, 1) if key == "JSHeapUsedSize" else int(v)
    return out


def long_stats(long: list) -> dict:
    durs = [int(x[1]) for x in long]
    return {"count": len(durs), "total_ms": sum(durs), "max_ms": max(durs) if durs else 0}


def _shift(s: list) -> dict:
    out = {"at_ms": s[0], "value": round(s[1], 4)}
    if len(s) > 2 and s[2]:
        out["moved"] = [{"node": x[0], "y": [x[1], x[2]], "height": [x[3], x[4]]} for x in s[2]]
    return out


def boot_stats(boot: dict, measure_from: int | None = None) -> dict:
    """Boot timeline: marks, layout shifts and long tasks before the window."""
    shifts = [s for s in boot.get("shifts", []) if measure_from is None or s[0] < measure_from]
    long = [x for x in boot.get("long", []) if measure_from is None or x[0] < measure_from]
    top = sorted(shifts, key=lambda s: -s[1])[:8]
    return {
        "dom_content_loaded_ms": boot.get("dcl"), "load_ms": boot.get("load"),
        "marks": boot.get("marks", {}),
        "layout_shift": {"cls": round(sum(s[1] for s in shifts), 4), "count": len(shifts),
                         "largest": [_shift(s) for s in top]},
        "long_tasks": long_stats(long),
    }


def _median_summary(runs: list) -> dict:
    """Median of the headline numbers across repeated runs of one variant."""
    def med(path):
        vals = []
        for r in runs:
            v = r
            for k in path:
                v = v.get(k) if isinstance(v, dict) else None
            if isinstance(v, (int, float)):
                vals.append(v)
        return round(statistics.median(vals), 1) if vals else None
    return {
        "fps": med(("window", "fps")),
        "frame_ms_p95": med(("window", "frame_ms", "p95")),
        "slow_frames_pct": med(("window", "slow_frames_pct")),
        "busy_pct": med(("window", "main_thread", "busy_pct")),
        "script_ms": med(("window", "main_thread", "script_ms")),
        "layout_ms": med(("window", "main_thread", "layout_ms")),
        "style_ms": med(("window", "main_thread", "style_ms")),
        "long_tasks_ms": med(("window", "long_tasks", "total_ms")),
        "boot_cls": med(("boot", "layout_shift", "cls")),
        "boot_long_tasks_ms": med(("boot", "long_tasks", "total_ms")),
    }


def _parse_viewport(v: str) -> tuple[int, int]:
    try:
        w, h = v.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise UsageError(f"--viewport must look like 1366x768, got {v!r}")


def _load_json(inline: str | None, path: str | None, flag: str, default):
    if inline and path:
        raise UsageError(f"provide either --{flag} or --{flag}-file, not both")
    raw = inline
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            raise UsageError(f"cannot read --{flag}-file {path!r}: {exc}")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise UsageError(f"--{flag} is not valid JSON: {exc}")


def _variants(args) -> list[dict]:
    extra = _load_json(args.variants, args.variants_file, "variants", [])
    if not isinstance(extra, list) or not all(isinstance(v, dict) and v.get("name") for v in extra):
        raise UsageError("--variants must be a JSON array of objects, each with a name")
    names = [v["name"] for v in extra]
    if "baseline" in names or len(set(names)) != len(names):
        raise UsageError("variant names must be unique and not 'baseline' (the page as served)")
    return ([] if args.no_baseline else [{"name": "baseline"}]) + extra


def _nav_timeout(args, rate: float) -> int:
    """How long to wait for a page load. CPU throttling slows the real load roughly in
    proportion to the rate, so a budget that is fine unthrottled cuts off a heavy page at
    4-6x and fails the whole probe. The default auto-scales the driver's nav budget by the
    rate; an explicit --nav-timeout overrides it."""
    if args.nav_timeout:
        return args.nav_timeout
    return int(DEFAULT_NAV_TIMEOUT_MS * max(1.0, rate))


def _run_one(driver, args, variant: dict, marks: dict, viewport: tuple[int, int]) -> dict:
    rate = float(variant.get("cpu_throttle", args.cpu_throttle))
    driver.cdp("Emulation.setCPUThrottlingRate", {"rate": max(1.0, rate)})
    driver.cdp("Emulation.setDeviceMetricsOverride",
               {"width": viewport[0], "height": viewport[1],
                "deviceScaleFactor": float(variant.get("dpr", args.dpr)), "mobile": False})
    media = [{"name": "prefers-reduced-motion",
              "value": "reduce" if variant.get("reduced_motion") else "no-preference"}]
    driver.cdp("Emulation.setEmulatedMedia", {"features": media})
    scripts = [COLLECTOR_JS.replace("__MARKS__", json.dumps(marks))]
    if variant.get("css") or variant.get("js"):
        scripts.append(VARIANT_JS.replace("__CSS__", json.dumps(variant.get("css") or ""))
                       .replace("__JS__", json.dumps(variant.get("js") or "")))
    ids = []
    for src in scripts:
        res = driver.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": src}) or {}
        ids.append(res.get("identifier"))
    try:
        # Same address with a #fragment is a same-document navigation: no reload,
        # no init scripts, the previous run's boot. A blank page in between forces
        # a fresh document every time.
        driver.goto("about:blank")
        driver.goto(args.url, timeout=_nav_timeout(args, rate))
        driver.wait(int(variant.get("settle_ms", args.settle_ms)))
        calib = driver.eval_js(CALIBRATE_JS) or {}
        m0 = _metrics(driver)
        win = driver.eval_js(MEASURE_JS, arg={"ms": int(variant.get("measure_ms", args.measure_ms)),
                                              "during": variant.get("during_js", args.during_js) or ""}) or {}
        m1 = _metrics(driver)
        boot = driver.eval_js(BOOT_JS) or {}
        elapsed = float(win.get("elapsed") or 0)
        window = frame_stats(win.get("gaps") or [], elapsed)
        window["elapsed_ms"] = round(elapsed)
        window["long_tasks"] = long_stats(win.get("long") or [])
        window["main_thread"] = main_thread(m0, m1, elapsed)
        measure_from = win.get("t0")
        out = {"cpu_throttle": rate, "calibration_ms": calib.get("ms"),
               "boot": boot_stats(boot, measure_from), "window": window}
        if boot.get("variantError") or win.get("duringError"):
            out["errors"] = {"variant": boot.get("variantError"), "during": win.get("duringError")}
        expose = variant.get("expose_js", args.expose_js)
        if expose:
            try:
                out["exposed"] = driver.eval_js(f"() => {{ try {{ return ({expose}); }} catch (e) {{ return {{ error: String(e) }}; }} }}")
            except Exception as exc:  # noqa: BLE001 - a page reader must not lose the run
                out["exposed"] = {"error": str(exc)[:300]}
        return out
    finally:
        for ident in ids:
            if ident:
                try:
                    driver.cdp("Page.removeScriptToEvaluateOnNewDocument", {"identifier": ident})
                except Exception:  # noqa: BLE001 - best effort between variants
                    pass


def perf_probe(driver_factory, args) -> dict:
    if not (args.url or "").lower().startswith(("http://", "https://")):
        raise UsageError("--url must be an http(s) address")
    if args.repeat < 1 or args.repeat > 10:
        raise UsageError("--repeat must be between 1 and 10")
    viewport = _parse_viewport(args.viewport)
    marks = _load_json(args.marks, args.marks_file, "marks", {})
    if not isinstance(marks, dict):
        raise UsageError("--marks must be a JSON object {name: css selector}")
    variants = _variants(args)
    if not variants:
        raise UsageError("nothing to measure: --no-baseline needs at least one --variants entry")

    if args.session:
        driver = api.open_session(args.session, headless=not args.headed, channel=args.channel,
                                  driver_factory=driver_factory)
    else:
        driver = driver_factory(storage_state=None, headless=not args.headed, channel=args.channel)
        driver.start()
    try:
        driver.cdp("Page.enable")
        driver.cdp("Performance.enable", {"timeDomain": "timeTicks"})
        if args.warmup:
            # one unmeasured load, so the first variant is not the only one paying for a cold cache
            driver.goto("about:blank")
            driver.goto(args.url, timeout=_nav_timeout(args, args.cpu_throttle))
            driver.wait(int(args.settle_ms))
        results = []
        for v in variants:
            runs = [_run_one(driver, args, v, marks, viewport) for _ in range(args.repeat)]
            entry = {"name": v["name"], "summary": _median_summary(runs)}
            if args.repeat == 1:
                entry.update(runs[0])
            else:
                entry["runs"] = runs
            results.append(entry)
        diag = api._diagnostics(driver)
    finally:
        api._safe_close(driver)

    base = next((r for r in results if r["name"] == "baseline"), None)
    if base:
        for r in results:
            if r is base:
                continue
            r["vs_baseline"] = {k: (round(r["summary"][k] - base["summary"][k], 1)
                                    if isinstance(r["summary"].get(k), (int, float))
                                    and isinstance(base["summary"].get(k), (int, float)) else None)
                                for k in base["summary"]}
    return {
        "url": args.url, "session": args.session or None,
        "cpu_throttle": args.cpu_throttle, "nav_timeout": args.nav_timeout or "auto",
        "viewport": args.viewport, "dpr": args.dpr,
        "settle_ms": args.settle_ms, "measure_ms": args.measure_ms, "repeat": args.repeat,
        "warmup": bool(args.warmup),
        "variants": results,
        "page_errors": [str(e)[:300] for e in (diag.get("page_errors") or [])][:20],
        "note": "headless Chromium rasterizes in software: paint cost shows as fps / slow frames, "
                "not as main-thread ms",
    }


def _perf_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--url", required=True, help="Page to measure")
    p.add_argument("--session", default=None,
                   help="Saved session to load (default: a fresh anonymous context)")
    p.add_argument("--cpu-throttle", type=float, default=4.0,
                   help="CPU slowdown factor (1 = this machine; 4 ~ a budget laptop; 6 ~ a low-end one)")
    p.add_argument("--nav-timeout", type=int, default=0,
                   help="Per-load navigation timeout in ms; 0 (default) scales the driver's nav "
                        "budget by the CPU-throttle rate so a throttled load is not cut off")
    p.add_argument("--viewport", default="1366x768", help="Viewport WIDTHxHEIGHT (default 1366x768)")
    p.add_argument("--dpr", type=float, default=1.0, help="Device pixel ratio (default 1)")
    p.add_argument("--settle-ms", type=int, default=6000,
                   help="Wait after load before measuring (the boot is measured over this time)")
    p.add_argument("--measure-ms", type=int, default=8000, help="Length of the measured window")
    p.add_argument("--marks", default=None,
                   help='JSON {name: selector}: when each first appears during boot')
    p.add_argument("--marks-file", default=None, help="Path to the --marks JSON")
    p.add_argument("--variants", default=None,
                   help='JSON array [{name, css?, js?, cpu_throttle?, dpr?, reduced_motion?, '
                        'settle_ms?, measure_ms?, during_js?, expose_js?}]')
    p.add_argument("--variants-file", default=None, help="Path to the --variants JSON")
    p.add_argument("--no-baseline", action="store_true",
                   help="Skip the page-as-served run (measure only the variants)")
    p.add_argument("--during-js", default=None,
                   help="JS run at the start of the window (e.g. a scroll loop); default: idle")
    p.add_argument("--expose-js", default=None,
                   help="JS expression read at the end (e.g. the page's own perf counters)")
    p.add_argument("--repeat", type=int, default=1, help="Runs per variant (1-10); summary is the median")
    p.add_argument("--warmup", action="store_true",
                   help="Load the page once, unmeasured, first: every variant then boots from a warm cache")
    p.add_argument("--headed", action="store_true", help="Show the browser window")
    p.add_argument("--channel", default=None, help="Chromium channel: 'chrome'|'msedge'")
    p.add_argument("--direct", action="store_true",
                   help="Bypass the owning tool's serializing broker and drive "
                        "the browser in-process (only safe when that broker is "
                        "stopped / idle-closed; perf-probe needs exclusive control anyway)")


ACTIONS = {
    "perf-probe": ActionDef(
        perf_probe, _perf_args,
        description="Measure a page's frame rate, main-thread cost and boot layout shifts "
                    "under CPU throttling, with optional CSS/JS variants to compare.",
    ),
}
