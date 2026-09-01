"""Profile-management actions (no HTTP - they only touch Credential Manager).

These let the user keep MANY credentials: several API keys (one per workspace)
and one or more username/password accounts, switching between them with
--profile or a stored default.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from tools.procesio import environments, profiles
from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError


# -- add-credential ---------------------------------------------------------

def _add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="profile name, e.g. 'personal'")
    p.add_argument("--type", required=True, choices=["apikey", "userpass"])
    # apikey fields
    p.add_argument("--key", help="apikey: the key NAME header value (omit to be prompted without echoing)")
    p.add_argument("--value", help="apikey: the key VALUE header value (omit to be prompted without echoing)")
    p.add_argument("--workspace-id", dest="workspace_id",
                   help="apikey: workspace GUID (sent as the workspaceid header)")
    p.add_argument("--workspace", help="apikey: a human label for the workspace")
    # userpass fields
    p.add_argument("--username", help="userpass: account email/username")
    p.add_argument("--password", help="userpass: account password (omit to be prompted without echoing)")
    p.add_argument("--realm", help="userpass: override realm (default procesio01)")
    p.add_argument("--client-id", dest="client_id",
                   help="userpass: override client_id (default procesio-ui)")
    # environment binding: which PROCESIO installation this credential authenticates
    # against. Its host URLs come from that environment; unbound == Internal-PROD.
    p.add_argument("--environment", dest="environment",
                   help="bind this credential to an environment, e.g. Internal-QA "
                        "(default: Internal-PROD). Add a client env first with add-environment.")
    # shared optional base overrides (rare — normally the environment supplies these)
    p.add_argument("--web-base", dest="web_base", help="override Web API base URL")
    p.add_argument("--auth-base", dest="auth_base", help="override Proxy API base URL")
    p.add_argument("--make-default", action="store_true",
                   help="set this profile as the default")


def _secret_arg(value, label: str, flag: str):
    """Return the secret, prompting for it when the flag was omitted.

    Passing a key/token/password as a CLI flag leaks it into shell history and into
    every process listing on the box, which defeats the point of storing it in the OS
    credential manager. So the flags stay OPTIONAL and an interactive terminal is
    prompted via getpass (never echoed) — same contract as scripts/set-credential.py.
    Non-interactive callers (CI, another tool) still pass the flag and are unaffected;
    only a non-interactive caller that ALSO omits the flag gets the usage error.

    The usage error names AAT_RUNNER_DIRECT because the common way to hit it is NOT
    being non-interactive: run-tool routes tools through the persistent runner by
    default, so the tool executes inside a daemon worker with no TTY and the prompt
    is unreachable even for a human at a real console. "Run interactively" alone is
    unactionable advice for someone who already is.
    """
    if value:
        return value
    if not sys.stdin.isatty():
        raise UsageError(f"{label} is required: pass {flag}, or re-run with the "
                         f"runner bypassed so it can prompt without echoing "
                         f"(PowerShell: $env:AAT_RUNNER_DIRECT=1)")
    entered = getpass.getpass(f"{label}: ").strip()
    if not entered:
        raise UsageError(f"{label} cannot be empty")
    return entered


def add_credential(args) -> dict:
    blob: dict = {"type": args.type}
    if args.type == "apikey":
        blob["key"] = _secret_arg(args.key, "API key NAME", "--key")
        blob["value"] = _secret_arg(args.value, "API key VALUE", "--value")
        if args.workspace_id:
            blob["workspace_id"] = args.workspace_id
        if args.workspace:
            blob["workspace"] = args.workspace
    else:  # userpass
        if not args.username:
            raise UsageError("userpass profiles need --username")
        blob["username"] = args.username
        blob["password"] = _secret_arg(args.password, "password", "--password")
        if args.realm:
            blob["realm"] = args.realm
        if args.client_id:
            blob["client_id"] = args.client_id
    if getattr(args, "environment", None):
        canon = environments.canonical_name(args.environment)
        if not canon:
            raise UsageError(
                f"unknown environment '{args.environment}'. "
                f"Known: {', '.join(sorted(environments.all_environments()))}. "
                f"Add a client environment first with: run-tool procesio add-environment ..."
            )
        blob["environment"] = canon
    for opt in ("web_base", "auth_base"):
        if getattr(args, opt):
            blob[opt] = getattr(args, opt)
    profiles.save_profile(args.name, blob)
    if args.make_default:
        profiles.set_default(args.name)
    return {
        "saved": True,
        "profile": profiles.public_view(blob, args.name),
        "environment": blob.get("environment", environments.DEFAULT_ENV_NAME),
        "default": profiles.get_default(),
        "note": "secret values stored in Windows Credential Manager, never on disk",
    }


# -- list-credentials -------------------------------------------------------

def list_credentials(_args) -> dict:
    default = profiles.get_default()
    out = []
    for name in profiles.profile_names():
        blob = profiles.get_profile(name)
        view = profiles.public_view(blob, name)
        view["is_default"] = (name == default)
        # An unbound credential belongs to Internal-PROD (backward-compatible).
        view["environment"] = blob.get("environment") or environments.DEFAULT_ENV_NAME
        out.append(view)
    return {
        "count": len(out),
        "default": default,
        "default_environment": environments.get_default(),
        "profiles": out,
    }


# -- set-default ------------------------------------------------------------

def _name_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="profile name")


def set_default(args) -> dict:
    profiles.set_default(args.name)
    return {"default": args.name}


def remove_credential(args) -> dict:
    profiles.remove_profile(args.name)
    return {"removed": args.name, "default": profiles.get_default(),
            "remaining": profiles.profile_names()}


def show_credential(args) -> dict:
    """Non-secret view of one profile (secret fields shown only as has_*)."""
    blob = profiles.get_profile(args.name)
    return profiles.public_view(blob, args.name)


ACTIONS = {
    "add-credential": ActionDef(
        func=add_credential, add_args=_add_args,
        description="Store a new credential profile (apikey or userpass) in Credential Manager.",
    ),
    "list-credentials": ActionDef(
        func=list_credentials,
        description="List stored credential profiles (names/types/workspaces only - no secrets).",
    ),
    "set-default": ActionDef(
        func=set_default, add_args=_name_arg,
        description="Set the default profile used when --profile is omitted.",
    ),
    "remove-credential": ActionDef(
        func=remove_credential, add_args=_name_arg,
        description="Delete a credential profile and its cached token.",
    ),
    "show-credential": ActionDef(
        func=show_credential, add_args=_name_arg,
        description="Show one profile's non-secret fields (secrets shown only as has_*).",
    ),
}
