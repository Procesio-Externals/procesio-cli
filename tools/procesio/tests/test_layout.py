"""Tests for the deterministic canvas layout engine + .procesio adapter."""
from __future__ import annotations

import copy
import glob
import json
import os

import pytest

from tools.procesio.layout import adapter, engine

EXPORTS = os.path.join(os.path.dirname(__file__), "..", "docs_info", "Exports")


def _diamond():
    """start -> a -> {b,c} -> d -> stop, plus an error edge a->err."""
    nodes = [{"id": i} for i in ("start", "a", "b", "c", "d", "err", "stop")]
    edges = [
        {"source": "start", "dest": "a"}, {"source": "a", "dest": "b"},
        {"source": "a", "dest": "c"}, {"source": "b", "dest": "d"},
        {"source": "c", "dest": "d"}, {"source": "d", "dest": "stop"},
        {"source": "a", "dest": "err", "type": 1},
    ]
    return nodes, edges


def _rects(res):
    """node id -> (x0, y0, x1, y1) using default 48x48."""
    out = {}
    for nid, p in res["positions"].items():
        out[nid] = (p["x"] - 24, p["y"] - 24, p["x"] + 24, p["y"] + 24)
    return out


def test_engine_deterministic():
    n, e = _diamond()
    assert engine.layout(n, e) == engine.layout(copy.deepcopy(n), copy.deepcopy(e))


def test_engine_left_to_right_by_depth():
    n, e = _diamond()
    p = engine.layout(n, e)["positions"]
    # start is leftmost; each node sits right of its predecessor on the happy path
    assert p["start"]["x"] == min(q["x"] for q in p.values())
    assert p["a"]["x"] > p["start"]["x"] > -1
    assert p["d"]["x"] > p["b"]["x"] and p["d"]["x"] > p["c"]["x"]
    assert p["stop"]["x"] > p["d"]["x"]


def test_engine_no_overlap():
    n, e = _diamond()
    rects = _rects(engine.layout(n, e))
    ids = list(rects)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            ax0, ay0, ax1, ay1 = rects[ids[i]]
            bx0, by0, bx1, by1 = rects[ids[j]]
            overlap = ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1
            assert not overlap, f"{ids[i]} overlaps {ids[j]}"


def test_engine_error_target_drops_below():
    n, e = _diamond()
    p = engine.layout(n, e)["positions"]
    # the error handler sits below the whole main band
    main_max_y = max(p[k]["y"] for k in ("start", "a", "b", "c", "d", "stop"))
    assert p["err"]["y"] > main_max_y


def test_engine_container_contains_children():
    nodes = [{"id": "start"}, {"id": "loop", "kind": "area"},
             {"id": "k1", "parent_id": "loop"}, {"id": "k2", "parent_id": "loop"},
             {"id": "stop"}]
    edges = [{"source": "start", "dest": "loop"}, {"source": "loop", "dest": "k1"},
             {"source": "k1", "dest": "k2"}, {"source": "loop", "dest": "stop"}]
    res = engine.layout(nodes, edges)
    frame = res["areas"]["loop"]
    for kid in ("k1", "k2"):
        p = res["positions"][kid]
        assert frame["x"] <= p["x"] <= frame["x"] + frame["width"]
        assert frame["y"] <= p["y"] <= frame["y"] + frame["height"]


# -- adapter: round-trip integrity on real exports ---------------------------

