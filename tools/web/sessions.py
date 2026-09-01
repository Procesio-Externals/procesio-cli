"""Saved-session storage for the web tool.

A *session* is a Playwright ``storageState`` JSON file (cookies + localStorage)
captured after a human logged in once. It lets later headless runs reuse that
authentication. These files contain live auth material and are therefore
**sensitive**:

  * They live under ``context-state-knowledge/sessions/<name>.json`` - the
    central, git-ignored user-data folder (framework/user-data separation;
    moved from tools/web/sessions/ on 2026-07-05).
  * That folder is never committed (see the repo .gitignore).
  * They are never printed or logged. ``list-sessions`` reports names and
    metadata (size, mtime) only - never file contents.

Session names are validated to a safe charset so a name can never escape the
sessions directory (no path traversal, no separators).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from tools.web.errors import SessionError, UsageError
from tools._lib import userdata

# Saved sessions are USER data (live auth for the user's accounts), so they live
# in the central user-data folder - context-state-knowledge/sessions/ - not in
# the tool dir (framework/user-data separation; migrated 2026-07-05, see
# tools/web/sessions/README.md breadcrumb). Resolved via tools/_lib/userdata.py,
# relocatable with AAT_USERDATA_DIR.
SESSIONS_DIR = userdata.sessions_dir()

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_name(name: str) -> str:
    """Return the name if it is a safe session identifier, else raise UsageError.

    Allowed: letters, digits, dot, dash, underscore; must start alphanumeric;
    1-64 chars. This blocks path traversal ('..', '/', '\\') by construction.
    """
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise UsageError(
            f"invalid session name {name!r}: use 1-64 chars of "
            "letters/digits/._- starting with a letter or digit"
        )
    return name


def sessions_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def session_path(name: str) -> Path:
    """Absolute path to a session file. Validates the name first."""
    validate_name(name)
    return sessions_dir() / f"{name}.json"


def exists(name: str) -> bool:
    return session_path(name).exists()


# --- persistent browser profiles ------------------------------------------
# Some sites (notably WhatsApp Web) keep their auth in IndexedDB, which a
# storageState snapshot cannot reliably restore — WhatsApp rejects a
# deserialized copy with "a database error occurred". For those, the web tool
# uses a PERSISTENT browser profile (a Chromium user-data-dir): the native
# on-disk profile is reused as-is, so the login survives across runs.

def profile_dir(name: str) -> Path:
    """Absolute path to a session's persistent browser-profile directory."""
    validate_name(name)
    return sessions_dir() / f"{name}.profile"


def profile_exists(name: str) -> bool:
    """True if a non-empty persistent profile directory exists for the name."""
    d = profile_dir(name)
    return d.is_dir() and any(d.iterdir())


def require_profile(name: str) -> Path:
    """Return an existing persistent profile dir or raise SessionError."""
    if not profile_exists(name):
        raise SessionError(
            f"no persistent profile for {name!r}. Capture one with: "
            f"python scripts/run-tool.py web save-session --name {name} "
            f"--url <login-url> --persistent"
        )
    return profile_dir(name)


def require(name: str) -> Path:
    """Return the path to an existing session or raise SessionError."""
    p = session_path(name)
    if not p.exists():
        raise SessionError(
            f"no saved session named {name!r}. Capture one with: "
            f"python scripts/run-tool.py web save-session --name {name} --url <login-url>"
        )
    return p


def load_state(name: str) -> dict:
    """Read and parse a session's storageState JSON. Raises SessionError on
    a missing or corrupt file. The returned dict is the Playwright storage_state."""
    p = require(name)
    try:
        # utf-8-sig tolerates a stray BOM if a session file was hand-edited.
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise SessionError(f"session {name!r} is unreadable/corrupt: {exc}") from exc


def write_state(name: str, state: dict) -> Path:
    """Persist a storageState dict to the session file. Returns the path."""
    p = session_path(name)
    p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return p


