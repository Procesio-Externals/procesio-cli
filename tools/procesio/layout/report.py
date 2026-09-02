"""Engine-agnostic layout verification: measure the readability of a laid-out flow.

Works on ANY flow's stored positions — whichever engine (legacy `engine` or `elk_engine`)
produced them — because it reads the OUTPUT geometry, not the algorithm. Pure + offline
(no network, no rendering).

`build_report(obj, flow_id)` returns:
  { ok, hard_issues, metrics, containers } where
  - hard_issues  = overlaps + container children rendered outside their frame (real defects)
  - metrics      = crossings, edge lengths, back-edges, bbox/aspect, vertical rows, fill
  - containers   = per For-Each: frame size, inner padding L/T/R/B, inner spacing, warnings
"""
from __future__ import annotations

# readability thresholds (px) — a long edge and a min sane For-Each frame
LONG_EDGE_PX = 600
MIN_FOREACH_W = 320
MIN_FOREACH_H = 200


def _g(d, *ks, default=None):
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for k in ks:
        if k.lower() in low:
            return low[k.lower()]
    return default


def _select_flow(obj: dict, flow_id: str | None) -> dict:
    flows = _g(obj, "Flows", "flows")
    if flows is None:
        return obj
    if flow_id:
        f = next((x for x in flows if _g(x, "Id", "id") == flow_id), None)
        if f is None:
            raise ValueError(f"flow_id {flow_id} not found")
        return f
    if len(flows) == 1:
        return flows[0]
    raise ValueError(f"bundle has {len(flows)} flows; pass flow_id")


def _extract(flow: dict) -> dict:
    """Absolute geometry: node centres, edge attach-points (area = frame top-left), edges."""
    acts = _g(flow, "actions", "Actions", default=[]) or []
    nodes = {}
    for a in acts:
        cd = _g(a, "customData", "CustomData", default={}) or {}
        pos = _g(cd, "position", default={}) or {}
        asz = _g(cd, "areaSize", default={}) or {}
        is_area = _g(cd, "type") == "area"
        nodes[_g(a, "id", "Id")] = {
            "x": float(_g(pos, "x", default=0) or 0), "y": float(_g(pos, "y", default=0) or 0),
            "parent": _g(a, "parentId", "ParentId"), "is_area": is_area,
            "w": float(_g(asz, "width", default=48) or 48) if is_area else 48.0,
            "h": float(_g(asz, "height", default=48) or 48) if is_area else 48.0,
            "name": _g(cd, "name") or _g(a, "actionTemplateName", "ActionTemplateName") or _g(a, "id", "Id"),
        }
    cen, att = {}, {}
    for aid, n in nodes.items():
        par = n["parent"]
        if n["is_area"]:
            base_x = n["x"] if par not in nodes else nodes[par]["x"] + n["x"]
            base_y = n["y"] if par not in nodes else nodes[par]["y"] + n["y"]
            cen[aid] = {"x": base_x + n["w"] / 2, "y": base_y + n["h"] / 2}
            att[aid] = {"x": base_x, "y": base_y}
        elif par in nodes and nodes[par]["is_area"]:
            cen[aid] = {"x": nodes[par]["x"] + n["x"], "y": nodes[par]["y"] + n["y"]}
            att[aid] = cen[aid]
        else:
            cen[aid] = {"x": n["x"], "y": n["y"]}
            att[aid] = cen[aid]
    edges = []
    for a in acts:
        s = _g(a, "id", "Id")
        for p in _g(a, "ports", "Ports", default=[]) or []:
            d = _g(p, "destinationId", "DestinationId")
            src = _g(p, "sourceId", "SourceId") or s
            t = int(_g(p, "type", "Type", default=0) or 0)
            if src in nodes and d in nodes and src != d:
                edges.append((src, d, t))
    return {"nodes": nodes, "cen": cen, "att": att, "edges": edges}


def _seg(a, b, c, d) -> bool:
    def o(p, q, r):
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])
    return (o(a, b, c) > 0) != (o(a, b, d) > 0) and (o(c, d, a) > 0) != (o(c, d, b) > 0)


