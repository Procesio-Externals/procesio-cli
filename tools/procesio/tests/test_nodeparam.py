"""Tests for the surgical node-parameter patcher (flowmodel/nodeparam.py).

Guards the two things that make a one-literal edit safe: the string-only scope (a structured
parameter must be refused, not silently text-patched) and the placeholder contract (the `<%N%>`
set binds `variable[]` positionally, so it may not drift without an explicit opt-in).
"""
from __future__ import annotations

import pytest

from tools.procesio.flowmodel import nodeparam

ENDPOINT = "45a7bbde-7e2a-4bd4-a6d3-8420f7790002"
PAYLOAD = "45a7bbde-7e2a-4bd4-a6d3-8420f7790003"


def _flow():
    """A Call API node shaped like the live DTO: a string Endpoint bound to one variable, plus a
    structured Request Parameters tab, mirrored in the designer side-pannel."""
    return {
        "id": "flow-1", "title": "Rates",
        "variables": [{"id": "var-year", "name": "year", "type": 20}],
        "actions": [
            {"id": "act-1", "actionName": "Get all by year", "actionTemplateName": "Call API",
             "parameters": [
                 {"tabPropertyId": ENDPOINT, "value": "https://old.example/x<%0%>.xml",
                  "variable": [{"id": 0, "variableId": "var-year", "attribute": None}]},
                 {"tabPropertyId": PAYLOAD, "value": {"headers": [], "queryParams": []},
                  "variable": []},
             ],
             "customData": {"configuration": [{"settings": [
                 {"id": "side", "type": "side-pannel", "label": "Configure Request", "value": [
                     {"id": ENDPOINT, "label": "Endpoint", "value": "https://old.example/xvar-year.xml"},
                     {"id": PAYLOAD, "label": "Request Parameters", "value": {}},
                 ]},
             ]}]}},
        ],
    }


def test_find_node_by_id_and_by_label():
    f = _flow()
    assert nodeparam.find_node(f, "act-1")["id"] == "act-1"
    assert nodeparam.find_node(f, "Get all by year")["id"] == "act-1"
    assert nodeparam.find_node(f, "nope") is None


def test_find_param_by_label_and_by_id():
    n = _flow()["actions"][0]
    assert nodeparam.find_param(n, "Endpoint")["tabPropertyId"] == ENDPOINT
    assert nodeparam.find_param(n, "endpoint")["tabPropertyId"] == ENDPOINT   # case-insensitive
    assert nodeparam.find_param(n, ENDPOINT)["tabPropertyId"] == ENDPOINT
    assert nodeparam.find_param(n, "Missing") is None


def test_describe_node_labels_binds_and_editability():
    f = _flow()
    d = nodeparam.describe_node(f, f["actions"][0])
    by_label = {p["label"]: p for p in d["parameters"]}
    assert by_label["Endpoint"]["editable"] is True
    assert by_label["Endpoint"]["binds"] == [{"index": 0, "variable": "year", "id": "var-year"}]
    assert by_label["Request Parameters"]["editable"] is False
    assert by_label["Request Parameters"]["value"] == "<structured>"


def test_set_param_value_rewrites_host_and_keeps_binding():
    f = _flow()
    n = f["actions"][0]
    p = nodeparam.find_param(n, "Endpoint")
    r = nodeparam.set_param_value(n, p, "https://new.example/x<%0%>.xml")
    assert r["changed"] is True
    assert p["value"] == "https://new.example/x<%0%>.xml"
    assert p["variable"] == [{"id": 0, "variableId": "var-year", "attribute": None}]


def test_set_param_value_is_noop_when_identical():
    f = _flow()
    n = f["actions"][0]
    p = nodeparam.find_param(n, "Endpoint")
    assert nodeparam.set_param_value(n, p, p["value"])["changed"] is False


def test_structured_parameter_is_refused():
    f = _flow()
    n = f["actions"][0]
    p = nodeparam.find_param(n, "Request Parameters")
    with pytest.raises(ValueError, match="not text"):
        nodeparam.set_param_value(n, p, "anything")


def test_dropping_a_placeholder_is_refused_unless_opted_in():
    f = _flow()
    n = f["actions"][0]
    p = nodeparam.find_param(n, "Endpoint")
    with pytest.raises(ValueError, match="placeholder set"):
        nodeparam.set_param_value(n, p, "https://new.example/fixed.xml")
    nodeparam.set_param_value(n, p, "https://new.example/fixed.xml", allow_binding_change=True)
    assert p["value"] == "https://new.example/fixed.xml"


def test_placeholders_reports_the_binding_contract():
    assert nodeparam.placeholders("a<%1%>b<%0%>c<%1%>") == [0, 1]
    assert nodeparam.placeholders({"not": "a string"}) == []


