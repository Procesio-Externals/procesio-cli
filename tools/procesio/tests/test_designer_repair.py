"""Rebuilding the designer layer a raw PUT left out (dto/process/normalize.rebuild_missing_designer_config).

A PROCESIO action stores its settings twice: `parameters[]` for the runtime and
`customData.configuration` for the designer. A node written without the second one still runs, but
the designer cannot open the process and the instance view cannot draw it. The repair fills that
layer from the node's template and its runtime parameters and must leave everything else alone.
"""
from __future__ import annotations

import copy

import pytest

from tools.procesio import client as cl
from tools.procesio.dto.process import builder as b
from tools.procesio.dto.process.normalize import (align_node_shapes, designer_render_problems,
                                                   rebuild_missing_designer_config)
from tools.procesio.errors import DesignerUnrenderable, classify

NODE_TPL = "e0fc20c3-e333-554c-a062-f64894db51dd"        # Node (JavaScript)
DECISIONAL_TPL = "f5dcbb04-253d-4061-99a1-9b2822c2e6d2"
JOIN_TPL = "fb6a9d14-dd15-420d-a2b2-fc637c0c37c6"
CODE = "1e6a5523-2091-6c4c-94ac-c7984074673d"
CASES = "11d4044a-8586-47f6-b3ce-1cae5da40f30"
DEFAULT = "11d4044a-8586-47f6-b3ce-1cae5da40f45"
VAR = "aaaaaaaa-0000-4000-8000-000000000001"


def _cd(name, configuration=None):
    cd = {"type": "square", "name": name, "icon": "", "position": {"x": 0, "y": 0},
          "inputPorts": 1, "outputPorts": 1, "wasDropped": True, "areaSize": {}}
    if configuration is not None:
        cd["configuration"] = configuration
    return cd


def _flow() -> dict:
    return {"id": "flow-1", "variables": [{"id": VAR, "name": "flag"}], "actions": [
        {"id": "node", "templateId": NODE_TPL, "actionName": "Build row", "customData": _cd("Build row"),
         "parameters": [{"tabPropertyId": CODE, "value": "return `<%0%>`;",
                         "variable": [{"id": 0, "variableId": VAR, "attribute": None}]}]},
        {"id": "dec", "templateId": DECISIONAL_TPL, "actionName": "Flag set?", "customData": _cd("Flag set?"),
         "parameters": [
             {"tabPropertyId": CASES, "variable": [], "value": [
                 {"id": 0, "actionid": "node", "condition": [
                     {"id": 0, "operator": "IS_TRUE", "logicOperator": 0,
                      "leftOperator": {"value": "<%0%>", "variable": [{"id": 0, "variableId": VAR}]},
                      "rightOperator": {}}]}]},
             {"tabPropertyId": DEFAULT, "variable": [], "value": "join"}]},
        {"id": "join", "templateId": JOIN_TPL, "actionName": "Join", "customData": _cd("Join"), "parameters": []},
        {"id": "ok", "templateId": NODE_TPL, "actionName": "Healthy", "parameters": [],
         "customData": _cd("Healthy", configuration=[{"settings": [{"id": CODE, "value": "keep me"}]}])},
        {"id": "odd", "templateId": "00000000-dead-beef-0000-000000000000", "actionName": "Unknown",
         "customData": _cd("Unknown"), "parameters": []},
    ]}


def _setting(action, sid):
    for tab in action["customData"]["configuration"]:
        for s in tab.get("settings") or []:
            if s.get("id") == sid:
                return s
    raise AssertionError(f"setting {sid} missing")


def _by_id(flow):
    return {a["id"]: a for a in flow["actions"]}


def test_a_node_without_designer_layer_gets_one_that_mirrors_its_runtime():
    flow = _flow()
    report = rebuild_missing_designer_config(flow, b.catalog_index())
    acts = _by_id(flow)

    assert report["changed"] is True
    assert {r["id"] for r in report["repaired"]} == {"node", "dec", "join"}
    # the designer stores the variable's id where the runtime holds a <%N%> placeholder
    assert _setting(acts["node"], CODE)["value"] == f"return `{VAR}`;"
    case = _setting(acts["dec"], CASES)["value"][0]
    assert case["target"] == "node"
    assert case["condition"][0]["leftOperator"]["value"] == VAR


def test_a_join_without_the_key_gets_an_empty_configuration():
    """A Join template has nothing to show, but the canvas engine maps over every node's
    configuration: a MISSING key throws and the designer loads forever with no error."""
    flow = _flow()
    rebuild_missing_designer_config(flow, b.catalog_index())

    assert _by_id(flow)["join"]["customData"]["configuration"] == []


def test_runtime_healthy_and_unknown_nodes_are_left_alone():
    flow = _flow()
    before = copy.deepcopy(flow)
    report = rebuild_missing_designer_config(flow, b.catalog_index())
    acts, old = _by_id(flow), _by_id(before)

    for aid in ("node", "dec", "join"):  # the runtime layer is never touched
        assert acts[aid]["parameters"] == old[aid]["parameters"]
    assert acts["ok"]["customData"] == old["ok"]["customData"], "an existing designer layer is kept"
    assert "configuration" not in acts["odd"]["customData"]
    assert report["skipped"] == [{"id": "odd", "name": "Unknown", "why": "template_not_in_catalog",
                                  "templateId": "00000000-dead-beef-0000-000000000000"}]


