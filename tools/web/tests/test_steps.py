"""The declarative step interpreter: each step type dispatches to the right
driver call with the right args, and bad steps fail fast as UsageError."""
from __future__ import annotations

import pytest

from tools.web.errors import UsageError
from tools.web.steps import KNOWN_STEPS, run_steps, validate_steps


def test_goto_click_fill_press_wait_dispatch(fake_driver):
    steps = [
        {"do": "goto", "url": "https://x.test"},
        {"do": "wait_for", "selector": "#ready"},
        {"do": "fill", "selector": "#q", "text": "hello"},
        {"do": "click", "selector": "#go"},
        {"do": "press", "key": "Enter"},
    ]
    run_steps(fake_driver, steps)
    assert fake_driver.methods() == [
        "goto", "wait_for", "fill", "click", "press", "current_url",
    ]
    # args carried through correctly
    calls = {m: kw for m, kw in fake_driver.calls}
    assert calls["goto"]["url"] == "https://x.test"
    assert calls["fill"]["selector"] == "#q"
    assert calls["fill"]["text"] == "hello"
    assert calls["press"]["key"] == "Enter"


def test_press_with_selector(fake_driver):
    run_steps(fake_driver, [{"do": "press", "key": "Tab", "selector": "#name"}])
    press = [kw for m, kw in fake_driver.calls if m == "press"][0]
    assert press == {"key": "Tab", "selector": "#name"}


def test_type_step_dispatches_keyboard(fake_driver):
    # No selector -> types into whatever is focused (e.g. a canvas grid cell).
    # With selector -> the element is focused first, then typed into.
    run_steps(fake_driver, [
        {"do": "type", "text": "hello world"},
        {"do": "type", "text": "x", "selector": "#t-name-box", "timeout": 3000},
    ])
    types = [kw for m, kw in fake_driver.calls if m == "type_text"]
    assert types[0] == {"text": "hello world", "selector": None, "timeout": None}
    assert types[1] == {"text": "x", "selector": "#t-name-box", "timeout": 3000}


def test_wait_step_dispatches_fixed_delay(fake_driver):
    run_steps(fake_driver, [{"do": "wait", "ms": 1500}])
    waits = [kw for m, kw in fake_driver.calls if m == "wait"]
    assert waits == [{"ms": 1500}]


def test_type_requires_text():
    with pytest.raises(UsageError) as e:
        validate_steps([{"do": "type", "selector": "#x"}])
    assert "missing required key" in str(e.value)


def test_wait_requires_ms():
    with pytest.raises(UsageError) as e:
        validate_steps([{"do": "wait"}])
    assert "missing required key" in str(e.value)


def test_extract_text_named_and_default_name(fake_driver):
    fake_driver.texts = {"h1": "Big Title", None: "whole body"}
    out = run_steps(fake_driver, [
        {"do": "extract_text", "selector": "h1", "name": "headline"},
        {"do": "extract_text"},  # no selector -> reads body; name falls back to "text"
    ])
    assert out["results"]["headline"] == "Big Title"
    assert out["results"]["text"] == "whole body"


def test_extract_attr_named_and_fallback_name(fake_driver):
    fake_driver.attrs = {("a.cta", "href"): "https://dest"}
    out = run_steps(fake_driver, [
        {"do": "extract_attr", "selector": "a.cta", "attr": "href", "name": "link"},
        {"do": "extract_attr", "selector": "img", "attr": "src"},
    ])
    assert out["results"]["link"] == "https://dest"
    # fallback name is "<selector>@<attr>"
    assert out["results"]["img@src"] == "attr:img:src"


def test_screenshot_collected(fake_driver):
    out = run_steps(fake_driver, [
        {"do": "screenshot", "path": "a.png"},
        {"do": "screenshot", "path": "b.png", "full_page": False},
    ])
    assert out["screenshots"] == ["a.png", "b.png"]
    shots = [kw for m, kw in fake_driver.calls if m == "screenshot"]
    assert shots[1]["full_page"] is False


