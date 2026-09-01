"""Tier-3 parity hardening: credential binding + locked builder invariants.

The invariants (shape inherited from the action; decisional fan-out unlimited) are already
correct in the builder — these tests lock them so a future change can't silently break them.
"""
from __future__ import annotations

import itertools

import pytest

from tools.procesio.dto.process import builder as pb
from tools.procesio.errors import UsageError


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}


def _by_name(dto):
    return {a["ActionName"]: a for a in dto["Actions"]}


def _cfg_setting(node, label):
    def walk(settings):
        for s in settings or []:
            if str(s.get("label", "")).lower() == label.lower():
                return s
            if isinstance(s.get("value"), list):
                r = walk(s["value"])
                if r:
                    return r
    for tab in node["CustomData"]["configuration"]:
        r = walk(tab.get("settings", []))
        if r:
            return r


def test_number_setting_designer_value_is_string():
    """A DESIGNER number input binds a STRING; a numeric config value renders EMPTY
    and the FE range-check then reads Number("")=0 -> "value between min and max"
    (even though the RUNTIME Parameter, which stays numeric, executes fine). So the
    builder must mirror number-type settings (e.g. a Node's Timeout) as strings."""
    cfg = {"title": "t",
           "variables": [{"name": "x", "type": "json", "direction": "input"},
                         {"name": "r", "type": "json", "direction": "output"}],
           "actions": [{"id": "n", "action": "Node", "name": "n",
                        "params": {"Code": {"template": "return <%0%>;", "vars": ["x"]},
                                   "Timeout": 60, "Single Result": {"var": "r"}}}]}
    node = _by_name(pb.build(cfg, _ctx()))["n"]
    s = _cfg_setting(node, "Timeout")
    assert s["value"] == "60" and isinstance(s["value"], str)   # designer: string
    assert any(p["Value"] == 60 for p in node["Parameters"])    # runtime: numeric, unchanged


# -- credential binding -------------------------------------------------------

CRED_GID = "45a1dd18-9d06-47cf-8a7b-7732447264af"


def _cred_setting(node):
    for tab in node["CustomData"]["configuration"]:
        for s in tab.get("settings", []):
            if s.get("type") == "credentials":
                return s
    return None


def test_credential_binding_sets_gid_and_keeps_template():
    cfg = {"title": "q", "variables": [{"name": "q", "type": "string"}],
           "actions": [{"id": "eq", "action": "Execute Query", "name": "eq",
                        "params": {"Select Database Server": {"credential": CRED_GID},
                                   "Query": {"var": "q"}}}]}
    dto = pb.build(cfg, _ctx())
    eq = _by_name(dto)["eq"]
    # runtime Parameter carries the instance gid
    cred_params = [p for p in eq["Parameters"] if p["Value"] == CRED_GID]
    assert len(cred_params) == 1 and cred_params[0]["Variable"] == []
    # designer config: value = gid AND the credential TEMPLATE id is preserved
    s = _cred_setting(eq)
    assert s["value"] == CRED_GID
    assert s.get("credentialsTemplateId")  # the credential TYPE, from the catalog


def test_credential_binding_rejects_non_guid():
    cfg = {"title": "q", "actions": [
        {"id": "eq", "action": "Execute Query",
         "params": {"Select Database Server": {"credential": "not-a-guid"}}}]}
    with pytest.raises(UsageError, match="credential"):
        pb.build(cfg, _ctx())


# -- invariant: node shape is action-dictated, never hardcoded ---------------

