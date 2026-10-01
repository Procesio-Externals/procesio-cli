"""Field names a designer save would rename are flagged, once per form, and never renamed.

A form built through the API keeps its field names as written. One save in the designer
re-keys `ProcesioForm.data.fields`: it splits each name on underscores, lowercases the
parts and joins them in camelCase. Form JS that reads the original name then gets
`undefined`. The tool warns; it does not rename, because scripts already in use read the
names as built.
"""
from __future__ import annotations

import json

from tools.procesio import formlint, main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}


def _data(*names):
    return {"elements": [{"id": f"e{i}", "type": "input",
                          "configs": [{"key": "name", "value": n}]}
                         for i, n in enumerate(names)]}


def test_the_designer_rekey_rule_as_measured():
    assert formlint.designer_key("orderList") == "orderlist"
    assert formlint.designer_key("order_id") == "orderId"
    assert formlint.designer_key("Customer_First_Name") == "customerFirstName"
    assert formlint.designer_key("order-id") is None        # hyphens were not measured


def test_single_lowercase_words_pass():
    assert formlint.lint_field_names(_data("orders", "total2")) == []


def test_one_warning_names_every_renamed_field():
    warnings = formlint.lint_field_names(_data("orderList", "order_id", "ok"))
    assert len(warnings) == 1
    assert warnings[0].startswith("2 field name(s)")
    assert "orderList -> orderlist" in warnings[0]
    assert "order_id -> orderId" in warnings[0]


def test_a_long_list_is_shortened():
    warnings = formlint.lint_field_names(_data(*[f"field_{i}" for i in range(10)]))
    assert "and 2 more" in warnings[0]


def test_an_unmeasured_name_says_so():
    warnings = formlint.lint_field_names(_data("order-id"))
    assert "order-id -> (renamed; rule not measured)" in warnings[0]


def test_elements_without_a_name_are_ignored():
    assert formlint.lint_field_names({"elements": [{"id": "e1", "configs": []}]}) == []


def test_the_form_lint_includes_it():
    assert any("designer re-keys" in w for w in formlint.lint_form_data(_data("orderList")))


def test_form_create_dry_run_reports_it_without_renaming():
    cfg = {"name": "F", "elements": [{"type": "input", "label": "Order", "name": "orderList"}]}
    out = main.dispatch(
        "form-create", ["--config", json.dumps(cfg), "--dry-run"],
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t",
                                                   session=FakeSession()))
    assert any("orderList -> orderlist" in w for w in out["warnings"])
    names = [c["value"] for e in out["dto"]["Data"]["elements"]
             for c in e["configs"] if c["key"] == "name"]
    assert "orderList" in names          # warned about, not renamed