def _map_node():
    """A Map Data node shaped like the live DTO: the runtime row holds `<%1%>-12-01`, the designer
    mirror the same literal appended to the variable GUID. The literal is identical in both."""
    return {
        "id": "map-1", "actionName": "set start currentDate", "actionTemplateName": "Map Data",
        "parameters": [{"tabPropertyId": "map-pid", "variable": [], "value": [
            {"id": 0, "slugId": "map-process-data",
             "source": {"value": "<%1%>-12-01", "variable": [{"id": 1, "variableId": "var-year"}]},
             "destination": {"id": 0, "variableId": "var-cur"}},
            {"id": 1, "slugId": "map-process-data",
             "source": {"value": "<%3%>-12-01", "variable": [{"id": 3, "variableId": "var-year"}]},
             "destination": {"id": 2, "variableId": "var-last"}},
        ]}],
        "customData": {"configuration": [{"settings": [
            {"id": "side", "type": "side-pannel", "label": "Map Process Data", "value": [
                {"id": "map-pid", "label": "Map Process Variables", "type": "map-process-data",
                 "value": [{"id": 0, "destination": "var-cur", "source": "var-year-12-01"},
                           {"id": 1, "destination": "var-last", "source": "var-year-12-01"}]},
            ]},
        ]}]},
    }


def test_replace_text_reaches_both_layers_of_a_structured_parameter():
    n = _map_node()
    hits = nodeparam.replace_text(n, "-12-01", "-01-01")
    assert sum(h["count"] for h in hits) == 4
    assert {h["layer"] for h in hits} == {"runtime", "designer"}
    rows = n["parameters"][0]["value"]
    assert rows[0]["source"]["value"] == "<%1%>-01-01"
    assert rows[1]["source"]["value"] == "<%3%>-01-01"
    designer = n["customData"]["configuration"][0]["settings"][0]["value"][0]["value"]
    assert [r["source"] for r in designer] == ["var-year-01-01", "var-year-01-01"]


def test_replace_text_keeps_variable_bindings_untouched():
    n = _map_node()
    nodeparam.replace_text(n, "-12-01", "-01-01")
    assert n["parameters"][0]["value"][0]["source"]["variable"] == [{"id": 1, "variableId": "var-year"}]


def test_replace_text_reports_nothing_when_the_literal_is_absent():
    n = _map_node()
    assert nodeparam.replace_text(n, "-99-99", "-01-01") == []


def test_replace_text_can_be_narrowed_to_one_property():
    f = _flow()
    n = f["actions"][0]
    hits = nodeparam.replace_text(n, "old.example", "new.example", property_key="Endpoint")
    assert sum(h["count"] for h in hits) == 2          # runtime param + designer mirror
    assert n["parameters"][0]["value"] == "https://new.example/x<%0%>.xml"


def test_replace_text_rejects_an_empty_needle():
    with pytest.raises(ValueError, match="non-empty"):
        nodeparam.replace_text(_map_node(), "", "x")


def _typed_flow():
    return {"id": "f", "title": "T", "actions": [], "variables": [
        {"id": "v-list", "name": "exchangeRateList", "type": 20,
         "dataType": "0317bfee-b2f5-4bde-bfe8-121212121220", "isList": True},
        {"id": "v-out", "name": "exchangeRate", "type": 30,
         "dataType": "0317bfee-b2f5-4bde-bfe8-121212121220", "isList": False},
        {"id": "v-in", "name": "payload", "type": 10,
         "dataType": "0317bfee-b2f5-4bde-bfe8-121212121214", "isList": False},
    ]}


OBJECT = "0317bfee-b2f5-4bde-bfe8-121212121221"


def test_find_variable_by_name_and_id():
    f = _typed_flow()
    assert nodeparam.find_variable(f, "exchangeRateList")["id"] == "v-list"
    assert nodeparam.find_variable(f, "v-out")["name"] == "exchangeRate"
    assert nodeparam.find_variable(f, "ghost") is None


def test_retyping_an_internal_variable_is_allowed():
    f = _typed_flow()
    v = nodeparam.find_variable(f, "exchangeRateList")
    r = nodeparam.set_variable_type(f, v, OBJECT)
    assert r["changed"] is True and r["direction"] == "process"
    assert v["dataType"] == OBJECT and v["isList"] is True     # isList untouched when not passed


def test_retyping_an_output_variable_needs_the_contract_override():
    f = _typed_flow()
    v = nodeparam.find_variable(f, "exchangeRate")
    with pytest.raises(ValueError, match="public contract"):
        nodeparam.set_variable_type(f, v, OBJECT)
    nodeparam.set_variable_type(f, v, OBJECT, allow_contract_change=True)
    assert v["dataType"] == OBJECT


