"""Single resolver for WHERE user-specific data lives.

North star: the framework (tools/, agents/, skills/, scripts/) carries ZERO
user-specific data. Everything user-specific - config, runtime state, knowledge,
resources, preferences, decisions, run history, saved sessions - lives under one
folder, ``context-state-knowledge/`` at the repo root. That folder is never
git-versioned (see .gitignore) and is safe to wipe: delete it and the framework
runs clean for a brand-new user.

This module is the ONE place that knows that path, so tools AND agents resolve
user-data locations the same way and a future move needs a single change here.
Agents already import ``tools._lib`` (creds, io), so this lives here rather than
in ``agents/_lib`` to be importable by both without a cross-package dependency.

Relocatable: set ``AAT_USERDATA_DIR`` to move the whole user-data root to another
path or laptop with no code change (serves the LLM-agnostic / portable direction).

Layout under the base:

    context-state-knowledge/
      store.db            # SQLite (context-store tool)
      state/<component>/  # per-agent/tool runtime state
      config/<component>/ # per-agent/tool user config
      prompts/<component>/# per-user prompt copies (base+personal, agents/_lib/prompts.py)
      sessions/           # relocated web login profiles
      exports/            # human-readable dumps

Pure path resolution + ensure-exists. Seeding docs/DB schema is the job of the
context-store tool and the curator/orchestrator agents, not this module.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# tools/_lib/userdata.py -> parents[2] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_VAR = "AAT_USERDATA_DIR"
_USER_ENV = "AAT_USER_ID"
_WORKSPACE_ENV = "AAT_WORKSPACE_ID"
_DEFAULT_DIRNAME = "context-state-knowledge"

_SAFE = re.compile(r"[^0-9A-Za-z._-]+")


def _safe_component(name: str) -> str:
    """Sanitize a component name into a single safe path segment.

    Prevents path traversal (no separators, no ``..``) so a caller-supplied
    agent/tool name can never escape the user-data root.
    """
    if not name or not str(name).strip():
        raise ValueError("component name must be a non-empty string")
    seg = _SAFE.sub("-", str(name).strip()).strip("-._")
    if not seg or seg in (".", ".."):
        raise ValueError(f"invalid component name: {name!r}")
    return seg


def _root() -> Path:
    override = os.environ.get(_ENV_VAR)
    return Path(override).expanduser() if override else _REPO_ROOT / _DEFAULT_DIRNAME


def current_user() -> str | None:
    """The active user id (``AAT_USER_ID``), sanitized to a single safe path segment,
    or None in single-user mode. The multi-user web platform sets this per request
    (server-established from the authenticated session, never from model output)."""
    uid = os.environ.get(_USER_ENV)
    return _safe_component(uid) if uid and str(uid).strip() else None


def current_workspace() -> str | None:
    """The active workspace id (``AAT_WORKSPACE_ID``), sanitized to a single safe path
    segment, or None. The multi-tenant PROCESIO module sets this per request alongside
    ``AAT_USER_ID`` (server-established from the authenticated session, never from model
    output). Unset = no workspace dimension, exactly the historical single-workspace
    behaviour, so local Claude Code is unaffected. Personal-workspace semantics
    (PROCESIO ``Guid.Empty``) are the caller's concern - this resolver only sees an id."""
    ws = os.environ.get(_WORKSPACE_ENV)
    return _safe_component(ws) if ws and str(ws).strip() else None


def base() -> Path:
    """The user-data root. Honors ``AAT_USERDATA_DIR`` (the root) and ``AAT_USER_ID``
    (a per-user subdir under it, for the multi-user web platform). Defaults to the
    repo's ``context-state-knowledge/``. **Unset AAT_USER_ID = single-user, exactly as
    before** - so local Claude Code is unaffected. Every other resolver here derives
    from ``base()``, so per-user isolation is automatic (store.db, state, config,
    prompts, sessions, schedule, exports all move under the user's subdir). Created on
    first access.

    **Workspace dimension (``AAT_WORKSPACE_ID``):** when set, a ``ws/<ws>`` segment is
    inserted BEFORE the user segment, so the data root is ``<root>/ws/<ws>/<user>`` -
    isolating per ``(workspace, user)`` for the multi-tenant PROCESIO module. **Unset =
    exactly today's paths** (``<root>`` or ``<root>/<user>``), so nothing local moves."""
    root = _root()
    ws = current_workspace()
    if ws:
        root = root / "ws" / ws
    uid = current_user()
    if uid:
        root = root / uid
    root.mkdir(parents=True, exist_ok=True)
    return root


def store_db_path() -> Path:
    """Path to the SQLite store file (parent ensured, file not created here)."""
    base()  # ensure root exists
    return base() / "store.db"


def state_dir(component: str) -> Path:
    """Per-component runtime state dir, e.g. state_dir('email-classifier')."""
    p = base() / "state" / _safe_component(component)
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir(component: str) -> Path:
    """Per-component user config dir, e.g. config_dir('mysql')."""
    p = base() / "config" / _safe_component(component)
    p.mkdir(parents=True, exist_ok=True)
    return p


def prompts_dir(component: str, *, create: bool = True) -> Path:
    """Per-agent personal prompt copies live here (base+personal versioning;
    agents/_lib/prompts.py). Wipe = agents fall back to their framework base
    prompts. ``create=False`` for read paths so resolving a prompt never leaves
    an empty dir behind."""
    p = base() / "prompts" / _safe_component(component)
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def sessions_dir() -> Path:
    """Relocated web login profiles / broker state live here."""
    p = base() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> Path:
    """Human-readable dumps written by the curator live here."""
    p = base() / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def schedule_dir() -> Path:
    """The user's recurring-work schedule (schedule/*.yaml declarative entries +
    machine-owned state.json/log.jsonl). Read and executed by the orchestrator's
    schedule-tick; user data like everything else here - wipe = no scheduled work."""
    p = base() / "schedule"
    p.mkdir(parents=True, exist_ok=True)
    return p


def describe() -> dict:
    """Small status view for orchestrator/curator health reporting."""
    b = base()
    return {
        "base": str(b),
        "overridden": bool(os.environ.get(_ENV_VAR)),
        "env_var": _ENV_VAR,
        "user": current_user(),
        "multi_user": current_user() is not None,
        "workspace": current_workspace(),
        "multi_tenant": current_workspace() is not None,
        "store_db": str(b / "store.db"),
        "store_db_exists": (b / "store.db").exists(),
    }


def scan() -> dict:
    """File counts across the user-data areas. This is how agents detect a fresh
    start: a wiped folder never breaks the framework - it just scans as empty and
    the orchestrator/curator prompt the user to start building (templates live
    beside each component as <name>.template.json; `orchestrator bootstrap` seeds)."""
    b = base()

    def count(p: Path) -> int:
        return sum(1 for x in p.rglob("*") if x.is_file()) if p.exists() else 0

    return {
        "store_db_exists": (b / "store.db").exists(),
        "config_files": count(b / "config"),
        "state_files": count(b / "state"),
        "session_files": count(b / "sessions"),
        "export_files": count(b / "exports"),
        "readme_exists": (b / "README.md").exists(),
    }
