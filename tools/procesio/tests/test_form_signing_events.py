"""form-set-element-event / form-get-element-events on a document-signing element.

The element raises three triggers of its own (ui-builder trigger.ts TriggerKey
ON_SIGNING_SIGNED/DECLINED/COMPLETED, EventType SIGNING_*). Before they were in the
builder's maps, `--on completed` was refused and the slot had to be hand-written with
form-update, usually as a bare list of events, which `form-get-element-events` then crashed
on. The runtime reads both slot shapes (trigger.ts::getTriggersDataByKey), so the tool must.
"""
from __future__ import annotations

import json

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import builder, fieldpath
from tools.procesio.handlers import form_events
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
NS = fieldpath.FIELDS_NS

SIGNING = {
    "signed": ("onSignedEvents", "SIGNING_SIGNED"),
    "declined": ("onDeclinedEvents", "SIGNING_DECLINED"),
    "completed": ("onCompletedEvents", "SIGNING_COMPLETED"),
}


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _form(completed=None, *, with_slots=True):
    slots = [{"key": "onSignedEvents", "value": None},
             {"key": "onDeclinedEvents", "value": None},
             {"key": "onCompletedEvents", "value": completed}] if with_slots else []
    return {
        "id": "F1", "name": "Agreement", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {
            "code": "", "theme": [], "dataModel": {"id": "dm"},
            "elements": [
                {"id": "S1", "type": "document-signing", "configs": [
                    {"key": "name", "value": "Signature"},
                    {"key": "value", "id": "vc-S1"},
                    *slots,
                ]},
                {"id": "E2", "type": "input", "configs": [
                    {"key": "name", "value": "client_name"},
                    {"key": "value", "id": "vc-E2"},
                ]},
            ],
        },
    }


_PROCESS = {"flow": {"id": "P1", "variables": [{"id": "v-name", "name": "ClientName"}]}}
_CFG = {"processId": "P1", "inputMap": [{"left": "ClientName", "right": "client_name"}],
        "outputMap": []}


@pytest.mark.parametrize("on", sorted(SIGNING))
def test_signing_triggers_resolve_to_the_ui_builder_key_and_type(on):
    assert form_events._resolve_trigger(on) == SIGNING[on]
    assert form_events._resolve_trigger(on.upper()) == SIGNING[on]


def test_the_document_signing_template_carries_every_signing_slot():
    """The golden template is what a missing slot is back-filled from, so each mapped key
    must exist on it, or the trigger would be refused as 'cannot raise'."""
    keys = {c.get("key") for c in builder._golden("document-signing")["configs"]}
    assert {key for key, _ in SIGNING.values()} <= keys


def test_dry_run_on_completed_builds_a_signing_completed_event_and_writes_nothing():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "Signature", "--on", "completed",
                 "--action", "RUN_PROCESS", "--config", json.dumps(_CFG), "--dry-run"], s)
    assert out["dry_run"] is True
    assert out["trigger"] == "onCompletedEvents"
    assert out["event"]["type"] == "SIGNING_COMPLETED"
    assert out["event"]["config"]["inputMap"][0]["left"]["value"] == "v-name"
    assert out["event"]["config"]["inputMap"][0]["right"]["value"] == f"dm.{NS}.E2.vc-E2"
    assert out["backfilled"] == []
    assert all(c["method"] == "GET" for c in s.calls)


def test_a_bare_list_slot_is_read_not_crashed_on():
    bare = [{"id": "e1", "type": "SIGNING_COMPLETED", "action": "RUN_PROCESS",
             "config": {"processId": "P1"}}]
    s = FakeSession(queue=[FakeResp(200, _form(bare))])
    out = _call("form-get-element-events", ["--id", "F1", "--element", "Signature"], s)
    assert out["type"] == "document-signing"
    assert out["events"]["onCompletedEvents"] == bare
    assert out["events"]["onSignedEvents"] == []


def test_setting_onto_a_bare_list_slot_appends_and_writes_the_designer_shape():
    bare = [{"id": "e1", "type": "SIGNING_COMPLETED", "action": "RUN_JAVASCRIPT",
             "config": {"code": "x"}}]
    s = FakeSession(queue=[FakeResp(200, _form(bare)), FakeResp(200, _PROCESS),
                           FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "S1", "--on", "completed",
                 "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)], s)
    assert out["updated"] is True and out["event_count"] == 2
    assert out["previous_events"] == bare

    put = s.calls[-1]
    assert put["method"] == "PUT" and put["url"].endswith("/api/FormTemplate")
    slot = next(c for e in put["json"]["Data"]["elements"] if e["id"] == "S1"
                for c in e["configs"] if c["key"] == "onCompletedEvents")
    assert slot["value"]["debounce"] == 0
    assert [e["id"] for e in slot["value"]["events"]][0] == "e1"
    assert slot["value"]["events"][1]["type"] == "SIGNING_COMPLETED"


def test_a_signing_element_saved_without_the_slot_gets_it_back_filled():
    s = FakeSession(queue=[FakeResp(200, _form(with_slots=False)), FakeResp(200, _PROCESS)])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "Signature", "--on", "signed",
                 "--action", "RUN_PROCESS", "--config", json.dumps(_CFG), "--dry-run"], s)
    assert out["backfilled"] == ["onSignedEvents"]
    assert out["event"]["type"] == "SIGNING_SIGNED"


def test_the_form_builder_accepts_signing_triggers():
    configs = [{"key": "onCompletedEvents", "value": None}]
    builder._apply_events({"events": [{"on": "completed", "do": "js", "code": "x"}]},
                          configs, {})
    value = configs[0]["value"]
    assert value["events"][0]["type"] == "SIGNING_COMPLETED"



def test_the_config_schema_lists_exactly_the_builders_triggers():
    """A trigger in the builder's map but not in the schema is refused by form-create
    before the builder ever sees it."""
    from pathlib import Path
    schema = json.loads((Path(builder.__file__).parent / "config.schema.json")
                        .read_text("utf-8"))
    assert set(schema["$defs"]["event"]["properties"]["on"]["enum"]) == set(builder._EVENT_KEY)
