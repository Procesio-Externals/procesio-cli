"""A config of type `function` must reach the data model as a FUNCTION attribute.

The form runtime builds a callable (`ProcesioForm.<element>.goToNextStep()`) only for a
data-model attribute whose dataTypeId is FUNCTION. Typed as a string, the call throws
"... is not a function" and the published form greys out after the JS error. The designer
writes FUNCTION with `hidden: true` (user-playground Form.model.ts); form-create and
form-add-element share `_dm_shape` / `_dm_attr`, so both are covered here.
"""
import uuid

import pytest

from tools.procesio.dto.form import builder

FUNCTION = "1c2fd144-836e-419a-aa25-9e624a4c7e40"


def _attrs(el_type: str) -> dict:
    dto = builder.build({"name": "F", "elements": [{"type": el_type, "label": "X"}]},
                        {"new_id": lambda: str(uuid.uuid4())})
    el = next(e for e in dto["Data"]["elements"] if e["type"] == el_type)
    fields = next(a for a in dto["Data"]["dataModel"]["attributes"] if a["name"] == "fields")
    sub = next(s for s in fields["attributes"] if s["id"] == el["id"])
    functions = {c["key"] for c in el["configs"] if c.get("type") == "function"}
    return {a["name"]: a for a in sub["attributes"]}, functions


@pytest.mark.parametrize("el_type", ["stepper", "side-panel"])
def test_function_configs_are_function_typed_and_hidden(el_type):
    attrs, functions = _attrs(el_type)
    assert functions, f"the {el_type} golden declares function configs"
    for name in functions:
        assert attrs[name]["dataTypeId"] == FUNCTION
        assert attrs[name]["hidden"] is True and attrs[name]["isList"] is False


def test_the_stepper_carries_both_step_functions():
    attrs, functions = _attrs("stepper")
    assert {"goToNextStep", "goToPreviousStep"} <= functions
    assert all(attrs[n]["dataTypeId"] == FUNCTION for n in ("goToNextStep", "goToPreviousStep"))


def test_other_configs_stay_visible():
    attrs, functions = _attrs("stepper")
    others = [a for n, a in attrs.items() if n not in functions]
    assert others and all(a["hidden"] is False and a["dataTypeId"] != FUNCTION for a in others)
