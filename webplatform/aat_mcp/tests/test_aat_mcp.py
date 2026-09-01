"""Tests for the aat-mcp bridge + stdio JSON-RPC server + reversibility gate.

Protocol dispatch, the reversibility gate, and the anti-thrash argv guarantee are
tested with fakes - no real subprocess, no credential access.
"""
from __future__ import annotations

import json

import bridge
import gate
import server


def _call(name, arguments, _id=1):
    return server.handle({"jsonrpc": "2.0", "id": _id, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})


# --- protocol dispatch ---------------------------------------------------

def test_initialize_echoes_protocol_and_serverinfo():
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "aat-mcp"
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in resp["result"]["capabilities"]


def test_initialize_defaults_protocol_when_absent():
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {}})
    assert resp["result"]["protocolVersion"] == server.DEFAULT_PROTOCOL


def test_notifications_get_no_response():
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None


def test_ping():
    assert server.handle({"jsonrpc": "2.0", "id": 7, "method": "ping"})["result"] == {}


def test_tools_list_exposes_the_six_tools():
    resp = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"capabilities", "run_tool", "run_tool_confirmed",
                     "run_agent", "run_agent_confirmed", "get_skill"}
    assert all("inputSchema" in t for t in resp["result"]["tools"])


def test_unknown_method_is_jsonrpc_error():
    resp = server.handle({"jsonrpc": "2.0", "id": 9, "method": "does/not/exist"})
    assert resp["error"]["code"] == -32601


def test_unknown_notification_is_swallowed():
    assert server.handle({"jsonrpc": "2.0", "method": "does/not/exist"}) is None


# --- reversibility gate --------------------------------------------------

def test_reversible_action_runs_on_plain_tool(monkeypatch):
    called = {}
    monkeypatch.setattr(server.bridge, "run_tool",
                        lambda t, a, args: called.update(t=t, a=a) or
                        {"ok": True, "data": {"x": 1}, "error": None})
    resp = _call("run_tool", {"tool": "google-mail", "action": "list-messages"})
    assert resp["result"]["isError"] is False
    assert called == {"t": "google-mail", "a": "list-messages"}


