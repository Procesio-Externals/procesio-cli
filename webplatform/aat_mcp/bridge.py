"""AAT-facing logic for the MCP bridge — pure, testable, no protocol code.

Exposes the live registry to a driver as a small generic surface and executes
capabilities by shelling to scripts/run-tool.py / run-agent.py with a Python LIST
argv (no shell), so structured args (including JSON objects) pass cleanly. This is
the fix for the bash-passthrough tax observed in the B0 spike: the model no longer
fights shell quote-escaping, and gets typed capability schemas instead of `--help`
spelunking.

Execution reuses dashboard.server.runner (the existing, tested subprocess bridge)
so there is ONE definition of "run a framework script and normalize its JSON".
"""
from __future__ import annotations

import contextvars
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import registry  # noqa: E402
from dashboard.server import runner  # noqa: E402  (shared shell-to-script bridge)
from tools._lib import accounting  # noqa: E402  (per-work-unit accounting seam, P0.0-05)

# Per-request user id (multi-user web platform). Set by the aat-mcp HTTP server from a
# SERVER-ESTABLISHED header (the authenticated session), NEVER from model output. Read
# here to run the tool/agent subprocess as that user, so userdata + creds isolate
# per-user (userdata.base() -> <root>/<user>, file creds -> per-user namespace). Unset =
# single-user, exactly as before (local Claude Code unaffected).
_user_ctx: "contextvars.ContextVar" = contextvars.ContextVar("aat_user_id", default=None)


def set_user(uid: str | None):
    """Set the current request's user; returns a token for reset_user()."""
    return _user_ctx.set(uid or None)


def reset_user(token) -> None:
    _user_ctx.reset(token)


# Per-request WORKSPACE id (multi-tenant PROCESIO module, spec P0.0-01). Set alongside
# the user from the SERVER-ESTABLISHED session, never from model output. Threads
# AAT_WORKSPACE_ID into the tool/agent subprocess env so userdata + creds isolate per
# (workspace, user). Unset = single-workspace, exactly as before.
_workspace_ctx: "contextvars.ContextVar" = contextvars.ContextVar(
    "aat_workspace_id", default=None)


def set_workspace(ws: str | None):
    """Set the current request's workspace; returns a token for reset_workspace()."""
    return _workspace_ctx.set(ws or None)


def reset_workspace(token) -> None:
    _workspace_ctx.reset(token)


def _user_env() -> dict | None:
    env: dict = {}
    uid = _user_ctx.get()
    if uid:
        env["AAT_USER_ID"] = str(uid)
    ws = _workspace_ctx.get()
    if ws:
        env["AAT_WORKSPACE_ID"] = str(ws)
    return env or None

# Tools that cannot run in a container (browser/profile, DB driver, media system libs).
# When AAT_HOST_RUNNER_URL is set, these (and agents that drive them) are executed on
# the HOST via the host-runner instead of in-container. Extend via AAT_HOST_ONLY_TOOLS.
_HOST_ONLY_TOOLS = {
    "sqlserver", "web",
    }


def _host_only_set() -> set[str]:
    extra = {t.strip() for t in os.environ.get("AAT_HOST_ONLY_TOOLS", "").split(",") if t.strip()}
    return _HOST_ONLY_TOOLS | extra


def _is_host_only(kind: str, name: str) -> bool:
    """A tool is host-only if listed or its manifest declares a web_session. An agent
    is host-only if any tool it drives is host-only."""
    hoset = _host_only_set()
    if kind == "tool":
        if name in hoset:
            return True
        try:
            return getattr(registry.get_tool(name), "web_session", None) is not None
        except Exception:  # noqa: BLE001
            return False
    try:
        drives = set(getattr(registry.get_agent(name), "tools", []) or [])
    except Exception:  # noqa: BLE001
        return False
    if drives & hoset:
        return True
    for t in drives:
        try:
            if getattr(registry.get_tool(t), "web_session", None) is not None:
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def _delegate(kind: str, name: str, action: str | None, args: dict | None) -> dict:
    """Run a host-only tool/agent on the host via the host-runner."""
    url = os.environ["AAT_HOST_RUNNER_URL"].rstrip("/") + "/run"
    token = os.environ.get("AAT_HOST_RUNNER_TOKEN", "")
    payload = json.dumps({"kind": kind, "name": name, "action": action,
                          "args": args or {}}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    uid = _user_ctx.get()
    if uid:
        headers["X-AAT-User"] = str(uid)  # host-only tools run as this user too
    ws = _workspace_ctx.get()
    if ws:
        headers["X-AAT-Workspace"] = str(ws)  # ...and in this workspace
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=330) as resp:  # noqa: S310 (host-local)
            return json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.URLError as e:
        return {"ok": False, "error": {"code": "host_runner_unreachable",
                                       "message": f"host-only {kind} {name!r}: {e}"}}


def _compact(entry: dict, kind: str) -> dict:
    routing = entry.get("routing") or {}
    return {
        "kind": kind,
        "name": entry["name"],
        "description": (entry.get("description") or "")[:240],
        "primary_action": routing.get("primary_action", ""),
        "example": routing.get("example", ""),
        "ready": bool(entry.get("ready", True)),
    }


