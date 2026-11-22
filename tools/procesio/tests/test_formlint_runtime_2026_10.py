"""Lints for front-end behaviour that changed in the 2026-10 releases.

- The number field renders <input type="text" inputmode="decimal"> (ui-builder 0.184 / 1.41,
  design-system ADR 0001), so a type=number selector matches nothing.
- `deserialze(x)` inserts the value as JSON since form-runtime 1.30 (designer 1.115), so a
  call wrapped in quotes yields a value that carries the literal's quotes.
"""
import uuid

import pytest

from tools.procesio import formlint
from tools.procesio.dto.form import builder


@pytest.mark.parametrize("code", [
    "document.querySelector('input[type=number]')",
    'document.querySelector("input[type=\\"number\\"]")',
    "if (el.type === 'number') {}",
])
def test_a_type_number_selector_is_flagged(code):
    assert any("inputmode" in w for w in formlint.lint_form_code_runtime("", code))


def test_a_type_number_css_rule_is_flagged():
    assert formlint.lint_form_code_runtime("input[type='number']{width:4rem}", "")


@pytest.mark.parametrize("code", ["const v = 'deserialze(amount)';",
                                  'const v = "deserialze(amount)";',
                                  "const v = `deserialze(amount)`;"])
def test_quoted_deserialze_is_flagged(code):
    assert any("deserialze" in w for w in formlint.lint_form_code_runtime(None, code))


@pytest.mark.parametrize("code", ["const v = deserialze(amount);",
                                  "window.parent.document.querySelector('.amount input').value",
                                  "const kind = 'numbered list';"])
def test_current_usage_is_clean(code):
    assert formlint.lint_form_code_runtime(None, code) == []


def test_event_scripts_are_linted_on_the_built_form():
    dto = builder.build({"name": "F", "elements": [
        {"type": "button", "label": "B", "events": [
            {"on": "click", "do": "js", "code": "x('deserialze(total)')"}]}]},
        {"new_id": lambda: str(uuid.uuid4())})
    warnings = formlint.lint_form_data(dto["Data"])
    assert any("onClickEvents script" in w and "deserialze" in w for w in warnings)


def test_form_level_code_is_linted_at_build_time():
    ctx = {"new_id": lambda: str(uuid.uuid4()), "_build_warnings": [], "form_code_key": "k" * 32}
    builder.build({"name": "F", "elements": [{"type": "input", "label": "X"}],
                   "css": ".f input[type=number]{width:5rem}"}, ctx)
    assert any("inputmode" in w for w in ctx["_build_warnings"])