def _hard_issues(geo: dict) -> list[dict]:
    """Overlaps between leaf nodes + container children rendered outside their frame."""
    nodes, cen = geo["nodes"], geo["cen"]
    issues = []
    for aid, n in nodes.items():
        par = n["parent"]
        if par in nodes and nodes[par]["is_area"]:
            pp, fx, fy = nodes[par], nodes[par]["x"], nodes[par]["y"]
            cx, cy = cen[aid]["x"], cen[aid]["y"]
            if not (fx - 1 <= cx - 24 and cx + 24 <= fx + pp["w"] + 1
                    and fy - 1 <= cy - 24 and cy + 24 <= fy + pp["h"] + 1):
                issues.append({"type": "child_outside_frame", "child": n["name"], "area": pp["name"]})
    leaves = [aid for aid, n in nodes.items() if not n["is_area"]]
    for i in range(len(leaves)):
        a = cen[leaves[i]]
        for j in range(i + 1, len(leaves)):
            b = cen[leaves[j]]
            if abs(a["x"] - b["x"]) < 46 and abs(a["y"] - b["y"]) < 46:
                issues.append({"type": "overlap",
                               "a": nodes[leaves[i]]["name"], "b": nodes[leaves[j]]["name"]})
    return issues


def _metrics(geo: dict) -> dict:
    att, edges, nodes, cen = geo["att"], geo["edges"], geo["nodes"], geo["cen"]
    cx = [c["x"] for c in cen.values()] or [0]
    cy = [c["y"] for c in cen.values()] or [0]
    W, H = max(cx) - min(cx) + 68, max(cy) - min(cy) + 68
    E = [(att[s], att[d]) for s, d, _ in edges]
    cr = 0
    for i in range(len(E)):
        s1, d1, _ = edges[i]
        for j in range(i + 1, len(E)):
            s2, d2, _ = edges[j]
            if len({s1, d1, s2, d2}) < 4:
                continue
            if _seg(E[i][0], E[i][1], E[j][0], E[j][1]):
                cr += 1
    lens = [abs(att[s]["x"] - att[d]["x"]) + abs(att[s]["y"] - att[d]["y"]) for s, d, _ in edges]
    back = sum(1 for s, d, _ in edges if att[d]["x"] < att[s]["x"] - 24)
    rows = len({round(c["y"] / 30) for c in cen.values()})
    fill = (len(nodes) * 68 * 68) / (W * H) if W * H else 0
    return {
        "nodes": len(nodes), "edges": len(edges), "crossings": cr, "back_edges": back,
        "max_edge_px": round(max(lens)) if lens else 0,
        "mean_edge_px": round(sum(lens) / len(lens)) if lens else 0,
        "long_edges": sum(1 for L in lens if L > LONG_EDGE_PX),
        "width": round(W), "height": round(H),
        "aspect_w_to_h": round(W / H, 2) if H else 0,
        "vertical_rows": rows, "fill_pct": round(fill * 100, 1),
    }


def _containers(geo: dict) -> list[dict]:
    nodes = geo["nodes"]
    out = []
    for aid, n in nodes.items():
        if not n["is_area"]:
            continue
        kids = [k for k in nodes.values() if k["parent"] == aid]
        c = {"name": n["name"], "width": round(n["w"]), "height": round(n["h"]),
             "children": len(kids), "warnings": []}
        if kids:
            cxs = [k["x"] for k in kids]
            cys = [k["y"] for k in kids]
            pad = {"l": round(min(cxs) - 24), "t": round(min(cys) - 24),
                   "r": round(n["w"] - (max(cxs) + 24)), "b": round(n["h"] - (max(cys) + 24))}
            c["padding"] = pad
            xs = sorted(cxs)
            c["inner_h_spacing"] = [round(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)]
            for side, v in pad.items():
                if v < 0:
                    c["warnings"].append(f"negative {side} padding ({v}) — child overflows frame")
        if n["w"] < MIN_FOREACH_W:
            c["warnings"].append(f"width {round(n['w'])} < min {MIN_FOREACH_W}")
        if n["h"] < MIN_FOREACH_H:
            c["warnings"].append(f"height {round(n['h'])} < min {MIN_FOREACH_H}")
        out.append(c)
    return out


def build_report(obj: dict, flow_id: str | None = None) -> dict:
    flow = _select_flow(obj, flow_id)
    geo = _extract(flow)
    hard = _hard_issues(geo)
    containers = _containers(geo)
    container_warnings = [w for c in containers for w in c["warnings"]]
    return {
        "ok": not hard and not container_warnings,
        "flow_id": _g(flow, "Id", "id"),
        "hard_issue_count": len(hard),
        "hard_issues": hard[:40],
        "metrics": _metrics(geo),
        "containers": containers,
    }
