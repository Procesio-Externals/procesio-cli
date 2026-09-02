"""Tests for the opt-in ELK 'layered' layout engine + the LAYOUT_ENGINE dispatch flag.

The ELK-runtime tests need Node + elkjs (tools/procesio/layout/elk/node_modules); they skip
if that toolchain is absent. The dispatch/flag and graceful-fallback tests are pure Python
and always run.
"""
from __future__ import annotations

import copy
import math

import pytest

from tools.procesio.layout import dispatch, elk_engine, engine


def _elk_available() -> bool:
    """True iff the REAL ELK runner works here — node on PATH, elkjs installed
    (tools/procesio/layout/elk/node_modules), runner returns a laid-out graph.

    Probe the runner DIRECTLY, never through elk_engine.layout(): layout() swallows every
    ELK failure and returns the LEGACY layout, so any "did we get sane positions back"
    check reports available on a machine with no node_modules. The skip then never fires
    and the ELK-specific assertions below run against the legacy engine — which is exactly
    how test_elk_long_straight_run_is_clustered failed on a fresh checkout while the other
    four @requires_elk tests passed by coincidence.
    """
    try:
        graph = elk_engine._build_elk_graph(
            [elk_engine._norm({"id": "a"}), elk_engine._norm({"id": "b"})],
            [{"source": "a", "dest": "b"}])
        return bool(elk_engine._run_elk(graph))
    except Exception:  # noqa: BLE001 — any failure means "not available", never a test error
        return False


requires_elk = pytest.mark.skipif(not _elk_available(),
                                  reason="Node/elkjs runner unavailable")


def _assert_all_finite(res, ids):
    """Every id has a position and no coordinate is NaN / None / non-finite."""
    p = res["positions"]
    for i in ids:
        assert i in p, f"{i} missing a position"
    for i, q in p.items():
        assert q["x"] is not None and q["y"] is not None, f"{i} has a None coordinate"
        assert isinstance(q["x"], float) and isinstance(q["y"], float), f"{i} non-float"
        assert not math.isnan(q["x"]) and not math.isnan(q["y"]), f"{i} is NaN"
        assert math.isfinite(q["x"]) and math.isfinite(q["y"]), f"{i} not finite"


# --- graph shapes ----------------------------------------------------------

def _linear(n=6):
    nodes = [{"id": f"n{i}"} for i in range(n)]
    edges = [{"source": f"n{i}", "dest": f"n{i + 1}"} for i in range(n - 1)]
    return nodes, edges


def _branching():
    """start -> a -> {b,c} -> d -> stop, with an error edge a->err and a d->a back-edge."""
    nodes = [{"id": i} for i in ("start", "a", "b", "c", "d", "err", "stop")]
    edges = [
        {"source": "start", "dest": "a"}, {"source": "a", "dest": "b"},
        {"source": "a", "dest": "c"}, {"source": "b", "dest": "d"},
        {"source": "c", "dest": "d"}, {"source": "d", "dest": "stop"},
        {"source": "a", "dest": "err", "type": 1},
        {"source": "d", "dest": "a"},                       # back-edge (loop / retry)
    ]
    return nodes, edges


def _compound():
    """A For-Each container 'loop' holding an inner k1->k2 pipeline."""
    nodes = [{"id": "start"}, {"id": "loop", "kind": "area"},
             {"id": "k1", "parent_id": "loop"}, {"id": "k2", "parent_id": "loop"},
             {"id": "stop"}]
    edges = [{"source": "start", "dest": "loop"}, {"source": "loop", "dest": "k1"},
             {"source": "k1", "dest": "k2"}, {"source": "loop", "dest": "stop"}]
    return nodes, edges


# --- ELK-runtime tests -----------------------------------------------------

@requires_elk
def test_elk_flat_linear_all_positioned():
    nodes, edges = _linear()
    res = elk_engine.layout(nodes, edges)
    _assert_all_finite(res, [n["id"] for n in nodes])
    p = res["positions"]
    assert res["areas"] == {}                                # no containers in a flat graph
    # readability config: a linear chain is ONE straight left-to-right row (wrapping OFF,
    # Brandes-Köpf alignment) — every node on the same y, x strictly increasing.
    assert len({round(q["y"]) for q in p.values()}) == 1     # single straight row
    xs = [p[f"n{i}"]["x"] for i in range(len(nodes))]
    assert xs == sorted(xs) and len(set(xs)) == len(nodes)   # each node right of the previous
    assert p["n0"]["x"] == min(q["x"] for q in p.values())   # starts at the left


@requires_elk
def test_elk_short_straight_run_not_clustered():
    # a 6-node chain is NOT longer than CLUSTER_MIN(6) → stays one straight left-to-right row
    nodes = [{"id": f"n{i}"} for i in range(6)]
    edges = [{"source": f"n{i}", "dest": f"n{i + 1}"} for i in range(5)]
    p = elk_engine.layout(nodes, edges)["positions"]
    assert len({round(v["y"]) for v in p.values()}) == 1     # single row (not folded)


