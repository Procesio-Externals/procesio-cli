"""Auto-discovery for tools and agents.

Walks tools/*/tool.yaml and agents/*/agent.yaml, validates manifests, and
returns a unified registry. Used by:
  - scripts/list-tools.py and scripts/run-tool.py
  - Agents (when they ship) to introspect available tools without hardcoding.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tools._lib import creds
from tools._lib.manifest import load_agent, load_skill, load_tool

ROOT = Path(__file__).parent
TOOLS_DIR = ROOT / "tools"
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"


def hidden_tools() -> set[str]:
    """Tool names this session must not see, by directory name.

    A scoped tool surface. Two sources, env first so a single run can override the
    persisted setting:

      AAT_TOOLS_HIDE=a,b                        (env, comma-separated)
      context-state-knowledge/config/registry/hidden-tools.json  -> {"hide": [...]}

    Hiding is REGISTRY-level only: the directory keeps its name and stays a normal
    Python package, so a tool that imports another one directly keeps working, and
    `get_tool(..., respect_hidden=False)` still resolves it for the framework's own
    plumbing. That separation is what let an A/B run swap the surface a session was
    offered without renaming anything or editing the code under test.

    Never raises: an unreadable config must not take the whole registry down."""
    raw = os.environ.get("AAT_TOOLS_HIDE")
    if raw is not None:
        return {n.strip() for n in raw.split(",") if n.strip()}
    try:
        from tools._lib import userdata
        cfg = Path(userdata.config_dir("registry")) / "hidden-tools.json"
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return {str(n) for n in data.get("hide", [])}
    except Exception:  # noqa: BLE001 - scoping is a convenience, never a blocker
        pass
    return set()


def _has_secret(tool_name: str, secret_name: str) -> bool:
    """Check secret presence. Supports `namespace:name` for shared secrets,
    e.g. `google:oauth-client` -> agents-and-tools:google:oauth-client.

    Never raises. Readiness is a REPORT, and a machine with no reachable
    credential store still has to be able to list what is installed: a headless
    Linux box has no session keyring at all, so constructing the backend there
    throws and would otherwise take down the whole registry, the router build and
    the dashboard with it. Unreachable is reported the same as absent, which is
    the honest answer to "is this tool ready" - it is not, and the store error
    says why the moment anyone actually calls creds.get, which still raises.
    """
    if ":" in secret_name:
        ns, _, name = secret_name.partition(":")
        return creds.has_for_report(ns, name)
    return creds.has_for_report(tool_name, secret_name)


def _oauth_scope_gap(tool_dir: Path) -> list[str] | None:
    """Scopes a tool declares that the stored OAuth token does not carry.

    `ready` used to mean only "every declared secret is present". The whole
    google-* family shares one client + one token, so the moment ANY of them
    finished its OAuth flow all of them flipped ready - carrying only the
    scopes that one flow had requested. Seven tools reported ready and then
    answered 403 "insufficient authentication scopes" on first use.

    Returns None when the tool has no OAuth scope surface at all, so "no gap"
    and "not applicable" stay distinguishable. Never raises: readiness
    reporting must not be able to take the registry down.
    """
    auth_py = tool_dir / "auth.py"
    if not auth_py.exists():
        return None
    try:
        if "register_scopes" not in auth_py.read_text(encoding="utf-8"):
            return None
        import importlib

        mod = importlib.import_module(f"tools.{tool_dir.name}.auth")
        declared = set(getattr(mod, "SCOPES", None) or [])
        if not declared:
            return None
        from tools._lib import google_auth

        token = google_auth._load_token()
        if token is None:
            # No token at all is already reported as a missing secret; saying
            # it twice, as ten missing scopes, buries the actual instruction.
            return None
        held = set(token.get("scopes") or [])
        return sorted(declared - held)
    except Exception:  # noqa: BLE001 - see docstring
        return None


def list_tools() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not TOOLS_DIR.exists():
        return out
    hidden = hidden_tools()
    for manifest_path in sorted(TOOLS_DIR.glob("*/tool.yaml")):
        dir_name = manifest_path.parent.name
        if dir_name.startswith("_") or dir_name in hidden:
            continue
        try:
            m = load_tool(manifest_path)
        except Exception as e:
            out.append({
                "name": dir_name,
                "error": f"manifest load failed: {e}",
                "ready": False,
            })
            continue
        absent = [s for s in m.secrets if not _has_secret(m.name, s.name)]
        missing = [s.name for s in absent if not s.optional]
        missing_optional = [s.name for s in absent if s.optional]
        missing_scopes = _oauth_scope_gap(manifest_path.parent) or []
        # Three outcomes, one boolean plus a label. `ready` stays a bool so no
        # existing consumer breaks, but "authorized, just not for this tool" is
        # the normal state during incremental setup, not an error - and it
        # needs a different instruction ("re-run auth-login") from a missing
        # credential ("store the secret"), so the label carries which.
        if missing:
            readiness = "needs-credentials"
        elif missing_scopes:
            readiness = "needs-scopes"
        else:
            readiness = "ready"
        out.append({
            "name": m.name,
            "description": m.description,
            "version": m.version,
            "tier": m.tier,
            "path": str(m.path),
            "entrypoint": m.entrypoint,
            "args": [a.model_dump() for a in m.args],
            "actions": [
                {
                    "name": a.name,
                    "description": a.description,
                    "args": [arg.model_dump() for arg in a.args],
                }
                for a in m.actions
            ],
            "secrets": [s.model_dump() for s in m.secrets],
            "routing": m.routing.model_dump() if m.routing else None,
            "healthcheck": m.healthcheck.model_dump() if m.healthcheck else None,
            "web_session": m.web_session.model_dump() if m.web_session else None,
            "missing_secrets": missing,
            # Absent but not blocking: shown so setup can still offer them,
            # never counted against readiness.
            "missing_optional_secrets": missing_optional,
            "missing_scopes": missing_scopes,
            "readiness": readiness,
            "ready": readiness == "ready",
        })
    return out


def get_tool(name: str, *, respect_hidden: bool = True):
    """Resolve a tool manifest by name.

    ``respect_hidden=False`` bypasses the scoped surface. Agents pass it: hiding
    is meant to shrink what a SESSION is offered, not to amputate the framework
    underneath it. Hiding a tool used to disable every agent that drives it -
    `procesio audit` died with "no registered tool named 'procesio'" the moment
    that tool was scoped out for an experiment - which is a silent, confusing
    failure a long way from its cause."""
    import sys
    hidden = hidden_tools() if respect_hidden else set()
    if name in hidden:
        raise KeyError(f"tool not found: {name}")
    for manifest_path in TOOLS_DIR.glob("*/tool.yaml"):
        if manifest_path.parent.name.startswith("_") or manifest_path.parent.name in hidden:
            continue
        try:
            m = load_tool(manifest_path)
        except Exception as exc:  # noqa: BLE001
            # A broken/transiently-unreadable SIBLING manifest must not block the
            # requested tool. Re-raise only if it's the tool we were asked for.
            if manifest_path.parent.name == name:
                raise
            print(f"warning: skipping unloadable tool manifest "
                  f"'{manifest_path.parent.name}': {exc}", file=sys.stderr)
            continue
        if m.name == name:
            return m
    raise KeyError(f"tool not found: {name}")


def list_agents(tool_index: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not AGENTS_DIR.exists():
        return out
    # Index every tool ONCE (name -> its list_tools() entry, which already carries
    # ready/missing_secrets). Previously each driven-tool lookup called get_tool(),
    # which re-globbed and re-parsed all tool manifests - O(agents x tools) YAML
    # parses that made this call take tens of seconds on a large registry. A caller
    # that has already built the tool list (e.g. the dashboard) can pass it in to
    # avoid a second full scan.
    if tool_index is None:
        tool_index = {t["name"]: t for t in list_tools()}
    for manifest_path in sorted(AGENTS_DIR.glob("*/agent.yaml")):
        dir_name = manifest_path.parent.name
        if dir_name.startswith("_"):
            continue
        try:
            m = load_agent(manifest_path)
        except Exception as e:
            out.append({"name": dir_name, "error": str(e), "ready": False})
            continue
        missing = [s.name for s in m.secrets if not _has_secret(m.name, s.name)]
        # An agent is "ready" only if its own secrets AND every tool it drives
        # are present and ready. Surface unready tools so gaps are visible.
        tool_status = {}
        for tname in m.tools:
            t = tool_index.get(tname)
            if t is not None and not t.get("error"):
                tool_status[tname] = {"present": True, "ready": bool(t.get("ready")),
                                      "missing_secrets": t.get("missing_secrets", [])}
            else:
                tool_status[tname] = {"present": False, "ready": False,
                                      "missing_secrets": []}
        out.append({
            "name": m.name,
            "description": m.description,
            "version": m.version,
            "tier": m.tier,
            "path": str(m.path),
            "entrypoint": m.entrypoint,
            "tools": m.tools,
            "tool_status": tool_status,
            "actions": [
                {"name": a.name, "description": a.description,
                 "args": [arg.model_dump() for arg in a.args]}
                for a in m.actions
            ],
            "secrets": [s.model_dump() for s in m.secrets],
            "routing": m.routing.model_dump() if m.routing else None,
            "healthcheck": m.healthcheck.model_dump() if m.healthcheck else None,
            "missing_secrets": missing,
            # An agent is ready only when its own secrets AND every tool it drives
            # are ready (matches the docstring above). own_ready is surfaced too so
            # a UI can distinguish "agent's own creds are set" from "a driven tool
            # is missing creds".
            "own_ready": len(missing) == 0,
            "ready": len(missing) == 0 and all(
                st["ready"] for st in tool_status.values()),
        })
    return out


def get_agent(name: str):
    for manifest_path in AGENTS_DIR.glob("*/agent.yaml"):
        if manifest_path.parent.name.startswith("_"):
            continue
        m = load_agent(manifest_path)
        if m.name == name:
            return m
    raise KeyError(f"agent not found: {name}")


def list_skills() -> list[dict[str, Any]]:
    """Discover skills. A skill's `SKILL.md` frontmatter is its manifest; skills
    carry no secrets, so a successfully-loaded skill is always ready."""
    out: list[dict[str, Any]] = []
    if not SKILLS_DIR.exists():
        return out
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        dir_name = skill_md.parent.name
        if dir_name.startswith("_") or dir_name == "tests":
            continue
        try:
            m = load_skill(skill_md)
        except Exception as e:
            out.append({
                "name": dir_name,
                "error": f"manifest load failed: {e}",
                "ready": False,
            })
            continue
        entry = {
            "name": m.name,
            "description": m.description,
            "version": m.version,
            "path": str(m.path),
            "routing": m.routing.model_dump() if m.routing else None,
            "ready": True,
        }
        # Non-fatal hygiene signal: folder name should match the manifest name.
        if m.name != dir_name:
            entry["warning"] = f"folder '{dir_name}' != skill name '{m.name}'"
        out.append(entry)
    return out


def get_skill(name: str):
    for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
        if skill_md.parent.name.startswith("_") or skill_md.parent.name == "tests":
            continue
        m = load_skill(skill_md)
        if m.name == name:
            return m
    raise KeyError(f"skill not found: {name}")


def resolve_catalog(entries: list[dict[str, Any]],
                    ws_overrides: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    """Effective per-workspace catalog under the official/template/custom + copy-on-write
    model (spec P0.0-06 / D11). Pure function over registry entries + a per-workspace
    override map (name -> the workspace's own copy/custom); the override STORE is the
    platform's job (object storage / a package feed), so this stays testable and
    storage-agnostic.

    Rules:
      - official : always present, from the shared registry; a workspace CANNOT override
        it (users can't change official).
      - template : the workspace's override if it forked one (copy-on-write), else the
        shared template. An untouched workspace holds ZERO copies (conserve resources).
      - custom   : the workspace's own entries (overrides that don't shadow an official).

    Each returned entry carries `effective_tier` in
    {official, template, custom-copy, custom}. `ws_overrides` unset = the shared catalog
    unchanged (exactly the single-tenant local behaviour)."""
    ws_overrides = dict(ws_overrides or {})
    by_name = {e["name"]: e for e in entries}
    out: dict[str, dict] = {}

    for e in entries:
        tier = e.get("tier", "template")
        if tier == "official":
            out[e["name"]] = {**e, "effective_tier": "official"}
        elif tier == "template":
            if e["name"] in ws_overrides:
                out[e["name"]] = {**ws_overrides[e["name"]],
                                  "name": e["name"], "effective_tier": "custom-copy"}
            else:
                out[e["name"]] = {**e, "effective_tier": "template"}
        # a 'custom'-tier entry shipped in the base registry is unusual; customs are
        # expected to arrive via ws_overrides, handled below.

    for name, ov in ws_overrides.items():
        base = by_name.get(name)
        if base is not None and base.get("tier") == "official":
            continue  # official is immutable per-workspace
        if name not in out:
            out[name] = {**ov, "name": name, "effective_tier": "custom"}

    return list(out.values())
