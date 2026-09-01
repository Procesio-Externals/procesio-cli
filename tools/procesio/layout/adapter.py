"""Bridge the layout engine to the `.procesio` export / live flow DTO.

Reads a flow with the flow graph reader, runs the pure engine, and writes the new
positions back into each action's `CustomData.position` (and a For-Each area's
`areaSize`), resetting `CanvasData`. Case-insensitive for read AND write (PascalCase
exports / camelCase live). Returns a NEW object — never mutates the input.
"""
from __future__ import annotations

import copy

from tools.procesio.flowmodel import read_bundle, read_flow
from tools.procesio.layout import cycles, dispatch, engine, report


def _key(d: dict, *names: str):
    """The actual key present in `d` matching any of `names` (case-insensitive)."""
    low = {str(k).lower(): k for k in d}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def _get(d, *names, default=None):
    k = _key(d, *names) if isinstance(d, dict) else None
    return d[k] if k else default


def _flows(obj: dict):
    k = _key(obj, "Flows")
    return (obj[k], k) if k else (None, None)


def _round(p: dict) -> dict:
    return {"x": round(float(p["x"]), 2), "y": round(float(p["y"]), 2)}


def _layout_score(bundle: dict, flow_id: str | None) -> float:
    """Lower = more readable. Hard issues dominate, then crossings, then long edges + overall
    size. Uses the engine-agnostic readability report, so both engines are judged identically."""
    rep = report.build_report(bundle, flow_id)
    m = rep["metrics"]
    return (rep["hard_issue_count"] * 10000.0 + m["crossings"] * 100.0
            + m["max_edge_px"] / 50.0 + (m["width"] + m["height"]) / 500.0)


def _best_of_engines(obj: dict, flow_id: str | None = None,
                     only: list[str] | None = None) -> dict:
    """LAYOUT_ENGINE=auto: lay the flow out with BOTH engines and return whichever the
    readability report scores better. Legacy runs with its opt-in cluster + min-crossings
    layers; ELK uses its own built-in clustering. Neither engine is modified — this only
    picks between their OUTPUTS, so 'what works' (e.g. the legacy retry loop-curl) is never
    lost: it just wins the score where it's better. Falls back to legacy if ELK errors or
    for `only`/subset mode (ELK has no partial layout)."""
    import os
    saved = os.environ.get("LAYOUT_ENGINE")
    try:
        os.environ["LAYOUT_ENGINE"] = dispatch.LEGACY
        legacy = layout_flow(obj, flow_id=flow_id, only=only,
                             cluster=True, minimize_crossings=True)
        elk = None
        if only is None:
            os.environ["LAYOUT_ENGINE"] = dispatch.ELK
            try:
                elk = layout_flow(obj, flow_id=flow_id)
            except Exception:  # noqa: BLE001
                elk = None
    finally:
        if saved is None:
            os.environ.pop("LAYOUT_ENGINE", None)
        else:
            os.environ["LAYOUT_ENGINE"] = saved
    if elk is None:
        return legacy
    if _layout_score(elk["bundle"], elk["flow_id"]) < _layout_score(legacy["bundle"], legacy["flow_id"]):
        return elk
    return legacy


