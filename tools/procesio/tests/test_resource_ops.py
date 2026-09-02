"""CRUD-parity + oracle actions: correct endpoint/method, bodies, multipart import."""
from __future__ import annotations

import json

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}


def _builder(session):
    return lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session)


def _call(action, argv, session):
    return main.dispatch(action, argv, client_builder=_builder(session))


def test_get_delete_list_endpoints():
    # get
    s = FakeSession(queue=[FakeResp(200, {"id": "F1"})])
    out = _call("form-get", ["--id", "F1"], s)
    assert s.calls[0]["method"] == "GET" and s.calls[0]["url"].endswith("/api/FormTemplate/F1")
    assert out == {"result": {"id": "F1"}}
    # delete
    s = FakeSession(queue=[FakeResp(200, {})])
    out = _call("process-delete", ["--id", "P1"], s)
    assert s.calls[0]["method"] == "DELETE" and s.calls[0]["url"].endswith("/api/Projects/P1")
    assert out == {"deleted": True, "id": "P1"}
    # list (pageItems normalized)
    s = FakeSession(queue=[FakeResp(200, {"pageItems": [{"id": "a"}, {"id": "b"}]})])
    out = _call("document-list", [], s)
    assert s.calls[0]["url"].endswith("/api/DocumentTemplate")
    assert out == {"count": 2, "items": [{"id": "a"}, {"id": "b"}]}


def test_toggle_activation_reads_real_state_not_the_patch_echo():
    # The PATCH always answers {value:null,errors:[]}; the tool must report the ACTUAL
    # `active` read back from the list-processes projection (B-048 cluster 4b), and it
    # reads the state on BOTH sides so "changed" is observed rather than assumed.
    s = FakeSession(queue=[
        FakeResp(200, {"pageItems": [{"id": "P1", "active": True}]}),   # before
        FakeResp(200, {"value": None, "errors": []}),                   # the lying PATCH
        FakeResp(200, {"pageItems": [{"id": "P1", "active": False}]}),  # after
    ])
    out = _call("process-toggle-activation", ["--id", "P1"], s)
    assert s.calls[0]["method"] == "GET" and s.calls[0]["url"].endswith("/api/Projects")
    assert s.calls[1]["method"] == "PATCH"
    assert s.calls[1]["url"].endswith("/api/Projects/P1/toggle-activation")
    assert s.calls[2]["method"] == "GET" and s.calls[2]["url"].endswith("/api/Projects")
    assert out["toggled"] is True
    assert out["active_before"] is True and out["active"] is False
    assert "warning" not in out


def test_toggle_activation_does_not_claim_a_flip_that_did_not_happen():
    """The endpoint only ever deactivates: called on an inactive process it answers
    success and changes nothing. Reporting that as a toggle is the whole bug."""
    s = FakeSession(queue=[
        FakeResp(200, {"pageItems": [{"id": "P1", "active": False}]}),  # before
        FakeResp(200, {"value": None, "errors": []}),                   # "success"
        FakeResp(200, {"pageItems": [{"id": "P1", "active": False}]}),  # unchanged
    ])
    out = _call("process-toggle-activation", ["--id", "P1"], s)
    assert out["toggled"] is False, "nothing moved, so nothing was toggled"
    assert out["active"] is False
    assert "only ever sets active to FALSE" in out["warning"]


def test_toggle_activation_warns_when_it_cannot_confirm():
    s = FakeSession(queue=[
        FakeResp(200, {"pageItems": [{"id": "OTHER", "active": True}]}),  # P1 not present
        FakeResp(200, {"value": None, "errors": []}),
        FakeResp(200, {"pageItems": [{"id": "OTHER", "active": True}]}),
    ])
    out = _call("process-toggle-activation", ["--id", "P1"], s)
    assert out["active"] is None and "warning" in out
    assert out["toggled"] is None, "unknown must not read as 'did not toggle'"


def test_form_duplicate():
    s = FakeSession(queue=[FakeResp(200, {"id": "new"})])
    out = _call("form-duplicate", ["--id", "F1"], s)
    assert s.calls[0]["method"] == "POST" and s.calls[0]["url"].endswith("/api/FormTemplate/F1/duplicate")
    assert out["duplicated"] is True


