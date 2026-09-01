"""DTO sub-tools: schema validation, pure builders (fixture regression), and the
generic action wiring. All offline (no network)."""
from __future__ import annotations

import itertools
import json

import pytest

from tools.procesio import main
from tools.procesio.dto import framework, refdata, registry
from tools.procesio.dto.datatype import builder as dt
from tools.procesio.errors import UsageError


# -- reference data -----------------------------------------------------------

def test_primitive_type_ids_and_aliases():
    assert refdata.primitive_type_id("string") == "0317bfee-b2f5-4bde-bfe8-121212121214"
    assert refdata.primitive_type_id("STR") == refdata.primitive_type_id("string")
    assert refdata.primitive_type_id("int") == refdata.primitive_type_id("integer")
    assert refdata.csharp_correspondent("string") == 50
    with pytest.raises(KeyError):
        refdata.primitive_type_id("widget")


# -- schema validation --------------------------------------------------------

def test_datatype_schema_accepts_valid():
    framework.validate_config(dt.COMPONENT, {"name": "M", "attributes": [{"name": "a", "type": "string"}]})


def test_datatype_schema_rejects_missing_name():
    with pytest.raises(UsageError):
        framework.validate_config(dt.COMPONENT, {"attributes": []})


def test_datatype_schema_rejects_unknown_primitive():
    with pytest.raises(UsageError):
        framework.validate_config(dt.COMPONENT, {"name": "M", "attributes": [{"name": "a", "type": "widget"}]})


def test_datatype_schema_rejects_attr_with_no_kind():
    with pytest.raises(UsageError):
        framework.validate_config(dt.COMPONENT, {"name": "M", "attributes": [{"name": "a"}]})


def test_datatype_schema_rejects_additional_props():
    with pytest.raises(UsageError):
        framework.validate_config(dt.COMPONENT, {"name": "M", "attributes": [], "bogus": 1})


# -- pure builder + fixture regression ---------------------------------------

def _det_ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}",
            "models": {"personmodel": "11111111-1111-1111-1111-111111111111"}}


def test_datatype_builder_matches_golden_fixture():
    fx = dt.DIR / "fixtures"
    cfg = json.loads((fx / "customer.config.json").read_text(encoding="utf-8"))
    want = json.loads((fx / "customer.dto.json").read_text(encoding="utf-8"))
    got = dt.build(cfg, _det_ctx())
    assert got == want


def test_datatype_builder_primitive_list_nested_modelref():
    cfg = {"name": "M", "attributes": [
        {"name": "s", "type": "string"},
        {"name": "tags", "type": "string", "isList": True},
        {"name": "child", "attributes": [{"name": "x", "type": "integer"}]},
        {"name": "ref", "model": "personmodel"},
    ]}
    dto = dt.build(cfg, _det_ctx())
    attrs = dto["Content"]["Attributes"]
    assert dto["Content"]["IsDataModel"] is True
    assert attrs[0]["DataTypeId"] == refdata.primitive_type_id("string")
    assert attrs[0]["IsDataModel"] is False
    assert attrs[1]["IsList"] is True
    assert attrs[2]["IsDataModel"] is True and [a["Name"] for a in attrs[2]["Attributes"]] == ["x"]
    assert attrs[3]["DataTypeId"] == "11111111-1111-1111-1111-111111111111"


# -- credential builder -------------------------------------------------------

def test_credential_builder_matches_golden_and_resolves_options():
    from tools.procesio.dto.credential import builder as cb
    fx = cb.DIR / "fixtures"
    cfg = json.loads((fx / "rest.config.json").read_text(encoding="utf-8"))
    template = json.loads((fx / "rest.template.json").read_text(encoding="utf-8"))
    want = json.loads((fx / "rest.dto.json").read_text(encoding="utf-8"))
    got = cb.build(cfg, {"template": template})
    assert got == want
    # option name resolved to value
    vals = {p["id"]: p["value"] for p in got["properties"]}
    assert vals["p-auth"] == "opt-noauth" and vals["p-method"] == "opt-get"


def test_credential_unknown_property_raises():
    from tools.procesio.dto.credential import builder as cb
    template = {"name": "X", "gid": "g", "pid": "p", "properties": [{"id": "i", "label": "URL"}]}
    with pytest.raises(UsageError):
        cb.build({"template": "X", "name": "n", "properties": {"Nope": "1"}}, {"template": template})


