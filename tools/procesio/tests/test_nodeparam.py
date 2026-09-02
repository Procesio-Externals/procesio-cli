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
