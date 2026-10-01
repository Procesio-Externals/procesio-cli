"""MCP protocol mechanics shared by both surfaces: version negotiation and the 2026-07-28 era.

The two servers publish different tools for different audiences and stay independent of each
other (neither imports the other; tests/test_chat_surface.py asserts it). The protocol they
speak is a different matter. It has one correct behaviour, and keeping a copy of it in each
server is how both came to agree to any protocol version a client asked for, including ones
that do not exist. So the mechanics live here, once. Each server supplies only what is its
own: its tools, its dispatcher and its identity.

MCP's own terms for the two eras:

  legacy  2025-11-25 and earlier. An `initialize` handshake fixes the version for the process.
  modern  2026-07-28. No handshake: every request carries its version in `_meta`, every result
          carries `resultType`, list results carry `ttlMs` and `cacheScope`, and servers MUST
          implement `server/discover`.

A server that speaks both is "dual-era". Both servers are dual-era over stdio, because a
modern-only stdio server would fail every legacy client, and legacy clients have no way to
fall forward.

The HTTP transport calls ``handle(..., modern=False)``. Modern Streamable HTTP adds header
rules (`Mcp-Method`, `Mcp-Name`) that transport does not implement, so it must not advertise
the modern era. Over it, `server/discover` stays a plain method-not-found: that is the answer a
dual-era client reads as "legacy server, fall back". Never answer it with a version-gated
message instead; one public MCP server did, and the client took it as a modern reply and
stopped seeing its tools.

Pure standard library, so either server can import it without widening what it depends on.
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Callable

MODERN_VERSIONS = ("2026-07-28",)
# Newest first. A tools-only server meets every one of these: later revisions only ADD
# optional fields (annotations, title, outputSchema), which earlier clients ignore.
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_TOOLS_DIGEST = "com.procesio/toolsDigest"

PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022

# The tool list cannot change while the process runs: it is built once at import and
# `listChanged` is false. So a long freshness hint is honest, and "public" is too, because
# the list carries no per-user data a shared intermediary should keep to itself.
LIST_TTL_MS = 3_600_000
CACHE_SCOPE = "public"


def negotiate_legacy(requested) -> str:
    """The version to answer `initialize` with: the client's if we serve it, else our newest.

    `initialize` always selects the legacy era, so a client asking for a modern version there
    gets the newest legacy one. That is what a dual-era server is required to do, and it is
    the answer that keeps a client from expecting fields this era never sends."""
    return requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]


def tools_digest(tools) -> str:
    """sha256 over the canonical JSON of a `tools/list` tools array.

    Canonical means keys sorted, no whitespace, UTF-8, non-ASCII left unescaped. A client or
    gateway reproduces it from the list it actually RECEIVED and compares it with the value
    published in server.json, which the MCP Registry does not let anyone change after
    publication. The value a server reports about itself is a convenience for spotting which
    release you are talking to, not a control: the spec says self-reported server information
    must not drive security decisions."""
    raw = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def handle(req: dict, *, tools: list, call_tool: Callable[[str, dict], tuple[dict, bool]],
           server_info: dict, modern: bool = True) -> dict | None:
    """Dispatch one JSON-RPC request. Returns a response, or None for a notification."""
    method = req.get("method") or ""
    req_id = req.get("id")
    is_notification = "id" not in req
    params = req.get("params") if isinstance(req.get("params"), dict) else {}
    meta = params.get("_meta")
    requested = meta.get(META_VERSION) if isinstance(meta, dict) else None
    is_modern = modern and requested is not None

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message, data=None):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": error}

    def complete(result, *, cacheable=False):
        """Modern results carry resultType and the server's identity; lists add cache hints."""
        result = dict(result)
        result["resultType"] = "complete"
        result["_meta"] = {**(result.get("_meta") or {}), META_SERVER_INFO: server_info}
        if cacheable:
            result["ttlMs"] = LIST_TTL_MS
            result["cacheScope"] = CACHE_SCOPE
        return ok(result)

    if method.startswith("notifications/"):
        return None

    if is_modern and requested not in MODERN_VERSIONS:
        if is_notification:
            return None
        # A recognised modern error: it tells a dual-era client this server IS modern, so it
        # retries with a listed version instead of falling back to `initialize`.
        return err(UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
                   {"supported": list(MODERN_VERSIONS), "requested": requested})

    if method == "server/discover":
        if not modern:
            return err(METHOD_NOT_FOUND, f"method not found: {method}")
        return complete({"supportedVersions": list(MODERN_VERSIONS),
                         "capabilities": {"tools": {}},
                         "_meta": {META_TOOLS_DIGEST: tools_digest(tools)}}, cacheable=True)

    if method == "initialize":
        return ok({"protocolVersion": negotiate_legacy(params.get("protocolVersion")),
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": server_info})

    if method == "ping":  # removed in the modern era; harmless to keep answering for legacy
        return ok({})

    if method == "tools/list":
        return complete({"tools": tools}, cacheable=True) if is_modern else ok({"tools": tools})

    if method == "tools/call":
        payload, is_error = call_tool(params.get("name", ""), params.get("arguments") or {})
        result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                  "isError": is_error}
        return complete(result) if is_modern else ok(result)

    if is_notification:
        return None
    return err(METHOD_NOT_FOUND, f"method not found: {method}")


def serve_stdio(handle_fn: Callable[[dict], dict | None], log: Callable[[str], None]) -> None:
    """Newline-delimited JSON-RPC over stdin/stdout. Never raises out of the loop."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - older interpreters; best effort
        pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": PARSE_ERROR, "message": "parse error"}}
        else:
            try:
                resp = handle_fn(req)
            except Exception as e:  # noqa: BLE001
                log(f"handler error: {e}")
                resp = {"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None,
                        "error": {"code": INTERNAL_ERROR, "message": f"internal error: {e}"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
