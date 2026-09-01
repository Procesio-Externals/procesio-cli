"""PROCESIO base URLs + auth constants.

PROCESIO splits into two services:
  * the **Web API** (process/instance/workspace/etc CRUD) - default
    https://webapi.procesio.app . This host is reachable with a valid
    DigiCert cert and serves the v1.19 Swagger.
  * the **Proxy API / Authentication Service** (username+password login,
    refreshToken, password change) - documented at https://auth.procesio.app .

Both hosts are CONFIGURABLE so the tool survives PROCESIO's infra moving
(e.g. auth.procesio.app currently fronts a Kong gateway whose default cert is
served for that SNI from some networks). Precedence, highest first:
  1. the profile's own "web_base" / "auth_base" field,
  2. the PROCESIO_WEB_BASE / PROCESIO_AUTH_BASE environment variables,
  3. the documented defaults below.

Login parameters (realm / client_id) come from PROCESIO's developer docs
(https://docs.procesio.com/developers-guide/procesio-api-documentation):
all users live in realm "procesio01"; the UI client_id is "procesio-ui";
client_secret is empty.
"""
from __future__ import annotations

import os

DEFAULT_WEB_BASE = "https://webapi.procesio.app"
DEFAULT_AUTH_BASE = "https://auth.procesio.app"
# The designer / front-end host (distinct from the Web API host): designer URLs and
# the CORS Origin/Referer sent on login. The forms host renders public forms.
DEFAULT_APP_BASE = "https://procesio.app"
DEFAULT_FORMS_BASE = "https://forms.procesio.app"
DEFAULT_REALM = "procesio01"
DEFAULT_CLIENT_ID = "procesio-ui"
# The gateway selects the API contract via the `x-version` request header. In
# production it is REQUIRED on the main-gateway routes (DataTypes/Projects/
# Actions/...): omitting it returns 401 (the documented
# AssumeDefaultVersionWhenUnspecified is NOT in effect in prod). Send it on
# every call. Overridable per-profile ("api_version") or via env.
DEFAULT_API_VERSION = "1.19"


def web_base(profile: dict | None = None) -> str:
    profile = profile or {}
    return (
        profile.get("web_base")
        or os.environ.get("PROCESIO_WEB_BASE")
        or DEFAULT_WEB_BASE
    ).rstrip("/")


def auth_base(profile: dict | None = None) -> str:
    profile = profile or {}
    return (
        profile.get("auth_base")
        or os.environ.get("PROCESIO_AUTH_BASE")
        or DEFAULT_AUTH_BASE
    ).rstrip("/")


def app_base(profile: dict | None = None) -> str:
    """The designer / front-end host. Sourced (like web_base) from the active
    environment via the profile the client injects it into; overridable per-profile
    or via PROCESIO_APP_BASE, else the production default."""
    profile = profile or {}
    return (
        profile.get("app_base")
        or os.environ.get("PROCESIO_APP_BASE")
        or DEFAULT_APP_BASE
    ).rstrip("/")


def forms_base(profile: dict | None = None) -> str:
    """The public forms host (rendered-form URLs). Same precedence as app_base."""
    profile = profile or {}
    return (
        profile.get("forms_base")
        or os.environ.get("PROCESIO_FORMS_BASE")
        or DEFAULT_FORMS_BASE
    ).rstrip("/")


def realm(profile: dict | None = None) -> str:
    return (profile or {}).get("realm") or DEFAULT_REALM


def client_id(profile: dict | None = None) -> str:
    return (profile or {}).get("client_id") or DEFAULT_CLIENT_ID


def api_version(profile: dict | None = None) -> str:
    profile = profile or {}
    return (
        profile.get("api_version")
        or os.environ.get("PROCESIO_API_VERSION")
        or DEFAULT_API_VERSION
    )
