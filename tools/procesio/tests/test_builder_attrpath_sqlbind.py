"""Two builder gaps that only surface when a process is actually SAVED.

1. **Attribute paths were never resolved.** `{"var": "row", "path": ["ToEmail"]}` is documented and
   accepted, but `attr_index` was never populated, so the attribute NAME was written straight into
   `attribute.attributeId` — a field the API parses as a Guid. Every model-typed attribute binding
   was rejected at save time with `Error converting value "ToEmail" to type 'System.Guid'`.

2. **A SQL node was built without its `Parameters config tab`.** The builder emits only the
   properties the caller named; the designer renders that property from the TEMPLATE, finds no
   value, and blocks the save with "Please make sure that the action is defined/configured
   properly". So no `process-create` config containing an Execute Query / Execute Command could be
   saved at all, whether or not it bound any parameter.
"""
from __future__ import annotations

import pytest

from tools.procesio.dto.process import builder
from tools.procesio.errors import UsageError
from tools.procesio.flowmodel import sqlparam


MODEL_ID = "11111111-1111-1111-1111-111111111111"
CHILD_ID = "22222222-2222-2222-2222-222222222222"
TO_EMAIL_ID = "aaaaaaaa-0000-0000-0000-000000000001"
CLIENT_ID = "aaaaaaaa-0000-0000-0000-000000000002"
CITY_ID = "bbbbbbbb-0000-0000-0000-000000000001"


def _ctx_with_model() -> dict:
    """A ctx whose model_attrs is what prepare_ctx builds from GET /api/DataTypes/{id}."""
    return {
        "var_ids": {"row": "var-row"},
        "var_models": {"row": MODEL_ID},
        "model_attrs": {
            MODEL_ID: {
                "toemail": {"id": TO_EMAIL_ID, "name": "ToEmail", "dataTypeId": None},
                "client": {"id": CLIENT_ID, "name": "Client", "dataTypeId": CHILD_ID},
            },
            CHILD_ID: {
                "city": {"id": CITY_ID, "name": "City", "dataTypeId": None},
            },
        },
    }


# ------------------------------------------------------------------ attribute paths

def test_an_attribute_name_resolves_to_its_guid():
    p = builder._make_parameter("prop-1", {"var": "row", "path": ["ToEmail"]},
                                _ctx_with_model(), [0])
    assert p["Variable"][0]["attribute"] == {"attributeId": TO_EMAIL_ID, "nextAttribute": None}


def test_attribute_names_are_matched_case_insensitively():
    p = builder._make_parameter("prop-1", {"var": "row", "path": ["toemail"]},
                                _ctx_with_model(), [0])
    assert p["Variable"][0]["attribute"]["attributeId"] == TO_EMAIL_ID


def test_a_nested_path_descends_through_the_child_model():
    p = builder._make_parameter("prop-1", {"var": "row", "path": ["Client", "City"]},
                                _ctx_with_model(), [0])
    assert p["Variable"][0]["attribute"] == {
        "attributeId": CLIENT_ID,
        "nextAttribute": {"attributeId": CITY_ID, "nextAttribute": None},
    }


def test_a_guid_passed_directly_is_left_alone():
    """A caller who already knows the attribute id must not need the model resolved."""
    p = builder._make_parameter("prop-1", {"var": "row", "path": [TO_EMAIL_ID]},
                                _ctx_with_model(), [0])
    assert p["Variable"][0]["attribute"]["attributeId"] == TO_EMAIL_ID


def test_an_unknown_attribute_fails_loudly_instead_of_writing_a_name_the_api_rejects():
    with pytest.raises(UsageError) as e:
        builder._make_parameter("prop-1", {"var": "row", "path": ["Nope"]},
                                _ctx_with_model(), [0])
    msg = str(e.value)
    assert "Nope" in msg
    assert "ToEmail" in msg, "the error must name the attributes that DO exist"


def test_a_template_binding_resolves_attribute_paths_the_same_way():
    p = builder._make_parameter(
        "prop-1",
        {"template": "EXEC p @a='<%0%>', @b='<%1%>'",
         "vars": [{"var": "row", "path": ["ToEmail"]}, {"var": "row", "path": ["Client", "City"]}]},
        _ctx_with_model(), [0])
    assert p["Variable"][0]["attribute"]["attributeId"] == TO_EMAIL_ID
    assert p["Variable"][1]["attribute"]["nextAttribute"]["attributeId"] == CITY_ID


