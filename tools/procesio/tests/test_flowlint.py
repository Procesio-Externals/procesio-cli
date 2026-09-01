"""flow-lint designer-layer pure-logic tests."""
from tools.procesio.handlers.flowlint import lint_flow_dto, CODE_PID

SP = {"Call Subprocess": "5456caf0", "Trigger Subprocess": "8540605e"}


def _node(name, code_var_ids):
    return {"actionName": name, "actionTemplateName": "Node",
            "parameters": [{"tabPropertyId": CODE_PID, "value": "x",
                            "variable": [{"id": i, "variableId": v} for i, v in enumerate(code_var_ids)]}]}


def _sub(name, target, sp_id, inputs=None, outputs=None):
    subsecs = [{"type": "process-inputs", "value": inputs or []},
               {"type": "process-outputs", "value": outputs or []}]
    return {"actionName": name, "actionTemplateName": "Call Subprocess",
            "parameters": [{"tabPropertyId": "flow", "value": target, "variable": []}],
            "customData": {"configuration": [{"settings": [
                {"type": "side-pannel", "id": sp_id, "value": subsecs}]}]}}


def test_clean_everything():
    flow = {"actions": [_node("N", ["v1"])], "variables": [{"id": "v1", "type": 20, "isError": False}]}
    assert lint_flow_dto(flow, SP, lambda f: {}) == []


def test_node_binds_error_scope_var():
    flow = {"actions": [_node("Compose", ["e1"])],
            "variables": [{"id": "e1", "type": 20, "isError": True, "name": "err_x"}]}
    assert lint_flow_dto(flow, SP, lambda f: {})[0]["kind"] == "CODE_ERROR_SCOPE"


def test_stale_sidepanel_id_flagged():
    tgt = "11111111-2222-4333-8444-555555555555"
    flow = {"actions": [_sub("Call X", tgt, "1da555da",
                             inputs=[{"id": 0, "subprocess": "A", "process": "v1"}])],
            "variables": [{"id": "v1", "type": 20}]}
    kinds = {p["kind"] for p in lint_flow_dto(flow, SP, lambda f: {"A": {"name": "in", "type": 10, "isRequired": True}} if f == tgt else {})}
    assert "SIDEPANEL_ID" in kinds


def test_required_input_unmapped():
    tgt = "11111111-2222-4333-8444-555555555555"
    flow = {"actions": [_sub("Call X", tgt, "5456caf0", inputs=[])], "variables": []}
    probs = lint_flow_dto(flow, SP, lambda f: {"B": {"name": "SessionId", "type": 10, "isRequired": True}} if f == tgt else {})
    assert probs and probs[0]["kind"] == "REQ_INPUT_UNMAPPED" and "SessionId" in probs[0]["detail"]


def test_output_not_type30():
    tgt = "11111111-2222-4333-8444-555555555555"
    flow = {"actions": [_sub("Call X", tgt, "5456caf0", outputs=[{"id": 0, "subprocess": "O", "process": "v1"}])],
            "variables": [{"id": "v1", "type": 20}]}
    probs = lint_flow_dto(flow, SP, lambda f: {"O": {"name": "dbout", "type": 20}} if f == tgt else {})
    assert probs and probs[0]["kind"] == "OUTPUT_NOT_TYPE30"


def test_execquery_null_output():
    flow = {"actions": [{"actionName": "EQ", "actionTemplateName": "Execute Query",
                         "customData": {"configuration": [{"settings": [
                             {"type": "side-pannel", "id": "8add0f17", "value": [
                                 {"label": "Output", "value": None}]}]}]}}],
            "variables": []}
    assert lint_flow_dto(flow, SP, lambda f: {})[0]["kind"] == "EXECQUERY_NO_OUTPUT"


def _eq(name, out_var_id):
    return {"actionName": name, "actionTemplateName": "Execute Query",
            "customData": {"configuration": [{"settings": [
                {"type": "side-pannel", "id": "8add0f17", "value": [
                    {"label": "Output", "value": out_var_id}]}]}]}}


def test_execquery_output_scalar_flagged():
    flow = {"actions": [_eq("EQ", "v1")],
            "variables": [{"id": "v1", "name": "RowsAffected", "type": 20,
                           "dataType": "0317bfee-b2f5-4bde-bfe8-121212121211", "isList": False}]}
    assert lint_flow_dto(flow, SP, lambda f: {})[0]["kind"] == "EXECQUERY_OUTPUT_TYPE"


def test_execquery_output_typed_dm_list_ok():
    flow = {"actions": [_eq("EQ", "v1")],
            "variables": [{"id": "v1", "name": "rows", "type": 20,
                           "dataType": "2639aaaa-0000-0000-0000-000000000000", "isList": True}]}
    assert lint_flow_dto(flow, SP, lambda f: {}) == []


def test_execquery_output_generic_object_list_ok():
    flow = {"actions": [_eq("EQ", "v1")],
            "variables": [{"id": "v1", "name": "dbout", "type": 20,
                           "dataType": "0317bfee-b2f5-4bde-bfe8-121212121221", "isList": True}]}
    assert lint_flow_dto(flow, SP, lambda f: {}) == []


def _node_cd(name, code_setting_value):
    """A Node with a customData (designer-layer) Code setting."""
    return {"actionName": name, "actionTemplateName": "Node",
            "parameters": [{"tabPropertyId": CODE_PID, "value": "return f(<%0%>);",
                            "variable": [{"id": 0, "variableId": "v1"}]}],
            "customData": {"configuration": [{"settings": [
                {"id": CODE_PID, "type": "code-editor", "label": "Code", "value": code_setting_value}]}]}}


def test_customdata_placeholder_flagged():
    # designer Code value still holds <%0%> (should be the variable GUID) -> designer paints it red
    flow = {"actions": [_node_cd("Build Msg", "return f(<%0%>);")],
            "variables": [{"id": "v1", "type": 20, "isError": False}]}
    assert "CUSTOMDATA_PLACEHOLDER" in {p["kind"] for p in lint_flow_dto(flow, SP, lambda f: {})}


def test_customdata_guid_form_clean():
    # designer Code value carries the variable GUID (correct) -> no placeholder problem
    flow = {"actions": [_node_cd("Build Msg", "return f(v1);")],
            "variables": [{"id": "v1", "type": 20, "isError": False}]}
    assert "CUSTOMDATA_PLACEHOLDER" not in {p["kind"] for p in lint_flow_dto(flow, SP, lambda f: {})}
