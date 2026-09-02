"""PROCESIO environments - named URL sets an installation is reached through.

A PROCESIO *environment* is one installation of the platform: a `<Client>-<ENV>`
label (e.g. `Internal-PROD`, `Internal-QA`, `Delgaz-DEVQA`) that carries the four
host URLs that installation lives on:

    web_base   the Web API host (every REST call)                webapi-*.procesio.app
    app_base   the designer / front-end host (designer URLs, CORS Origin)   *.procesio.app
    forms_base the public forms host (rendered-form URLs)        forms-*.procesio.app
    auth_base  the legacy Proxy/Authentication host (rarely used - login goes to web_base)

Environments are NON-secret (they are just hostnames). Credentials are stored
separately (Credential Manager, see profiles.py) and each credential is *bound*
to one environment by name - so switching environment also switches which
account/key is used. A credential with no binding belongs to the DEFAULT
environment, which itself defaults to `Internal-PROD`. That is what keeps every
pre-existing single-credential setup working unchanged as production: no env
config on disk + an unbound credential == Internal-PROD == the historical
hard-coded URLs, with nothing to re-enter.

Two layers, merged at read time:
  * BUILT-IN presets in code (Internal-PROD/QA/DEV) - PROCESIO's own infra, shared
    with every teammate, available with zero setup.
  * a USER registry at ``config/procesio/environments.json`` (per-user, wipeable)
    holding client-specific environments (Delgaz-*, ...) and the default pointer.
    A user entry with the same name OVERRIDES a built-in (so a moved Internal host
    can be corrected without a code change).

Client environment URLs are customer-specific, so they are USER DATA and live in
the registry file - never baked into the shared framework code (only PROCESIO's
own Internal-* presets are).
"""
from __future__ import annotations

import json
import re

from tools._lib import userdata
from tools.procesio.errors import UsageError

COMPONENT = "procesio"
REGISTRY_FILE = "environments.json"

# The canonical fallback: an unbound credential and an unset default both resolve
# here, and its URLs equal the historical hard-coded production defaults.
DEFAULT_ENV_NAME = "Internal-PROD"

# The four hosts every environment defines. Keys are the field names injected into
# a profile so config.web_base/app_base/forms_base/auth_base pick them up.
URL_KEYS = ("web_base", "app_base", "forms_base", "auth_base")

# Built-in PROCESIO-internal environments (framework-shared, non-secret infra).
# Production keeps the bare hostnames; QA/DEV use the -qa/-dev host family. auth_base
# is only meaningful on PROD (the legacy Proxy host); QA/DEV omit it and fall back to
# the config default, since login goes to web_base anyway.
BUILTIN: dict[str, dict] = {
    "Internal-PROD": {
        "name": "Internal-PROD", "client": "Internal", "env": "PROD",
        "web_base": "https://webapi.procesio.app",
        "app_base": "https://procesio.app",
        "forms_base": "https://forms.procesio.app",
        "auth_base": "https://auth.procesio.app",
        "builtin": True,
    },
    "Internal-QA": {
        "name": "Internal-QA", "client": "Internal", "env": "QA",
        "web_base": "https://webapi-qa.procesio.app",
        "app_base": "https://qa.procesio.app",
        "forms_base": "https://forms-qa.procesio.app",
        "builtin": True,
    },
    "Internal-DEV": {
        "name": "Internal-DEV", "client": "Internal", "env": "DEV",
        "web_base": "https://webapi-dev.procesio.app",
        "app_base": "https://dev.procesio.app",
        "forms_base": "https://forms-dev.procesio.app",
        "builtin": True,
    },
}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# -- registry file ----------------------------------------------------------

def _registry_path():
    return userdata.config_dir(COMPONENT) / REGISTRY_FILE


def _load_registry() -> dict:
    p = _registry_path()
    if not p.exists():
        return {"environments": {}, "default": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"environments": {}, "default": None}
    if not isinstance(data, dict):
        return {"environments": {}, "default": None}
    envs = data.get("environments")
    data["environments"] = envs if isinstance(envs, dict) else {}
    if "default" not in data:
        data["default"] = None
    return data


def _save_registry(data: dict) -> None:
    p = _registry_path()
    # Direct bytes write with LF endings - never the (Cowork-mount-capped) Write tool.
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    p.write_bytes(payload.encode("utf-8"))


# -- read -------------------------------------------------------------------