def test_retyping_an_input_variable_needs_the_contract_override():
    f = _typed_flow()
    v = nodeparam.find_variable(f, "payload")
    with pytest.raises(ValueError, match="public contract"):
        nodeparam.set_variable_type(f, v, OBJECT)


def test_retype_is_a_noop_when_already_that_type():
    f = _typed_flow()
    v = nodeparam.find_variable(f, "exchangeRateList")
    assert nodeparam.set_variable_type(f, v, v["dataType"], is_list=True)["changed"] is False


def test_clearing_required_on_an_input_needs_no_override():
    """Loosening cannot break a caller: every payload that was valid stays valid."""
    f = _typed_flow()
    v = nodeparam.find_variable(f, "payload")
    v["isRequired"] = True
    r = nodeparam.set_variable_required(f, v, False)
    assert r["changed"] is True and r["direction"] == "input"
    assert v["isRequired"] is False


def test_making_an_input_required_needs_the_contract_override():
    """Tightening breaks every caller that legitimately omitted the field."""
    f = _typed_flow()
    v = nodeparam.find_variable(f, "payload")
    v["isRequired"] = False
    with pytest.raises(ValueError, match="public contract"):
        nodeparam.set_variable_required(f, v, True)
    nodeparam.set_variable_required(f, v, True, allow_contract_change=True)
    assert v["isRequired"] is True


def test_isrequired_is_refused_on_a_non_input_variable():
    """Only an input carries a caller-supplied value, so the flag means nothing elsewhere."""
    f = _typed_flow()
    for name in ("exchangeRate", "exchangeRateList"):
        with pytest.raises(ValueError, match="only an input variable"):
            nodeparam.set_variable_required(f, nodeparam.find_variable(f, name), False)


def test_setting_required_to_its_current_value_is_a_noop():
    f = _typed_flow()
    v = nodeparam.find_variable(f, "payload")
    v["isRequired"] = True
    assert nodeparam.set_variable_required(f, v, True)["changed"] is False


def test_add_variable_appends_and_is_addressable_by_name_and_id():
    f = _typed_flow()
    before = len(f["variables"])
    v = nodeparam.add_variable(f, "historyText", "string", "output")
    assert len(f["variables"]) == before + 1
    assert v["type"] == 30 and v["isList"] is False and v["isRequired"] is False
    assert nodeparam.find_variable(f, "historyText")["id"] == v["id"]
    assert nodeparam.find_variable(f, v["id"])["name"] == "historyText"


def test_add_variable_refuses_a_duplicate_name():
    """The form-event tooling resolves names to ids, so two same-named variables are ambiguous."""
    f = _typed_flow()
    with pytest.raises(ValueError, match="already exists"):
        nodeparam.add_variable(f, "payload", "string", "input")


def test_add_variable_refuses_an_unknown_direction_or_type():
    f = _typed_flow()
    with pytest.raises(ValueError, match="direction must be"):
        nodeparam.add_variable(f, "x", "string", "sideways")
    with pytest.raises(ValueError, match="unknown data type"):
        nodeparam.add_variable(f, "y", "stringy", "output")


def _chain_flow():
    """start -> a -> b -> stop, ports living on the SOURCE action."""
    def port(src, dst):
        return {"id": f"p-{src}-{dst}", "flowId": "f", "sourceId": src, "destinationId": dst}
    return {"id": "f", "title": "T", "variables": [], "actions": [
        {"id": "a", "actionName": "a", "actionTemplateName": "Node", "ports": [port("a", "b")]},
        {"id": "b", "actionName": "b", "actionTemplateName": "Node", "ports": [port("b", "stop")]},
    ]}


def test_insert_node_takes_the_successor_and_repoints_the_anchor():
    """Both edits, or the graph is broken in a way that still validates."""
    f = _chain_flow()
    anchor = f["actions"][0]
    new = {"id": "n", "actionName": "mid", "actionTemplateName": "Node"}
    ok, msg = nodeparam.insert_node(f, anchor, new)
    assert ok and "between" in msg
    assert anchor["ports"][0]["destinationId"] == "n"          # anchor now points at the new node
    assert new["ports"][0]["destinationId"] == "b"             # new node inherited the successor
    assert [a["id"] for a in f["actions"]] == ["a", "b", "n"]


def test_insert_node_after_a_tail_node_needs_no_successor():
    f = _chain_flow()
    tail = f["actions"][1]
    tail["ports"] = []                                          # nothing downstream
    ok, msg = nodeparam.insert_node(f, tail, {"id": "n", "actionName": "mid"})
    assert ok and "no successor" in msg
    assert f["actions"][-1]["id"] == "n"


def test_insert_node_refuses_a_branching_anchor():
    """Which branch the new node belongs on is a design decision, not a default."""
    f = _chain_flow()
    a = f["actions"][0]
    a["ports"].append({"id": "p2", "sourceId": "a", "destinationId": "b"})
    ok, msg = nodeparam.insert_node(f, a, {"id": "n"})
    assert ok is False and "outgoing ports" in msg