def test_credential_schema_accepts_array_pills_value():
    """OAuth2 credentials carry a 'Scopes' pills LIST; the credential config schema
    must accept an ARRAY property value. Regression: values were scalar-only, which
    rejected the scopes list and blocked OAuth2 (Google Drive/Mail/etc.) credentials."""
    from tools.procesio.dto import framework
    from tools.procesio.dto.credential import builder as credential
    cfg = {"template": "OAuth2 (REST API) / Google Drive", "name": "google-drive",
           "properties": {"URL": "https://www.googleapis.com",
                          "Scopes": ["https://www.googleapis.com/auth/drive",
                                     "https://www.googleapis.com/auth/drive.readonly"],
                          "Method": "GET"}}
    framework.validate_config(credential.COMPONENT, cfg)  # must not raise
    # a scalar value still validates (no regression)
    framework.validate_config(credential.COMPONENT,
                              {"template": "REST API", "name": "x",
                               "properties": {"URL": "https://api.example.com"}})


# -- document builder ---------------------------------------------------------

def test_document_builder_matches_golden():
    from tools.procesio.dto.document import builder as db
    fx = db.DIR / "fixtures"
    cfg = json.loads((fx / "invoice.config.json").read_text(encoding="utf-8"))
    want = json.loads((fx / "invoice.dto.json").read_text(encoding="utf-8"))
    cnt = itertools.count(1)
    got = db.build(cfg, {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"})
    assert got == want
    assert got["placeholderDelimiterStart"] == "&lt;%" and got["documentPageOrientation"] == 0


def test_document_landscape_and_types():
    from tools.procesio.dto.document import builder as db
    dto = db.build({"name": "D", "body": "x", "orientation": "landscape",
                    "variables": [{"name": "n", "type": "integer"}]}, {})
    assert dto["documentPageOrientation"] == 1
    assert dto["variables"][0]["dataType"] == refdata.primitive_type_id("integer")


# -- webhook builder ----------------------------------------------------------

def test_webhook_builder_matches_golden():
    from tools.procesio.dto.webhook import builder as wb
    fx = wb.DIR / "fixtures"
    cfg = json.loads((fx / "order.config.json").read_text(encoding="utf-8"))
    want = json.loads((fx / "order.dto.json").read_text(encoding="utf-8"))
    fake_dm = json.loads(want["DataModel"]) if isinstance(want.get("DataModel"), str) else want["DataModel"]
    got = wb.build(cfg, {"new_id": lambda: "00000000-0000-0000-0000-000000000001", "data_model": fake_dm})
    assert got == want
    assert got["Type"] == 1 and got["IsEdited"] is True


def test_webhook_auto_type_and_custom_response_dto():
    from tools.procesio.dto.webhook import builder as wb
    fake_dm = {"id": "dm", "name": "X", "isDataModel": True, "type": 2, "attributes": []}
    dto = wb.build({"name": "W", "sample": {"a": 1}, "type": "auto",
                    "customResponse": {"type": "staticjson", "config": "{\"ok\":1}"}},
                   {"new_id": lambda: "id", "data_model": fake_dm})
    assert dto["Type"] == 0                                   # AUTO requested
    assert dto["CustomResponseConfig"] == {"ConfigType": 1, "Config": "{\"ok\":1}"}


def test_process_custom_response_binds_variable():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "r", "type": "string", "direction": "output"}],
           "actions": [{"id": "g", "action": "Generate GUID"}],
           "customResponse": {"var": "r"}}
    dto = pb.build(cfg, _proc_ctx())
    cr = dto["CustomResponse"]
    assert cr["Value"] == "<%0%>" and cr["Variable"]["variableId"] is not None


def test_webhook_requires_data_model_in_ctx():
    from tools.procesio.dto.webhook import builder as wb
    with pytest.raises(UsageError):
        wb.build({"name": "W", "sample": {"a": 1}}, {})


# -- form builder -------------------------------------------------------------

def _form_ctx():
    cnt = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"}


def test_form_builder_elements_match_golden():
    from tools.procesio.dto.form import builder as fb
    fx = fb.DIR / "fixtures"
    cfg = json.loads((fx / "reg.config.json").read_text(encoding="utf-8"))
    want = json.loads((fx / "reg.elements.json").read_text(encoding="utf-8"))
    got = fb.build(cfg, _form_ctx())["Data"]["elements"]
    assert got == want


