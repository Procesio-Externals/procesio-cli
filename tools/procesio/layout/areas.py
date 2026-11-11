"""Area shapes: the canvas rectangles that name a group of actions and say what it does.

PROCESIO stores decorative canvas shapes in the flow's `canvasData.shapes` (canvas-engine,
PRC-4391). The persisted model is exactly:

    {id, kind (0 rectangle | 1 ellipse | 2 diamond), position {x, y} (top-left),
     dimension {width, height}, title, text, zIndex, style {fillColor, fillAlpha, ...}}

`zIndex` lives in the shape band [-1000, -1], below connectors (0) and nodes, so a shape never
hides an action. The designer rebuilds `canvasData` from those keys on every save, so nothing
extra survives there: group MEMBERSHIP is geometric. An action belongs to the area whose
rectangle holds its centre (the smallest one when several do). A For Each's children belong to
the area of their container.

This module is pure (no I/O, no PROCESIO imports) and deterministic:

    boxes = node_boxes(actions)                       # top-level footprint per action id
    rects = fit(boxes, [(key, [member ids]), ...])    # rectangles per group, never covering
                                                      # a node that is not a member
    shapes = to_shapes(groups, rects, ids)            # canvasData.shapes entries
    members = membership(actions, shapes)             # shape index -> action ids (reading)

Geometry, in designer coordinates: a square/circle/diamond node's position is its CENTRE and
it is 48x48 with its name drawn underneath; a For Each (`area`) node's position is its frame's
TOP-LEFT and `areaSize` is the frame; a container child's position is relative to its frame.
"""
from __future__ import annotations

import math

NODE = 48.0
HALF_W = 60.0          # half-width reserved around a node centre: the label is wider than the icon
LABEL_H = 36.0         # the node name drawn under the icon
SIDE_PAD = 12.0        # breathing room between the outermost member and the rectangle edge
FRAME_PAD = 14.0       # same, around a For Each frame
TITLE_PAD = 6.0        # canvas-engine TITLE_PADDING
TITLE_LINE = 18.0      # title at the default 14px
TEXT_GAP = 4.0         # canvas-engine TEXT_GAP
TEXT_LINE = 15.0       # body text at the default 12px
CHAR_W = 6.6           # average glyph width of the 12px body font
MAX_TEXT_LINES = 4     # beyond this the header would cover the row above: keep area text short
CONT = " (cont.)"      # title suffix of a group's second and later rectangles
Z_DEFAULT = -500       # canvas-engine SHAPE_DEFAULT
SHAPE_MIN, SHAPE_MAX = -1000, -1

# Soft, distinct fills (PIXI numeric colours), cycled per group. A low alpha keeps the actions
# and connectors on top readable; the border carries the group's colour at full strength.
PALETTE = [
    (0x2E7D32, 0xE8F5E9),   # green
    (0x1565C0, 0xE3F2FD),   # blue
    (0xEF6C00, 0xFFF3E0),   # orange
    (0x6A1B9A, 0xF3E5F5),   # purple
    (0x00838F, 0xE0F7FA),   # teal
    (0xAD1457, 0xFCE4EC),   # pink
    (0x5D4037, 0xEFEBE9),   # brown
    (0x455A64, 0xECEFF1),   # slate
]


def _g(d, *names, default=None):
    """Case-insensitive get: the live API is camelCase, the PUT DTO PascalCase."""
    if not isinstance(d, dict):
        return default
    low = {k.lower(): k for k in d}
    for n in names:
        k = low.get(n.lower())
        if k is not None:
            return d[k]
    return default


def _cd(a: dict) -> dict:
    return _g(a, "customData", default={}) or {}


def _is_area(a: dict) -> bool:
    return _cd(a).get("type") == "area"


def _pos(a: dict) -> tuple[float, float]:
    p = _cd(a).get("position") or {}
    return float(p.get("x") or 0), float(p.get("y") or 0)


def _size(a: dict) -> tuple[float, float]:
    s = _cd(a).get("areaSize") or {}
    return float(s.get("width") or NODE), float(s.get("height") or NODE)


def top_level_of(actions: list[dict]) -> dict:
    """action id -> the id of its top-level ancestor (itself when it is top-level)."""
    parent = {_g(a, "id"): _g(a, "parentId") for a in actions}
    out = {}
    for aid in parent:
        cur, seen = aid, set()
        while parent.get(cur) in parent and cur not in seen:
            seen.add(cur)
            cur = parent[cur]
        out[aid] = cur
    return out