def _first_multiaction_flow(bundle):
    for f in bundle.get("Flows") or []:
        if len(f.get("Actions") or []) >= 3:
            return f["Id"]
    return None


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(EXPORTS, "*.procesio")))[:3])
def test_adapter_changes_only_geometry(path):
    bundle = json.load(open(path, encoding="utf-8"))
    fid = _first_multiaction_flow(bundle)
    if not fid:
        pytest.skip("no multi-action flow")
    before = copy.deepcopy(bundle)
    res = adapter.layout_flow(bundle, flow_id=fid)
    out = res["bundle"]
    # input bundle is untouched (pure)
    assert bundle == before
    bflow = next(f for f in before["Flows"] if f["Id"] == fid)
    aflow = next(f for f in out["Flows"] if f["Id"] == fid)
    # topology unchanged: same action ids, ports, parameters
    b_by = {a["Id"]: a for a in bflow["Actions"]}
    a_by = {a["Id"]: a for a in aflow["Actions"]}
    assert set(b_by) == set(a_by)
    for aid in b_by:
        ba, aa = b_by[aid], a_by[aid]
        assert ba["Ports"] == aa["Ports"]
        assert ba.get("Parameters") == aa.get("Parameters")
        assert ba.get("ParentId") == aa.get("ParentId")
        # everything in CustomData except position/areaSize is identical
        bcd = {k: v for k, v in ba["CustomData"].items() if k not in ("position", "areaSize")}
        acd = {k: v for k, v in aa["CustomData"].items() if k not in ("position", "areaSize")}
        assert bcd == acd
    # CanvasData (the designer viewport) is NEVER touched
    assert aflow.get("CanvasData") == bflow.get("CanvasData")


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(EXPORTS, "*.procesio")))[:3])
def test_adapter_idempotent(path):
    bundle = json.load(open(path, encoding="utf-8"))
    fid = _first_multiaction_flow(bundle)
    if not fid:
        pytest.skip("no multi-action flow")
    once = adapter.layout_flow(bundle, flow_id=fid)
    twice = adapter.layout_flow(once["bundle"], flow_id=fid)
    assert once["positions"] == twice["positions"]


def test_linear_chain_is_one_straight_row():
    n = 8
    nodes = [{"id": f"n{i}"} for i in range(n)]
    edges = [{"source": f"n{i}", "dest": f"n{i + 1}"} for i in range(n - 1)]
    p = engine.layout(nodes, edges)["positions"]
    assert len({round(v["y"]) for v in p.values()}) == 1            # all on one row
    assert sorted(v["x"] for v in p.values()) == [80 + 160 * i for i in range(n)]


def test_parallel_chains_become_straight_distinct_lanes():
    # the image-6 case: 3 independent P->C->S chains -> 3 straight, non-crossing lanes
    nodes, edges = [], []
    for k in (1, 2, 3):
        for s in ("P", "C", "S"):
            nodes.append({"id": f"{s}{k}"})
        edges += [{"source": f"P{k}", "dest": f"C{k}"}, {"source": f"C{k}", "dest": f"S{k}"}]
    p = engine.layout(nodes, edges)["positions"]
    for k in (1, 2, 3):                                             # each chain straight
        assert p[f"P{k}"]["y"] == p[f"C{k}"]["y"] == p[f"S{k}"]["y"]
    assert len({p[f"P{k}"]["y"] for k in (1, 2, 3)}) == 3           # 3 distinct lanes
    # no crossings: the lane order is identical in every column
    lane_order = lambda col: [k for _, k in sorted((p[f"{col}{k}"]["y"], k) for k in (1, 2, 3))]
    assert lane_order("P") == lane_order("C") == lane_order("S")


def test_short_deadend_branch_folds_vertical():
    # dec -> x -> stop1 is a short dead-end (2 nodes) -> folds vertical at dec's column;
    # dec -> cont -> join is a rejoining branch (join has 2 inputs) -> stays horizontal.
    nodes = [{"id": i} for i in ("start", "dec", "x", "stop1", "cont", "join", "extra", "stop2")]
    edges = [
        {"source": "start", "dest": "dec"}, {"source": "start", "dest": "extra"},
        {"source": "dec", "dest": "x"}, {"source": "x", "dest": "stop1"},       # dead-end
        {"source": "dec", "dest": "cont"}, {"source": "cont", "dest": "join"},
        {"source": "extra", "dest": "join"}, {"source": "join", "dest": "stop2"},
    ]
    p = engine.layout(nodes, edges)["positions"]
    assert p["x"]["x"] == p["stop1"]["x"] == p["dec"]["x"]    # folded into dec's column
    assert p["cont"]["x"] > p["dec"]["x"]                      # spine continues horizontally


