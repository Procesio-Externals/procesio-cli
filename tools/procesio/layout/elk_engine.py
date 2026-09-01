"""Opt-in ELK 'layered' (Sugiyama) canvas layout — a drop-in alternative to engine.py.

WHAT THIS IS
------------
A second, independent auto-layout implementation with the *exact same I/O contract* as
`engine.layout` (positions = absolute node CENTERS, areas = absolute container frames,
plus a bbox). It maps the PROCESIO node/edge graph onto the Eclipse Layout Kernel's
`layered` algorithm (elkjs) and translates the result back. The legacy engine is untouched
and remains the default; this one is selected via the LAYOUT_ENGINE flag (see dispatch.py).

HOW TO FLIP THE FLAG
--------------------
    setx LAYOUT_ENGINE elk          # or: $env:LAYOUT_ENGINE = "elk"  (this shell)
    LAYOUT_ENGINE=elk python ...    # bash

`dispatch.layout()` reads it: `elk` → this module; anything else / unset → legacy. Nothing
in the UI or tool.yaml changes.

HOW IT RUNS (process boundary)
------------------------------
The legacy engine runs backend-side, in-process, synchronously. There is no pure-Python
ELK, so ELK runs backend-side too: elkjs is invoked through a *synchronous* Node subprocess
(`elk/elk_runner.mjs`), offline (no network). If Node or elkjs is unavailable, or ELK errors
on a graph, this module logs and DEGRADES GRACEFULLY to the legacy engine — callers always
get a valid layout.

TUNING FOR READABILITY
----------------------
All ELK knobs are named constants just below, each commented. The layout is tuned for a clean,
untangled left-to-right process flow: NETWORK_SIMPLEX layering aligns parallel branches,
Brandes-Köpf BALANCED placement straightens chains, wrapping is OFF (a wide scrollable flow
reads better than stacked bands), and disconnected sub-flows are packed close. Top-level
spacing is NODE_NODE_SPACING / NODE_NODE_BETWEEN_LAYERS; inside For-Each containers it is
CONTAINER_BETWEEN_LAYERS / CONTAINER_NODE_NODE. To bound width instead, set
WRAPPING_STRATEGY="SINGLE_EDGE" and re-add an aspect ratio — at the cost of fragmenting read.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tools.procesio.layout import engine  # reused ONLY for graceful fallback; never mutated

# ---------------------------------------------------------------------------
# ELK tunables — all named + commented so the width/height tradeoff is easy to tweak.
# ---------------------------------------------------------------------------
ALGORITHM = "layered"          # the Sugiyama layered algorithm.
DIRECTION = "RIGHT"            # left-to-right flow, matching the PROCESIO canvas.
# Layering: NETWORK_SIMPLEX minimises total edge length, which ALIGNS parallel branches and
# keeps chains on one rank line (longest-path staggers them). The biggest readability win.
LAYERING_STRATEGY = "NETWORK_SIMPLEX"
# Wrapping OFF → a clean, uninterrupted left-to-right flow. Wrapping ("SINGLE_EDGE" +
# an aspect ratio) bounds width by folding long runs into stacked rows, but for process
# flows that fragments the read; a wide, scrollable, untangled flow is more understandable.
WRAPPING_STRATEGY = "OFF"
# Crossing minimisation: barycenter/median layer-sweep passes.
CROSSING_MIN_STRATEGY = "LAYER_SWEEP"
# Node placement: Brandes-Köpf balanced coordinates with BALANCED alignment — straightens
# chains and centres parallel branches (groups consecutive actions into one run).
NODE_PLACEMENT_STRATEGY = "BRANDES_KOEPF"
BK_ALIGNMENT = "BALANCED"
# Lay each disconnected sub-flow out on its own, then pack them CLOSE (componentComponent
# gap) instead of scattering them across the canvas with huge empty gaps.
SEPARATE_COMPONENTS = "true"
COMPONENT_SPACING = 50
# Post-compaction pulls nodes left to squeeze out slack, shortening long edges.
POST_COMPACTION = "LEFT"
# Lay compound (container) contents out in the SAME layered pass as their parents, so edges
# that cross hierarchy levels (a For-Each container ↔ its inner actions) are legal and routed.
# Without this ELK rejects a container→child edge (UnsupportedGraphException).
HIERARCHY_HANDLING = "INCLUDE_CHILDREN"
# Spacing (px). node-node = VERTICAL gap between action rows sharing a rank; between-layers =
# HORIZONTAL gap between ranks (also the room after a decisional, and for its branch labels).
# Calibrated to the user's hand-layout (row gaps ~120-160; branch labels need horizontal room).
NODE_NODE_SPACING = 130
NODE_NODE_BETWEEN_LAYERS = 120
# Inner padding of a compound (For-Each) container. Extra room on the LEFT leaves space for
# the implicit ForEach-Start, mirroring the legacy container convention. ELK format string.
CONTAINER_PADDING = "[top=52,left=104,bottom=100,right=48]"
# Spacing INSIDE a compound container. Larger than the top-level between-layers so the
# container's inner action chain doesn't cram its labels together (a real readability defect
# on For-Each bodies). Tune these up if inner labels still collide.
CONTAINER_BETWEEN_LAYERS = 150
CONTAINER_NODE_NODE = 70
# Minimum For-Each frame (px). A floor so a 1-2 node For-Each still has room; larger bodies
# grow past it from content + padding. Matches the user's hand-sized container (~W791 H200).
CONTAINER_MIN_W = 320
CONTAINER_MIN_H = 200
# Clustering: fold a straight run of MORE THAN CLUSTER_MIN consecutive 1-in / 1-out actions
# (Start/Stop included; NOT inside a For-Each; a branch/merge/error-port breaks the run) into a
# compact serpentine block — down a column of CLUSTER_WRAP, up the next — so a long linear chain
# stops sprawling the canvas wide. The block is reserved to ELK as ONE node, so no overlaps.
CLUSTER_ENABLED = True
CLUSTER_MIN = 6      # cluster runs LONGER than this (>= 7 nodes); 6-node entry spines stay
                     # horizontal, matching the reference hand-layout of the ANAF entry
CLUSTER_WRAP = 4     # nodes stacked per serpentine column before wrapping
CLUSTER_DX = 170     # serpentine column spacing (centre→centre)
CLUSTER_DY = 150     # serpentine row spacing (centre→centre)
# PROCESIO branch conventions (post-ELK): an error-port target, and a decisional's DEFAULT
# target that leads to a dead-end (Stop/Throw/private chain, NOT a Join and not a rejoining
# path), is moved PERPENDICULAR to the flow — directly above/below its source (same x) — with
# its private chain continuing right along that lane. Default→Join and a default that rejoins
# the main flow stay in-flow. PERP_LANE_GAP is the vertical offset to that lane.
BRANCH_CONVENTIONS = True
PERP_LANE_GAP = 185
# A DEFAULT branch only drops perpendicular when it goes ~directly to a terminal (a stop-branch,
# chain <= SHORT_DEADEND). A LONGER default chain is the decisional's main processing path and
# stays IN-FLOW. Error ports always drop perpendicular regardless of length.
SHORT_DEADEND = 2
# Fixed seed → deterministic output (same graph in → same layout out), matching the legacy
# engine's determinism guarantee.
RANDOM_SEED = 1

DEFAULT_W = 48.0
DEFAULT_H = 48.0

_RUNNER = Path(__file__).with_name("elk") / "elk_runner.mjs"
_SUBPROCESS_TIMEOUT = 60  # seconds; a runaway ELK run must not hang the tool


def _log(msg: str) -> None:
    """Progress/diagnostics go to stderr only (stdout is reserved for tool JSON)."""
    print(f"[elk_engine] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# node normalisation — same dimension source as the legacy engine's _node()
# ---------------------------------------------------------------------------

def _norm(n: dict) -> dict:
    pos = n.get("position") or {"x": n.get("x", 0.0), "y": n.get("y", 0.0)}
    w = n.get("width") or (n.get("size") or {}).get("w") or DEFAULT_W
    h = n.get("height") or (n.get("size") or {}).get("h") or DEFAULT_H
    try:
        w = float(w) or DEFAULT_W
    except (TypeError, ValueError):
        w = DEFAULT_W
    try:
        h = float(h) or DEFAULT_H
    except (TypeError, ValueError):
        h = DEFAULT_H
    return {
        "id": n["id"],
        "w": w,
        "h": h,
        "parent_id": n.get("parent_id"),
        "kind": n.get("kind") or n.get("shape"),
        "pos": {"x": float((pos or {}).get("x", 0.0) or 0.0),
                "y": float((pos or {}).get("y", 0.0) or 0.0)},
    }


# ---------------------------------------------------------------------------
# graph translation: PROCESIO nodes/edges -> ELK graph JSON
# ---------------------------------------------------------------------------

def _ancestors(nid: str, parent_of: dict) -> list[str]:
    """[nid, parent, ..., 'root'] — the id's ancestor chain up to the synthetic root."""
    chain = [nid]
    seen = {nid}
    cur = parent_of.get(nid, "root")
    while True:
        chain.append(cur)
        if cur == "root" or cur in seen:
            break
        seen.add(cur)
        cur = parent_of.get(cur, "root")
    return chain


