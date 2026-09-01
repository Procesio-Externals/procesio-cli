"""LLM-agnostic verification + setup copilot.

The dashboard cannot call Claude, so every model-backed feature here goes through
the `llm` tool, which is provider-neutral (OpenAI / Azure / local / Anthropic /
Codex CLI - whatever the user configured). Nothing here hardcodes a provider.

Features:
  * provider_test  - ping a provider's credential (llm test-provider)
  * test_tool      - run a tool's live probe, then have the model judge the result
  * test_agent     - run an agent's status/readiness, then a model summary
  * context_inspect- summarize what the context/state store actually contains
  * copilot        - a setup assistant that reads the current state and replies
                     with guidance plus one-click suggested actions
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import registry
from tools._lib import userdata

from . import inventory, runner, validate


def _provider_ready() -> bool:
    return any(p.get("key_present") for p in inventory.providers().get("providers", []))


def _llm(system: str, user: str, *, max_tokens: int = 400) -> tuple[str | None, str | None]:
    """One provider-agnostic completion via the llm tool (default provider)."""
    messages = json.dumps([{"role": "user", "content": user}])
    argv = ["complete", "--system", system, "--messages", messages,
            "--temperature", "0", "--max-tokens", str(max_tokens)]
    r = runner.run_tool("llm", argv, timeout=90)
    if r["ok"]:
        return (r["data"] or {}).get("content"), None
    err = r["error"] or {}
    return None, (err.get("message") or err.get("code") or "llm call failed")


def provider_test(req) -> Any:
    provider = (req.body.get("provider") or "").strip()
    argv = ["test-provider"] + (["--provider", provider] if provider else [])
    r = runner.run_tool("llm", argv, timeout=60)
    if r["ok"]:
        d = r["data"] or {}
        return {"ok": True, "provider": provider or d.get("provider"),
                "model": d.get("model"), "usage": d.get("usage")}
    err = r["error"] or {}
    return {"ok": False, "provider": provider,
            "detail": err.get("message") or err.get("code") or "failed"}


def _tool_entry(name: str) -> dict | None:
    for t in registry.list_tools():
        if t["name"] == name:
            return t
    return None


def test_tool(req) -> Any:
    name = (req.body.get("name") or "").strip()
    entry = _tool_entry(name)
    if entry is None:
        return (404, {"error": "unknown tool"})
    probe = validate.probe("tool:" + name, entry, force=True)
    out = {"name": name, "ok": probe["status"] == "connected",
           "summary": probe["status"], "probe": probe}
    if _provider_ready():
        content, err = _llm(
            "You verify software integrations. Given a tool's live-check result, "
            "say in ONE sentence whether the credential works and what to do if not.",
            f"Tool '{name}'. Live check: {json.dumps(probe)}.", max_tokens=120)
        out["llm"] = content or f"(llm unavailable: {err})"
    else:
        out["llm"] = "configure an LLM provider to get a judged explanation"
    return out


def test_agent(req) -> Any:
    name = (req.body.get("name") or "").strip()
    entry = None
    for a in registry.list_agents():
        if a["name"] == name:
            entry = a
            break
    if entry is None:
        return (404, {"error": "unknown agent"})
    action_names = {a["name"] for a in entry.get("actions", [])}
    detail: Any
    if "status" in action_names:
        r = runner.run_agent(name, ["status"], timeout=90)
        detail = r["data"] if r["ok"] else r["error"]
        ok = r["ok"] and bool(entry.get("ready"))
    else:
        detail = entry.get("tool_status", {})
        ok = bool(entry.get("ready"))
    out = {"name": name, "ok": ok, "ready": entry.get("ready"),
           "summary": "ready" if entry.get("ready") else "not ready",
           "tool_status": entry.get("tool_status", {}), "status": detail}
    if _provider_ready():
        content, err = _llm(
            "You verify multi-tool agents. In ONE sentence, say whether this agent "
            "is ready to run and what is missing if not.",
            f"Agent '{name}'. Ready={entry.get('ready')}. "
            f"Driven tools: {json.dumps(entry.get('tool_status', {}))}.", max_tokens=120)
        out["llm"] = content or f"(llm unavailable: {err})"
    return out


def _sample_titles(limit: int = 15) -> list[str]:
    p = userdata.store_db_path()
    if not p.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
        rows = con.execute(
            "SELECT title FROM records WHERE status='active' "
            "ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return [r[0] for r in rows]
    except sqlite3.Error:
        return []


def context_inspect(req) -> Any:
    stats = inventory.store_stats()
    titles = _sample_titles()
    out = {"stats": stats, "sample_titles": titles}
    if _provider_ready() and (stats or titles):
        content, err = _llm(
            "You summarize a knowledge store. In 2-3 short lines say what the user's "
            "context covers and what looks thin. No preamble.",
            f"Store stats: {json.dumps(stats)}. Recent record titles: {json.dumps(titles)}.",
            max_tokens=200)
        out["summary"] = content or f"(llm unavailable: {err})"
    else:
        out["summary"] = ("Configure an LLM provider for a written summary. "
                          f"Raw: {stats}")
    return out


_COPILOT_SYSTEM = (
    "You are the setup assistant embedded in the Agents-and-Tools dashboard. Help "
    "the user get tools and agents working. Be concise and concrete. You cannot see "
    "or enter secret values yourself - for a credential, direct the user to the "
    "Store button. Reply as STRICT JSON: {\"reply\": \"...\", \"suggestions\": "
    "[{\"action\": one of set_credential|edit_config|test_tool|test_agent|"
    "oauth_login|web_login|bootstrap, \"label\": \"...\", \"data\": {...}}]}. "
    "Keep suggestions to at most 4, each directly relevant. data carries the args "
    "(tool/secret for set_credential; component/name for edit_config; name for "
    "test_tool/test_agent; tool for oauth_login)."
)


def copilot(req) -> Any:
    message = (req.body.get("message") or "").strip()
    if not message:
        return (400, {"error": "message is required"})
    if not _provider_ready():
        return {"reply": "No LLM provider is configured yet. Open the LLM Providers "
                "tab, store a key, and test it - then I can help.", "suggestions": []}
    inv = inventory.build()
    state = {
        "fresh_start": inv["fresh_start"],
        "llm_ready": inv["summary"]["llm_ready"],
        "tools_needing_setup": [t["name"] for t in inv["tools"] if t.get("needs_setup")][:25],
        "agents_needing_setup": [a["name"] for a in inv["agents"] if a.get("needs_setup")][:25],
    }
    content, err = _llm(_COPILOT_SYSTEM,
                        f"Current state: {json.dumps(state)}\n\nUser: {message}",
                        max_tokens=600)
    if content is None:
        return {"reply": f"LLM call failed: {err}", "suggestions": []}
    parsed = runner._parse_json(content)
    if isinstance(parsed, dict) and "reply" in parsed:
        parsed.setdefault("suggestions", [])
        return parsed
    return {"reply": content, "suggestions": []}
