"""Tests for the offline flow digest (flowmodel/digest.py + the flow-digest action)."""
from __future__ import annotations

import json
import types

from tools.procesio.flowmodel import digest
from tools.procesio.handlers import flowgraph

SUB = "11111111-1111-1111-1111-111111111111"
PARENT = "22222222-2222-2222-2222-222222222222"
V_IN = "33333333-3333-3333-3333-333333333333"
V_OUT = "44444444-4444-4444-4444-444444444444"
CRED = "55555555-5555-5555-5555-555555555555"


def _flow(fid, title, actions, variables=()):
    return {"id": fid, "title": title, "variables": list(variables), "actions": actions}


def _parent():
    return _flow(PARENT, "Parent", [
        {"id": "s", "actionTemplateName": "Start", "actionName": "Start",
         "ports": [{"destinationId": "n", "type": 0}]},
        {"id": "n", "actionTemplateName": "Node", "actionName": "Build rows",
         "customData": {"configuration": [{"settings": [{"id": "p-code", "label": "Code"}]}]},
         "parameters": [{"tabPropertyId": "p-code", "value": "const x = <%0%>;\nreturn x;",
                         "variable": [{"id": 0, "variableId": V_IN}]}],
         "ports": [{"destinationId": "q", "type": 0}, {"destinationId": "e", "type": 1}]},
        {"id": "q", "actionTemplateName": "Execute Query", "actionName": "Save",
         "parameters": [{"tabPropertyId": "p-sql", "value": "SELECT * FROM t WHERE a = <%0%>",
                         "variable": [{"id": 0, "variableId": V_IN}]},
                        {"tabPropertyId": "p-cred", "value": CRED, "variable": []}],
         "ports": [{"destinationId": "c", "type": 0}]},
        {"id": "c", "actionTemplateName": "Call Subprocess", "actionName": "Child",
         "parameters": [{"tabPropertyId": "p-flow", "value": SUB, "variable": []},
                        {"tabPropertyId": "p-map", "value": [{"source": {"variable": [{"variableId": V_OUT}]}}]}],
         "ports": []},
        {"id": "e", "actionTemplateName": "Stop", "actionName": "Error", "ports": []},
        {"id": "orphan", "actionTemplateName": "Map Data", "actionName": "Unreached",
         "isDisabled": True, "ports": []},
    ], variables=[
        {"id": V_IN, "name": "payload", "type": 10, "dataType": "0317bfee-b2f5-4bde-bfe8-121212121214"},
        {"id": V_OUT, "name": "rows", "type": 30, "isList": True,
         "dataType": "0317bfee-b2f5-4bde-bfe8-121212121220"},
    ])


def test_resolves_placeholders_variables_flows_and_names():
    md = digest.render(_parent(), {SUB: "Child flow", CRED: "db-main"})
    assert "const x = {{payload}};" in md                      # <%N%> -> variable name
    assert "WHERE a = {{payload}}" in md and "```sql" in md    # SQL fenced as sql
    assert "[[Child flow]]" in md                              # subprocess target by title
    assert "[[db-main]]" in md                                 # caller-supplied name
    assert "{{rows}}" in md                                    # GUID inside structured value
    assert "| payload | input | String |" in md
    assert "| rows | output | JSON | yes |" in md


def test_execution_order_error_edges_and_unreachable_last():
    md = digest.render(_parent())
    assert md.index("1. Start") < md.index("2. Node: Build rows") < md.index("Execute Query: Save")
    assert "error → " in md
    assert "Map Data: Unreached — DISABLED" in md
    assert md.index("Unreached") > md.index("Call Subprocess")


def test_huge_and_base64_literals_are_elided():
    f = _parent()
    f["actions"][1]["parameters"][0]["value"] = "QUJD" * 2000
    md = digest.render(f)
    assert "base64/binary literal" in md and "QUJDQUJD" * 10 not in md


