"""procesio_env dashboard routes — thin wrappers over existing tool actions.

runner.run_tool is monkeypatched to a recorder, so these assert argv construction,
mutation-triggered cache invalidation, error passthrough, and required-field guards
without ever launching a subprocess.
"""
from __future__ import annotations

from dashboard.server import procesio_env as PE


class _Req:
    def __init__(self, body=None):
        self.body = body or {}

    def q(self, name, default=None):
        return default


def _recorder(result):
    calls = []

    def fake_run(tool, argv, timeout=60):
        calls.append({"tool": tool, "argv": argv, "timeout": timeout})
        return result

    return calls, fake_run


def _patch(monkeypatch, result, *, track_invalidate=True):
    calls, fake = _recorder(result)
    monkeypatch.setattr(PE.runner, "run_tool", fake)
    invalidated = []
    monkeypatch.setattr(PE.inventory, "invalidate", lambda: invalidated.append(True))
    return calls, invalidated


_OK = {"ok": True, "data": {"default_environment": "Internal-QA"}, "error": None}
_ERR = {"ok": False, "data": None, "error": {"code": "x", "message": "boom"}}


# -- state (read) -----------------------------------------------------------

def test_state_runs_both_read_actions(monkeypatch):
    calls, _ = _patch(monkeypatch, _OK)
    out = PE.state(_Req())
    argvs = [c["argv"] for c in calls]
    assert ["list-environments"] in argvs
    assert ["list-credentials"] in argvs
    assert out["environments"] == _OK["data"]


def test_state_does_not_invalidate(monkeypatch):
    _, invalidated = _patch(monkeypatch, _OK)
    PE.state(_Req())
    assert invalidated == []  # reads never drop the inventory cache


def test_state_surfaces_errors(monkeypatch):
    _patch(monkeypatch, _ERR)
    out = PE.state(_Req())
    assert out["environments_error"]["message"] == "boom"
    assert out["environments"] is None


# -- set-environment --------------------------------------------------------

def test_set_environment_builds_argv_and_invalidates(monkeypatch):
    calls, invalidated = _patch(monkeypatch, _OK)
    out = PE.set_environment(_Req({"name": "Internal-QA"}))
    assert calls[0]["argv"] == ["set-environment", "--name", "Internal-QA"]
    assert out["ok"] is True
    assert invalidated == [True]  # default moved -> card + probe must re-read


def test_set_environment_requires_name(monkeypatch):
    calls, _ = _patch(monkeypatch, _OK)
    status, body = PE.set_environment(_Req({"name": "  "}))
    assert status == 400 and "name" in body["error"]
    assert calls == []  # never touched the tool


def test_failed_mutation_does_not_invalidate(monkeypatch):
    _, invalidated = _patch(monkeypatch, _ERR)
    out = PE.set_environment(_Req({"name": "Ghost-PROD"}))
    assert out["ok"] is False and out["error"]["message"] == "boom"
    assert invalidated == []


# -- add-environment --------------------------------------------------------

def test_add_environment_full_argv(monkeypatch):
    calls, invalidated = _patch(monkeypatch, _OK)
    PE.add_environment(_Req({
        "name": "Delgaz-PROD", "web_base": "https://w", "app_base": "https://a",
        "forms_base": "https://f", "auth_base": "https://au", "make_default": True,
    }))
    assert calls[0]["argv"] == [
        "add-environment", "--name", "Delgaz-PROD",
        "--web-base", "https://w", "--app-base", "https://a", "--forms-base", "https://f",
        "--auth-base", "https://au", "--make-default"]
    assert invalidated == [True]


def test_add_environment_omits_optional_flags(monkeypatch):
    calls, _ = _patch(monkeypatch, _OK)
    PE.add_environment(_Req({
        "name": "X-PROD", "web_base": "https://w", "app_base": "https://a",
        "forms_base": "https://f"}))
    argv = calls[0]["argv"]
    assert "--auth-base" not in argv and "--make-default" not in argv


def test_add_environment_requires_all_urls(monkeypatch):
    calls, _ = _patch(monkeypatch, _OK)
    status, body = PE.add_environment(_Req({"name": "X-PROD", "web_base": "https://w"}))
    assert status == 400
    assert calls == []


# -- remove-environment / credentials ---------------------------------------

def test_remove_environment_argv(monkeypatch):
    calls, invalidated = _patch(monkeypatch, _OK)
    PE.remove_environment(_Req({"name": "Delgaz-PROD"}))
    assert calls[0]["argv"] == ["remove-environment", "--name", "Delgaz-PROD"]
    assert invalidated == [True]


def test_set_default_credential_uses_set_default(monkeypatch):
    calls, invalidated = _patch(monkeypatch, _OK)
    PE.set_default_credential(_Req({"name": "qa-me"}))
    assert calls[0]["argv"] == ["set-default", "--name", "qa-me"]
    assert invalidated == [True]


def test_remove_credential_uses_remove_credential(monkeypatch):
    calls, _ = _patch(monkeypatch, _OK)
    PE.remove_credential(_Req({"name": "old"}))
    assert calls[0]["argv"] == ["remove-credential", "--name", "old"]


def test_credential_actions_guard_name(monkeypatch):
    calls, _ = _patch(monkeypatch, _OK)
    assert PE.set_default_credential(_Req({}))[0] == 400
    assert PE.remove_credential(_Req({}))[0] == 400
    assert calls == []


# -- routes are wired -------------------------------------------------------

def test_routes_registered():
    from dashboard.server import routes
    assert routes.resolve("GET", "/api/procesio/state") is not None
    assert routes.resolve("POST", "/api/procesio/set-environment") is not None
    assert routes.resolve("POST", "/api/procesio/add-environment") is not None
    assert routes.resolve("POST", "/api/procesio/remove-environment") is not None
    assert routes.resolve("POST", "/api/procesio/set-default-credential") is not None
    assert routes.resolve("POST", "/api/procesio/remove-credential") is not None