def test_long_deadend_chain_stays_horizontal():
    # a 4-node dead-end chain (> FOLD_MAX) is NOT folded — laid out as a horizontal lane
    chain = ["c1", "c2", "c3", "stopL"]
    nodes = [{"id": i} for i in ["start", "dec", "cont", "join", "extra", "stop2"] + chain]
    edges = [
        {"source": "start", "dest": "dec"}, {"source": "start", "dest": "extra"},
        {"source": "dec", "dest": "c1"}, {"source": "c1", "dest": "c2"},
        {"source": "c2", "dest": "c3"}, {"source": "c3", "dest": "stopL"},
        {"source": "dec", "dest": "cont"}, {"source": "cont", "dest": "join"},
        {"source": "extra", "dest": "join"}, {"source": "join", "dest": "stop2"},
    ]
    p = engine.layout(nodes, edges, opts={"FOLD_MAX": 2})["positions"]   # threshold below len
    xs = [p[c]["x"] for c in chain]
    assert xs == sorted(xs) and len(set(xs)) == 4              # distinct increasing columns


def test_cluster_chains_serpentine_opt_in():
    # a 7-action chain stays one long row by default; with CLUSTER it folds to a serpentine
    nodes = [{"id": f"n{i}"} for i in range(7)]
    edges = [{"source": f"n{i}", "dest": f"n{i + 1}"} for i in range(6)]
    plain = engine.layout(nodes, edges)["positions"]
    assert len({round(p["y"]) for p in plain.values()}) == 1          # one row
    assert len({round(p["x"]) for p in plain.values()}) == 7          # seven columns
    clustered = engine.layout(nodes, edges, opts={"CLUSTER": True})["positions"]
    assert len({round(p["x"]) for p in clustered.values()}) < 7       # fewer columns
    assert len({round(p["y"]) for p in clustered.values()}) > 1       # multiple rows
    # short chains (< CLUSTER_MIN) are NOT clustered
    short = [{"id": f"m{i}"} for i in range(3)]
    se = [{"source": f"m{i}", "dest": f"m{i + 1}"} for i in range(2)]
    sc = engine.layout(short, se, opts={"CLUSTER": True})["positions"]
    assert len({round(p["y"]) for p in sc.values()}) == 1             # stays one row


def _count_norm_crossings(positions, edges):
    E = [(e["source"], e["dest"]) for e in edges if int(e.get("type", 0) or 0) == 0
         and e["source"] in positions and e["dest"] in positions]

    def orient(p, q, r):
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])

    def inter(a, b, c, d):
        return (orient(a, b, c) > 0) != (orient(a, b, d) > 0) and \
               (orient(c, d, a) > 0) != (orient(c, d, b) > 0)
    P = positions
    n = 0
    for i in range(len(E)):
        s, d = E[i]
        for j in range(i + 1, len(E)):
            s2, d2 = E[j]
            if len({s, d, s2, d2}) < 4:
                continue
            if inter(P[s], P[d], P[s2], P[d2]):
                n += 1
    return n


def test_minimize_crossings_never_worse_and_opt_in():
    # a spine with a skip-edge + an error region — the pattern that produces crossings
    nodes = [{"id": i} for i in ("start", "d", "a", "b", "join", "e", "stop", "stop2")]
    edges = [
        {"source": "start", "dest": "d"},
        {"source": "d", "dest": "join"},                          # long skip edge
        {"source": "d", "dest": "a"}, {"source": "a", "dest": "b"},
        {"source": "b", "dest": "join"},
        {"source": "a", "dest": "e", "type": 1}, {"source": "e", "dest": "stop2"},
        {"source": "join", "dest": "stop"},
    ]
    plain = engine.layout(nodes, edges)["positions"]
    mc = engine.layout(nodes, edges, opts={"MINIMIZE_CROSSINGS": True})["positions"]
    assert _count_norm_crossings(mc, edges) <= _count_norm_crossings(plain, edges)  # never worse
    assert engine.layout(nodes, edges)["positions"] == plain          # off by default (no-op)


