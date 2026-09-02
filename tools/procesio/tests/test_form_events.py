"""Control events -> element event configs. Event type/key/action values VERIFIED
2026-06-25 against ui-builder source (trigger.ts, FieldEvents.component.vue, EventType /
EventAction enums in model/config/events). Guards the bugs fixed there (open/close=
SIDE_PANEL_*, step*=STEPPER_*, message*=CHAT_*, form=TRIGGER_FORM not RUN_FORM)."""
import uuid

import pytest

from tools.procesio.dto.form import builder
from tools.procesio.errors import UsageError


def _build(el):
    dto = builder.build({"name": "E", "elements": [el]},
                        {"new_id": lambda: str(uuid.uuid4())})
    return dto["Data"]["elements"]


def _event(els, el_type, cfg_key):
    el = next(e for e in els if e["type"] == el_type)
    return next(c for c in el["configs"] if c["key"] == cfg_key)["value"]


def test_click_js_event():
    els = _build({"type": "button", "label": "B",
                  "events": [{"on": "click", "do": "js", "code": "x()"}]})
    ev = _event(els, "button", "onClickEvents")
    assert ev["events"][0]["type"] == "CLICK"
    assert ev["events"][0]["action"] == "RUN_JAVASCRIPT"
    assert ev["events"][0]["config"] == {"code": "x()"}
    assert ev["debounce"] == 0


def test_side_panel_open_close_types():
    els = _build({"type": "side-panel", "label": "SP", "events": [
        {"on": "open", "do": "js", "code": "o()"},
        {"on": "close", "do": "js", "code": "c()"}]})
    assert _event(els, "side-panel", "onOpenEvents")["events"][0]["type"] == "SIDE_PANEL_OPEN"
    assert _event(els, "side-panel", "onCloseEvents")["events"][0]["type"] == "SIDE_PANEL_CLOSE"


def test_stepper_step_event_type():
    els = _build({"type": "stepper", "label": "S",
                  "events": [{"on": "stepchange", "do": "js", "code": "s()"}]})
    assert _event(els, "stepper", "onStepChangeEvents")["events"][0]["type"] == "STEPPER_STEP_CHANGE"


def test_process_event_shape():
    els = _build({"type": "input", "label": "I", "events": [
        {"on": "input", "do": "process", "processId": "p1", "syncRun": True}]})
    ev = _event(els, "input", "onInputEvents")["events"][0]
    assert ev["type"] == "INPUT" and ev["action"] == "RUN_PROCESS"
    assert ev["config"]["processId"] == "p1" and ev["config"]["syncRun"] is True
    assert "inputMap" in ev["config"] and "outputMap" in ev["config"]


def test_trigger_form_action():
    els = _build({"type": "button", "label": "B",
                  "events": [{"on": "click", "do": "form", "formId": "f1"}]})
    ev = _event(els, "button", "onClickEvents")["events"][0]
    assert ev["action"] == "TRIGGER_FORM"  # not RUN_FORM
    assert ev["config"]["formId"] == "f1" and "mapping" in ev["config"]


def test_unknown_event_fails_loud():
    with pytest.raises(UsageError):
        _build({"type": "input", "label": "I", "events": [{"on": "nope", "do": "js"}]})


def _value_cfg(els, el_type):
    el = next(e for e in els if e["type"] == el_type)
    return next(c for c in el["configs"] if c["key"] == "value")


def test_multiple_file_upload_value_is_array():
    # a multiple file-upload is array-valued: its value config must default to [] + isList=True
    # (else the form sends a single object and a List<File> process input fails at launch).
    els = _build({"type": "file-upload", "name": "docs", "multiple": True})
    v = _value_cfg(els, "file-upload")
    assert v["value"] == [] and v["isList"] is True


def test_single_file_upload_value_not_array():
    els = _build({"type": "file-upload", "name": "doc"})   # multiple defaults false
    v = _value_cfg(els, "file-upload")
    assert v["value"] != [] and not v.get("isList")


def test_list_control_value_is_array():
    els = _build({"type": "list", "name": "rows"})
    v = _value_cfg(els, "list")
    assert v["value"] == [] and v["isList"] is True
