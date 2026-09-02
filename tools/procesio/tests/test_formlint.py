"""DTO safety lints (warnings, never blockers) — red/green for each check."""
from __future__ import annotations

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
