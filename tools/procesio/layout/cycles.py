"""Cycle-aware layout: collapse a LARGE embedded cycle (a strongly-connected component) to a
single meta-node, lay the main graph out around it (so the spine flows past the loop and the
loop's external connections stay short), then expand the cycle's own compact DAG band back into
the reserved space.

Without this, longest-path layering smears a big retry/processing loop across the whole canvas
(its members land in very different layers), producing canvas-spanning edges. A small retry loop
(< MIN_CYCLE nodes) is intentionally left alone — the engine's loop-curl handles those.

Engine-agnostic: the main + collapsed layout runs on the DISPATCHED engine (legacy or ELK, via
the callable passed in); the cycle's internal band uses the legacy engine as a clean DAG
sub-layout (its back-edges removed first, so the engine doesn't apply its own loop heuristics
inside the block). Same {positions, areas, bbox} contract as engine.layout.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from tools.procesio.layout import engine

MIN_CYCLE = 8                 # only compact GENUINELY large cycles — a smaller retry loop (e.g.
#                               a 6-node error/retry loop) is already handled well by the engine's
#                               loop-curl, and collapsing it there makes it worse.
_META = "__cycle__"
sys.setrecursionlimit(10000)


def _sccs(node_ids: list, edges: list) -> list:
    """Tarjan's strongly-connected components. `edges` = list of (src, dst)."""
    succ: dict = defaultdict(list)
    for s, d in edges:
        succ[s].append(d)
    index: dict = {}
    low: dict = {}
    onstack: dict = {}
    stack: list = []
    counter = [0]
    out: list = []

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack[v] = True
        for w in succ.get(v, []):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif onstack.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                onstack[w] = False
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in node_ids:
        if v not in index:
            strong(v)
    return out


def _ring_positions(scc_ids: list, scc_edges: list, back: set) -> dict:
    """Lay the cycle as a compact RING (the reference hand-pattern on a get-information loop): the
    forward half runs left-to-right on the top row, the return half runs right-to-left on the
    row below, so the loop visibly circulates in a tight two-row block instead of smearing
    into a wide DAG band. Layer order comes from the back-edge-free internal DAG."""
    pairs = [(e["source"], e["dest"]) for e in scc_edges]
    layer = engine._longest_path_layers(scc_ids, pairs)
    max_l = max(layer.values()) if layer else 0
    half = max_l / 2.0
    DX, DY = 160.0, 180.0
    out: dict = {}
    used: dict = {}
    for nid in sorted(scc_ids, key=lambda i: (layer[i], str(i))):
        L = layer[nid]
        if L <= half:
            row, x = 0, L * DX
        else:
            row, x = 1, (max_l - L) * DX
        k = used.get((row, round(x)), 0)
        used[(row, round(x))] = k + 1
        y = row * DY + (k * DY * 0.6 * (-1 if row == 0 else 1))   # same-slot spill: stack outward
        out[nid] = {"x": x, "y": y}
    return out


def _score(pos: dict, epairs: list) -> tuple:
    """(crossings, max manhattan edge) on straight segments -- enough to compare two
    expansions of the same collapsed layout."""
    segs = [(pos[s], pos[d]) for s, d in epairs if s in pos and d in pos]

    def orient(p, q, r):
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])
    cross = 0
    for i in range(len(segs)):
        a, b = segs[i]
        for j in range(i + 1, len(segs)):
            c, d = segs[j]
            if len({id(a), id(b), id(c), id(d)}) < 4:
                continue
            if (a["x"], a["y"]) in ((c["x"], c["y"]), (d["x"], d["y"])) or                (b["x"], b["y"]) in ((c["x"], c["y"]), (d["x"], d["y"])):
                continue
            if (orient(a, b, c) > 0) != (orient(a, b, d) > 0) and                (orient(c, d, a) > 0) != (orient(c, d, b) > 0):
                cross += 1
    med = max((abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]) for a, b in segs), default=0.0)
    return (cross, med)


