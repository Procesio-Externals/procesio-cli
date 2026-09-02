"""Auth lifecycle actions: login, check-auth, logout.

These are client-backed (they need a profile + session) but deliberately never
return a token value - only whether authentication works and how it was done.
"""
from __future__ import annotations

from tools.procesio import auth, config, profiles
from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError
from tools.procesio.handlers.common import add_profile_arg

# A cheap, side-effect-free GET used to confirm a credential actually works.
# /api/Workspaces lists the caller's workspaces; it requires only valid auth.
_PROBE_PATH = "/api/Workspaces"


def login(client, _args) -> dict:
    """Force-acquire (userpass) or confirm (apikey) authentication."""
    kind = client.profile.get("type")
    if kind == "userpass":
        session = auth.force_login(client.name, client.profile, client._session)
        cookies = session.get("cookies", {})
        return {
            "authenticated": True,
            "mode": "userpass",
            "profile": client.name,
            "environment": client.env.get("name"),
            "session_cached": True,
            "cookie_names": sorted(cookies.keys()),   # names only, never values
            "expires_at": session.get("expires_at"),
            "web_base": config.web_base(client.profile),
            "login_path": auth.LOGIN_PATH,
        }
    # apikey: nothing to fetch - just confirm the headers are well-formed.
    headers = auth.auth_headers(client.name, client.profile, client._session)
    return {
        "authenticated": True,
        "mode": "apikey",
        "profile": client.name,
        "environment": client.env.get("name"),
        "sends_workspaceid": "workspaceid" in headers,
        "web_base": config.web_base(client.profile),
        "note": ("apikey auth is validated per-request; run check-auth to hit a "
                 "live endpoint"),
    }


def check_auth(client, _args) -> dict:
    """Hit a live read endpoint to confirm the credential is accepted."""
    try:
        body = client.get(_PROBE_PATH)
    except ProcesioAPIError as e:
        return {
            "authenticated": False,
            "profile": client.name,
            "environment": client.env.get("name"),
            "mode": client.profile.get("type"),
            "probe": _PROBE_PATH,
            "status": e.status,
            "detail": e.details,
            "web_base": config.web_base(client.profile),
            "auth_base": config.auth_base(client.profile),
        }
    n = len(body) if isinstance(body, list) else None
    return {
        "authenticated": True,
        "profile": client.name,
        "environment": client.env.get("name"),
        "web_base": config.web_base(client.profile),
        "mode": client.profile.get("type"),
        "probe": _PROBE_PATH,
        "workspaces_visible": n,
    }


def logout(client, _args) -> dict:
    """Clear the cached session (in-process + persistent), best-effort server logOut."""
    name = client.name
    had = (name in auth._MEM_COOKIES) or (profiles.get_token_cache(name) is not None)
    if client.profile.get("type") == "userpass" and had:
        try:
            client.post("/api/Authentication/logOut")
        except ProcesioAPIError:
            pass
    auth.clear_cookies(name)
    return {"profile": name, "cleared_cached_token": had}


ACTIONS = {
    "login": ActionDef(
        func=login, add_args=add_profile_arg, needs_client=True,
        description="Acquire (userpass) or confirm (apikey) authentication; caches the token.",
    ),
    "check-auth": ActionDef(
        func=check_auth, add_args=add_profile_arg, needs_client=True,
        description="Hit a live read endpoint to verify the profile authenticates.",
    ),
    "logout": ActionDef(
        func=logout, add_args=add_profile_arg, needs_client=True,
        description="Clear the cached Bearer token for a userpass profile.",
    ),
}