def artifacts(name: str) -> list[tuple[str, Path]]:
    """Every on-disk artifact belonging to a session, as (kind, path).

    A session is up to THREE files, not one: the storageState snapshot, the
    persistent browser profile, and the cookie sidecar. Anything that forgets
    the last two leaves a stale login behind - ``open_session`` auto-detects
    ``<name>.profile`` and will silently reuse it.
    """
    validate_name(name)
    return [
        ("state", session_path(name)),
        ("profile", profile_dir(name)),
        ("cookies", cookies_path(name)),
    ]


def present_artifacts(name: str) -> list[str]:
    """Kinds that actually exist on disk for ``name``."""
    out = []
    for kind, path in artifacts(name):
        if (profile_exists(name) if kind == "profile" else path.exists()):
            out.append(kind)
    return out


def delete(name: str, *, confirm: bool = False) -> dict:
    """Delete ALL of a session's artifacts (state + profile + cookie sidecar).

    Deleting a session destroys a real login that only a human at a browser can
    re-establish, so this REFUSES to act unless ``confirm=True``. Without it the
    call is a non-destructive preview reporting ``would_remove`` - which also
    serves as the dry run. Returns a report; never raises for a missing session.
    """
    validate_name(name)
    present = present_artifacts(name)
    if not present:
        return {"session": name, "deleted": False, "existed": False, "removed": []}
    if not confirm:
        return {"session": name, "deleted": False, "existed": True, "removed": [],
                "would_remove": present, "confirmation_required": True}

    removed: list[str] = []
    failed: dict[str, str] = {}
    for kind, path in artifacts(name):
        if kind not in present:
            continue
        try:
            if kind == "profile":
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(kind)
        except OSError as exc:   # e.g. Windows lock: a browser still has the profile
            failed[kind] = str(exc)

    out = {"session": name, "existed": True, "removed": removed,
           "deleted": bool(removed) and not failed}
    if failed:
        out["failed"] = failed
        out["note"] = ("some artifacts could not be removed - a browser or "
                       "serializing broker may still hold the profile; close it "
                       "and retry")
    return out


# --- cookie sidecar (for persistent profiles) ------------------------------
# A persistent Chromium profile persists localStorage + IndexedDB to disk, but
# Chromium NEVER writes *session-scoped* cookies (no Expires/Max-Age) to the
# profile — they live in memory and vanish when the browser closes. Apps that
# authenticate with a session cookie (e.g. Ryver) therefore appear logged-out on
# every reopen of an otherwise-valid profile. The fix: at save time, while the
# browser is still alive, snapshot ALL cookies (session ones included) to this
# sidecar; at open time, re-inject them into the fresh context before navigating.
# The file holds live auth material — same sensitivity/gitignore as the profile.

def cookies_path(name: str) -> Path:
    """Absolute path to a persistent session's cookie sidecar JSON."""
    validate_name(name)
    return sessions_dir() / f"{name}.cookies.json"


def cookies_exist(name: str) -> bool:
    return cookies_path(name).exists()


def write_cookies(name: str, cookies: list[dict]) -> Path:
    """Persist a list of Playwright cookie dicts. Returns the path."""
    p = cookies_path(name)
    p.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    return p


def load_cookies(name: str) -> list[dict]:
    """Read a session's cookie sidecar. Returns [] if absent or unreadable
    (best-effort: a corrupt sidecar must not block opening the profile)."""
    p = cookies_path(name)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _meta(p: Path, *, persistent: bool = False) -> dict:
    st = p.stat()
    return {
        "name": p.stem,
        "bytes": st.st_size,
        "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
        "persistent": persistent,
    }


def list_all() -> list[dict]:
    """List saved sessions (metadata only, never contents). Sorted by name.

    Includes BOTH storageState sessions (``<name>.json``) and persistent browser
    profiles (``<name>.profile/``); the ``persistent`` flag tells them apart.
    Without the profiles, a session saved via ``--persistent`` would be invisible
    here even though it exists and is usable.
    """
    d = sessions_dir()
    items = [_meta(p) for p in d.glob("*.json")]
    items += [_meta(p, persistent=True) for p in d.glob("*.profile") if p.is_dir()]
    return sorted(items, key=lambda i: i["name"])
