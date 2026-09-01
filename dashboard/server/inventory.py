"""The read model: assemble the full dashboard picture from the live registry.

Reads are in-process (import registry / userdata / bootstraplib) so the inventory
is fast and always reflects the real folder + Credential Manager state. The only
subprocess reads here are the store stats and llm providers (they belong to tools
that own their own config/DB).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

import registry
from agents.orchestrator import bootstraplib
from tools._lib import creds, userdata

# A full build scans every manifest (a few seconds on a large registry). Cache it
# briefly and serialize builds so a page reload, a validation reconnect, or two
# concurrent requests never stack N full scans. Mutations (credential/config
# writes) call invalidate() so the next read reflects the change immediately.
_INV_TTL = 4.0
_INV_LOCK = threading.Lock()
_INV_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}


def invalidate() -> None:
    with _INV_LOCK:
        _INV_CACHE["ts"] = 0.0
        _INV_CACHE["data"] = None


def _probe_kind(entry: dict[str, Any]) -> str | None:
    """What live-validation path exists for this capability: an explicit
    healthcheck, else a conventional auth-status action, else nothing."""
    if entry.get("healthcheck"):
        return "healthcheck"
    action_names = {a["name"] for a in entry.get("actions", [])}
    if "auth-status" in action_names:
        return "auth-status"
    return None


def _present_sessions() -> set[str]:
    """Base names of saved web sessions (X.json / X.profile / X.cookies.json)."""
    d = userdata.sessions_dir()
    names: set[str] = set()
    if not d.exists():
        return names
    for p in d.iterdir():
        for suf in (".cookies.json", ".json", ".profile"):
            if p.name.endswith(suf):
                names.add(p.name[: -len(suf)])
                break
    return names


def _annotate(entry: dict[str, Any], kind: str,
              present_sessions: set[str] | None = None) -> dict[str, Any]:
    entry["kind"] = kind
    missing = set(entry.get("missing_secrets", []))
    # OAuth tools carry oauth-token/oauth-accounts secrets that are PRODUCED by the
    # sign-in flow (auth-login), not entered by hand. Hide them from the card so a
    # newcomer sees "Connect (sign in)" instead of confusing set/delete rows for a
    # token they can't type. The oauth CLIENT key (which the user does provide) stays.
    has_oauth = any(a.get("name") == "auth-login" for a in entry.get("actions", []))

    def _oauth_output(nm: str) -> bool:
        return has_oauth and (nm.endswith("oauth-token") or nm.endswith("oauth-accounts"))

    entry["secrets_status"] = [
        {"name": s["name"], "description": s.get("description", ""),
         "present": s["name"] not in missing}
        for s in entry.get("secrets", []) if not _oauth_output(s["name"])
    ]
    entry["probe"] = _probe_kind(entry)
    # A tool may need a saved web login instead of (or on top of) a credential.
    ws = entry.get("web_session")
    session_missing = False
    if ws:
        present = ws["name"] in (present_sessions or set())
        entry["web_session_status"] = {
            "name": ws["name"], "login_url": ws.get("login_url", ""),
            "persistent": ws.get("persistent", False), "channel": ws.get("channel", ""),
            "label": ws.get("label", ""), "present": present}
        session_missing = not present
    entry["needs_setup"] = bool(missing) or session_missing or (
        kind == "agent" and not entry.get("ready", False))
    return entry


def store_stats() -> dict[str, Any] | None:
    """Record/run counts read straight from the SQLite store (read-only), so the
    dashboard never shells out to the context-store tool for a simple count -
    faster, and immune to the keyring-import hang that afflicts subprocesses
    spawned from a detached parent."""
    p = userdata.store_db_path()
    if not p.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        rec = con.execute("SELECT count(*) FROM records").fetchone()[0]
        runs = con.execute("SELECT count(*) FROM runs").fetchone()[0]
        openruns = con.execute(
            "SELECT count(*) FROM runs WHERE status IN ('open','active')").fetchone()[0]
        return {"records": rec, "runs": runs, "open_runs": openruns}
    except sqlite3.Error:
        return None  # schema not initialized yet (fresh install)
    finally:
        con.close()


def providers() -> dict[str, Any]:
    """llm provider config + key presence (NEVER a key value), read in-process
    from providers.json + Credential Manager. Mirrors the llm tool's
    list-providers shape without importing that tool's provider adapters (which
    require its own sys.path) or spawning a subprocess."""
    p = userdata.config_dir("llm") / "providers.json"
    if not p.exists():
        return {"default": None, "providers": [],
                "error": {"code": "no_config", "message": "no providers.json yet"}}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return {"default": None, "providers": [],
                "error": {"code": "bad_config", "message": str(e)}}
    default = cfg.get("default")
    out = []
    for name, pc in (cfg.get("providers") or {}).items():
        out.append({
            "name": name,
            "adapter": pc.get("adapter", "openai_compat"),
            "base_url": pc.get("base_url"),
            "model": pc.get("model"),
            "auth_style": pc.get("auth_style", "bearer"),
            "config": {k: v for k, v in pc.items() if k != "api_key"},
            "key_present": creds.has("llm", name),
            "is_default": name == default,
        })
    return {"default": default, "providers": out}


def build(force: bool = False) -> dict[str, Any]:
    """Cached, single-flight inventory build."""
    with _INV_LOCK:
        fresh = (_INV_CACHE["data"] is not None
                 and (time.time() - _INV_CACHE["ts"]) < _INV_TTL)
        if fresh and not force:
            return _INV_CACHE["data"]
        data = _build()
        _INV_CACHE["ts"] = time.time()
        _INV_CACHE["data"] = data
        return data


def _build() -> dict[str, Any]:
    tool_entries = registry.list_tools()
    tool_index = {t["name"]: t for t in tool_entries}
    sessions = _present_sessions()
    tools = [_annotate(t, "tool", sessions) for t in tool_entries]
    agents = [_annotate(a, "agent", sessions)
              for a in registry.list_agents(tool_index=tool_index)]
    skills = registry.list_skills()
    for s in skills:
        s["kind"] = "skill"

    store = store_stats()
    fresh = bootstraplib.freshness(store)
    prov = providers()
    llm_ready = any(p.get("key_present") for p in prov.get("providers", []))

    def cnt(items, pred):
        return sum(1 for x in items if pred(x))

    def is_ready(x):  # truly set up: no missing secrets, no missing session, loads
        return not x.get("needs_setup") and not x.get("error")

    summary = {
        "tools": {
            "total": len(tools),
            "ready": cnt(tools, is_ready),
            "needs_setup": cnt(tools, lambda t: t.get("needs_setup")),
            "errored": cnt(tools, lambda t: t.get("error")),
        },
        "agents": {
            "total": len(agents),
            "ready": cnt(agents, is_ready),
            "needs_setup": cnt(agents, lambda a: a.get("needs_setup")),
            "errored": cnt(agents, lambda a: a.get("error")),
        },
        "skills": {"total": len(skills)},
        "llm_ready": llm_ready,
    }

    return {
        "summary": summary,
        "tools": tools,
        "agents": agents,
        "skills": skills,
        "providers": prov,
        "store": store,
        "userdata": {
            **userdata.describe(),
            "scan": fresh["scan"],
        },
        "fresh_start": fresh["fresh_start"],
        "onboarding": bootstraplib.onboarding_hint() if fresh["fresh_start"] else None,
    }