def test_insert_node_refuses_an_anchor_from_another_flow():
    f = _chain_flow()
    ok, msg = nodeparam.insert_node(f, {"id": "ghost", "actionName": "ghost"}, {"id": "n"})
    assert ok is False and "not in this flow" in msg


def test_to_live_action_lowercases_the_dto_and_its_parameter_rows():
    """The builder emits the CREATE shape; a live flow is camelCase. Splicing one into the
    other unconverted is accepted by the API and renders inconsistently."""
    dto = {"Id": "n", "FlowId": "f", "ActionName": "mid", "CustomData": {"name": "mid"},
           "Parameters": [{"TabPropertyId": "t", "Value": "v", "Variable": []}]}
    live = nodeparam.to_live_action(dto)
    assert set(live) == {"id", "flowId", "actionName", "customData", "parameters"}
    assert live["parameters"][0] == {"tabPropertyId": "t", "value": "v", "variable": []}
    assert live["customData"] == {"name": "mid"}


def test_add_variable_resolves_aliases_and_passes_guids_through():
    f = _typed_flow()
    assert nodeparam.add_variable(f, "a", "string", "process")["dataType"].endswith("121214")
    assert nodeparam.add_variable(f, "b", "file", "input")["dataType"].endswith("121219")
    assert nodeparam.add_variable(f, "c", OBJECT, "output")["dataType"] == OBJECT


def test_defaulting_a_process_variable_needs_no_override():
    """A process variable has no caller and no signature, so stamping its default breaks nobody."""
    f = _typed_flow()
    v = nodeparam.find_variable(f, "exchangeRateList")
    r = nodeparam.set_variable_default(f, v, [1, 2])
    assert r["changed"] is True and r["direction"] == "process"
    assert r["before"] == {"defaultValue": None} and v["defaultValue"] == [1, 2]


def test_defaulting_an_input_needs_the_contract_override():
    """Changing what a run does when the caller supplies nothing is a contract change, even
    though the signature is untouched - so the refusal has to come before the write."""
    f = _typed_flow()
    v = nodeparam.find_variable(f, "payload")
    with pytest.raises(ValueError, match="allow-contract-change"):
        nodeparam.set_variable_default(f, v, {"a": 1})
    assert "defaultValue" not in v
    nodeparam.set_variable_default(f, v, {"a": 1}, allow_contract_change=True)
    assert v["defaultValue"] == {"a": 1}


def test_the_output_direction_is_guarded_too():
    """Both signature-bearing directions are behind the flag, not just the input one."""
    f = _typed_flow()
    with pytest.raises(ValueError, match="is an output variable"):
        nodeparam.set_variable_default(f, nodeparam.find_variable(f, "exchangeRate"), 1.5)


def test_clearing_a_default_is_guarded_as_well_unlike_isrequired():
    """The asymmetry between this and set_variable_required: loosening `isRequired` can never
    break a caller, so it is allowed outright - but REMOVING a default is as much a contract
    change as adding one, because a caller that omitted the field now gets nothing instead of
    the value it silently relied on. The guard is on the DIRECTION, so it fires either way."""
    f = _typed_flow()
    v = nodeparam.find_variable(f, "payload")
    v["defaultValue"] = {"a": 1}
    with pytest.raises(ValueError, match="allow-contract-change"):
        nodeparam.set_variable_default(f, v, None)
    assert v["defaultValue"] == {"a": 1}
    assert nodeparam.set_variable_default(f, v, None, allow_contract_change=True)["changed"] is True
    assert v["defaultValue"] is None


def test_setting_a_default_to_its_current_value_is_a_noop():
    """`changed` drives whether the caller PUTs at all; a false positive is a pointless write."""
    f = _typed_flow()
    v = nodeparam.find_variable(f, "exchangeRateList")
    v["defaultValue"] = [1, 2]
    assert nodeparam.set_variable_default(f, v, [1, 2])["changed"] is False


def test_the_default_is_written_into_the_flow_not_a_copy():
    """The patch is in place: the caller PUTs the flow it passed in, so a write to a detached
    copy would validate, upload, and change nothing."""
    f = _typed_flow()
    nodeparam.set_variable_default(f, nodeparam.find_variable(f, "exchangeRateList"), "x")
    assert [v.get("defaultValue") for v in f["variables"]] == ["x", None, None]


def test_set_variable_default_changes_process_var():
    f = _typed_flow()
    f['variables'][0]['defaultValue'] = 'old-event-id'
    v = nodeparam.find_variable(f, 'exchangeRateList')
    r = nodeparam.set_variable_default(f, v, 'new-event-id')
    assert r['changed'] is True and r['direction'] == 'process'
    assert r['before'] == {'defaultValue': 'old-event-id'}
    assert r['after'] == {'defaultValue': 'new-event-id'}
    assert v['defaultValue'] == 'new-event-id'


