"""A RUN_PROCESS map row's FORM side can also be a form variable or a path into the form's own
data model (instance.currentUser.email) - shapes real forms use (FORM_LOAD passes the signed-in
user's email; a click passes a form variable such as an offer id). The resolver used to refuse
both, so a correct event could not be written through form-set-element-event."""
from __future__ import annotations

import pytest

from tools.procesio.dto.form import fieldpath
from tools.procesio.errors import UsageError

NS = fieldpath.FIELDS_NS


def _live():
    return fieldpath.LiveForm({"data": {
        "dataModel": {"id": "dm", "attributes": [
            {"id": NS, "name": "fields", "attributes": []},
            {"id": "inst", "name": "instance", "attributes": [
                {"id": "cu", "name": "currentUser", "attributes": [
                    {"id": "em", "name": "email", "attributes": []},
                    {"id": "nm", "name": "name", "attributes": []}]}]}]},
        "variables": [
            {"id": "dm", "name": "form", "type": 20},
            {"id": "v-offer", "name": "Offer_ID", "type": 20},
            {"id": "v-status", "name": "status", "type": 20}],
        "elements": [
            {"id": "E1", "type": "input", "configs": [{"key": "name", "value": "status"},
                                                      {"key": "value", "id": "vc-E1"}]}]}})


def test_a_form_variable_by_at_name_resolves_to_its_id():
    live = _live()
    assert live.resolve("@Offer_ID", "row") == "v-offer"
    assert live.is_variable("v-offer")


def test_a_bare_variable_name_resolves_when_no_field_has_that_name():
    assert _live().resolve("Offer_ID", "row") == "v-offer"


def test_a_field_name_still_wins_over_a_variable_of_the_same_name():
    live = _live()
    assert live.resolve("status", "row") == f"dm.{NS}.E1.vc-E1"
    assert live.resolve("@status", "row") == "v-status"


def test_the_form_handle_variable_is_not_a_value():
    with pytest.raises(UsageError):
        _live().resolve("@form", "row")


def test_a_data_model_name_path_resolves_to_its_id_path():
    assert _live().resolve("instance.currentUser.email", "row") == "dm.inst.cu.em"


def test_an_id_path_into_the_instance_tree_passes_through():
    assert _live().resolve("dm.inst.cu.nm", "row") == "dm.inst.cu.nm"


def test_an_unknown_attribute_names_what_exists():
    with pytest.raises(UsageError) as e:
        _live().resolve("instance.currentUser.phone", "row")
    assert "email" in str(e.value) and "name" in str(e.value)


def _live_with_paragraph():
    live = _live()
    p = {"id": "P9", "type": "paragraph", "configs": [{"key": "name", "value": "Paragraph9"},
                                                     {"key": "label", "id": "lbl-P9"},
                                                     {"key": "visible", "id": "vis-P9"}]}
    live.elements.append(p); live.by_id["P9"] = p; live.by_name["Paragraph9"] = [p]
    return live


def test_an_element_config_by_name_resolves_to_its_config_path():
    assert _live_with_paragraph().resolve("Paragraph9.label", "row") == f"dm.{NS}.P9.lbl-P9"


def test_a_path_to_any_config_of_the_element_passes_the_check():
    live = _live_with_paragraph()
    assert live.resolve(f"dm.{NS}.P9.vis-P9", "row") == f"dm.{NS}.P9.vis-P9"


def test_a_config_id_of_another_element_is_still_refused():
    with pytest.raises(UsageError):
        _live_with_paragraph().resolve(f"dm.{NS}.P9.vc-E1", "row")