def _lca(a: str, b: str, parent_of: dict) -> str:
    """Lowest common ancestor of two node ids in the containment tree. An edge is declared
    in its endpoints' LCA so hierarchy-crossing edges (container -> child) stay legal."""
    aset = set(_ancestors(a, parent_of))
    for x in _ancestors(b, parent_of):
        if x in aset:
            return x
    return "root"


def _build_elk_graph(nodes: list[dict], edges: list[dict],
                     extra_opts: dict | None = None) -> dict:
    """Translate normalised nodes + raw edges into the ELK graph JSON the runner consumes.

    - Each action -> an ELK node with its real width/height.
    - A node that has children -> an ELK COMPOUND node (children nested, laid out recursively
      by ELK); its own size is left for ELK to compute from its contents.
    - Each connection -> an ELK edge (direction preserved). Back/cycle edges are passed
      through unchanged — the layered algorithm resolves cycles internally.
    - Ports are intentionally NOT modelled: the PROCESIO JSON carries no per-connector
      attachment points (edge endpoints are node ids), so inventing ports would be wrong.
    """
    by_id = {n["id"]: n for n in nodes}
    parent_of = {n["id"]: (n["parent_id"] if n["parent_id"] in by_id else "root")
                 for n in nodes}
    children_of: dict[str, list[str]] = {"root": []}
    for n in nodes:
        children_of.setdefault(parent_of[n["id"]], []).append(n["id"])
        children_of.setdefault(n["id"], children_of.get(n["id"], []))

    # bucket edges by the container they must be declared in (their endpoints' LCA)
    edges_in: dict[str, list[dict]] = {}
    dropped = 0
    for i, e in enumerate(sorted(edges, key=lambda e: (str(e.get("source")),
                                                       str(e.get("dest")),
                                                       int(e.get("type", 0) or 0)))):
        s, d = e.get("source"), e.get("dest")
        if s not in by_id or d not in by_id or s == d:
            dropped += 1
            continue
        host = _lca(s, d, parent_of)
        edges_in.setdefault(host, []).append(
            {"id": f"e{i}", "sources": [s], "targets": [d]})
    if dropped:
        _log(f"dropped {dropped} edge(s) with a missing endpoint or self-loop")

    def build_node(nid: str) -> dict:
        kids = sorted(children_of.get(nid, []))
        node: dict = {"id": nid}
        if kids:
            # compound: nest children, let ELK size the frame from its contents, and recurse
            # the layered layout inside with the same tunables.
            node["children"] = [build_node(k) for k in kids]
            node["layoutOptions"] = {
                "elk.padding": CONTAINER_PADDING,
                # inherit the root's algorithm/direction/hierarchyHandling (one layered pass
                # across the hierarchy); just size the frame from its contents.
                "elk.hierarchyHandling": "INHERIT",
                # roomier spacing inside the container so its inner chain's labels don't cram
                "elk.layered.spacing.nodeNodeBetweenLayers": str(CONTAINER_BETWEEN_LAYERS),
                "elk.spacing.nodeNode": str(CONTAINER_NODE_NODE),
            }
        else:
            node["width"] = by_id[nid]["w"]
            node["height"] = by_id[nid]["h"]
        if nid in edges_in:
            node["edges"] = edges_in[nid]
        return node

    root = {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": ALGORITHM,
            "elk.direction": DIRECTION,
            "elk.hierarchyHandling": HIERARCHY_HANDLING,
            "elk.layered.layering.strategy": LAYERING_STRATEGY,
            "elk.layered.wrapping.strategy": WRAPPING_STRATEGY,
            "elk.layered.crossingMinimization.strategy": CROSSING_MIN_STRATEGY,
            "elk.layered.nodePlacement.strategy": NODE_PLACEMENT_STRATEGY,
            "elk.layered.nodePlacement.bk.fixedAlignment": BK_ALIGNMENT,
            "elk.separateConnectedComponents": SEPARATE_COMPONENTS,
            "elk.spacing.componentComponent": str(COMPONENT_SPACING),
            "elk.layered.compaction.postCompaction.strategy": POST_COMPACTION,
            "elk.layered.spacing.nodeNodeBetweenLayers": str(NODE_NODE_BETWEEN_LAYERS),
            "elk.spacing.nodeNode": str(NODE_NODE_SPACING),
            "elk.spacing.edgeNode": "25",
            "elk.layered.spacing.edgeNodeBetweenLayers": "30",
            "elk.randomSeed": str(RANDOM_SEED),
        },
        "children": [build_node(nid) for nid in sorted(children_of["root"])],
    }
    # optional per-call overrides (opts["elk"]) — for tuning without editing the constants.
    # A None value REMOVES that option key entirely.
    for k, v in (extra_opts or {}).items():
        if v is None:
            root["layoutOptions"].pop(k, None)
        else:
            root["layoutOptions"][k] = str(v)
    if "root" in edges_in:
        root["edges"] = edges_in["root"]
    return root