def test_node_shape_inherited_from_action():
    """Every node's CustomData.type equals its catalog template's `shape` — i.e. the
    shape is inherited from the action, never assigned per action by the builder."""
    cfg = {"title": "shapes", "variables": [{"name": "n", "type": "integer"}],
           "actions": [
               {"id": "g", "action": "Generate GUID"},
               {"id": "loop", "action": "For Each"},
               {"id": "d", "action": "Decisional",
                "branches": [{"to": "g", "when": [{"left": {"var": "n"}, "op": "EQUALS", "right": 1}]},
                             {"to": "loop", "default": True}]},
           ]}
    dto = pb.build(cfg, _ctx())
    catalog = pb.catalog_index()
    for a in dto["Actions"]:
        tpl = catalog.get((a["ActionTemplateName"] or "").strip().lower())
        assert tpl is not None, f"no catalog template for {a['ActionTemplateName']!r}"
        assert a["CustomData"]["type"] == (tpl.get("shape") or "square"), \
            f"{a['ActionTemplateName']} shape not inherited from catalog"
    # and the catalog genuinely carries distinct shapes (so the test isn't vacuous)
    shapes = {a["CustomData"]["type"] for a in dto["Actions"]}
    assert {"diamond", "area"} <= shapes


def test_decisional_fanout_is_unlimited():
    # 6 cases + a default — must all be emitted (no 2-5 cap)
    targets = [{"id": f"t{i}", "action": "Generate GUID"} for i in range(6)]
    branches = [{"to": f"t{i}", "when": [{"left": {"var": "n"}, "op": "EQUALS", "right": i}]}
                for i in range(6)]
    branches.append({"to": "t0", "default": True})
    cfg = {"title": "fan", "variables": [{"name": "n", "type": "integer"}],
           "actions": [{"id": "d", "action": "Decisional", "branches": branches}] + targets}
    dto = pb.build(cfg, _ctx())
    d = _by_name(dto)["Decisional"]
    cases_param = next(p for p in d["Parameters"] if isinstance(p["Value"], list)
                       and p["Value"] and "actionid" in p["Value"][0])
    assert len(cases_param["Value"]) == 6  # all six cases survive (no 2-5 cap)
    # at least the 6 case ports + 1 default port leave the decisional
    assert sum(1 for pt in d["Ports"] if pt["SourceId"] == d["Id"]) >= 7


def test_subprocess_literal_input_hoisted_to_variable():
    # A LITERAL subprocess input must be hoisted to a synthetic process variable (default =
    # the literal) and the binding rewritten to {var: ...}, so the mapping's parent side is
    # a real variable id (a raw literal there makes the designer reject a Trigger Subprocess
    # as "Mapping of required subprocess variable (X) is missing", blocking the launch).
    cfg = {"title": "sub", "variables": [{"name": "f", "model": "FileDataModel"}],
           "actions": [{"id": "t", "action": "Trigger Subprocess", "subprocess": {
               "target": "d7af1675-abe3-4193-a8e6-ef6aa501f78c",
               "inputs": {"S1": {"value": "hello.pdf"}, "S2": {"var": "f"}, "S3": 42},
               "outputs": {}}}]}
    out = pb._hoist_subprocess_literals(cfg)
    inputs = out["actions"][0]["subprocess"]["inputs"]
    # both literals ({"value":...} and a bare scalar) became {var: <synthetic>}; the var stays
    assert set(inputs["S1"].keys()) == {"var"} and set(inputs["S3"].keys()) == {"var"}
    assert inputs["S2"] == {"var": "f"}                       # var binding untouched
    syn = {v["name"]: v for v in out["variables"] if v["name"].startswith("_sublit")}
    assert len(syn) == 2
    assert syn[inputs["S1"]["var"]]["default"] == "hello.pdf"
    assert syn[inputs["S1"]["var"]]["type"] == "string"
    assert syn[inputs["S3"]["var"]]["default"] == 42
    assert syn[inputs["S3"]["var"]]["type"] == "integer"
    # the original config is not mutated
    assert cfg["actions"][0]["subprocess"]["inputs"]["S1"] == {"value": "hello.pdf"}


def test_subprocess_no_literals_is_noop():
    cfg = {"title": "sub", "variables": [{"name": "f", "model": "FileDataModel"}],
           "actions": [{"id": "t", "action": "Call Subprocess", "subprocess": {
               "target": "x", "inputs": {"S1": {"var": "f"}}, "outputs": {}}}]}
    assert pb._hoist_subprocess_literals(cfg) is cfg          # unchanged, same object
