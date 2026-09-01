"""Pure, deterministic layered graph layout (Sugiyama) tuned for PROCESIO readability.

Pipeline per coordinate space:
  1. longest-path layering (x = layer * DX) — left-to-right, sources at the left.
  2. dummy nodes on every edge spanning >1 layer, so long edges route as straight
     horizontal lanes through dummies instead of cutting across the canvas.
  3. crossing-minimization: weighted-median ordering sweeps + a transpose (adjacent
     swap) step, keeping the lowest-crossing order seen.
  4. y-coordinate straightening: median relaxation pulls each node onto its neighbours'
     median y (dummies included), so a chain lands on ONE row and parallel chains become
     parallel straight lanes; per-layer min-gap keeps lanes apart.
  5. error-port targets drop to a lane below the happy path.
  6. compaction via a tight DX/DY; For-Each container bodies laid out recursively.

No PROCESIO imports, no I/O. Same input -> same output (all sorts are id-stable, all
iteration counts fixed).
"""
from __future__ import annotations

from collections import defaultdict

DEFAULTS = {
    "DX": 160, "DY": 180, "NODE_W": 48, "NODE_H": 48,
    "AREA_PAD": 40, "MARGIN": 80, "ERR_GAP": 200,
    "ORDER_ITERS": 8, "RELAX_ITERS": 16, "DUMMY_H": 1, "FOLD_MAX": 5,
    "DY_AFTER_DECISIONAL": 240,
    "FE_START_PAD": 32, "FE_TOP": 78, "FE_RIGHT_PAD": 100, "FE_BOTTOM_PAD": 125,
    "CLUSTER": False, "CLUSTER_MIN": 5, "CLUSTER_WRAP": 4,
    "MINIMIZE_CROSSINGS": True, "MINCROSS_ITERS": 6, "MINCROSS_RANGE": 6,
    "MINCROSS_MOVE_PENALTY": 0.25, "MINCROSS_LEN_PENALTY": 0.0,
}


