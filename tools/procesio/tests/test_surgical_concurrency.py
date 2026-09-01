"""Optimistic-concurrency guard shared by the surgical write actions.

A surgical action reads the live DTO, changes one field, and PUTs the whole thing
back — last-write-wins. The guard re-reads right before the PUT and refuses to
overwrite if the resource's update-token moved since it was read. It is INERT when
the resource exposes no update-timestamp/version field (a safe no-op, never a false
conflict), which is why the token-less fakes in the other suites are unaffected.
"""
from __future__ import annotations

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import UsageError
from tools.procesio.handlers import common
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
KEY = "test-passphrase"


# -- guard unit ---------------------------------------------------------------

def test_concurrency_token_matches_common_fields_case_insensitively():
    assert common.concurrency_token({"updatedOn": "2026-08-07T10:00:00Z"})[1] == "2026-08-07T10:00:00Z"
    assert common.concurrency_token({"Version": 7})[1] == 7
    assert common.concurrency_token({"name": "x", "data": {}}) is None   # no token field
    assert common.concurrency_token("not a dict") is None


def test_guard_is_inert_without_a_token_and_never_refetches():
    calls = []
    def refetch():
        calls.append(1); return {}
    out = common.guard_unchanged(refetch, {"name": "no token here"}, force=False)
    assert out["checked"] is False and "inactive" in out["note"]
    assert calls == []                                    # no extra GET when inert


def test_guard_passes_when_the_token_is_unchanged():
    base = {"updatedOn": "T1"}
    out = common.guard_unchanged(lambda: {"updatedOn": "T1"}, base, force=False)
    assert out == {"checked": True, "token": "T1"}


def test_guard_aborts_when_the_token_moved():
    base = {"updatedOn": "T1"}
    with pytest.raises(UsageError, match="changed since it was read"):
        common.guard_unchanged(lambda: {"updatedOn": "T2"}, base, force=False)


def test_force_skips_the_check_and_does_not_refetch():
    calls = []
    def refetch():
        calls.append(1); return {"updatedOn": "T2"}
    out = common.guard_unchanged(refetch, {"updatedOn": "T1"}, force=True)
    assert out["forced"] is True and out["checked"] is False
    assert calls == []                                    # forced -> no refetch


# -- integration through form-set-code ---------------------------------------

@pytest.fixture(autouse=True)
def _stub_key(monkeypatch):
    monkeypatch.setattr("tools.procesio.handlers.form_code._code_key", lambda: KEY)


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _form(updated_on):
    """A form DTO that carries an update token, so the guard is ACTIVE on it."""
    return {"id": "F1", "name": "F", "isPrivate": False, "type": 1, "status": 1,
            "state": True, "assignees": [], "customUrl": None, "updatedOn": updated_on,
            "data": {"code": "", "elements": []}}


def test_set_code_proceeds_when_the_form_is_unchanged():
    # GET (read) -> GET (guard re-read, same token) -> PUT
    s = FakeSession(queue=[FakeResp(200, _form("T1")), FakeResp(200, _form("T1")),
                           FakeResp(200, {})])
    out = _call("form-set-code", ["--id", "F1", "--css", ".x{}"], s)
    assert out["updated"] is True and out["concurrency"] == {"checked": True, "token": "T1"}
    assert s.calls[-1]["method"] == "PUT"


def test_set_code_aborts_when_the_form_changed_since_read():
    # GET (read, T1) -> GET (guard re-read, T2) -> abort BEFORE any PUT
    s = FakeSession(queue=[FakeResp(200, _form("T1")), FakeResp(200, _form("T2"))])
    with pytest.raises(UsageError, match="changed since it was read"):
        _call("form-set-code", ["--id", "F1", "--css", ".x{}"], s)
    assert all(c["method"] == "GET" for c in s.calls)     # never wrote


def test_set_code_force_overwrites_without_re_reading():
    # force -> no guard GET: GET (read) -> PUT
    s = FakeSession(queue=[FakeResp(200, _form("T1")), FakeResp(200, {})])
    out = _call("form-set-code", ["--id", "F1", "--css", ".x{}", "--force"], s)
    assert out["updated"] is True and out["concurrency"]["forced"] is True
    assert sum(1 for c in s.calls if c["method"] == "GET") == 1   # single read, no guard GET
    assert s.calls[-1]["method"] == "PUT"


# -- integration through rename-actions (the other guarded writer) ------------

class _FlowClient:
    """A process client whose flow token can move between the baseline read and the
    guard's re-read, to exercise rename-actions' concurrency guard."""
    def __init__(self, tokens):
        self.workspace_id = "ws"
        self.profile = {}                             # unbound -> production designer host
        self._tokens = list(tokens)
        self.i = 0
        self.puts = []

    def _flow(self):
        tok = self._tokens[min(self.i, len(self._tokens) - 1)]
        self.i += 1
        return {"id": "P", "updatedOn": tok,
                "actions": [{"id": "a1", "actionName": "Node",
                             "customData": {"name": "Node"}}]}

    def get(self, path, query=None):
        return {"flow": self._flow()}

    def post(self, path, body=None, query=None):
        return {"raw_text": ""}

    def put(self, path, body=None, query=None):
        self.puts.append(body)
        return {}


def _rename_args(force=False):
    from argparse import Namespace
    return Namespace(id="P", workspace_id="ws", profile=None, map='{"a1": "Renamed"}',
                     map_file=None, no_validate=True, dry_run=False, force=force)


def test_rename_actions_proceeds_when_the_flow_is_unchanged():
    from tools.procesio.handlers import process_naming as pn
    c = _FlowClient(["T1", "T1"])                      # baseline read + guard re-read: same
    out = pn.rename_actions(c, _rename_args())["result"]
    assert out["saved"] is True and out["concurrency"] == {"checked": True, "token": "T1"}
    assert len(c.puts) == 1


def test_rename_actions_aborts_when_the_flow_moved():
    from tools.procesio.handlers import process_naming as pn
    c = _FlowClient(["T1", "T2"])                      # token moved between read and re-read
    with pytest.raises(UsageError, match="changed since it was read"):
        pn.rename_actions(c, _rename_args())
    assert c.puts == []                                # never saved