def test_irreversible_action_refused_on_plain_tool(monkeypatch):
    # bridge.run_tool must NOT be called - the gate refuses before execution.
    monkeypatch.setattr(server.bridge, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    resp = _call("run_tool", {"tool": "google-mail", "action": "send-message",
                              "args": {"to": "a@example.com"}})
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert "approval_required" in payload
    assert payload["approval_required"]["verb"] == "send"
    assert payload["approval_required"]["blast_class"] == "message-sent"
    assert "run_tool_confirmed" in payload["approval_required"]["next"]


def test_irreversible_action_runs_on_confirmed_tool(monkeypatch):
    called = {}
    monkeypatch.setattr(server.bridge, "run_tool",
                        lambda t, a, args: called.update(t=t, a=a, args=args) or
                        {"ok": True, "data": {"id": "m1"}, "error": None})
    resp = _call("run_tool_confirmed", {"tool": "google-mail", "action": "send-message",
                                        "args": {"to": "a@example.com"}})
    assert resp["result"]["isError"] is False
    assert called["t"] == "google-mail" and called["a"] == "send-message"


def test_confirmed_denied_when_headless_env_set(monkeypatch):
    monkeypatch.setattr(gate, "deny_irreversible_env", lambda: True)
    monkeypatch.setattr(server.bridge, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    resp = _call("run_tool_confirmed", {"tool": "google-mail", "action": "send-message"})
    assert resp["result"]["isError"] is True
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert "refused" in payload


def test_agent_intake_is_reversible_and_runs(monkeypatch):
    called = {}
    monkeypatch.setattr(server.bridge, "run_agent",
                        lambda ag, a, args: called.update(ag=ag, a=a) or
                        {"ok": True, "data": {}, "error": None})
    resp = _call("run_agent", {"agent": "orchestrator", "action": "intake",
                               "args": {"request": "collect invoices"}})
    assert resp["result"]["isError"] is False
    assert called == {"ag": "orchestrator", "a": "intake"}


def test_run_tool_requires_tool_arg():
    resp = _call("run_tool", {})
    assert resp["result"]["isError"] is True


def test_call_unknown_tool_is_error():
    resp = _call("nope", {})
    assert resp["result"]["isError"] is True


def test_get_skill_keyerror_becomes_readable_error(monkeypatch):
    def boom(name):
        raise KeyError("skill not found: ghost")
    monkeypatch.setattr(server.bridge, "get_skill", boom)
    resp = _call("get_skill", {"name": "ghost"})
    assert resp["result"]["isError"] is True
    assert "ghost" in resp["result"]["content"][0]["text"]


# --- gate classifier -----------------------------------------------------

def test_gate_classify_verbs():
    assert gate.classify("google-mail", "send-message")["reversible"] is False
    assert gate.classify("whatsapp-personal", "delete-messages")["reversible"] is False
    assert gate.classify("fgo", "issue-invoice")["reversible"] is False
    assert gate.classify("google-mail", "list-messages")["reversible"] is True
    assert gate.classify("apollo", "search-people")["reversible"] is True
    assert gate.classify("hello-world", None)["reversible"] is True


def test_gate_ignores_arg_values_only_action_and_name():
    # The gate classifies on name + action, never arg values - so a subject line
    # that contains "send" does not trip it (that is the caller's job to pass action).
    assert gate.classify("google-mail", "create-draft")["reversible"] is True


# --- the anti-thrash guarantee ------------------------------------------

def test_bridge_encodes_json_args_as_single_argv_element(monkeypatch):
    seen = {}

    def fake_run_tool(tool, argv, **k):
        seen.update(tool=tool, argv=argv)
        return {"ok": True, "data": {}, "error": None}

    monkeypatch.setattr(bridge.runner, "run_tool", fake_run_tool)
    bridge.run_tool("google-mail", "send-message",
                    {"to": "a@example.com", "cc": ["x@example.com", "z@example.com"]})
    assert seen["argv"][0] == "send-message"
    i = seen["argv"].index("--cc")
    assert json.loads(seen["argv"][i + 1]) == ["x@example.com", "z@example.com"]


def test_bridge_omits_action_for_flat_tool(monkeypatch):
    seen = {}
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: seen.update(argv=argv) or
                        {"ok": True, "data": {}, "error": None})
    bridge.run_tool("hello-world", None, {"name": "Z"})
    assert seen["argv"] == ["--name", "Z"]


# --- host-only delegation (host-side tool-runner) ------------------------

def test_is_host_only_detects_listed_vs_plain():
    assert bridge._is_host_only("tool", "web") is True    # listed: drives a real browser profile
    assert bridge._is_host_only("tool", "xlsx") is False  # neither listed nor web_session


def test_run_tool_delegates_host_only_when_runner_set(monkeypatch):
    seen = {}
    monkeypatch.setenv("AAT_HOST_RUNNER_URL", "http://host.docker.internal:8904")
    monkeypatch.setattr(bridge, "_delegate",
                        lambda kind, name, action, args: seen.update(kind=kind, name=name) or
                        {"ok": True, "data": {"delegated": True}})
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran locally!")))
    r = bridge.run_tool("web", "get-text", {"url": "https://example.com"})
    assert r["data"]["delegated"] is True
    assert seen == {"kind": "tool", "name": "web"}


def test_run_tool_runs_locally_when_not_host_only(monkeypatch):
    monkeypatch.setenv("AAT_HOST_RUNNER_URL", "http://host.docker.internal:8904")
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: {"ok": True, "data": {"local": tool}})
    monkeypatch.setattr(bridge, "_delegate",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("delegated!")))
    assert bridge.run_tool("hello-world", None, {"name": "X"})["data"]["local"] == "hello-world"


def test_no_delegation_without_runner_url(monkeypatch):
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: {"ok": True, "data": {"local": True}})
    # a host-only tool still runs locally when no host-runner is configured (local platform)
    assert bridge.run_tool("whatsapp-personal", "list-chats", {})["data"]["local"] is True