def _apply_fan_lanes(positions: dict, fg) -> dict:
    """The reference FAN pattern (hand-arranged entry spine): when a decisional's parallel alternative
    branches all reconnect at the SAME merge, stack each branch as a flat LANE parallel to
    the spine axis -- lanes at +/-GAP around the split->merge row, bodies spread EVENLY
    between split.x and merge.x (a 1-node branch sits at the midpoint), keeping the side
    the engine chose for each branch. Dead-end stubs are left alone here; the branch
    conventions pass re-places them outward off the new lane bodies afterwards.

    The base layered engine has no concept of sibling branches between one split and one
    merge, so it gives each branch a semi-arbitrary diagonal. This pass is applied by
    layout_flow ONLY when the final layout is strictly better (overlaps, crossings,
    maxedge) than without it -- ties keep the existing output, so approved layouts can't
    churn."""
    from collections import defaultdict
    P = positions
    kind = {n.id: n.shape for n in fg.nodes}
    parent = {n.id: n.parent_id for n in fg.nodes}
    nsucc: dict = defaultdict(list)
    pred: dict = defaultdict(list)
    for e in fg.edges:
        if e.source in P and e.dest in P:
            if getattr(e, "type", 0) == 0:
                nsucc[e.source].append(e.dest)
            pred[e.dest].append(e.source)
    GAP = 180.0

    def deadend_private(start, src):
        """True if `start` heads a private chain that terminates (a stub -- not a branch)."""
        if len(pred.get(start, [])) != 1:
            return False
        seen, cur = {start, src}, start
        while True:
            nx = nsucc.get(cur, [])
            if not nx:
                return True
            if len(nx) != 1:
                return False
            nxt = nx[0]
            if nxt in seen or len(pred.get(nxt, [])) != 1:
                return False
            seen.add(nxt)
            cur = nxt

    for s in sorted(P):
        if kind.get(s) != "diamond" or parent.get(s):
            continue
        branches: list = []
        merge = None
        ok = True
        for t in dict.fromkeys(nsucc.get(s, [])):
            if len(pred.get(t, [])) > 1:            # direct edge to the merge (e.g. default->Join)
                if merge is None:
                    merge = t
                elif merge != t:
                    ok = False
                continue
            if deadend_private(t, s):               # stub off the split -- not a fan branch
                continue
            body, cur, guard = [], t, 0
            while ok and guard < 64:
                guard += 1
                if parent.get(cur) or kind.get(cur) == "area":
                    ok = False
                    break
                body.append(cur)
                cont = [x for x in nsucc.get(cur, []) if not deadend_private(x, cur)]
                if len(cont) != 1:
                    ok = False
                    break
                nxt = cont[0]
                if len(pred.get(nxt, [])) > 1:      # merge reached
                    if merge is None:
                        merge = nxt
                    elif merge != nxt:
                        ok = False
                    break
                cur = nxt
            else:
                ok = False
            if not ok:
                break
            branches.append(body)
        if not ok or len(branches) < 2 or merge is None or merge not in P or parent.get(merge):
            continue
        sx, mx = P[s]["x"], P[merge]["x"]
        if mx - sx < 2 * GAP:                       # merge must sit meaningfully to the right
            continue
        spine_y = (P[s]["y"] + P[merge]["y"]) / 2.0
        # balanced lanes STRADDLING the spine (the reference fan: ceil(n/2) above, rest below),
        # preserving the engine's vertical order of the branches -- his 0GetInfo golden:
        # 3 branches -> lanes -2, -1, +1.
        infos = sorted([(sorted(P[b]["y"] for b in body)[len(body) // 2], body)
                        for body in branches], key=lambda bi: bi[0])
        n_above = (len(infos) + 1) // 2
        lanes = [(-(n_above - i), body) for i, (_m, body) in enumerate(infos[:n_above])]
        lanes += [(+(i + 1), body) for i, (_m, body) in enumerate(infos[n_above:])]
        def _stub_chain(start, src):
            out, cur, seen = [start], start, {start, src}
            while True:
                nx = nsucc.get(cur, [])
                if len(nx) != 1 or nx[0] in seen:
                    return out
                out.append(nx[0])
                seen.add(nx[0])
                cur = nx[0]

        for lane, body in lanes:
            y = spine_y + lane * GAP
            step = (mx - sx) / (len(body) + 1)
            for i, b in enumerate(body):
                nx_, ny_ = sx + (i + 1) * step, y
                dx_, dy_ = nx_ - P[b]["x"], ny_ - P[b]["y"]
                # drag the node's dead-end stubs along -- the branch-conventions pass will
                # re-place them outward, but they must not be STRANDED at the old location
                # (a stranded stub can end up under its own moved parent).
                for t2 in nsucc.get(b, []):
                    if t2 not in body and deadend_private(t2, b):
                        for m2 in _stub_chain(t2, b):
                            P[m2] = {"x": P[m2]["x"] + dx_, "y": P[m2]["y"] + dy_}
                P[b] = {"x": nx_, "y": ny_}
    return P


def _layout_quality(positions: dict, fg) -> tuple:
    """(overlaps, crossings, maxedge) on straight segments -- the strictly-better gate for
    optional post-passes (fan lanes): ties keep the existing output so approved layouts
    can't churn."""
    P = positions
    ids = [i for i in P]
    ov = 0
    for i in range(len(ids)):
        a = P[ids[i]]
        for j in range(i + 1, len(ids)):
            b = P[ids[j]]
            # TRUE intersection only (nodes are 48px): the reference layout deliberately tucks a stub ~50px
            # from a neighbouring lane -- a near-touch must not veto a variant that saves a
            # crossing. (Placement decisions still use the looser 56px `occupied`.)
            if abs(a["x"] - b["x"]) < 48 and abs(a["y"] - b["y"]) < 48:
                ov += 1
    segs = [(P[e.source], P[e.dest]) for e in fg.edges if e.source in P and e.dest in P]

    def orient(p, q, r):
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])
    cross = 0
    for i in range(len(segs)):
        a, b = segs[i]
        for j in range(i + 1, len(segs)):
            c, d = segs[j]
            pts = {(a["x"], a["y"]), (b["x"], b["y"]), (c["x"], c["y"]), (d["x"], d["y"])}
            if len(pts) < 4:
                continue
            if (orient(a, b, c) > 0) != (orient(a, b, d) > 0) and                (orient(c, d, a) > 0) != (orient(c, d, b) > 0):
                cross += 1
    med = max((abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]) for a, b in segs), default=0.0)
    return (ov, cross, round(med))