def test_form_sections_and_overrides():
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "heading", "label": "H"},
        {"type": "input", "label": "Name", "name": "nm", "required": True},
        {"type": "select", "label": "C", "options": ["a", "b"]},
        {"type": "checkbox", "label": "Sub"},
        {"type": "button", "label": "Go", "submit": True}]}
    dto = fb.build(cfg, _form_ctx())
    els = {e["type"]: e for e in dto["Data"]["elements"]}
    assert els["heading"]["section"] == "header" and els["button"]["section"] == "footer"
    for e in dto["Data"]["elements"]:
        assert e["parentId"] is None           # all top-level
        for c in e["configs"]:
            if c["key"] == "visible":
                assert c["value"] is True
    # required propagated; options resolved
    inp = els["input"]["configs"]
    assert next(c["value"] for c in inp if c["key"] == "required") is True
    opts = next(c["value"] for c in els["select"]["configs"] if c["key"] == "sourceValue")
    assert opts == [{"name": "a", "value": "a"}, {"name": "b", "value": "b"}]
    # form Data.code is empty (renders from elements)
    assert dto["Data"]["code"] == "" and dto["Status"] == 1


def test_form_nested_children_flat_with_parentid():
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "section", "label": "S", "children": [{"type": "input", "label": "X"}]}]}
    dto = fb.build(cfg, _form_ctx())
    els = dto["Data"]["elements"]
    assert [e["type"] for e in els] == ["section", "input"]   # FLAT, not nested
    assert all("children" not in e for e in els)
    assert els[1]["parentId"] == els[0]["id"]


def test_form_table_structure():
    from tools.procesio.dto.form import builder as fb
    dto = fb.build({"name": "F", "elements": [
        {"type": "table", "label": "Items", "columns": [
            {"key": "product", "label": "Product", "cell": {"type": "input", "label": "P"}},
            {"key": "qty", "label": "Qty", "cell": {"type": "number-input", "label": "Q"}}]}]}, _form_ctx())
    els = dto["Data"]["elements"]
    table = next(e for e in els if e["type"] == "table")
    row = next(e for e in els if e["type"] == "static-table-row")
    assert row["parentId"] == table["id"]
    cols = next(c["value"] for c in table["configs"] if c["key"] == "tableColumnsSourceValue")
    assert [c["key"] for c in cols] == ["product", "qty"]
    cells = [e for e in els if e["parentId"] == row["id"]]
    assert len(cells) == 2


def test_form_events_and_theme():
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "theme": {"--c-primary": "#abc123"}, "elements": [
        {"type": "button", "label": "Go", "submit": True,
         "events": [{"on": "click", "do": "js", "code": "alert(1)"},
                    {"on": "click", "do": "process", "processId": "PID",
                     "inputs": [{"to": "v", "from": "p"}]}]}]}
    dto = fb.build(cfg, _form_ctx())
    btn = dto["Data"]["elements"][0]
    ev = next(c["value"] for c in btn["configs"] if c["key"] == "onClickEvents")
    assert ev["events"][0]["action"] == "RUN_JAVASCRIPT"
    assert ev["events"][1]["action"] == "RUN_PROCESS" and ev["events"][1]["config"]["processId"] == "PID"
    prim = next(p["value"] for s in dto["Data"]["theme"] for p in s.get("properties", [])
                if p.get("cssVariable") == "--c-primary")
    assert prim == "#abc123"


def test_form_assignee_and_event_trigger_kinds():
    from tools.procesio.dto.form import builder as fb
    dto = fb.build({"name": "F", "elements": [
        {"type": "section", "label": "S", "assignee": "USER-1", "children": [{"type": "input", "label": "x"}]},
        {"type": "input", "label": "m", "events": [{"on": "input", "do": "map",
            "mapping": [{"to": "dest", "value": "lit"}]}]}]}, _form_ctx())
    els = dto["Data"]["elements"]
    sec = next(e for e in els if e["type"] == "section")
    assert next(c["value"] for c in sec["configs"] if c["key"] == "assignee") == "USER-1"
    # flat list: find the input that carries the event (not the section's child)
    inp = next(e for e in els if e["type"] == "input"
               and any(c["key"] == "onInputEvents" and c["value"] for c in e["configs"]))
    ev = next(c["value"] for c in inp["configs"] if c["key"] == "onInputEvents")
    assert ev["events"][0]["action"] == "MAP_FORM_DATA"


def test_form_unknown_control_raises():
    from tools.procesio.dto.form import builder as fb
    with pytest.raises(UsageError):
        fb.build({"name": "F", "elements": [{"type": "no-such-control"}]}, _form_ctx())


# -- action wiring ------------------------------------------------------------

def test_dto_actions_registered():
    for comp in registry.all_components():
        assert f"{comp}-create" in main.ACTIONS
        assert f"{comp}-edit" in main.ACTIONS


# -- process builder ----------------------------------------------------------

def _proc_ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}


def test_process_builder_matches_golden_fixture():
    from tools.procesio.dto.process import builder as pb
    fx = pb.DIR / "fixtures"
    cfg = json.loads((fx / "greet.config.json").read_text(encoding="utf-8"))
    want = json.loads((fx / "greet.dto.json").read_text(encoding="utf-8"))
    assert pb.build(cfg, _proc_ctx()) == want