def _node(n: dict) -> dict:
    pos = n.get("position") or {"x": n.get("x", 0.0), "y": n.get("y", 0.0)}
    return {
        "id": n["id"],
        "w": n.get("width") or n.get("size", {}).get("w") or DEFAULTS["NODE_W"],
        "h": n.get("height") or n.get("size", {}).get("h") or DEFAULTS["NODE_H"],
        "parent_id": n.get("parent_id"),
        "kind": n.get("kind") or n.get("shape"),
        "pos": {"x": float(pos.get("x", 0.0)), "y": float(pos.get("y", 0.0))},
    }


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    if n % 2:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _longest_path_layers(ids: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """layer(v) = longest path from any source to v. Cycle-safe (bounded relaxation;
    a back-edge simply stops extending). A second ALAP pass then pulls single-successor
    chains RIGHT, adjacent to their join: a short branch that merges into a long one used
    to keep its early (ASAP) layers, stretching its join edge across the canvas (Networky
    v2: Map Route A -> Join Route spanned 8 layers / 1450px). Pulling u to
    min(layer(succ))-1 when ALL of u's out-edges point right keeps the graph valid and
    makes branch tails land next to their merge point."""
    layer = {i: 0 for i in ids}
    for _ in range(len(ids) + 1):
        changed = False
        for s, d in edges:
            if layer[s] + 1 > layer[d]:
                layer[d] = layer[s] + 1
                changed = True
        if not changed:
            break
    # ALAP pull (bounded sweeps; skips back-edges which would point left). Branch HEADS stay
    # anchored at their split (a node whose predecessor fans out keeps its ASAP layer), so a
    # short branch hugs its join at the TAIL while its head remains next to the decisional -
    # the slack becomes one long parallel bypass edge instead of a head edge crossing lanes.
    out = defaultdict(list)
    inc = defaultdict(list)
    for s, d in edges:
        out[s].append(d)
        inc[d].append(s)
    branch_heads = {u for u in ids if any(len(out.get(p, [])) > 1 for p in inc.get(u, []))}
    for _ in range(len(ids) + 1):
        changed = False
        for u in ids:
            if u in branch_heads:
                continue
            succs = [d for d in out.get(u, []) if layer[d] > layer[u]]
            if not succs or len(succs) != len(out.get(u, [])):
                continue                       # sink, or has a back/flat edge - leave anchored
            want = min(layer[d] for d in succs) - 1
            if want > layer[u]:
                layer[u] = want
                changed = True
        if not changed:
            break
    return layer


def _back_edges(ids, edges) -> set:
    """Back-edges of the graph via iterative DFS (an edge to a node still on the DFS
    stack = a cycle's return edge). Deterministic in  order."""
    idset = set(ids)
    succ = defaultdict(list)
    for s, d in edges:
        if s in idset and d in idset:
            succ[s].append(d)
    color = {i: 0 for i in ids}          # 0 white, 1 on-stack, 2 done
    back = set()
    for root in ids:
        if color[root] != 0:
            continue
        color[root] = 1
        stack = [(root, iter(succ.get(root, [])))]
        while stack:
            u, it = stack[-1]
            nxt = None
            for v in it:
                if color[v] == 0:
                    nxt = v
                    break
                if color[v] == 1:
                    back.add((u, v))
            if nxt is None:
                color[u] = 2
                stack.pop()
            else:
                color[nxt] = 1
                stack.append((nxt, iter(succ.get(nxt, []))))
    return back


def _layer_inversions(orderL: list, orderL1: list, down: dict) -> int:
    idx1 = {n: i for i, n in enumerate(orderL1)}
    seq = [idx1[m] for n in orderL for m in down.get(n, []) if m in idx1]
    inv = 0
    for i in range(len(seq)):
        si = seq[i]
        for j in range(i + 1, len(seq)):
            if si > seq[j]:
                inv += 1
    return inv


def _total_crossings(order: dict, down: dict, maxL: int) -> int:
    return sum(_layer_inversions(order.get(L, []), order.get(L + 1, []), down)
               for L in range(maxL))


def _wmedian(order: dict, L: int, adj_layer: int, neigh: dict) -> None:
    idx_adj = {n: i for i, n in enumerate(order.get(adj_layer, []))}
    cur = {n: i for i, n in enumerate(order[L])}

    def key(n):
        ps = sorted(idx_adj[x] for x in neigh.get(n, []) if x in idx_adj)
        return _median(ps) if ps else float(cur[n])
    order[L] = sorted(order[L], key=lambda n: (key(n), str(n)))


def _transpose(order: dict, down: dict, maxL: int) -> None:
    def local(L):
        c = _layer_inversions(order.get(L, []), order.get(L + 1, []), down)
        if L > 0:
            c += _layer_inversions(order.get(L - 1, []), order.get(L, []), down)
        return c
    improved = True
    guard = 0
    while improved and guard < 8:
        improved = False
        guard += 1
        for L in range(maxL + 1):
            ol = order[L]
            for i in range(len(ol) - 1):
                before = local(L)
                ol[i], ol[i + 1] = ol[i + 1], ol[i]
                if local(L) < before:
                    improved = True
                else:
                    ol[i], ol[i + 1] = ol[i + 1], ol[i]


def _place(order_L: list, desired: dict, ue: dict, de: dict, gap: float) -> dict:
    """Assign y to a layer's nodes as close as possible to `desired` while keeping the
    given order with a minimum gap. Solves it as isotonic regression (pool-adjacent-
    violators) on the gap-shifted target, so a chain stays straight and there is no
    systematic drift. `ue`/`de` are per-node up/down half-extents (asymmetric: a folded
    decisional reserves its fold's height on the fold side)."""
    n = len(order_L)
    if not n:
        return {}
    sep = [0.0] * n
    for i in range(1, n):
        sep[i] = de[order_L[i - 1]] + gap + ue[order_L[i]]
    cum = [0.0] * n
    for i in range(1, n):
        cum[i] = cum[i - 1] + sep[i]
    # fit a non-decreasing sequence to t[i] = desired - cum[i]; PAVA with mean pools
    pools = []  # [sum, count, mean]
    for i in range(n):
        ti = desired[order_L[i]] - cum[i]
        pools.append([ti, 1, ti])
        while len(pools) >= 2 and pools[-2][2] > pools[-1][2]:
            s2, c2, _ = pools.pop()
            s1, c1, _ = pools.pop()
            s, c = s1 + s2, c1 + c2
            pools.append([s, c, s / c])
    z = []
    for s, c, _m in pools:
        z += [s / c] * c
    return {order_L[i]: z[i] + cum[i] for i in range(n)}


def _layout_layer(nodes: list[dict], typed_edges: list[tuple[str, str, int]], o: dict,
                  extents: dict | None = None) -> dict:
    ids = [n["id"] for n in nodes]
    if not ids:
        return {"positions": {}, "bbox": {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0}}
    sizes = {n["id"]: (n["w"], n["h"]) for n in nodes}
    idset = set(ids)
    norm = [(s, d) for (s, d, t) in typed_edges if s in idset and d in idset and s != d and t == 0]
    errs = [(s, d) for (s, d, t) in typed_edges if s in idset and d in idset and s != d and t == 1]
    err_targets = {d for _s, d in errs}
    all_edges = list(dict.fromkeys(norm + errs))

    bk = _back_edges(ids, all_edges)
    layer = _longest_path_layers(ids, [e for e in all_edges if e not in bk])

    # working node geometry (reals + dummies) keyed by id
    vlayer = {i: layer[i] for i in ids}
    vh = {i: sizes[i][1] for i in ids}
    # dummy chains for normal edges that span more than one layer
    segs: list[tuple[str, str]] = []
    dn = [0]

    def new_dummy(L):
        did = f"__d{dn[0]}"
        dn[0] += 1
        vlayer[did] = L
        vh[did] = o["DUMMY_H"]
        return did
    for s, d in norm:
        ls, ld = layer[s], layer[d]
        if ld - ls == 1:
            segs.append((s, d))
        elif ld - ls > 1:
            prev = s
            for L in range(ls + 1, ld):
                nd = new_dummy(L)
                segs.append((prev, nd))
                prev = nd
            segs.append((prev, d))
        # edges that don't go strictly one+ layers right (cycles/flat) are dropped from
        # routing; they remain as ports the designer draws, just not laid-out lanes.

    down: dict = defaultdict(list)
    up: dict = defaultdict(list)
    for a, b in segs:                       # a in layer L, b in layer L+1 by construction
        down[a].append(b)
        up[b].append(a)

    layers: dict = defaultdict(list)
    for i in vlayer:
        layers[vlayer[i]].append(i)
    maxL = max(layers) if layers else 0
    order = {L: sorted(layers[L], key=str) for L in range(maxL + 1)}

    # crossing-minimization: median sweeps + transpose, keep the best order
    best = {L: list(order[L]) for L in order}
    best_c = _total_crossings(order, down, maxL)
    for it in range(o["ORDER_ITERS"]):
        if it % 2 == 0:
            for L in range(1, maxL + 1):
                _wmedian(order, L, L - 1, up)
        else:
            for L in range(maxL - 1, -1, -1):
                _wmedian(order, L, L + 1, down)
        _transpose(order, down, maxL)
        c = _total_crossings(order, down, maxL)
        if c < best_c:
            best_c = c
            best = {L: list(order[L]) for L in order}
    order = best

    # asymmetric per-node extents: a folded decisional reserves its fold's height on the
    # fold side (extents[id] = (up_extra, down_extra)) so the core spaces it to fit and the
    # fold can sit adjacent.
    ext = extents or {}
    ue = {i: vh[i] / 2 + ext.get(i, (0.0, 0.0))[0] for i in vlayer}
    de = {i: vh[i] / 2 + ext.get(i, (0.0, 0.0))[1] for i in vlayer}
    # y-coordinates: stack by order, then relax toward neighbour medians (straightening)
    y: dict = {}
    for L in range(maxL + 1):
        cy = 0.0
        for nid in order[L]:
            y[nid] = cy + ue[nid]
            cy = y[nid] + de[nid] + o["DY"]
    for it in range(o["RELAX_ITERS"]):
        down_sweep = (it % 2 == 0)           # align to predecessors, then to successors
        seq = range(1, maxL + 1) if down_sweep else range(maxL - 1, -1, -1)
        for L in seq:
            desired = {}
            for nid in order[L]:
                nb = up.get(nid, []) if down_sweep else down.get(nid, [])
                desired[nid] = _median([y[x] for x in nb]) if nb else y[nid]
            y.update(_place(order[L], desired, ue, de, o["DY"]))

    # error-port targets: drop to a lane below the happy path
    main_ys = [y[i] for i in ids if i not in err_targets]
    if err_targets and main_ys:
        base = max(main_ys) + o["ERR_GAP"]
        for k, i in enumerate(sorted(err_targets, key=lambda i: vlayer[i])):
            y[i] = base + k * o["DY"]

    # x by column: spaced by the edge gap (DX - NODE_W) so WIDE nodes (containers) get
    # room; for normal 48px nodes this is identical center-to-center spacing as before.
    col_w = {}
    for i in ids:
        col_w[vlayer[i]] = max(col_w.get(vlayer[i], o["NODE_W"]), sizes[i][0])
    gap = o["DX"] - o["NODE_W"]
    col_x, prev_x, prev_w = {}, None, None
    for L in range(maxL + 1):
        w = col_w.get(L, o["NODE_W"])
        col_x[L] = w / 2 if prev_x is None else prev_x + prev_w / 2 + gap + w / 2
        prev_x, prev_w = col_x[L], w
    positions = {i: {"x": float(col_x[vlayer[i]]), "y": float(y[i])} for i in ids}
    xs = [p["x"] for p in positions.values()]
    ys = [p["y"] for p in positions.values()]
    return {"positions": positions,
            "bbox": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}}


# ---------------------------------------------------------------------------
# partial / subset mode (re-tidy only some nodes; the rest stay put)
# ---------------------------------------------------------------------------

def _avoid_overlap(x, y, w, h, positions, by_id, o, exclude) -> float:
    def collides(cy):
        for oid, op in positions.items():
            if oid in exclude:
                continue
            ow, oh = by_id[oid]["w"], by_id[oid]["h"]
            if abs(op["x"] - x) < (w + ow) / 2 and abs(op["y"] - cy) < (h + oh) / 2 + 1:
                return True
        return False
    if not collides(y):
        return y
    for k in range(1, 80):
        for cand in (y + k * o["DY"], y - k * o["DY"]):
            if not collides(cand):
                return cand
    return y