def test_set_variable_default_is_a_noop_when_already_that_value():
    f = _typed_flow()
    f['variables'][0]['defaultValue'] = 'same'
    v = nodeparam.find_variable(f, 'exchangeRateList')
    assert nodeparam.set_variable_default(f, v, 'same')['changed'] is False


def test_set_variable_default_allowed_on_input_and_output_vars():
    f = _typed_flow()
    # settable on both directions - but it changes what a run does when the caller says
    # nothing, so unlike a process var it is an EXPLICIT contract change, not a free edit
    for name in ('payload', 'exchangeRate'):
        v = nodeparam.find_variable(f, name)
        r = nodeparam.set_variable_default(f, v, {'k': 1}, allow_contract_change=True)
        assert r['changed'] is True and v['defaultValue'] == {'k': 1}


def test_set_process_title_changes_and_is_noop_when_same():
    f = _typed_flow()
    r = nodeparam.set_process_title(f, 'New Name')
    assert r['changed'] is True and r['before'] == 'T' and f['title'] == 'New Name'
    assert nodeparam.set_process_title(f, 'New Name')['changed'] is False


def test_bind_param_var_turns_literal_token_into_a_bound_placeholder():
    node = {"actionName": "Send Email",
            "parameters": [{"tabPropertyId": "body", "value": "Hey <%firstName%>, welcome", "variable": []}]}
    param = node["parameters"][0]
    r = nodeparam.bind_param_var(node, param, {0: "v-first"}, find="<%firstName%>", replace="<%0%>")
    assert r["value_changed"] is True
    assert param["value"] == "Hey <%0%>, welcome"
    assert param["variable"] == [{"id": 0, "variableId": "v-first", "attribute": None}]


def test_bind_param_var_refuses_mismatched_placeholder_and_binding_sets():
    node = {"actionName": "N", "parameters": [{"tabPropertyId": "body", "value": "Hey <%0%>", "variable": []}]}
    param = node["parameters"][0]
    import pytest as _pt
    with _pt.raises(ValueError, match="each"):
        nodeparam.bind_param_var(node, param, {0: "a", 1: "b"})  # value has only <%0%>


def test_bind_param_var_refuses_a_structured_value():
    node = {"actionName": "N", "parameters": [{"tabPropertyId": "body", "value": {"x": 1}, "variable": []}]}
    import pytest as _pt
    with _pt.raises(ValueError, match="structured"):
        nodeparam.bind_param_var(node, node["parameters"][0], {0: "a"})


def test_handler_variable_set_default_accepts_clear_alone(monkeypatch):
    """Regression on the HANDLER's argument plumbing, which the library tests above never
    reach. `--clear` alone (no --value / --value-file) must clear a process variable's
    default. The guard used to raise 'nothing to set' one line before the --clear branch,
    so --clear was refused by an error that named --clear as the remedy and only worked as
    `--clear --value ""`. The validate/lint/save tail is stubbed so this asserts on the
    plumbing, not the network."""
    from types import SimpleNamespace
    from tools.procesio.handlers import nodeparams

    flow = {"id": "p1", "title": "T", "actions": [], "variables": [
        {"id": "v", "name": "eventId", "type": 20,
         "dataType": "0317bfee-b2f5-4bde-bfe8-121212121220",
         "isList": False, "defaultValue": "stale"}]}

    class _Client:
        def get(self, path):
            return flow

    monkeypatch.setattr(nodeparams, "_validate", lambda c, f: (True, None))
    monkeypatch.setattr(nodeparams, "_lint", lambda c, f: [])
    args = SimpleNamespace(id="p1", variable="eventId", value=None, value_file=None,
                           clear=True, json=False, allow_contract_change=False, dry_run=True)

    res = nodeparams.variable_set_default(_Client(), args)   # must not raise
    assert res["variable"] == "eventId"
    assert res["changed"] is True
    assert flow["variables"][0]["defaultValue"] is None       # the default was actually cleared


def test_handler_variable_set_default_rejects_clear_with_a_value():
    """The other half of the fix: --clear combined with --value hides which one wins, so it
    is refused up front rather than silently letting one shadow the other."""
    from types import SimpleNamespace
    from tools.procesio.handlers import nodeparams
    from tools.procesio.errors import UsageError

    flow = {"id": "p1", "title": "T", "actions": [], "variables": [
        {"id": "v", "name": "eventId", "type": 20, "defaultValue": "stale"}]}

    class _Client:
        def get(self, path):
            return flow

    args = SimpleNamespace(id="p1", variable="eventId", value="x", value_file=None,
                           clear=True, json=False, allow_contract_change=False, dry_run=True)
    with pytest.raises(UsageError, match="do not combine it with"):
        nodeparams.variable_set_default(_Client(), args)



