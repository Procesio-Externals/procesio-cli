"""form-set-element-event, RUN_DATA_STORE_OPERATION: the form side of a map row.

The right side of a Data Store row is text, and it holds a form value or a typed value. The
form runtime reads as a form value only a chain of ids that starts at the form's data model;
any other text is sent as written. So a field name, or a path built from the names in the
guide's tree, is saved without complaint and then written into the Data Store as the value,
or refused by a typed column with a message about the value and none about the map. The
write is the last place the mistake can be caught.
"""
from __future__ import annotations

import json

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import fieldpath
from tools.procesio.errors import UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
NS = fieldpath.FIELDS_NS
ROOT = "11111111-1111-1111-1111-111111111111"
FORM_ID = "22222222-2222-2222-2222-222222222222"
E_NAME = "33333333-3333-3333-3333-333333333333"
E_SCORE = "44444444-4444-4444-4444-444444444444"
E_TABLE = "55555555-5555-5555-5555-555555555555"
E_ROW = "66666666-6666-6666-6666-666666666666"
E_STATIC = "77777777-7777-7777-7777-777777777777"
E_SELECT = "88888888-8888-8888-8888-888888888888"
V_NAME, V_SCORE = "aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000002"
V_ROW, S_ROW = "aaaaaaaa-0000-0000-0000-000000000003", "aaaaaaaa-0000-0000-0000-000000000004"
V_SELECT, S_SELECT = "aaaaaaaa-0000-0000-0000-000000000005", "aaaaaaaa-0000-0000-0000-000000000006"
VAR = "bbbbbbbb-0000-0000-0000-000000000001"
A_INSTANCE, A_USER, A_ID = ("cccccccc-0000-0000-0000-000000000001",
                            "cccccccc-0000-0000-0000-000000000002",
                            "cccccccc-0000-0000-0000-000000000003")

P_NAME = f"{ROOT}.{NS}.{E_NAME}.{V_NAME}"
P_SCORE = f"{ROOT}.{NS}.{E_SCORE}.{V_SCORE}"
P_ROW_SOURCE = f"{ROOT}.{NS}.{E_ROW}.{S_ROW}"
P_SELECT_SOURCE = f"{ROOT}.{NS}.{E_SELECT}.{S_SELECT}"


def _form(source_type="JSON"):
    def el(eid, etype, name, *configs, parent=None):
        out = {"id": eid, "type": etype,
               "configs": [{"key": "name", "value": name}, *configs]}
        if parent:
            out["parentId"] = parent
        return out

    return {
        "id": FORM_ID, "name": "Scores", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None, "queries": [],
        "data": {
            "code": "",
            "variables": [{"id": ROOT, "name": "form"}, {"id": VAR, "name": "Offer"}],
            "dataModel": {"id": ROOT, "name": "form", "attributes": [
                {"id": A_INSTANCE, "name": "instance", "attributes": [
                    {"id": A_USER, "name": "currentUser", "attributes": [
                        {"id": A_ID, "name": "id", "attributes": []}]}]}]},
            "elements": [
                el("b1", "button", "save", {"key": "onClickEvents", "value": None}),
                el(E_NAME, "input", "playerName", {"key": "value", "id": V_NAME}),
                el(E_SCORE, "number-input", "score", {"key": "value", "id": V_SCORE}),
                el(E_TABLE, "table", "scores"),
                el(E_STATIC, "static-table-row", "scoresHead", parent=E_TABLE),
                el(E_ROW, "dynamic-table-row", "scoresRow", {"key": "value", "id": V_ROW},
                   {"key": "sourceValue", "id": S_ROW}, parent=E_TABLE),
                el(E_SELECT, "select", "pick", {"key": "value", "id": V_SELECT},
                   {"key": "sourceType", "value": source_type},
                   {"key": "sourceValue", "id": S_SELECT}),
            ],
        },
    }


