"""A select's option source reaches the form's data model, in the designer's shape.

Only data-model attributes reach `ProcesioForm` in form JS. The builder used to keep
`sourceType` / `sourceValue` out of the data model, so a script on an API-built form
could never read a select's options, while a save in the designer added them. These pin
the shape a designer save writes, captured on 2026-10-01 from a form built here and then
saved and published in the designer: attribute ids equal the config ids, `sourceType` is
a plain string, and a static `sourceValue` is a list of Objects.
"""
from __future__ import annotations

import itertools

from tools.procesio.dto.form import addelement
from tools.procesio.dto.form import builder as fb

STR = "0317bfee-b2f5-4bde-bfe8-121212121214"
OBJECT = "0317bfee-b2f5-4bde-bfe8-121212121221"

# The designer's attribute shape, as captured. Ids differ per form; the rest is fixed.
DESIGNER = {
    "sourceType": {"dataTypeId": STR, "isList": False, "isDataModel": False,
                   "isPublic": False, "isProcesio": False, "jsonProperty": None,
                   "attributes": [], "hidden": False},
    "sourceValue": {"dataTypeId": OBJECT, "isList": True, "isDataModel": False,
                    "isPublic": False, "isProcesio": False, "jsonProperty": None,
                    "attributes": [], "hidden": False},
}


def _ctx():
    cnt = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"}


def _built(spec):
    dto = fb.build({"name": "F", "elements": [spec]}, _ctx())
    data = dto["Data"]
    el = next(e for e in data["elements"] if e.get("type") == "select")
    fields = next(a for a in data["dataModel"]["attributes"] if a["id"] == fb._FIELDS_NS)
    sub = next(s for s in fields["attributes"] if s["id"] == el["id"])
    return el, {a["name"]: a for a in sub["attributes"]}


def _cfg(el, key):
    return next(c for c in el["configs"] if c["key"] == key)


def test_a_static_select_carries_its_option_source_in_the_designer_shape():
    el, attrs = _built({"type": "select", "label": "Pick", "name": "pick",
                        "options": ["alpha", "beta"]})
    for key, shape in DESIGNER.items():
        assert key in attrs, f"{key} is missing from the data model"
        attr = attrs[key]
        assert attr["id"] == _cfg(el, key)["id"], f"{key}: attribute id must equal the config id"
        assert attr["parentDataTypeId"] == el["id"]
        assert {k: attr[k] for k in shape} == shape, key
    assert _cfg(el, "sourceValue")["value"] == [{"name": "alpha", "value": "alpha"},
                                                 {"name": "beta", "value": "beta"}]


def test_a_json_sourced_select_gets_no_guessed_source_value_attribute():
    """Only the static-list shape was captured from the designer."""
    _el, attrs = _built({"type": "select", "label": "Pick", "name": "pick",
                         "optionsSource": {"type": "json", "value": "[]"}})
    assert "sourceType" in attrs
    assert "sourceValue" not in attrs


def test_form_add_element_writes_the_same_attributes_as_form_create():
    """The two used to carry separate copies of this rule; now they share one."""
    el, attrs = _built({"type": "select", "label": "Pick", "name": "pick", "options": ["a"]})
    spliced = addelement._sub_model(el, fb._FIELDS_NS, {})
    assert {a["name"]: a for a in spliced["attributes"]} == attrs