def test_process_validate_empty_response_is_valid():
    # GET the flow, then POST validate -> empty 200 body == valid
    s = FakeSession(queue=[
        FakeResp(200, {"flow": {"id": "P1", "title": "T"}}),
        FakeResp(200, text="")])
    out = _call("process-validate", ["--id", "P1"], s)
    assert s.calls[0]["method"] == "GET" and s.calls[0]["url"].endswith("/api/Projects/P1")
    assert s.calls[1]["method"] == "POST" and s.calls[1]["url"].endswith("/api/Projects/validate")
    assert s.calls[1]["json"]["title"] == "T"             # posts the flow DTO
    assert out["isValid"] is True and out["errors"] == []


def test_process_validate_errors_surface():
    # validator rejects -> platform 4xx with the error list -> isValid False + errors
    s = FakeSession(queue=[
        FakeResp(200, {"flow": {"id": "P1"}}),
        FakeResp(400, {"body": [{"value": "Action has too many input ports."}]})])
    out = _call("process-validate", ["--id", "P1"], s)
    assert out["isValid"] is False
    assert out["errors"] == [{"value": "Action has too many input ports."}]


def test_webhook_launch_with_payload():
    s = FakeSession(queue=[FakeResp(200, {"ok": True})])
    out = _call("webhook-launch", ["--id", "W1", "--payload", '{"x":1}'], s)
    assert s.calls[0]["method"] == "POST" and s.calls[0]["url"].endswith("/api/Webhooks/launch/W1")
    assert s.calls[0]["json"] == {"x": 1} and out["launched"] is True


def test_import_multipart(tmp_path):
    bundle = tmp_path / "b.procesio"
    bundle.write_bytes(b'{"Flows":[]}')
    s = FakeSession(queue=[FakeResp(200, {"imported": 1})])
    out = _call("import", ["--file", str(bundle)], s)
    assert s.calls[0]["method"] == "POST" and s.calls[0]["url"].endswith("/api/Transport/import")
    # ⚠ THE PART IS `importedData`, NOT `file`. This assertion previously
    # encoded the wrong name: `POST api/Transport/import` documents the part as
    # `importedData`, and the endpoint reports a wrongly named part only as a
    # generic 403/MIGRATE, so nothing about the response would have revealed it.
    field = s.calls[0]["files"]["importedData"]
    assert field[0] == "b.procesio" and field[1] == b'{"Flows":[]}'
    # ⚠ and all seven required boolean headers must go with it
    sent = s.calls[0].get("headers") or {}
    for wire in ("overrideData", "importDataTypes", "importFlows",
                 "importCredentials", "importDocuments", "importForms",
                 "importDataStores"):
        assert sent.get(wire) == "true", "missing required header " + wire
    assert out["imported"] is True and out["bytes"] == 12
    # the captured headers also carry auth and user-agent, so the echo is
    # compared as a SUBSET rather than for equality
    assert out["headers_sent"].items() <= sent.items(), (
        "the result must echo the flags it sent: a 403 from this endpoint "
        "cannot be read without knowing what was asked")


def test_credential_test_builds_dto_and_probes():
    # GET /api/Credentials/types (template resolve), POST /api/Credentials/test (probe x2:
    # once inside prepare_ctx, once in the action) -> return the last verdict
    tmpl = {"name": "REST API", "gid": "G", "pid": "P",
            "properties": [{"id": "u", "label": "URL", "validations": {"isRequired": True}}]}
    def responder(method, url, kw):
        if url.endswith("/api/Credentials/types"):
            return FakeResp(200, [tmpl])
        if url.endswith("/api/Credentials/test"):
            return FakeResp(200, {"isSuccess": True})
        return FakeResp(200, {})
    s = FakeSession(responder=responder)
    out = _call("credential-test", ["--config", json.dumps({"template": "REST API", "name": "x",
                                                             "properties": {"URL": "https://a"}})], s)
    assert any(c["url"].endswith("/api/Credentials/test") for c in s.calls)
    assert out == {"tested": True, "isSuccess": True, "result": {"isSuccess": True}}
