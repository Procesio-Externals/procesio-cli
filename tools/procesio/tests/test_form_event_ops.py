"""form-set-element-event: wire one element's trigger without touching the rest.

Two invariants matter. First, the one form_code also guards — rewiring must never
rewrite the element tree. Second, the documented RUN_PROCESS trap: the PROCESS
VARIABLE GUID belongs on the LEFT of inputMap/outputMap. A name there is accepted
by the API, but the designer then renders raw guids and the launch 400s, so names
must resolve before the write and an unknown one must fail before anything is sent.
"""
from __future__ import annotations

import json

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


def _form(event_value=None):
    return {
        "id": "F1", "name": "Some form", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {
            "code": "", "theme": [{"label": "Colors"}], "dataModel": {"id": "dm"},
            "elements": [
                {"id": "E1", "type": "file-upload", "configs": [
                    {"key": "name", "value": "doccipf"},
                    {"key": "onInputEvents", "value": event_value},
                ]},
                {"id": "E2", "type": "input", "configs": [{"key": "name", "value": "nume"}]},
            ],
        },
    }


_PROCESS = {"flow": {"id": "P1", "variables": [
    {"id": "v-file", "name": "fisier"}, {"id": "v-nume", "name": "nume_extras"}]}}

_CFG = {"processId": "P1",
        "inputMap": [{"left": "fisier", "right": "root.upload.val"}],
        "outputMap": [{"left": "nume_extras", "right": "root.nume.val"}]}


def test_variable_names_resolve_to_guids_and_only_that_element_changes():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "doccipf", "--on", "input",
                 "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)], s)

    put = s.calls[-1]
    assert put["method"] == "PUT" and put["url"].endswith("/api/FormTemplate")
    els = put["json"]["Data"]["elements"]
    assert els[1] == _form()["data"]["elements"][1]      # sibling untouched
    ev = [c for c in els[0]["configs"] if c["key"] == "onInputEvents"][0]["value"]["events"][0]
    assert ev["action"] == "RUN_PROCESS" and ev["type"] == "INPUT"
    # Each side is the designer's OBJECT shape, not a bare string; the process
    # side carries path {} and the form side path null.
    assert ev["config"]["inputMap"][0]["left"] == {
        "value": "v-file", "isList": False, "path": {}}          # NAME -> GUID
    assert ev["config"]["outputMap"][0]["left"] == {
        "value": "v-nume", "isList": False, "path": {}}
    assert ev["config"]["inputMap"][0]["right"] == {
        "value": "root.upload.val", "isList": False, "path": None}
    assert ev["config"]["syncRun"] is True
    # the canonical RUN_PROCESS keys the designer needs are backfilled from a minimal config
    assert ev["config"]["areConditionsConfigured"] is True
    assert ev["config"]["conditions"] == [] and ev["config"]["mapLatestTriggerOnly"] is False
    assert out["updated"] is True and out["previous_events"] == []


def test_unknown_variable_name_fails_before_any_write():
    bad = {"processId": "P1", "inputMap": [{"left": "nu_exista", "right": "x"}], "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError, match="neither a variable id nor a variable name"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(bad)], s)
    assert all(c["method"] == "GET" for c in s.calls)


def test_a_null_event_slot_means_no_handler_not_an_error():
    """A fresh element carries the trigger key with a null value — seen on a real
    file-upload control, which is exactly what this action is meant to wire."""
    s = FakeSession(queue=[FakeResp(200, _form(None)), FakeResp(200, _PROCESS),
                           FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "doccipf", "--on", "input",
                 "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)], s)
    assert out["updated"] is True and out["event_count"] == 1


def test_append_versus_replace_and_previous_is_returned():
    existing = {"debounce": 0, "events": [{"id": "old", "type": "INPUT",
                                           "action": "RUN_JAVASCRIPT", "config": {"code": "x"}}]}
    for flags, expected in ((["--replace"], 1), ([], 2)):
        s = FakeSession(queue=[FakeResp(200, _form(existing)), FakeResp(200, _PROCESS),
                               FakeResp(200, {})])
        out = _call("form-set-element-event",
                    ["--id", "F1", "--element", "doccipf", "--on", "input",
                     "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)] + flags, s)
        assert out["event_count"] == expected
        assert out["previous_events"][0]["id"] == "old"   # recoverable either way


def test_dry_run_writes_nothing():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "doccipf", "--on", "input", "--action",
                 "RUN_PROCESS", "--config", json.dumps(_CFG), "--dry-run"], s)
    assert out["dry_run"] is True
    assert all(c["method"] == "GET" for c in s.calls)


def test_lookup_by_id_and_a_helpful_miss():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "E1", "--on", "input",
                 "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)], s)
    assert out["elementId"] == "E1"

    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError, match="no element with id or name"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "nope", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)], s)