# ---------------------------------------------------------------------------
# run ELK (synchronous Node subprocess) + translate coordinates back
# ---------------------------------------------------------------------------

def _run_elk(graph: dict) -> dict:
    """Invoke elkjs via the Node runner. Returns the laid-out graph, or raises on any
    failure (missing node/elkjs, timeout, ELK error) so the caller can fall back."""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node executable not found on PATH")
    if not _RUNNER.exists():
        raise RuntimeError(f"elk runner missing: {_RUNNER}")
    proc = subprocess.run(
        [node, str(_RUNNER)],
        input=json.dumps(graph).encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=_SUBPROCESS_TIMEOUT,
    )
    out = proc.stdout.decode("utf-8", "replace").strip()
    if not out:
        raise RuntimeError(f"elk runner produced no output (exit {proc.returncode}); "
                           f"stderr: {proc.stderr.decode('utf-8', 'replace')[:400]}")
    laid = json.loads(out)
    if isinstance(laid, dict) and laid.get("error"):
        raise RuntimeError(f"elk runner error: {laid['error']}")
    if proc.returncode != 0:
        raise RuntimeError(f"elk runner exit {proc.returncode}")
    return laid


def _harvest(laid: dict) -> tuple[dict, dict]:
    """Walk the laid-out ELK graph, accumulating absolute offsets, and produce the legacy
    contract: positions = absolute node CENTERS (every node incl. compounds + children),
    areas = absolute container frames (top-left + size)."""
    positions: dict = {}
    areas: dict = {}

    def walk(node: dict, off_x: float, off_y: float) -> None:
        for child in node.get("children", []) or []:
            # ELK x/y are the child's top-left RELATIVE to this node's content origin.
            tlx = off_x + float(child.get("x", 0.0) or 0.0)
            tly = off_y + float(child.get("y", 0.0) or 0.0)
            kids = child.get("children") or []
            if kids:
                w = max(float(child.get("width", DEFAULT_W) or DEFAULT_W), CONTAINER_MIN_W)
                h = max(float(child.get("height", DEFAULT_H) or DEFAULT_H), CONTAINER_MIN_H)
                areas[child["id"]] = {"x": tlx, "y": tly, "width": w, "height": h}
                positions[child["id"]] = {"x": tlx + w / 2, "y": tly + h / 2}
                walk(child, tlx, tly)  # children are positioned inside this frame
            else:
                w = float(child.get("width", DEFAULT_W) or DEFAULT_W)
                h = float(child.get("height", DEFAULT_H) or DEFAULT_H)
                positions[child["id"]] = {"x": tlx + w / 2, "y": tly + h / 2}

    walk(laid, float(laid.get("x", 0.0) or 0.0), float(laid.get("y", 0.0) or 0.0))
    return positions, areas


