"""PROCESIO authentication: API-key headers and username/password cookie session.

Two auth modes, both validated live (2026-06-23) against the production Web API.

  * **API key** (workspace-scoped): three request headers on every Web-API call -
    `key` (key name), `value` (key value) and `workspaceid` (workspace GUID).
    A master/personal key works without `workspaceid`; a scoped key requires it.

  * **username/password** (full account): a **cookie session**, NOT a Bearer JWT.
    Login is a form POST to `{web_base}/api/authentication`:

        POST https://webapi.procesio.app/api/authentication
        Content-Type: application/x-www-form-urlencoded
        x-requested-by: playground-v1
        body: username=<>&password=<>&client_id=procesio-ui

    The 200 response is just {"message":"Authentication successful"} and sets two
    HttpOnly cookies - `__Host-procesio.access` and `__Host-procesio.refresh` -
    with the session expiry in the `x-session-expires-at` response header. Every
    subsequent call carries those cookies plus the `x-requested-by` header. This
    is exactly what the procesio.app SPA does (captured from a real login HAR);
    the old auth.procesio.app / OAuth-grant flow in the docs is obsolete.

The HTTP `session` is always injected so tests never touch the network. It must
expose `.request(method, url, data=, json=, params=, headers=, timeout=) -> resp`
with `.status_code`, `.json()`, `.text`, `.headers`, and `.cookies`.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from tools._lib.io import log
from tools.procesio import config, profiles
from tools.procesio.errors import AuthError, ProcesioAPIError

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0 Safari/537.36"
)
LOGIN_PATH = "/api/authentication"        # lowercase, form-encoded
# Renew a session from the refresh cookie WITHOUT re-sending the password. Same
# form-encoded shape as login; the 200 sets a fresh cookie pair. Verified live:
# the refreshed access cookie authenticates an ordinary Web-API call.
REFRESH_PATH = "/api/Authentication/refreshToken"
DEFAULT_REQUESTED_BY = "playground-v1"    # the SPA's gateway identifier
ACCESS_COOKIE = "__Host-procesio.access"
REFRESH_COOKIE = "__Host-procesio.refresh"
_SKEW = 60   # treat a session as expired this many seconds early
# A token we just minted whose expiry we cannot read (not a JWT, no
# x-session-expires-at) is trusted for this long. A CACHED entry of unknown
# expiry is still distrusted — it could be arbitrarily old — but a token created
# one round-trip ago demonstrably is not, and re-logging in on the very next
# request instead is strictly worse. A rejected session still self-heals, because
# 401/403 triggers re-authentication anyway.
_ASSUMED_TTL = 300

# In-process cookie cache (name -> {"cookies": {...}, "expires_at": float|None}).
# Always works and avoids re-login within a single CLI invocation. The persistent
# cache is best-effort on top of this (see _persist_cookies).
_MEM_COOKIES: dict[str, dict] = {}


def requested_by(profile: dict) -> str:
    return (profile or {}).get("requested_by") or DEFAULT_REQUESTED_BY


def _gateway_headers(profile: dict) -> dict[str, str]:
    # Origin/Referer must match the environment's front-end host (CORS), which the
    # client folds into the profile as app_base; defaults to production.
    app = config.app_base(profile)
    return {
        "User-Agent": _BROWSER_UA,
        "Accept": "application/json",
        "x-requested-by": requested_by(profile),
        "Origin": app,
        "Referer": f"{app}/",
    }


def _parse_body(resp) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"raw_text": getattr(resp, "text", "")}


def _trim(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: v for k, v in body.items() if k != "raw_text"} or body
    return body


def _cookies_from(resp) -> dict[str, str]:
    """Extract Set-Cookie name->value from a response, tolerant of a real
    requests RequestsCookieJar or a plain dict (tests)."""
    jar = getattr(resp, "cookies", None)
    if not jar:
        return {}
    if isinstance(jar, dict):
        return dict(jar)
    try:
        return dict(jar.get_dict())
    except Exception:  # noqa: BLE001
        try:
            return {c.name: c.value for c in jar}
        except Exception:  # noqa: BLE001
            return {}


def _parse_expiry(header_val) -> float | None:
    """`x-session-expires-at` may be epoch seconds/millis or an ISO-8601 string.
    NOTE: this header carries the *refresh*-token expiry (~24h), NOT the access
    cookie's. Prefer `_jwt_exp` of the access cookie for accurate freshness."""
    if not header_val:
        return None
    s = str(header_val).strip()
    try:
        n = float(s)
        return n / 1000.0 if n > 1e12 else n
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _jwt_exp(token: str) -> float | None:
    """The `exp` claim (epoch seconds) of a JWT, or None. The access cookie is a
    Bearer JWT (~30 min TTL); its own `exp` is the only accurate freshness signal
    (the `x-session-expires-at` header reflects the longer-lived refresh token)."""
    try:
        import base64
        import json as _json
        parts = token.split(".")
        if len(parts) != 3:
            return None
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(pad))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except Exception:  # noqa: BLE001
        return None