def _set(config, form=None, extra=()):
    session = FakeSession(queue=[FakeResp(200, form or _form()), FakeResp(200, {})])
    out = main.dispatch(
        "form-set-element-event",
        ["--id", FORM_ID, "--element", "save", "--on", "click",
         "--action", "RUN_DATA_STORE_OPERATION", "--config", json.dumps(config), *extra],
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))
    return out, session


def _add(*inputs, **more):
    return {"dataStoreId": "DS1", "operation": "ADD", "inputMap": list(inputs), **more}


def _query(*outputs):
    return {"dataStoreId": "DS1", "operation": "READ", "outputMap": list(outputs)}


def _refused(config, form=None) -> str:
    session = FakeSession(queue=[FakeResp(200, form or _form())])
    with pytest.raises(UsageError) as e:
        main.dispatch(
            "form-set-element-event",
            ["--id", FORM_ID, "--element", "save", "--on", "click",
             "--action", "RUN_DATA_STORE_OPERATION", "--config", json.dumps(config)],
            client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))
    assert [c["method"] for c in session.calls] == ["GET"], "nothing may be written"
    return str(e.value)


def _rights(out, side="inputMap"):
    return [row["right"] for row in out["event"]["config"][side]]


# -- an input: a field, by name ----------------------------------------------

def test_a_field_name_becomes_its_value_path():
    out, session = _set(_add({"left": "playerName", "right": "playerName"},
                             {"left": "score", "right": "score"}))
    assert _rights(out) == [P_NAME, P_SCORE]
    saved = next(c for c in session.calls[-1]["json"]["Data"]["elements"][0]["configs"]
                 if c["key"] == "onClickEvents")["value"]["events"][0]["config"]
    assert [row["right"] for row in saved["inputMap"]] == [P_NAME, P_SCORE]
    assert "typed_values" not in out


def test_an_element_id_and_an_element_config_resolve_too():
    out, _ = _set(_add({"left": "a", "right": E_SCORE}, {"left": "b", "right": "playerName.value"}))
    assert _rights(out) == [P_SCORE, P_NAME]


def test_a_variable_and_a_data_model_name_path_resolve_to_ids():
    out, _ = _set(_add({"left": "a", "right": "@Offer"},
                       {"left": "b", "right": "instance.currentUser.id"}))
    assert _rights(out) == [VAR, f"{ROOT}.{A_INSTANCE}.{A_USER}.{A_ID}"]


def test_a_correct_path_passes_through_untouched():
    out, _ = _set(_add({"left": "a", "right": P_NAME},
                       {"left": "b", "right": f"{ROOT}.{A_INSTANCE}.{A_USER}.{A_ID}"},
                       {"left": "c", "right": VAR}))
    assert _rights(out) == [P_NAME, f"{ROOT}.{A_INSTANCE}.{A_USER}.{A_ID}", VAR]


# -- an input: a path that is nearly right -----------------------------------

def test_a_path_built_from_the_form_id_and_names_is_refused_with_the_right_one():
    msg = _refused(_add({"left": "playerName", "right": f"{FORM_ID}.fields.{E_NAME}.value"}))
    assert "segment 1" in msg and "segment 2 'fields'" in msg
    assert P_NAME in msg and "playerName" in msg


def test_a_value_id_of_another_element_is_refused():
    msg = _refused(_add({"left": "a", "right": f"{ROOT}.{NS}.{E_NAME}.{V_SCORE}"}))
    assert "segment 4" in msg and P_NAME in msg


def test_a_path_with_the_wrong_number_of_segments_is_refused():
    assert "4 segments" in _refused(_add({"left": "a", "right": f"{ROOT}.{E_NAME}"}))


def test_a_wrong_path_inside_a_longer_text_is_refused():
    msg = _refused(_add({"left": "a", "right": f"Score: {ROOT}.{NS}.{E_NAME}.{V_SCORE}"}))
    assert "segment 4" in msg


def test_a_right_path_inside_a_longer_text_is_kept():
    out, _ = _set(_add({"left": "a", "right": f"Score: {P_SCORE} points"}))
    assert _rights(out) == [f"Score: {P_SCORE} points"]


