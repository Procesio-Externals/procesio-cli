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


# What each flag of GET /api/Features switches off when it is false. An installation (an
# on-prem or client environment) may turn optional modules off; the API then answers their
# endpoints with 400 code 1013 FEATURE_DISABLED and refuses to save a process that uses a
# Data Store / Query Store (dataStore) or Form Trigger (forms) action.
FEATURE_SCOPE = {
    "customActions": "custom actions: upload, Action Designer, custom-action toolbox "
                     "(on when the installation has a NuGet store configured)",
    "dataStore": "Data Stores: store/row/CSV endpoints, Data Store and Query Store actions, "
                 "data stores in forms and in import/export",
    "forms": "Forms: form templates, submissions, chains, assignments, signing, custom URLs "
             "to forms, the Form Trigger action, forms in import/export",
    "executionEnvironment": "Execution Environment (Thread) licensing: its analytics, "
                            "Thread plans, changing a workspace's maxThreads",
}


def features(client, _args) -> dict:
    """Which optional modules this PROCESIO environment has switched on."""
    flags = client.get("/api/Features")
    flags = flags if isinstance(flags, dict) else {}
    off = sorted(k for k, v in flags.items() if v is False)
    return {
        "environment": client.env.get("name"),
        "features": flags,
        "disabled": off,
        "disabled_scope": {k: FEATURE_SCOPE.get(k, "") for k in off},
        "all_enabled": bool(flags) and not off,
    }


def server_build(client, _args) -> dict:
    """Which Web-Api build this environment runs, from its anonymous health check.

    Since Web-Api v2.80.0 `GET /health` reports `entries.self.data = {version, commit}`. The
    commit is the reliable part: it is the tag's commit in the Web-Api repository, so it says
    which release is live without waiting for an announcement. `version` is the assembly
    version and does not follow the release tags."""
    import json as _json

    status, raw, _ = client.request_bytes("GET", "/health")
    try:
        body = _json.loads((raw or b"").decode("utf-8", "replace") or "null")
    except ValueError:
        body = None
    entries = body.get("entries") if isinstance(body, dict) else None
    me = (entries or {}).get("self") if isinstance(entries, dict) else None
    data = (me or {}).get("data") if isinstance(me, dict) else None
    data = data if isinstance(data, dict) else {}
    out = {"environment": client.env.get("name"), "web_base": config.web_base(client.profile),
           "http_status": status,
           "health": body.get("status") if isinstance(body, dict) else None,
           "web_api": {"version": data.get("version"), "commit": data.get("commit")}}
    if not data.get("commit"):
        out["note"] = ("this environment's /health reports no build (a Web-Api older than "
                       "v2.80.0, or a gateway that does not route /health)")
    return out


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
    "features": ActionDef(
        func=features, add_args=add_profile_arg, needs_client=True,
        description=("Which optional modules this environment has on (GET /api/Features): "
                     "customActions, dataStore, forms, executionEnvironment. An installation "
                     "can switch them off; their endpoints then answer 400 code 1013 "
                     "(error code feature_disabled)."),
    ),
    "server-build": ActionDef(
        func=server_build, add_args=add_profile_arg, needs_client=True,
        description=("Which Web-Api build this environment runs (GET /health, anonymous): the "
                     "version and the commit, which is the release tag's commit in the Web-Api "
                     "repository. Read-only."),
    ),
    "logout": ActionDef(
        func=logout, add_args=add_profile_arg, needs_client=True,
        description="Clear the cached Bearer token for a userpass profile.",
    ),
}