def _minted_expiry(cookies: dict, headers) -> float:
    """Expiry to record for a session we just obtained. Prefer the access
    cookie's own `exp` (accurate, ~30 min), then the x-session-expires-at header,
    then a short assumed TTL — never None, so a just-minted token is usable."""
    return (_jwt_exp(cookies.get(ACCESS_COOKIE, ""))
            or _parse_expiry((headers or {}).get("x-session-expires-at"))
            or (time.time() + _ASSUMED_TTL))


def login(profile: dict, session) -> dict:
    """Perform the cookie-session login. Returns
    {"cookies": {name: value}, "expires_at": <epoch|None>}."""
    username = profile.get("username")
    password = profile.get("password")
    if not username or not password:
        raise AuthError("userpass profile is missing username/password")
    headers = _gateway_headers(profile)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    form = {"username": username, "password": password,
            "client_id": config.client_id(profile)}
    url = f"{config.web_base(profile)}{LOGIN_PATH}"
    resp = session.request("POST", url, data=form, headers=headers, timeout=30)
    status = getattr(resp, "status_code", 0)
    if not (200 <= status < 300):
        raise ProcesioAPIError(status or 0, "username/password login failed",
                               {"body": _trim(_parse_body(resp)), "url": url})
    cookies = _cookies_from(resp)
    if not cookies.get(ACCESS_COOKIE):
        raise AuthError(
            "login returned 2xx but no access cookie was set "
            f"(cookies seen: {sorted(cookies)})"
        )
    resp_headers = getattr(resp, "headers", {}) or {}
    return {"cookies": cookies,
            "expires_at": _minted_expiry(cookies, resp_headers)}


def refresh(profile: dict, session, refresh_token: str) -> dict:
    """Renew the session from the refresh cookie — no password involved. Returns
    the same shape as login(). Raises so the caller can fall back to a full login.

    This is what the SPA gets for free (the gateway refreshes its cookies behind
    a 307). A programmatic cookie client has to ask for it explicitly, which is
    why the REFRESH cookie must be cached alongside the access one."""
    headers = _gateway_headers(profile)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    form = {"refresh_token": refresh_token, "client_id": config.client_id(profile)}
    url = f"{config.web_base(profile)}{REFRESH_PATH}"
    resp = session.request("POST", url, data=form, headers=headers, timeout=30)
    status = getattr(resp, "status_code", 0)
    if not (200 <= status < 300):
        raise ProcesioAPIError(status or 0, "session refresh failed",
                               {"body": _trim(_parse_body(resp)), "url": url})
    cookies = _cookies_from(resp)
    if not cookies.get(ACCESS_COOKIE):
        raise AuthError("refresh returned 2xx but set no access cookie "
                        f"(cookies seen: {sorted(cookies)})")
    return {"cookies": cookies,
            "expires_at": _minted_expiry(cookies, getattr(resp, "headers", {}))}


def _usable_refresh_token(name: str, *entries) -> str | None:
    """The first REFRESH cookie still alive by its own `exp` — from the in-memory
    entries first, then the persistent `refresh-<name>` credential. A dead refresh
    token is worth nothing: fall straight through to a full login rather than
    spending a round-trip proving it."""
    now = time.time()
    candidates = [((entry or {}).get("cookies") or {}).get(REFRESH_COOKIE)
                  for entry in entries]
    try:
        candidates.append(profiles.get_refresh_cookie(name))
    except Exception:  # noqa: BLE001 - a vault read must never break a request
        pass
    for tok in candidates:
        if not tok:
            continue
        exp = _jwt_exp(tok)
        if exp is None or exp - now > _SKEW:
            return tok
    return None


def _is_fresh(entry: dict | None, now: float) -> bool:
    if not entry or not entry.get("cookies", {}).get(ACCESS_COOKIE):
        return False
    exp = entry.get("expires_at")
    # Unknown expiry -> do NOT trust it (re-login). The access cookie is a ~30 min
    # JWT; a cached entry without an expiry could be long dead. force_login always
    # records an accurate exp now, so this only bites legacy/None cache entries.
    if exp is None:
        return False
    return exp - now > _SKEW


