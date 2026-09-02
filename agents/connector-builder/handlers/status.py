"""status action — report the connector-builder agent's readiness and that of the
tools it drives (`connector-builder`, `procesio`). Pure registry introspection:
no network, no secrets. A tool not yet registered/ready surfaces as unready, never
an error.
"""
from __future__ import annotations

from agents._lib.actiondef import ActionDef


def _status(_args) -> dict:
    from registry import list_agents

    me = next((a for a in list_agents() if a.get("name") == "connector-builder"), None)
    if me is None:
        return {"agent": "connector-builder", "found": False,
                "note": "agent.yaml not discovered by the registry"}
    tools = me.get("tool_status", {})
    return {
        "agent": "connector-builder",
        "found": True,
        "version": me.get("version"),
        "ready": me.get("ready", False),
        "missing_secrets": me.get("missing_secrets", []),
        "tools_ready": sorted(n for n, s in tools.items() if s.get("ready")),
        "tools_unready": {n: s for n, s in tools.items() if not s.get("ready")},
    }


ACTIONS = {
    "status": ActionDef(
        func=_status,
        description="Report agent + driven-tool readiness (connector-builder, procesio).",
    ),
}
