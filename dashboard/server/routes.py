"""Central route wiring. One place maps URL -> handler function.

Handlers take a `Req` and return either a JSON-able object (200) or a
(status, object) tuple. SSE routes (validate/all) are handled directly in
handler.py. Later-milestone route modules are wired only when their file exists,
so a not-yet-built module never blocks the ones already present - but a real
import error inside an existing module still surfaces.
"""
from __future__ import annotations

import importlib.util
from typing import Callable

_GET: dict[str, Callable] = {}
_POST: dict[str, Callable] = {}


def resolve(method: str, path: str):
    return (_GET if method == "GET" else _POST).get(path)


def _exists(mod: str) -> bool:
    return importlib.util.find_spec(f"dashboard.server.{mod}") is not None


def _wire():
    from . import inventory, validate

    _GET["/api/health"] = lambda req: {"ok": True}
    _GET["/api/inventory"] = lambda req: inventory.build(
        force=req.q("force") in ("1", "true", "yes"))
    _POST["/api/validate/one"] = validate.validate_one_route

    if _exists("setup"):
        from . import setup
        _POST["/api/credential/set"] = setup.credential_set
        _POST["/api/credential/delete"] = setup.credential_delete
        _GET["/api/credential/check"] = setup.credential_check
        _POST["/api/bootstrap"] = setup.bootstrap
        _GET["/api/config/list"] = setup.config_list
        _GET["/api/config/get"] = setup.config_get
        _POST["/api/config/validate"] = setup.config_validate
        _POST["/api/config/set"] = setup.config_set
        _POST["/api/session/start"] = setup.session_start
        _POST["/api/session/commit"] = setup.session_commit
        _POST["/api/oauth/start"] = setup.oauth_start
        _GET["/api/job/get"] = setup.job_get

    if _exists("google"):
        from . import google
        _GET["/api/google/accounts"] = google.accounts
        _GET["/api/google/email"] = google.email
        _POST["/api/google/login"] = google.login
        _POST["/api/google/remove"] = google.remove

    if _exists("procesio_env"):
        from . import procesio_env
        _GET["/api/procesio/state"] = procesio_env.state
        _POST["/api/procesio/set-environment"] = procesio_env.set_environment
        _POST["/api/procesio/add-environment"] = procesio_env.add_environment
        _POST["/api/procesio/remove-environment"] = procesio_env.remove_environment
        _POST["/api/procesio/set-default-credential"] = procesio_env.set_default_credential
        _POST["/api/procesio/remove-credential"] = procesio_env.remove_credential

    if _exists("llmtest"):
        from . import llmtest
        _POST["/api/llm/provider/test"] = llmtest.provider_test
        _POST["/api/test/tool"] = llmtest.test_tool
        _POST["/api/test/agent"] = llmtest.test_agent
        _GET["/api/context/inspect"] = llmtest.context_inspect
        _POST["/api/copilot"] = llmtest.copilot


_wire()
