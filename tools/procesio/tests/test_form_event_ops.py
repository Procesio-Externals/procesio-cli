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
from tools.procesio.dto.form import fieldpath
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


NS = fieldpath.FIELDS_NS

# A realistic live form: every value-bearing control carries the `value` config whose id is
# the fourth segment of that field's path. The earlier fixture omitted them and mapped to
# invented strings like "root.upload.val", which passed only because nothing checked — the
# same permissiveness that let five autonomous builds write a path the platform accepts and
# the runtime ignores.
def _form(event_value=None):
    return {
        "id": "F1", "name": "Some form", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {
            "code": "", "theme": [{"label": "Colors"}], "dataModel": {"id": "dm"},
            "elements": [
                {"id": "E1", "type": "file-upload", "configs": [
                    {"key": "name", "value": "doccipf"},
                    {"key": "value", "id": "vc-E1"},
                    {"key": "onInputEvents", "value": event_value},
                ]},
                {"id": "E2", "type": "input", "configs": [
                    {"key": "name", "value": "nume"},
                    {"key": "value", "id": "vc-E2"},
                ]},
            ],
        },
    }


def _live(form):
    return fieldpath.LiveForm(form)


PATH_E1 = f"dm.{NS}.E1.vc-E1"
PATH_E2 = f"dm.{NS}.E2.vc-E2"

_PROCESS = {"flow": {"id": "P1", "variables": [
    {"id": "v-file", "name": "fisier"}, {"id": "v-nume", "name": "nume_extras"}]}}

# Mapped by field NAME — the calling convention the action now resolves for you.
_CFG = {"processId": "P1",
        "inputMap": [{"left": "fisier", "right": "doccipf"}],
        "outputMap": [{"left": "nume_extras", "right": "nume"}]}


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
    # The form side is resolved too: a field NAME becomes its four-segment value path.
    assert ev["config"]["inputMap"][0]["right"] == {
        "value": PATH_E1, "isList": False, "path": None}
    assert ev["config"]["outputMap"][0]["right"] == {
        "value": PATH_E2, "isList": False, "path": None}
    assert ev["config"]["syncRun"] is True
    # the canonical RUN_PROCESS keys the designer needs are backfilled from a minimal config
    assert ev["config"]["areConditionsConfigured"] is True
    assert ev["config"]["conditions"] == [] and ev["config"]["mapLatestTriggerOnly"] is False
    assert out["updated"] is True and out["previous_events"] == []


def test_unknown_variable_name_fails_before_any_write():
    bad = {"processId": "P1", "inputMap": [{"left": "nu_exista", "right": "doccipf"}],
           "outputMap": []}
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
                             "right": {"value": PATH_E1, "isList": False, "path": None}}],
               "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS), FakeResp(200, {})])
    _call("form-set-element-event",
          ["--id", "F1", "--element", "doccipf", "--on", "input",
           "--action", "RUN_PROCESS", "--config", json.dumps(already)], s)
    row = [c for c in s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
           if c["key"] == "onInputEvents"][0]["value"]["events"][0]["config"]["inputMap"][0]
    assert row["left"] == {"value": "v-file", "isList": False, "path": {}}
    assert row["right"] == {"value": PATH_E1, "isList": False, "path": None}


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


# -- the form side of a map row: resolved, or refused -----------------------
#
# A wrong value path is the one mistake nothing downstream reports: the API answers
# `updated: true`, the designer renders the mapping, and clicking the control launches
# nothing. Measured across five autonomous builds, every one wrote
# `root.fields.<elementId>.value` — the NAMES from the guide's tree diagram substituted for
# the ids printed beside them. Since the platform will not object, the write is the last
# place the mistake can be caught.

def test_an_invented_value_path_is_refused_before_any_write():
    bad = {"processId": "P1",
           "inputMap": [{"left": "fisier", "right": "root.fields.E1.value"}],
           "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError) as e:
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(bad)], s)
    assert all(c["method"] == "GET" for c in s.calls), "nothing may be written"
    msg = str(e.value)
    assert "segment 1 'root'" in msg and "segment 2 'fields'" in msg
    assert PATH_E1 in msg, "the message must carry the correct path"
    assert "doccipf" in msg, "…and the field name that would have worked"


