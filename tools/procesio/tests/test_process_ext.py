"""Process builder: For-Each containment + Call/Trigger Subprocess mapping (Tier-2)."""
from __future__ import annotations

import itertools

import pytest

from tools.procesio.dto.process import builder as pb
from tools.procesio.errors import UsageError


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}


def _by_cid(dto):
    return {a["ActionName"]: a for a in dto["Actions"]}


# -- For-Each containment ----------------------------------------------------

def test_foreach_body_is_parented():
    cfg = {"title": "loop", "actions": [
        {"id": "loop", "action": "For Each", "name": "loop"},
        {"id": "body", "action": "Map Data", "name": "body", "parent": "loop"},
    ]}
    dto = pb.build(cfg, _ctx())
    nodes = _by_cid(dto)
    loop, body = nodes["loop"], nodes["body"]
    assert loop["CustomData"]["type"] == "area"
    # the layout engine sizes the For-Each frame to bound its child (not the 48x48 default)
    assert loop["CustomData"]["areaSize"]["width"] >= 48
    assert loop["CustomData"]["areaSize"]["height"] >= 48
    # the body action points at the For-Each node id
    assert body["ParentId"] == loop["Id"]
    # a normal (non-area) node keeps the small node frame
    assert body["CustomData"]["areaSize"]["width"] == 48
    # the built process renders correctly: body inside the loop frame, stored RELATIVE
    from tools.procesio.layout import adapter
    assert adapter.verify_render(dto)["ok"]
    bp = body["CustomData"]["position"]
    asz = loop["CustomData"]["areaSize"]
    assert 0 <= bp["x"] <= asz["width"] and 0 <= bp["y"] <= asz["height"]


def test_non_parented_action_has_null_parent():
    cfg = {"title": "t", "actions": [{"id": "g", "action": "Generate GUID"}]}
    dto = pb.build(cfg, _ctx())
    assert all(a["ParentId"] is None for a in dto["Actions"])


def test_unknown_parent_raises():
    cfg = {"title": "t", "actions": [
        {"id": "a", "action": "Map Data", "parent": "nope"}]}
    with pytest.raises(UsageError):
        pb.build(cfg, _ctx())


def test_nested_foreach_rejected():
    cfg = {"title": "t", "actions": [
        {"id": "outer", "action": "For Each"},
        {"id": "inner", "action": "For Each", "parent": "outer"}]}
    with pytest.raises(UsageError, match="cannot be nested"):
        pb.build(cfg, _ctx())


# -- template default-valued OUTPUT slots (For Each hang) --
# A For Each built from the compact config must carry the two runtime-written output
# slots the designer materialises — `Zero based list index` (61724e="-1") and
# `Action start time` (808b0d=the 2010 sentinel) — or the loop iterates its body ZERO
# times and times out. The builder is binding-driven and used to drop them; it now
# materialises any `direction:2 / type:ignore` template setting carrying a scalar
# default that no binding supplied.
FE_IDX = "99e8766d-d6be-4948-8f57-1f141f61724e"      # Zero based list index -> "-1"
FE_START = "9d2d3483-f04b-48ac-9dea-2ef7ae808b0d"    # Action start time -> 2010-... sentinel


def _params_by_id(action):
    return {p["TabPropertyId"]: p for p in action["Parameters"]}


def test_foreach_materialises_template_default_outputs():
    cfg = {"title": "loop", "variables": [
        {"name": "items", "type": "string", "direction": "process", "isList": True},
        {"name": "cur", "type": "string", "direction": "process"}],
        "actions": [
        {"id": "loop", "action": "For Each", "name": "loop",
         "params": {"In List": {"var": "items"}, "For Each Item": {"var": "cur"},
                    "Action timeout": 120}},
        {"id": "body", "action": "Map Data", "name": "body", "parent": "loop"}]}
    loop = _by_cid(pb.build(cfg, _ctx()))["loop"]
    P = _params_by_id(loop)
    # the three bound params AND the two template-default outputs = 5 total
    assert len(loop["Parameters"]) == 5
    assert FE_IDX in P and P[FE_IDX]["Value"] == "-1" and P[FE_IDX]["Variable"] == []
    assert FE_START in P and str(P[FE_START]["Value"]).startswith("2010-01-01T00:00:00")
    assert P[FE_START]["Variable"] == []