# ---------------------------------------------------------------------------
# serpentine clustering of long straight runs (pre-collapse → ELK → expand)
# ---------------------------------------------------------------------------

def _serpentine_size(k: int) -> tuple[float, float]:
    cols = (k + CLUSTER_WRAP - 1) // CLUSTER_WRAP
    rows = min(k, CLUSTER_WRAP)
    return (cols - 1) * CLUSTER_DX + DEFAULT_W, (rows - 1) * CLUSTER_DY + DEFAULT_H


def _find_straight_runs(ns: list[dict], edges: list[dict]) -> list[list[str]]:
    """Maximal chains of top-level, 1-in/1-out actions (Start/Stop included) connected by
    private edges, NOT inside a For-Each. A branch (out>1, incl. an error port), a merge
    (in>1), or a container boundary ends the run. Only runs longer than CLUSTER_MIN returned."""
    by = {n["id"]: n for n in ns}
    area_ids = {n["id"] for n in ns if n["kind"] == "area"}
    ids = set(by)
    indeg = {i: 0 for i in ids}
    outdeg = {i: 0 for i in ids}
    norm = []
    for e in (edges or []):
        s, d, tp = e.get("source"), e.get("dest"), int(e.get("type", 0) or 0)
        if s in ids and d in ids and s != d:
            outdeg[s] += 1            # counts normal AND error edges → an error handler = branch
            indeg[d] += 1
            if tp == 0:
                norm.append((s, d))

    def straight(nid):
        n = by[nid]
        return (n["kind"] != "area" and n["parent_id"] not in area_ids
                and indeg[nid] <= 1 and outdeg[nid] <= 1)

    nnext, nprev = {}, {}
    for s, d in norm:
        if straight(s) and straight(d):
            nnext[s] = d
            nprev[d] = s
    runs, seen = [], set()
    for s in sorted(u for u in ids if straight(u) and u in nnext and u not in nprev):
        if s in seen:
            continue
        run, cur = [s], s
        seen.add(s)
        while cur in nnext and nnext[cur] not in seen:
            cur = nnext[cur]
            run.append(cur)
            seen.add(cur)
        if len(run) > CLUSTER_MIN:
            runs.append(run)
    return runs


