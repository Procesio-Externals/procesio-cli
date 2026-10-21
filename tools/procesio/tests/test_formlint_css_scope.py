"""Form custom CSS is scoped to the form container, so code that styles or mounts UI outside it
needs the scope attribute copied onto <html>; the lint says so, and stays quiet otherwise."""
from __future__ import annotations

from tools.procesio import formlint

FIX = ("var host = document.querySelector('[data-form-css-scope]');"
       "document.documentElement.setAttribute('data-form-css-scope',"
       " host.getAttribute('data-form-css-scope'));")


def test_ui_mounted_on_body_without_the_attribute_is_warned():
    w = formlint.lint_form_code_scope(".card{color:red}", "document.body.appendChild(el);")
    assert len(w) == 1 and "document.body" in w[0] and "<html>" in w[0]


def test_page_level_css_without_the_attribute_is_warned():
    w = formlint.lint_form_code_scope(":root{--brand:#123} html, body{margin:0} .x{}", "")
    assert len(w) == 1 and ":root / body / html" in w[0]


def test_a_framework_mounted_on_body_is_warned():
    assert formlint.lint_form_code_scope("", "createApp(App).mount(document.body)")
    assert formlint.lint_form_code_scope("", "app.mount('body')")


def test_code_that_propagates_the_attribute_is_not_warned():
    assert formlint.lint_form_code_scope(":root{--a:1}", FIX + "document.body.appendChild(el);") == []


def test_ui_that_stays_inside_the_form_is_not_warned():
    css = ".card{color:red} @media (max-width:600px){.card{color:blue}} /* body{} */"
    assert formlint.lint_form_code_scope(css, "document.querySelector('.card').append(x);") == []


def test_body_inside_another_selector_is_not_a_page_rule():
    # `.tbody` / `.html-preview` are classes, not the html/body elements.
    assert formlint.lint_form_code_scope(".tbody td{} .html-preview{}", "") == []