def test_unwrap_envelope_bundle_and_pascal_case():
    env = {"result": {"flow": _parent()}}
    assert [f["id"] for f in digest.unwrap(env)] == [PARENT]
    pascal = {"Flows": [{"Id": SUB, "Title": "Child", "Variables": [], "Actions": [
        {"Id": "s", "ActionTemplateName": "Start", "ActionName": "Start", "Ports": []}]}]}
    flows = digest.unwrap(pascal)
    assert flows[0]["title"] == "Child" and "# Child" in digest.render(flows[0])


def test_action_writes_index_with_cross_process_calls(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    (src / "p.json").write_text(json.dumps({"result": {"flow": _parent()}}))
    (src / "c.json").write_text(json.dumps(_flow(SUB, "Child flow", [
        {"id": "s", "actionTemplateName": "Start", "actionName": "Start", "ports": []}])))
    out = tmp_path / "out"
    res = flowgraph.flow_digest(types.SimpleNamespace(in_path=str(src), out_dir=str(out), names=None))
    assert res["result"]["count"] == 2
    index = (out / "INDEX.md").read_text()
    assert "Child flow" in index.split("[Parent]")[1]            # Parent's row lists its callee
    assert "[[Child flow]]" in (out / f"parent-{PARENT[:8]}.md").read_text()


def test_action_inline_without_out(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps(_parent()))
    res = flowgraph.flow_digest(types.SimpleNamespace(in_path=str(p), out_dir=None, names=None))
    assert res["result"]["flows"][0]["markdown"].startswith("# Parent")


def test_null_tabpropertyid_does_not_crash():
    # A parameter can carry tabPropertyId explicitly null; `.get(k, "")` returns None
    # (key present) not the default, so the fallback must coalesce before slicing.
    flow = _flow("f", "F", [
        {"id": "s", "actionTemplateName": "Start", "actionName": "Start",
         "ports": [{"destinationId": "n", "type": 0}]},
        {"id": "n", "actionTemplateName": "Node", "actionName": "N",
         "parameters": [{"tabPropertyId": None, "value": "a snippet"}], "ports": []},
    ])
    md = digest.render(flow)
    assert "a snippet" in md


# ---------------------------------------------------------------- form-digest

from tools.procesio.flowmodel import formdigest  # noqa: E402

FORM_VAR = "cb3e93c9-652d-41c6-aa53-a59791f8f6e0"
ROOT = "11223344-5566-7788-99aa-aabbccddeeff"
EL_UP = "66666666-6666-6666-6666-666666666666"
EL_TBL = "77777777-7777-7777-7777-777777777777"
ATTR_VAL = "88888888-8888-8888-8888-888888888888"
FVAR = "99999999-9999-9999-9999-999999999999"


def _form():
    def el(eid, typ, name, parent=None, events=None, visible=True):
        cfgs = [{"key": "name", "value": name}, {"key": "id", "value": name.lower()},
                {"key": "visible", "value": visible}]
        if events:
            cfgs.append({"key": "onInputEvents", "value": {"events": events}})
        return {"id": eid, "type": typ, "parentId": parent, "configs": cfgs}
    run = {"action": "RUN_PROCESS", "config": {
        "processId": PARENT, "syncRun": False,
        "inputMap": [{"left": {"value": V_IN}, "right": {"value": f"{FORM_VAR}.{ROOT}.{EL_UP}.{ATTR_VAL}"}}],
        "outputMap": [{"left": {"value": V_OUT}, "right": {"value": f"{FORM_VAR}.{ROOT}.{EL_TBL}.{ATTR_VAL}"}},
                      {"left": {"value": V_OUT}, "right": {"value": FVAR}}]}}
    mapf = {"action": "MAP_FORM_DATA", "config": {
        "areConditionsConfigured": True,
        "conditions": [{"operator": "IS_TRUE", "leftOperator": {"value": FVAR}, "logicOperator": 0}],
        "mapping": [{"left": f"{FORM_VAR}.{ROOT}.{EL_TBL}.{ATTR_VAL}", "right": "true"}]}}
    js = {"action": "RUN_JAVASCRIPT", "config": {"code": "// My Guard v2 — blocks bad picks\nfoo();"}}
    return {"id": "form-1", "name": "Offer form", "status": 1, "data": {
        "variables": [{"id": FORM_VAR, "name": "form"}, {"id": FVAR, "name": "rows_ready", "isList": False}],
        "dataModel": {"id": FORM_VAR, "name": "form", "attributes": [
            {"id": ROOT, "name": "root", "attributes": [
                {"id": EL_UP, "name": "Upload1", "attributes": [{"id": ATTR_VAL, "name": "value"}]},
                {"id": EL_TBL, "name": "Table1", "attributes": [{"id": ATTR_VAL, "name": "value"}]}]}]},
        "events": [{"type": "FORM_LOAD", "action": "RUN_JAVASCRIPT", "config": {"code": "init();"}}],
        "elements": [el("step", "step", "step-one"),
                     el(EL_UP, "file-upload", "offer-upload", "step", [run, js]),
                     el(EL_TBL, "table", "Table_Offers", "step", [mapf], visible=False)]}}


def test_form_digest_resolves_paths_process_vars_and_conditions():
    md, scripts = formdigest.render(_form(), {PARENT: _parent()})
    assert "RUN_PROCESS → **Parent** (async)" in md
    assert "in: `payload` ← `offer-upload.value`" in md
    assert "out: `Table_Offers.value` ← `rows`" in md
    assert "out: `rows_ready` ← `rows`" in md                 # bare form-variable target
    assert "when: rows_ready IS_TRUE" in md and "set `Table_Offers.value` = `true`" in md
    assert "My Guard v2" in md and len(scripts) == 2           # FORM_LOAD + element script
    assert "(hidden by default)" in md and "FORM_LOAD" in md
    assert md.index("step-one") < md.index("offer-upload")    # tree order


def test_form_digest_action_writes_map_scripts_and_global_code(tmp_path):
    forms, procs, out = tmp_path / "forms", tmp_path / "procs", tmp_path / "out"
    forms.mkdir(); procs.mkdir()
    (forms / "form-1.json").write_text(json.dumps({"result": _form()}))
    (forms / "form-1.code.json").write_text(json.dumps({"javascript": "g();", "css": "a{}"}))
    (procs / "p.json").write_text(json.dumps({"result": {"flow": _parent()}}))
    res = flowgraph.form_digest(types.SimpleNamespace(in_path=str(forms), processes=str(procs),
                                                      out_dir=str(out)))
    assert res["result"]["count"] == 1
    fmap = (out / "FORM-PROCESS-MAP.md").read_text()
    assert "| Offer form | offer-upload | Input | Parent |" in fmap
    side = out / "offer-form-form-1"
    assert (side / "form.js").read_text() == "g();" and (side / "script-002.js").exists()


def test_form_digest_accepts_bare_string_map_sides():
    # A real form carries a RUN_PROCESS map row's left/right as a bare string, not
    # {"value": ...}; the digest must handle both shapes without crashing.
    run = {"action": "RUN_PROCESS", "config": {
        "processId": PARENT, "syncRun": True,
        "inputMap": [{"left": V_IN, "right": FVAR}],
        "outputMap": [{"left": V_OUT, "right": FVAR}]}}
    form = {"id": "f", "name": "F", "data": {
        "variables": [{"id": FVAR, "name": "rows_ready"}],
        "dataModel": {"id": "dm", "name": "form", "attributes": []},
        "elements": [{"id": "btn", "type": "button", "parentId": None,
                      "configs": [{"key": "name", "value": "go"},
                                  {"key": "onInputEvents", "value": {"events": [run]}}]}]}}
    md, _ = formdigest.render(form, {PARENT: _parent()})
    assert "RUN_PROCESS → **Parent** (sync)" in md
    assert "in: `payload` ← `rows_ready`" in md
    assert "out: `rows_ready` ← `rows`" in md
