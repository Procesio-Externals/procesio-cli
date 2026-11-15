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

Geometry, in designer coordinates (checked on screenshots of the designer): a square/circle/
diamond node's position is the TOP-LEFT of its 48x48 icon, with its name drawn underneath and
centred on the icon; a For Each (`area`) node's position is its frame's TOP-LEFT, `areaSize` is
the frame and its name is drawn under the frame; a container child's position is relative to its
frame. Shape positions are top-left too, so all of these share one coordinate space.
"""
from __future__ import annotations

import math

NODE = 48.0
HALF_W = 60.0          # half-width reserved around a node centre: the label is wider than the icon
LABEL_H = 36.0         # the node name drawn under the icon (or under a For Each frame)
PORT_PAD = 10.0        # room above a node for the incoming connector's arrow and port
SIDE_PAD = 12.0        # breathing room between the outermost member and the rectangle edge
FRAME_PAD = 14.0       # same, around a For Each frame
TITLE_PAD = 6.0        # canvas-engine TITLE_PADDING
TITLE_LINE = 18.0      # title at the default 14px
TEXT_GAP = 4.0         # canvas-engine TEXT_GAP
TEXT_LINE = 15.0       # body text at the default 12px
CHAR_W = 6.6           # average glyph width of the 12px body font
MAX_TEXT_LINES = 4     # beyond this the header would cover the row above: keep area text short
CONT = " (cont.)"      # title suffix of a group's second and later rectangles
FRAGMENTED = 2         # more rectangles than this for one area: its actions are scattered
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
            # the loop's name is drawn under the frame: the area must hold it too
            w, h = _size(a)
            out[_g(a, "id")] = (x - FRAME_PAD, y - FRAME_PAD, x + w + FRAME_PAD, y + h + LABEL_H)
        else:
            cx = x + NODE / 2             # position is the icon's top-left; the label is centred
            out[_g(a, "id")] = (cx - HALF_W, y - PORT_PAD, cx + HALF_W, y + NODE + LABEL_H)
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
        return bx + x + NODE / 2, by + y + NODE / 2
    return x + NODE / 2, y + NODE / 2


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


def _gap(a, b) -> float:
    """Distance between two rectangles (0 when they touch or overlap)."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def _clip_header(fr, members_rect, obstacles):
    """A rectangle around a single action whose header runs into something ABOVE it (rows sit
    closer than a header is tall, e.g. right under a Decisional): start it just below the lowest
    such obstacle instead, as long as that still clears the action itself. The header then
    shares the band beside the icon, where a left-aligned title has room."""
    tops = [o[3] for o in obstacles if _hits(fr, o) and o[3] <= members_rect[1]]
    if not tops:
        return fr
    return (fr[0], max(fr[1], max(tops) + 2.0), fr[2], fr[3])