def node_boxes(actions: list[dict]) -> dict:
    """Footprint (x0, y0, x1, y1) of every TOP-LEVEL action, label included."""
    ids = {_g(a, "id") for a in actions}
    out = {}
    for a in actions:
        if _g(a, "parentId") in ids:
            continue                      # inside a For Each: covered by its frame
        x, y = _pos(a)
        if _is_area(a):
            w, h = _size(a)
            out[_g(a, "id")] = (x - FRAME_PAD, y - FRAME_PAD, x + w + FRAME_PAD, y + h + FRAME_PAD)
        else:
            out[_g(a, "id")] = (x - HALF_W, y - NODE / 2, x + HALF_W, y + NODE / 2 + LABEL_H)
    return out


def centre(a: dict, by_id: dict) -> tuple[float, float]:
    """Absolute centre of an action (container children resolved through their frame)."""
    x, y = _pos(a)
    par = by_id.get(_g(a, "parentId"))
    if _is_area(a):
        w, h = _size(a)
        bx, by = (centre_origin(par, by_id) if par else (0.0, 0.0))
        return bx + x + w / 2, by + y + h / 2
    if par is not None:
        bx, by = centre_origin(par, by_id)
        return bx + x, by + y
    return x, y


def centre_origin(frame: dict, by_id: dict) -> tuple[float, float]:
    """Absolute top-left of a For Each frame (frames can nest through subprocess-free loops)."""
    x, y = _pos(frame)
    par = by_id.get(_g(frame, "parentId"))
    if par is None:
        return x, y
    bx, by = centre_origin(par, by_id)
    return bx + x, by + y


def text_lines(text: str, width: float) -> int:
    """Lines the canvas wraps `text` into at the default body font, inside `width`."""
    text = (text or "").strip()
    if not text:
        return 0
    per_line = max(1, int((width - 2 * TITLE_PAD) / CHAR_W))
    lines = 0
    for para in text.split("\n"):
        lines += max(1, math.ceil(len(para) / per_line))
    return lines


def header_height(title: str, text: str, width: float) -> float:
    """Height of the title + wrapped text drawn at the top of a shape."""
    h = TITLE_PAD
    if (title or "").strip():
        h += TITLE_LINE
    n = min(text_lines(text, width), MAX_TEXT_LINES)
    if n:
        h += TEXT_GAP + n * TEXT_LINE
    return h + TITLE_PAD


def _union(rs):
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def _hits(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _frame(members_rect, title, text):
    x0, y0, x1, y1 = members_rect
    x0, x1 = x0 - SIDE_PAD, x1 + SIDE_PAD
    return (x0, y0 - header_height(title, text, x1 - x0), x1, y1 + SIDE_PAD)


def fit(boxes: dict, groups: list[tuple], texts: dict | None = None) -> dict:
    """Rectangles for each group, as {key: [rect, ...]} in reading order.

    `groups` is [(key, [member ids])]; `texts` {key: (title, text)} sizes each header. A group
    whose members sit together gets ONE rectangle. Members that cannot share a rectangle without
    it covering a node outside the group, or another group's rectangle, are split into several
    (agglomerative: the closest pair that can merge does, until none can). Deterministic."""
    texts = texts or {}
    placed: list = []                     # rectangles of earlier groups: never overlapped
    out: dict = {}
    for key, members in groups:
        members = [m for m in members if m in boxes]
        if not members:
            out[key] = []
            continue
        title, text = texts.get(key, ("", ""))
        mine = set(members)
        foreign = [b for nid, b in boxes.items() if nid not in mine]
        clusters = [[m] for m in sorted(members, key=lambda m: (boxes[m][0], boxes[m][1], m))]

        def ok(rect):
            return not any(_hits(rect, f) for f in foreign) and not any(_hits(rect, p) for p in placed)

        while True:
            best = None
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    u = _union([boxes[m] for m in clusters[i] + clusters[j]])
                    fr = _frame(u, title, text)
                    if not ok(fr):
                        continue
                    area = (fr[2] - fr[0]) * (fr[3] - fr[1])
                    if best is None or area < best[0]:
                        best = (area, i, j)
            if best is None:
                break
            _, i, j = best
            clusters[i] = clusters[i] + clusters[j]
            del clusters[j]
        rects = []
        for c in sorted(clusters, key=lambda c: (min(boxes[m][1] for m in c), min(boxes[m][0] for m in c))):
            u = _union([boxes[m] for m in c])
            rects.append(_frame(u, title, text) if not rects else
                         _frame(u, title + CONT, ""))
        out[key] = rects
        placed.extend(rects)
    return out


def style_for(index: int) -> dict:
    border, fill = PALETTE[index % len(PALETTE)]
    return {"fillColor": fill, "fillAlpha": 0.35, "borderColor": border, "borderWidth": 1,
            "titleColor": border, "titleAlign": 0}


def to_shapes(groups: list[dict], rects: dict, new_id) -> list[dict]:
    """canvasData.shapes entries for `groups` ([{key, title, text, id?, style?}]) placed at
    `rects` ({key: [rect, ...]}). The first rectangle carries the title and the text; any
    further one is titled '<title> (cont.)' with no text. An existing shape id is reused for
    the first rectangle so a re-fit keeps the shape's identity."""
    shapes = []
    for gi, g in enumerate(groups):
        for ri, (x0, y0, x1, y1) in enumerate(rects.get(g["key"]) or []):
            sid = g.get("id") if ri == 0 and g.get("id") else new_id()
            shapes.append({
                "id": sid, "kind": 0,
                "position": {"x": round(x0, 2), "y": round(y0, 2)},
                "dimension": {"width": round(x1 - x0, 2), "height": round(y1 - y0, 2)},
                "title": g["title"] if ri == 0 else g["title"] + CONT,
                "text": g.get("text", "") if ri == 0 else "",
                "zIndex": Z_DEFAULT - gi,
                "style": dict(g.get("style") or style_for(gi)),
            })
    return shapes


def shape_rect(s: dict) -> tuple[float, float, float, float]:
    p = _g(s, "position", default={}) or {}
    d = _g(s, "dimension", default={}) or {}
    x, y = float(p.get("x") or 0), float(p.get("y") or 0)
    return x, y, x + float(d.get("width") or 0), y + float(d.get("height") or 0)


def base_title(title: str) -> str:
    t = (title or "").strip()
    return t[: -len(CONT)].strip() if t.endswith(CONT) else t


def membership(actions: list[dict], shapes: list[dict]) -> dict:
    """{shape index: [top-level action ids]} - an action belongs to the SMALLEST shape whose
    rectangle holds its centre. Children of a For Each follow their container."""
    by_id = {_g(a, "id"): a for a in actions}
    top = top_level_of(actions)
    rects = [shape_rect(s) for s in shapes]
    out: dict = {i: [] for i in range(len(shapes))}
    for a in actions:
        aid = _g(a, "id")
        if top.get(aid) != aid:
            continue
        cx, cy = centre(a, by_id)
        hit = [(r[2] - r[0]) * (r[3] - r[1]) for r in rects]
        cands = [i for i, r in enumerate(rects) if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]]
        if cands:
            out[min(cands, key=lambda i: (hit[i], i))].append(aid)
    return out


