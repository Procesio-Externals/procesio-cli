"""Self-documenting processes: create and edit write and keep the process purpose, every
action's purpose (customData.description) and, past 3 actions besides Start/Stop, titled areas
on the canvas (canvasData.shapes), and refuse a save that drops or outdates them."""
from __future__ import annotations

import copy
import itertools

import pytest

from tools.procesio.dto.process import builder as pb
from tools.procesio.dto.process import selfdoc
from tools.procesio.errors import DocumentationMissing
from tools.procesio.flowmodel import docs
from tools.procesio.layout import adapter, areas


def _ctx(**extra):
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}", "_doc": {}, **extra}


def _act(cid, action="To Upper", src="s", out="o", desc=None):
    a = {"id": cid, "action": action, "name": cid,
         "params": {"Input String": {"var": src}, "Result": {"var": out}}}
    if desc is not None:
        a["description"] = desc
    return a


VARS = [{"name": "s", "type": "string", "direction": "input"},
        {"name": "o", "type": "string", "direction": "output"}]


def _config(n=5, with_groups=True, **over):
    acts = [_act(f"a{i}", desc=f"step {i}: uppercases the name for record {i}") for i in range(1, n + 1)]
    cfg = {"title": "doc test", "description": "Normalises a name before it is stored.",
           "variables": copy.deepcopy(VARS), "actions": acts}
    if with_groups and n > 3:
        half = (n + 1) // 2
        cfg["groups"] = [
            {"title": "Prepare", "text": "Cleans the incoming name.", "actions": [f"a{i}" for i in range(1, half + 1)]},
            {"title": "Finish", "text": "Produces the stored form.", "actions": [f"a{i}" for i in range(half + 1, n + 1)]},
        ]
    cfg.update(over)
    return cfg


