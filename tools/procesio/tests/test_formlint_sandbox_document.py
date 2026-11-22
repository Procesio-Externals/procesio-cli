"""Lint for form JavaScript written against the sandbox's own document.

Form-level code and every RUN_JAVASCRIPT event run in a hidden sandbox iframe that the runtime
removes after the run. `document` there holds nothing but the script, so a lookup finds no form
element and what the script mounts is never on screen. The server stores such code and the form
shows no error; the write is the only place left to say so.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

from tools.procesio import formlint, main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import builder
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}

# The pattern FORM-DEV-GUIDE/02 teaches: the file is an installer, the runtime is injected into
# the parent page, and inside the runtime `document` is the page's own.
INSTALLER = """
function UX_RUNTIME() {
  if (window.__uxFormRuntime) { return; }
  window.__uxFormRuntime = true;
  document.addEventListener('click', function () {}, true);
  var host = document.querySelector('.form-builder--form-body') || document.body;
}
(function () {
  try {
    var W = window.parent && window.parent !== window ? window.parent : window;
    var D = W.document;
    if (!D || !D.body || D.getElementById('ux-runtime')) { return; }
    var s = D.createElement('script');
    s.id = 'ux-runtime';
    s.textContent = '(' + UX_RUNTIME.toString() + ')();';
    D.body.appendChild(s);
  } catch (e) {}
})();
"""


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


@pytest.mark.parametrize("code", [
    "document.getElementById('game-root').textContent = 'ready';",
    "var el = window.document.querySelector('.card'); el.hidden = true;",
    "var b = document.createElement('div'); document.body.appendChild(b);",
    "document.addEventListener('click', start, true);",
    # the parent window is kept only to hang a value on it: the DOM calls still miss the page
    "var P = null; try { P = window.parent !== window ? window.parent : null; } catch (e) {}\n"
    "P.__game = {}; var root = document.getElementById('game-root');",
    # the parent document appears only in comments
    "// console.log(window.parent.document); -> to access the DOM\n"
    "document.querySelectorAll('input');",
    "/* use window.parent.document */ document.getElementById('a');",
])
def test_a_script_that_only_uses_its_own_document_is_flagged(code):
    warnings = formlint.lint_form_code_sandbox(code)
    assert len(warnings) == 1
    assert "window.parent.document" in warnings[0] and "sandbox" in warnings[0]


@pytest.mark.parametrize("code", [
    "window.parent.document.getElementById('game-root').textContent = 'ready';",
    "parent.document.querySelector('.card').hidden = true;",
    "window.frameElement.ownerDocument.querySelector('.card');",
    "var W = window.parent; var D = W.document; D.body.appendChild(document.createElement('div'));",
    INSTALLER,
    # a string that holds // is not a comment, so the parent document after it still counts
    "var u = 'https://example.test/x'; var D = window.parent.document; "
    "D.title = u; document.getElementById('a');",
    # no DOM lookup at all
    "const total = deserialze(amount); ProcesioForm.data.fields.total = total;",
    "var c = document.createElement('canvas'); c.getContext('2d');",
    "",
    None,
])
def test_a_script_that_reaches_the_page_or_touches_no_dom_is_clean(code):
    assert formlint.lint_form_code_sandbox(code) == []


def test_the_shipped_form_kit_draws_no_warning():
    kit = Path(formlint.__file__).parent / "assets" / "form-kit"
    for name in ("runtime.template.js", "core.js", "effects.js"):
        source = (kit / name).read_text(encoding="utf-8")
        assert formlint.lint_form_code_sandbox(source) == [], name


def test_no_javascript_example_in_the_form_guides_draws_the_warning():
    """An example is pasted into form code as it stands, so it must reach the page from there.
    One that is right only inside the parent-page runtime gets `window.parent.document`, or the
    `W` / `D` of the installer, written into the example itself."""
    root = Path(formlint.__file__).parent
    guides = sorted([*(root / "FORM-DEV-GUIDE").glob("*.md"), *(root / "dto" / "form").glob("*.md"),
                     *root.glob("PROCESIO-FORM*.md")])
    examples, flagged = 0, []
    for guide in guides:
        text = guide.read_text(encoding="utf-8")
        for block in re.finditer(r"```(?:js|javascript)[ \t]*\n(.*?)```", text, re.S):
            examples += 1
            if formlint.uses_only_sandbox_document(block.group(1)):
                first = block.group(1).strip().splitlines()[0].strip()
                flagged.append(f"{guide.relative_to(root).as_posix()}: {first}")
    assert examples > 20, "the guides moved: this test reads no example"
    assert flagged == []


def test_the_message_names_the_script():
    w = formlint.lint_form_code_sandbox("document.getElementById('a')", "the onClickEvents script of 'go'")
    assert w[0].startswith("the onClickEvents script of 'go' works on the page through `document`")


# ------------------------------------------------------------------ where the lint is reported

def test_form_set_code_reports_it_and_still_saves(monkeypatch):
    monkeypatch.setattr("tools.procesio.handlers.form_code._code_key", lambda *_a, **_k: "k" * 16)
    form = {"id": "F1", "name": "F", "isPrivate": False, "type": 1, "status": 1, "state": True,
            "assignees": [], "customUrl": None, "data": {"code": "", "elements": []}}
    s = FakeSession(queue=[FakeResp(200, form)])
    out = _call("form-set-code", ["--id", "F1", "--dry-run",
                                  "--javascript", "document.getElementById('game-root')"], s)
    assert out["dry_run"] is True
    assert any("sandbox iframe" in w for w in out["warnings"])

    s = FakeSession(queue=[FakeResp(200, form)])
    out = _call("form-set-code", ["--id", "F1", "--dry-run", "--javascript",
                                  "window.parent.document.getElementById('game-root')"], s)
    assert "warnings" not in out


def _button_form():
    return {"id": "F1", "name": "F", "type": 0, "status": 1, "state": True,
            "data": {"elements": [{"id": "btn", "type": "button", "configs": [
                {"key": "name", "value": "btn"},
                {"key": "onClickEvents", "value": {"debounce": 0, "events": []}}]}]}}


def test_form_set_element_event_reports_it_for_a_javascript_event():
    s = FakeSession(queue=[FakeResp(200, _button_form()), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "btn", "--on", "click", "--action", "RUN_JAVASCRIPT",
                 "--config", json.dumps({"code": "document.getElementById('game-root').click()"})], s)
    assert out["updated"] is True                       # a warning never refuses the save
    assert len(out["warnings"]) == 1
    assert out["warnings"][0].startswith("the onClickEvents script of 'btn'")


def test_form_set_element_event_is_quiet_for_a_script_that_reaches_the_page():
    s = FakeSession(queue=[FakeResp(200, _button_form()), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "btn", "--on", "click", "--action", "RUN_JAVASCRIPT",
                 "--config", json.dumps({"code": "window.parent.document.title = 'x'"})], s)
    assert "warnings" not in out


def test_event_scripts_of_a_form_draw_one_warning_that_names_them():
    code = "document.getElementById('game-root').click()"
    dto = builder.build({"name": "F", "elements": [
        {"type": "button", "label": "One", "name": "one",
         "events": [{"on": "click", "do": "js", "code": code}]},
        {"type": "button", "label": "Two", "name": "two",
         "events": [{"on": "click", "do": "js", "code": code}]},
        {"type": "button", "label": "Three", "name": "three",
         "events": [{"on": "click", "do": "js", "code": "window.parent.document.title = 'x'"}]}]},
        {"new_id": lambda: str(uuid.uuid4())})
    warnings = [w for w in formlint.lint_form_data(dto["Data"]) if "sandbox iframe" in w]
    assert len(warnings) == 1
    assert "'one'" in warnings[0] and "'two'" in warnings[0] and "'three'" not in warnings[0]
    assert " work on the page" in warnings[0]


def test_form_level_code_is_linted_at_build_time():
    ctx = {"new_id": lambda: str(uuid.uuid4()), "_build_warnings": [], "form_code_key": "k" * 32}
    builder.build({"name": "F", "elements": [{"type": "input", "label": "X"}],
                   "javascript": "document.getElementById('game-root')"}, ctx)
    assert any("sandbox iframe" in w for w in ctx["_build_warnings"])


# ------------------------------------------------------------------ the note on the read answers

def _coded_form(js: str, key: str) -> dict:
    from tools.procesio.dto.form import code_cipher
    return {"id": "F1", "name": "F", "isPrivate": False, "type": 1, "status": 1, "state": True,
            "assignees": [], "customUrl": None,
            "data": {"code": code_cipher.encrypt_code(js, ".a{color:red}", key), "elements": []}}


def test_form_get_code_says_where_the_javascript_runs_before_it_shows_the_code(monkeypatch):
    key = "k" * 16
    monkeypatch.setattr("tools.procesio.handlers.form_code._code_key", lambda *_a, **_k: key)
    s = FakeSession(queue=[FakeResp(200, _coded_form("window.parent.document.title = 'x'", key))])
    out = _call("form-get-code", ["--id", "F1"], s)
    assert out["note"] == formlint.SANDBOX_NOTE
    assert "window.parent.document" in out["note"] and "forms-code" in out["note"]
    keys = list(out)
    # a caller that keeps only the start of a long answer must still get the note
    assert keys.index("note") < keys.index("css") < keys.index("javascript")
    assert "warnings" not in out


def test_form_get_code_warns_about_stored_code_that_misses_the_page(monkeypatch):
    key = "k" * 16
    monkeypatch.setattr("tools.procesio.handlers.form_code._code_key", lambda *_a, **_k: key)
    s = FakeSession(queue=[FakeResp(200, _coded_form("document.getElementById('game-root')", key))])
    out = _call("form-get-code", ["--id", "F1"], s)
    assert any("sandbox iframe" in w for w in out["warnings"])
    assert list(out).index("warnings") < list(out).index("javascript")


def _form_with_events(events):
    form = _button_form()
    form["data"]["elements"][0]["configs"][1]["value"]["events"] = events
    return form


def test_form_get_element_events_carries_the_note_only_when_a_script_is_there():
    script = {"id": "e1", "type": "CLICK", "action": "RUN_JAVASCRIPT",
              "config": {"code": "window.parent.document.title = 'x'"}}
    s = FakeSession(queue=[FakeResp(200, _form_with_events([script]))])
    out = _call("form-get-element-events", ["--id", "F1", "--element", "btn"], s)
    assert out["note"] == formlint.SANDBOX_NOTE and "warnings" not in out
    assert list(out).index("note") < list(out).index("events")

    process = {"id": "e2", "type": "CLICK", "action": "RUN_PROCESS", "config": {"processId": "p"}}
    s = FakeSession(queue=[FakeResp(200, _form_with_events([process]))])
    out = _call("form-get-element-events", ["--id", "F1", "--element", "btn"], s)
    assert "note" not in out and "warnings" not in out


def test_form_get_element_events_warns_about_a_stored_script_that_misses_the_page():
    script = {"id": "e1", "type": "CLICK", "action": "RUN_JAVASCRIPT",
              "config": {"code": "document.getElementById('game-root').click()"}}
    s = FakeSession(queue=[FakeResp(200, _form_with_events([script]))])
    out = _call("form-get-element-events", ["--id", "F1", "--element", "btn"], s)
    assert len(out["warnings"]) == 1
    assert out["warnings"][0].startswith("the onClickEvents script of 'btn'")