def _collapse_runs(ns, edges, runs):
    """Replace each run with one meta-node sized as its serpentine block; rewire edges to it."""
    node_to_meta, metas, meta_map = {}, [], {}
    for k, run in enumerate(runs):
        mid = f"__cluster{k}"
        w, h = _serpentine_size(len(run))
        metas.append({"id": mid, "w": w, "h": h, "parent_id": None, "kind": None,
                      "pos": {"x": 0.0, "y": 0.0}})
        meta_map[mid] = run
        for nid in run:
            node_to_meta[nid] = mid
    run_nodes = set(node_to_meta)
    new_ns = [n for n in ns if n["id"] not in run_nodes] + metas
    new_edges, seen_e = [], set()
    for e in (edges or []):
        s, d, tp = e.get("source"), e.get("dest"), int(e.get("type", 0) or 0)
        ms, md = node_to_meta.get(s, s), node_to_meta.get(d, d)
        if ms == md or (ms, md, tp) in seen_e:
            continue
        seen_e.add((ms, md, tp))
        new_edges.append({"source": ms, "dest": md, "type": tp})
    return new_ns, new_edges, meta_map


def _expand_serpentine(positions: dict, mid: str, run: list[str]) -> None:
    """Replace a placed meta-node with its run laid out as a serpentine inside the block."""
    c = positions.pop(mid)
    w, h = _serpentine_size(len(run))
    mx, my = c["x"] - w / 2, c["y"] - h / 2
    rows = min(len(run), CLUSTER_WRAP)
    for i, nid in enumerate(run):
        col, r = i // CLUSTER_WRAP, i % CLUSTER_WRAP
        row = r if col % 2 == 0 else (rows - 1 - r)      # boustrophedon: down, then up
        positions[nid] = {"x": mx + DEFAULT_W / 2 + col * CLUSTER_DX,
                          "y": my + DEFAULT_H / 2 + row * CLUSTER_DY}