def test_only_limits_the_repair_to_the_named_nodes():
    flow = _flow()
    report = rebuild_missing_designer_config(flow, b.catalog_index(), only={"flag set?"})
    acts = _by_id(flow)

    assert [r["id"] for r in report["repaired"]] == ["dec"]
    assert "configuration" not in acts["node"]["customData"]


def test_unknown_shapes_and_wrong_port_counts_are_set_back_to_the_template():
    """A Decisional stored as 'rhombus' (a shape the canvas engine does not know) hangs the
    designer with no error; a Join with one input cannot take its second line."""
    idx = b.catalog_index()
    flow = _flow()
    acts = _by_id(flow)
    acts["dec"]["customData"].update({"type": "rhombus", "outputPorts": 2})
    acts["join"]["customData"].update({"type": "square", "inputPorts": 1})

    report = align_node_shapes(flow, idx)

    assert acts["dec"]["customData"]["type"] == idx[DECISIONAL_TPL]["shape"] == "diamond"
    assert acts["dec"]["customData"]["outputPorts"] == idx[DECISIONAL_TPL]["outputPorts"]
    assert acts["join"]["customData"]["type"] == idx[JOIN_TPL]["shape"]
    assert acts["join"]["customData"]["inputPorts"] == idx[JOIN_TPL]["inputPorts"]
    assert {r["id"] for r in report["aligned"]} == {"dec", "join"}
    assert report["aligned"][0]["fields"]["type"] == ["rhombus", "diamond"]


def test_a_node_that_already_matches_its_template_is_not_touched():
    idx = b.catalog_index()
    flow = _flow()
    for a in flow["actions"]:
        tpl = idx.get(a["templateId"])
        if tpl:
            a["customData"].update({"type": tpl.get("shape") or "square",
                                    "inputPorts": tpl.get("inputPorts"), "outputPorts": tpl.get("outputPorts")})
    before = copy.deepcopy(flow)

    report = align_node_shapes(flow, idx)

    assert report == {"changed": False, "aligned": []}
    assert flow == before


def test_the_repair_is_idempotent():
    flow = _flow()
    rebuild_missing_designer_config(flow, b.catalog_index())
    once = copy.deepcopy(flow)
    report = rebuild_missing_designer_config(flow, b.catalog_index())

    assert report["changed"] is False
    assert flow == once


# -- the save guard: never let such a flow land again ---------------------------------------------

def _repaired() -> dict:
    flow = _flow()
    flow["actions"] = [a for a in flow["actions"] if a["id"] != "odd"]
    rebuild_missing_designer_config(flow, b.catalog_index())
    align_node_shapes(flow, b.catalog_index())
    return flow


def test_render_problems_name_the_nodes_the_designer_cannot_draw():
    flow = _flow()
    flow["actions"][1]["customData"]["type"] = "rhombus"

    problems = designer_render_problems(flow)

    assert {"id": "join", "name": "Join", "why": "no configuration key"} in problems
    assert {"id": "dec", "name": "Flag set?", "why": "unknown shape 'rhombus'"} in problems
    assert designer_render_problems(_repaired()) == []


def test_render_problems_read_the_builder_pascal_case_shape():
    dto = {"Actions": [{"Id": "x", "ActionName": "Join", "CustomData": {"type": "circle"}}]}

    assert designer_render_problems(dto) == [{"id": "x", "name": "Join", "why": "no configuration key"}]


def _offline_client(monkeypatch):
    c = cl.ProcesioClient(profile={"name": "test"})
    sent = []
    monkeypatch.setattr(cl.config, "web_base", lambda profile: "https://example.invalid")
    monkeypatch.setattr(c, "_send_once", lambda *a, **k: (sent.append(a[0]), (200, {}))[1])
    return c, sent


def test_the_client_refuses_to_save_a_flow_the_designer_cannot_draw(monkeypatch):
    c, sent = _offline_client(monkeypatch)

    with pytest.raises(DesignerUnrenderable) as err:
        c.put("/api/Projects", _flow())

    assert sent == [], "nothing may reach the API"
    code, _msg, details, exit_code = classify(err.value)
    assert (code, exit_code) == ("designer_unrenderable", 2)
    assert "node-repair-designer" in details["fix"]
    assert any(n["name"] == "Join" for n in details["nodes"])


def test_the_client_saves_a_repaired_flow_and_leaves_other_calls_alone(monkeypatch):
    c, sent = _offline_client(monkeypatch)

    c.put("/api/Projects", _repaired())
    c.post("/api/Projects/validate", _flow())   # validating is not saving
    c.get("/api/Projects/flow-1")

    assert sent == ["PUT", "POST", "GET"]