def test_an_unknown_variable_is_refused():
    assert "names no form variable" in _refused(_add({"left": "a", "right": "@Missing"}))


def test_a_field_name_in_another_letter_case_is_refused():
    msg = _refused(_add({"left": "a", "right": "playername"}))
    assert "'playerName' is" in msg and "`value`" in msg


def test_an_element_that_holds_no_value_cannot_be_an_input():
    assert "holds no value" in _refused(_add({"left": "a", "right": "save"}))


# -- an input: `Element.config`, the element by its DOM id --------------------
#
# The `id` config is the DOM id the element carries on the page: the handle a caller holds
# after reading the form's script. A new element starts with its type's word as its DOM id.

def _form_with_dom_ids(**dom_ids):
    form = _form()
    for el in form["data"]["elements"]:
        name = el["configs"][0]["value"]
        if name in dom_ids:
            el["configs"].append({"key": "id", "value": dom_ids[name]})
    return form


def test_an_element_config_is_found_by_the_dom_id():
    form = _form_with_dom_ids(playerName="nameBox", score="scoreBox")
    out, _ = _set(_add({"left": "a", "right": "nameBox.value"},
                       outputMap=[{"left": "success", "right": "scoreBox.value"}]), form)
    assert _rights(out) == [P_NAME]
    assert _rights(out, "outputMap") == [P_SCORE]
    assert "typed_values" not in out


def test_a_name_is_tried_before_a_dom_id():
    form = _form_with_dom_ids(score="playerName")
    out, _ = _set(_add({"left": "a", "right": "playerName.value"}), form)
    assert _rights(out) == [P_NAME]


def test_a_dom_id_before_a_word_that_is_no_config_stays_a_typed_value():
    form = _form_with_dom_ids(playerName="input")
    out, _ = _set(_add({"left": "file", "right": "input.png"}), form)
    assert _rights(out) == ["input.png"]
    assert out["typed_values"] == [{"left": "file", "value": "input.png"}]


def test_a_dom_id_that_several_elements_carry_is_refused_for_a_config_only():
    form = _form_with_dom_ids(playerName="input", score="input")
    msg = _refused(_add({"left": "a", "right": "input.value"}), form)
    assert "2 elements carry the DOM id 'input'" in msg
    assert "'playerName', 'score'" in msg
    out, _ = _set(_add({"left": "file", "right": "input.png"}), form)
    assert _rights(out) == ["input.png"]


# -- an input: a typed value -------------------------------------------------

def test_text_that_names_nothing_is_kept_and_reported():
    out, _ = _set(_add({"left": "status", "right": "open"}, {"left": "host", "right": "10.0.0.1"}))
    assert _rights(out) == ["open", "10.0.0.1"]
    assert out["typed_values"] == [{"left": "status", "value": "open"},
                                   {"left": "host", "value": "10.0.0.1"}]
    assert "typed value" in out["typed_values_note"]


def test_a_number_is_a_typed_value_nobody_needs_told_about():
    out, _ = _set(_add({"left": "qty", "right": "50"}, {"left": "n", "right": 7},
                       {"left": "on", "right": True}))
    assert _rights(out) == ["50", "7", "true"]
    assert "typed_values" not in out


def test_value_states_a_typed_value_even_when_a_field_has_that_name():
    out, _ = _set(_add({"left": "note", "value": "score"}))
    assert out["event"]["config"]["inputMap"] == [{"left": "note", "right": "score", "id": 0}]
    assert "typed_values" not in out


def test_right_and_value_together_are_refused():
    assert "not both" in _refused(_add({"left": "a", "right": "score", "value": "x"}))


def test_an_empty_right_side_stays_empty():
    out, _ = _set(_add({"left": "a", "right": ""}))
    assert _rights(out) == [""]


# -- an output ---------------------------------------------------------------

def test_an_output_takes_a_field_name():
    out, _ = _set(_query({"left": "count", "right": "score"}, {"left": "columns", "right": ""}))
    assert _rights(out, "outputMap") == [P_SCORE, ""]