def test_engine_partial_moves_only_subset():
    # a -> b -> c with current positions; b is parked far off. Re-tidy only b.
    nodes = [{"id": "a", "position": {"x": 0, "y": 100}},
             {"id": "b", "position": {"x": 5000, "y": 9000}},
             {"id": "c", "position": {"x": 520, "y": 100}}]
    edges = [{"source": "a", "dest": "b"}, {"source": "b", "dest": "c"}]
    res = engine.layout(nodes, edges, subset=["b"])
    # a and c are untouched
    assert res["positions"]["a"] == {"x": 0.0, "y": 100.0}
    assert res["positions"]["c"] == {"x": 520.0, "y": 100.0}
    # b is placed between its neighbours, at their median y
    assert 0 < res["positions"]["b"]["x"] < 520
    assert abs(res["positions"]["b"]["y"] - 100.0) < 1


def test_engine_partial_deterministic():
    nodes = [{"id": "a", "position": {"x": 0, "y": 0}},
             {"id": "b", "position": {"x": 9, "y": 9}},
             {"id": "c", "position": {"x": 600, "y": 0}}]
    edges = [{"source": "a", "dest": "b"}, {"source": "b", "dest": "c"}]
    assert engine.layout(nodes, edges, subset=["b"]) == \
        engine.layout(copy.deepcopy(nodes), copy.deepcopy(edges), subset=["b"])


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(EXPORTS, "*.procesio")))[:3])
def test_adapter_only_touches_target(path):
    bundle = json.load(open(path, encoding="utf-8"))
    fid = _first_multiaction_flow(bundle)
    if not fid:
        pytest.skip("no multi-action flow")
    flow = next(f for f in bundle["Flows"] if f["Id"] == fid)
    # pick an action that has at least one edge (so it actually relocates)
    edged = {p["SourceId"] for a in flow["Actions"] for p in a.get("Ports") or []} | \
            {p["DestinationId"] for a in flow["Actions"] for p in a.get("Ports") or []}
    target = next((a["Id"] for a in flow["Actions"] if a["Id"] in edged), flow["Actions"][0]["Id"])
    before = copy.deepcopy(bundle)
    res = adapter.layout_flow(bundle, flow_id=fid, only=[target])
    out = res["bundle"]
    assert bundle == before                          # input untouched (pure)
    bflow = next(f for f in before["Flows"] if f["Id"] == fid)
    aflow = next(f for f in out["Flows"] if f["Id"] == fid)
    b_by = {a["Id"]: a for a in bflow["Actions"]}
    a_by = {a["Id"]: a for a in aflow["Actions"]}
    for aid in b_by:
        if aid == target:
            # only CustomData.position may differ on the target
            bclean = {k: v for k, v in b_by[aid]["CustomData"].items() if k != "position"}
            aclean = {k: v for k, v in a_by[aid]["CustomData"].items() if k != "position"}
            assert bclean == aclean
        else:
            assert b_by[aid] == a_by[aid]            # every other action byte-identical
    assert bflow.get("CanvasData") == aflow.get("CanvasData")   # viewport untouched
    assert res["nodes_moved"] == 1