def test_a_correct_value_path_passes_through_untouched():
    """Back-compat for a caller that builds the path itself — but on validity, not on
    the presence of dots."""
    ok = {"processId": "P1",
          "inputMap": [{"left": "fisier", "right": PATH_E1}], "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS), FakeResp(200, {})])
    _call("form-set-element-event",
          ["--id", "F1", "--element", "doccipf", "--on", "input",
           "--action", "RUN_PROCESS", "--config", json.dumps(ok)], s)
    row = [c for c in s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
           if c["key"] == "onInputEvents"][0]["value"]["events"][0]["config"]["inputMap"][0]
    assert row["right"]["value"] == PATH_E1


def test_a_value_config_id_borrowed_from_another_element_is_refused():
    """The subtle one: four id-shaped segments, correct root and namespace, but the value
    id belongs to a DIFFERENT element. Nothing downstream notices."""
    crossed = {"processId": "P1",
               "inputMap": [{"left": "fisier", "right": f"dm.{NS}.E1.vc-E2"}],
               "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError, match="must be that element's own"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(crossed)], s)
    assert all(c["method"] == "GET" for c in s.calls)


def test_a_path_pointing_at_no_element_of_this_form_is_refused():
    stray = {"processId": "P1",
             "inputMap": [{"left": "fisier", "right": f"dm.{NS}.E9.vc-E9"}], "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError, match="is not an element on this form"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(stray)], s)


def test_neither_a_field_name_nor_a_path_lists_the_fields():
    junk = {"processId": "P1",
            "inputMap": [{"left": "fisier", "right": "campul-meu"}], "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError) as e:
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(junk)], s)
    assert "doccipf" in str(e.value) and "nume" in str(e.value)


def test_a_control_that_holds_no_value_cannot_be_mapped():
    form = _form()
    form["data"]["elements"].append(
        {"id": "E3", "type": "heading", "configs": [{"key": "name", "value": "titlu"}]})
    cfg = {"processId": "P1",
           "inputMap": [{"left": "fisier", "right": "titlu"}], "outputMap": []}
    s = FakeSession(queue=[FakeResp(200, form), FakeResp(200, _PROCESS)])
    with pytest.raises(UsageError) as e:
        _call("form-set-element-event",
              ["--id", "F1", "--element", "doccipf", "--on", "input",
               "--action", "RUN_PROCESS", "--config", json.dumps(cfg)], s)
    # The name IS on the form, so the refusal says why that control cannot hold a value —
    # more use than a generic "not a field" would be.
    assert "has no 'value' config" in str(e.value) and "heading" in str(e.value)
    # …and it is not offered as a destination anywhere.
    assert "titlu" not in _live(form).field_names()


def test_a_file_viewer_maps_through_its_src_config():
    """The one control whose value config is not named `value` — kept in the shared rule so
    the builder and this action cannot disagree about it."""
    form = _form()
    form["data"]["elements"].append(
        {"id": "E4", "type": "file-viewer", "configs": [
            {"key": "name", "value": "previzualizare"}, {"key": "src", "id": "vc-E4"}]})
    cfg = {"processId": "P1", "inputMap": [],
           "outputMap": [{"left": "nume_extras", "right": "previzualizare"}]}
    s = FakeSession(queue=[FakeResp(200, form), FakeResp(200, _PROCESS), FakeResp(200, {})])
    _call("form-set-element-event",
          ["--id", "F1", "--element", "doccipf", "--on", "input",
           "--action", "RUN_PROCESS", "--config", json.dumps(cfg)], s)
    row = [c for c in s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
           if c["key"] == "onInputEvents"][0]["value"]["events"][0]["config"]["outputMap"][0]
    assert row["right"]["value"] == f"dm.{NS}.E4.vc-E4"


def test_the_builder_and_the_event_editor_share_one_path_rule():
    """Two places produce these paths. A second copy of the rule would be a rule nothing
    enforces, and the platform accepts a wrong path without any error."""
    from tools.procesio.dto.form import builder
    assert builder._FIELDS_NS is fieldpath.FIELDS_NS
    assert builder._value_key is fieldpath.value_key
    assert builder._VALUE_CONFIG_KEY is fieldpath.VALUE_CONFIG_KEY