def _frames(ns: list[dict], by_id: dict, positions: dict, o: dict) -> dict:
    children: dict = defaultdict(list)
    for n in ns:
        pid = n["parent_id"]
        if pid and pid in by_id:
            children[pid].append(n["id"])
    areas = {}
    for cid, kids in children.items():
        xs = [positions[k]["x"] for k in kids]
        ys = [positions[k]["y"] for k in kids]
        ws = [by_id[k]["w"] for k in kids]
        hs = [by_id[k]["h"] for k in kids]
        minx = min(x - w / 2 for x, w in zip(xs, ws))
        maxx = max(x + w / 2 for x, w in zip(xs, ws))
        miny = min(yy - hh / 2 for yy, hh in zip(ys, hs))
        maxy = max(yy + hh / 2 for yy, hh in zip(ys, hs))
        areas[cid] = {"x": minx - o["AREA_PAD"], "y": miny - o["AREA_PAD"],
                      "width": (maxx - minx) + 2 * o["AREA_PAD"],
                      "height": (maxy - miny) + 2 * o["AREA_PAD"]}
    return areas


def _partial(ns: list[dict], edges: list[dict], by_id: dict, subset: list[str], o: dict) -> dict:
    positions = {n["id"]: dict(n["pos"]) for n in ns}
    idset = set(by_id)
    sub = [nid for nid in subset if nid in idset]
    norm = [(e["source"], e["dest"]) for e in edges if int(e.get("type", 0) or 0) == 0]
    pred: dict = defaultdict(list)
    succ: dict = defaultdict(list)
    for s, d in norm:
        if s in idset and d in idset and s != d:
            succ[s].append(d)
            pred[d].append(s)
    for s in sorted(sub, key=lambda i: (positions[i]["x"], i)):
        xs_p = [positions[p]["x"] for p in pred[s]]
        xs_q = [positions[q]["x"] for q in succ[s]]
        if xs_p and xs_q:
            lo, hi = max(xs_p), min(xs_q)
            tx = (lo + hi) / 2 if hi - lo >= o["DX"] else lo + o["DX"]
        elif xs_p:
            tx = max(xs_p) + o["DX"]
        elif xs_q:
            tx = min(xs_q) - o["DX"]
        else:
            tx = positions[s]["x"]
        ys = [positions[n]["y"] for n in pred[s] + succ[s]]
        ty = _median(ys) if ys else positions[s]["y"]
        ty = _avoid_overlap(tx, ty, by_id[s]["w"], by_id[s]["h"], positions, by_id, o, exclude={s})
        positions[s] = {"x": tx, "y": ty}
    areas = _frames(ns, by_id, positions, o)
    xs = [p["x"] for p in positions.values()] or [0]
    ys = [p["y"] for p in positions.values()] or [0]
    return {"positions": positions, "areas": areas,
            "bbox": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}}


# ---------------------------------------------------------------------------
# branch-aware top-level layout (PROCESIO reading conventions)
# ---------------------------------------------------------------------------

def _reach(starts, adj: dict) -> set:
    seen = set(starts)
    stack = list(starts)
    while stack:
        for m in adj.get(stack.pop(), []):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


def _deadend_chains(ids, succ, indeg, outdeg):
    """Maximal private chains b1->..->terminal that hang off a branch node (out-degree
    >= 2) and end in a terminal (out-degree 0) without rejoining (every node in the
    chain has in-degree 1). These fold into a vertical tributary."""
    idset = set(ids)
    used = set()
    chains = []
    for b in ids:
        if outdeg.get(b, 0) < 2:
            continue
        for s in succ.get(b, []):
            if s in used or s not in idset:
                continue
            chain, cur, ok = [], s, True
            while True:
                if cur in used or indeg.get(cur, 0) != 1 or cur not in idset:
                    ok = False
                    break
                chain.append(cur)
                nxt = [x for x in succ.get(cur, []) if x in idset]
                if not nxt:
                    break                       # terminal reached
                if len(nxt) > 1:
                    ok = False
                    break
                cur = nxt[0]
            if ok and chain and outdeg.get(chain[-1], 0) == 0:
                used.update(chain)
                chains.append((b, chain))
    return chains


