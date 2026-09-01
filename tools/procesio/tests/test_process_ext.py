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
