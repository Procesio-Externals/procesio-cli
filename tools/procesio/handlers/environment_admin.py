"""Environment-management actions (no HTTP - they only touch the local registry).

A PROCESIO environment is one installation, named `<Client>-<ENV>`, carrying the
host URLs it lives on (see environments.py). These actions let a user list the
known environments, add a client-specific one, switch the default (the natural
"I want to work on PROCESIO Internal-QA" gesture), and remove a user-defined one.

Built-in Internal-PROD/QA/DEV always exist and are shared with every teammate;
switching to one needs no setup beyond a credential bound to it.
"""
from __future__ import annotations

import argparse

from tools.procesio import environments, profiles
from tools.procesio.actiondef import ActionDef


def _creds_by_environment() -> dict[str, list[str]]:
    """Credential names grouped by the environment they are bound to (unbound ->
    Internal-PROD), so listings can show which environments are usable."""
    out: dict[str, list[str]] = {}
    for name in profiles.profile_names():
        blob = profiles.get_profile(name)
        env = blob.get("environment") or environments.DEFAULT_ENV_NAME
        out.setdefault(env, []).append(name)
    return out


# -- list-environments ------------------------------------------------------

def list_environments(_args) -> dict:
    default = environments.get_default()
    by_env = _creds_by_environment()
    out = []
    for name in sorted(environments.all_environments()):
        env = environments.get(name)
        out.append({
            "name": name,
            "client": env.get("client"),
            "env": env.get("env"),
            "builtin": bool(env.get("builtin")),
            "is_default": (name == default),
            "web_base": env.get("web_base"),
            "app_base": env.get("app_base"),
            "forms_base": env.get("forms_base"),
            "credentials": by_env.get(name, []),
        })
    return {
        "count": len(out),
        "default_environment": default,
        "environments": out,
    }


# -- add-environment --------------------------------------------------------

def _add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True,
                   help="environment name, '<Client>-<ENV>' e.g. Delgaz-PROD")
    p.add_argument("--web-base", dest="web_base", required=True,
                   help="Web API host, e.g. https://webapi.delgaz.example")
    p.add_argument("--app-base", dest="app_base", required=True,
                   help="designer / front-end host, e.g. https://delgaz.example")
    p.add_argument("--forms-base", dest="forms_base", required=True,
                   help="public forms host, e.g. https://forms.delgaz.example")
    p.add_argument("--auth-base", dest="auth_base",
                   help="legacy auth host (optional; login uses the web host)")
    p.add_argument("--client", help="client label (default: derived from the name)")
    p.add_argument("--env", help="env label e.g. PROD/QA/DEV (default: derived from the name)")
    p.add_argument("--make-default", dest="make_default", action="store_true",
                   help="switch the default environment to this one")


def add_environment(args) -> dict:
    entry = environments.add(
        args.name, web_base=args.web_base, app_base=args.app_base,
        forms_base=args.forms_base, auth_base=args.auth_base,
        client=args.client, env=args.env, make_default=args.make_default,
    )
    return {
        "saved": True,
        "environment": entry,
        "default_environment": environments.get_default(),
        "note": "environments are non-secret host URLs; bind a credential with "
                "add-credential --environment " + entry["name"],
    }


# -- set-environment (switch the default) -----------------------------------

def _name_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="environment name to switch to")


def set_environment(args) -> dict:
    canon = environments.set_default(args.name)
    env = environments.get(canon)
    creds = _creds_by_environment().get(canon, [])
    return {
        "default_environment": canon,
        "web_base": env.get("web_base"),
        "app_base": env.get("app_base"),
        "forms_base": env.get("forms_base"),
        "credentials": creds,
        "note": ("no credential is bound to this environment yet — add one with "
                 f"add-credential --environment {canon}") if not creds else
                (f"using credential '{creds[0]}'" if len(creds) == 1 else
                 "multiple credentials bound — pass --profile to pick one"),
    }


def remove_environment(args) -> dict:
    environments.remove(args.name)
    return {"removed": args.name, "default_environment": environments.get_default()}


def show_environment(args) -> dict:
    env = environments.get(args.name)
    creds = _creds_by_environment().get(env["name"], [])
    return {**env, "is_default": env["name"] == environments.get_default(),
            "credentials": creds}


ACTIONS = {
    "list-environments": ActionDef(
        func=list_environments,
        description="List known PROCESIO environments (URLs, default, bound credentials).",
    ),
    "add-environment": ActionDef(
        func=add_environment, add_args=_add_args,
        description="Add a client environment (<Client>-<ENV> + its host URLs) to the registry.",
    ),
    "set-environment": ActionDef(
        func=set_environment, add_args=_name_arg,
        description="Switch the default environment (e.g. to Internal-QA); persists the choice.",
    ),
    "remove-environment": ActionDef(
        func=remove_environment, add_args=_name_arg,
        description="Remove a user-defined environment (built-in Internal-* cannot be removed).",
    ),
    "show-environment": ActionDef(
        func=show_environment, add_args=_name_arg,
        description="Show one environment's URLs, default flag, and bound credentials.",
    ),
}