def test_process_binding_modes_and_ports():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "v", "type": "string"}],
           "actions": [{"id": "c", "action": "Concatenate", "params": {
               "Input String 1": {"var": "v"},
               "Input String 2": "lit",
               "Result": {"var": "v"}}}]}
    dto = pb.build(cfg, _proc_ctx())
    names = [a["ActionName"] for a in dto["Actions"]]
    assert names == ["Start", "Concatenate", "Stop"]
    params = {p["Value"]: p for p in dto["Actions"][1]["Parameters"]}
    assert "lit" in params and params["lit"]["Variable"] == []       # literal
    var_param = next(p for p in dto["Actions"][1]["Parameters"] if p["Variable"])
    assert var_param["Value"] == "<%0%>"                             # variable binding
    # entry edge (null->Start) + Start->Concat on Start; Concat->Stop on Concat
    assert len(dto["Actions"][0]["Ports"]) == 2
    assert dto["Actions"][2]["Ports"] == []


def test_process_explicit_edges_and_template_binding():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "a", "type": "string"}],
           "actions": [{"id": "c", "action": "Concatenate",
                        "params": {"Input String 1": {"template": "x <%0%>", "vars": ["a"]}}}],
           "edges": [["start", "c"], ["c", "stop"]]}
    dto = pb.build(cfg, _proc_ctx())
    p = dto["Actions"][1]["Parameters"][0]
    assert p["Value"] == "x <%0%>" and len(p["Variable"]) == 1


def test_process_webhook_attachment():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "p", "type": "string", "direction": "input"}],
           "actions": [{"id": "g", "action": "Generate GUID"}],
           "webhooks": [{"webhookId": "wh-1", "variables": [{"name": "p", "source": "body"}]}]}
    dto = pb.build(cfg, _proc_ctx())
    assert len(dto["Webhooks"]) == 1
    wh = dto["Webhooks"][0]
    assert wh["WebhookId"] == "wh-1"
    assert wh["WebhookVariables"][0]["VariableType"] == 3  # body


def test_process_decisional_branches():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "n", "type": "integer", "direction": "input"}],
           "actions": [
               {"id": "dec", "action": "Decisional", "branches": [
                   {"to": "hi", "when": [{"left": {"var": "n"}, "op": "GREATER_THAN", "right": 5}]},
                   {"to": "lo", "default": True}]},
               {"id": "hi", "action": "Generate GUID"},
               {"id": "lo", "action": "Generate GUID"},
               {"id": "s1", "action": "Stop"}, {"id": "s2", "action": "Stop"}],
           "edges": [["start", "dec"], ["hi", "s1"], ["lo", "s2"]]}
    dto = pb.build(cfg, _proc_ctx())
    dec = next(a for a in dto["Actions"] if a["ActionName"] == "Decisional")
    cases = next(p for p in dec["Parameters"] if isinstance(p["Value"], list))
    assert cases["Value"][0]["condition"][0]["operator"] == "GREATER_THAN"
    # two branch ports (case + default), default carries the marker
    assert any(p.get("Data", {}).get("isDefault") == "default" for p in dec["Ports"])
    # user-supplied Stops -> no auto stop duplication
    assert sum(1 for a in dto["Actions"] if a["ActionName"] == "Stop") == 2


def test_process_error_port_and_join():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "m", "type": "string", "direction": "output"}],
           "actions": [
               {"id": "t", "action": "Throw", "onError": "h"},
               {"id": "h", "action": "Generate GUID"},
               {"id": "j", "action": "Join"}],
           "edges": [["start", "t"], ["t", "j"], ["h", "j"], ["j", "stop"]]}
    dto = pb.build(cfg, _proc_ctx())
    th = next(a for a in dto["Actions"] if a["ActionName"] == "Throw")
    assert th["VariableErrorId"] is not None
    assert any(p.get("Type") == 1 and p.get("Data", {}).get("isDefault") == "error" for p in th["Ports"])
    assert any(v.get("IsError") for v in dto["Variables"])      # ErrorDataModel variable
    jn = next(a for a in dto["Actions"] if a["ActionName"] == "Join")
    assert jn["CustomData"]["inputPorts"] == -1                 # flow Join accepts many inputs