def fit(boxes: dict, groups: list[tuple], texts: dict | None = None) -> dict:
    """Rectangles for each group, as {key: [rect, ...]}; the first one holds the group's first
    member (in the order given, which is flow order) and carries the title and text.

    `groups` is [(key, [member ids])]; `texts` {key: (title, text)} sizes each header. A group
    whose members sit together gets ONE rectangle. Otherwise the rectangles GROW: start from the
    first unplaced member, add the nearest member whose inclusion keeps the rectangle clear of
    every node outside the group, every rectangle of an earlier group AND every rectangle already
    made for this group, repeat until no member fits, then start the next rectangle. So a group
    becomes as few rectangles as the canvas allows, and its own rectangles never overlap (an
    earlier pairwise-merge version let them, and on a crowded canvas split a group into one
    rectangle per action). Deterministic."""
    texts = texts or {}
    placed: list = []                     # rectangles of earlier groups: never overlapped
    out: dict = {}
    for key, members in groups:
        members = list(dict.fromkeys(m for m in members if m in boxes))
        if not members:
            out[key] = []
            continue
        title, text = texts.get(key, ("", ""))
        mine = set(members)
        foreign = [b for nid, b in boxes.items() if nid not in mine]
        own: list = []                    # this group's rectangles made so far

        def ok(rect):
            return not any(_hits(rect, f) for f in foreign + placed + own)

        def framed(u, cont=False):
            """The rectangle around `u`, its header trimmed when it would run into something
            above (see _clip_header); None when even that leaves it touching something."""
            fr = _frame(u, title + CONT, "") if cont else _frame(u, title, text)
            if not ok(fr):
                fr = _clip_header(fr, u, foreign + placed + own)
            return fr if ok(fr) else None

        whole = framed(_union([boxes[m] for m in members]))
        if whole is not None:
            out[key] = [whole]
            placed.append(whole)
            continue
        left = list(members)
        clusters = []
        while left:
            cluster = [left.pop(0)]
            while True:
                cur = _union([boxes[m] for m in cluster])
                best = None
                for m in left:
                    if framed(_union([cur, boxes[m]]), cont=bool(clusters)) is not None:
                        d = _gap(cur, boxes[m])
                        if best is None or d < best[0]:
                            best = (d, m)
                if best is None:
                    break
                cluster.append(best[1])
                left.remove(best[1])
            clusters.append(cluster)
            u = _union([boxes[m] for m in cluster])
            fr = framed(u, cont=len(clusters) > 1)
            if fr is None:                # a lone member boxed in on every side: best effort
                base = _frame(u, title + CONT, "") if len(clusters) > 1 else _frame(u, title, text)
                fr = _clip_header(base, u, foreign + placed + own)
            own.append(fr)
        out[key] = own
        placed.extend(own)
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


def _neighbours(actions: list[dict]) -> dict:
    """action id -> ids it is wired to (in or out), from the ports on each source action."""
    out: dict = {}
    for a in actions:
        sid = _g(a, "id")
        for p in _g(a, "ports", default=[]) or []:
            d = _g(p, "destinationId")
            src = _g(p, "sourceId") or sid
            if d and src and d != src:
                out.setdefault(src, set()).add(d)
                out.setdefault(d, set()).add(src)
    return out


def membership(actions: list[dict], shapes: list[dict]) -> dict:
    """{shape index: [top-level action ids]} - an action belongs to the shape whose rectangle
    holds its centre. Children of a For Each follow their container.

    When several shapes hold it (rectangles that overlap, as hand-drawn ones or older fits can),
    the area its wired neighbours belong to wins - an action sits in the same area as the actions
    before and after it far more often than not - and only then the smallest rectangle. Smallest
    alone misfiled an action into a neighbouring area's corner on a crowded canvas."""
    by_id = {_g(a, "id"): a for a in actions}
    top = top_level_of(actions)
    rects = [shape_rect(s) for s in shapes]
    titles = [base_title(_g(s, "title", default="") or "") for s in shapes]
    size = [(r[2] - r[0]) * (r[3] - r[1]) for r in rects]
    out: dict = {i: [] for i in range(len(shapes))}
    cands: dict = {}
    for a in actions:
        aid = _g(a, "id")
        if top.get(aid) != aid:
            continue
        cx, cy = centre(a, by_id)
        hit = [i for i, r in enumerate(rects) if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]]
        if hit:
            cands[aid] = hit
    settled = {aid: hit[0] for aid, hit in cands.items() if len(hit) == 1}
    nb = _neighbours(actions)
    for aid, hit in cands.items():
        if aid in settled:
            continue
        near = [titles[settled[n]] for n in nb.get(aid, ()) if n in settled]
        settled[aid] = min(hit, key=lambda i: (-near.count(titles[i]), size[i], i))
    for aid in cands:                     # keep the actions' own order inside each shape
        out[settled[aid]].append(aid)
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
    """Shapes that hold no action - a person's notes on the canvas. Kept as they are. A shape
    titled like one of the areas (its "(cont.)" rectangles included) is part of that area even
    when overlapping rectangles left it no action of its own, so it is not a note: keeping it
    would leave a stale rectangle behind on every re-fit."""
    mem = membership(actions, shapes)
    area_titles = {base_title(_g(s, "title", default="") or "") for i, s in enumerate(shapes)
                   if mem.get(i)}
    return [s for i, s in enumerate(shapes) if not mem.get(i)
            and base_title(_g(s, "title", default="") or "") not in area_titles]


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
