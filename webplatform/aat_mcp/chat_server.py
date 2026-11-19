"""procesio-chat: the PUBLISHED MCP surface, built from chat_surface.yaml.

A second surface over the same substrate as server.py, for a different audience.
server.py offers six freeform tools that dispatch any registered action - the right
shape for an operator driving the whole framework. This one offers a fixed, named
tool per operation, which is what a general chat client and a directory review both
need: every tool says what it does, and nothing here takes a caller-supplied action.

WHAT IS SHARED AND WHAT IS NOT
    shared: bridge (execution, redaction, timeouts), gate (reversibility), protocol
            (the JSON-RPC mechanics) and surface (turning a declaration into a tool
            list, shared with the platform's typed surface).
    not shared: the tool list, the wording, the schemas, the version, and what
                happens to a call.

Neither surface imports the other, and a test asserts it (tests/test_chat_surface.py).
The loop is ~50 duplicated lines, paid deliberately: it is what lets this surface
change transport or protocol version later without touching a server that is already
in use. A seam costs something or it is not a seam.

The gate still runs. Annotations are a hint the spec tells clients to treat as
untrusted, so they are not a control; gate.classify is, and it refuses an
irreversible action outright here rather than offering a confirmed twin. There is no
twin because a curated surface has no business carrying one - a conformance test
asserts every declared tool maps to a reversible action, so adding a destructive one
fails the build instead of quietly growing a second approval path.

Run:  python webplatform/aat_mcp/chat_server.py     (a client spawns this over stdio)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge  # noqa: E402  (sibling module, shared substrate)
import gate  # noqa: E402
import protocol  # noqa: E402  (shared MCP mechanics)
import surface  # noqa: E402  (shared: a declaration -> the tool list a client receives)

SURFACE_PATH = Path(__file__).resolve().parent / "chat_surface.yaml"
DEFAULT_PROTOCOL = protocol.LEGACY_VERSIONS[0]  # what `initialize` gets when it names no version


def load_surface(path: Path = SURFACE_PATH) -> dict:
    """Parse the declaration. Kept a function so tests can load it directly."""
    return surface.load(path)


SURFACE = load_surface()
SERVER_INFO = {"name": "procesio-chat", "version": SURFACE["surface_version"]}
MAX_RESPONSE_BYTES = int((SURFACE.get("limits") or {}).get("max_response_bytes", 60000))


# How a declaration becomes a tool list is the same for every declared surface, so it
# lives in surface.py. The names stay here: this module is where the published surface is
# read from, by its tests and by anything that builds its snapshot.
exposed_name = surface.exposed_name
build_tools = surface.build_tools


TOOLS = build_tools(SURFACE)
_BY_NAME = {s["name"]: s for s in SURFACE["tools"]}


def _log(msg: str) -> None:
    print(f"[procesio-chat] {msg}", file=sys.stderr, flush=True)


_narrowing_hint = surface.narrowing_hint


def _cap(payload: dict, spec: dict) -> dict:
    """Hold a result to the declared size (surface.cap), with this surface's default."""
    return surface.cap(payload, spec, MAX_RESPONSE_BYTES)


def call_tool(name: str, arguments: dict) -> tuple[dict, bool]:
    """Return (payload, is_error). Never raises: a failure comes back as a payload
    the model can read and act on."""
    spec = _BY_NAME.get(name)
    if spec is None:
        return {"error": f"unknown tool: {name}"}, True

    target = spec["target"]
    kind = "tool" if "tool" in target else "agent"
    who = target.get("tool") or target.get("agent")
    action = target.get("action")

    verdict = gate.classify(who, action)
    if not verdict["reversible"]:
        # Unreachable while the conformance test holds. Kept because a gate that only
        # runs when the test is green is not a gate.
        return {"refused": "This operation is irreversible and is not offered on this "
                           "surface.",
                "verb": verdict["verb"], "blast_class": verdict["blast_class"]}, True

    # Exposed names back to CLI flags. Unknown keys are dropped rather than forwarded:
    # this surface's schema is the contract, and passing an undeclared flag through
    # would let a caller reach past it.
    by_exposed = surface.flags_by_exposed_name(SURFACE, spec)
    args = {by_exposed[k]: v for k, v in (arguments or {}).items() if k in by_exposed}

    runner = bridge.run_tool if kind == "tool" else bridge.run_agent
    res = runner(who, action, args)
    if not res.get("ok", False):
        res = dict(res)
        res["hint"] = ("This call failed - it does not mean you lack access. Check the "
                       "arguments against this tool's schema and retry.")
        return res, True
    return _cap(res, spec), False


def handle(req: dict, *, modern: bool = True) -> dict | None:
    """Dispatch one JSON-RPC request; None for a notification.

    Protocol mechanics live in protocol.py, shared with the full surface. What stays here is
    what is this surface's own: the published tool list and the dispatcher behind it."""
    return protocol.handle(req, tools=TOOLS, call_tool=call_tool,
                           server_info=SERVER_INFO, modern=modern)


def main() -> None:
    _log(f"started (stdio). surface {SURFACE['surface_version']}, {len(TOOLS)} tools.")
    protocol.serve_stdio(handle, _log)


if __name__ == "__main__":
    main()