def test_foreach_default_outputs_are_append_only():
    """The materialised outputs are APPENDED after the bound params; the bound
    params keep their identity and order (a transform, not a rewrite)."""
    cfg = {"title": "loop", "variables": [
        {"name": "items", "type": "string", "direction": "process", "isList": True},
        {"name": "cur", "type": "string", "direction": "process"}],
        "actions": [{"id": "loop", "action": "For Each", "name": "loop",
                     "params": {"In List": {"var": "items"}, "For Each Item": {"var": "cur"},
                                "Action timeout": 120}}]}
    loop = _by_cid(pb.build(cfg, _ctx()))["loop"]
    ids = [p["TabPropertyId"] for p in loop["Parameters"]]
    # the two materialised slots come LAST, after the three bound ones
    assert ids[-2:] == [FE_IDX, FE_START] or set(ids[-2:]) == {FE_IDX, FE_START}
    assert ids.index(FE_IDX) >= 3 and ids.index(FE_START) >= 3


def test_paramless_foreach_still_gets_the_two_outputs():
    """Even a For Each the config binds nothing on (empty params -> the early
    return in _action_parameters) still receives the two template defaults."""
    cfg = {"title": "t", "actions": [{"id": "loop", "action": "For Each"}]}
    loop = next(a for a in pb.build(cfg, _ctx())["Actions"]
                if a["CustomData"]["type"] == "area")
    P = _params_by_id(loop)
    assert FE_IDX in P and FE_START in P and len(loop["Parameters"]) == 2


def test_non_foreach_action_gains_no_template_defaults():
    """An action whose template has no defaulted OUTPUT slot gains no OUTPUT default.

    The INPUT half of this guard was SUPERSEDED upstream. `_ensure_input_defaults`
    now materialises a template's input defaults deliberately: an unbound Node
    `Timeout` was dropped, the engine ran it as 00:00:00 and the action died with
    "value ('00:00:00') must be greater than '00:00:00'" (verified live). So a bare
    Node legitimately carries its default "60" now, and the three tests around
    `test_node_unbound_timeout_gets_template_default` pin that behaviour. What must
    still never appear is an OUTPUT-side slot: that is what the For Each fix touched,
    and its blast radius is what this test exists to hold.
    """
    cfg = {"title": "t", "actions": [{"id": "n", "action": "Node", "name": "n"}]}
    n = _by_cid(pb.build(cfg, _ctx()))["n"]
    # the input default 177a57 ("60") is intended; nothing else may be materialised
    assert [p["TabPropertyId"] for p in n["Parameters"]] == [
        "d3e52aab-b9d0-2d42-911e-b0e6de177a57"]


def test_call_subprocess_started_flow_not_doubled():
    """Call Subprocess's a03fe2 started-flow slot (direction 2/ignore, default the
    null guid) is already emitted by _build_subprocess; the materialiser must dedupe
    it, not emit a second copy."""
    cfg = _sub_cfg()
    call = _by_cid(pb.build(cfg, _ctx()))["call"]
    a03 = [p for p in call["Parameters"] if p["TabPropertyId"].endswith("a03fe2")]
    assert len(a03) == 1 and a03[0]["Value"] == pb.NULL_GUID


# -- Call/Trigger Subprocess --------------------------------------------------

TARGET = "b8f1d9e7-906e-46fa-9947-8700d1602d22"
SUB_IN = "0f1e0ceb-6c83-4f5e-b2f3-8b013ae13865"
SUB_OUT = "39d984af-ba12-4e42-82be-327ef9d51648"


def _sub_cfg():
    return {"title": "caller",
            "variables": [{"name": "x", "type": "string"},
                          {"name": "y", "type": "string", "direction": "output"}],
            "actions": [{"id": "call", "action": "Call Subprocess", "name": "call",
                         "subprocess": {"target": TARGET,
                                        "inputs": {SUB_IN: {"var": "x"}},
                                        "outputs": {"y": SUB_OUT}}}]}


def _settings_by_type(node):
    out = {}

    def walk(settings):
        for s in settings or []:
            out.setdefault(s.get("type"), []).append(s)
            if isinstance(s.get("value"), list):
                walk(s["value"])
    for tab in node["CustomData"]["configuration"]:
        walk(tab.get("settings", []))
    return out