def test_trigger_the_element_cannot_raise_is_rejected():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError, match="cannot raise that trigger"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "click",
               "--action", "RUN_PROCESS", "--config", json.dumps(_CFG)], s)


def test_trigger_names_come_from_the_builders_verified_maps():
    """Re-deriving the trigger->type map here would let it drift from the builder's,
    and a wrong event type is silently accepted by the API."""
    from tools.procesio.dto.form import builder
    from tools.procesio.handlers import form_events
    for friendly in ("input", "click", "stepchange", "paginated"):
        assert form_events._resolve_trigger(friendly) == (
            builder._EVENT_KEY[friendly], builder._EVENT_TYPE[friendly])
    with pytest.raises(UsageError, match="unknown trigger"):
        form_events._resolve_trigger("not-a-trigger")


def test_get_element_events_reports_by_trigger():
    existing = {"debounce": 0, "events": [{"id": "e", "action": "RUN_JAVASCRIPT"}]}
    s = FakeSession(queue=[FakeResp(200, _form(existing))])
    out = _call("form-get-element-events", ["--id", "F1", "--element", "doccipf"], s)
    assert out["type"] == "file-upload"
    assert out["events"]["onInputEvents"][0]["id"] == "e"


def test_map_rows_use_the_designers_object_shape_and_survive_a_round_trip():
    """Bare strings are accepted by the API but the designer cannot render the row —
    found by reading a mapping the designer itself had written."""
    already = {"processId": "P1",
               "inputMap": [{"id": 0,
                             "left": {"value": "v-file", "isList": False, "path": {}},
                             "right": {"value": "p", "isList": False, "path": None}}],
               "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS), FakeResp(200, {})])
    _call("form-set-element-event",
          ["--id", "F1", "--element", "doccipf", "--on", "input",
           "--action", "RUN_PROCESS", "--config", json.dumps(already)], s)
    row = [c for c in s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
           if c["key"] == "onInputEvents"][0]["value"]["events"][0]["config"]["inputMap"][0]
    assert row["left"] == {"value": "v-file", "isList": False, "path": {}}
    assert row["right"] == {"value": "p", "isList": False, "path": None}


# -- RUN_DATA_STORE_OPERATION (DataStore form trigger) ----------------------

def test_datastore_trigger_writes_event_and_leaves_tree():
    # No process fetch and no concurrency refetch (form has no updatedOn) -> GET, PUT.
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "doccipf", "--on", "input",
                 "--action", "RUN_DATA_STORE_OPERATION",
                 "--data-store-id", "DS9", "--operation", "read"], s)
    put = s.calls[-1]
    assert put["method"] == "PUT" and put["url"].endswith("/api/FormTemplate")
    els = put["json"]["Data"]["elements"]
    assert els[1] == _form()["data"]["elements"][1]           # sibling untouched
    ev = [c for c in els[0]["configs"] if c["key"] == "onInputEvents"][0]["value"]["events"][0]
    assert ev["action"] == "RUN_DATA_STORE_OPERATION" and ev["type"] == "INPUT"
    cfg = ev["config"]
    assert cfg["dataStoreId"] == "DS9" and cfg["operation"] == "READ"   # name upper-cased
    assert cfg["inputMap"] == [] and cfg["outputMap"] == []
    assert cfg["filters"] == [] and cfg["areFiltersConfigured"] is False
    assert out["updated"] is True


def test_datastore_trigger_requires_datastore_id():
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError, match="dataStoreId"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_DATA_STORE_OPERATION", "--operation", "READ"], s)


def test_datastore_trigger_add_operation_omits_filters():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    _call("form-set-element-event",
          ["--id", "F1", "--element", "doccipf", "--on", "input",
           "--action", "RUN_DATA_STORE_OPERATION",
           "--data-store-id", "DS9", "--operation", "ADD"], s)
    cfg = [c for c in s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
           if c["key"] == "onInputEvents"][0]["value"]["events"][0]["config"]
    assert "filters" not in cfg                              # ADD does not support filters


def test_builder_trigger_datastore_branch():
    from tools.procesio.dto.form.builder import _trigger
    got = _trigger({"do": "datastore", "dataStoreId": "D1", "operation": "READ",
                    "inputs": [{"left": "page", "right": "root.p.val"}],
                    "filters": [{"displayName": "S", "operator": 1}]}, {})
    assert got["action"] == "RUN_DATA_STORE_OPERATION"
    assert got["config"]["dataStoreId"] == "D1"
    assert got["config"]["inputMap"] == [{"id": 0, "left": "page", "right": "root.p.val"}]
    assert got["config"]["areFiltersConfigured"] is True