# --------------------------------------------------------------------------- error ports

def _err_flow():
    """Two nodes in a line: a Call API that can fault, and the Node that consumes its response.

    Shaped like the live DTO on the detail that matters here - ports live on the SOURCE action and
    carry `destinationId` - because an error port written on the wrong side validates and never
    fires.
    """
    return {
        "id": "flow-e", "title": "Bootstrap",
        "variables": [{"id": "var-res", "name": "response", "type": 20}],
        "actions": [
            {"id": "call-1", "actionName": "List the workspace credentials",
             "actionTemplateName": "Call API", "variableErrorId": None,
             "parameters": [], "customData": {},
             "ports": [{"id": "p1", "flowId": "flow-e", "sourceId": "call-1",
                        "destinationId": "node-1", "type": 0, "state": 1, "data": {}}]},
            {"id": "node-1", "actionName": "Keep only the calendar ones",
             "actionTemplateName": "Node", "parameters": [], "customData": {}, "ports": []},
            {"id": "join-1", "actionName": "Join", "actionTemplateName": "Join",
             "parameters": [], "customData": {}, "ports": []},
        ],
    }


def test_an_error_port_is_written_as_all_three_parts():
    flow = _err_flow()
    node = nodeparam.find_node(flow, "List the workspace credentials")
    handler = nodeparam.find_node(flow, "Keep only the calendar ones")
    report = nodeparam.set_error_port(flow, node, handler)

    err = [p for p in node["ports"] if p["type"] == 1]
    assert len(err) == 1
    assert err[0]["destinationId"] == "node-1"
    assert err[0]["data"] == {"isDefault": "error"}          # the port
    var = next(v for v in flow["variables"] if v["id"] == node["variableErrorId"])
    assert var["isError"] is True                             # the variable
    assert var["dataType"] == nodeparam.ERROR_DATA_MODEL      # of the only accepted datatype
    assert report["handler"] == "Keep only the calendar ones"
    assert report["variable_created"] is True


def test_the_normal_port_is_left_alone():
    flow = _err_flow()
    node = nodeparam.find_node(flow, "List the workspace credentials")
    nodeparam.set_error_port(flow, node, nodeparam.find_node(flow, "Keep only the calendar ones"))
    normal = [p for p in node["ports"] if p["type"] == 0]
    assert len(normal) == 1 and normal[0]["id"] == "p1" and normal[0]["destinationId"] == "node-1"


def test_rewiring_replaces_the_port_rather_than_adding_a_second():
    flow = _err_flow()
    node = nodeparam.find_node(flow, "List the workspace credentials")
    nodeparam.set_error_port(flow, node, nodeparam.find_node(flow, "Keep only the calendar ones"))
    first_var = node["variableErrorId"]
    report = nodeparam.set_error_port(flow, node, nodeparam.find_node(flow, "Join"))
    assert len([p for p in node["ports"] if p["type"] == 1]) == 1
    assert report["handler_before"] == "node-1"
    assert node["variableErrorId"] == first_var               # the variable is reused, not duplicated
    assert len([v for v in flow["variables"] if v.get("isError")]) == 1


def test_a_half_wired_error_variable_is_repaired_not_trusted():
    """A plain string variable in that slot validates and the port never fires, so the shape is
    corrected on the way past rather than left as the caller found it."""
    flow = _err_flow()
    flow["variables"].append({"id": "var-bad", "name": "oops", "type": 20,
                              "dataType": "0317bfee-b2f5-4bde-bfe8-121212121214", "isError": False})
    node = nodeparam.find_node(flow, "List the workspace credentials")
    node["variableErrorId"] = "var-bad"
    nodeparam.set_error_port(flow, node, nodeparam.find_node(flow, "Keep only the calendar ones"))
    var = next(v for v in flow["variables"] if v["id"] == "var-bad")
    assert var["isError"] is True and var["dataType"] == nodeparam.ERROR_DATA_MODEL


def test_clear_removes_the_port_and_its_now_unused_variable():
    flow = _err_flow()
    node = nodeparam.find_node(flow, "List the workspace credentials")
    nodeparam.set_error_port(flow, node, nodeparam.find_node(flow, "Keep only the calendar ones"))
    report = nodeparam.set_error_port(flow, node, None, clear=True)
    assert [p for p in node["ports"] if p["type"] == 1] == []
    assert node["variableErrorId"] is None
    assert [v for v in flow["variables"] if v.get("isError")] == []
    assert report["cleared"] is True and report["handler_before"] == "node-1"