def test_process_scripting_global_indexing():
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "n", "type": "integer", "direction": "input"},
                                       {"name": "out", "type": "json", "direction": "output"}],
           "actions": [{"id": "js", "action": "Javascript",
                        "params": {"Code": {"template": "setOutput(<%0%>+1)", "vars": ["n"]},
                                   "Output": {"var": "out"}}}]}
    dto = pb.build(cfg, _proc_ctx())
    js = next(a for a in dto["Actions"] if a["ActionName"] == "Javascript")
    # Code uses <%0%> (id 0), Output captured at a distinct global index (<%1%>)
    code = next(p for p in js["Parameters"] if "setOutput" in str(p["Value"]))
    out = next(p for p in js["Parameters"] if p["Value"] == "<%1%>")
    assert code["Variable"][0]["id"] == 0 and out["Variable"][0]["id"] == 1


def test_process_doc_mapper_destination_shape():
    from tools.procesio.dto.process import builder as pb
    ctx = _proc_ctx()
    ctx["doc_vars"] = {"gd": {"clientname": "DOC-VAR-ID"}}
    cfg = {"title": "T", "variables": [{"name": "c", "type": "string", "direction": "input"}],
           "actions": [{"id": "gd", "action": "Generate Document",
                        "params": {"Select Document Template": "DID", "File Name": "f"},
                        "docMap": {"clientName": "c"}}]}
    dto = pb.build(cfg, ctx)
    gd = next(a for a in dto["Actions"] if a["ActionTemplateName"] == "Generate Document")
    assert gd["ActionName"] == "Generate f"          # auto-named from the File Name literal
    mapper = next(p for p in gd["Parameters"] if isinstance(p["Value"], list) and p["Value"]
                  and "destination" in p["Value"][0])
    row = mapper["Value"][0]
    assert row["destination"]["variableId"] == "DOC-VAR-ID"
    assert row["source"]["value"].startswith("<%")


def test_process_unknown_action_raises():
    from tools.procesio.dto.process import builder as pb
    with pytest.raises(UsageError):
        pb.build({"title": "T", "actions": [{"id": "x", "action": "NoSuchAction"}]}, _proc_ctx())


def test_process_unknown_property_raises():
    from tools.procesio.dto.process import builder as pb
    with pytest.raises(UsageError):
        pb.build({"title": "T", "actions": [{"id": "x", "action": "Generate GUID",
                                             "params": {"Nope": "1"}}]}, _proc_ctx())


def test_datatype_create_dry_run_builds_without_network():
    # needs_client path, but --dry-run must not call the network; pass a client
    # whose any network use would raise.
    class Boom:
        def __getattr__(self, _):
            raise AssertionError("dry-run must not touch the network")
    defn = main.ACTIONS["datatype-create"]
    import argparse
    p = argparse.ArgumentParser()
    defn.add_args(p)
    args = p.parse_args(["--config", json.dumps({"name": "M", "attributes": [{"name": "a", "type": "string"}]}),
                         "--dry-run"])
    # datatype has no `model` refs here, so prepare_ctx makes no calls.
    out = defn.func(Boom(), args)
    assert out["dry_run"] is True and out["dto"]["Content"]["Name"] == "M"



def test_action_config_mirrors_parameters():
    """Designer reads CustomData.configuration; it must mirror Parameters (literal as-is,
    a variable ref as the raw var id, not <%N%>)."""
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T", "variables": [{"name": "v", "type": "string"}],
           "actions": [{"id": "c", "action": "Concatenate", "params": {
               "Input String 1": {"var": "v"}, "Input String 2": "lit", "Result": {"var": "v"}}}]}
    dto = pb.build(cfg, _proc_ctx())
    act = [a for a in dto["Actions"] if a["ActionName"] not in ("Start", "Stop")][0]
    vals = {}

    def walk(ss):
        for s in ss or []:
            if s.get("label"):
                vals[s["label"]] = s.get("value")
            if isinstance(s.get("value"), list):
                walk(s["value"])
    for t in act["CustomData"]["configuration"]:
        walk(t.get("settings", []))
    assert vals.get("Input String 2") == "lit"
    assert vals.get("Input String 1") == dto["Variables"][0]["Id"]   # <%0%> -> var id


def test_generate_document_docmapper_config_shape():
    """document-mapper config must be the designer shape [{id, process, document}],
    not the runtime {source/destination} shape (else the designer shows it empty)."""
    from tools.procesio.dto.process import builder as pb
    ctx = _proc_ctx()
    ctx["doc_vars"] = {"g": {"htmlcontent": "DOCVAR"}}
    cfg = {"title": "T", "variables": [{"name": "html", "type": "string"}],
           "actions": [{"id": "g", "action": "Generate Document", "name": "gd",
                        "params": {"Save document as": "1"},
                        "docMap": {"htmlContent": {"var": "html"}}}]}
    dto = pb.build(cfg, ctx)
    gd = [a for a in dto["Actions"] if a["ActionName"] == "gd"][0]
    found = []

    def find(ss):
        for s in ss or []:
            if s.get("type") == "document-mapper":
                found.append(s)
            if isinstance(s.get("value"), list):
                find(s["value"])
    for t in gd["CustomData"]["configuration"]:
        find(t.get("settings", []))
    assert found, "no document-mapper setting"
    row = found[0]["value"][0]
    assert {"id", "process", "document"} <= set(row) and row["document"] == "DOCVAR"