def test_timeout_passed_through(fake_driver):
    run_steps(fake_driver, [{"do": "wait_for", "selector": "#x", "timeout": 5000}])
    wait = [kw for m, kw in fake_driver.calls if m == "wait_for"][0]
    assert wait["timeout"] == 5000


def test_final_url_included(fake_driver):
    fake_driver.url = "https://x.test/final"
    out = run_steps(fake_driver, [{"do": "goto", "url": "https://x.test"}])
    assert out["final_url"] == "https://x.test/final"


# --- validation / error cases (no driver interaction needed) --------------

def test_steps_must_be_list():
    with pytest.raises(UsageError):
        validate_steps({"do": "goto", "url": "x"})


def test_unknown_step_rejected():
    with pytest.raises(UsageError) as e:
        validate_steps([{"do": "teleport", "url": "x"}])
    assert "unknown action" in str(e.value)


def test_missing_required_key_rejected():
    with pytest.raises(UsageError) as e:
        validate_steps([{"do": "fill", "selector": "#q"}])  # missing text
    assert "missing required key" in str(e.value)


def test_unknown_key_rejected():
    with pytest.raises(UsageError) as e:
        validate_steps([{"do": "goto", "url": "x", "bogus": 1}])
    assert "unknown key" in str(e.value)


def test_missing_do_rejected():
    with pytest.raises(UsageError):
        validate_steps([{"url": "x"}])


def test_non_object_step_rejected():
    with pytest.raises(UsageError):
        validate_steps(["just a string"])


def test_validation_happens_before_any_driver_call(fake_driver):
    # A later bad step must abort the whole run before the good first step runs.
    with pytest.raises(UsageError):
        run_steps(fake_driver, [
            {"do": "goto", "url": "https://x.test"},
            {"do": "nope"},
        ])
    assert fake_driver.calls == []  # nothing executed


def test_known_steps_constant_matches_schema():
    assert KNOWN_STEPS == {
        "goto", "click", "fill", "press", "type", "wait", "wait_for",
        "extract_text", "extract_attr", "eval", "screenshot",
        "upload", "upload_via_chooser",
    }


def test_upload_dispatches_set_input_files(fake_driver):
    run_steps(fake_driver, [
        {"do": "upload", "selector": "#avatar", "path": "C:/pics/me.jpg"},
        {"do": "upload", "selector": "#docs", "path": ["a.pdf", "b.pdf"], "timeout": 9000},
    ])
    calls = [kw for m, kw in fake_driver.calls if m == "set_input_files"]
    assert calls[0] == {"selector": "#avatar", "files": "C:/pics/me.jpg", "timeout": None}
    assert calls[1] == {"selector": "#docs", "files": ["a.pdf", "b.pdf"], "timeout": 9000}


def test_upload_via_chooser_dispatches(fake_driver):
    run_steps(fake_driver, [
        {"do": "upload_via_chooser", "selector": "button.attach", "path": "note.png"},
    ])
    call = [kw for m, kw in fake_driver.calls if m == "set_files_via_chooser"][0]
    assert call == {"selector": "button.attach", "files": "note.png", "timeout": None}


def test_upload_requires_selector_and_path():
    with pytest.raises(UsageError) as e:
        validate_steps([{"do": "upload", "selector": "#f"}])  # missing path
    assert "missing required key" in str(e.value)


def test_click_defaults_to_the_actionability_check(fake_driver):
    run_steps(fake_driver, [{"do": "click", "selector": "button.save"}])
    assert ("click", {"selector": "button.save", "timeout": None,
                      "force": False}) in fake_driver.calls


def test_click_can_be_forced_through_an_overlay(fake_driver):
    """Some frameworks paint a container over their own controls; without this
    the click is refused even though a person can press the control."""
    run_steps(fake_driver, [{"do": "click", "selector": "button.save", "force": True}])
    assert ("click", {"selector": "button.save", "timeout": None,
                      "force": True}) in fake_driver.calls