def test_a_template_without_an_error_port_is_refused():
    flow = _err_flow()
    with pytest.raises(ValueError) as e:
        nodeparam.set_error_port(flow, nodeparam.find_node(flow, "Join"),
                                 nodeparam.find_node(flow, "Keep only the calendar ones"))
    assert "no error port" in str(e.value)


def test_a_node_cannot_handle_its_own_error():
    flow = _err_flow()
    node = nodeparam.find_node(flow, "List the workspace credentials")
    with pytest.raises(ValueError) as e:
        nodeparam.set_error_port(flow, node, node)
    assert "its own error" in str(e.value)


def test_a_handler_outside_the_flow_is_refused():
    flow = _err_flow()
    node = nodeparam.find_node(flow, "List the workspace credentials")
    with pytest.raises(ValueError) as e:
        nodeparam.set_error_port(flow, node, {"id": "elsewhere", "actionName": "Other"})
    assert "not in this flow" in str(e.value)


# --------------------------------------------------------------------------- Query Store nodes

def _qs_node(statement="SELECT <%0%>\nFROM <%1%>", chips=None, pmap=None):
    return {"id": "qs-1", "actionName": "Read the meetings 1",
            "actionTemplateName": "Query Store", "customData": {}, "ports": [],
            "parameters": [
                {"tabPropertyId": "02577ada-0000-0200-0000-00000000b102", "value": statement,
                 "variable": chips if chips is not None else [{"id": 0}, {"id": 1}]},
                {"tabPropertyId": "02577ada-0000-0200-0000-00000000b103", "value": pmap or [],
                 "variable": []},
                {"tabPropertyId": "02577ada-0000-0200-0000-00000000b104", "value": "1800",
                 "variable": []},
            ]}


def test_the_statement_and_its_params_map_are_found_by_property_suffix():
    node = _qs_node()
    query, pmap = nodeparam.find_query_params(node)
    assert query["value"].startswith("SELECT")
    assert pmap["value"] == []


def test_a_node_with_no_statement_reports_none():
    node = {"id": "n", "actionName": "Some node", "actionTemplateName": "Node",
            "parameters": [{"tabPropertyId": "whatever-else", "value": "x"}]}
    assert nodeparam.find_query_params(node) == (None, None)


def test_a_non_empty_params_map_is_visible_to_the_caller():
    """The guard that protects a bound @param lives in the handler, so the model has to hand the
    map back rather than hide it."""
    node = _qs_node(pmap=[{"id": 0, "source": {"value": "<%7%>"},
                           "destination": {"value": "e", "variable": []}}])
    _, pmap = nodeparam.find_query_params(node)
    assert pmap["value"] and pmap["value"][0]["destination"]["value"] == "e"


def _qs_full():
    """A Query Store node shaped like the live release step: statement chips 0-4, a parameters map
    on 5-7, and an output binding on 8 - one sequence across three parameters."""
    return {"id": "qs", "actionName": "Update the meetings 3", "actionTemplateName": "Query Store",
            "customData": {}, "ports": [], "parameters": [
                {"tabPropertyId": "x-b102",
                 "value": "UPDATE <%0%>\nSET <%1%> = 'Cancelled', <%2%> = NULL\n"
                          "WHERE <%3%> = @mid\nAND <%4%> = 'Confirmed'",
                 "variable": [{"id": i} for i in range(5)]},
                {"tabPropertyId": "x-b103", "value": [
                    {"id": 0, "source": {"value": "<%5%>", "variable": [{"id": 5, "variableId": "v-row"}]},
                     "destination": {"value": "mid", "variable": []}},
                    {"id": 1, "source": {"value": "<%6%>", "variable": [{"id": 6, "variableId": "v-st"}]},
                     "destination": {"value": "status", "variable": []}},
                ], "variable": []},
                {"tabPropertyId": "x-b104", "value": "1800", "variable": []},
                {"tabPropertyId": "x-b106", "value": "<%7%>",
                 "variable": [{"id": 7, "variableId": "v-out"}]},
            ]}


def test_renumbering_keeps_one_sequence_across_every_parameter():
    node = _qs_full()
    query, pmap = nodeparam.find_query_params(node)
    nxt = nodeparam.renumber_node_placeholders(node, [query, pmap])
    assert nxt == 8
    assert node["parameters"][0]["value"].startswith("UPDATE <%0%>")
    rows = node["parameters"][1]["value"]
    assert [r["source"]["value"] for r in rows] == ["<%5%>", "<%6%>"]
    assert node["parameters"][3]["value"] == "<%7%>"      # the output keeps its place at the end


