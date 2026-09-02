"""Auth: cookie-session login, header construction, caching, expiry."""
from __future__ import annotations

import time

import pytest

from tools.procesio import auth, profiles
from tools.procesio.errors import AuthError, ProcesioAPIError
from tools.procesio.tests.conftest import FakeResp, FakeSession

_COOKIES = {auth.ACCESS_COOKIE: "AAA", auth.REFRESH_COOKIE: "RRR"}


# -- login (form POST + cookies) --------------------------------------------

def test_login_form_post_shape_and_cookies():
    profile = {"type": "userpass", "username": "u@example.com", "password": "p"}
    sess = FakeSession(queue=[FakeResp(200, {"message": "Authentication successful"},
                                       cookies=_COOKIES,
                                       headers={"x-session-expires-at": "1893456000"})])
    tok = auth.login(profile, sess)
    assert tok["cookies"][auth.ACCESS_COOKIE] == "AAA"
    assert tok["expires_at"] == 1893456000.0
    call = sess.calls[0]
    assert call["url"] == "https://webapi.procesio.app/api/authentication"
    assert call["data"] == {"username": "u@example.com", "password": "p",
                            "client_id": "procesio-ui"}      # form body, not json
    assert call["json"] is None
    assert call["headers"]["x-requested-by"] == "playground-v1"
    assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_login_non_2xx_raises():
    profile = {"type": "userpass", "username": "u", "password": "p"}
    sess = FakeSession(queue=[FakeResp(407, {}, "Unauthorized")])
    with pytest.raises(ProcesioAPIError) as ei:
        auth.login(profile, sess)
    assert ei.value.status == 407


def test_login_2xx_without_access_cookie_raises():
    profile = {"type": "userpass", "username": "u", "password": "p"}
    sess = FakeSession(queue=[FakeResp(200, {"message": "ok"}, cookies={})])
    with pytest.raises(AuthError):
        auth.login(profile, sess)


def test_parse_expiry_iso_and_epoch():
    assert auth._parse_expiry("1893456000") == 1893456000.0
    assert auth._parse_expiry(None) is None
    iso = auth._parse_expiry("2030-01-01T00:00:00Z")
    assert iso and iso > time.time()


# -- auth_headers: apikey ---------------------------------------------------

def test_apikey_headers_include_workspaceid(store):
    profiles.save_profile("k", {"type": "apikey", "key": "N", "value": "V",
                                "workspace_id": "WS"})
    h = auth.auth_headers("k", profiles.get_profile("k"), FakeSession())
    assert h == {"key": "N", "value": "V", "workspaceid": "WS"}


def test_apikey_headers_without_workspaceid(store):
    profiles.save_profile("k", {"type": "apikey", "key": "N", "value": "V"})
    h = auth.auth_headers("k", profiles.get_profile("k"), FakeSession())
    assert h == {"key": "N", "value": "V"}


# -- auth_headers: userpass (cookie) ----------------------------------------