def layout(nodes: list, edges: list, opts: dict | None, subset: list | None,
           dispatch_layout) -> dict:
    """Cycle-aware wrapper around `dispatch_layout` (same signature as engine.layout). Falls
    back to a plain dispatch when there's no large collapsible cycle, in partial (`subset`)
    mode, or when a cycle would touch a container (For-Each) — containers are never collapsed."""
    if subset is not None:
        return dispatch_layout(nodes, edges, opts=opts, subset=subset)

    by_id = {n["id"]: n for n in nodes}
    epairs = [(e["source"], e["dest"]) for e in edges
              if e["source"] in by_id and e["dest"] in by_id and e["source"] != e["dest"]]
    comps = [set(c) for c in _sccs([n["id"] for n in nodes], epairs) if len(c) >= MIN_CYCLE]
    areas = {n["id"] for n in nodes if n.get("kind") == "area"}
    kids = {n["id"] for n in nodes if n.get("parent_id")}
    comps = [c for c in comps if not (c & (areas | kids))]
    if not comps:
        return dispatch_layout(nodes, edges, opts=opts, subset=subset)

    scc = max(comps, key=len)               # compact the largest cycle

    # 1. internal band: lay the cycle out as a clean left-to-right DAG (back-edges removed).
    # sorted() so the DFS root (=> which edge becomes the back edge => where the cycle's chain
    # starts) is deterministic, not an artifact of Tarjan's pop order.
    scc_sorted = sorted(scc)
    internal = [(e["source"], e["dest"]) for e in edges if e["source"] in scc and e["dest"] in scc]
    back = engine._back_edges(scc_sorted, internal)
    scc_edges = [{"source": s, "dest": d, "type": 0} for (s, d) in internal if (s, d) not in back]
    sres = engine.layout([by_id[i] for i in scc_sorted], scc_edges)
    spos = sres["positions"]
    if len(spos) != len(scc):
        return dispatch_layout(nodes, edges, opts=opts, subset=subset)
    xs = [p["x"] for p in spos.values()]
    ys = [p["y"] for p in spos.values()]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    # 2. collapse: the cycle becomes one meta-node sized as its band; external edges redirect.
    col_nodes = [n for n in nodes if n["id"] not in scc]
    col_nodes.append({"id": _META, "width": (maxx - minx) + 96.0, "height": (maxy - miny) + 96.0,
                      "parent_id": None, "kind": "square", "position": {"x": cx, "y": cy}})
    seen = set()
    col_edges = []
    for e in edges:
        s = _META if e["source"] in scc else e["source"]
        d = _META if e["dest"] in scc else e["dest"]
        if s == d or (s, d) in seen:
            continue
        seen.add((s, d))
        col_edges.append({"source": s, "dest": d, "type": e.get("type", 0)})
    cres = dispatch_layout(col_nodes, col_edges, opts=opts, subset=None)
    cpos = cres["positions"]
    mp = cpos.get(_META, {"x": cx, "y": cy})

    # 3. expand: drop the cycle back in, centred on where the meta-node landed. Two shapes are
    # tried -- the compact two-row RING (preferred: the loop visibly circulates) and the
    # DAG band -- and the one with fewer crossings (then shorter max edge) wins.
    epairs = [(e["source"], e["dest"]) for e in edges
              if e["source"] in by_id and e["dest"] in by_id and e["source"] != e["dest"]]
    base = {i: dict(cpos[i]) for i in cpos if i != _META}
    variants = []
    rpos = _ring_positions(scc_sorted, scc_edges, back)
    for tag, shape in (("ring", rpos), ("band", spos)):
        xs2 = [p["x"] for p in shape.values()]
        ys2 = [p["y"] for p in shape.values()]
        scx, scy = (min(xs2) + max(xs2)) / 2.0, (min(ys2) + max(ys2)) / 2.0
        full = dict(base)
        for i in scc:
            full[i] = {"x": mp["x"] + (shape[i]["x"] - scx), "y": mp["y"] + (shape[i]["y"] - scy)}
        variants.append((_score(full, epairs), tag, full))
    variants.sort(key=lambda v: v[0])                  # ring listed first -> wins ties
    final = variants[0][2]
    return {"positions": final, "areas": cres.get("areas", {}), "bbox": cres.get("bbox", {})}