def all_environments() -> dict[str, dict]:
    """Every known environment: built-ins overlaid by any user entry of the same
    name, plus purely user-defined ones. Values are copies safe to mutate."""
    merged: dict[str, dict] = {k: dict(v) for k, v in BUILTIN.items()}
    for name, env in _load_registry()["environments"].items():
        if not isinstance(env, dict):
            continue
        base = merged.get(name, {})
        base.update(env)
        base["name"] = name
        base["builtin"] = name in BUILTIN
        merged[name] = base
    return merged


def _find(name: str) -> tuple[str, dict] | None:
    """Case-insensitive lookup by canonical name. Returns (canonical_name, env)."""
    if not name:
        return None
    envs = all_environments()
    if name in envs:
        return name, envs[name]
    low = name.strip().lower()
    for canon, env in envs.items():
        if canon.lower() == low:
            return canon, env
    return None


def get(name: str) -> dict:
    hit = _find(name)
    if not hit:
        raise UsageError(
            f"no PROCESIO environment named '{name}'. "
            f"Known: {', '.join(sorted(all_environments())) or '(none)'}. "
            f"Add one with: run-tool procesio add-environment ..."
        )
    return hit[1]


def exists(name: str) -> bool:
    return _find(name) is not None


def canonical_name(name: str) -> str | None:
    hit = _find(name)
    return hit[0] if hit else None


# -- default pointer --------------------------------------------------------

def get_default() -> str:
    """The active environment name. The stored pointer if set and still valid,
    else DEFAULT_ENV_NAME (Internal-PROD) - so a fresh box is production."""
    stored = _load_registry().get("default")
    if stored and exists(stored):
        return canonical_name(stored)
    return DEFAULT_ENV_NAME


def set_default(name: str) -> str:
    canon = canonical_name(name)
    if not canon:
        raise UsageError(
            f"cannot switch to unknown environment '{name}'. "
            f"Known: {', '.join(sorted(all_environments()))}. "
            f"Add it first with: run-tool procesio add-environment ..."
        )
    data = _load_registry()
    data["default"] = canon
    _save_registry(data)
    return canon


# -- add / remove (user registry only) --------------------------------------

def _derive_client_env(name: str, client: str | None, env: str | None):
    """Fill client/env from the `<Client>-<ENV>` name when not given explicitly."""
    if client and env:
        return client, env
    if "-" in name:
        c, _, e = name.rpartition("-")
        return client or c, env or e
    return client or name, env or ""


def add(name: str, *, web_base: str, app_base: str, forms_base: str,
        auth_base: str | None = None, client: str | None = None,
        env: str | None = None, make_default: bool = False) -> dict:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise UsageError(
            "environment name must look like '<Client>-<ENV>' "
            "(letters/digits/.-_ , e.g. 'Delgaz-PROD')"
        )
    if not (web_base and app_base and forms_base):
        raise UsageError("add-environment needs --web-base, --app-base and --forms-base")
    client, env = _derive_client_env(name, client, env)
    entry = {
        "name": name, "client": client, "env": env,
        "web_base": web_base.rstrip("/"),
        "app_base": app_base.rstrip("/"),
        "forms_base": forms_base.rstrip("/"),
    }
    if auth_base:
        entry["auth_base"] = auth_base.rstrip("/")
    data = _load_registry()
    data["environments"][name] = entry
    if make_default:
        data["default"] = name
    _save_registry(data)
    out = dict(entry)
    out["builtin"] = name in BUILTIN
    return out


def remove(name: str) -> None:
    data = _load_registry()
    canon = None
    for existing in data["environments"]:
        if existing.lower() == name.strip().lower():
            canon = existing
            break
    if canon is None:
        if name in BUILTIN or canonical_name(name) in BUILTIN:
            raise UsageError(f"'{name}' is a built-in environment and cannot be removed")
        raise UsageError(f"no user-defined environment named '{name}'")
    del data["environments"][canon]
    if data.get("default") and data["default"].lower() == canon.lower():
        data["default"] = None
    _save_registry(data)


# -- resolution -------------------------------------------------------------

def resolve(name: str | None, profile: dict | None = None) -> dict:
    """The active environment for a call. Precedence, highest first:
      1. an explicit environment name (the --environment flag),
      2. the credential's own `environment` binding,
      3. the stored default environment,
      4. Internal-PROD.
    Always returns a full environment dict (never raises for the fallbacks;
    only an explicit unknown name raises)."""
    if name:
        return get(name)
    bound = (profile or {}).get("environment")
    if bound and exists(bound):
        return get(bound)
    return get(get_default())
