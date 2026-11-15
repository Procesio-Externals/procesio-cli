"""Client behaviour for the Web-Api v2.79.1 / v2.80.0 and Authentication-Proxy v2.38.0 step.

- Sign-in refusals: 423 account_locked (with retryAfterSeconds, 0 = unknown), 428 when a
  TOTP account sent no code, 406 when the workspace requires 2FA the account lacks.
- Uploads to one owner take a lock; one that cannot get it answers coded 215
  FILE_LIST_LOCKED and writes nothing, so the tool retries it.
- GET /health reports the Web-Api build (version + commit).
"""
import json

import pytest

from tools.procesio import errors
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import ProcesioAPIError
from tools.procesio.handlers import common
from tools.procesio import main
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V", "workspace_id": "WS1"}


def _classify(status, body):
    return errors.classify(ProcesioAPIError(status, "username/password login failed",
                                            {"body": body, "url": "u"}))


def test_a_locked_account_names_the_wait():
    code, msg, out, rc = _classify(423, {"error": "account_locked",
                                         "error_description": "Account temporarily locked.",
                                         "retryAfterSeconds": 181})
    assert (code, msg, rc) == ("account_locked", "Account temporarily locked.", 1)
    assert out["retry_after_s"] == 181 and "wait" in out["hint"]


def test_a_zero_retry_after_means_unknown_not_now():
    _, _, out, _ = _classify(423, {"error": "account_locked", "retryAfterSeconds": 0})
    assert out["retry_after_s"] is None


def test_a_totp_account_without_a_code_points_at_an_api_key():
    code, _, out, rc = _classify(428, "Authentication token is null!")
    assert code == "otp_required" and rc == 1 and "apikey" in out["hint"]


def test_the_workspace_2fa_gate_is_named():
    code, msg, out, _ = _classify(406, "Unauthorized")
    assert code == "otp_setup_required" and "two-factor" in msg and "hint" in out


def _locked():
    return ProcesioAPIError(400, "HTTP 400", {"body": [
        {"statusCode": 215, "value": "The file list is being updated by another upload. "
                                     "Retry the upload.", "target": None}]})


class _Client:
    def __init__(self, fails):
        self.fails, self.calls = fails, 0

    def request_multipart(self, path, files=None, headers=None):
        self.calls += 1
        if self.calls <= self.fails:
            raise _locked()
        return {"ok": True}


def test_an_upload_waiting_on_the_file_list_lock_is_retried():
    waits = []
    c = _Client(fails=2)
    assert common.upload_retrying_lock(c, "/api/File/upload/flow", files={},
                                       sleep=waits.append) == {"ok": True}
    assert c.calls == 3 and waits == [0.5, 1.0]


def test_a_lock_that_outlasts_the_backoff_is_raised():
    c = _Client(fails=99)
    with pytest.raises(ProcesioAPIError):
        common.upload_retrying_lock(c, "/p", files={}, sleep=lambda s: None)
    assert c.calls == len(common._UPLOAD_BACKOFF_S) + 1


def test_any_other_upload_error_is_not_retried():
    class Other(_Client):
        def request_multipart(self, path, files=None, headers=None):
            self.calls += 1
            raise ProcesioAPIError(400, "HTTP 400", {"body": [{"statusCode": 999, "value": "x"}]})
    c = Other(0)
    with pytest.raises(ProcesioAPIError):
        common.upload_retrying_lock(c, "/p", files={}, sleep=lambda s: None)
    assert c.calls == 1


def test_server_build_reads_the_health_entries():
    health = {"status": "Healthy", "entries": {"self": {"data": {
        "version": "1.17.1.3", "commit": "d5831d15"}}}}
    s = FakeSession(queue=[FakeResp(200, content=json.dumps(health).encode("utf-8"))])
    out = main.dispatch("server-build", [], client_builder=lambda prof: ProcesioClient(
        profile=APIKEY, name="t", session=s))
    assert s.calls[0]["url"].endswith("/health")
    assert out["web_api"] == {"version": "1.17.1.3", "commit": "d5831d15"}
    assert out["health"] == "Healthy" and "note" not in out


def test_server_build_says_when_the_build_is_not_reported():
    s = FakeSession(queue=[FakeResp(200, content=b'{"status": "Healthy"}')])
    out = main.dispatch("server-build", [], client_builder=lambda prof: ProcesioClient(
        profile=APIKEY, name="t", session=s))
    assert out["web_api"]["commit"] is None and "v2.80.0" in out["note"]