def test_an_output_is_never_typed_text():
    assert "neither a field" in _refused(_query({"left": "count", "right": "total"}))


def test_an_output_path_built_from_names_is_refused():
    msg = _refused(_query({"left": "count", "right": f"{FORM_ID}.fields.{E_SCORE}.value"}))
    assert P_SCORE in msg


# -- rows: a table shows them through its dynamic row's source ----------------

@pytest.mark.parametrize("target", ["scores", "scoresRow", E_TABLE, E_ROW, P_ROW_SOURCE])
def test_rows_reach_the_dynamic_rows_source(target):
    out, _ = _set(_query({"left": "rows", "right": target}))
    assert _rights(out, "outputMap") == [P_ROW_SOURCE]


@pytest.mark.parametrize("target", [
    f"{ROOT}.{NS}.{E_ROW}.{V_ROW}",                 # the row's own value
    f"{FORM_ID}.fields.{E_ROW}.value",              # the same, built from names
    f"{ROOT}.{NS}.{E_TABLE}.{V_ROW}",               # a path into the table
])
def test_rows_mapped_to_a_value_of_the_table_are_refused_with_the_source_path(target):
    msg = _refused(_query({"left": "rows", "right": target}))
    assert "every cell empty" in msg and P_ROW_SOURCE in msg


def test_rows_cannot_fill_a_static_row_or_a_table_without_a_dynamic_row():
    assert "static table row" in _refused(_query({"left": "rows", "right": "scoresHead"}))
    form = _form()
    form["data"]["elements"] = [e for e in form["data"]["elements"] if e["id"] != E_ROW]
    assert "no dynamic row" in _refused(_query({"left": "rows", "right": "scores"}), form)


def test_rows_fill_a_dropdown_through_its_own_source():
    out, _ = _set(_query({"left": "rows", "right": "pick"}))
    assert _rights(out, "outputMap") == [P_SELECT_SOURCE]
    assert "warnings" not in out


def test_a_dropdown_without_a_source_type_is_warned_about():
    out, _ = _set(_query({"left": "rows", "right": "pick"}), _form(source_type=None))
    assert _rights(out, "outputMap") == [P_SELECT_SOURCE]
    (warning,) = out["warnings"]
    assert "'pick'" in warning and "sourceType" in warning


def test_rows_of_a_write_are_an_ordinary_output():
    """`rows` means a list only where an operation returns one."""
    out, _ = _set(_add(outputMap=[{"left": "success", "right": "score"}]))
    assert _rights(out, "outputMap") == [P_SCORE]


# -- filters -----------------------------------------------------------------

def _filter(value):
    return {"dataStoreId": "DS1", "operation": "READ", "filters": [
        {"id": 0, "operator": "EQUALS", "leftOperator": {"value": "Player"},
         "rightOperator": {"value": value}, "auxOperator": {"value": ""}, "logicOperator": 0}]}


def test_a_filter_keeps_a_typed_value_and_a_right_path():
    for value in ("score", "open", P_NAME):
        out, _ = _set(_filter(value))
        assert out["event"]["config"]["filters"][0]["rightOperator"]["value"] == value


def test_a_filter_path_built_from_names_is_refused():
    msg = _refused(_filter(f"{FORM_ID}.fields.{E_NAME}.value"))
    assert "filter 0 rightOperator" in msg and P_NAME in msg


# -- the other actions are left alone -----------------------------------------

def test_dry_run_reports_the_resolved_rows_and_writes_nothing():
    session = FakeSession(queue=[FakeResp(200, _form())])
    out = main.dispatch(
        "form-set-element-event",
        ["--id", FORM_ID, "--element", "save", "--on", "click", "--dry-run",
         "--action", "RUN_DATA_STORE_OPERATION",
         "--config", json.dumps(_add({"left": "playerName", "right": "playerName"}))],
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))
    assert out["dry_run"] is True and _rights(out) == [P_NAME]
    assert [c["method"] for c in session.calls] == ["GET"]
