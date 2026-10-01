"""Auto-generated field names are single lowercase words, stable across a designer save.

When a form config gives no explicit `name`, the builder derives one from the label. It
used to title-case it (`Company Name` -> `CompanyName`), which a designer save re-keys and
`formlint.lint_field_names` then flags. The builder now makes a single lowercase word, so
an auto-named field survives a designer save unchanged and does not trip the lint. The
human-readable text stays in the label, not the name. `_slug` (flowgraph display, which
keeps case) is a different function and is left alone.
"""
from __future__ import annotations

import itertools

from tools.procesio import formlint
from tools.procesio.dto.form import builder as fb


def _ctx():
    cnt = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"}


def test_field_slug_is_a_single_lowercase_word():
    assert fb._field_slug("Company Name") == "companyname"
    assert fb._field_slug("order_id") == "orderid"
    assert fb._field_slug("Already lower") == "alreadylower"
    assert fb._field_slug("") == "field"


def test_unnamed_elements_get_lowercase_names_that_do_not_trip_the_lint():
    dto = fb.build({"name": "F", "elements": [
        {"type": "input", "label": "Company Name"},
        {"type": "select", "label": "Order List", "options": ["a", "b"]},
    ]}, _ctx())
    data = dto["Data"]
    names = [c["value"] for e in data["elements"] for c in e.get("configs", [])
             if c.get("key") == "name"]
    assert "companyname" in names and "orderlist" in names, names
    assert all(fb._SINGLE_WORD.fullmatch(n) for n in names) if hasattr(fb, "_SINGLE_WORD") \
        else all(n == n.lower() and n.isalnum() for n in names), names
    assert formlint.lint_field_names(data) == []


def test_an_explicit_mixed_case_name_is_left_as_written_and_still_warns():
    dto = fb.build({"name": "F", "elements": [
        {"type": "input", "label": "x", "name": "OrderList"},
    ]}, _ctx())
    data = dto["Data"]
    names = [c["value"] for e in data["elements"] for c in e.get("configs", [])
             if c.get("key") == "name"]
    assert "OrderList" in names, names
    assert formlint.lint_field_names(data), "an explicit mixed-case name must still warn"