def test_container_children_written_relative_and_render_ok():
    # a For-Each area child's position must be stored RELATIVE to the area frame, and the
    # rendered children must land inside the frame (the PROCESIO container convention).
    flow = {"Id": "f", "Actions": [
        {"Id": "start", "ActionTemplateName": "Start",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "start", "DestinationId": "loop", "Type": 0}]},
        {"Id": "loop", "ActionTemplateName": "For Each",
         "CustomData": {"type": "area", "name": "For Each", "position": {"x": 0, "y": 0},
                        "areaSize": {"width": 0, "height": 0, "x": 0, "y": 0}},
         "Ports": [{"SourceId": "loop", "DestinationId": "k1", "Type": 0},
                   {"SourceId": "loop", "DestinationId": "stop", "Type": 0}]},
        {"Id": "k1", "ActionTemplateName": "Map Data", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "k1", "DestinationId": "k2", "Type": 0}]},
        {"Id": "k2", "ActionTemplateName": "Add", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}}, "Ports": []},
        {"Id": "stop", "ActionTemplateName": "Stop",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}}, "Ports": []},
    ]}
    out = adapter.layout_flow(flow)["bundle"]
    assert adapter.verify_render(out)["ok"]                     # children render inside frame
    byid = {a["Id"]: a for a in out["Actions"]}
    asz = byid["loop"]["CustomData"]["areaSize"]
    for kid in ("k1", "k2"):                                    # stored relative, within frame
        p = byid[kid]["CustomData"]["position"]
        assert 0 <= p["x"] <= asz["width"] and 0 <= p["y"] <= asz["height"]
    # first child leaves room for the implicit ForEach-Start (>= one DX from frame left)
    assert min(byid[k]["CustomData"]["position"]["x"] for k in ("k1", "k2")) >= 160


def test_loop_back_edge_returns_vertically():
    # a -> dec -> b -> u, with u looping back to a (retry pattern). The back-edge source u
    # should align under its target a (vertical return), in a lane below.
    nodes = [{"id": i} for i in ("start", "a", "dec", "b", "u", "stop")]
    edges = [{"source": "start", "dest": "a"}, {"source": "a", "dest": "dec"},
             {"source": "dec", "dest": "b"}, {"source": "b", "dest": "u"},
             {"source": "u", "dest": "a"},                       # back-edge (loop return)
             {"source": "dec", "dest": "stop"}]
    p = engine.layout(nodes, edges)["positions"]
    assert abs(p["u"]["x"] - p["a"]["x"]) < 1                    # u aligned under target a
    assert p["u"]["y"] > p["a"]["y"]                             # in a lane below


def test_wide_container_does_not_overlap_neighbours():
    # a wide area node next to normal nodes must not overlap them (column spacing accounts
    # for node width). verify_render catches overlaps.
    flow = {"Id": "f", "Actions": [
        {"Id": "s", "ActionTemplateName": "Start",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "s", "DestinationId": "loop", "Type": 0}]},
        {"Id": "loop", "ActionTemplateName": "For Each",
         "CustomData": {"type": "area", "name": "For Each", "position": {"x": 0, "y": 0},
                        "areaSize": {"width": 0, "height": 0, "x": 0, "y": 0}},
         "Ports": [{"SourceId": "loop", "DestinationId": "k1", "Type": 0},
                   {"SourceId": "loop", "DestinationId": "e", "Type": 0}]},
        {"Id": "k1", "ActionTemplateName": "Map Data", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "k1", "DestinationId": "k2", "Type": 0}]},
        {"Id": "k2", "ActionTemplateName": "Add", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}}, "Ports": []},
        {"Id": "e", "ActionTemplateName": "Stop",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}}, "Ports": []},
    ]}
    assert adapter.verify_render(adapter.layout_flow(flow)["bundle"])["ok"]


def test_full_relayout_anchors_start_in_place():
    # a full re-layout must keep Start exactly where it was (so the viewport still frames it)
    flow = {"Id": "f", "Actions": [
        {"Id": "start", "ActionTemplateName": "Start",
         "CustomData": {"type": "circle", "position": {"x": -1600, "y": 140}},
         "Ports": [{"SourceId": "start", "DestinationId": "a", "Type": 0}]},
        {"Id": "a", "ActionTemplateName": "Map Data",
         "CustomData": {"type": "square", "position": {"x": -1400, "y": 140}},
         "Ports": [{"SourceId": "a", "DestinationId": "stop", "Type": 0}]},
        {"Id": "stop", "ActionTemplateName": "Stop",
         "CustomData": {"type": "circle", "position": {"x": -1200, "y": 140}}, "Ports": []},
    ]}
    out = adapter.layout_flow(flow)["bundle"]
    sp = next(x for x in out["Actions"] if x["Id"] == "start")["CustomData"]["position"]
    assert sp == {"x": -1600.0, "y": 140.0}     # Start unmoved; the rest flows from it


