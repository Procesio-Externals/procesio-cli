"""Removing a control is the mirror of splicing one in, and is guarded the same way.

The property that makes `form-add-element` safe is that it touches nothing that already exists.
Delete has to hold the same line: every surviving element keeps its id and its field path, and a
control something still points at is refused rather than quietly turned into a dangling path -
which the platform saves without any error, leaving the referring control launching nothing.
"""
import pytest

from tools.procesio.dto.form import addelement
from tools.procesio.errors import UsageError

FORM_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
ROOT = "11111111-1111-1111-1111-111111111111"


def _el(eid, name, parent=None, etype="input", configs=None):
    return {"id": eid, "type": etype, "parentId": parent, "section": "body",
            "configs": (configs or []) + [{"key": "name", "value": name}]}


def _form(elements, attrs=None, events=None):
    return {"id": FORM_ID,
            "data": {"elements": elements,
                     "variables": [{"id": ROOT}],
                     "events": events or [],
                     "dataModel": {"id": ROOT, "name": "form", "attributes": [
                         {"id": "fields-ns", "name": "fields",
                          "attributes": attrs or []}]}}}


def test_the_control_and_its_model_entry_both_go():
    form = _form([_el("a", "Keep"), _el("b", "Drop")],
                 attrs=[{"id": "a", "name": "Keep"}, {"id": "b", "name": "Drop"}])
    data, report = addelement.delete_element(form, "Drop")
    assert [e["id"] for e in data["elements"]] == ["a"]
    assert report["model_attributes_removed"] == 1
    assert [r["name"] for r in report["removed"]] == ["Drop"]


def test_it_can_be_addressed_by_id_as_well_as_by_name():
    form = _form([_el("a", "Keep"), _el("b", "Drop")])
    data, _ = addelement.delete_element(form, "b")
    assert [e["id"] for e in data["elements"]] == ["a"]


def test_a_surviving_control_is_untouched():
    keep = _el("a", "Keep")
    form = _form([keep, _el("b", "Drop")])
    data, _ = addelement.delete_element(form, "Drop")
    assert data["elements"][0] == keep


def test_a_referenced_control_is_refused():
    referring = _el("a", "Keep", configs=[{"key": "onClickEvents",
                                           "value": {"events": [{"config": {"inputMap": [
                                               {"right": {"value": f"{FORM_ID}.fields.b"}}]}}]}}])
    form = _form([referring, _el("b", "Drop")])
    with pytest.raises(UsageError) as e:
        addelement.delete_element(form, "Drop")
    assert "still referenced" in str(e.value)


def test_force_deletes_a_referenced_control_and_reports_the_breakage():
    referring = _el("a", "Keep", configs=[{"key": "onClickEvents",
                                           "value": {"events": [{"config": {"inputMap": [
                                               {"right": {"value": f"{FORM_ID}.fields.b"}}]}}]}}])
    form = _form([referring, _el("b", "Drop")])
    data, report = addelement.delete_element(form, "Drop", force=True)
    assert [e["id"] for e in data["elements"]] == ["a"]
    assert report["broken_references"] == ["b"]


def test_a_container_with_children_is_refused_then_removed_whole_with_force():
    form = _form([_el("box", "Box", etype="tabs"),
                  _el("c1", "Child1", parent="box"),
                  _el("c2", "Child2", parent="box")])
    with pytest.raises(UsageError) as e:
        addelement.delete_element(form, "Box")
    assert "contains 2 control" in str(e.value)

    data, report = addelement.delete_element(form, "Box", force=True)
    assert data["elements"] == []
    assert report["descendants"] == 2


def test_the_container_list_stops_naming_a_removed_child():
    box = _el("box", "Box", etype="tabs", configs=[{"key": "tabs", "value": ["Child1", "Child2"]}])
    form = _form([box, _el("c1", "Child1", parent="box"), _el("c2", "Child2", parent="box")])
    data, _ = addelement.delete_element(form, "Child1")
    listed = next(c["value"] for c in data["elements"][0]["configs"] if c["key"] == "tabs")
    assert listed == ["Child2"]


def test_an_unknown_element_is_refused_with_the_known_names():
    form = _form([_el("a", "Keep")])
    with pytest.raises(UsageError) as e:
        addelement.delete_element(form, "Nope")
    assert "Keep" in str(e.value)
