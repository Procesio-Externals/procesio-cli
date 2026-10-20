"""customaction-test runs an action in test mode and polls for the resolved result.

POST /api/Actions/test only STARTS the test and returns a server-assigned gid; the
result is produced asynchronously, so the handler polls GET /api/Actions/test/{gid}
until a terminal status and returns {status, errorMessage, testResult, variables}.
The friendly path builds the request from the live catalog (built-in OR a workspace
custom action), binding each supplied input and every output to a test variable.
"""
import time

import tools.procesio.handlers.resource_ops as ro

FAKE_ACTION = {
    "actionId": "11111111-1111-1111-1111-111111111111",
    "name": "Demo Action",
    "isProcesioAction": False,
    "configuration": [
        {"label": "Config", "settings": [
            {"id": "a1a1a1a1-0000-0000-0000-000000000001", "label": "Input One",
             "direction": 1, "dataTypeId": "dt-string"},
            {"id": "b2b2b2b2-0000-0000-0000-000000000002", "label": "Result",
             "direction": 3, "dataTypeId": "dt-string"},
        ]},
    ],
}


class _FakeClient:
    def __init__(self, polls=None):
        self.posted = None
        self._polls = list(polls or [])

    def get(self, path, query=None, **kw):
        if path == "/api/Actions/node":          # the scoped custom-action fetch
            return {"actions": [FAKE_ACTION]}
        return self._polls.pop(0)                 # a test-result poll

    def post(self, path, body=None, query=None, **kw):
        self.posted = (path, body)
        return {"testActionInstance": {"gid": "ta-123"}}


def test_build_request_binds_supplied_inputs_and_every_output():
    body = ro._build_test_request(_FakeClient(), "Demo Action", {"Input One": "hello"})
    assert body["Action"]["gtid"] == "11111111-1111-1111-1111-111111111111"
    bound = {p["TabPropertyId"] for p in body["Action"]["parameters"]}
    assert bound == {"a1a1a1a1-0000-0000-0000-000000000001",   # input bound
                     "b2b2b2b2-0000-0000-0000-000000000002"}    # output captured
    assert [v["Type"] for v in body["variables"]] == [10, 30]   # INPUT / OUTPUT
    assert body["TestValues"] == [
        {"VariableId": body["variables"][0]["Id"], "Value": "hello", "Attribute": None}]


def test_unknown_value_label_is_rejected():
    import pytest
    with pytest.raises(ro.UsageError):
        ro._build_test_request(_FakeClient(), "Demo Action", {"Nope": 1})


def test_run_test_action_polls_until_terminal_and_parses_result(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = _FakeClient(polls=[
        {"status": 30},                                           # still running
        {"status": 40, "errorMessage": None,                     # terminal (success)
         "testResult": '{"b2b2b2b2-0000-0000-0000-000000000002": {"ok": 1}}',
         "variables": []},
    ])
    out = ro._run_test_action(c, {"Gid": "x"}, timeout=30)
    assert out["tested"] is True and out["gid"] == "ta-123"
    assert out["status"] == 40 and out["errorMessage"] is None
    assert out["testResult"] == {"b2b2b2b2-0000-0000-0000-000000000002": {"ok": 1}}


def test_run_test_action_stops_on_failure_status_90(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = _FakeClient(polls=[
        {"status": 90, "errorMessage": "boom", "errorCode": 400, "testResult": "{}"},
    ])
    out = ro._run_test_action(c, {"Gid": "x"}, timeout=30)
    assert out["status"] == 90 and out["errorMessage"] == "boom"