def test_resource_map():
    # a tiny 2-flow bundle where flow A calls flow B
    bundle = {"Flows": [
        {"Id": "A", "Title": "Caller", "Actions": [
            {"Id": "n1", "ActionTemplateName": "Call Subprocess",
             "CustomData": {"type": "square", "configuration": [{"settings": [
                 {"label": "Select Subprocess", "type": "flow-list", "value": "B"}]}]},
             "Ports": []}]},
        {"Id": "B", "Title": "Callee", "Actions": []},
    ]}
    rm = adapter.layout_resource_map(bundle)
    ids = {n["flow_id"] for n in rm["nodes"]}
    assert ids == {"A", "B"}
    assert {"source": "A", "target": "B", "kind": "call"} in rm["edges"]
    # caller is left of callee
    pos = {n["flow_id"]: n["x"] for n in rm["nodes"]}
    assert pos["A"] < pos["B"]



def _bundle_crossings(bundle, flow_id=None):
    """Render-faithful crossing count for a laid-out bundle: children resolved to absolute,
    area nodes attached at frame top-left, all normal+error edges."""
    flows = bundle.get("Flows") or bundle.get("flows") or ([bundle["flow"]] if "flow" in bundle else [bundle])
    def g(d, *ks):
        for k in ks:
            if k in d:
                return d[k]
        return None
    flow = flows[0] if flow_id is None else next((f for f in flows if g(f, "Id", "id") == flow_id), flows[0])
    acts = g(flow, "Actions", "actions") or []
    byid = {g(a, "Id", "id"): a for a in acts}
    def cd(a):
        return g(a, "CustomData", "customData") or {}
    def pos_of(a):
        p = g(cd(a), "position") or {}
        return {"x": float(p.get("x", 0)), "y": float(p.get("y", 0))}
    pos = {g(a, "Id", "id"): pos_of(a) for a in acts}
    kind = {g(a, "Id", "id"): (cd(a).get("type")) for a in acts}
    for a in acts:
        par = g(a, "ParentId", "parentId"); aid = g(a, "Id", "id")
        if par in byid and (cd(byid[par]).get("type")) == "area":
            pp = pos[par]; pos[aid] = {"x": pp["x"] + pos[aid]["x"], "y": pp["y"] + pos[aid]["y"]}
    edges = []
    for a in acts:
        for pt in (g(a, "Ports", "ports") or []):
            s2 = g(pt, "SourceId", "sourceId"); d2 = g(pt, "DestinationId", "destinationId")
            if s2 in pos and d2 in pos and s2 != d2:
                edges.append((s2, d2))
    def orient(p, q, r):
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])
    def si(a, b, c, d):
        return (orient(a, b, c) > 0) != (orient(a, b, d) > 0) and (orient(c, d, a) > 0) != (orient(c, d, b) > 0)
    n = 0
    for i in range(len(edges)):
        s, d = edges[i]
        for j in range(i + 1, len(edges)):
            s2, d2 = edges[j]
            if len({s, d, s2, d2}) < 4:
                continue
            if si(pos[s], pos[d], pos[s2], pos[d2]):
                n += 1
    return n