def test_form_builds_data_model_mirror():
    """Each form field must get a data-model attribute under the `fields` container so
    triggers resolve and values flow."""
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "input", "label": "Company", "name": "companyName"},
        {"type": "button", "label": "Go", "name": "go"}]}
    dto = fb.build(cfg, _form_ctx())
    dm = dto["Data"]["dataModel"]
    assert dm["id"] != dto["Id"]                       # data-model root is a SEPARATE id
    fields = next(a for a in dm["attributes"] if a["id"] == fb._FIELDS_NS)
    assert fields["parentDataTypeId"] == dm["id"]      # fields container hangs off the root
    names = {f["name"]: f for f in fields["attributes"]}
    assert "companyName" in names
    assert any(at["name"] == "value" for at in names["companyName"]["attributes"])



def test_decisional_cases_config_designer_shape():
    """decisional-case config must carry every field the designer needs to render a
    condition (value/rightOperandAsListRequired/operandsAsListOptional/uid), map a
    variable operand to its id, and coerce a literal operand to a string."""
    from tools.procesio.dto.process import builder as pb
    cases = [{"id": 0, "actionid": "TARGET", "condition": [{
        "id": 0, "operator": "GREATER_THAN", "logicOperator": 1,
        "leftOperator": {"value": "<%0%>", "variable": [{"id": 0, "variableId": "VARID", "attribute": None}]},
        "rightOperator": {"value": 50, "variable": []},
        "auxOperator": {"value": "", "variable": []}}]}]
    out = pb._decisional_cases_config(cases, _proc_ctx())
    case = out[0]
    assert case["target"] == "TARGET" and case["name"] == "Case 1"
    cond = case["condition"][0]
    assert {"value", "rightOperandAsListRequired", "operandsAsListOptional", "uid"} <= set(cond)
    assert cond["leftOperator"]["value"] == "VARID"   # <%0%> -> variable id
    assert cond["rightOperator"]["value"] == "50"     # literal coerced to string


def test_form_field_paths_root_matches_form_handle_variable():
    """The designer resolves a field path back to its name by walking from the form
    handle variable (Data.variables[0]) into Data.dataModel. So dataModel.id, every
    field-path first segment, AND variables[0].id must be the SAME id; otherwise the
    process<->form maps render as raw guids (input) or blank (output). Regression guard
    for the live bug where a fresh dm_root_id != variables[0].id (65396456...)."""
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "input", "label": "Company", "name": "companyName"},
        {"type": "file-upload", "label": "PDF", "name": "briefFile"},
        {"type": "button", "label": "Go", "name": "go", "events": [
            {"on": "click", "do": "process", "processId": "P", "syncRun": True,
             "inputs": [{"to": "pin", "from": "companyName"}],
             "outputs": [{"to": "pout", "from": "briefFile"}]}]}]}
    dto = fb.build(cfg, _form_ctx())
    data = dto["Data"]
    fv = data["variables"][0]["id"]
    assert data["dataModel"]["id"] == fv               # root == form handle variable
    assert fv != dto["Id"]                             # ...and still != form template id
    # every field path embedded in the button's RUN_PROCESS maps roots at fv
    paths = []
    for el in data["elements"]:
        for c in el.get("configs", []):
            if c.get("key") == "onClickEvents":
                cfgv = c["value"]["events"][0]["config"]
                for row in cfgv["inputMap"] + cfgv["outputMap"]:
                    for v in (row["left"], row["right"]):
                        if isinstance(v, str) and v.count(".") == 3:
                            paths.append(v)
    assert paths, "expected at least one field-path reference in the maps"
    assert all(p.startswith(fv + ".") for p in paths), paths