def test_no_path_still_means_no_attribute():
    p = builder._make_parameter("prop-1", {"var": "row"}, _ctx_with_model(), [0])
    assert p["Variable"][0]["attribute"] is None


def test_a_variable_with_no_known_model_passes_the_path_through_unchanged():
    """Offline or for an untyped variable, the old pass-through behaviour is the safe fallback."""
    ctx = {"var_ids": {"row": "var-row"}}
    p = builder._make_parameter("prop-1", {"var": "row", "path": ["ToEmail"]}, ctx, [0])
    assert p["Variable"][0]["attribute"]["attributeId"] == "ToEmail"


# ------------------------------------------------------------------ SQL bind property

@pytest.mark.parametrize("template_name,bind_pid", [
    ("Execute Query", sqlparam.PID_BIND),
    ("Execute Command", sqlparam.EC_PID_BIND),
])
def test_a_sql_node_always_carries_its_parameters_config_tab(template_name, bind_pid):
    params = [{"TabPropertyId": "some-other-prop", "Variable": [], "Value": "x"}]
    out = builder._ensure_sql_bind_property({"name": template_name}, params)
    bind = [p for p in out if p["TabPropertyId"] == bind_pid]
    assert len(bind) == 1
    assert bind[0]["Value"] == [], "an unbound SQL node still needs the property, just empty"


def test_an_existing_binding_is_not_overwritten():
    existing = [{"TabPropertyId": sqlparam.PID_BIND, "Variable": [], "Value": [{"id": 0}]}]
    out = builder._ensure_sql_bind_property({"name": "Execute Query"}, existing)
    assert out == existing


def test_a_non_sql_action_is_left_alone():
    params = [{"TabPropertyId": "p", "Variable": [], "Value": "x"}]
    assert builder._ensure_sql_bind_property({"name": "Node"}, params) == params


def test_the_command_family_gets_its_own_bind_id_not_the_query_one():
    out = builder._ensure_sql_bind_property({"name": "Execute Command"}, [])
    pids = {p["TabPropertyId"] for p in out}
    assert sqlparam.EC_PID_BIND in pids
    assert sqlparam.PID_BIND not in pids, (
        "the Query bind id on a Command node leaves every @param unbound at runtime")


# ------------------------------------------------------------------ engine-state properties

def _foreach_template() -> dict:
    """The For Each template as the live catalog serves it: two `ignore` properties carrying the
    engine's loop state, with their seed values already on the template."""
    return {"name": "For Each", "configuration": [{"settings": [
        {"id": "in-list", "label": "In List", "type": "any", "value": None},
        {"id": "timeout", "label": "Action timeout", "type": "number", "value": None},
        {"id": "idx", "label": "Zero based list index", "type": "ignore", "value": "-1"},
        {"id": "started", "label": "Action start time", "type": "ignore",
         "value": "2010-01-01T00:00:00.0000000Z"},
        {"id": "item", "label": "For Each Item", "type": "any", "value": None},
    ]}]}


def test_engine_state_properties_are_seeded_from_the_template():
    """A For Each whose start time is missing times out on its FIRST iteration: the engine compares
    against a default far in the past, so the elapsed time is always over any cap."""
    params = [{"TabPropertyId": "in-list", "Variable": [], "Value": "<%0%>"}]

    out = builder._ensure_engine_state_properties(_foreach_template(), params)

    by_pid = {p["TabPropertyId"]: p["Value"] for p in out}
    assert by_pid["idx"] == "-1"
    assert by_pid["started"] == "2010-01-01T00:00:00.0000000Z"
    assert by_pid["in-list"] == "<%0%>", "the caller's own parameters are untouched"


def test_a_seeded_state_property_is_not_duplicated():
    params = [{"TabPropertyId": "idx", "Variable": [], "Value": "7"}]
    out = builder._ensure_engine_state_properties(_foreach_template(), params)
    idx = [p for p in out if p["TabPropertyId"] == "idx"]
    assert len(idx) == 1 and idx[0]["Value"] == "7"


def test_an_action_with_no_ignore_properties_is_unchanged():
    tpl = {"name": "Node", "configuration": [{"settings": [
        {"id": "code", "label": "Code", "type": "code-editor", "value": None}]}]}
    params = [{"TabPropertyId": "code", "Variable": [], "Value": "x"}]
    assert builder._ensure_engine_state_properties(tpl, params) == params
