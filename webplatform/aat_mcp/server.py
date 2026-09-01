"""aat-mcp: a stdio MCP server exposing the AAT registry as a small generic surface.

Hand-rolled JSON-RPC 2.0 over newline-delimited stdio (no third-party dependency,
robust to environment quirks). A driver (opencode, or any MCP client) connects and
gets these tools (opencode shows them prefixed with the server name, e.g.
`aat_run_tool`):

  capabilities        - list tools/agents/skills; or one capability's full arg schema
  run_tool            - run a REVERSIBLE tool with structured JSON args
  run_agent           - run a REVERSIBLE agent
  run_tool_confirmed  - run a tool INCLUDING irreversible actions (human-approved)
  run_agent_confirmed - run an agent INCLUDING irreversible actions (human-approved)
  get_skill           - fetch a skill's markdown (model-decided loading; spec 04)

Two things this fixes vs the B0 bash spike: args are JSON objects (no shell
quote-escaping) and capability schemas replace `--help` spelunking.

Safety (spec 03): the reversibility gate is CODE, evaluated before execution
(gate.py -> agents/_lib/reversibility, the same policy as `orchestrator drive` and
`deputy`). `run_tool`/`run_agent` refuse irreversible actions and return
`approval_required`, naming the `*_confirmed` path. Only the `*_confirmed` tools are
marked `ask` in opencode, so a HUMAN approves each side effect; a model cannot forge
the click and cannot bypass by picking the plain tool. Set AAT_MCP_DENY_IRREVERSIBLE
for a headless run where even confirmed actions must be refused.

Run:  python webplatform/aat_mcp/server.py         (opencode spawns this over stdio)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge  # noqa: E402  (sibling module)
import gate  # noqa: E402

SERVER_INFO = {"name": "aat-mcp", "version": "0.2.0"}
DEFAULT_PROTOCOL = "2024-11-05"

_RUN_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "description": "registered tool name"},
        "action": {"type": "string", "description": "action name (omit for a flat tool)"},
        "args": {"type": "object", "description": "flag name -> value (objects/arrays pass cleanly)"},
    },
    "required": ["tool"],
}
_RUN_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "agent": {"type": "string", "description": "registered agent name"},
        "action": {"type": "string", "description": "action name"},
        "args": {"type": "object", "description": "flag name -> value"},
    },
    "required": ["agent"],
}

TOOLS = [
    {
        "name": "capabilities",
        "description": (
            "List AAT capabilities. No args -> a compact list of every ready "
            "tool/agent/skill (name, description, primary_action). Pass name=<tool "
            "or agent> to get that capability's full action+arg schema - use this "
            "INSTEAD of running a tool with --help. Optional kind filter: "
            "tool|agent|skill."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["tool", "agent", "skill"]},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "run_tool",
        "description": (
            "Run a registered AAT tool for a REVERSIBLE / read action. 'args' is a "
            "JSON object of flag name->value (objects/arrays pass cleanly, no shell "
            "escaping). If the action is irreversible (send/delete/pay/post/...), "
            "this REFUSES and returns approval_required telling you to use "
            "run_tool_confirmed. Discover tools/actions via capabilities."
        ),
        "inputSchema": _RUN_TOOL_SCHEMA,
    },
    {
        "name": "run_tool_confirmed",
        "description": (
            "Run a tool INCLUDING an irreversible action (send/delete/pay/post/"
            "issue-invoice/...). The operator is asked to approve before it runs. "
            "Use this only after run_tool returned approval_required, or when you "
            "know the action has a real-world side effect."
        ),
        "inputSchema": _RUN_TOOL_SCHEMA,
    },
    {
        "name": "run_agent",
        "description": (
            "Run a registered AAT agent for a REVERSIBLE action. Route every "
            "substantive request first with agent='orchestrator', action='intake', "
            "args={'request': '<the ask>'} (per AGENTS.md). Irreversible agent "
            "actions are refused here - use run_agent_confirmed."
        ),
        "inputSchema": _RUN_AGENT_SCHEMA,
    },
    {
        "name": "run_agent_confirmed",
        "description": (
            "Run an agent INCLUDING an irreversible action. The operator is asked to "
            "approve before it runs."
        ),
        "inputSchema": _RUN_AGENT_SCHEMA,
    },
    {
        "name": "get_skill",
        "description": "Fetch a registered skill's full markdown content by name.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def _log(msg: str) -> None:
    print(f"[aat-mcp] {msg}", file=sys.stderr, flush=True)


def _run(kind: str, arguments: dict, confirmed: bool) -> tuple[dict, bool]:
    """Execute a tool/agent through the reversibility gate.

    kind: 'tool' or 'agent'. confirmed: True for the *_confirmed tools (opencode has
    already asked the operator). Returns (payload, is_error)."""
    key = "tool" if kind == "tool" else "agent"
    target = arguments.get(key)
    if not target:
        return {"error": f"run_{kind} requires '{key}'"}, True
    action = arguments.get("action")
    verdict = gate.classify(target, action)

    if not confirmed and not verdict["reversible"]:
        # Plain tool refuses an irreversible action and names the confirmed path.
        return {"approval_required": {
            key: target, "action": action, "verb": verdict["verb"],
            "blast_class": verdict["blast_class"], "reason": verdict["reason"],
            "next": (f"This action is irreversible ({verdict['blast_class']}). To "
                     f"proceed, call run_{kind}_confirmed with the same arguments - "
                     f"the operator will be asked to approve it."),
        }}, False

    if confirmed and not verdict["reversible"] and gate.deny_irreversible_env():
        # Headless fail-safe: no human in the seat to approve.
        return {"refused": ("irreversible action denied (AAT_MCP_DENY_IRREVERSIBLE "
                            "is set; no human in the seat)"),
                "verb": verdict["verb"], "blast_class": verdict["blast_class"]}, True

    runner = bridge.run_tool if kind == "tool" else bridge.run_agent
    res = runner(target, action, arguments.get("args"))
    if not res.get("ok", False):
        # Recovery hint so the driver re-discovers instead of guessing again, falling
        # back to bash, or claiming it lacks access (observed with weaker models on a
        # bad action/args or a transient tool error).
        res = dict(res)
        res["hint"] = (f"This {kind} call failed - it does NOT mean you lack access. "
                       f"Call capabilities with name='{target}' to see its valid actions "
                       f"and required args, then retry run_{kind}. Do NOT fall back to bash.")
        return res, True
    return res, False


def _call_tool(name: str, arguments: dict) -> tuple[dict, bool]:
    """Return (result_payload, is_error). Never raises: failures come back as a
    structured payload the model can read."""
    try:
        if name == "capabilities":
            return bridge.capabilities(arguments.get("kind"), arguments.get("name")), False
        if name == "run_tool":
            return _run("tool", arguments, confirmed=False)
        if name == "run_tool_confirmed":
            return _run("tool", arguments, confirmed=True)
        if name == "run_agent":
            return _run("agent", arguments, confirmed=False)
        if name == "run_agent_confirmed":
            return _run("agent", arguments, confirmed=True)
        if name == "get_skill":
            if not arguments.get("name"):
                return {"error": "get_skill requires 'name'"}, True
            return bridge.get_skill(arguments["name"]), False
        return {"error": f"unknown tool: {name}"}, True
    except KeyError as e:
        return {"error": str(e)}, True
    except Exception as e:  # noqa: BLE001 - surface as a readable tool error
        return {"error": f"{type(e).__name__}: {e}"}, True


def handle(req: dict) -> dict | None:
    """Dispatch one JSON-RPC request. Returns a response dict, or None for a
    notification (no response)."""
    method = req.get("method")
    req_id = req.get("id")
    is_notification = "id" not in req

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        params = req.get("params") or {}
        proto = params.get("protocolVersion") or DEFAULT_PROTOCOL
        return ok({"protocolVersion": proto,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": SERVER_INFO})
    if method == "notifications/initialized" or (method or "").startswith("notifications/"):
        return None
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        payload, is_error = _call_tool(name, arguments)
        text = json.dumps(payload, ensure_ascii=False)
        return ok({"content": [{"type": "text", "text": text}], "isError": is_error})

    if is_notification:
        return None
    return err(-32601, f"method not found: {method}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - older interpreters; best effort
        pass
    _log("started (stdio). Waiting for JSON-RPC on stdin.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        try:
            resp = handle(req)
        except Exception as e:  # noqa: BLE001
            _log(f"handler error: {e}")
            resp = {"jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32603, "message": f"internal error: {e}"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
