"""Adding a control to a LIVE form (flowmodel-free: dto/form/addelement).

Why this exists: `form-create` speaks an authoring config, `form-edit` rebuilds a form from one, and
neither can add a control to a form that was hand-built in the designer — the two shapes are
different languages (the create config has no element ids at all). Everything else in the toolkit is
surgical (set one config, wire one event); adding a control was the missing verb, so a new admin
button meant hand-writing a stored element DTO.

The invariant that makes it safe: PROCESIO backs every control with a data-model sub-model whose id
is the ELEMENT id and whose attribute ids are the ELEMENT'S OWN CONFIG IDS. So new controls can be
SPLICED into the live `Data.dataModel` without touching what is already there — which matters,
because a RUN_PROCESS map references a field by the path `root.fields.elementId.valueAttrId`, and
regenerating those ids would break every existing mapping on the form.
"""
from __future__ import annotations

import copy

import pytest

from tools.procesio.dto.form import addelement
from tools.procesio.errors import UsageError


ROOT = "65396456-36bf-4d9f-8d32-63a4a9e5c8c0"
FIELDS_NS = "11223344-5566-7788-99aa-aabbccddeeff"
EXISTING_EL = "aaaaaaaa-1111-1111-1111-111111111111"
EXISTING_CFG = "bbbbbbbb-2222-2222-2222-222222222222"


def _live_form() -> dict:
    """A form as GET /api/FormTemplate/{id} returns it, with one existing control."""
    return {
        "id": "form-1", "name": "Admin", "isPrivate": True, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {
            "elements": [
                {"id": EXISTING_EL, "type": "input", "section": "body", "parentId": None,
                 "category": "field",
                 "configs": [{"id": EXISTING_CFG, "key": "value", "label": "Value", "value": ""},
                             {"id": "cccccccc-3333-3333-3333-333333333333", "key": "name",
                              "label": "Name", "value": "DefaultTimeZone"}]},
            ],
            "variables": [{"id": ROOT, "dataType": ROOT, "name": "form", "type": 20}],
            "dataModel": {
                "id": ROOT, "name": "form", "attributes": [
                    {"id": FIELDS_NS, "dataTypeId": FIELDS_NS, "name": "fields",
                     "parentDataTypeId": ROOT, "isDataModel": True, "attributes": [
                         {"id": EXISTING_EL, "dataTypeId": EXISTING_EL, "name": "DefaultTimeZone",
                          "parentDataTypeId": FIELDS_NS, "isDataModel": True, "attributes": [
                              {"id": EXISTING_CFG, "name": "value", "parentDataTypeId": EXISTING_EL}]},
                     ]},
                ]},
        },
    }


def _fields_attrs(data: dict) -> list:
    fields = next(a for a in data["dataModel"]["attributes"] if a["id"] == FIELDS_NS)
    return fields["attributes"]


def _by_name(elements: list, name: str):
    for el in elements:
        for c in el.get("configs", []):
            if c.get("key") == "name" and c.get("value") == name:
                return el
    return None


# --------------------------------------------------------------------------- the happy path

def test_a_new_control_is_appended_to_the_elements_list():
    form = _live_form()
    out = addelement.add_elements(form, [{"type": "input", "label": "Organiser Email",
                                          "name": "OrganiserEmail"}])

    assert len(out["elements"]) == 2
    added = _by_name(out["elements"], "OrganiserEmail")
    assert added is not None and added["type"] == "input"


def test_the_existing_control_is_untouched_down_to_its_config_ids():
    form = _live_form()
    before = copy.deepcopy(form["data"]["elements"][0])

    out = addelement.add_elements(form, [{"type": "input", "name": "OrganiserEmail"}])

    assert out["elements"][0] == before