def _full(entry: dict, kind: str) -> dict:
    """Full action + arg schema for one capability — the structured replacement for
    `--help`, so the driver never has to spelunk help text."""
    def _args(arglist):
        return [
            {
                "name": arg["name"],
                "type": arg.get("type", "string"),
                "required": bool(arg.get("required", False)),
                "description": arg.get("description", ""),
            }
            for arg in (arglist or [])
        ]

    return {
        "kind": kind,
        "name": entry["name"],
        "description": entry.get("description", ""),
        "ready": bool(entry.get("ready", True)),
        "missing_secrets": entry.get("missing_secrets", []),
        "tools": entry.get("tools", []) if kind == "agent" else None,
        # Flat tools (e.g. hello-world) keep args at the top level, not under actions.
        "args": _args(entry.get("args")) if not entry.get("actions") else [],
        "actions": [
            {
                "name": a["name"],
                "description": a.get("description", ""),
                "args": [
                    {
                        "name": arg["name"],
                        "type": arg.get("type", "string"),
                        "required": bool(arg.get("required", False)),
                        "description": arg.get("description", ""),
                    }
                    for arg in a.get("args", [])
                ],
            }
            for a in entry.get("actions", [])
        ],
    }


_REG_CACHE: dict = {}


def _scan_registry():
    """Cache the registry scan (parse ~74 manifests + per-secret presence checks) for a
    short TTL. In a running container the registry is static and the model calls
    capabilities several times per loop; without this each call re-parses every manifest
    and re-checks every secret. AAT_REGISTRY_TTL seconds (0 = off)."""
    ttl = float(os.environ.get("AAT_REGISTRY_TTL", "30") or 0)
    if ttl > 0:
        hit = _REG_CACHE.get("data")
        if hit is not None and hit[1] > time.monotonic():
            return hit[0]
    tools = registry.list_tools()
    agents = registry.list_agents({t["name"]: t for t in tools})
    skills = registry.list_skills()
    if ttl > 0:
        _REG_CACHE["data"] = ((tools, agents, skills), time.monotonic() + ttl)
    return tools, agents, skills


def capabilities(kind: str | None = None, name: str | None = None) -> dict:
    """No name -> compact list of every ready tool/agent (+ skills), like the
    router map. With name -> the full action/arg schema for that one capability."""
    tools, agents, skills = _scan_registry()

    if name:
        for e in tools:
            if e.get("name") == name:
                return {"capability": _full(e, "tool")}
        for e in agents:
            if e.get("name") == name:
                return {"capability": _full(e, "agent")}
        raise KeyError(f"no tool or agent named {name!r}")

    out: list[dict] = []
    if kind in (None, "tool"):
        out += [_compact(e, "tool") for e in tools if not e.get("error")]
    if kind in (None, "agent"):
        out += [_compact(e, "agent") for e in agents if not e.get("error")]
    if kind in (None, "skill"):
        out += [_compact(e, "skill") for e in skills
                if not e.get("error")]
    return {"count": len(out), "capabilities": out}


def run_tool(tool: str, action: str | None, args: dict[str, Any] | None) -> dict:
    """Execute a tool. args is a JSON object -> --flags via runner.flags_from
    (dict/list values are JSON-encoded into ONE argv element; no shell). Host-only
    tools are delegated to the host-runner when AAT_HOST_RUNNER_URL is set."""
    # Wrap in a per-work-unit accounting span (no-op locally; the platform injects a
    # sink that acquires an EE slot + emits TrackAction - spec P0.0-05 / seam S2).
    with accounting.work_unit("tool", ws=_workspace_ctx.get(),
                              user=_user_ctx.get()) as wu:
        wu["tool"] = tool
        if action:
            wu["action"] = action
        if os.environ.get("AAT_HOST_RUNNER_URL") and _is_host_only("tool", tool):
            return _delegate("tool", tool, action, args)
        argv = ([action] if action else []) + runner.flags_from(args)
        return runner.run_tool(tool, argv, env=_user_env())


def run_agent(agent: str, action: str | None, args: dict[str, Any] | None) -> dict:
    with accounting.work_unit("agent", ws=_workspace_ctx.get(),
                              user=_user_ctx.get()) as wu:
        wu["agent"] = agent
        if action:
            wu["action"] = action
        if os.environ.get("AAT_HOST_RUNNER_URL") and _is_host_only("agent", agent):
            return _delegate("agent", agent, action, args)
        argv = ([action] if action else []) + runner.flags_from(args)
        return runner.run_agent(agent, argv, env=_user_env())


def get_skill(name: str) -> dict:
    """Return a skill's full markdown (model-decided skill loading — the substitute
    for harness auto-trigger; see spec 04)."""
    m = registry.get_skill(name)  # raises KeyError if unknown
    md = (m.path / "SKILL.md").read_text(encoding="utf-8")
    return {"name": name, "content": md}