# ---------------------------------------------------------------------------
# PROCESIO branch conventions: error / default-dead-end targets -> perpendicular lane
# ---------------------------------------------------------------------------

def _lane_collides(cand: dict, others: dict, by: dict) -> bool:
    for cid, cp in cand.items():
        cw = by.get(cid, {}).get("w", DEFAULT_W)
        ch = by.get(cid, {}).get("h", DEFAULT_H)
        for oid, op in others.items():
            ow = by.get(oid, {}).get("w", DEFAULT_W)
            oh = by.get(oid, {}).get("h", DEFAULT_H)
            if abs(cp["x"] - op["x"]) < (cw + ow) / 2 and abs(cp["y"] - op["y"]) < (ch + oh) / 2 + 1:
                return True
    return False


def _apply_branch_conventions(positions: dict, ns: list[dict], edges: list[dict]) -> dict:
    """Move error / default-dead-end targets to a perpendicular lane at the source's column.
    A dead-end = a private chain that ends in a terminal WITHOUT passing through a merge (Join);
    so default->Join and a default that rejoins the flow return no chain and stay in-flow.
    Loop-backs (target upstream) and For-Each members are left alone. Collision-checked; if no
    clear lane is found the chain is left where ELK placed it (safe no-op)."""
    by = {n["id"]: n for n in ns}
    ids = set(by)
    area_ids = {n["id"] for n in ns if n["kind"] == "area"}

    def movable(nid):
        return nid in by and by[nid]["kind"] != "area" and by[nid]["parent_id"] not in area_ids

    norm_succ, indeg_norm = {}, {}
    for e in edges:
        s, d, tp = e["source"], e["dest"], int(e.get("type", 0) or 0)
        if tp == 0 and s in ids and d in ids and s != d:
            norm_succ.setdefault(s, []).append(d)
            indeg_norm[d] = indeg_norm.get(d, 0) + 1

    def deadend(tgt):
        chain, cur = [], tgt
        while True:
            if indeg_norm.get(cur, 0) > 1:          # a merge (Join) -> rejoins the flow
                return None
            chain.append(cur)
            outs = [d for d in norm_succ.get(cur, []) if d in ids]
            if not outs:
                return chain                        # terminal -> private dead-end chain
            if len(outs) > 1 or outs[0] in chain:
                return None                         # branches / cycle -> not a simple dead-end
            cur = outs[0]

    DX = NODE_NODE_BETWEEN_LAYERS + DEFAULT_W
    moves = []
    for e in edges:
        s, d, tp = e["source"], e["dest"], int(e.get("type", 0) or 0)
        if s not in ids or d not in ids or s == d or s not in positions or d not in positions:
            continue
        if not (tp == 1 or bool(e.get("is_default"))):
            continue
        if positions[d]["x"] < positions[s]["x"] - 24:   # loop-back -> leave in place
            continue
        if not movable(s):
            continue
        chain = deadend(d)
        if chain and all(movable(c) for c in chain):
            if tp == 1 or len(chain) <= SHORT_DEADEND:   # error: always; default: stop-branch only
                moves.append((s, chain))

    moved = set()
    for s, chain in sorted(moves, key=lambda m: positions[m[0]]["x"]):
        if any(c in moved for c in chain):
            continue
        sx, sy = positions[s]["x"], positions[s]["y"]
        for mult in range(1, 10):
            done = False
            for direction in (1, -1):               # prefer below, then above
                lane_y = sy + direction * mult * PERP_LANE_GAP
                cand = {chain[i]: {"x": sx + i * DX, "y": lane_y} for i in range(len(chain))}
                others = {i: positions[i] for i in positions if i not in chain}
                if not _lane_collides(cand, others, by):
                    positions.update(cand)
                    moved.update(chain)
                    done = True
                    break
            if done:
                break
    return positions