@requires_elk
def test_elk_long_straight_run_is_clustered():
    # an 8-node straight run (> CLUSTER_MIN) folds into a compact serpentine: fewer columns,
    # more than one row, every node still placed and finite.
    n = 8
    nodes = [{"id": f"n{i}"} for i in range(n)]
    edges = [{"source": f"n{i}", "dest": f"n{i + 1}"} for i in range(n - 1)]
    res = elk_engine.layout(nodes, edges)
    _assert_all_finite(res, [f"n{i}" for i in range(n)])
    p = res["positions"]
    assert len({round(v["y"]) for v in p.values()}) > 1      # folded into multiple rows
    assert len({round(v["x"]) for v in p.values()}) < n      # fewer columns than nodes


@requires_elk
def test_elk_branching_all_positioned():
    nodes, edges = _branching()
    res = elk_engine.layout(nodes, edges)
    _assert_all_finite(res, [n["id"] for n in nodes])        # cycle + error edge don't crash it


@requires_elk
def test_elk_compound_children_inside_frame():
    nodes, edges = _compound()
    res = elk_engine.layout(nodes, edges)
    _assert_all_finite(res, [n["id"] for n in nodes])
    assert "loop" in res["areas"], "container must produce an area frame"
    fr = res["areas"]["loop"]
    for k in ("width", "height", "x", "y"):
        assert math.isfinite(fr[k])
    for kid in ("k1", "k2"):                                 # children land inside the frame
        q = res["positions"][kid]
        assert fr["x"] <= q["x"] <= fr["x"] + fr["width"]
        assert fr["y"] <= q["y"] <= fr["y"] + fr["height"]


@requires_elk
def test_elk_deterministic():
    nodes, edges = _branching()
    a = elk_engine.layout(nodes, edges)
    b = elk_engine.layout(copy.deepcopy(nodes), copy.deepcopy(edges))
    assert a == b                                            # fixed seed → identical output


@requires_elk
def test_elk_missing_endpoint_is_dropped_not_crashed():
    res = elk_engine.layout([{"id": "x"}, {"id": "y"}],
                            [{"source": "x", "dest": "GHOST"}, {"source": "x", "dest": "y"}])
    _assert_all_finite(res, ["x", "y"])                      # ghost edge ignored, nodes placed


# --- resilience (engine-agnostic) ------------------------------------------

def test_elk_empty_graph():
    res = elk_engine.layout([], [])
    assert res["positions"] == {} and res["areas"] == {}
    assert res["bbox"] == {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0}


def test_elk_subset_delegates_to_legacy():
    # partial re-tidy is legacy-only; the ELK engine must delegate and match legacy exactly.
    nodes = [{"id": "a", "position": {"x": 0, "y": 100}},
             {"id": "b", "position": {"x": 5000, "y": 9000}},
             {"id": "c", "position": {"x": 520, "y": 100}}]
    edges = [{"source": "a", "dest": "b"}, {"source": "b", "dest": "c"}]
    assert elk_engine.layout(nodes, edges, subset=["b"]) == \
        engine.layout(copy.deepcopy(nodes), copy.deepcopy(edges), subset=["b"])


def test_elk_falls_back_to_legacy_on_runner_failure(monkeypatch):
    # force the ELK invocation to fail; the engine must degrade to a valid legacy layout.
    def boom(_graph):
        raise RuntimeError("simulated: node not found")
    monkeypatch.setattr(elk_engine, "_run_elk", boom)
    nodes, edges = _linear()
    res = elk_engine.layout(nodes, edges)
    assert res == engine.layout(nodes, edges)               # exactly the legacy result
    _assert_all_finite(res, [n["id"] for n in nodes])


# --- dispatch flag ---------------------------------------------------------

def test_dispatch_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv("LAYOUT_ENGINE", raising=False)
    assert dispatch.selected_engine() == "legacy"
    nodes, edges = _linear()
    assert dispatch.layout(nodes, edges) == engine.layout(nodes, edges)


@pytest.mark.parametrize("val", ["", "  ", "bogus", "LEGACY", "ELKZ"])
def test_dispatch_invalid_or_unset_is_legacy(monkeypatch, val):
    monkeypatch.setenv("LAYOUT_ENGINE", val)
    assert dispatch.selected_engine() == "legacy"


@pytest.mark.parametrize("val", ["elk", "ELK", "  elk  "])
def test_dispatch_selects_elk(monkeypatch, val):
    monkeypatch.setenv("LAYOUT_ENGINE", val)
    assert dispatch.selected_engine() == "elk"


def test_dispatch_routes_to_elk_engine(monkeypatch):
    monkeypatch.setenv("LAYOUT_ENGINE", "elk")
    sentinel = {"positions": {"_": {"x": 1.0, "y": 2.0}}, "areas": {}, "bbox": {}}
    called = {}

    def fake(nodes, edges, opts=None, subset=None):
        called["hit"] = True
        return sentinel
    monkeypatch.setattr(elk_engine, "layout", fake)
    out = dispatch.layout([{"id": "n0"}], [])
    assert called.get("hit") and out is sentinel