def groups_from_shapes(actions: list[dict], shapes: list[dict]) -> list[dict]:
    """The documented areas of a flow: [{title, text, shape_ids, members: [action ids]}],
    rectangles of one group ('<title> (cont.)') folded together. Shapes holding no action
    (free notes on the canvas) are not areas and are left out."""
    mem = membership(actions, shapes)
    groups: dict = {}
    order: list = []
    for i, s in enumerate(shapes):
        if not mem.get(i):
            continue
        key = base_title(_g(s, "title", default="") or "") or f"(untitled area {i + 1})"
        if key not in groups:
            groups[key] = {"title": key, "text": "", "shape_ids": [], "members": []}
            order.append(key)
        g = groups[key]
        g["shape_ids"].append(_g(s, "id"))
        if not g["text"]:
            g["text"] = (_g(s, "text", default="") or "").strip()
        g["members"].extend(m for m in mem[i] if m not in g["members"])
    return [groups[k] for k in order]


def free_shapes(actions: list[dict], shapes: list[dict]) -> list[dict]:
    """Shapes that hold no action - a person's notes on the canvas. Kept as they are."""
    mem = membership(actions, shapes)
    return [s for i, s in enumerate(shapes) if not mem.get(i)]


def refit(old_actions: list[dict], new_actions: list[dict], shapes: list[dict], new_id) -> list[dict]:
    """Re-fit area shapes after the actions moved (a re-layout): membership is read on the OLD
    positions, the rectangles are recomputed around the NEW ones. Free notes stay put. Shape
    ids, titles, texts and styles are kept."""
    if not shapes:
        return shapes
    groups = groups_from_shapes(old_actions, shapes)
    if not groups:
        return shapes
    by_title = {}
    for s in shapes:
        by_title.setdefault(base_title(_g(s, "title", default="") or ""), s)
    spec, keyed = [], []
    for gi, g in enumerate(groups):
        first = by_title.get(g["title"]) or {}
        spec.append({"key": gi, "title": g["title"], "text": g["text"], "id": g["shape_ids"][0],
                     "style": _g(first, "style")})
        keyed.append((gi, g["members"]))
    boxes = node_boxes(new_actions)
    rects = fit(boxes, keyed, {s["key"]: (s["title"], s["text"]) for s in spec})
    return free_shapes(old_actions, shapes) + to_shapes(spec, rects, new_id)
