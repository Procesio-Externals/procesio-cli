"""normalize_designer_layer: deterministic designer<-runtime mirror, pure-logic tests."""
from tools.procesio.dto.process.normalize import normalize_designer_layer


def _node(code_setting_value, param_value, param_variable, stype="code-editor", pid="S1"):
    """A one-setting action: a designer setting (id=pid) mirrored by a runtime param (tabPropertyId=pid)."""
    return {"actionName": "N", "id": "a1",
            "parameters": [{"tabPropertyId": pid, "value": param_value, "variable": param_variable}],
            "customData": {"configuration": [{"settings": [
                {"id": pid, "type": stype, "label": "Code", "value": code_setting_value}]}]}}


def _val(f):
    return f["actions"][0]["customData"]["configuration"][0]["settings"][0]["value"]


def test_placeholder_fixed_to_guid():
    f = {"actions": [_node("var d = <%0%>;", "var d = <%0%>;", [{"id": 0, "variableId": "V1"}])]}
    r = normalize_designer_layer(f)
    assert r["changed"] and _val(f) == "var d = V1;"


def test_noop_on_guid_form():
    # designer already carries the GUID -> nothing to do
    f = {"actions": [_node("var d = V1;", "var d = <%0%>;", [{"id": 0, "variableId": "V1"}])]}
    assert not normalize_designer_layer(f)["changed"] and _val(f) == "var d = V1;"


def test_idempotent():
    f = {"actions": [_node("var d = <%0%>;", "var d = <%0%>;", [{"id": 0, "variableId": "V1"}])]}
    normalize_designer_layer(f)
    assert not normalize_designer_layer(f)["changed"]


def test_attribute_chain_preserved():
    f = {"actions": [_node("x=<%0%>;", "x=<%0%>;",
                           [{"id": 0, "variableId": "V1", "attribute": {"attributeId": "A1", "nextAttribute": None}}])]}
    normalize_designer_layer(f)
    assert _val(f) == "x=V1.A1;"


def test_multi_var_by_binding_id_not_position():
    # <%N%> binds to variable[].id, not positional order
    f = {"actions": [_node("f(<%1%>,<%0%>);", "f(<%1%>,<%0%>);",
                           [{"id": 0, "variableId": "VA"}, {"id": 1, "variableId": "VB"}])]}
    normalize_designer_layer(f)
    assert _val(f) == "f(VB,VA);"


def test_list_valued_setting_left_untouched():
    # a process-outputs-like LIST value must NOT be regenerated (string-only scope avoids corruption)
    lst = [{"id": 0, "subprocess": "S", "process": "V1.A1"}]
    f = {"actions": [_node(lst, [{"id": 0, "source": {"variable": [{"variableId": "V1"}]},
                                  "destination": {"variableId": "S"}}], [], stype="process-outputs")]}
    r = normalize_designer_layer(f)
    assert not r["changed"] and _val(f) == lst


def test_unbound_placeholder_left_literal():
    # a <%5%> with no matching variable id must be left as-is, never blanked
    f = {"actions": [_node("keep <%5%>", "keep <%5%>", [{"id": 0, "variableId": "V1"}])]}
    assert not normalize_designer_layer(f)["changed"] and _val(f) == "keep <%5%>"


def test_warning_param_without_setting():
    f = {"actions": [{"actionName": "N", "id": "a1",
                      "parameters": [{"tabPropertyId": "NOPE", "value": "x", "variable": []}],
                      "customData": {"configuration": [{"settings": []}]}}]}
    r = normalize_designer_layer(f)
    assert any(w["why"] == "param_without_setting" for w in r["warnings"])