def test_growing_the_map_pushes_the_output_binding_along():
    """The failure this exists to stop: two more map rows and the output index moves, so an output
    left at its old number is written back to the wrong variable."""
    node = _qs_full()
    query, pmap = nodeparam.find_query_params(node)
    pmap["value"].append({"id": 2, "source": {"value": "<%99%>",
                                              "variable": [{"id": 99, "variableId": "v-new"}]},
                          "destination": {"value": "event", "variable": []}})
    nodeparam.renumber_node_placeholders(node, [query, pmap])
    rows = node["parameters"][1]["value"]
    assert [r["source"]["value"] for r in rows] == ["<%5%>", "<%6%>", "<%7%>"]
    assert [r["source"]["variable"][0]["id"] for r in rows] == [5, 6, 7]
    out = node["parameters"][3]
    assert out["value"] == "<%8%>" and out["variable"][0]["id"] == 8


def test_binding_ids_and_their_value_stay_in_step():
    node = _qs_full()
    query, pmap = nodeparam.find_query_params(node)
    nodeparam.renumber_node_placeholders(node, [query, pmap])
    for p in node["parameters"]:
        for b in p.get("variable") or []:
            if isinstance(b.get("id"), int) and isinstance(p.get("value"), str):
                assert ("<%%%d%%>" % b["id"]) in p["value"] or p["tabPropertyId"].endswith("b102")


# --------------------------------------------------------------------------- structured bindings

def _body_node():
    """A Call API node whose Request Parameters is a dict holding a JSON template - the shape that
    bind_param_var refuses and that an HTTP body always has."""
    return {"id": "api-1", "actionName": "Create the calendar event",
            "actionTemplateName": "Call API", "customData": {}, "ports": [],
            "parameters": [{
                "tabPropertyId": "x-0003",
                "value": {"body": {"type": "RAW", "value": {"RAW": {
                    "format": "json",
                    "value": '{\n  "summary": "<%4%>",\n  "start": {\n    "dateTime": "<%8%>"\n  }\n}'}}},
                          "headers": [], "queryParams": []},
                "variable": [{"id": 4, "variableId": "v-row",
                              "attribute": {"attributeId": "a-name", "nextAttribute": None}},
                             {"id": 8, "variableId": "v-row",
                              "attribute": {"attributeId": "a-start", "nextAttribute": None}}],
            }]}


def test_a_binding_can_be_added_inside_a_structured_parameter():
    node = _body_node()
    p = node["parameters"][0]
    report = nodeparam.add_param_bindings(
        node, p, {12: {"variableId": "v-row", "attributeId": "a-zone"}},
        find='"dateTime": "<%8%>"',
        replace='"dateTime": "<%8%>",\n    "timeZone": "<%12%>"')
    raw = p["value"]["body"]["value"]["RAW"]["value"]
    assert '"timeZone": "<%12%>"' in raw
    assert report["replacements"] == 1 and report["bindings_total"] == 3
    new = next(b for b in p["variable"] if b["id"] == 12)
    assert new["attribute"] == {"attributeId": "a-zone", "nextAttribute": None}


def test_the_existing_bindings_are_kept_with_their_attribute_paths():
    node = _body_node()
    p = node["parameters"][0]
    nodeparam.add_param_bindings(node, p, {12: {"variableId": "v-row", "attributeId": "a-zone"}},
                                 find='"dateTime": "<%8%>"',
                                 replace='"dateTime": "<%8%>",\n    "timeZone": "<%12%>"')
    by_id = {b["id"]: b for b in p["variable"]}
    assert by_id[4]["attribute"]["attributeId"] == "a-name"
    assert by_id[8]["attribute"]["attributeId"] == "a-start"


def test_a_placeholder_left_unbound_is_refused():
    node = _body_node()
    p = node["parameters"][0]
    with pytest.raises(ValueError) as e:
        nodeparam.add_param_bindings(node, p, {}, find='"<%8%>"',
                                     replace='"<%8%>", "timeZone": "<%12%>"')
    assert "exactly one binding" in str(e.value)


def test_a_binding_with_no_placeholder_is_refused():
    node = _body_node()
    p = node["parameters"][0]
    with pytest.raises(ValueError) as e:
        nodeparam.add_param_bindings(node, p, {99: {"variableId": "v-row", "attributeId": "a-x"}})
    assert "exactly one binding" in str(e.value)


def test_a_binding_with_no_attribute_is_written_as_the_whole_variable():
    node = _body_node()
    p = node["parameters"][0]
    nodeparam.add_param_bindings(node, p, {12: {"variableId": "v-other"}},
                                 find='"dateTime": "<%8%>"',
                                 replace='"dateTime": "<%8%>",\n    "tz": "<%12%>"')
    assert next(b for b in p["variable"] if b["id"] == 12)["attribute"] is None


def test_find_text_that_is_absent_is_refused():
    node = _body_node()
    p = node["parameters"][0]
    with pytest.raises(ValueError) as e:
        nodeparam.add_param_bindings(node, p, {}, find="nothing like this", replace="x")
    assert "not present" in str(e.value)