def test_minimize_crossings_reduces_and_stays_local():
    """The optional pass must REDUCE crossings via local/compact moves and NEVER teleport a
    node far into empty space. C->D crosses A->B; a small endpoint nudge clears it."""
    nodes = [{"id": x, "w": 48, "h": 48} for x in ("A", "B", "C", "D")]
    typed = [("A", "B", 0), ("C", "D", 0)]
    DX, DY = engine.DEFAULTS["DX"], engine.DEFAULTS["DY"]
    base = {"A": {"x": 0.0, "y": 0.0}, "B": {"x": 6 * DX, "y": 0.0},
            "C": {"x": 5 * DX, "y": -0.5 * DY}, "D": {"x": 6 * DX, "y": 0.5 * DY}}

    def crossings(P):
        E = [("A", "B"), ("C", "D")]
        return sum(1 for i in range(len(E)) for j in range(i + 1, len(E))
                   if len(set(E[i]) | set(E[j])) == 4
                   and engine._seg_int(P[E[i][0]], P[E[i][1]], P[E[j][0]], P[E[j][1]]))

    def run(pen):
        P = copy.deepcopy(base)
        o = dict(engine.DEFAULTS); o["MINCROSS_MOVE_PENALTY"] = pen
        engine._minimize_crossings(P, [dict(n) for n in nodes], typed, o, movable={"C", "D"})
        return P

    assert crossings(base) == 1
    Pd = run(0.25)
    assert crossings(Pd) == 0                                      # it actually fixes it
    step = max(abs(Pd[n]["x"] - base[n]["x"]) / DX + abs(Pd[n]["y"] - base[n]["y"]) / DY
              for n in ("C", "D"))
    assert step <= 3                                               # via a LOCAL move, not a teleport
    assert run(50.0) == base                                       # heavy penalty pins everything


def test_minimize_crossings_never_worse_on_corpus():
    """On every real export flow, the optional pass must never INCREASE crossings vs base
    (the render-faithful count, area nodes attached at their frame top-left)."""
    import glob as _glob
    for path in sorted(_glob.glob(os.path.join(EXPORTS, "*.procesio")))[:4]:
        bundle = json.load(open(path, encoding="utf-8"))
        fid = _first_multiaction_flow(bundle)
        if not fid:
            continue
        b0 = adapter.layout_flow(bundle, flow_id=fid)["bundle"]
        b1 = adapter.layout_flow(bundle, flow_id=fid, minimize_crossings=True)["bundle"]
        assert _bundle_crossings(b1, fid) <= _bundle_crossings(b0, fid)

def test_loop_curl_aligns_retry_loop():
    """A retry/error loop region (entry edge from main + return edge back to main) lays out as
    two vertical columns aligned to its anchors: decisional + fail path above the entry source,
    loop tail above the return target -- so both boundary edges are vertical (no crossing) and
    the decisional reads in-flow."""
    P = {"src": {"x": 1000.0, "y": 500.0}, "ret": {"x": 800.0, "y": 500.0},
         "dec": {"x": 0.0, "y": 0.0}, "t1": {"x": 0.0, "y": 0.0}, "exit": {"x": 0.0, "y": 0.0},
         "f1": {"x": 0.0, "y": 0.0}, "f2": {"x": 0.0, "y": 0.0}}
    rset = {"dec", "t1", "exit", "f1", "f2"}
    typed = [("src", "dec", 1),                                   # entry (error) from main
             ("dec", "t1", 0), ("t1", "exit", 0), ("exit", "ret", 0),  # loop -> back to main
             ("dec", "f1", 0), ("f1", "f2", 0)]                   # fail path
    o = dict(engine.DEFAULTS)
    out = engine._loop_curl(rset, typed, P, o)
    assert out is not None and set(out) == rset
    assert out["dec"]["x"] == P["src"]["x"]            # decisional above its entry source
    assert out["exit"]["x"] == P["ret"]["x"]           # loop tail above the return target
    assert out["t1"]["x"] == P["ret"]["x"]
    assert out["f1"]["x"] == P["src"]["x"] and out["f1"]["y"] < out["dec"]["y"]  # fail above dec
    # both boundary edges vertical -> src->dec and exit->ret cannot cross each other
    assert not engine._seg_int(P["src"], out["dec"], out["exit"], P["ret"])


