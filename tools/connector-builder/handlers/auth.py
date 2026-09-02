"""Auth / identity actions: connectivity, current user, API-key + LLM-key mgmt."""
from __future__ import annotations

import argparse

from actiondef import ActionDef


def check(client, args) -> dict:
    """Connectivity + auth probe via GET /auth/me."""
    me = client.get("/auth/me")
    return {"ok": True, "email": me.get("email"), "role": me.get("role"),
            "has_llm_key": me.get("has_llm_key"), "base_url": client.base_url}


def whoami(client, args) -> dict:
    """Full GET /auth/me for the authenticated principal."""
    return client.get("/auth/me")


def list_api_keys(client, args) -> dict:
    keys = client.get("/auth/api-keys")
    return {"api_keys": keys, "count": len(keys) if isinstance(keys, list) else None}


def create_api_key(client, args) -> dict:
    """POST /auth/api-keys — returns full_key ONCE (store it immediately)."""
    return client.post("/auth/api-keys", {"name": args.name})


def revoke_api_key(client, args) -> dict:
    return client.delete(f"/auth/api-keys/{args.id}")


def set_llm_key(client, args) -> dict:
    """POST /auth/llm-key — set the LLM provider key used to power builds."""
    return client.post("/auth/llm-key",
                       {"api_key": args.api_key, "provider": args.provider})


def delete_llm_key(client, args) -> dict:
    return client.delete("/auth/llm-key")


def _create_api_key_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="Label for the new API key")


def _revoke_api_key_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", required=True, help="API key id to revoke")


def _set_llm_key_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--api-key", dest="api_key", required=True,
                   help="LLM provider API key (e.g. sk-ant-... / sk-...)")
    p.add_argument("--provider", required=True,
                   help="Provider id, e.g. anthropic | openai")


ACTIONS: dict[str, ActionDef] = {
    "check": ActionDef(check, description="Connectivity + auth probe (GET /auth/me)."),
    "whoami": ActionDef(whoami, description="Full current-user record (GET /auth/me)."),
    "list-api-keys": ActionDef(list_api_keys, description="List your API keys."),
    "create-api-key": ActionDef(
        create_api_key, _create_api_key_args,
        description="Create an API key (full_key shown only once)."),
    "revoke-api-key": ActionDef(
        revoke_api_key, _revoke_api_key_args, description="Revoke an API key by id."),
    "set-llm-key": ActionDef(
        set_llm_key, _set_llm_key_args,
        description="Set the LLM provider key that powers builds."),
    "delete-llm-key": ActionDef(
        delete_llm_key, description="Remove the stored LLM provider key."),
}
