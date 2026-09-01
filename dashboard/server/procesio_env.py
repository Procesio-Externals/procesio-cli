"""PROCESIO environments panel — dashboard routes.

Every operation is a thin wrapper over an EXISTING procesio tool action run through
`runner.run_tool` (the same subprocess bridge every other setup action uses). The
dashboard never reimplements the environment logic, credential handling, or URL
validation — the tool remains the single source of truth, so this stays trivial to
maintain: add an action to the tool and it shows up here for free.

Read:   list-environments, list-credentials
Write:  set-environment, add-environment, remove-environment  (environments)
        set-default, remove-credential                        (credentials)
"""
from __future__ import annotations

from typing import Any

from . import inventory, runner

TOOL = "procesio"


def _run(argv: list[str], *, mutating: bool) -> dict[str, Any]:
    """Run a procesio action and shape a uniform {ok, data, error}. On a successful
    mutation, drop the inventory cache so the card (and its env-aware health probe)
    re-reads on the next poll."""
    res = runner.run_tool(TOOL, argv, timeout=90)
    if mutating and res["ok"]:
        inventory.invalidate()
    return {"ok": res["ok"], "data": res.get("data"), "error": res.get("error")}


def _name(req) -> str:
    return (req.body.get("name") or "").strip()


# -- read -------------------------------------------------------------------

def state(req) -> Any:
    """Everything the panel needs in one round-trip: the environment registry
    (built-ins + user, the default, bound credentials) and the credential profiles
    (names/types/workspaces/environment binding — never a secret value)."""
    envs = _run(["list-environments"], mutating=False)
    creds = _run(["list-credentials"], mutating=False)
    return {
        "environments": envs["data"],
        "environments_error": envs["error"],
        "credentials": creds["data"],
        "credentials_error": creds["error"],
    }


# -- environments -----------------------------------------------------------

def set_environment(req) -> Any:
    if not _name(req):
        return (400, {"error": "name is required"})
    return _run(["set-environment", "--name", _name(req)], mutating=True)


def add_environment(req) -> Any:
    b = req.body or {}
    name = (b.get("name") or "").strip()
    web = (b.get("web_base") or "").strip()
    app = (b.get("app_base") or "").strip()
    forms = (b.get("forms_base") or "").strip()
    if not (name and web and app and forms):
        return (400, {"error": "name, web_base, app_base and forms_base are all required"})
    argv = ["add-environment", "--name", name,
            "--web-base", web, "--app-base", app, "--forms-base", forms]
    if (b.get("auth_base") or "").strip():
        argv += ["--auth-base", b["auth_base"].strip()]
    if b.get("make_default"):
        argv += ["--make-default"]
    return _run(argv, mutating=True)


def remove_environment(req) -> Any:
    if not _name(req):
        return (400, {"error": "name is required"})
    return _run(["remove-environment", "--name", _name(req)], mutating=True)


# -- credentials (existing profile actions; no secrets pass through here) ----

def set_default_credential(req) -> Any:
    if not _name(req):
        return (400, {"error": "name is required"})
    return _run(["set-default", "--name", _name(req)], mutating=True)


def remove_credential(req) -> Any:
    if not _name(req):
        return (400, {"error": "name is required"})
    return _run(["remove-credential", "--name", _name(req)], mutating=True)