def test_loop_curl_none_without_return_edge():
    """No return-to-main edge -> not a loop; _loop_curl declines (falls back to flush)."""
    P = {"src": {"x": 100.0, "y": 100.0}, "dec": {"x": 0.0, "y": 0.0}, "a": {"x": 0.0, "y": 0.0}}
    typed = [("src", "dec", 1), ("dec", "a", 0)]
    assert engine._loop_curl({"dec", "a"}, typed, P, dict(engine.DEFAULTS)) is None

def test_resolve_overlaps_separates_and_is_noop_when_clean():
    """De-overlap pushes coincident nodes apart (grid-aligned) and is a NO-OP when clean."""
    by_id = {i: {"w": 48, "h": 48} for i in ("a", "b", "c")}
    DY = engine.DEFAULTS["DY"]
    # a and b coincide; c is clear
    pos = {"a": {"x": 0.0, "y": 0.0}, "b": {"x": 0.0, "y": 0.0}, "c": {"x": 500.0, "y": 0.0}}
    engine._resolve_overlaps(pos, by_id, {"a", "b", "c"}, dict(engine.DEFAULTS))
    assert engine._count_overlaps(pos, by_id, list(pos)) == 0
    # clean input untouched
    clean = {"a": {"x": 0.0, "y": 0.0}, "b": {"x": 0.0, "y": DY}, "c": {"x": 500.0, "y": 0.0}}
    before = {k: dict(v) for k, v in clean.items()}
    engine._resolve_overlaps(clean, by_id, {"a", "b", "c"}, dict(engine.DEFAULTS))
    assert clean == before


def test_layout_never_leaves_overlaps_on_corpus():
    """After a full layout (both optional layers on) no two nodes overlap, on real exports."""
    import glob as _glob
    for path in sorted(_glob.glob(os.path.join(EXPORTS, "*.procesio")))[:4]:
        bundle = json.load(open(path, encoding="utf-8"))
        fid = _first_multiaction_flow(bundle)
        if not fid:
            continue
        out = adapter.layout_flow(bundle, flow_id=fid, cluster=True, minimize_crossings=True)
        v = adapter.verify_render(out["bundle"], flow_id=fid)
        assert v.get("issue_count", 0) == 0, (path, v.get("issues"))



def test_ufold_mid_spine_pocket():
    """The reference ANAF pattern: a long private mid-spine chain folds into a vertical U-pocket --
    entry and exit stay on the spine row, the pocket hangs BELOW in columns, and the
    downstream compacts LEFT by the reclaimed width (unit-level: _fold_run ufold mode)."""
    run = [f"c{i}" for i in range(7)]
    ids = ["a"] + run + ["z0", "z1", "j"]
    ns = [{"id": i, "parent_id": None, "kind": "square"} for i in ids]
    pos = {"a": {"x": 0.0, "y": 0.0}}
    for i in range(7):
        pos[f"c{i}"] = {"x": (i + 1) * 160.0, "y": 0.0}
    pos["z0"] = {"x": 1280.0, "y": 0.0}
    pos["z1"] = {"x": 1440.0, "y": 0.0}
    pos["j"] = {"x": 1280.0, "y": -180.0}              # second feeder ABOVE -> pocket clear
    typed = ([("a", "c0", 0), ("c6", "z0", 0), ("j", "z0", 0), ("z0", "z1", 0)]
             + [(f"c{i}", f"c{i + 1}", 0) for i in range(6)])
    o = dict(engine.DEFAULTS)
    r = engine._fold_run(dict(pos), run, ns, typed, o, mode="ufold")
    assert r is not None
    assert round(r["c0"]["y"]) == round(r["c6"]["y"]) == 0     # entry AND exit on the spine row
    assert len({round(r[f"c{i}"]["x"]) for i in range(7)}) == 2   # folded to two columns
    assert all(r[f"c{i}"]["y"] >= -1 for i in range(7))          # pocket hangs BELOW
    assert r["z0"]["x"] < pos["z0"]["x"]                         # downstream compacted LEFT
    assert r["j"] == pos["j"]                                    # non-downstream feeder untouched