def test_subprocess_target_and_maps_build():
    dto = pb.build(_sub_cfg(), _ctx())
    call = _by_cid(dto)["call"]
    params = {p["TabPropertyId"]: p for p in call["Parameters"]}
    # flow-list param carries the target flow id
    flow_vals = [p["Value"] for p in call["Parameters"] if p["Value"] == TARGET]
    assert flow_vals == [TARGET]
    # the designer config exposes the {subprocess, process} rows
    by_type = _settings_by_type(call)
    in_rows = by_type["process-inputs"][0]["value"]
    assert in_rows and in_rows[0]["subprocess"] == SUB_IN  # destination = sub input var
    assert in_rows[0]["process"]                            # parent var id resolved
    out_rows = by_type["process-outputs"][0]["value"]
    assert out_rows and out_rows[0]["subprocess"] == SUB_OUT  # source = sub output var
    assert out_rows[0]["process"]                              # parent (y) var id


def test_subprocess_runtime_rows_match_doc_mapper_shape():
    dto = pb.build(_sub_cfg(), _ctx())
    call = _by_cid(dto)["call"]
    in_param = next(p for p in call["Parameters"]
                    if isinstance(p["Value"], list) and p["Value"]
                    and p["Value"][0].get("destination", {}).get("variableId") == SUB_IN)
    row = in_param["Value"][0]
    assert "source" in row and "destination" in row
    assert row["destination"]["variableId"] == SUB_IN
    assert row["source"]["variable"][0]["variableId"]  # bound to parent var x


def test_subprocess_unknown_output_var_raises():
    cfg = _sub_cfg()
    cfg["actions"][0]["subprocess"]["outputs"] = {"missing": SUB_OUT}
    with pytest.raises(UsageError):
        pb.build(cfg, _ctx())


def test_subprocess_build_passes_config_audit():
    # build() runs _audit_config internally; a clean build means the designer would
    # show the subprocess rows configured (not empty/invalid).
    pb.build(_sub_cfg(), _ctx())  # must not raise


# -- edit-time layout: preserve existing positions + scoped relayout ----------

def _two_action_cfg():
    return {"title": "t", "actions": [
        {"id": "a", "action": "Generate GUID"},
        {"id": "b", "action": "Map Data"}]}


_EXISTING = {"a": {"x": 999, "y": 111}, "b": {"x": 1500, "y": 222},
             "start": {"x": 10, "y": 20}, "stop": {"x": 2000, "y": 300}}


def test_create_uses_engine_layout():
    # a fresh build (no existing positions) lays out left-to-right from the margin
    dto = pb.build(_two_action_cfg(), _ctx())
    assert _by_cid(dto)["Start"]["CustomData"]["position"] == {"x": 80.0, "y": 80.0}


def test_edit_default_preserves_everyone_when_nothing_new():
    ctx = {**_ctx(), "existing_positions": _EXISTING}
    nodes = _by_cid(pb.build(_two_action_cfg(), ctx))
    assert nodes["Generate GUID"]["CustomData"]["position"] == {"x": 999, "y": 111}
    assert nodes["Map Data"]["CustomData"]["position"] == {"x": 1500, "y": 222}
    assert nodes["Start"]["CustomData"]["position"] == {"x": 10, "y": 20}


def test_edit_default_places_new_action_preserves_existing():
    cfg = {"title": "t", "actions": [
        {"id": "a", "action": "Generate GUID"},
        {"id": "c", "action": "Add"}]}            # 'c' is new (not in existing)
    existing = {"a": {"x": 999, "y": 111}, "start": {"x": 10, "y": 20},
                "stop": {"x": 2000, "y": 300}}
    nodes = _by_cid(pb.build(cfg, {**_ctx(), "existing_positions": existing}))
    assert nodes["Generate GUID"]["CustomData"]["position"] == {"x": 999, "y": 111}  # stays
    # the new action got an engine-computed position (not left at the provisional grid)
    assert nodes["Add"]["CustomData"]["position"] != {"x": 999, "y": 111}


def test_edit_relayout_all_does_full_layout():
    ctx = {**_ctx(), "existing_positions": _EXISTING}
    cfg = {**_two_action_cfg(), "relayout": "all"}
    nodes = _by_cid(pb.build(cfg, ctx))
    assert nodes["Start"]["CustomData"]["position"] == {"x": 80.0, "y": 80.0}  # re-tidied