def _branch_managed_nodes(fg) -> set:
    """Node ids whose placement _apply_branch_conventions owns: the private dead-end chains of
    decisional DEFAULT / conditional branches and error-port branches (mirrors that pass's own
    selection). Clustering must not fold these -- the perpendicular post-pass would re-flatten
    them, wasting the fold and leaving make-room artifacts. default->Join (in-flow) is NOT
    managed, so it stays foldable as part of the spine."""
    from collections import defaultdict
    kind = {n.id: n.shape for n in fg.nodes}
    parent = {n.id: n.parent_id for n in fg.nodes}
    succ: dict = defaultdict(list)
    pred: dict = defaultdict(list)
    for e in fg.edges:
        succ[e.source].append(e.dest)
        pred[e.dest].append(e.source)

    def private_chain(start, src):
        chain, cur, seen = [start], start, {start, src}
        while True:
            nx = succ.get(cur, [])
            if len(nx) != 1:
                break
            nxt = nx[0]
            if nxt in seen or len(pred.get(nxt, [])) != 1:
                break
            chain.append(nxt)
            seen.add(nxt)
            cur = nxt
        return chain

    managed: set = set()
    for e in fg.edges:
        s, d = e.source, e.dest
        if parent.get(s) or parent.get(d):
            continue
        is_err = getattr(e, "type", 0) == 1
        is_def = bool(getattr(e, "is_default", False)) and kind.get(s) == "diamond"
        # only DEFAULT + ERROR branches are laid perpendicular-flat; a conditional (non-default)
        # port is usually the in-flow spine continuation, so it stays foldable.
        if not (is_err or is_def):
            continue
        if is_def and kind.get(d) == "circle":     # default -> Join stays in-flow (foldable)
            continue
        if len(pred.get(d, [])) != 1:
            continue
        chain = private_chain(d, s)
        if succ.get(chain[-1]):                     # reconnects (retry loop) -> loop-curl owns it
            continue
        managed.update(chain)
    return managed