def test_form_datamodel_attr_ids_match_element_config_ids_and_are_private():
    """The process-designer trigger-map resolves a 'Form variable' to its name only
    when the form's data model matches what the platform generates for a real UI form:
    (1) every fields sub-model attribute id == that element's config id of the same key
    (live evidence: OMS 15/16 match; our old builder 0/11 -> 'Unknown'), and (2) field
    sub-models AND their leaf attrs are isPublic:false (the 100%-consistent property of
    all 163 real forms scanned). Regression guard for both fixes."""
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "input", "label": "Company", "name": "companyName"},
        {"type": "file-upload", "label": "PDF", "name": "briefFile"}]}
    dto = fb.build(cfg, _form_ctx())
    data = dto["Data"]
    elements = {e["id"]: e for e in data["elements"]}
    fields = next(a for a in data["dataModel"]["attributes"] if a["id"] == fb._FIELDS_NS)
    checked = 0
    for sub in fields["attributes"]:
        el = elements.get(sub["id"])
        if not el:
            continue
        assert sub["isPublic"] is False, f"sub-model {sub['name']} must be isPublic:false"
        cfg_ids = {fb._attr_name(c.get("key")): c.get("id") for c in el.get("configs", [])}
        for attr in sub["attributes"]:
            assert attr["isPublic"] is False, f"attr {attr['name']} must be isPublic:false"
            assert attr["id"] == cfg_ids.get(attr["name"]), (
                f"dataModel attr id for {sub['name']}.{attr['name']} "
                f"({attr['id']}) must equal the element config id ({cfg_ids.get(attr['name'])})")
            checked += 1
    assert checked >= 2, "expected to check several attributes"
    # the value-attr path segment equals the element's value config id
    cn = next(e for e in data["elements"]
              if next((c["value"] for c in e["configs"] if c["key"] == "name"), None) == "companyName")
    val_cfg_id = next(c["id"] for c in cn["configs"] if c["key"] == "value")
    # find the field path for companyName in the (rebuilt) ctx via a button map would be
    # indirect; assert directly that the value attr in the data model uses that id
    sub = next(a for a in fields["attributes"] if a["id"] == cn["id"])
    val_attr = next(a for a in sub["attributes"] if a["name"] == "value")
    assert val_attr["id"] == val_cfg_id


def test_form_every_field_submodel_has_visible_attr():
    """The process-designer trigger-map INPUT-side resolver only treats a form field as
    a mappable variable if its data-model sub-model carries a `visible` attribute; a
    field without it renders as 'Unknown' (live-confirmed: briefFile had `visible` and
    resolved on the output side, companyName/country lacked it and showed 'Unknown' on
    the input side). The builder synthesizes `visible` for goldens that omit it (e.g.
    input). Guard that every field sub-model has it."""
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "input", "label": "Company", "name": "companyName"},
        {"type": "input", "label": "Country", "name": "country"},
        {"type": "file-upload", "label": "PDF", "name": "briefFile"}]}
    dto = fb.build(cfg, _form_ctx())
    data = dto["Data"]
    elements = {e["id"]: e for e in data["elements"]}
    fields = next(a for a in data["dataModel"]["attributes"] if a["id"] == fb._FIELDS_NS)
    for sub in fields["attributes"]:
        if sub["id"] not in elements:
            continue
        attr_names = {a["name"] for a in sub["attributes"]}
        assert "visible" in attr_names, f"field {sub['name']} sub-model missing 'visible' attr"
        # and the visible attr id still equals the element's visible config id (invariant)
        el = elements[sub["id"]]
        vis_cfg_id = next((c["id"] for c in el["configs"] if c.get("key") == "visible"), None)
        vis_attr_id = next(a["id"] for a in sub["attributes"] if a["name"] == "visible")
        assert vis_attr_id == vis_cfg_id


def test_datatype_create_uses_empty_post_then_attribute_endpoint():
    """The PROCESIO UI (HAR-verified) creates a model EMPTY (content:null) then adds EVERY
    attribute via POST /api/DataTypes/attribute/{id} — that path compiles them and inlines
    referenced child models. Attributes in the initial POST Content are never compiled
    (documents then render them "Unknown" / "Unable to find attribute"). Guard that the
    create flow replicates the UI exactly. Regression guard for the AAT_SearchHit bug."""
    from tools.procesio.dto.datatype import builder as db
    cnt = itertools.count(1)
    dto = db.build(
        {"name": "Parent", "attributes": [
            {"name": "title", "type": "string"},
            {"name": "items", "model": "ChildModel", "isList": True}]},
        {"new_id": lambda: f"id{next(cnt)}", "models": {"childmodel": "CHILD-ID"}})
    calls = []
    class FakeClient:
        def post(self, path, body=None):
            calls.append((path, body))
            return {"id": "NEW-PARENT-ID"} if path == "/api/DataTypes" else {}
    db._create(FakeClient(), dto, {})
    model_posts = [b for p, b in calls if p == "/api/DataTypes"]
    assert len(model_posts) == 1                       # one empty-model create
    assert model_posts[0].get("content") is None and "Content" not in model_posts[0]
    attr_calls = [(p, b) for p, b in calls if p.startswith("/api/DataTypes/attribute/")]
    assert len(attr_calls) == 2                         # BOTH attrs via the attribute endpoint
    by_name = {b["name"]: b for _, b in attr_calls}
    assert set(by_name) == {"title", "items"}
    for b in by_name.values():
        assert b["id"] is None and b["parentDataTypeId"] == "NEW-PARENT-ID"
        assert {"displayName", "name", "dataTypeId", "isList", "jsonProperty"} <= set(b)
    assert by_name["items"]["dataTypeId"] == "CHILD-ID" and by_name["items"]["isList"] is True