def _layout_main(nodes: list[dict], typed_edges: list[tuple[str, str, int]], o: dict) -> dict:
    ids = [n["id"] for n in nodes]
    if not ids:
        return {"positions": {}, "bbox": {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0}}
    by_id = {n["id"]: n for n in nodes}
    idset = set(ids)
    norm = [(s, d) for (s, d, t) in typed_edges if t == 0 and s in idset and d in idset and s != d]
    errs = [(s, d) for (s, d, t) in typed_edges if t == 1 and s in idset and d in idset and s != d]
    succ = defaultdict(list)
    pred = defaultdict(list)
    for s, d in norm:
        succ[s].append(d)
        pred[d].append(s)
    err_targets = {d for _s, d in errs}
    sources = [i for i in ids if not pred.get(i) and i not in err_targets]
    # error region = everything at-or-after an error-port target. The main-flow reach STOPS AT
    # error targets: a normal edge may point INTO one (e.g. a script-error gate's case edge into
    # the shared error Join) but is never traversed THROUGH it. Without the stop, one normal edge
    # into the error sink pulled the whole notify subtree into the main graph and shredded the
    # layout (Networky v2 2026-07-05: 14 edges into one Join laid out mid-canvas).
    main_reach = set(sources)
    _stack = [s for s in sources if s not in err_targets]
    while _stack:
        for m in succ.get(_stack.pop(), []):
            if m not in main_reach:
                main_reach.add(m)
                if m not in err_targets:      # reachable as an endpoint, not traversed through
                    _stack.append(m)
    error_region = _reach(err_targets, succ) - (main_reach - err_targets)
    main_ids = [i for i in ids if i not in error_region]
    mset = set(main_ids)
    msucc = defaultdict(list)
    mpred = defaultdict(list)
    for s, d in norm:
        if s in mset and d in mset:
            msucc[s].append(d)
            mpred[d].append(s)
    outdeg = {i: len(msucc.get(i, [])) for i in main_ids}
    indeg = {i: len(mpred.get(i, [])) for i in main_ids}
    chains = _deadend_chains(main_ids, msucc, indeg, outdeg)
    chains = [(b, ch) for b, ch in chains if len(ch) <= o["FOLD_MAX"]]
    # at most ONE folded chain per branch node: several dead-end chains folding onto the same
    # column stack on top of each other (Networky v2: the AI Router's 5-way fan collapsed into
    # two overlapping piles). The shortest chain folds; the rest stay in the normal layered flow.
    _best: dict = {}
    for b, ch in chains:
        cur = _best.get(b)
        if cur is None or (len(ch), ch) < (len(cur), cur):
            _best[b] = ch
    chains = sorted(_best.items())
    folded = {n for _b, ch in chains for n in ch}

    # core = the spine + rejoining branches (everything except folded + error region)
    core_ids = [i for i in main_ids if i not in folded]
    cset = set(core_ids)
    core_edges = [(s, d, 0) for s, d in norm if s in cset and d in cset]
    core_nodes = [by_id[i] for i in core_ids]

    # pass 1: rough core layout (no reservation) to choose each fold's direction by free space
    pos1 = _layout_layer(core_nodes, core_edges, o)["positions"]
    fold_dir, extents = {}, {}
    for b, ch in chains:
        if b not in pos1:
            continue
        bx, by = pos1[b]["x"], pos1[b]["y"]
        col = [pos1[i]["y"] for i in core_ids if i != b and abs(pos1[i]["x"] - bx) < o["DX"] / 2]
        above = [yv for yv in col if yv < by]
        below = [yv for yv in col if yv > by]
        gap_up = (by - max(above)) if above else float("inf")
        gap_dn = (min(below) - by) if below else float("inf")
        fh = o["DY_AFTER_DECISIONAL"] + (len(ch) - 1) * o["DY"] + o["NODE_H"] / 2
        if gap_up >= gap_dn:                 # more (or equal) room above -> fold up; tie -> up
            fold_dir[b], extents[b] = -1, (fh, 0.0)
        else:                                # more room below -> fold down
            fold_dir[b], extents[b] = 1, (0.0, fh)

    # pass 2: core layout reserving the fold height beside each folded decisional, so the
    # fold sits ADJACENT to its decisional (short edge) instead of at the column extreme
    pos = dict(_layout_layer(core_nodes, core_edges, o, extents=extents)["positions"])
    for b, ch in chains:
        if b not in pos:
            continue
        bx, by = pos[b]["x"], pos[b]["y"]
        step = fold_dir.get(b, -1)
        yy = by
        for idx, node in enumerate(ch):
            yy += step * (o["DY_AFTER_DECISIONAL"] if idx == 0 else o["DY"])
            pos[node] = {"x": bx, "y": yy}

    # error region -> a parallel lane BELOW everything. Each weakly-CONNECTED COMPONENT of the
    # region anchors under the MEDIAN x of ITS OWN entry sources (error-port sources AND normal
    # edges into the region, e.g. script-error gates). One shared anchor dragged independent
    # error rails toward each other and stretched entry edges across the canvas (Networky v2:
    # 3.5k-px edges into a shared error Join; still wrong after splitting the flow into two
    # rails, because both rails were laid out and anchored as one block).
    if error_region:
        main_maxY = max((p["y"] for p in pos.values()), default=0.0)
        # weakly-connected components over the region's own edges
        nbr = defaultdict(set)
        for s, dd in norm:
            if s in error_region and dd in error_region:
                nbr[s].add(dd)
                nbr[dd].add(s)
        unseen = set(error_region)
        comps = []
        while unseen:
            root = unseen.pop()
            comp = {root}
            stack = [root]
            while stack:
                for m in nbr.get(stack.pop(), ()):
                    if m in unseen:
                        unseen.discard(m)
                        comp.add(m)
                        stack.append(m)
            comps.append(comp)
        err_comps = comps
        for comp in comps:
            er_edges = [(s, dd, 0) for s, dd in norm if s in comp and dd in comp]
            erpos = _layout_layer([by_id[i] for i in comp], er_edges, o)["positions"]
            # rotate the rail VERTICAL (chain descends) so its internal edges are drops that
            # cannot cross the horizontal main flow or a decisional fan above it
            order = sorted(erpos, key=lambda i: (erpos[i]["x"], erpos[i]["y"]))
            for k, i in enumerate(order):
                erpos[i] = {"x": 0.0, "y": k * o["DY"]}
            feeders = [s for s, dd in errs if dd in comp and s in pos and s not in error_region]
            feeders += [s for s, dd in norm if dd in comp and s in pos and s not in error_region]
            if feeders:
                anchor_x = _median([pos[s]["x"] for s in feeders])
            else:
                anchor_x = min((p["x"] for p in pos.values()), default=0.0)
            shift_y = (main_maxY + o["ERR_GAP"])
            for i, p in erpos.items():
                pos[i] = {"x": anchor_x + p["x"], "y": p["y"] + shift_y}

    # loop closure: a back-edge (u -> v where u ends up RIGHT of v) is a retry/loop return.
    # Place the loop-tail chain in a lane below everything and align u under v, so the
    # return reads as a short vertical instead of a long diagonal across the canvas.
    back = sorted(e for e in _back_edges(ids, norm + errs) if e[0] in pos and e[1] in pos)
    if back:
        fpred: dict = defaultdict(list)        # full normal adjacency (incl. error region)
        fout: dict = defaultdict(int)
        for s, d in norm:
            fpred[d].append(s)
            fout[s] += 1
        lane_y = max(p["y"] for p in pos.values()) + o["DY"]
        for u, v in back:
            chain = [u]
            cur, branch = u, None
            while True:
                ps = fpred.get(cur, [])
                if len(ps) != 1:
                    break
                p = ps[0]
                if fout.get(p, 0) >= 2 or p in chain:
                    branch = p
                    break
                chain.append(p)
                cur = p
            chain.reverse()                       # [nearest-branch .. u]
            bx = pos[branch]["x"] if branch in pos else pos[chain[0]]["x"]
            vx = pos[v]["x"]
            n = len(chain)
            for i, node in enumerate(chain):
                tt = i / (n - 1) if n > 1 else 1.0
                pos[node] = {"x": bx + (vx - bx) * tt, "y": lane_y}

    # off-spine movable sub-regions (for the optional crossing-min pass to relocate as units)
    regions = ([set(c) for c in err_comps] if error_region else []) + [set(ch) for _b, ch in chains]

    xs = [p["x"] for p in pos.values()] or [0]
    ys = [p["y"] for p in pos.values()] or [0]
    return {"positions": pos, "regions": regions,
            "bbox": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}}


# ---------------------------------------------------------------------------
# public entry: full layout (with For-Each container recursion) or partial
# ---------------------------------------------------------------------------

def _spine_runs(positions: dict, nodes: list, typed: list, o: dict) -> list:
    """Detect maximal horizontal SPINE runs (>= CLUSTER_MIN), left to right. The spine follows
    the same-row successor, so a decisional with a dead-end side branch does NOT break the run."""
    DY = o["DY"]
    elig = {n["id"] for n in nodes
            if not n.get("parent_id") and n.get("kind") != "area" and n["id"] in positions}
    fsucc: dict = defaultdict(list)
    for s, d, t in typed:
        if t == 0 and s in positions and d in positions and s != d:
            fsucc[s].append(d)
    spine_next: dict = {}
    used: set = set()
    for a in elig:
        cands = [b for b in fsucc.get(a, [])
                 if b in elig and abs(positions[b]["y"] - positions[a]["y"]) < DY * 0.5
                 and positions[b]["x"] > positions[a]["x"] + 1]
        if cands:
            b = min(cands, key=lambda z: positions[z]["x"])
            spine_next[a] = b
            used.add(b)
    starts = [u for u in elig if u in spine_next and u not in used]
    no_clus = o.get("NO_CLUSTER_IDS") or set()   # branch-managed chains: the adapter's perpendicular
    indeg: dict = defaultdict(int)               # post-pass owns them, so folding them just wastes work
    for s, d, t in typed:
        if t == 0 and s in positions and d in positions and s != d:
            indeg[d] += 1
    runs: list = []
    claimed: set = set()
    for s in sorted(starts, key=lambda i: positions[i]["x"]):
        if s in claimed:
            continue
        run = [s]
        cur = s
        while cur in spine_next and spine_next[cur] not in claimed and spine_next[cur] not in run:
            cur = spine_next[cur]
            run.append(cur)
        claimed |= set(run)
        # split at MERGE nodes (indeg>1): where other flow arrives is a natural fold boundary --
        # The reference layout folds the private stretch BEFORE a Join and leaves the merge onward in-flow.
        seg: list = []
        segs: list = []
        for nid in run:
            if indeg.get(nid, 0) > 1 and seg:
                segs.append(seg)
                seg = []
            seg.append(nid)
        if seg:
            segs.append(seg)
        for sg in segs:
            if len(sg) >= o["CLUSTER_MIN"] and not (no_clus and set(sg) & no_clus):
                runs.append(sg)
    return runs