def _camel(o):
    """The live API answers camelCase; the builder writes PascalCase."""
    if isinstance(o, dict):
        return {(k[:1].lower() + k[1:]): _camel(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_camel(x) for x in o]
    return o


class _Client:
    def __init__(self, flow):
        self.flow = flow
        self.writes = []

    def get(self, path, query=None):
        return {"flow": _camel(self.writes[-1]) if self.writes else self.flow}

    def put(self, path, body=None, query=None):
        self.writes.append(body)
        return {}

    def post(self, path, body=None, query=None):
        return {"raw_text": ""}


def _built(cfg):
    ctx = _ctx()
    dto = pb.build(cfg, ctx)
    return dto, ctx["_doc"]


def _edit(live_dto, cfg, **flags):
    monkey_gate = pb._save_gate
    pb._save_gate = lambda *a, **k: None
    try:
        c = _Client(_camel(live_dto))
        ctx = _ctx(_force=True, **flags)
        pb._edit(c, "P1", cfg, ctx)
        return c.writes[-1], ctx["_doc"]
    finally:
        pb._save_gate = monkey_gate


def _codes(state):
    return {f["code"] for f in state["findings"] if f["severity"] == "error"}


# -- create ------------------------------------------------------------------------------

def test_create_writes_process_and_action_purposes():
    dto, state = _built(_config(3))
    assert dto["Description"] == "Normalises a name before it is stored."
    by = {a["ActionName"]: a for a in dto["Actions"]}
    assert by["a2"]["CustomData"]["description"].startswith("step 2")
    assert "description" not in by["Start"]["CustomData"]          # Start/Stop are not documented
    assert not _codes(state)
    assert dto["CanvasData"] is None                                # 3 actions: no areas needed


def test_create_without_any_documentation_reports_every_gap():
    cfg = {"title": "t", "variables": VARS, "actions": [_act(f"a{i}") for i in range(4)]}
    _, state = _built(cfg)
    assert {"PROCESS_DESCRIPTION_MISSING", "ACTION_DESCRIPTION_MISSING", "AREAS_MISSING"} <= _codes(state)
    with pytest.raises(DocumentationMissing) as ei:
        selfdoc.gate({"_doc": state})
    assert ei.value.report["documented"] is False
    # the escape hatch saves and reports
    assert selfdoc.gate({"_doc": state, "_allow_undocumented": True})["documented"] is False


def test_stock_caption_counts_as_undocumented():
    cap = selfdoc.stock_captions()["to upper"]
    cfg = _config(2)
    cfg["actions"][0]["description"] = cap
    _, state = _built(cfg)
    assert "ACTION_DESCRIPTION_GENERIC" in _codes(state)
    assert selfdoc.is_generic("To Upper", "To Upper")              # the template name says nothing


def test_more_than_three_actions_need_every_action_in_an_area():
    cfg = _config(5)
    cfg["groups"][1]["actions"].pop()                               # a5 left out
    _, state = _built(cfg)
    assert _codes(state) == {"ACTION_UNGROUPED"}


def test_areas_become_shapes_behind_their_members_and_cover_no_one_else():
    dto, state = _built(_config(8))
    assert not _codes(state)
    shapes = dto["CanvasData"]["shapes"]
    assert shapes and all(s["kind"] == 0 for s in shapes)
    assert all(areas.SHAPE_MIN <= s["zIndex"] <= areas.SHAPE_MAX for s in shapes)
    assert shapes[0]["title"] == "Prepare" and shapes[0]["text"] == "Cleans the incoming name."
    flow = _camel(dto)
    groups = {g["title"]: g for g in areas.groups_from_shapes(flow["actions"], shapes)}
    name = {a["id"]: a["actionName"] for a in flow["actions"]}
    assert sorted(name[m] for m in groups["Prepare"]["members"]) == ["a1", "a2", "a3", "a4"]
    assert sorted(name[m] for m in groups["Finish"]["members"]) == ["a5", "a6", "a7", "a8"]
    # no rectangle holds a node that is not its member (Start/Stop included)
    boxes = areas.node_boxes(flow["actions"])
    for s in shapes:
        r = areas.shape_rect(s)
        holders = {aid for aid, b in boxes.items() if areas._hits(r, b)}
        mine = set(groups[areas.base_title(s["title"])]["members"])
        assert holders <= mine, (s["title"], holders - mine)


def test_groups_are_checked():
    with pytest.raises(Exception, match="not an action id"):
        _built(_config(5, with_groups=False, groups=[{"title": "x", "text": "y", "actions": ["start"]}]))
    with pytest.raises(Exception, match="two areas"):
        _built(_config(5, with_groups=False, groups=[{"title": "x", "text": "y", "actions": ["a1"]},
                                                 {"title": "z", "text": "y", "actions": ["a1"]}]))


# -- edit ---------------------------------------------------------------------------------

def _strip_docs(cfg):
    cfg = copy.deepcopy(cfg)
    cfg.pop("description", None)
    cfg.pop("groups", None)
    for a in cfg["actions"]:
        a.pop("description", None)
    return cfg


def test_edit_keeps_purposes_and_areas_the_config_does_not_restate():
    live, _ = _built(_config(5))
    put, state = _edit(live, _strip_docs(_config(5)))
    assert not _codes(state)
    assert put["Description"] == "Normalises a name before it is stored."
    assert {a["ActionName"]: a["CustomData"].get("description") for a in put["Actions"]}["a4"].startswith("step 4")
    assert [s["title"] for s in put["CanvasData"]["shapes"]] == [s["title"] for s in live["CanvasData"]["shapes"]]
    assert {s["id"] for s in put["CanvasData"]["shapes"]} == {s["id"] for s in live["CanvasData"]["shapes"]}


def test_edit_refuses_an_action_that_changed_without_a_restated_purpose():
    live, _ = _built(_config(5))
    cfg = _strip_docs(_config(5))
    cfg["actions"][1]["params"]["Input String"] = "literal text"     # a2 now does something else
    with pytest.raises(DocumentationMissing) as ei:
        _edit(live, cfg)
    stale = [f for f in ei.value.report["findings"] if f["code"] == "ACTION_DESCRIPTION_STALE"]
    assert [f["action"] for f in stale] == ["a2"]
    cfg["actions"][1]["description"] = "uppercases a fixed label instead of the input"
    put, state = _edit(live, cfg)
    assert not _codes(state)
    assert {a["ActionName"]: a["CustomData"].get("description") for a in put["Actions"]}["a2"] == \
        "uppercases a fixed label instead of the input"


def test_edit_new_action_needs_a_purpose_and_an_area():
    live, _ = _built(_config(5))
    cfg = _strip_docs(_config(5))
    cfg["actions"].append(_act("a6", action="To Lower"))
    with pytest.raises(DocumentationMissing) as ei:
        _edit(live, cfg)
    assert {"ACTION_DESCRIPTION_MISSING", "ACTION_UNGROUPED"} <= {f["code"] for f in ei.value.report["findings"]}
    cfg["actions"][-1]["description"] = "lower-cases a copy for the search index"
    cfg["groups"] = _config(5)["groups"]
    cfg["groups"][1]["actions"].append("a6")
    put, state = _edit(live, cfg)
    assert not _codes(state)


def test_edit_deleting_an_area_member_asks_to_restate_the_area():
    live, _ = _built(_config(5))
    cfg = _strip_docs(_config(5))
    cfg["actions"] = [a for a in cfg["actions"] if a["id"] != "a5"]
    with pytest.raises(DocumentationMissing) as ei:
        _edit(live, cfg, _allow_remove=True)
    assert "AREA_MEMBERS_CHANGED" in {f["code"] for f in ei.value.report["findings"]}
    cfg["groups"] = [{"title": "Prepare", "text": "Cleans the incoming name.", "actions": ["a1", "a2", "a3"]},
                     {"title": "Finish", "text": "Produces the stored form.", "actions": ["a4"]}]
    put, state = _edit(live, cfg, _allow_remove=True)
    assert not _codes(state)


def test_edit_changes_the_process_purpose():
    live, _ = _built(_config(3))
    cfg = _strip_docs(_config(3))
    cfg["description"] = "Now also used by the import job."
    put, _ = _edit(live, cfg)
    assert put["Description"] == "Now also used by the import job."


def test_edit_keeps_a_persons_free_notes():
    live, _ = _built(_config(5))
    note = {"id": "n1", "kind": 0, "position": {"x": -5000, "y": -5000},
            "dimension": {"width": 100, "height": 50}, "title": "TODO", "text": "ask finance"}
    live["CanvasData"]["shapes"].append(note)
    put, _ = _edit(live, _strip_docs(_config(5)))
    assert note in put["CanvasData"]["shapes"]


# -- readers + layout --------------------------------------------------------------------

def test_reader_returns_the_documented_intent():
    dto, _ = _built(_config(5))
    d = docs.read(_camel(dto))
    assert d["documented"] and d["purpose"].startswith("Normalises")
    assert [a["title"] for a in d["areas"]] == ["Prepare", "Finish"]
    assert d["coverage"] == {"actions": 5, "described": 5, "grouped": 5, "areas_required": True}
    md = docs.render_markdown(d)
    assert "**Purpose:**" in md and "**Prepare**" in md


def test_relayout_moves_the_areas_with_their_actions():
    dto, _ = _built(_config(8))
    flow = _camel(dto)
    for a in flow["actions"]:                                        # scatter the canvas
        a["customData"]["position"] = {"x": a["customData"]["position"]["x"] + 3000,
                                       "y": a["customData"]["position"]["y"] + 900}
    before = areas.groups_from_shapes(flow["actions"], flow["canvasData"]["shapes"])
    assert before == []                                              # the actions left their areas
    # a re-layout re-reads membership on the input positions, so put the areas back over them
    flow["canvasData"]["shapes"] = areas.refit(_camel(dto)["actions"], flow["actions"],
                                               flow["canvasData"]["shapes"], lambda: "x")
    res = adapter.layout_flow({"Actions": flow["actions"], "CanvasData": flow["canvasData"]}, cluster=True)
    out = res["bundle"]
    groups = {g["title"]: len(g["members"]) for g in areas.groups_from_shapes(out["Actions"], out["CanvasData"]["shapes"])}
    assert groups == {"Prepare": 4, "Finish": 4}


def test_platform_reformatting_a_setting_does_not_outdate_a_purpose():
    """The platform rewrites a stored timestamp ("...00Z" -> "...00.0000000Z") and may return a
    number as a string; neither is a change in what the action does (seen live on For Each)."""
    a = {"TemplateId": "t", "Parameters": [{"TabPropertyId": "p", "Value": "2010-01-01T00:00:00Z"},
                                           {"TabPropertyId": "q", "Value": 120}]}
    b = {"templateId": "t", "parameters": [{"tabPropertyId": "p", "value": "2010-01-01T00:00:00.0000000Z"},
                                           {"tabPropertyId": "q", "value": "120"}]}
    assert selfdoc.fingerprint(a, {}) == selfdoc.fingerprint(b, {})
    b["parameters"][1]["value"] = "121"
    assert selfdoc.fingerprint(a, {}) != selfdoc.fingerprint(b, {})


# -- crowded canvases (a long Decisional branch next to a short one) ---------------------

def _long_branch_config():
    """A 6-action run into a Decisional whose condition branch is 11 actions long and whose
    default branch is one action, both meeting at a Join: the shape that made the fan-lanes
    pass squeeze the long branch to 66 px per action and the areas fall apart."""
    acts = [_act(f"a{i}", desc=f"step a{i} of the check") for i in range(1, 7)]
    acts.append({"id": "dec", "action": "Decisional", "name": "dec", "description": "Routes a known caller.",
                 "branches": [{"name": "known", "to": "b1", "when": [{"left": {"var": "s"}, "op": "IS_NOT_EMPTY"}]},
                              {"to": "r", "default": True}]})
    acts += [_act(f"b{i}", desc=f"step b{i} of the save") for i in range(1, 12)]
    acts.append(_act("r", action="To Lower", desc="Answers that the entry is locked."))
    acts.append({"id": "join", "action": "Join", "name": "join", "description": "Both paths end here."})
    edges = ([["start", "a1"]] + [[f"a{i}", f"a{i + 1}"] for i in range(1, 6)] + [["a6", "dec"]]
             + [[f"b{i}", f"b{i + 1}"] for i in range(1, 11)] + [["b11", "join"], ["r", "join"], ["join", "stop"]])
    groups = [{"title": "Check", "text": "Checks the caller.", "actions": [f"a{i}" for i in range(1, 7)] + ["dec", "r"]},
              {"title": "Save", "text": "Saves the entry.", "actions": ["b1", "b2", "b3"]},
              {"title": "Rank", "text": "Ranks the others.", "actions": ["b4", "b5", "b6", "b7"]},
              {"title": "Remember", "text": "Remembers what was shown.", "actions": ["b8", "b9", "b10", "b11", "join"]}]
    return {"title": "crowded", "description": "Saves an entry and ranks the others.",
            "variables": copy.deepcopy(VARS), "actions": acts, "edges": edges, "groups": groups}


def test_a_long_branch_keeps_a_column_per_action():
    dto, state = _built(_long_branch_config())
    pos = {a["ActionName"]: a["CustomData"]["position"] for a in dto["Actions"]}
    crowded = [(m, n) for m, n in itertools.combinations(sorted(pos), 2)
               if abs(pos[m]["y"] - pos[n]["y"]) < 48 and abs(pos[m]["x"] - pos[n]["x"]) < 120]
    assert not crowded, crowded                     # names under the icons cannot collide
    assert not _codes(state)


def test_areas_on_a_crowded_canvas_stay_few_and_never_overlap():
    dto, _ = _built(_long_branch_config())
    flow = _camel(dto)
    shapes = flow["canvasData"]["shapes"]
    rects = [areas.shape_rect(s) for s in shapes]
    assert not [(shapes[i]["title"], shapes[j]["title"])
                for i, j in itertools.combinations(range(len(shapes)), 2) if areas._hits(rects[i], rects[j])]
    groups = {g["title"]: g for g in areas.groups_from_shapes(flow["actions"], shapes)}
    # a run of consecutive actions stays one rectangle; the default branch's lone action lands
    # far from its Decisional here, so "Check" is scattered and only that area is reported
    assert len(groups["Save"]["shape_ids"]) == 1
    assert max(len(g["shape_ids"]) for g in groups.values()) <= 3
    frag = [f for f in docs.read(flow)["findings"] if f["code"] == "AREA_FRAGMENTED"]
    assert [f["area"] for f in frag] == ["Check"]
    name = {a["id"]: a["actionName"] for a in flow["actions"]}
    assert sorted(name[m] for m in groups["Save"]["members"]) == ["b1", "b2", "b3"]
    boxes = areas.node_boxes(flow["actions"])
    for s, r in zip(shapes, rects):                 # no rectangle covers another area's action
        mine = set(groups[areas.base_title(s["title"])]["members"])
        assert {i for i, b in boxes.items() if areas._hits(r, b)} <= mine, s["title"]


def test_fan_lanes_refuse_to_squeeze_a_branch():
    """Directly on the post-pass: a split->merge pair whose long lane would get less than one
    column per action is left as the engine placed it."""
    from types import SimpleNamespace as N
    ids = ["d"] + [f"b{i}" for i in range(11)] + ["r", "j"]
    nodes = [N(id=i, shape="diamond" if i == "d" else "square", parent_id=None) for i in ids]
    chain = ["d"] + [f"b{i}" for i in range(11)] + ["j"]
    edges = [N(source=chain[k], dest=chain[k + 1], type=0) for k in range(len(chain) - 1)]
    edges += [N(source="d", dest="r", type=0), N(source="r", dest="j", type=0)]
    P = {i: {"x": 0.0, "y": 0.0} for i in ids}
    P["d"], P["j"] = {"x": 0.0, "y": 0.0}, {"x": 800.0, "y": 0.0}
    before = {k: dict(v) for k, v in P.items()}
    out = adapter._apply_fan_lanes(P, N(nodes=nodes, edges=edges))
    assert out == before


def test_overlapping_rectangles_file_an_action_with_its_neighbours():
    """Two overlapping rectangles both hold an action: it goes to the area its wired
    neighbours are in, not to the smaller rectangle."""
    def act(i, x, y, to=None):
        return {"id": i, "actionTemplateName": "To Upper", "customData": {"type": "square", "position": {"x": x, "y": y}},
                "ports": [{"sourceId": i, "destinationId": to}] if to else []}
    acts = [act("p", 0, 0, "m"), act("m", 160, 0, "n"), act("n", 320, 0), act("o", 200, 200)]
    big = {"id": "A", "kind": 0, "title": "Mine", "position": {"x": -60, "y": -60}, "dimension": {"width": 460, "height": 160}}
    small = {"id": "B", "kind": 0, "title": "Other", "position": {"x": 150, "y": -20}, "dimension": {"width": 140, "height": 300}}
    groups = {g["title"]: g["members"] for g in areas.groups_from_shapes(acts, [big, small])}
    assert groups["Mine"] == ["p", "m", "n"] and groups["Other"] == ["o"]


def test_a_rectangle_left_empty_is_part_of_its_area_not_a_note():
    def act(i, x, y):
        return {"id": i, "actionTemplateName": "To Upper", "customData": {"type": "square", "position": {"x": x, "y": y}}}
    acts = [act("p", 0, 0), act("q", 160, 0)]
    outer = {"id": "A", "kind": 0, "title": "Save", "position": {"x": -60, "y": -60}, "dimension": {"width": 400, "height": 200}}
    inner = {"id": "B", "kind": 0, "title": "Save (cont.)", "position": {"x": -40, "y": -40}, "dimension": {"width": 380, "height": 160}}
    note = {"id": "N", "kind": 0, "title": "TODO", "position": {"x": 900, "y": 900}, "dimension": {"width": 50, "height": 50}}
    assert areas.free_shapes(acts, [outer, inner, note]) == [note]