def _apply_branch_conventions(positions: dict, fg, fold_long: bool = False) -> dict:
    """The reference branch-placement rule as an ENGINE-AGNOSTIC post-pass (runs on final absolute
    positions, so it applies to either engine's output).

    An action's **error-port** target, and a decisional's **DEFAULT** target, are placed
    PERPENDICULAR to the flow — the branch's private dead-end chain sits in a lane directly
    above/below the source (first node at the source's x), continuing right along that lane.
    The ONLY exception is a DEFAULT whose target is a **Join** (merge): it stays IN-FLOW. This
    follows the stated rule verbatim ("default … perpendicular … exception … goes to a
    Join") — there is deliberately NO chain-length test (a long default main-path chain still
    drops perpendicular; confirmed by his newest hand-edit). A branch that RECONNECTS (a retry
    loop) is left to the loop-curl. Collision-checked: a branch keeps its engine position if no
    free up/down lane exists. Container (For-Each) members are never moved."""
    from collections import defaultdict
    P = positions
    kind = {n.id: n.shape for n in fg.nodes}
    parent = {n.id: n.parent_id for n in fg.nodes}
    succ: dict = defaultdict(list)
    pred: dict = defaultdict(list)
    for e in fg.edges:
        if e.source in P and e.dest in P:
            succ[e.source].append(e.dest)
            pred[e.dest].append(e.source)
    DX, GAP = 160.0, 180.0
    # main-body centre for the OUTWARD side choice — measured from the SPINE only (nodes that
    # have a successor), NOT all nodes: the terminal Stops we're about to move are scattered
    # up/down and would skew a global median, tipping near-spine sources to the wrong side.
    _spine = sorted(P[k]["y"] for k in P if succ.get(k)) or sorted(v["y"] for v in P.values())
    center_y = _spine[len(_spine) // 2] if _spine else 0.0

    def occupied(x, y, exclude, thresh=56):
        # default 56 = comfortable non-overlap; the _eval fallback retries at 48 (true node
        # intersection) so the deliberate ~50px stub tucks stay possible as a LAST resort.
        return any(k not in exclude and abs(P[k]["x"] - x) < thresh and abs(P[k]["y"] - y) < thresh
                   for k in P)

    def near_edge(x, y, exclude):
        # a node must never sit ON an edge path (rule: the default lane belongs to the edge).
        for e2 in fg.edges:
            a, b = e2.source, e2.dest
            if a not in P or b not in P or a in exclude or b in exclude:
                continue
            if a in pending_stubs or b in pending_stubs:   # stub awaits re-placement: its edge
                continue                                    # position is stale, must not veto
            ax_, ay_, bx_, by_ = P[a]["x"], P[a]["y"], P[b]["x"], P[b]["y"]
            dx_, dy_ = bx_ - ax_, by_ - ay_
            L2 = dx_ * dx_ + dy_ * dy_
            if L2 < 1:
                continue
            u = max(0.0, min(1.0, ((x - ax_) * dx_ + (y - ay_) * dy_) / L2))
            px_, py_ = ax_ + u * dx_, ay_ + u * dy_
            if (x - px_) ** 2 + (y - py_) ** 2 < 28 * 28:
                return True
        return False

    edges_geo = [(e.source, e.dest) for e in fg.edges if e.source in P and e.dest in P]

    def _orient(a, b, c):
        return (b["y"] - a["y"]) * (c["x"] - b["x"]) - (b["x"] - a["x"]) * (c["y"] - b["y"])

    def crossings():
        n = 0
        for i in range(len(edges_geo)):
            s1, d1 = edges_geo[i]
            a, b = P[s1], P[d1]
            for j in range(i + 1, len(edges_geo)):
                s2, d2 = edges_geo[j]
                if len({s1, d1, s2, d2}) < 4:
                    continue
                cc, dd = P[s2], P[d2]
                if ((_orient(a, b, cc) > 0) != (_orient(a, b, dd) > 0)
                        and (_orient(cc, dd, a) > 0) != (_orient(cc, dd, b) > 0)):
                    n += 1
        return n

    def _lane_coords(ax, sy, sign, n):
        """Perpendicular lane positions for a branch's private chain. Short chains (or when
        clustering is off) run flat along a single lane; a LONG chain (clustering on) FOLDS into
        boustrophedon shelves that stack AWAY from the spine, so a 13-action default tail becomes
        a compact block beside the flow instead of a lane running off-screen."""
        lane = sy + sign * GAP
        W = 4
        if not fold_long or n <= W:
            return [(ax + k * DX, lane) for k in range(n)]
        coords = [None] * n
        for si in range((n + W - 1) // W):
            block = list(range(si * W, min(si * W + W, n)))
            seq = block if si % 2 == 0 else list(reversed(block))
            base = 0 if si % 2 == 0 else (W - len(block))   # right-align R->L shelves: a short
            rowy = lane + sign * si * GAP                    # remainder drops under the previous
            for ci, k in enumerate(seq):                     # shelf's END, not back at its start
                coords[k] = (ax + (base + ci) * DX, rowy)
        return coords

    def _inflow_coords(ax, sy, n):
        """In-flow lane (a conditional dead-end continuing right of the decisional). Short chains
        stay a single flat in-flow row; a LONG one (clustering on) FOLDS into shelves that wrap
        DOWNWARD, so a give-up tail compacts into a block instead of running off the canvas."""
        W = 4
        if not fold_long or n <= W:
            return [(ax + (k + 1) * DX, sy) for k in range(n)]
        coords = [None] * n
        for si in range((n + W - 1) // W):
            block = list(range(si * W, min(si * W + W, n)))
            seq = block if si % 2 == 0 else list(reversed(block))
            base = 0 if si % 2 == 0 else (W - len(block))    # right-align R->L shelves (see above)
            rowy = sy + si * GAP
            for ci, k in enumerate(seq):
                coords[k] = (ax + (base + ci + 1) * DX, rowy)
        return coords

    def private_chain(start, src):
        chain, cur, seen = [start], start, {start, src}
        while True:
            nx = succ.get(cur, [])
            if len(nx) != 1:
                break
            nxt = nx[0]
            if nxt in seen or len(pred.get(nxt, [])) != 1:
                break
            chain.append(nxt)
            seen.add(nxt)
            cur = nxt
        return chain

    # collect every stub chain this pass WILL re-place: until a chain is placed, its edges
    # must be invisible to near_edge (an unplaced stub's edge can slice through a good slot).
    pending_stubs: set = set()
    for e in fg.edges:
        s, d = e.source, e.dest
        if s not in P or d not in P or parent.get(s) or parent.get(d):
            continue
        _err = (getattr(e, "type", 0) == 1)
        _def = bool(getattr(e, "is_default", False)) and kind.get(s) == "diamond"
        _cond = kind.get(s) == "diamond" and not _def and not _err
        if not (_err or _def or _cond):
            continue
        if _def and kind.get(d) == "circle":
            continue
        if len(pred.get(d, [])) != 1:
            continue
        ch = private_chain(d, s)
        if not succ.get(ch[-1]):
            pending_stubs.update(ch)

    for e in fg.edges:
        s, d = e.source, e.dest
        if s not in P or d not in P or parent.get(s) or parent.get(d):
            continue
        is_err = (getattr(e, "type", 0) == 1)
        is_def = bool(getattr(e, "is_default", False)) and kind.get(s) == "diamond"
        # a conditional (non-default / non-error) branch OFF A DECISIONAL
        cond = kind.get(s) == "diamond" and not is_def and not is_err
        if not (is_err or is_def or cond):
            continue
        if is_def and kind.get(d) == "circle":        # default -> Join: stays in-flow
            continue
        if len(pred.get(d, [])) != 1:                 # target must be a private branch head
            continue
        chain = private_chain(d, s)
        if succ.get(chain[-1]):                        # reconnects (retry loop) -> leave it
            continue
        pending_stubs.difference_update(chain)         # being placed now -> edges become real
        ax, sy, excl = P[s]["x"], P[s]["y"], set(chain)
        # A CONDITIONAL dead-end branch of a decisional continues IN-FLOW (right of the
        # decisional) when that lane is free — the flow keeps moving right, with the
        # perpendicular lanes reserved for the default + loop branches (the rule: a
        # non-default terminal like a give-up Stop goes in-flow if the default didn't take it).
        def _eval(cands):
            exclS = excl | {s}
            for thresh in (56, 48):                    # tight 48 tuck only when nothing clears 56
                best, best_cc = None, None
                for cand in cands:
                    if any(occupied(px, py, excl, thresh) for px, py in cand):
                        continue
                    if any(near_edge(px, py, exclS) for px, py in cand):
                        continue
                    snap = {nid: dict(P[nid]) for nid in chain}
                    for nid, (px, py) in zip(chain, cand):
                        P[nid] = {"x": px, "y": py}
                    cc = crossings()
                    for nid in chain:
                        P[nid] = snap[nid]
                    if best is None or cc < best_cc:   # candidates ordered: ties keep the FIRST
                        best, best_cc = cand, cc
                if best is not None:
                    return best
            return None

        n = len(chain)

        def _vcol(x_first, y_first, sign, n_):
            """Vertical serpentine for a dead-end chain: columns of <=4 stepping away from the
            flow (sign), folding into the next column when deeper -- reference chains run
            vertically but never taller than ~4 rows (his ANAF pocket is 2 columns x 4)."""
            W = 4
            cols = [list(range(k, min(k + W, n_))) for k in range(0, n_, W)]
            out = [None] * n_
            base = len(cols[0]) - 1
            for j, col in enumerate(cols):
                x = x_first + j * DX
                for r, idx in enumerate(col):
                    row = r if j % 2 == 0 else base - r
                    out[idx] = (x, y_first + sign * row * GAP)
            return out

        # Reference pattern: a LONG dead-end chain runs VERTICALLY (constant x, stepping away
        # from the flow) -- a compact column instead of a lane running off-canvas (his
        # GetInfoSales terminal chain and 0GetInfo stubs). Short chains (1-2) keep the
        # approved L-shape lane. Vertical goes FIRST for n>=3 so it wins crossing ties.
        # the DEFAULT owns the in-flow lane: when this decisional's default edge continues
        # in-flow (default -> Join stays in-flow per the stated exception), a conditional
        # dead-end must NOT take that slot -- it goes perpendicular instead (his 0GetInfo
        # fix: the no-info Stop drops below the decisional; the default runs on to the Join).
        default_inflow = any(bool(getattr(e2, "is_default", False)) and kind.get(e2.dest) == "circle"
                             for e2 in fg.edges if e2.source == s)
        if cond and not default_inflow:
            flat = _inflow_coords(ax, sy, n)
            drop = _vcol(ax + DX, sy, 1, n)                      # head in-flow, then DOWN
            best = _eval([drop, flat] if n >= 3 else [flat])
            if best is not None:
                for nid, (px, py) in zip(chain, best):
                    P[nid] = {"x": px, "y": py}
                continue
        # outward = AWAY from where the flow came from: a fan-lane branch above the spine
        # sends its stub further up, one below sends it down (the 0GetInfo golden). When
        # the source sits in-line with its predecessors (a spine node), fall back to the
        # global centre -- which keeps every previously-approved placement unchanged.
        preds_y = sorted(P[p]["y"] for p in pred.get(s, []) if p in P)
        pmed = preds_y[len(preds_y) // 2] if preds_y else None
        if pmed is not None and abs(sy - pmed) > GAP * 0.5:
            outward = 1 if sy > pmed else -1
        else:
            outward = 1 if sy >= center_y else -1      # perpendicular, crossing-driven side
        cands = []
        for sign in (outward, -outward):               # outward tried first => ties keep outward
            lane = _lane_coords(ax, sy, sign, n)
            vert = _vcol(ax, sy + sign * GAP, sign, n)
            cands += [vert, lane] if n >= 3 else [lane, vert]
            if n == 1:                                 # the reference half-gap tuck for a lone stub
                cands.append([(ax, sy + sign * GAP * 0.72)])
        best = _eval(cands)
        if best:
            for nid, (px, py) in zip(chain, best):
                P[nid] = {"x": px, "y": py}
    return positions


def layout_flow(obj: dict, flow_id: str | None = None,
                only: list[str] | None = None, cluster: bool = False,
                minimize_crossings: bool = False) -> dict:
    """Re-lay-out one flow. Returns {flow_id, nodes_moved, areas_resized, bbox, positions,
    areas, bundle} where `bundle` is the modified copy of `obj`.

    `only` = a list of action ids to reposition WITHOUT reshuffling the rest (the
    "re-tidy just this action" mode). In that mode only those actions' positions are
    written; every other action, the area frames, and CanvasData are left byte-identical."""
    import os
    if (os.environ.get("LAYOUT_ENGINE") or "").strip().lower() == "auto":
        return _best_of_engines(obj, flow_id=flow_id, only=only)
    obj = copy.deepcopy(obj)
    flows, _fk = _flows(obj)
    if flows is not None:
        if flow_id:
            flow = next((f for f in flows if _get(f, "Id") == flow_id), None)
            if flow is None:
                raise ValueError(f"flow_id {flow_id} not found")
        elif len(flows) == 1:
            flow = flows[0]
        else:
            raise ValueError(f"bundle has {len(flows)} flows; pass flow_id")
    else:
        flow = obj

    fg = read_flow(flow)
    nodes = [{"id": n.id, "width": n.size["w"], "height": n.size["h"],
              "parent_id": n.parent_id, "kind": n.shape, "position": n.position}
             for n in fg.nodes]
    edges = [{"source": e.source, "dest": e.dest, "type": e.type,
              "is_default": e.is_default} for e in fg.edges]
    only_set = set(only) if only else None
    if only_set is not None:
        missing = only_set - {n.id for n in fg.nodes}
        if missing:
            raise ValueError(f"--only action id(s) not in this flow: {sorted(missing)}")
    opts = {}
    if only_set is None:
        if cluster:
            opts["CLUSTER"] = True
            opts["NO_CLUSTER_IDS"] = _branch_managed_nodes(fg)
        if minimize_crossings:
            opts["MINIMIZE_CROSSINGS"] = True
    # Single dispatch point: dispatch.layout picks the engine from the LAYOUT_ENGINE flag
    # (legacy default, elk opt-in). Both engines share this exact signature + return contract,
    # so everything below (designer_writes, Start-anchoring, write-back) is engine-agnostic.
    # Cycle-aware: a large embedded cycle (SCC) is collapsed to a meta-node, laid out around,
    # then expanded as a compact band; falls through to a plain dispatch otherwise.
    result = cycles.layout(nodes, edges, opts=(opts or None),
                           subset=(list(only_set) if only_set else None),
                           dispatch_layout=dispatch.layout)
    positions, areas = result["positions"], result["areas"]

    # Engine-agnostic branch-placement convention (the reference rule): error-port + decisional
    # default branches drop perpendicular to the flow (unless default->Join). Full layouts only.
    if only_set is None and positions:
        base_pos = _apply_branch_conventions({k: dict(v) for k, v in positions.items()},
                                             fg, fold_long=cluster)
        # FAN pattern (parallel alternative branches between one split and one merge -> flat
        # stacked lanes). Tried as a variant and kept ONLY when strictly better.
        fan_pos = _apply_fan_lanes({k: dict(v) for k, v in positions.items()}, fg)
        if fan_pos != positions:
            fan_pos = _apply_branch_conventions(fan_pos, fg, fold_long=cluster)
            positions = fan_pos if _layout_quality(fan_pos, fg) < _layout_quality(base_pos, fg)                 else base_pos
        else:
            positions = base_pos

    actions = _get(flow, "Actions", default=[]) or []
    # Anchor a full re-layout to where the diagram already sits — keep Start exactly put —
    # so the user's designer viewport still frames it. Without this the whole graph jumps to
    # the origin and the canvas looks empty until you pan/fit far away.
    if only_set is None and positions:
        old = {}
        for a in actions:
            aid = _get(a, "Id")
            p = _get(_get(a, "CustomData", default={}) or {}, "position")
            if aid and isinstance(p, dict) and p.get("x") is not None:
                old[aid] = {"x": float(p["x"]), "y": float(p["y"])}
        anchor = fg.start_id if (fg.start_id in old and fg.start_id in positions) else None
        if anchor:
            sx = old[anchor]["x"] - positions[anchor]["x"]
            sy = old[anchor]["y"] - positions[anchor]["y"]
        elif old:
            sx = min(p["x"] for p in old.values()) - min(p["x"] for p in positions.values())
            sy = min(p["y"] for p in old.values()) - min(p["y"] for p in positions.values())
        else:
            sx = sy = 0.0
        if sx or sy:
            positions = {k: {"x": v["x"] + sx, "y": v["y"] + sy} for k, v in positions.items()}
            areas = {k: {**v, "x": v["x"] + sx, "y": v["y"] + sy} for k, v in areas.items()}

    # PROCESIO stores a container child's position RELATIVE to its parent area's frame,
    # and an area node's position IS that frame top-left. engine.designer_writes encodes it.
    parent_of = {_get(a, "Id"): _get(a, "ParentId") for a in actions
                 if _get(a, "ParentId") in areas}
    writes = engine.designer_writes(positions, areas, parent_of)

    moved = resized = 0
    for a in actions:
        aid = _get(a, "Id")
        if only_set is not None and aid not in only_set:
            continue                       # partial mode: leave the rest untouched
        w = writes.get(aid)
        if not w:
            continue
        cd_key = _key(a, "CustomData")
        if not cd_key:
            continue
        cd = a[cd_key]
        pos_key = _key(cd, "position") or "position"
        cd[pos_key] = dict(w["pos"])
        moved += 1
        if w["areaSize"] is not None:
            asz_key = _key(cd, "areaSize") or "areaSize"
            cd[asz_key] = dict(w["areaSize"])
            resized += 1
    # NEVER touch CanvasData (the designer viewport pan/zoom). Resetting it jumps the
    # user's view away from the content — leave it exactly as the flow had it; the user
    # can fit-to-screen in the designer to frame a re-laid-out process.
    return {"flow_id": _get(flow, "Id"), "nodes_moved": moved,
            "areas_resized": resized, "bbox": result["bbox"],
            "positions": {k: _round(v) for k, v in positions.items()},
            "areas": areas, "bundle": obj}


def verify_render(obj: dict, flow_id: str | None = None) -> dict:
    """Simulate how the PROCESIO designer renders a flow's CURRENT positions (a container
    child's stored position is RELATIVE to its parent area's frame top-left) and report
    layout problems: children rendered outside their container frame, and node overlaps.
    Read-only — does not modify the flow. Returns {ok, issue_count, issues, areas, nodes}."""
    flows, _fk = _flows(obj)
    if flows is not None:
        flow = (next((f for f in flows if _get(f, "Id") == flow_id), None) if flow_id
                else (flows[0] if len(flows) == 1 else None))
        if flow is None:
            raise ValueError("verify_render: bundle has multiple flows; pass flow_id")
    else:
        flow = obj
    actions = _get(flow, "Actions", default=[]) or []
    nodes = {}
    for a in actions:
        aid = _get(a, "Id")
        cd = _get(a, "CustomData", default={}) or {}
        p = _get(cd, "position") or {}
        asz = _get(cd, "areaSize") or {}
        is_area = _get(cd, "type") == "area"
        nodes[aid] = {
            "x": float(p.get("x", 0) or 0), "y": float(p.get("y", 0) or 0),
            "parent": _get(a, "ParentId"), "is_area": is_area,
            "w": float(asz.get("width", 48) or 48) if is_area else 48.0,
            "h": float(asz.get("height", 48) or 48) if is_area else 48.0,
            "name": _get(cd, "name") or _get(a, "ActionTemplateName") or aid,
        }
    # absolute rendered position: a child is offset by its parent area's absolute top-left
    absol = {}
    for aid, n in nodes.items():
        par = n["parent"]
        if par in nodes and nodes[par]["is_area"]:
            absol[aid] = {"x": nodes[par]["x"] + n["x"], "y": nodes[par]["y"] + n["y"]}
        else:
            absol[aid] = {"x": n["x"], "y": n["y"]}
    issues = []
    for aid, n in nodes.items():
        par = n["parent"]
        if par in nodes and nodes[par]["is_area"]:
            pp = nodes[par]
            cx, cy = absol[aid]["x"], absol[aid]["y"]
            if not (pp["x"] - 1 <= cx - 24 and cx + 24 <= pp["x"] + pp["w"] + 1
                    and pp["y"] - 1 <= cy - 24 and cy + 24 <= pp["y"] + pp["h"] + 1):
                issues.append({"type": "child_outside_frame", "child": n["name"], "area": pp["name"]})
    leaves = [aid for aid, n in nodes.items() if not n["is_area"]]
    for i in range(len(leaves)):
        a = absol[leaves[i]]
        for j in range(i + 1, len(leaves)):
            b = absol[leaves[j]]
            if abs(a["x"] - b["x"]) < 46 and abs(a["y"] - b["y"]) < 46:
                issues.append({"type": "overlap",
                               "a": nodes[leaves[i]]["name"], "b": nodes[leaves[j]]["name"]})
    return {"ok": not issues, "issue_count": len(issues), "issues": issues[:40],
            "areas": sum(1 for n in nodes.values() if n["is_area"]), "nodes": len(nodes)}


def layout_resource_map(obj: dict, root_flow_id: str | None = None,
                        levels: int | None = None) -> dict:
    """Position the cross-process (process→process) call graph. Returns
    {root, nodes:[{flow_id, title, x, y}], edges:[...]}. Callers fall left of their
    callees (longest-path layering); LVL-centering on the root is a future refinement."""
    rm = read_bundle(obj)
    graphs = rm["flows"]
    proc_edges = rm["process_edges"]
    node_ids = set(graphs) | {e["target"] for e in proc_edges} | {e["source"] for e in proc_edges}
    nodes = [{"id": fid, "width": 220, "height": 60} for fid in sorted(node_ids)]
    edges = [{"source": e["source"], "dest": e["target"], "type": 0} for e in proc_edges]
    result = engine.layout(nodes, edges, {"DX": 360, "DY": 90, "NODE_W": 220, "NODE_H": 60})
    titles = {fid: (g.get("title") if isinstance(g, dict) else None) for fid, g in graphs.items()}
    out_nodes = [{"flow_id": fid, "title": titles.get(fid),
                  "x": p["x"], "y": p["y"]} for fid, p in sorted(result["positions"].items())]
    return {"root": root_flow_id, "nodes": out_nodes, "edges": proc_edges,
            "bbox": result["bbox"]}