def _fold_run(positions: dict, run: list, nodes: list, typed: list, o: dict,
              mode: str = "shelves") -> dict | None:
    """Fold ONE spine run and return NEW positions (or None when `mode` doesn't apply).

    Two shapes, learned from the reference hand-arrangements:

    - "ufold" (mid-spine runs -- the exit continues into downstream flow): a vertical
      U-pocket hanging BELOW the flow line. Columns descend then ascend (alternating), and
      the final ascending column is bottom-anchored so the EXIT lands back ON the spine row
      -- downstream keeps its row and simply compacts LEFT (his ANAF fold: 7 nodes, 2
      columns, 785px reclaimed). Only for stub-free runs with a real downstream.
    - "shelves" (terminal tails): row-major boustrophedon shelves wrapping downward
      (approved on Start/Callback). Dead-end side stubs travel with their parent and hang
      DOWN into the gap reserved beneath each shelf.

    Rows below the run (within its x-band) are pushed down to make room; downstream of the
    exit is translated to follow it. Purely additive room -> the caller's 'no worse
    crossings/overlaps' guard decides whether to keep the fold."""
    positions = dict(positions)
    DX, DY = o["DX"], o["DY"]
    # reachability must follow ALL edge types: an error-port region is still downstream flow --
    # leaving it out of the translation set tears it from its anchors when everything else slides.
    fsucc: dict = defaultdict(list)
    for s, d, t in typed:
        if s in positions and d in positions and s != d:
            fsucc[s].append(d)
    rs = set(run)
    x0, y0 = positions[run[0]]["x"], positions[run[0]]["y"]
    exit_old = dict(positions[run[-1]])
    down, stack = set(), [run[-1]]
    while stack:
        for m in fsucc.get(stack.pop(), []):
            if m not in down and m not in rs:
                down.add(m)
                stack.append(m)
    attached: dict = {}
    for rn in run:
        sub: list = []
        st = [m for m in fsucc.get(rn, []) if m not in rs and m not in down]
        seen = set(st)
        while st:
            m = st.pop()
            sub.append(m)
            for k in fsucc.get(m, []):
                if k not in rs and k not in down and k not in seen:
                    seen.add(k)
                    st.append(k)
        if sub:
            attached[rn] = [(m, positions[m]["x"] - positions[rn]["x"],
                             positions[m]["y"] - positions[rn]["y"]) for m in sub]

    target: dict = {}
    if mode == "ufold":
        # mid-spine only: needs a downstream to keep on-row, and side stubs would collide
        # inside the tight pocket -- those runs fall through to shelves.
        if not down or attached:
            return None
        Dmax = max(2, o["CLUSTER_WRAP"])
        C = max(2, -(-len(run) // Dmax))
        if C % 2:                                   # even column count => last column ASCENDS,
            C += 1                                  # so the exit can land back on the spine row
        D = -(-len(run) // C)
        # the pocket must hang into EMPTY space (the reference ANAF fold does): shoving occupants
        # aside to make room tears shared clusters apart (seen on Start's Join cluster).
        px_lo, px_hi = x0 - DX * 0.5, x0 + (C - 1) * DX + DX * 0.5
        py_hi = y0 + (D - 1) * DY + DY * 0.5
        for nid, p in positions.items():
            if nid in rs or nid in down:
                continue
            if px_lo <= p["x"] <= px_hi and y0 + DY * 0.5 < p["y"] <= py_hi:
                return None
        cols = [run[k:k + D] for k in range(0, len(run), D)]
        for j, col in enumerate(cols):
            x = x0 + j * DX
            if j % 2 == 0:                          # descending column
                for r, nid in enumerate(col):
                    target[nid] = (x, y0 + r * DY)
            else:                                   # ascending column, bottom-anchored to end at row 0
                for r, nid in enumerate(col):
                    target[nid] = (x, y0 + (len(col) - 1 - r) * DY)
        # the downstream slide must land in FREE space: if the translated downstream would
        # collide with a parallel branch that does NOT move, de-overlap tears the collision
        # apart (seen on Start). The reference ANAF pocket works because everything downstream of
        # the run moves together -- nothing is left to collide with.
        tsx = target[run[-1]][0] - exit_old["x"]
        tsy = target[run[-1]][1] - exit_old["y"]
        stay = [p for nid, p in positions.items() if nid not in rs and nid not in down]
        for nid in down:
            nx2, ny2 = positions[nid]["x"] + tsx, positions[nid]["y"] + tsy
            if any(abs(q["x"] - nx2) < DX * 0.5 and abs(q["y"] - ny2) < DY * 0.5 for q in stay):
                return None
        block_h = 0.0                               # pocket verified empty -> nothing to push
        x_lo, x_hi = px_lo, px_hi
    else:
        W = max(2, o["CLUSTER_WRAP"])
        shelves = [run[i:i + W] for i in range(0, len(run), W)]
        yy = y0
        for si, shelf in enumerate(shelves):
            depth = 0.0
            for rn in shelf:
                for (_m, _dx, dy) in attached.get(rn, []):
                    depth = max(depth, abs(dy))     # branches all hang DOWN into the reserved gap
            # odd (right-to-left) shelves are RIGHT-ALIGNED: a short remainder sits under the
            # END of the previous shelf (short vertical drop), not carriage-returned to the
            # left (the reference ANAF fix: the terminal Stop goes below the last node, +480 right).
            seq = shelf if si % 2 == 0 else list(reversed(shelf))
            base = 0 if si % 2 == 0 else (W - len(shelf))
            for ci, rn in enumerate(seq):
                target[rn] = (x0 + (base + ci) * DX, yy)
            yy += DY + depth
        block_h = (yy - DY) - y0
        x_lo, x_hi = x0 - DX * 0.5, x0 + (W - 1) * DX + DX * 0.5

    # MAKE ROOM: push rows strictly below the run's row, within the fold's x-band, down by
    # the fold's added height. Uniform shift preserves relative order -> no new crossings.
    moved = rs | down | {m for lst in attached.values() for (m, _a, _b) in lst}
    if block_h > 0:
        for nid in list(positions):
            if nid in moved:
                continue
            px, py = positions[nid]["x"], positions[nid]["y"]
            if py > y0 + DY * 0.5 and x_lo <= px <= x_hi:
                positions[nid] = {"x": px, "y": py + block_h}
    for rn in run:
        nx, ny = target[rn]
        for (m, dx, dy) in attached.get(rn, []):
            positions[m] = {"x": nx + dx, "y": ny + abs(dy)}   # hang the branch downward
        positions[rn] = {"x": nx, "y": ny}
    sx = positions[run[-1]]["x"] - exit_old["x"]
    sy = positions[run[-1]]["y"] - exit_old["y"]
    for nid in down:
        positions[nid] = {"x": positions[nid]["x"] + sx, "y": positions[nid]["y"] + sy}
    return positions


def _cluster_chains(positions: dict, nodes: list, typed: list, o: dict) -> dict:
    """OPTIONAL (off by default): fold every long horizontal spine run into compact shelves.
    Non-incremental (folds all runs); layout() drives an incremental, guard-checked variant for
    live use so that a fold which would add crossings is skipped instead of poisoning the rest."""
    positions = dict(positions)
    for run in _spine_runs(positions, nodes, typed, o):
        positions = _fold_run(positions, run, nodes, typed, o)
    return positions


def _seg_int(a: dict, b: dict, c: dict, d: dict) -> bool:
    """Do segments a-b and c-d properly intersect?"""
    def orient(p, q, r):
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _loop_curl(rset: set, typed: list, P: dict, o: dict) -> dict | None:
    """If a region is a retry/error LOOP -- it has an ENTRY edge from the main flow AND a
    RETURN edge back to the main flow (e.g. an error handler that retries by looping to a
    Join) -- lay it as two vertical columns aligned to its anchors: the loop tail rises above
    its RETURN target, the decisional + the fail path rise above the ENTRY source. Both
    boundary edges become vertical, so they don't cross and the decisional reads in-flow.
    Returns {id: {x, y}} for every region node, or None when the pattern doesn't apply."""
    from collections import deque
    DY = o["DY"]
    rsucc: dict = defaultdict(list)
    entry = ret = None
    for (s, d, tp) in typed:
        if s not in P or d not in P:
            continue
        if s in rset and d in rset and tp == 0:
            rsucc[s].append(d)
        elif s not in rset and d in rset:
            if entry is None or tp == 1:      # prefer the error edge as the entry
                entry = (s, d)
        elif s in rset and d not in rset and ret is None:
            ret = (s, d)
    if not entry or not ret:
        return None
    entry_node, src_main = entry[1], entry[0]
    exit_node, ret_main = ret[0], ret[1]
    if entry_node not in rset or exit_node not in rset:
        return None
    ax, ay = P[src_main]["x"], P[src_main]["y"]
    bx, by = P[ret_main]["x"], P[ret_main]["y"]
    if abs(ax - bx) < o["DX"] / 2:            # need two distinct columns
        return None
    par = {entry_node: None}
    q = deque([entry_node])
    while q:
        u = q.popleft()
        for v in rsucc.get(u, []):
            if v not in par:
                par[v] = u
                q.append(v)
    if exit_node not in par:
        return None
    path = []
    c = exit_node
    while c is not None:
        path.append(c)
        c = par[c]
    path.reverse()                            # [entry_node .. exit_node]
    loop_tail = [n for n in path if n != entry_node]
    fail = [n for n in rset if n not in loop_tail and n != entry_node]
    fail_order: list = []
    c = entry_node
    fpool = set(fail)
    while True:
        nxt = [v for v in rsucc.get(c, []) if v in fpool and v not in fail_order]
        if not nxt:
            break
        fail_order.append(nxt[0])
        c = nxt[0]
    for n in fail:                            # any unreached fail nodes
        if n not in fail_order:
            fail_order.append(n)
    out = {entry_node: {"x": ax, "y": ay - 2 * DY}}
    for k, n in enumerate(fail_order):        # fail path stacked above the decisional
        out[n] = {"x": ax, "y": ay - (3 + k) * DY}
    for k, n in enumerate(reversed(loop_tail)):   # loop tail rises above its return target
        out[n] = {"x": bx, "y": by - (1 + k) * DY}
    return out if set(out) == rset else None


def _minimize_crossings(positions: dict, nodes: list, typed: list, o: dict, movable: set,
                        regions: list | None = None) -> dict:
    """OPTIONAL (off by default): best-effort edge-crossing reduction, in two phases.

    PHASE A -- region re-placement: each off-spine sub-region (the error region, dead-end
    folds) is RE-LAID-OUT compactly (a chain collapses to one row) and offered up FLUSH just
    above or just below the main body; whichever placement has the fewest crossings wins, and
    the region is only replaced if that is STRICTLY better than leaving it where the base put
    it. This is what lets an error/retry loop that the base drops into a low lane (where its
    connectors cross a long skip-edge) move to a tidy lane on the crossing-free side, close to
    the flow -- matching how a human re-arranges it. Compact + flush, so no far teleport and no
    empty gap. It never overlaps other nodes/frames.

    PHASE B -- bounded, distance-penalized per-node local search: each movable top-level node
    is nudged within a small grid neighbourhood, keeping the move that most lowers
    `crossings + PENALTY * grid-steps-from-start`. Distance being a REAL cost keeps every move
    LOCAL (e.g. sliding a skip-edge endpoint one row), never a teleport.

    Counts ALL drawn edges (normal + error). Strictly-better-only + monotone bounded score =>
    never worse than the input, and it terminates. Containers/children stay fixed. Not zero-
    guaranteed -- structural crossings a compact/local move can't remove (a container-exit edge)
    are left as-is by design."""
    by_id = {n["id"]: n for n in nodes}
    edges = [(s, d) for s, d, t in typed
             if t in (0, 1) and s in positions and d in positions and s != d]
    norm = [(s, d, t) for (s, d, t) in typed if t == 0]
    inc: dict = defaultdict(list)
    for i, (s, d) in enumerate(edges):
        inc[s].append(i)
        inc[d].append(i)
    P = positions

    def rp(nid):
        # RENDER point of a node for crossing tests: the designer attaches edges to an area
        # (For-Each) frame at its TOP-LEFT (the frame's stored position), not the node centre
        # that `positions` holds. Using the centre miscounts every container-boundary edge by
        # (w/2, h/2). All non-area nodes render where they sit.
        p = P[nid]
        if by_id.get(nid, {}).get("kind") == "area":
            return {"x": p["x"] - by_id[nid]["w"] / 2, "y": p["y"] - by_id[nid]["h"] / 2}
        return p

    def box_hit(nid, x, y, oid):
        return (abs(P[oid]["x"] - x) < (by_id[nid]["w"] + by_id[oid]["w"]) / 2
                and abs(P[oid]["y"] - y) < (by_id[nid]["h"] + by_id[oid]["h"]) / 2)

    def overlaps(nid, x, y):
        return any(oid != nid and box_hit(nid, x, y, oid) for oid in P)

    def total_cross():
        n = 0
        for i in range(len(edges)):
            s, d = edges[i]
            a, b = rp(s), rp(d)
            for j in range(i + 1, len(edges)):
                s2, d2 = edges[j]
                if s2 in (s, d) or d2 in (s, d):
                    continue
                if _seg_int(a, b, rp(s2), rp(d2)):
                    n += 1
        return n

    # PHASE A: re-lay each off-spine region compactly, place it FLUSH above/below on the side
    # that cuts the most crossings; replace only if strictly better (else leave base untouched).
    for region in (regions or []):
        region = [r for r in region if r in P]
        if not region:
            continue
        rset = set(region)
        others = [i for i in P if i not in rset]
        if not others:
            continue
        base_c = total_cross()
        snap = {i: dict(P[i]) for i in region}
        rnodes = [by_id[i] for i in region if i in by_id]
        redges = [(s, d, tp) for (s, d, tp) in norm if s in rset and d in rset]
        try:
            rel = _layout_layer(rnodes, redges, o)["positions"]
        except Exception:  # noqa: BLE001
            rel = {}
        rel = {i: rel[i] for i in region if i in rel}
        if len(rel) != len(region):
            continue
        rminx = min(p["x"] for p in rel.values())
        rminy = min(p["y"] for p in rel.values())
        rh = max(p["y"] for p in rel.values()) - rminy
        cur_minx = min(snap[i]["x"] for i in region)
        mtop = min(P[i]["y"] for i in others)
        mbot = max(P[i]["y"] for i in others)

        def place(yoff):
            for i in region:
                P[i] = {"x": cur_minx + (rel[i]["x"] - rminx),
                        "y": yoff + (rel[i]["y"] - rminy)}

        def region_clear():
            return not any(box_hit(i, P[i]["x"], P[i]["y"], oid)
                           for i in region for oid in others)

        # candidate placements: compact FLUSH above/below, plus a LOOP-CURL for retry loops.
        candidates = []
        for yoff in (mtop - o["DY"] - rh, mbot + o["DY"]):
            candidates.append({i: {"x": cur_minx + (rel[i]["x"] - rminx),
                                   "y": yoff + (rel[i]["y"] - rminy)} for i in region})
        curl = _loop_curl(rset, typed, P, o)
        if curl:
            candidates.append(curl)

        best_c, best = base_c, snap
        for cand in candidates:
            for i in region:
                P[i] = cand[i]
            c = total_cross() if region_clear() else float("inf")
            if c < best_c - 1e-9:
                best_c, best = c, {i: dict(P[i]) for i in region}
        for i in region:
            P[i] = best[i]

    # PHASE B: bounded, distance-penalized per-node local search (fine-tune).
    PEN = o.get("MINCROSS_MOVE_PENALTY", 0.5)
    R = o.get("MINCROSS_RANGE", 6)
    DX, DY = o["DX"], o["DY"]
    region_nodes = set().union(*[set(r) for r in (regions or [])]) if regions else set()
    startp = {nid: dict(P[nid]) for nid in movable if nid in P}
    # Phase A owns each region's compact internal layout; Phase B must NOT drag a region node
    # (e.g. a decisional) out of place chasing a crossing -- it only fine-tunes free nodes.
    order = sorted(m for m in movable if m in P and inc.get(m) and m not in region_nodes)

    def disp():
        # QUADRATIC per-node displacement: a 1-step nudge is cheap (fine-tuning, this phase's
        # job) but a multi-row flight is prohibitive -- Phase B must never fling a node far
        # from its neighbours to shave one crossing (rule: locality beats a single crossing;
        # seen on 0GetInfo where found? was launched 4 rows above its own row).
        return sum((abs(P[m]["x"] - startp[m]["x"]) / DX + abs(P[m]["y"] - startp[m]["y"]) / DY) ** 2
                   for m in startp)

    LEN = o.get("MINCROSS_LEN_PENALTY", 0.15)

    def elen():
        # total edge length (render points, in grid units) -- a READABILITY term: prefers the
        # crossing fix that keeps edges SHORT, so a node is never flung downstream of its own
        # successors (reversing/lengthening its edges) just to shave a crossing.
        return sum((abs(rp(s)["x"] - rp(d)["x"]) + abs(rp(s)["y"] - rp(d)["y"])) / DX
                   for s, d in edges)

    # FLOW MONOTONICITY: a crossing fix must never point an edge BACKWARD -- a node stays
    # right of its normal-edge predecessors and left of its successors (back/loop edges
    # exempt). Rule: readability of the left-to-right flow beats any crossing saved.
    mono_edges = [(s, d) for s, d in edges if s in P and d in P]
    mono_back = _back_edges(list(P), mono_edges)
    mono_pred: dict = defaultdict(list)
    mono_succ: dict = defaultdict(list)
    for s, d in mono_edges:
        if (s, d) in mono_back:
            continue
        mono_succ[s].append(d)
        mono_pred[d].append(s)

    def mono_ok(nid, x):
        return (all(x >= P[p]["x"] - DX * 0.25 for p in mono_pred.get(nid, []))
                and all(x <= P[s2]["x"] + DX * 0.25 for s2 in mono_succ.get(nid, [])))

    for _ in range(o.get("MINCROSS_ITERS", 6)):
        improved = False
        for nid in order:
            cur = dict(P[nid])
            best_score = total_cross() + PEN * disp() + (LEN * elen() if LEN else 0.0)
            best_p = cur
            for kx in range(-R, R + 1):
                for ky in range(-R, R + 1):
                    if kx == 0 and ky == 0:
                        continue
                    x, y = cur["x"] + kx * DX, cur["y"] + ky * DY
                    if overlaps(nid, x, y) or not mono_ok(nid, x):
                        continue
                    P[nid] = {"x": x, "y": y}
                    sc = total_cross() + PEN * disp() + (LEN * elen() if LEN else 0.0)
                    if sc < best_score - 1e-9:
                        best_score, best_p = sc, {"x": x, "y": y}
            P[nid] = best_p
            if best_p != cur:
                improved = True
        if not improved:
            break
    return positions


def _count_crossings(positions: dict, edges: list, by_id: dict) -> int:
    """Render-faithful crossing count: area (For-Each) nodes attach edges at their frame
    top-left (centre - w/2, h/2), everything else at its point. `edges` = (src, dst) pairs."""
    def rp(nid):
        p = positions[nid]
        n = by_id.get(nid)
        if n and n.get("kind") == "area":
            return {"x": p["x"] - n["w"] / 2, "y": p["y"] - n["h"] / 2}
        return p
    es = [(s, d) for (s, d) in edges if s in positions and d in positions and s != d]
    n = 0
    for i in range(len(es)):
        s, d = es[i]
        a, b = rp(s), rp(d)
        for j in range(i + 1, len(es)):
            s2, d2 = es[j]
            if s2 in (s, d) or d2 in (s, d):
                continue
            if _seg_int(a, b, rp(s2), rp(d2)):
                n += 1
    return n


def _count_overlaps(positions: dict, by_id: dict, ids) -> int:
    """Number of overlapping node pairs among `ids` (box test on node w/h)."""
    ii = [i for i in ids if i in positions]
    n = 0
    for a in range(len(ii)):
        for b in range(a + 1, len(ii)):
            i, j = ii[a], ii[b]
            if (abs(positions[i]["x"] - positions[j]["x"]) < (by_id[i]["w"] + by_id[j]["w"]) / 2
                    and abs(positions[i]["y"] - positions[j]["y"]) < (by_id[i]["h"] + by_id[j]["h"]) / 2):
                n += 1
    return n


def _resolve_overlaps(positions: dict, by_id: dict, movable: set, o: dict) -> dict:
    """Deterministic final safety net: if a movable top-level node overlaps another node or a
    container frame, nudge it DOWN a row until clear. A NO-OP when nothing overlaps, so clean
    layouts stay byte-identical. Guarantees the 'no node overlaps' invariant that independent
    off-spine lane placements (error region + dead-end chains dropped into the same lane) can
    otherwise violate. Grid-aligned (pushes by DY), so alignment is preserved."""
    DY = o["DY"]
    order = sorted((m for m in movable if m in positions),
                   key=lambda i: (positions[i]["y"], positions[i]["x"], str(i)))

    def hit(nid, oid):
        p, q = positions[nid], positions[oid]
        return (abs(p["x"] - q["x"]) < (by_id[nid]["w"] + by_id[oid]["w"]) / 2
                and abs(p["y"] - q["y"]) < (by_id[nid]["h"] + by_id[oid]["h"]) / 2)

    for _ in range(len(order) + 5):
        moved = False
        for nid in order:
            clash = [oid for oid in positions if oid != nid and hit(nid, oid)]
            if clash:
                drop = max(positions[oid]["y"] for oid in clash) + DY
                positions[nid] = {"x": positions[nid]["x"], "y": drop}
                moved = True
        if not moved:
            break
    return positions


def layout(nodes: list[dict], edges: list[dict], opts: dict | None = None,
           subset: list[str] | None = None) -> dict:
    """Lay out a node/edge graph. Returns {positions:{id:{x,y}}, areas:{id:{x,y,width,
    height}}, bbox}. nodes: {id, width?, height?, parent_id?, kind?, position?}. edges:
    {source, dest, type?} (type 1 = error edge -> target drops to a low lane).

    `subset` -> reposition ONLY those node ids among their fixed neighbours (re-tidy mode);
    every other node keeps its current position."""
    o = {**DEFAULTS, **(opts or {})}
    ns = [_node(n) for n in nodes]
    by_id = {n["id"]: n for n in ns}
    if subset is not None:
        return _partial(ns, edges, by_id, subset, o)
    typed = [(e["source"], e["dest"], int(e.get("type", 0) or 0)) for e in edges]

    children: dict = defaultdict(list)
    top: list[dict] = []
    for n in ns:
        pid = n["parent_id"]
        (children[pid].append(n) if pid and pid in by_id else top.append(n))

    child_rel: dict = {}
    for cid, kids in children.items():
        kid_ids = {k["id"] for k in kids}
        sub = [(s, d, t) for (s, d, t) in typed if s in kid_ids and d in kid_ids]
        res = _layout_layer(kids, sub, o)
        b = res["bbox"]
        # reserve room at the LEFT for the implicit ForEach-Start (+ one DX) and a top pad;
        # min right/bottom pad. Evidence-based (corpus of 39 For-Each + the reference arrangement).
        fe_left = o["DX"] + o["FE_START_PAD"]
        offx, offy = fe_left - b["minX"], o["FE_TOP"] - b["minY"]
        for k in kids:
            p = res["positions"][k["id"]]
            child_rel[k["id"]] = {"x": p["x"] + offx, "y": p["y"] + offy}
        by_id[cid]["w"] = (b["maxX"] - b["minX"]) + fe_left + o["FE_RIGHT_PAD"]
        by_id[cid]["h"] = (b["maxY"] - b["minY"]) + o["FE_TOP"] + o["FE_BOTTOM_PAD"]

    top_ids = {n["id"] for n in top}
    top_edges = [(s, d, t) for (s, d, t) in typed if s in top_ids and d in top_ids]
    res = _layout_main(top, top_edges, o)
    top0 = dict(res["positions"])
    regions = res.get("regions", [])
    all_pairs = [(s, d) for (s, d, _t) in typed]

    def _place_children(top_pos):
        """Place container children on a top-level placement; return (full_pos, areas)."""
        pos = dict(top_pos)
        ars: dict = {}
        for cid, kids in children.items():
            cpos = pos.get(cid, {"x": 0.0, "y": 0.0})
            fx = cpos["x"] - by_id[cid]["w"] / 2
            fy = cpos["y"] - by_id[cid]["h"] / 2
            for k in kids:
                rel = child_rel[k["id"]]
                pos[k["id"]] = {"x": fx + rel["x"], "y": fy + rel["y"]}
            ars[cid] = {"x": fx, "y": fy, "width": by_id[cid]["w"], "height": by_id[cid]["h"]}
        return pos, ars

    def _mincross_top(top_pos):
        """Min-crossings (needs children placed for faithful crossing counts) -> TOP-LEVEL
        positions only. Min-crossings never moves children or containers, so the top-level slice
        is enough to re-place children afterward."""
        full, _ars = _place_children(top_pos)
        if o.get("MINIMIZE_CROSSINGS"):
            mv = {n["id"] for n in ns if not n["parent_id"] and n["kind"] != "area" and n["id"] in full}
            full = _minimize_crossings(full, ns, typed, o, mv, regions)
        return {n["id"]: full[n["id"]] for n in top if n["id"] in full}

    def _deoverlap(pos):
        dv = {n["id"] for n in ns if not n["parent_id"] and n["kind"] != "area" and n["id"] in pos}
        return _resolve_overlaps(pos, by_id, dv, o)

    def _final_score(pos):
        return (_count_overlaps(pos, by_id, list(pos)), _count_crossings(pos, all_pairs, by_id))

    # Optional passes IN ORDER: base layout -> MINIMIZE_CROSSINGS -> CLUSTERING (LAST) -> de-overlap.
    # (Cycle-aware collapse wraps this whole call from the adapter, so it runs first of all.)
    top_mc = _mincross_top(top0)
    positions, areas = _place_children(top_mc)
    positions = _deoverlap(positions)
    if o.get("CLUSTER"):
        # Clustering is the FINAL transformation, applied to the MIN-CROSSINGS result. Fold the
        # spine runs ONE AT A TIME, keeping each fold only if the full-layout (overlaps, crossings)
        # is no worse than before. Incremental (not all-at-once) so that a run whose fold would add
        # a crossing is skipped instead of poisoning the runs that fold cleanly.
        def _max_edge(pos):
            return max((abs(pos[s]["x"] - pos[d]["x"]) + abs(pos[s]["y"] - pos[d]["y"])
                        for s, d in all_pairs if s in pos and d in pos), default=0.0)

        cur_top = dict(top_mc)
        best_score = _final_score(positions)
        # edge limit anchored to the BASE (pre-fold) max edge -- NOT ratcheting per kept fold,
        # or each fold inflates the limit for the next one and a late fold can tear geometry.
        # Slack covers legit growth: a serpentine's wrap connector lengthens one edge
        # (Callback 180->340), a fold beside a tall region reroutes one edge (Start ~1260).
        edge_lim = _max_edge(positions) * 2.0 + 400
        for run in _spine_runs(cur_top, top, top_edges, o):
            for mode in ("ufold", "shelves"):     # U-pocket for mid-spine runs, shelves for tails
                trial_top = _fold_run(cur_top, run, top, top_edges, o, mode=mode)
                if trial_top is None:
                    continue
                tpos, tars = _place_children(trial_top)
                tpos = _deoverlap(tpos)
                if _final_score(tpos) <= best_score and _max_edge(tpos) <= edge_lim:
                    cur_top, positions, areas = trial_top, tpos, tars
                    best_score = _final_score(tpos)
                    break

    if positions:
        minx = min(p["x"] for p in positions.values())
        miny = min(p["y"] for p in positions.values())
        dx, dy = o["MARGIN"] - minx, o["MARGIN"] - miny
        for p in positions.values():
            p["x"] += dx
            p["y"] += dy
        for a in areas.values():
            a["x"] += dx
            a["y"] += dy
    xs = [p["x"] for p in positions.values()] or [0]
    ys = [p["y"] for p in positions.values()] or [0]
    return {"positions": positions, "areas": areas,
            "bbox": {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}}



def designer_writes(positions: dict, areas: dict, parent_of: dict) -> dict:
    """Map engine output to designer node values honoring the PROCESIO container
    convention: an  node's position is its frame TOP-LEFT (plus areaSize); a
    container child's position is RELATIVE to its parent area frame; everything else is
    absolute.  maps child_id -> parent area id. Returns
    {id: {"pos": {x, y}, "areaSize": {...} | None}}."""
    out = {}
    for nid in set(positions) | set(areas):
        if nid in areas:
            fr = areas[nid]
            out[nid] = {"pos": {"x": round(fr["x"], 2), "y": round(fr["y"], 2)},
                        "areaSize": {"width": round(fr["width"], 2),
                                     "height": round(fr["height"], 2), "x": 0, "y": 0}}
        elif parent_of.get(nid) in areas and nid in positions:
            fr = areas[parent_of[nid]]
            p = positions[nid]
            out[nid] = {"pos": {"x": round(p["x"] - fr["x"], 2),
                                "y": round(p["y"] - fr["y"], 2)}, "areaSize": None}
        elif nid in positions:
            p = positions[nid]
            out[nid] = {"pos": {"x": round(p["x"], 2), "y": round(p["y"], 2)}, "areaSize": None}
    return out
