"""Execute Command <-> Execute Query family conversion + Output rebinding (flowmodel/sqlparam).

Why this exists: a stored procedure that ends in SELECT returns a RESULT SET, and only the
`Execute Query` family carries a result set back into a flow variable. `Execute Command` returns
rows-affected (its Output property is typed `number`), so a Command node pointed at a SELECT-ing
procedure silently discards everything the procedure returns and reports success. Converting the
family is the only fix; the conversion is a role-based property-id remap, exactly like the legacy
template migration, plus the Output setting's designer type.
"""
from __future__ import annotations

import copy

import pytest

from tools.procesio.flowmodel import sqlparam as sp


def _command_node() -> dict:
    """A parameterized Execute Command node whose SQL is an EXEC of a SELECT-ing procedure."""
    sql = "EXEC meet.sp_BookMeeting @MeetingTypeID=@p0, @ClientName=@p1;"
    bind_runtime = [
        {"id": 0, "source": {"value": "<%0%>", "variable": [{"id": 0, "variableId": "var-a", "attribute": None}]},
         "destination": {"value": "p0", "variable": []}},
        {"id": 1, "source": {"value": "<%1%>", "variable": [{"id": 1, "variableId": "var-b", "attribute": None}]},
         "destination": {"value": "p1", "variable": []}},
    ]
    return {
        "id": "node-1",
        "templateId": sp.EC_TEMPLATE_ID,
        "actionName": "meet.sp_BookMeeting",
        "actionTemplateName": "Execute Command",
        "parameters": [
            {"tabPropertyId": sp.EC_PID_CRED, "variable": [], "value": "cred-1"},
            {"tabPropertyId": sp.EC_PID_COMMAND, "variable": [], "value": sql},
            {"tabPropertyId": sp.EC_PID_BIND, "variable": [], "value": bind_runtime},
            {"tabPropertyId": sp.EC_PID_TIMEOUT, "variable": [], "value": "60"},
            {"tabPropertyId": sp.EC_PID_OUTPUT,
             "variable": [{"id": 7, "variableId": "scalar-result", "attribute": None}], "value": "<%7%>"},
        ],
        "customData": {
            "name": "meet.sp_BookMeeting",
            "description": "Execute a custom SQL Command on the target database.",
            "icon": "icon-mssql",
            "configuration": [{
                "id": "cfg-1", "label": "Execute Command", "orderId": 0,
                "settings": [
                    {"id": sp.EC_PID_CRED, "label": "Select Database Server", "type": "credentials",
                     "value": "cred-1"},
                    {"id": sp.EC_PID_SIDEPANEL, "label": "Execute Command", "type": "side-pannel", "value": [
                        {"id": sp.EC_PID_COMMAND, "label": "Command", "type": "code-editor",
                         "language": "sql", "value": sql},
                        {"id": sp.EC_PID_BIND, "label": "Parameters config tab", "type": "map-parameters",
                         "value": [{"id": 0, "destination": "p0", "source": "var-a"},
                                   {"id": 1, "destination": "p1", "source": "var-b"}]},
                        {"id": sp.EC_PID_TIMEOUT, "label": "Time Out", "type": "number", "value": "60"},
                        {"id": sp.EC_PID_OUTPUT, "label": "Output", "type": "number",
                         "value": "scalar-result"},
                    ]},
                ],
            }],
        },
    }


def _pid_values(node: dict) -> dict:
    return {p["tabPropertyId"]: p.get("value") for p in node["parameters"]}


def _settings(node: dict) -> dict:
    """{property id: setting} across the configuration, flattened through the side-pannel."""
    out = {}
    for cfg in node["customData"]["configuration"]:
        for s in cfg["settings"]:
            out[s["id"]] = s
            if isinstance(s.get("value"), list):
                for sub in s["value"]:
                    if isinstance(sub, dict) and "id" in sub:
                        out[sub["id"]] = sub
    return out


# --------------------------------------------------------------------------- convert_family

def test_command_to_query_remaps_every_property_id_in_both_layers():
    node = _command_node()
    changed, msg = sp.convert_family(node, sp.EQ_TEMPLATE)

    assert changed is True
    assert "Execute Command -> Execute Query" in msg
    assert node["templateId"] == sp.EQ_TEMPLATE_ID
    assert node["actionTemplateName"] == sp.EQ_TEMPLATE

    runtime = _pid_values(node)
    assert sp.PID_CRED in runtime and sp.EC_PID_CRED not in runtime
    assert sp.PID_QUERY in runtime and sp.EC_PID_COMMAND not in runtime
    assert sp.PID_BIND in runtime and sp.EC_PID_BIND not in runtime
    assert sp.PID_TIMEOUT in runtime and sp.EC_PID_TIMEOUT not in runtime
    assert sp.PID_OUTPUT in runtime and sp.EC_PID_OUTPUT not in runtime

    settings = _settings(node)
    assert sp.PID_QUERY in settings and sp.EC_PID_COMMAND not in settings
    assert sp.PID_BIND in settings and sp.EC_PID_BIND not in settings


