"""The tool surface the platform's assistant is served: generic, typed, or both.

server.py offers a few generic tools that dispatch any registered action. That is right for
the long tail, and costly for the common work: to use an action, a model searches for it,
asks for its arguments, and only then runs it. platform_surface.yaml names the actions the
assistant is measured to call most, and this module publishes each of them as a tool of its
own, with its own argument schema, beside the generic ones.

AAT_MCP_SURFACE chooses what is served:

    generic   the generic tools only. The default, and what was served before this module.
    typed     the named tools only.
    both      the named tools, then the generic ones for everything without a named tool.

WHAT A NAMED CALL ADDS to the generic path it shares (bridge.run_tool / bridge.run_agent,
so turn credentials, the workspace check, timeouts, metrics and the call log are the same):

  - An argument the tool does not declare is an error that lists the valid ones. The model
    has the schema, so a wrong name is a mistake to correct, not something to drop quietly.
  - Every result says `read_only` and `dry_run`. A caller that has to know whether a call
    changed anything reads those, instead of inferring it from the tool's name and the
    layout of its arguments. They are the FIRST two keys of the answer: a caller that
    keeps only the head of a long answer still has them.
  - A result is held to a size (surface.cap), with a hint that names how to ask for less.
  - An irreversible action is refused outright. There is no confirmed twin here: a test
    asserts that nothing declared is irreversible.

This module imports the generic surface (it serves it) and never the public one
(chat_server.py). The two declared surfaces share surface.py and nothing else.

HTTP only: http_server.py serves this module. Over stdio, server.py and chat_server.py are
started on their own, as before.
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge  # noqa: E402  (shared substrate: execution, credentials, timeouts)
import gate  # noqa: E402
import protocol  # noqa: E402  (shared MCP mechanics)
import server  # noqa: E402  (the generic surface, served beside the named tools)
import surface  # noqa: E402  (shared: a declaration -> the tool list a client receives)

SURFACE_PATH = Path(__file__).resolve().parent / "platform_surface.yaml"
SURFACE_ENV = "AAT_MCP_SURFACE"
GENERIC, TYPED, BOTH = "generic", "typed", "both"
MODES = (GENERIC, TYPED, BOTH)


def mode(value: str | None = None) -> str:
    """Which surface to serve. An unset or unknown value is `generic`: a typo in a setting
    must leave the assistant with the tools it had, not with a list nobody chose."""
    raw = os.environ.get(SURFACE_ENV) if value is None else value
    raw = (raw or "").strip().lower()
    return raw if raw in MODES else GENERIC


def load_surface(path: Path = SURFACE_PATH) -> dict:
    """Parse the declaration. Kept a function so tests can load it directly."""
    return surface.load(path)


def _target(spec: dict) -> tuple[str, str, str | None]:
    """(kind, tool or agent name, action) that a declared tool runs."""
    target = spec["target"]
    kind = "tool" if "tool" in target else "agent"
    return kind, target.get("tool") or target.get("agent"), target.get("action")


def _manifest_schema(spec: dict, flag: str) -> dict | None:
    """The JSON Schema the action's manifest publishes for one argument, or None.

    The schema of a structured argument is written once, in the tool that validates
    against it. Copying it into the declaration would give it a second home to drift in."""
    kind, who, action = _target(spec)
    try:
        manifest = (bridge.registry.get_tool(who) if kind == "tool"
                    else bridge.registry.get_agent(who))
        args = manifest.args
        for candidate in manifest.actions or []:
            if candidate.name == action:
                args = candidate.args
                break
        for arg in args or []:
            if arg.name == flag:
                return arg.json_schema
    except Exception:  # noqa: BLE001 - a missing manifest leaves the plain type
        return None
    return None


def resolved(declaration: dict) -> dict:
    """The declaration with every `schema_from_manifest` argument given its schema."""
    out = copy.deepcopy(declaration)
    for spec in out["tools"]:
        for arg in spec.get("args") or []:
            if arg.get("schema_from_manifest"):
                schema = _manifest_schema(spec, arg["flag"])
                if schema:
                    arg["schema"] = schema
    return out


def build_tools(declaration: dict) -> list[dict]:
    """The `tools/list` entries of the named tools."""
    return surface.build_tools(resolved(declaration))


SURFACE = load_surface()
MAX_RESPONSE_BYTES = int((SURFACE.get("limits") or {}).get("max_response_bytes", 24000))
TYPED_TOOLS = build_tools(SURFACE)
_BY_NAME = {s["name"]: s for s in SURFACE["tools"]}


def tools_for(served: str) -> list[dict]:
    """The tool list of one mode. Named tools come first: a model reads the list in order,
    and the named tool is the one to prefer when both can do the work."""
    if served == TYPED:
        return list(TYPED_TOOLS)
    if served == BOTH:
        return list(TYPED_TOOLS) + list(server.TOOLS)
    return list(server.TOOLS)


MODE = mode()
TOOLS = tools_for(MODE)
SERVER_INFO = server.SERVER_INFO


def target_of(name: str) -> tuple[str, str | None] | None:
    """(tool or agent, action) behind a named tool, for a log line. None for any other name."""
    spec = _BY_NAME.get(name)
    if spec is None:
        return None
    _, who, action = _target(spec)
    return who, action


def _valid_args(spec: dict) -> list[dict]:
    required = {surface.exposed_name(a) for a in (spec.get("args") or []) if a.get("required")}
    return [{"name": name, "required": name in required}
            for name in surface.flags_by_exposed_name(SURFACE, spec)]


def _usage_error(spec: dict, message: str, stated: dict) -> tuple[dict, bool]:
    """A call that this module refuses before anything runs: the mistake, and the valid
    arguments beside it, so the next call can be the right one."""
    return {**stated,
            "ok": False,
            "error": {"code": "invalid_argument", "message": message},
            "valid_args": _valid_args(spec),
            "hint": "Nothing ran. Correct the arguments against this tool's schema and call "
                    "it again."}, True


def shape_topics(spec: dict) -> dict:
    """{the name a caller uses: the guidance topic that serves that argument's shape}.

    For an argument whose schema is too large for the tool list (`shape_topic` in the
    declaration). Empty for every other tool."""
    return {surface.exposed_name(a): a["shape_topic"]
            for a in (spec.get("args") or []) if a.get("shape_topic")}


def guidance_tool() -> str | None:
    """The named tool that serves the guidance topics, read from the declaration."""
    for spec in SURFACE["tools"]:
        target = spec["target"]
        if target.get("agent") and target.get("action") == "guidance":
            return spec["name"]
    return None


def _failure_hint(spec: dict) -> str:
    """What a failed call tells the model to do next.

    For most tools the whole contract is in the tool list, so a lookup is a wasted step and
    the hint says so. A tool with a `shape_topic` argument is the exception: the shape of
    that argument is NOT in the tool list, and a hint that sends the model back to the tool
    list leaves it to learn the shape from validation errors, one layer per attempt. There
    the hint names the topic that holds the shape."""
    start = "This call failed - it does not mean you lack access. Read the error"
    shapes = shape_topics(spec)
    if not shapes:
        return (f"{start}, correct the arguments against this tool's schema, and call it "
                "again. The schema is in the tool list: do not look it up.")
    where = "; ".join(f"`{arg}` is the guidance topic {topic}" for arg, topic in shapes.items())
    return (f"{start} and correct the arguments. The shape of {where}. It is not in the tool "
            f"list: if you have not loaded that topic in this conversation, load it now with "
            f"{guidance_tool()}, then call this tool again. Do not guess property names.")


def call_typed(name: str, arguments: dict | None) -> tuple[dict, bool]:
    """Run one named tool. Returns (payload, is_error). Never raises."""
    spec = _BY_NAME[name]
    kind, who, action = _target(spec)
    flags = surface.flags_by_exposed_name(SURFACE, spec)
    arguments = arguments if isinstance(arguments, dict) else {}
    # What the call is, said on every answer (see the module docstring).
    stated = {"read_only": bool(spec["read_only"]),
              "dry_run": bool("dry_run" in flags and arguments.get("dry_run") is True)}

    unknown = sorted(k for k in arguments if k not in flags)
    if unknown:
        return _usage_error(spec, f"{name} has no argument {', '.join(unknown)}", stated)
    missing = [a["name"] for a in _valid_args(spec)
               if a["required"] and arguments.get(a["name"]) in (None, "")]
    if missing:
        return _usage_error(spec, f"{name} needs {', '.join(missing)}", stated)

    verdict = gate.classify(who, action)
    if not verdict["reversible"]:
        # Unreachable while the conformance test holds. Kept because a gate that only
        # runs when the test is green is not a gate.
        bridge.metrics.refusal("irreversible_denied")
        bridge.log_refusal("irreversible_denied", who, action,
                           "an irreversible action was declared on the typed surface")
        return {**stated,
                "refused": "This operation is irreversible and is not offered on this surface.",
                "verb": verdict["verb"], "blast_class": verdict["blast_class"]}, True

    args = {flags[k]: v for k, v in arguments.items()}
    args.update(spec.get("fixed") or {})
    runner = bridge.run_tool if kind == "tool" else bridge.run_agent
    try:
        res = runner(who, action, args)
    except Exception as e:  # noqa: BLE001 - surface as a readable tool error
        return {**stated, "ok": False, "error": f"{type(e).__name__}: {e}"}, True

    if not res.get("ok", False):
        res = {**stated, **res}
        code = (res.get("error") or {}).get("code") if isinstance(res.get("error"), dict) else None
        if code not in server._FINAL_REFUSAL_CODES:
            # A refusal that no retry can fix reaches the model as it is. Anything else gets
            # the one sentence that keeps a model from concluding it has no access.
            res["hint"] = _failure_hint(spec)
        return res, True
    return {**stated, **surface.cap(res, spec, MAX_RESPONSE_BYTES)}, False


def call_tool(name: str, arguments: dict) -> tuple[dict, bool]:
    """Dispatch one `tools/call` for the mode being served."""
    served = MODE
    if served != GENERIC and name in _BY_NAME:
        return call_typed(name, arguments)
    if served != TYPED:
        return server._call_tool(name, arguments)
    return {"error": f"unknown tool: {name}"}, True


def handle(req: dict, *, modern: bool = True) -> dict | None:
    """Dispatch one JSON-RPC request; None for a notification."""
    return protocol.handle(req, tools=TOOLS, call_tool=call_tool,
                           server_info=SERVER_INFO, modern=modern)