def test_every_existing_data_model_id_survives():
    """A RUN_PROCESS map references root.fields.elementId.valueAttrId — regenerating any of those
    ids silently breaks every mapping already on the form."""
    form = _live_form()
    out = addelement.add_elements(form, [{"type": "input", "name": "OrganiserEmail"}])

    existing = next(s for s in _fields_attrs(out) if s["id"] == EXISTING_EL)
    assert existing["attributes"][0]["id"] == EXISTING_CFG
    assert out["dataModel"]["id"] == ROOT


def test_the_new_control_gets_a_sub_model_keyed_by_its_element_id():
    form = _live_form()
    out = addelement.add_elements(form, [{"type": "input", "name": "OrganiserEmail"}])

    added = _by_name(out["elements"], "OrganiserEmail")
    sub = next((s for s in _fields_attrs(out) if s["id"] == added["id"]), None)
    assert sub is not None
    assert sub["name"] == "OrganiserEmail"
    assert sub["parentDataTypeId"] == FIELDS_NS


def test_the_new_sub_model_attribute_ids_equal_the_new_element_config_ids():
    form = _live_form()
    out = addelement.add_elements(form, [{"type": "input", "name": "OrganiserEmail"}])

    added = _by_name(out["elements"], "OrganiserEmail")
    sub = next(s for s in _fields_attrs(out) if s["id"] == added["id"])
    cfg_ids = {c["id"] for c in added["configs"]}
    assert {a["id"] for a in sub["attributes"]} <= cfg_ids
    assert any(a["name"] == "value" for a in sub["attributes"]), (
        "the value attribute is what a process map binds to")


# --------------------------------------------------------------------------- placement

def test_a_control_can_be_parented_to_an_existing_container():
    form = _live_form()
    form["data"]["elements"].append(
        {"id": "tab-1", "type": "tab", "section": "body", "parentId": None,
         "configs": [{"id": "n1", "key": "name", "value": "Tab1"}]})

    out = addelement.add_elements(form, [{"type": "button", "label": "Delete", "name": "delBtn"}],
                                  parent="Tab1")

    assert _by_name(out["elements"], "delBtn")["parentId"] == "tab-1"


def test_an_unknown_parent_is_refused_and_names_what_exists():
    form = _live_form()
    with pytest.raises(UsageError) as e:
        addelement.add_elements(form, [{"type": "button", "name": "b"}], parent="Nope")
    assert "Nope" in str(e.value)


def test_a_duplicate_control_name_is_refused():
    """Two controls sharing a name make the field-path resolver ambiguous."""
    form = _live_form()
    with pytest.raises(UsageError) as e:
        addelement.add_elements(form, [{"type": "input", "name": "DefaultTimeZone"}])
    assert "DefaultTimeZone" in str(e.value)


def test_several_controls_can_be_added_in_one_call_and_keep_their_order():
    form = _live_form()
    out = addelement.add_elements(form, [
        {"type": "input", "name": "MinimumNoticeHours"},
        {"type": "input", "name": "GoogleCalendarId"},
        {"type": "input", "name": "OrganiserEmail"}])

    names = [c["value"] for el in out["elements"] for c in el["configs"] if c["key"] == "name"]
    assert names[-3:] == ["MinimumNoticeHours", "GoogleCalendarId", "OrganiserEmail"]


def test_adding_nothing_is_refused_rather_than_writing_the_form_back_unchanged():
    with pytest.raises(UsageError):
        addelement.add_elements(_live_form(), [])


def test_the_form_passed_in_is_not_mutated():
    form = _live_form()
    snapshot = copy.deepcopy(form)
    addelement.add_elements(form, [{"type": "input", "name": "OrganiserEmail"}])
    assert form == snapshot, "the caller decides when to write; the builder stays pure"


# --------------------------------------------------------------------------- container registration