def test_conversion_preserves_sql_credential_timeout_and_binding():
    node = _command_node()
    sql_before = _pid_values(node)[sp.EC_PID_COMMAND]
    bind_before = copy.deepcopy(_pid_values(node)[sp.EC_PID_BIND])

    sp.convert_family(node, sp.EQ_TEMPLATE)

    runtime = _pid_values(node)
    assert runtime[sp.PID_QUERY] == sql_before
    assert runtime[sp.PID_CRED] == "cred-1"
    assert runtime[sp.PID_TIMEOUT] == "60"
    assert runtime[sp.PID_BIND] == bind_before, "the @param binding must survive the family change"


def test_conversion_relabels_the_designer_so_the_next_reader_is_not_misled():
    node = _command_node()
    sp.convert_family(node, sp.EQ_TEMPLATE)

    settings = _settings(node)
    assert settings[sp.PID_QUERY]["label"] == "Query"
    assert settings[sp.PID_SIDEPANEL]["label"] == "Execute Query"
    assert node["customData"]["configuration"][0]["label"] == "Execute Query"
    assert "Query" in node["customData"]["description"]
    assert "Command" not in node["customData"]["description"]


def test_output_setting_is_retyped_because_a_query_returns_a_result_set_not_a_count():
    node = _command_node()
    assert _settings(node)[sp.EC_PID_OUTPUT]["type"] == "number"

    sp.convert_family(node, sp.EQ_TEMPLATE)

    assert _settings(node)[sp.PID_OUTPUT]["type"] == "any"


def test_query_to_command_is_the_exact_inverse():
    node = _command_node()
    original = copy.deepcopy(node)

    sp.convert_family(node, sp.EQ_TEMPLATE)
    sp.convert_family(node, sp.EC_TEMPLATE)

    assert node["templateId"] == original["templateId"]
    assert _pid_values(node) == _pid_values(original)
    assert _settings(node)[sp.EC_PID_OUTPUT]["type"] == "number"


def test_converting_to_the_family_it_is_already_on_is_a_no_op():
    node = _command_node()
    before = copy.deepcopy(node)

    changed, msg = sp.convert_family(node, sp.EC_TEMPLATE)

    assert changed is False
    assert "already" in msg
    assert node == before


def test_a_node_on_a_deprecated_template_is_refused_rather_than_half_converted():
    node = _command_node()
    node["templateId"] = "c2760ff2-cd9e-49b4-b751-c05c88e06dac"   # Execute Command V1
    before = copy.deepcopy(node)

    changed, msg = sp.convert_family(node, sp.EQ_TEMPLATE)

    assert changed is False
    assert "deprecated" in msg
    assert node == before, "a refused conversion must not leave the node partly remapped"


def test_a_non_sql_node_is_refused():
    node = {"actionTemplateName": "Node", "templateId": "whatever", "parameters": [], "customData": {}}
    changed, msg = sp.convert_family(node, sp.EQ_TEMPLATE)
    assert changed is False
    assert "SQL" in msg


def test_an_unknown_target_family_raises_rather_than_silently_doing_nothing():
    with pytest.raises(ValueError):
        sp.convert_family(_command_node(), "Execute Something")


# --------------------------------------------------------------------------- rebind_output

def test_rebind_output_moves_both_layers_to_the_new_variable():
    node = _command_node()
    sp.convert_family(node, sp.EQ_TEMPLATE)

    changed, _ = sp.rebind_output(node, "resultset-var")

    assert changed is True
    out = next(p for p in node["parameters"] if p["tabPropertyId"] == sp.PID_OUTPUT)
    assert out["variable"][0]["variableId"] == "resultset-var"
    assert _settings(node)[sp.PID_OUTPUT]["value"] == "resultset-var"


def test_rebind_output_keeps_the_positional_slot_so_it_cannot_collide_with_a_param_bind():
    node = _command_node()
    sp.convert_family(node, sp.EQ_TEMPLATE)
    slot_before = next(p for p in node["parameters"] if p["tabPropertyId"] == sp.PID_OUTPUT)["value"]

    sp.rebind_output(node, "resultset-var")

    out = next(p for p in node["parameters"] if p["tabPropertyId"] == sp.PID_OUTPUT)
    assert out["value"] == slot_before == "<%7%>"
    bound = {b["source"]["value"] for b in _pid_values(node)[sp.PID_BIND]}
    assert out["value"] not in bound


def test_rebind_output_to_the_same_variable_reports_no_change():
    node = _command_node()
    changed, msg = sp.rebind_output(node, "scalar-result")
    assert changed is False
    assert "already" in msg


def test_rebind_output_seeds_the_binding_when_the_node_has_none():
    node = _command_node()
    out = next(p for p in node["parameters"] if p["tabPropertyId"] == sp.EC_PID_OUTPUT)
    out["variable"] = []
    out["value"] = None

    changed, _ = sp.rebind_output(node, "fresh-var")

    assert changed is True
    out = next(p for p in node["parameters"] if p["tabPropertyId"] == sp.EC_PID_OUTPUT)
    assert out["variable"][0]["variableId"] == "fresh-var"
    # the slot must sit past every @param bind index, or the engine reads the wrong value
    assert out["value"] == "<%2%>"