def test_userpass_uses_cached_cookies(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": _COOKIES, "expires_at": time.time() + 9999})
    sess = FakeSession()  # must NOT be called - session is fresh
    h = auth.auth_headers("u", profiles.get_profile("u"), sess)
    assert h["x-requested-by"] == "playground-v1"
    assert auth.ACCESS_COOKIE in h["Cookie"] and "AAA" in h["Cookie"]
    assert sess.calls == []


def test_userpass_logs_in_when_no_cache(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    sess = FakeSession(queue=[FakeResp(200, {"message": "ok"}, cookies=_COOKIES,
                                       headers={"x-session-expires-at": "1893456000"})])
    h = auth.auth_headers("u", profiles.get_profile("u"), sess)
    assert "AAA" in h["Cookie"]
    assert profiles.get_token_cache("u")["cookies"][auth.ACCESS_COOKIE] == "AAA"


def test_userpass_relogs_in_when_expired(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": {auth.ACCESS_COOKIE: "OLD"},
                                   "expires_at": time.time() - 10})   # expired
    sess = FakeSession(queue=[FakeResp(200, {"message": "ok"},
                                       cookies={auth.ACCESS_COOKIE: "NEW"})])
    h = auth.auth_headers("u", profiles.get_profile("u"), sess)
    assert "NEW" in h["Cookie"] and "OLD" not in h["Cookie"]


# -- session renewal: refresh before re-sending the password ------------------

def _refresh_resp(access="NEW", refresh="RNEW"):
    return FakeResp(200, {"message": "Token refreshed successfully"},
                    cookies={auth.ACCESS_COOKIE: access, auth.REFRESH_COOKIE: refresh})


def test_persist_caches_both_cookies(store):
    """The refresh cookie is the whole point of caching - dropping it forces a
    full username/password login every ~30 min (the access JWT's lifetime)."""
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    auth._persist_cookies("u", {"cookies": _COOKIES, "expires_at": 123.0})
    assert profiles.get_token_cache("u")["cookies"][auth.ACCESS_COOKIE] == "AAA"
    assert profiles.get_refresh_cookie("u") == "RRR"


def test_expired_access_refreshes_instead_of_logging_in(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": _COOKIES, "expires_at": time.time() - 10})
    sess = FakeSession(queue=[_refresh_resp()])
    h = auth.auth_headers("u", profiles.get_profile("u"), sess)
    assert "NEW" in h["Cookie"]
    assert len(sess.calls) == 1
    assert sess.calls[0]["url"].endswith(auth.REFRESH_PATH)
    # the password was never sent
    assert "password" not in (sess.calls[0].get("data") or {})
    assert sess.calls[0]["data"]["refresh_token"] == "RRR"
    # and the renewed pair replaced the cache (access + its own refresh entry)
    assert profiles.get_token_cache("u")["cookies"][auth.ACCESS_COOKIE] == "NEW"
    assert profiles.get_refresh_cookie("u") == "RNEW"


def test_refresh_failure_falls_back_to_full_login(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": _COOKIES, "expires_at": time.time() - 10})
    sess = FakeSession(queue=[
        FakeResp(400, {"error": "invalid_grant"}),                        # refresh
        FakeResp(200, {"message": "ok"}, cookies={auth.ACCESS_COOKIE: "LOGGEDIN"}),
    ])
    h = auth.auth_headers("u", profiles.get_profile("u"), sess)
    assert "LOGGEDIN" in h["Cookie"]
    assert sess.calls[0]["url"].endswith(auth.REFRESH_PATH)
    assert sess.calls[1]["url"].endswith(auth.LOGIN_PATH)


def test_no_refresh_cookie_goes_straight_to_login(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": {auth.ACCESS_COOKIE: "OLD"},
                                   "expires_at": time.time() - 10})
    sess = FakeSession(queue=[FakeResp(200, {"message": "ok"},
                                       cookies={auth.ACCESS_COOKIE: "NEW"})])
    h = auth.auth_headers("u", profiles.get_profile("u"), sess)
    assert "NEW" in h["Cookie"]
    assert len(sess.calls) == 1 and sess.calls[0]["url"].endswith(auth.LOGIN_PATH)


def test_dead_refresh_token_is_not_spent_on_a_round_trip(store):
    """A refresh JWT that is already past its own exp buys nothing."""
    dead = auth._usable_refresh_token(
        "u", {"cookies": {auth.REFRESH_COOKIE: _jwt_with_exp(time.time() - 500)}})
    assert dead is None
    live = auth._usable_refresh_token(
        "u", {"cookies": {auth.REFRESH_COOKIE: _jwt_with_exp(time.time() + 5000)}})
    assert live is not None


def test_refresh_cookie_persists_in_its_own_entry(store):
    """Credential Manager caps a blob at ~1280 CHARS (2560 bytes UTF-16LE), so the
    two ~1700-char JWTs cannot share one entry - the refresh cookie gets its own."""
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    auth._persist_cookies("u", {"cookies": _COOKIES, "expires_at": 123.0})
    assert profiles.get_token_cache("u")["cookies"] == {auth.ACCESS_COOKIE: "AAA"}
    assert profiles.get_refresh_cookie("u") == "RRR"
    # and it is reachable when only the persistent store has it
    auth._MEM_COOKIES.clear()
    assert auth._usable_refresh_token("u") == "RRR"


def test_clearing_a_session_drops_the_refresh_cookie_too(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    auth._persist_cookies("u", {"cookies": _COOKIES, "expires_at": 123.0})
    auth.clear_cookies("u")
    assert profiles.get_refresh_cookie("u") is None


def test_reauthenticate_prefers_refresh(store):
    profiles.save_profile("u", {"type": "userpass", "username": "u", "password": "p"})
    profiles.set_token_cache("u", {"cookies": _COOKIES, "expires_at": time.time() + 9999})
    sess = FakeSession(queue=[_refresh_resp(access="REAUTH")])
    cookies = auth.reauthenticate("u", profiles.get_profile("u"), sess)
    assert cookies[auth.ACCESS_COOKIE] == "REAUTH"
    assert sess.calls[0]["url"].endswith(auth.REFRESH_PATH)


def _jwt_with_exp(exp: float) -> str:
    import base64, json as _json
    def seg(d):
        return base64.urlsafe_b64encode(_json.dumps(d).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'HS256'})}.{seg({'exp': int(exp)})}.sig"
