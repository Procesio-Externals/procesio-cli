"""DTO safety lints (warnings, never blockers) — red/green for each check."""
from __future__ import annotations

import pytest

from tools.procesio import formlint


def _el(el_id, parent=None, configs=None):
    return {"id": el_id, "parentId": parent, "configs": configs or []}


def _cfg(key, value):
    return {"key": key, "value": value}


# -- (a) phantom parentId ---------------------------------------------------

def test_phantom_parent_flagged():
    data = {"elements": [
        _el("tab1"),
        _el("child", parent="GHOST"),          # references no element
    ]}
    warns = formlint.lint_phantom_parent(data)
    assert len(warns) == 1
    assert "GHOST" in warns[0] and "NO pane" in warns[0]


def test_valid_parent_not_flagged():
    data = {"elements": [_el("tab1"), _el("child", parent="tab1")]}
    assert formlint.lint_phantom_parent(data) == []


def test_null_parent_not_flagged():
    data = {"elements": [_el("top", parent=None)]}
    assert formlint.lint_phantom_parent(data) == []


# -- (b) duplicate id/name configs ------------------------------------------

def test_duplicate_name_config_flagged():
    data = {"elements": [
        _el("a", configs=[_cfg("name", "email")]),
        _el("b", configs=[_cfg("name", "email")]),
    ]}
    warns = formlint.lint_duplicate_configs(data)
    assert any("name" in w and "email" in w for w in warns)


def test_unique_configs_not_flagged():
    data = {"elements": [
        _el("a", configs=[_cfg("name", "email"), _cfg("id", "e1")]),
        _el("b", configs=[_cfg("name", "phone"), _cfg("id", "e2")]),
    ]}
    assert formlint.lint_duplicate_configs(data) == []


# -- (c) patch-key wrapping mistake -----------------------------------------

def test_patch_data_wrapping_mistake_flagged():
    existing = {"hideBranding": False, "elements": []}
    warns = formlint.lint_patch_keys(existing, {"Data": {"hideBranding": True}})
    assert len(warns) == 1 and "wrapping mistake" in warns[0]


def test_patch_unknown_key_flagged_as_addition():
    existing = {"hideBranding": False}
    warns = formlint.lint_patch_keys(existing, {"hideBrandng": True})   # typo
    assert len(warns) == 1 and "not an existing Data field" in warns[0]


def test_patch_known_key_not_flagged():
    existing = {"hideBranding": False}
    assert formlint.lint_patch_keys(existing, {"hideBranding": True}) == []


# -- (d) multiple-select without isList -------------------------------------

def test_multiple_select_missing_islist_flagged():
    data = {"elements": [_el("s1", configs=[
        _cfg("multiple", True),
        {"key": "value", "isList": False},
    ])]}
    warns = formlint.lint_multiple_select_islist(data)
    assert len(warns) == 1 and "isList" in warns[0]


def test_multiple_select_with_islist_ok():
    data = {"elements": [_el("s1", configs=[
        _cfg("multiple", True),
        {"key": "value", "isList": True},
    ])]}
    assert formlint.lint_multiple_select_islist(data) == []


def test_single_select_not_flagged():
    data = {"elements": [_el("s1", configs=[
        _cfg("multiple", False),
        {"key": "value", "isList": False},
    ])]}
    assert formlint.lint_multiple_select_islist(data) == []


# -- IS_TRUE / IS_FALSE on a Boolean variable whose default is a STRING ------

def _cond(left, op, right=""):
    return {"operator": op, "leftOperator": {"value": left}, "rightOperator": {"value": right}}


def _form_with_condition(default, op="IS_TRUE", left="var-pj"):
    return {
        "variables": [{"id": "var-pj", "name": "isPJ", "defaultValue": default}],
        "elements": [_el("btn", configs=[
            _cfg("name", "confirm"),
            _cfg("onClickEvents", {"events": [{"action": "MAP_FORM_DATA", "config": {
                "mapping": [], "conditions": [_cond(left, op)]}}]}),
        ])],
    }


@pytest.mark.parametrize("default", ["False", "false"])
def test_is_true_on_text_false_default_flagged(default):
    # measured live: IS_TRUE passes on both spellings, because any non-empty text is true
    warns = formlint.lint_string_boolean_conditions(_form_with_condition(default))
    assert len(warns) == 1
    assert "isPJ IS_TRUE" in warns[0] and repr(default) in warns[0] and "'confirm'" in warns[0]
    assert "PASSES" in warns[0]
    assert warns[0] in formlint.lint_form_data(_form_with_condition(default))


def test_is_false_on_text_false_default_flagged_as_never_passing():
    warns = formlint.lint_string_boolean_conditions(_form_with_condition("False", op="IS_FALSE"))
    assert len(warns) == 1 and "never passes" in warns[0]


def test_text_true_default_is_not_flagged():
    # "True" evaluates the way it reads, in both directions
    assert formlint.lint_string_boolean_conditions(_form_with_condition("True")) == []
    assert formlint.lint_string_boolean_conditions(_form_with_condition("True", op="IS_FALSE")) == []


def test_null_default_equals_operator_and_field_operand_not_flagged():
    assert formlint.lint_string_boolean_conditions(_form_with_condition(None)) == []
    assert formlint.lint_string_boolean_conditions(_form_with_condition("False", op="EQUALS")) == []
    field = "root.11223344-5566-7788-99aa-aabbccddeeff.el.cfg"
    assert formlint.lint_string_boolean_conditions(_form_with_condition("False", left=field)) == []


def test_form_level_events_are_checked_too():
    data = {"variables": [{"id": "v", "name": "flag", "defaultValue": "False"}],
            "events": [{"action": "MAP_FORM_DATA",
                        "config": {"mapping": [], "conditions": [_cond("v", "IS_TRUE")]}}],
            "elements": []}
    warns = formlint.lint_string_boolean_conditions(data)
    assert len(warns) == 1 and warns[0].startswith("form-level event")