def _form_with_tabs() -> dict:
    """A tabs container that draws its children from its own `tabs` list, as the runtime does."""
    form = _live_form()
    form["data"]["elements"].append(
        {"id": "tabs-1", "type": "tabs", "section": "body", "parentId": None,
         "configs": [{"id": "tn", "key": "name", "value": "Tabs1"},
                     {"id": "tl", "key": "tabs", "value": ["Tab1"]}]})
    form["data"]["elements"].append(
        {"id": "tab-1", "type": "tab", "section": "body", "parentId": "tabs-1",
         "configs": [{"id": "t1n", "key": "name", "value": "Tab1"}]})
    return form


def test_a_new_tab_is_registered_in_its_container_list():
    """Parenting alone is not enough: a tabs container renders the names in its `tabs` config, so a
    spliced tab that is missing from it exists, saves, lints clean and never appears on screen."""
    out = addelement.add_elements(_form_with_tabs(), [{"type": "tab", "name": "Tab2"}],
                                  parent="Tabs1")
    tabs = next(e for e in out["elements"] if e["id"] == "tabs-1")
    listed = next(c["value"] for c in tabs["configs"] if c["key"] == "tabs")
    assert listed == ["Tab1", "Tab2"]


def test_a_table_row_is_registered_in_the_table_rows_list():
    form = _live_form()
    form["data"]["elements"].append(
        {"id": "table-1", "type": "table", "section": "body", "parentId": None,
         "configs": [{"id": "tbn", "key": "name", "value": "Table1"},
                     {"id": "tbr", "key": "rows", "value": []}]})
    out = addelement.add_elements(form, [{"type": "dynamic-table-row", "name": "Row1"}],
                                  parent="Table1")
    table = next(e for e in out["elements"] if e["id"] == "table-1")
    assert next(c["value"] for c in table["configs"] if c["key"] == "rows") == ["Row1"]


def test_a_container_with_no_list_config_is_untouched():
    form = _live_form()
    form["data"]["elements"].append(
        {"id": "sec-1", "type": "section", "section": "body", "parentId": None,
         "configs": [{"id": "sn", "key": "name", "value": "Section1"}]})
    out = addelement.add_elements(form, [{"type": "input", "name": "Extra"}], parent="Section1")
    sec = next(e for e in out["elements"] if e["id"] == "sec-1")
    assert [c["key"] for c in sec["configs"]] == ["name"]


def test_an_existing_entry_is_not_duplicated():
    form = _form_with_tabs()
    out = addelement.add_elements(form, [{"type": "tab", "name": "Tab2"}], parent="Tabs1")
    form2 = {"id": "form-1", "data": out}
    out2 = addelement.add_elements(form2, [{"type": "tab", "name": "Tab3"}], parent="Tabs1")
    tabs = next(e for e in out2["elements"] if e["id"] == "tabs-1")
    assert next(c["value"] for c in tabs["configs"] if c["key"] == "tabs") == ["Tab1", "Tab2", "Tab3"]


def test_a_control_placed_inside_a_table_row_is_flagged_as_unreachable():
    """A map cannot read a control that exists once per row, and nothing else reports that."""
    elements = [
        {"id": "tbl", "type": "table", "parentId": None,
         "configs": [{"key": "name", "value": "Table1"}, {"key": "rows", "value": ["Row1"]}]},
        {"id": "row", "type": "dynamic-table-row", "parentId": "tbl",
         "configs": [{"key": "name", "value": "Row1"}]},
        {"id": "panel", "type": "side-panel", "parentId": "row",
         "configs": [{"key": "name", "value": "EditPanel"}]},
    ]
    warning = addelement.unreachable_in_row(elements, "panel")
    assert warning is not None
    assert "Row1" in warning
    assert "$.item" in warning


def test_a_control_outside_any_row_is_not_flagged():
    elements = [
        {"id": "tab", "type": "tab", "parentId": None,
         "configs": [{"key": "name", "value": "Tab1"}]},
    ]
    assert addelement.unreachable_in_row(elements, "tab") is None
    assert addelement.unreachable_in_row(elements, None) is None
