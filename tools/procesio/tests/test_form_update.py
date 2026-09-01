"""form-update: safe GET->deep-merge->PUT of a live form.

Verifies the accepted PascalCase envelope, deep-merge semantics (nested merge,
array/scalar replace), top-level overrides (rename/publish), dry-run, and usage
errors. CustomUrl is ECHOED from the GET (main's behaviour; the PUT ignores it
either way — verified live). HTTP via FakeSession (no live API)."""
from __future__ import annotations

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.handlers.form_code import build_put_body
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
ENVELOPE = {"Id", "Name", "IsPrivate", "Type", "Status", "State", "Assignees", "Data", "CustomUrl"}


def _call(action, argv, session):
    builder = lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session)
    return main.dispatch(action, argv, client_builder=builder)


def _form(*, status=1, state=True, data=None):
    """A GET echo (camelCase) with server metadata that must be dropped from the PUT.
    No updatedOn/version field, so the concurrency guard is inert (GET + PUT only)."""
    d = data or {
        "code": "ENC", "elements": [{"id": "el1"}], "theme": [], "hideBranding": False,
        "images": {"logo": None, "header": "H"},
    }
    return {
        "id": "F1", "name": "Overview", "isPrivate": False, "type": 1,
        "status": status, "state": state, "assignees": [],
        "customUrl": {"tinyUrl": "t"},                 # separate entity — echoed, PUT ignores it
        "createdBy": "server-meta", "workspaceName": "server-meta",  # server metadata, dropped
        "data": d,
    }


def test_scalar_patch_builds_accepted_envelope_and_preserves_data():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    out = _call("form-update", ["--id", "F1", "--data", '{"hideBranding": true}'], s)

    assert out["applied"] is True and out["patched_keys"] == ["hideBranding"]
    get, put = s.calls
    assert get["method"] == "GET" and get["url"].endswith("/api/FormTemplate/F1")
    assert put["method"] == "PUT" and put["url"].endswith("/api/FormTemplate")
    body = put["json"]
    # PascalCase top level only, no server metadata, CustomUrl echoed
    assert set(body) == ENVELOPE
    assert body["Id"] == "F1" and body["Name"] == "Overview"
    assert body["CustomUrl"] == {"tinyUrl": "t"}
    # patched key applied; everything else in Data round-trips untouched
    assert body["Data"]["hideBranding"] is True
    assert body["Data"]["elements"] == [{"id": "el1"}]
    assert body["Data"]["code"] == "ENC"
    assert body["Data"]["images"] == {"logo": None, "header": "H"}


def test_nested_merge_and_array_replace():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    _call("form-update",
          ["--id", "F1", "--data", '{"images": {"logo": "X"}, "elements": [{"id": "new"}]}'], s)
    data = s.calls[1]["json"]["Data"]
    assert data["images"] == {"logo": "X", "header": "H"}   # nested dict merges (header kept)
    assert data["elements"] == [{"id": "new"}]              # array replaces wholesale


def test_top_level_overrides_publish_a_draft():
    s = FakeSession(queue=[FakeResp(200, _form(status=0, state=False)), FakeResp(200, {})])
    out = _call("form-update",
                ["--id", "F1", "--name", "ENG/ Overview", "--status", "1", "--state", "true"], s)
    body = s.calls[1]["json"]
    assert body["Name"] == "ENG/ Overview" and body["Status"] == 1 and body["State"] is True
    assert out["name"] == "ENG/ Overview" and out["status"] == 1 and out["state"] is True
    assert out["patched_keys"] == []                        # no Data patch given


def test_dry_run_gets_only_and_returns_dto():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-update", ["--id", "F1", "--data", '{"hideBranding": true}', "--dry-run"], s)
    assert out["applied"] is False and out["dry_run"] is True
    assert out["dto"]["Data"]["hideBranding"] is True
    assert len(s.calls) == 1 and s.calls[0]["method"] == "GET"


def test_usage_errors():
    with pytest.raises(errors.UsageError):   # nothing to update (no patch, no override) -> no GET
        _call("form-update", ["--id", "F1"], FakeSession(queue=[]))
    with pytest.raises(errors.UsageError):   # invalid JSON, rejected before any HTTP call
        _call("form-update", ["--id", "F1", "--data", "{bad"], FakeSession(queue=[]))
    with pytest.raises(errors.UsageError):   # patch must be an object, not an array
        _call("form-update", ["--id", "F1", "--data", "[1, 2]"], FakeSession(queue=[]))


def test_build_put_body_transform_contract():
    """The single canonical transform: camelCase echo -> PascalCase envelope, CustomUrl echoed."""
    echo = _form(status=0, state=False)
    body = build_put_body(echo, data={"k": 1}, name="R", status=1, state=True)
    assert set(body) == ENVELOPE
    assert body["Name"] == "R" and body["Status"] == 1 and body["State"] is True
    assert body["Data"] == {"k": 1} and body["CustomUrl"] == {"tinyUrl": "t"}
    # omitted overrides fall back to the echo's values
    keep = build_put_body(echo)
    assert keep["Name"] == "Overview" and keep["Status"] == 0 and keep["State"] is False
    # missing required echo key is refused
    with pytest.raises(errors.UsageError):
        build_put_body({"id": "X", "name": "Y"})   # no 'data'


# --------------------------------------------------------------- IsPrivate (publishing switch)

def test_is_private_is_echoed_untouched_when_not_asked_for():
    """Reachability is a publishing decision: an unrelated save must never flip it."""
    form = {"id": "f1", "name": "F", "data": {"elements": []}, "isPrivate": True,
            "type": 1, "status": 1, "state": True, "assignees": [], "customUrl": None}
    body = build_put_body(form, name="Renamed")
    assert body["IsPrivate"] is True


def test_is_private_false_is_what_opens_a_form_to_an_anonymous_visitor():
    form = {"id": "f1", "name": "F", "data": {"elements": []}, "isPrivate": True,
            "type": 1, "status": 1, "state": True, "assignees": [], "customUrl": None}
    body = build_put_body(form, is_private=False)
    assert body["IsPrivate"] is False
    assert body["Status"] == 1, "publishing also needs Status 1, which must survive untouched"


def test_is_private_can_be_put_back():
    form = {"id": "f1", "name": "F", "data": {"elements": []}, "isPrivate": False,
            "type": 1, "status": 1, "state": True, "assignees": [], "customUrl": None}
    assert build_put_body(form, is_private=True)["IsPrivate"] is True
