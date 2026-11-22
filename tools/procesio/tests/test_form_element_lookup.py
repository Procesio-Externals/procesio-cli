"""How the form actions find the element a caller names.

An element has three handles: its element id, its `name` config and its `id` config. The `id`
config is the DOM id the element carries on the page, so it is the only handle visible in the
form's script or markup. A caller that read the script and then asked for the element by that
id was told the element does not exist, although the element carries exactly that id.
"""
from __future__ import annotations

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import UsageError
from tools.procesio.handlers.form_events import _find_element
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}


def _el(guid, name, dom_id, el_type="input"):
    return {"id": guid, "type": el_type, "configs": [
        {"key": "name", "value": name},
        {"key": "id", "value": dom_id},
        {"key": "label", "value": "L"},
        {"key": "onClickEvents", "value": {"debounce": 0, "events": []}}]}


def _elements():
    return [_el("G1", "Game", "gameHeading", "heading"),
            _el("G2", "playerName", "playerName"),
            _el("G3", "First", "input"),
            _el("G4", "Second", "input"),
            _el("G5", "save", "Game", "button")]


def _form():
    return {"id": "F1", "name": "F", "type": 0, "status": 1, "state": True,
            "data": {"elements": _elements()}}


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def test_an_element_is_found_by_its_dom_id():
    assert _find_element(_elements(), "gameHeading")["id"] == "G1"


def test_the_element_id_and_the_name_still_work():
    assert _find_element(_elements(), "G2")["id"] == "G2"
    assert _find_element(_elements(), "playerName")["id"] == "G2"
    assert _find_element(_elements(), "save")["id"] == "G5"


def test_the_name_wins_over_another_elements_dom_id():
    # "Game" is the name of G1 and the DOM id of G5
    assert _find_element(_elements(), "Game")["id"] == "G1"


def test_a_dom_id_that_several_elements_share_is_refused_and_names_them():
    with pytest.raises(UsageError) as err:
        _find_element(_elements(), "input")
    message = str(err.value)
    assert "2 elements carry the DOM id 'input'" in message
    assert "'First'" in message and "'Second'" in message


def test_a_miss_lists_the_names_on_the_form():
    with pytest.raises(UsageError) as err:
        _find_element(_elements(), "game-root")
    message = str(err.value)
    assert "no element with id, name or DOM id 'game-root'" in message
    for name in ("Game", "playerName", "First", "Second", "save"):
        assert name in message


def test_a_miss_on_a_form_without_names_still_answers():
    with pytest.raises(UsageError, match="Element names here: none"):
        _find_element([{"id": "G1", "type": "input", "configs": []}], "x")


def test_form_get_element_reads_by_dom_id():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-get-element", ["--id", "F1", "--element", "gameHeading"], s)
    assert out["element_id"] == "G1"
    assert out["configs"]["name"] == "Game"      # the answer teaches the caller the name


def test_form_get_element_events_reads_by_dom_id():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-get-element-events", ["--id", "F1", "--element", "gameHeading"], s)
    assert out["elementId"] == "G1"


def test_form_set_element_config_writes_the_element_found_by_dom_id():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    out = _call("form-set-element-config",
                ["--id", "F1", "--element", "gameHeading", "--set", "label=New"], s)
    sent = next(c for c in s.calls if c["method"] != "GET")
    elements = (sent["json"].get("Data") or sent["json"].get("data"))["elements"]
    changed = {e["id"]: next(c["value"] for c in e["configs"] if c["key"] == "label")
               for e in elements}
    assert changed["G1"] == "New"
    assert all(v == "L" for k, v in changed.items() if k != "G1")
    assert out.get("element_id", out.get("elementId")) == "G1"