def test_process_ai_decisional_branches():
    """AI Decisional: string-condition cases -> runtime {id,actionid,condition:str} +
    designer {id,name,target,condition,internalId}; default port carries the marker;
    Model/Endpoint/extra-config pass through; LLM Response is an OUTPUT binding."""
    from tools.procesio.dto.process import builder as pb
    cfg = {"title": "T",
           "variables": [{"name": "animal", "type": "string", "direction": "input"},
                         {"name": "res", "type": "json", "direction": "process"}],
           "actions": [
               {"id": "ai", "action": "AI Decisional",
                "params": {"Select AI Configuration": "CRED", "Model": "gpt-4o",
                           "Endpoint": "1", "Timeout (seconds)": 60,
                           "User Prompt": {"template": "which? <%0%>", "vars": ["animal"]},
                           "LLM Response": {"var": "res"},
                           "Temperature": 0, "Top P": 1, "Max Output Tokens": 1024,
                           "Presence Penalty": 0, "Frequency Penalty": 0, "Seed": "", "Store": False},
                "branches": [
                    {"name": "bear", "to": "a", "condition": "Is it a bear?"},
                    {"to": "b", "condition": "Is it a fish?"},
                    {"to": "d", "default": True}]},
               {"id": "a", "action": "Generate GUID"},
               {"id": "b", "action": "Generate GUID"},
               {"id": "d", "action": "Generate GUID"}],
           "edges": [["start", "ai"], ["a", "stop"], ["b", "stop"], ["d", "stop"]]}
    dto = pb.build(cfg, _proc_ctx())
    ai = next(a for a in dto["Actions"] if a["ActionTemplateName"] == "AI Decisional")
    P = {p["TabPropertyId"]: p for p in ai["Parameters"]}
    cases = P["772aac51-73f5-471d-bf9f-f5099cb30124"]["Value"]
    assert [set(c) for c in cases] == [{"id", "actionid", "condition"}] * 2
    assert [c["condition"] for c in cases] == ["Is it a bear?", "Is it a fish?"]
    assert P["772aac51-73f5-471d-bf9f-f5099cb30112"]["Value"] == "gpt-4o"       # Model
    assert P["772aac51-73f5-471d-bf9f-f5099cb30113"]["Value"] == "1"            # Endpoint
    assert str(P["772aac51-73f5-471d-bf9f-f5099cb30118"]["Value"]) == "1024"    # Max Output Tokens (int/str ok)
    lr = P["772aac51-73f5-471d-bf9f-f5099cb30123"]                              # LLM Response OUTPUT
    assert lr["Value"].startswith("<%") and lr["Variable"][0]["variableId"]
    dc = next(s for tab in ai["CustomData"]["configuration"]
              for s in tab["settings"] if s.get("type") == "ai-decisional-case")
    assert all(set(c) == {"id", "name", "target", "condition", "internalId"} for c in dc["value"])
    assert dc["value"][0]["name"] == "bear" and dc["value"][1]["name"] == "Is it a fish?"
    assert any(p.get("Data", {}).get("isDefault") == "default" for p in ai["Ports"])


def test_ai_decisional_cases_config_designer_shape():
    """ai-decisional-case: runtime {id,actionid,condition:str} -> designer
    {id,name,target,condition,internalId}; name/internalId from the stashed meta, with
    a 'Case N' name + generated internalId fallback when no meta is present."""
    from tools.procesio.dto.process import builder as pb
    ctx = _proc_ctx()
    ctx["_ai_case_meta"] = {"NODE": [{"id": 0, "name": "bear", "internalId": "IID0"}]}
    cases = [{"id": 0, "actionid": "TARGET", "condition": "Is it a bear?"}]
    assert pb._ai_decisional_cases_config(cases, ctx, "NODE") == [
        {"id": 0, "name": "bear", "target": "TARGET",
         "condition": "Is it a bear?", "internalId": "IID0"}]
    out2 = pb._ai_decisional_cases_config(cases, _proc_ctx(), "OTHER")
    assert out2[0]["name"] == "Case 1" and out2[0]["internalId"]
