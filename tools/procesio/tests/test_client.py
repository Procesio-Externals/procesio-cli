"""ProcesioClient: URL building, header injection, error mapping, 401 retry."""
from __future__ import annotations

import pytest

from tools.procesio import profiles
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import ProcesioAPIError
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _client(profile, session):
    return ProcesioClient(profile=profile, name="t", session=session)


def test_get_builds_url_and_injects_apikey_headers():
    sess = FakeSession(queue=[FakeResp(200, {"ok": True})])
    c = _client({"type": "apikey", "key": "N", "value": "V", "workspace_id": "WS"}, sess)
    out = c.get("/api/Workspaces")
    assert out == {"ok": True}
    call = sess.calls[0]
    assert call["url"] == "https://webapi.procesio.app/api/Workspaces"
    assert call["headers"]["key"] == "N"
    assert call["headers"]["value"] == "V"
    assert call["headers"]["workspaceid"] == "WS"


def test_query_drops_none_values():
    sess = FakeSession(queue=[FakeResp(200, [])])
    c = _client({"type": "apikey", "key": "N", "value": "V"}, sess)
    c.get("/api/Projects", {"pageNumber": 1, "searchName": None})
    assert sess.calls[0]["params"] == {"pageNumber": 1}


def test_non_2xx_raises_apierror_with_status():
    sess = FakeSession(queue=[FakeResp(403, {"message": "nope"})])
    c = _client({"type": "apikey", "key": "N", "value": "V"}, sess)
    with pytest.raises(ProcesioAPIError) as ei:
        c.get("/api/Projects")
    assert ei.value.status == 403
    assert ei.value.details["message"] == "nope"


def test_userpass_401_triggers_relogin_retry(store):
    from tools.procesio import auth
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    # Far-future expiry -> treated as fresh and used (an unknown/None expiry is now
    # distrusted, forcing a pre-emptive re-login). This exercises the 401-retry path:
    # the cached token IS sent, the GET 401s, then the client re-logins and retries.
    profiles.set_token_cache("u", {"cookies": {auth.ACCESS_COOKIE: "STALE"},
                                   "expires_at": 9999999999})
    # 1st GET -> 401 ; client clears cache, re-logs-in, retries -> 200
    sess = FakeSession(queue=[
        FakeResp(401, {"message": "expired"}),                                   # the GET
        FakeResp(200, {"message": "ok"}, cookies={auth.ACCESS_COOKIE: "FRESH"}),  # re-login
        FakeResp(200, {"ok": 1}),                                                # retried GET
    ])
    c = ProcesioClient(profile=profiles.get_profile("u"), name="u", session=sess)
    out = c.get("/api/Workspaces")
    assert out == {"ok": 1}
    # final retried GET carried the FRESH session cookie
    assert "FRESH" in sess.calls[-1]["headers"]["Cookie"]


def test_post_sets_content_type_and_body():
    sess = FakeSession(queue=[FakeResp(200, {"id": "x"})])
    c = _client({"type": "apikey", "key": "N", "value": "V"}, sess)
    c.post("/api/Projects/abc/run", {"payload": {}, "connectionid": None})
    call = sess.calls[0]
    assert call["json"] == {"payload": {}, "connectionid": None}
    assert call["headers"]["Content-Type"] == "application/json"


def test_userpass_403_also_triggers_reauth_retry(store):
    """A REJECTED session comes back 403, not 401 (measured against the prod
    gateway). Treating 403 as final surfaced a stale session as an unactionable
    permission error."""
    from tools.procesio import auth
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": {auth.ACCESS_COOKIE: "STALE"},
                                   "expires_at": 9999999999})
    sess = FakeSession(queue=[
        FakeResp(403, {"message": "rejected"}),                                   # the GET
        FakeResp(200, {"message": "ok"}, cookies={auth.ACCESS_COOKIE: "FRESH"}),  # re-login
        FakeResp(200, {"ok": 1}),                                                 # retried GET
    ])
    c = ProcesioClient(profile=profiles.get_profile("u"), name="u", session=sess)
    assert c.get("/api/Workspaces") == {"ok": 1}
    assert "FRESH" in sess.calls[-1]["headers"]["Cookie"]


def test_reauth_is_one_shot_so_a_real_permission_denial_still_raises(store):
    from tools.procesio import auth
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": {auth.ACCESS_COOKIE: "OK"},
                                   "expires_at": 9999999999})
    sess = FakeSession(queue=[
        FakeResp(403, {"message": "denied"}),
        FakeResp(200, {"message": "ok"}, cookies={auth.ACCESS_COOKIE: "FRESH"}),
        FakeResp(403, {"message": "denied"}),     # still denied -> genuine
    ])
    c = ProcesioClient(profile=profiles.get_profile("u"), name="u", session=sess)
    with pytest.raises(ProcesioAPIError) as e:
        c.get("/api/Workspaces")
    assert e.value.status == 403


def test_apikey_403_is_never_retried(store):
    """Only a userpass SESSION can go stale; an API key that is denied is denied."""
    sess = FakeSession(queue=[FakeResp(403, {"message": "denied"})])
    c = _client({"type": "apikey", "key": "N", "value": "V"}, sess)
    with pytest.raises(ProcesioAPIError):
        c.get("/api/Workspaces")
    assert len(sess.calls) == 1
