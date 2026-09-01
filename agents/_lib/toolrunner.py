"""Drive registered tools from an agent.

An agent never imports a tool's internals. It invokes the tool's entrypoint as a
subprocess and parses the single JSON object the tool prints to stdout — exactly
the JSON-in / JSON-out contract every tool already honors. This keeps agents
decoupled: a tool can be rewritten freely as long as its manifest contract holds.

Throughput note: subprocess-per-call adds ~hundreds of ms, which is irrelevant for
outreach (deliberately throttled, warmup-capped sends) and keeps the boundary clean.

Testability: `invoke` takes an optional `runner` callable so tests can fake tool
execution without spawning processes or hitting the network.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from registry import get_agent, get_tool  # noqa: E402

# A runner takes the argv list and returns (returncode, stdout, stderr).
Runner = Callable[[list[str]], "tuple[int, str, str]"]


class ToolError(Exception):
    """A driven tool failed: it returned an {"error": {...}} envelope, produced
    non-JSON output, or could not be located/spawned."""

    def __init__(self, tool: str, code: str, message: str,
                 details: dict[str, Any] | None = None):
        self.tool = tool
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"{tool}: {code}: {message}")


def _subprocess_runner(timeout: int) -> Runner:
    def run(cmd: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    return run


def _parse_tool_output(tool: str, stdout: str, stderr: str) -> dict[str, Any]:
    """Tools emit exactly one JSON object on stdout (logs go to stderr). Parse the
    last non-empty stdout line defensively, raising ToolError on anything else."""
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        raise ToolError(tool, "no_output", "tool produced no stdout",
                        {"stderr": stderr[-800:]})
    try:
        data = json.loads(lines[-1])
    except ValueError:
        raise ToolError(tool, "bad_output", "tool stdout was not JSON",
                        {"stdout": stdout[-800:], "stderr": stderr[-800:]})
    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        err = data["error"]
        raise ToolError(tool, err.get("code", "tool_error"),
                        err.get("message", ""), err.get("details") or {})
    if not isinstance(data, dict):
        raise ToolError(tool, "bad_output", "tool JSON was not an object",
                        {"stdout": stdout[-800:]})
    return data


def invoke(tool_name: str, *args: Any, runner: Runner | None = None,
           timeout: int = 120) -> dict[str, Any]:
    """Run a registered tool and return its parsed JSON object.

    Example: invoke("apollo", "search-people", "--keywords", "energy", "--per-page", 25)
    Raises ToolError on tool-not-found, spawn failure, non-JSON output, or an
    {"error": ...} envelope from the tool.
    """
    try:
        # respect_hidden=False: a scoped surface limits what a session is offered,
        # it must not break an agent's own plumbing. See registry.get_tool.
        m = get_tool(tool_name, respect_hidden=False)
    except KeyError:
        raise ToolError(tool_name, "tool_not_found",
                        f"no registered tool named {tool_name!r}")
    if m.path is None:
        raise ToolError(tool_name, "no_path", "tool manifest has no path")
    entry = m.path / m.entrypoint
    if not entry.exists():
        raise ToolError(tool_name, "no_entrypoint", f"entrypoint missing: {entry}")

    argv = [sys.executable, str(entry), *[str(a) for a in args]]
    run = runner or _subprocess_runner(timeout)
    try:
        rc, out, err = run(argv)
    except subprocess.TimeoutExpired:
        raise ToolError(tool_name, "timeout", f"tool timed out after {timeout}s")
    except Exception as exc:  # noqa: BLE001
        raise ToolError(tool_name, "spawn_failed", str(exc))
    # A tool failure still prints a JSON error envelope, so parse before trusting rc.
    return _parse_tool_output(tool_name, out, err)


def invoke_agent(agent_name: str, *args: Any, runner: Runner | None = None,
                 timeout: int = 300) -> dict[str, Any]:
    """Run a registered AGENT and return its parsed JSON object.

    An agent honors the same JSON-in / JSON-out contract as a tool (action name
    as the first positional arg, one JSON object on stdout, {"error": ...} on
    failure), so this mirrors ``invoke`` but resolves the entrypoint via
    ``get_agent``. This is what lets the headless ``orchestrator drive`` loop
    drive OTHER agents (curator, email-classifier, ...) as well as tools.

    Example: invoke_agent("curator", "recall", "--query", "pricing deck")
    Raises ToolError (with the agent name as ``.tool``) on not-found, spawn
    failure, non-JSON output, or an {"error": ...} envelope from the agent.
    """
    try:
        m = get_agent(agent_name)
    except KeyError:
        raise ToolError(agent_name, "agent_not_found",
                        f"no registered agent named {agent_name!r}")
    if m.path is None:
        raise ToolError(agent_name, "no_path", "agent manifest has no path")
    entry = m.path / m.entrypoint
    if not entry.exists():
        raise ToolError(agent_name, "no_entrypoint", f"entrypoint missing: {entry}")

    argv = [sys.executable, str(entry), *[str(a) for a in args]]
    run = runner or _subprocess_runner(timeout)
    try:
        rc, out, err = run(argv)
    except subprocess.TimeoutExpired:
        raise ToolError(agent_name, "timeout", f"agent timed out after {timeout}s")
    except Exception as exc:  # noqa: BLE001
        raise ToolError(agent_name, "spawn_failed", str(exc))
    return _parse_tool_output(agent_name, out, err)
