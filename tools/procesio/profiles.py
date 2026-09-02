"""Multi-credential profile store for PROCESIO.

The user explicitly wants "a system that allows multiple credentials so that I
can have multiple accounts, multiple api keys, etc." A *profile* is one named
credential: either an API key (workspace-scoped) or a username/password account
(full UI access). All profiles live in the OS credential store via
tools._lib.creds - NEVER on disk.

Credential-store layout (all under target agents-and-tools:procesio:<secret>):
  credentials        -> JSON index: [{"name","type","workspace"}, ...]   (NO secrets)
  default-profile    -> the name used when --profile is omitted
  cred-<name>        -> JSON blob for one profile (CONTAINS secret values)
  token-<name>       -> JSON cached Bearer token for a userpass profile

A profile blob:
  apikey:   {"type":"apikey","key":..,"value":..,"workspace_id":<guid?>,
             "workspace":<label?>,"web_base":<override?>,"auth_base":<override?>}
  userpass: {"type":"userpass","username":..,"password":..,"realm":<override?>,
             "client_id":<override?>,"web_base":<override?>,"auth_base":<override?>}

The index lets `list-credentials` enumerate profiles WITHOUT reading any secret
(keyring can't list keys, so the index is the source of truth for membership).
"""
from __future__ import annotations

import json

from tools._lib import creds
from tools.procesio.errors import AuthError, UsageError

TOOL = "procesio"
INDEX_SECRET = "credentials"
DEFAULT_SECRET = "default-profile"

# Fields that must never appear in a non-secret view (list-credentials, logs).
_SECRET_FIELDS = {"key", "value", "password"}


# -- index ------------------------------------------------------------------

def _load_index() -> list[dict]:
    raw = creds.get_optional(TOOL, INDEX_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_index(index: list[dict]) -> None:
    creds.set_secret(TOOL, INDEX_SECRET, json.dumps(index, ensure_ascii=False))


def _index_meta(blob: dict, name: str) -> dict:
    meta = {"name": name, "type": blob.get("type")}
    if blob.get("workspace"):
        meta["workspace"] = blob["workspace"]
    return meta


# -- profile CRUD -----------------------------------------------------------

def profile_names() -> list[str]:
    return [e["name"] for e in _load_index() if e.get("name")]


def get_profile(name: str) -> dict:
    raw = creds.get_optional(TOOL, f"cred-{name}")
    if not raw:
        raise AuthError(
            f"no PROCESIO credential profile named '{name}'. "
            f"Known: {', '.join(profile_names()) or '(none)'}. "
            f"Add one with: run-tool procesio add-credential ..."
        )
    try:
        blob = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AuthError(f"profile '{name}' is corrupted: {e}") from e
    if not isinstance(blob, dict) or "type" not in blob:
        raise AuthError(f"profile '{name}' is malformed (no type)")
    return blob


def save_profile(name: str, blob: dict) -> None:
    if blob.get("type") not in ("apikey", "userpass"):
        raise UsageError("profile type must be 'apikey' or 'userpass'")
    creds.set_secret(TOOL, f"cred-{name}", json.dumps(blob, ensure_ascii=False))
    index = [e for e in _load_index() if e.get("name") != name]
    index.append(_index_meta(blob, name))
    index.sort(key=lambda e: e["name"])
    _save_index(index)
    if not get_default():
        set_default(name)


def remove_profile(name: str) -> None:
    if name not in profile_names():
        raise UsageError(f"no profile named '{name}'")
    creds.delete(TOOL, f"cred-{name}")
    creds.delete(TOOL, f"token-{name}")
    creds.delete(TOOL, f"refresh-{name}")
    _save_index([e for e in _load_index() if e.get("name") != name])
    if get_default() == name:
        remaining = profile_names()
        if remaining:
            set_default(remaining[0])
        else:
            creds.delete(TOOL, DEFAULT_SECRET)


def public_view(blob: dict, name: str) -> dict:
    """A profile dict safe to return/log: secret fields removed, presence noted."""
    out = {"name": name}
    for k, v in blob.items():
        if k in _SECRET_FIELDS:
            out[f"has_{k}"] = bool(v)
        else:
            out[k] = v
    out["has_cached_token"] = creds.has_for_report(TOOL, f"token-{name}")
    return out


# -- default ----------------------------------------------------------------

def get_default() -> str | None:
    return creds.get_optional(TOOL, DEFAULT_SECRET)


def set_default(name: str) -> None:
    if name not in profile_names():
        raise UsageError(f"cannot default to unknown profile '{name}'")
    creds.set_secret(TOOL, DEFAULT_SECRET, name)


def resolve(name: str | None) -> tuple[str, dict]:
    """Return (name, blob) for an explicit name, else the default, else - if
    exactly one profile exists - that one. Raises a clear UsageError otherwise."""
    if name:
        return name, get_profile(name)
    default = get_default()
    if default:
        return default, get_profile(default)
    names = profile_names()
    if len(names) == 1:
        return names[0], get_profile(names[0])
    raise UsageError(
        "no --profile given and no default set. "
        f"Profiles: {', '.join(names) or '(none)'}. "
        "Set one with: run-tool procesio set-default --name <name>"
    )


# -- token cache (userpass) -------------------------------------------------

def get_token_cache(name: str) -> dict | None:
    raw = creds.get_optional(TOOL, f"token-{name}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def set_token_cache(name: str, token: dict) -> None:
    creds.set_secret(TOOL, f"token-{name}", json.dumps(token, ensure_ascii=False))


def clear_token_cache(name: str) -> None:
    creds.delete(TOOL, f"token-{name}")
    clear_refresh_cookie(name)


# The refresh cookie lives in its OWN entry, not alongside the access cookie.
# Windows Credential Manager caps a blob at 2560 BYTES (the tightest of the OS
# stores, so it sets the budget everywhere), and keyring stores the
# value as UTF-16LE — so the real ceiling is ~1280 CHARACTERS (measured on this
# machine). The two JWT cookies total ~1700 chars and blow past it together;
# each one alone (~961 and ~733) fits comfortably. Splitting them is what lets a
# session be renewed without re-sending the password.

def get_refresh_cookie(name: str) -> str | None:
    return creds.get_optional(TOOL, f"refresh-{name}") or None


def set_refresh_cookie(name: str, value: str) -> None:
    creds.set_secret(TOOL, f"refresh-{name}", value)


def clear_refresh_cookie(name: str) -> None:
    creds.delete(TOOL, f"refresh-{name}")
