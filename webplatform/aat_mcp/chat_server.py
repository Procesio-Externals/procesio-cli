"""procesio-chat: the PUBLISHED MCP surface, built from chat_surface.yaml.

A second surface over the same substrate as server.py, for a different audience.
server.py offers six freeform tools that dispatch any registered action - the right
shape for an operator driving the whole framework. This one offers a fixed, named
tool per operation, which is what a general chat client and a directory review both
need: every tool says what it does, and nothing here takes a caller-supplied action.

WHAT IS SHARED AND WHAT IS NOT
    shared: bridge (execution, redaction, timeouts) and gate (reversibility).
    not shared: the tool list, the wording, the schemas, the version - and the
                JSON-RPC loop below.

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

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge  # noqa: E402  (sibling module, shared substrate)
import gate  # noqa: E402

import yaml  # noqa: E402

SURFACE_PATH = Path(__file__).resolve().parent / "chat_surface.yaml"
DEFAULT_PROTOCOL = "2024-11-05"


def load_surface(path: Path = SURFACE_PATH) -> dict:
    """Parse the declaration. Kept a function so tests can load it directly."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


SURFACE = load_surface()
SERVER_INFO = {"name": "procesio-chat", "version": SURFACE["surface_version"]}
MAX_RESPONSE_BYTES = int((SURFACE.get("limits") or {}).get("max_response_bytes", 60000))


def exposed_name(arg: dict) -> str:
    """The name a caller uses. CLI flags are kebab-case; a model reaches for
    snake_case and gets it wrong the other way round, so the mapping is explicit
    rather than left to whoever is calling."""
    return arg.get("expose") or arg["flag"].replace("-", "_")


def _arg_schema(arg: dict) -> dict:
    return {"type": arg.get("type", "string"), "description": arg.get("description", "")}


def build_tools(surface: dict) -> list[dict]:
    """Turn the declaration into the exact `tools/list` payload.

    Pure: same declaration in, same bytes out. That is what lets the snapshot test
    treat the published contract as reviewable in a diff."""
    common = surface.get("common_args") or {}
    tools = []
    for spec in surface["tools"]:
        props: dict = {}
        required: list[str] = []
        for arg in spec.get("args") or []:
            props[exposed_name(arg)] = _arg_schema(arg)
            if arg.get("required"):
                required.append(exposed_name(arg))
        for key in spec.get("common") or []:
            decl = dict(common[key])
            props[key] = _arg_schema(decl)

        read_only = bool(spec["read_only"])
        title = spec["title"]
        schema: dict = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        tools.append({
            "name": spec["name"],
            "title": title,
            "description": " ".join(spec["description"].split()),
            "inputSchema": schema,
            "annotations": {
                "title": title,
                "readOnlyHint": read_only,
                "destructiveHint": False,   # every declared action is reversible; enforced in CI
                "idempotentHint": read_only,
                "openWorldHint": True,      # all of these reach the PROCESIO platform
            },
        })
    return tools


TOOLS = build_tools(SURFACE)
_BY_NAME = {s["name"]: s for s in SURFACE["tools"]}


def _log(msg: str) -> None:
    print(f"[procesio-chat] {msg}", file=sys.stderr, flush=True)


def _narrowing_hint(spec: dict) -> str:
    """Name the arguments this particular tool offers for asking a smaller question.
    A generic 'response too large' tells a model nothing it can act on."""
    names = [exposed_name(a) for a in (spec.get("args") or [])]
    useful = [n for n in names if n in ("search", "page", "page_size", "actions")]
    if useful:
        return f"Ask a narrower question using: {', '.join(useful)}."
    return "Request a single item by id instead of a listing."


def _cap(payload: dict, spec: dict) -> dict:
    """Hold a result to the declared size. A tool result lands directly in a model's
    context, so an unbounded one spends context that the task needed."""
    limit = int(spec.get("max_response_bytes") or MAX_RESPONSE_BYTES)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= limit:
        return payload
    return {
        "truncated": True,
        "bytes": len(text),
        "max_response_bytes": limit,
        "hint": f"The result was {len(text)} bytes, over the {limit}-byte cap for this "
                f"surface, so it is not returned in full. {_narrowing_hint(spec)}",
        "preview": text[:2000],
    }


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
    by_exposed = {exposed_name(a): a["flag"] for a in (spec.get("args") or [])}
    for key in spec.get("common") or []:
        by_exposed[key] = (SURFACE["common_args"][key])["flag"]
    args = {by_exposed[k]: v for k, v in (arguments or {}).items() if k in by_exposed}

    runner = bridge.run_tool if kind == "tool" else bridge.run_agent
    res = runner(who, action, args)
    if not res.get("ok", False):
        res = dict(res)
        res["hint"] = ("This call failed - it does not mean you lack access. Check the "
                       "arguments against this tool's schema and retry.")
        return res, True
    return _cap(res, spec), False


def handle(req: dict) -> dict | None:
    """Dispatch one JSON-RPC request; None for a notification."""
    method = req.get("method")
    req_id = req.get("id")
    is_notification = "id" not in req

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    if method == "initialize":
        params = req.get("params") or {}
        return ok({"protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": SERVER_INFO})
    if (method or "").startswith("notifications/"):
        return None
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        payload, is_error = call_tool(params.get("name", ""), params.get("arguments") or {})
        return ok({"content": [{"type": "text",
                                "text": json.dumps(payload, ensure_ascii=False)}],
                   "isError": is_error})
    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - older interpreters; best effort
        pass
    _log(f"started (stdio). surface {SURFACE['surface_version']}, {len(TOOLS)} tools.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700,
                                                   "message": "parse error"}}) + "\n")
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