# ---------------------------------------------------------------------------
# public entry: same signature as engine.layout
# ---------------------------------------------------------------------------

def layout(nodes: list[dict], edges: list[dict], opts: dict | None = None,
           subset: list[str] | None = None) -> dict:
    """Lay out a node/edge graph with ELK 'layered'. Same contract as engine.layout:
    returns {positions:{id:{x,y}}, areas:{id:{x,y,width,height}}, bbox}.

    `subset` (partial re-tidy) is a legacy-only capability (ELK is not incremental), so a
    subset request is delegated to the legacy engine. Any ELK failure also falls back to
    legacy — the caller always gets a valid layout."""
    if subset is not None:
        _log("subset/partial re-tidy requested → delegating to legacy engine (ELK is not "
             "incremental)")
        return engine.layout(nodes, edges, opts=opts, subset=subset)

    ns = [_norm(n) for n in nodes]
    if not ns:
        return {"positions": {}, "areas": {},
                "bbox": {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0}}

    # pre-collapse long straight runs into serpentine meta-nodes (ELK reserves their space)
    runs = _find_straight_runs(ns, edges or []) if CLUSTER_ENABLED else []
    cns, cedges, meta_map = (_collapse_runs(ns, edges or [], runs) if runs
                             else (ns, list(edges or []), {}))
    if runs:
        _log(f"clustered {len(runs)} straight run(s) of sizes {[len(r) for r in runs]}")

    try:
        graph = _build_elk_graph(cns, cedges, extra_opts=(opts or {}).get("elk"))
        laid = _run_elk(graph)
        positions, areas = _harvest(laid)
        for mid, run in meta_map.items():        # expand each serpentine block in place
            if mid in positions:
                _expand_serpentine(positions, mid, run)
        if BRANCH_CONVENTIONS:
            _apply_branch_conventions(positions, ns, edges or [])
    except Exception as exc:  # noqa: BLE001 — any ELK failure must degrade, not crash
        _log(f"ELK layout failed ({type(exc).__name__}: {exc}); falling back to legacy engine")
        return engine.layout(nodes, edges, opts=opts, subset=subset)

    # guard: every input node must have landed with finite coordinates; otherwise fall back
    missing = [n["id"] for n in ns if n["id"] not in positions]
    bad = [i for i, p in positions.items()
           if not (isinstance(p["x"], float) and isinstance(p["y"], float))
           or p["x"] != p["x"] or p["y"] != p["y"]]  # NaN self-inequality
    if missing or bad:
        _log(f"ELK output incomplete (missing={missing[:5]} nan={bad[:5]}); "
             f"falling back to legacy engine")
        return engine.layout(nodes, edges, opts=opts, subset=subset)

    xs = [p["x"] for p in positions.values()] or [0]
    ys = [p["y"] for p in positions.values()] or [0]
    return {"positions": positions, "areas": areas,
            "bbox": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}}
