"""Protocol behaviour both MCP surfaces must share: version negotiation and the 2026-07-28 era.

Two eras of MCP coexist. Legacy clients (2025-11-25 and earlier) open with an `initialize`
handshake. Modern clients (2026-07-28) send no handshake at all: every request carries its
protocol version in `_meta`, and servers MUST implement `server/discover`. A server may serve
both, which the spec calls dual-era. A modern-only stdio server would fail every legacy
client, because legacy clients have no way to fall forward, so dual-era is the target here.

What these pin, and why each one matters:

- **A server must never agree to a version it does not implement.** Both servers used to
  echo whatever a client asked for, including `1999-01-01`. Every MCP revision since
  2024-11-05 requires the server to answer with a version IT supports. A client that asks
  for `2026-07-28` inside `initialize` (one Claude Code release briefly did) would have been
  told yes, and would then expect fields the server never sends.
- **Modern results carry `resultType`, and list results carry `ttlMs` and `cacheScope`.**
- **An unsupported modern version gets `-32022` with the list of supported versions.**
  That code is what tells a dual-era client the server is modern and it should retry,
  rather than fall back to `initialize`.
- **The HTTP transport stays legacy-only.** Modern Streamable HTTP adds header rules
  (`Mcp-Method`, `Mcp-Name`) that transport does not implement, so advertising the modern
  era over it would claim more than it does.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

import chat_server
import server

MODERN = "2026-07-28"
LEGACY_LATEST = "2025-11-25"
LEGACY_SUPPORTED = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
DIGEST_KEY = "com.procesio/toolsDigest"
HERE = Path(__file__).resolve().parents[1]

SURFACES = [pytest.param(server, id="full-surface"), pytest.param(chat_server, id="chat-surface")]


def _legacy(method, params=None, id_=1):
    req = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        req["params"] = params
    return req


def _modern(method, params=None, version=MODERN, id_=1):
    p = dict(params or {})
    p["_meta"] = {META_VERSION: version, "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "0"}}
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": p}


# --- 1. version negotiation (the echo bug) --------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("asked", ["1999-01-01", "2099-12-31", MODERN])
def test_initialize_never_agrees_to_a_version_it_does_not_implement(surface, asked):
    got = surface.handle(_legacy("initialize", {"protocolVersion": asked}))["result"]["protocolVersion"]
    assert got != asked, f"agreed to {asked!r}, which this server does not implement over initialize"
    assert got == LEGACY_LATEST


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("asked", LEGACY_SUPPORTED)
def test_initialize_honours_a_legacy_version_it_supports(surface, asked):
    assert surface.handle(_legacy("initialize", {"protocolVersion": asked}))["result"]["protocolVersion"] == asked


@pytest.mark.parametrize("surface", SURFACES)
def test_initialize_with_no_version_gets_the_latest_legacy_one(surface):
    assert surface.handle(_legacy("initialize", {}))["result"]["protocolVersion"] == LEGACY_LATEST


# --- 3. the 2026-07-28 era -------------------------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES)
def test_server_discover_advertises_the_modern_era(surface):
    r = surface.handle(_modern("server/discover"))["result"]
    assert r["resultType"] == "complete"
    assert r["supportedVersions"] == [MODERN]
    assert "tools" in r["capabilities"]
    assert r["_meta"][META_SERVER_INFO]["name"]
    assert r["ttlMs"] > 0 and r["cacheScope"] == "public"


@pytest.mark.parametrize("surface", SURFACES)
def test_a_modern_tool_list_carries_the_required_fields_and_the_same_tools(surface):
    modern = surface.handle(_modern("tools/list"))["result"]
    legacy = surface.handle(_legacy("tools/list"))["result"]
    assert modern["resultType"] == "complete"
    assert modern["ttlMs"] > 0 and modern["cacheScope"] == "public"
    assert modern["_meta"][META_SERVER_INFO]["name"]
    assert modern["tools"] == legacy["tools"], "the two eras must publish one contract"


@pytest.mark.parametrize("surface", SURFACES)
def test_the_legacy_shape_is_unchanged(surface):
    """Legacy clients get exactly what they got before: no modern-only fields."""
    legacy = surface.handle(_legacy("tools/list"))["result"]
    assert set(legacy) == {"tools"}


@pytest.mark.parametrize("surface", SURFACES)
def test_a_modern_tool_call_is_marked_complete(surface):
    r = surface.handle(_modern("tools/call", {"name": "procesio_not_a_tool", "arguments": {}}))["result"]
    assert r["resultType"] == "complete"
    assert r["isError"] is True


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("method", ["tools/list", "server/discover", "tools/call"])
def test_an_unsupported_modern_version_is_refused_with_what_is_supported(surface, method):
    resp = surface.handle(_modern(method, version="2099-01-01"))
    assert resp["error"]["code"] == -32022
    assert resp["error"]["data"] == {"supported": [MODERN], "requested": "2099-01-01"}


@pytest.mark.parametrize("surface", SURFACES)
def test_legacy_server_discover_is_still_method_not_found_when_modern_is_off(surface):
    """A plain -32601 is the answer a dual-era client reads as 'legacy server, fall back'.
    A version-gated message here is what made one public MCP server unusable in Claude Code."""
    resp = surface.handle(_modern("server/discover"), modern=False)
    assert resp["error"]["code"] == -32601


def test_the_http_transport_serves_the_legacy_era_only():
    src = (HERE / "http_server.py").read_text(encoding="utf-8")
    assert re.search(r"server\.handle\(\s*m\s*,\s*modern\s*=\s*False\s*\)", src), (
        "http_server.py must call server.handle(m, modern=False): it does not implement the "
        "Streamable HTTP header rules the modern era requires")


# --- 4. a pinnable digest of the published tool surface -------------------------------------

def _canonical_digest(tools) -> str:
    raw = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_the_digest_is_the_documented_canonical_hash():
    import protocol
    tools = chat_server.TOOLS
    assert protocol.tools_digest(tools) == _canonical_digest(tools)


def test_the_published_snapshot_has_the_digest_the_server_reports():
    """The snapshot ships in the public repo and its digest goes into server.json. A client
    or gateway can therefore hash the tool list it actually received and compare it with a
    value the server cannot change after publication. The self-report is a convenience, not
    the control: the spec says self-reported server info must not drive security decisions."""
    snapshot = json.loads((HERE / "chat_surface.snapshot.json").read_text(encoding="utf-8"))
    reported = chat_server.handle(_modern("server/discover"))["result"]["_meta"][DIGEST_KEY]
    assert reported == _canonical_digest(snapshot)


def test_any_change_to_a_tool_changes_the_digest():
    import protocol
    tools = json.loads(json.dumps(chat_server.TOOLS))
    before = protocol.tools_digest(tools)
    tools[0]["description"] += " "
    assert protocol.tools_digest(tools) != before


def test_the_protocol_module_depends_on_nothing_but_the_standard_library():
    tree = ast.parse((HERE / "protocol.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    assert names <= {"__future__", "hashlib", "json", "sys", "typing", "collections"}, names
