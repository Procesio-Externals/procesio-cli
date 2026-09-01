"""form-get-element / form-set-element-config: surgical rewrite of one element's configs.

The invariants worth guarding are the ones whose breach is SILENT on the platform:
a rewritten config that gets a fresh id breaks every value path pointing at it, and
a config invented on an element has no data-model attribute behind it, so the
designer renders raw guids and values never flow. Both must fail loudly here rather
than produce a form that looks saved and does not work.
"""
from __future__ import annotations

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _form() -> dict:
    return {
        "id": "F1", "name": "Some form", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {
            "code": "",
            "elements": [
                {"id": "e1", "type": "paragraph", "parentId": "s1", "section": "body",
                 "configs": [
                     {"id": "c-label", "key": "label", "value": "<p>old</p>"},
                     {"id": "c-name", "key": "name", "value": "intro1"},
                     {"id": "c-visible", "key": "visible", "value": True},
                 ]},
                {"id": "e2", "type": "input", "parentId": "s1", "section": "body",
                 "configs": [
                     {"id": "c2-name", "key": "name", "value": "cnp"},
                     {"id": "c2-req", "key": "required", "value": False},
                     {"id": "c2-regex", "key": "regex", "value": ""},
                     {"id": "c2-input", "key": "onInputEvents", "value": None},
                 ]},
            ],
            "theme": [{"label": "Colors"}],
            "dataModel": {"id": "dm"},
        },
    }


def test_get_element_by_name_returns_its_configs():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-get-element", ["--id", "F1", "--element", "intro1"], s)
    assert out["element_id"] == "e1" and out["type"] == "paragraph"
    assert out["configs"]["label"] == "<p>old</p>"


def test_get_element_can_be_narrowed_to_one_key():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-get-element",
                ["--id", "F1", "--element", "cnp", "--key", "regex"], s)
    assert out["configs"] == {"regex": ""}
    assert "required" in out["config_keys"]        # the full key list is still reported


def test_set_preserves_the_config_id_and_leaves_every_sibling_untouched():
    """The data model addresses each attribute by the element's OWN config id, so a
    fresh id on a rewritten config silently breaks every value path pointing at it."""
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    out = _call("form-set-element-config",
                ["--id", "F1", "--element", "intro1", "--set", "label=<p>new</p>"], s)
    assert out["updated"] is True
    assert out["previous"] == {"label": "<p>old</p>"}

    put = s.calls[-1]
    elements = put["json"]["Data"]["elements"]
    label = next(c for c in elements[0]["configs"] if c["key"] == "label")
    assert label["id"] == "c-label" and label["value"] == "<p>new</p>"
    # every sibling element and config byte-identical
    assert elements[1] == _form()["data"]["elements"][1]
    assert put["json"]["Data"]["theme"] == [{"label": "Colors"}]
    assert put["json"]["Data"]["dataModel"] == {"id": "dm"}


def test_scalars_are_parsed_as_json_so_required_stores_a_boolean():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    _call("form-set-element-config",
          ["--id", "F1", "--element", "cnp",
           "--set", "required=true", "--set", "regex=^[0-9]{13}$"], s)
    configs = {c["key"]: c["value"] for c in s.calls[-1]["json"]["Data"]["elements"][1]["configs"]}
    assert configs["required"] is True                  # boolean, not the string "true"
    assert configs["regex"] == "^[0-9]{13}$"            # not valid JSON -> kept as a string


def test_set_file_carries_a_long_html_label(tmp_path):
    body = tmp_path / "label.html"
    body.write_text("<div>lung</div>", encoding="utf-8")
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    _call("form-set-element-config",
          ["--id", "F1", "--element", "intro1", "--set-file", f"label={body}"], s)
    label = next(c for c in s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
                 if c["key"] == "label")
    assert label["value"] == "<div>lung</div>"


def test_an_unknown_config_is_refused_before_anything_is_written():
    """Inventing a config would need a matching data-model attribute with the same id;
    without one the designer shows raw guids. Refusing is the honest failure."""
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError) as e:
        _call("form-set-element-config",
              ["--id", "F1", "--element", "intro1", "--set", "placeholder=x"], s)
    assert "no config placeholder" in str(e.value)
    assert not any(c["method"] == "PUT" for c in s.calls)


def test_event_configs_are_routed_to_the_event_action():
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError) as e:
        _call("form-set-element-config",
              ["--id", "F1", "--element", "cnp", "--set", 'onInputEvents={"events":[]}'], s)
    assert "form-set-element-event" in str(e.value)


def test_dry_run_reports_the_change_without_writing():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-set-element-config",
                ["--id", "F1", "--element", "intro1",
                 "--set", "visible=false", "--dry-run"], s)
    assert out["dry_run"] is True and out["set"] == {"visible": False}
    assert out["elements"] == 2          # the count to watch on every write
    assert not any(c["method"] == "PUT" for c in s.calls)


def test_nothing_to_set_is_a_usage_error():
    s = FakeSession(queue=[])
    with pytest.raises(UsageError):
        _call("form-set-element-config", ["--id", "F1", "--element", "intro1"], s)