def _persist_cookies(name: str, token: dict) -> None:
    """Best-effort persistent cache, in TWO Credential Manager entries.

    Both cookies must survive: the access cookie authenticates, and the REFRESH
    cookie is what lets the next process renew the session without re-sending the
    password (without it, every ~30 min of use costs a full login).

    They cannot share one entry. Credential Manager caps a blob at 2560 BYTES and
    keyring writes UTF-16LE, so the real ceiling is ~1280 CHARACTERS; the two JWTs
    total ~1700 and are rejected together with WinError 1783 "stub received bad
    data". Each alone fits, so they go to `token-<name>` and `refresh-<name>`.
    Never raises: on failure we keep the in-process cache and re-login next time.
    """
    cookies = token.get("cookies") or {}
    slim = {"cookies": {ACCESS_COOKIE: cookies.get(ACCESS_COOKIE)},
            "expires_at": token.get("expires_at")}
    try:
        profiles.set_token_cache(name, slim)
    except Exception as e:  # noqa: BLE001
        log(f"[procesio] session not persisted to Credential Manager ({e}); "
            f"using in-process cache (will re-login next invocation)")
    refresh_cookie = cookies.get(REFRESH_COOKIE)
    if not refresh_cookie:
        return
    try:
        profiles.set_refresh_cookie(name, refresh_cookie)
    except Exception as e:  # noqa: BLE001
        log(f"[procesio] refresh cookie not persisted ({e}); the next process "
            f"will re-login with the password instead of refreshing")


def force_login(name: str, profile: dict, session) -> dict:
    """Log in fresh and cache (memory + best-effort persistent). Returns the token."""
    fresh = login(profile, session)
    _MEM_COOKIES[name] = fresh
    _persist_cookies(name, fresh)
    return fresh


def clear_cookies(name: str) -> None:
    """Drop both the in-process and persistent session for a profile."""
    _MEM_COOKIES.pop(name, None)
    profiles.clear_token_cache(name)


def try_refresh(name: str, profile: dict, session, *entries) -> dict | None:
    """Renew from a cached refresh cookie, or None if that is not possible.
    Never raises — a failed refresh just means "do a full login"."""
    token = _usable_refresh_token(name, *entries)
    if not token:
        return None
    try:
        fresh = refresh(profile, session, token)
    except (AuthError, ProcesioAPIError) as e:
        log(f"[procesio] session refresh failed ({e}); doing a full login")
        return None
    _MEM_COOKIES[name] = fresh
    _persist_cookies(name, fresh)
    return fresh


def get_valid_cookies(name: str, profile: dict, session) -> dict[str, str]:
    """Return usable session cookies for a userpass profile. Order: in-process
    cache → persistent cache → REFRESH → fresh login.

    The refresh step matters: the access cookie is a ~30 min JWT, so without it
    every half hour of use re-sends the username and password to the login
    endpoint. Refreshing costs one round-trip and no credentials."""
    now = time.time()
    mem = _MEM_COOKIES.get(name)
    if _is_fresh(mem, now):
        return mem["cookies"]
    cache = profiles.get_token_cache(name)
    if _is_fresh(cache, now):
        _MEM_COOKIES[name] = cache
        return cache["cookies"]
    renewed = try_refresh(name, profile, session, mem, cache)
    if renewed is not None:
        return renewed["cookies"]
    return force_login(name, profile, session)["cookies"]


def reauthenticate(name: str, profile: dict, session) -> dict[str, str]:
    """Recovery path after the gateway rejects our session mid-call. Try a
    refresh first (cheap, no password); only if that fails drop the cached entry
    and log in fully. Order matters — clearing the cache first would throw away
    the very refresh cookie the refresh needs."""
    mem = _MEM_COOKIES.get(name)
    cache = profiles.get_token_cache(name)
    renewed = try_refresh(name, profile, session, mem, cache)
    if renewed is not None:
        return renewed["cookies"]
    clear_cookies(name)
    return force_login(name, profile, session)["cookies"]


def auth_headers(name: str, profile: dict, session) -> dict[str, str]:
    """Headers that authenticate a Web-API request for this profile."""
    kind = profile.get("type")
    if kind == "apikey":
        key, value = profile.get("key"), profile.get("value")
        if not key or not value:
            raise AuthError("apikey profile is missing key/value")
        headers = {"key": key, "value": value}
        wsid = profile.get("workspace_id")
        if wsid:
            headers["workspaceid"] = wsid
        return headers
    if kind == "userpass":
        cookies = get_valid_cookies(name, profile, session)
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {"Cookie": cookie_header, "x-requested-by": requested_by(profile)}
    raise AuthError(f"unknown profile type: {kind!r}")