def test_edit_relayout_subset_moves_only_that_action():
    ctx = {**_ctx(), "existing_positions": _EXISTING}
    cfg = {**_two_action_cfg(), "relayout": ["b"]}
    nodes = _by_cid(pb.build(cfg, ctx))
    assert nodes["Generate GUID"]["CustomData"]["position"] == {"x": 999, "y": 111}  # stays
    assert nodes["Start"]["CustomData"]["position"] == {"x": 10, "y": 20}            # stays
    assert nodes["Map Data"]["CustomData"]["position"] != {"x": 1500, "y": 222}      # moved


# -- Shapes / canvasData preservation on edit (canvas-engine PRC-4391) -------

class _CanvasClient:
    """Serves a live flow carrying canvasData (viewport + decorative shapes) and
    captures the PUT DTO, so we can assert an edit preserves it."""
    def __init__(self, canvas):
        self._flow = {"flow": {"variables": [], "actions": [], "canvasData": canvas}}
        self.put_dto = None

    def get(self, path, query=None):
        return self._flow

    def put(self, path, body=None, query=None):
        self.put_dto = body
        return {}

    def post(self, path, body=None, query=None):
        return {"raw_text": ""}


def test_edit_preserves_canvas_shapes(monkeypatch):
    monkeypatch.setattr(pb, "_save_gate", lambda *a, **k: None)   # isolate preservation
    shapes = [{"id": "s1", "kind": "rectangle", "title": "Zone A"}]
    canvas = {"shapes": shapes, "viewport": {"x": 5, "y": 9, "zoom": 1.2}}
    c = _CanvasClient(canvas)
    pb._edit(c, "P1", {"title": "t", "actions": []}, {**_ctx(), "_force": True})
    assert c.put_dto["CanvasData"] == canvas          # shapes + viewport survive the edit


def test_edit_without_canvas_leaves_canvasdata_none(monkeypatch):
    monkeypatch.setattr(pb, "_save_gate", lambda *a, **k: None)
    c = _CanvasClient(None)                             # live flow has no canvasData
    pb._edit(c, "P1", {"title": "t", "actions": []}, {**_ctx(), "_force": True})
    assert c.put_dto["CanvasData"] is None             # nothing to preserve, no crash


# -- input-side template defaults (B-048 cluster 2) --------------------------

def _node_cfg(params):
    return {"title": "n",
            "variables": [{"name": "out", "type": "json", "direction": "output"}],
            "actions": [{"id": "n", "action": "Node", "name": "nd", "params": params}]}


def test_node_unbound_timeout_gets_template_default():
    # An unbound Node Timeout was dropped and the engine ran it as 00:00:00, dying with
    # "value ('00:00:00') must be greater than '00:00:00'". The builder now materialises
    # the template default (60), matching what the designer pre-fills. Verified live.
    dto = pb.build(_node_cfg({"Code": {"template": "return 42;", "vars": []},
                              "Single Result": {"var": "out"}}), _ctx())
    node = _by_cid(dto)["nd"]
    assert "60" in [p.get("Value") for p in node["Parameters"]]


def test_bound_input_default_is_not_overridden_or_duplicated():
    dto = pb.build(_node_cfg({"Code": {"template": "return 1;", "vars": []},
                              "Timeout": 120, "Single Result": {"var": "out"}}), _ctx())
    node = _by_cid(dto)["nd"]
    vals = [p.get("Value") for p in node["Parameters"]]
    assert 120 in vals and "60" not in vals   # user value kept, default not re-added


def test_ensure_input_defaults_subclass_and_skips():
    tpl = {"name": "X", "configuration": [{"settings": [
        {"id": "a", "direction": 1, "type": "number", "value": "7"},         # materialise
        {"id": "b", "direction": 1, "type": "code-editor", "value": "f(){}"},  # skip: code
        {"id": "c", "direction": 1, "type": "text", "value": ""},            # skip: empty
        {"id": "d", "direction": 3, "type": "number", "value": "9"},         # skip: output
        {"id": "e", "direction": 1, "type": "select", "value": "1"},         # materialise
    ]}]}
    got = {p["TabPropertyId"]: p["Value"] for p in pb._ensure_input_defaults(tpl, [])}
    assert got == {"a": "7", "e": "1"}
    # an already-bound property is never re-materialised
    got2 = pb._ensure_input_defaults(tpl, [{"TabPropertyId": "a", "Variable": [], "Value": "99"}])
    assert [p for p in got2 if p["TabPropertyId"] == "a" and p["Value"] == "7"] == []
