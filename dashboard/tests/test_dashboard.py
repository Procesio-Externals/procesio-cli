"""Dashboard tests - hermetic units + one in-process server smoke.

Network/subprocess-touching pieces (validation probes, credential writes) are
monkeypatched so the suite is fast and side-effect free.
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from dashboard.server import (config_schemas, google, handler, inventory,
                              routes, security, setup, validate)


class _Req:
    def __init__(self, body=None, query=None):
        self.body = body or {}
        self._q = query or {}

    def q(self, name, default=None):
        return self._q.get(name, default)


# ---- config_schemas -----------------------------------------------------
def test_llm_schema_rejects_bad_adapter():
    v = config_schemas.validate("llm", "providers",
                                {"providers": {"x": {"adapter": "nope"}}})
    assert not v["ok"]
    assert any("adapter" in e for e in v["errors"])


def test_llm_schema_default_must_exist():
    v = config_schemas.validate("llm", "providers", {
        "providers": {"openai": {"adapter": "openai_compat"}}, "default": "ghost"})
    assert not v["ok"]
    assert any("default" in e for e in v["errors"])


def test_llm_schema_accepts_good():
    v = config_schemas.validate("llm", "providers", {
        "providers": {"openai": {"adapter": "openai_compat", "model": "gpt-4o"}},
        "default": "openai"})
    assert v["ok"] and not v["warnings"]


def test_placeholder_is_a_warning_not_error():
    v = config_schemas.validate("anything", "cfg", {"host": "YOUR-HOST"})
    assert v["ok"]
    assert any("placeholder" in w for w in v["warnings"])


def test_non_object_config_rejected():
    v = config_schemas.validate("x", "y", [1, 2, 3])
    assert not v["ok"]


# ---- secret namespace resolution ---------------------------------------
def test_namespaced_secret_resolves_to_namespace():
    assert setup._resolve_secret("google-mail", "google:oauth-client") == (
        "google", "oauth-client")
    assert setup._resolve_secret("ryver", "token") == ("ryver", "token")


# ---- validation interpretation (monkeypatched runner) -------------------
def test_probe_skips_when_secret_missing():
    entry = {"name": "t", "missing_secrets": ["token"], "actions": []}
    res = validate.probe("tool:t", entry, force=True)
    assert res["status"] == "unknown" and "credentials not set" in res["detail"]


def test_probe_connected_on_healthcheck_ok(monkeypatch):
    monkeypatch.setattr(validate.runner, "run_tool",
                        lambda *a, **k: {"ok": True, "data": {"count": 3}, "error": None})
    entry = {"name": "t", "missing_secrets": [],
             "healthcheck": {"action": "ping", "args": {}}, "actions": []}
    res = validate.probe("tool:t", entry, force=True)
    assert res["status"] == "connected"


def test_probe_invalid_on_authstatus_not_ready(monkeypatch):
    monkeypatch.setattr(validate.runner, "run_tool",
                        lambda *a, **k: {"ok": True, "data": {"ready": False}, "error": None})
    entry = {"name": "t", "missing_secrets": [], "healthcheck": None,
             "actions": [{"name": "auth-status"}]}
    res = validate.probe("tool:t", entry, force=True)
    assert res["status"] == "invalid"


def test_probe_invalid_on_error(monkeypatch):
    monkeypatch.setattr(validate.runner, "run_tool",
                        lambda *a, **k: {"ok": False, "data": None,
                                         "error": {"code": "x", "message": "bad key"}})
    entry = {"name": "t", "missing_secrets": [], "healthcheck": {"action": "ping"},
             "actions": []}
    res = validate.probe("tool:t", entry, force=True)
    assert res["status"] == "invalid" and "bad key" in res["detail"]


# ---- google multi-account -----------------------------------------------
def test_google_label_validation():
    assert google._valid_label("personal")
    assert google._valid_label("work-2")
    assert not google._valid_label("bad@email")
    assert not google._valid_label("UPPER")
    assert not google._valid_label("")


def test_google_login_builds_account_argv(monkeypatch):
    captured = {}

    class FakeJob:
        def snapshot(self):
            return {"id": "x", "status": "running"}

    def fake_create(kind, argv, stdin_signal=False):
        captured["argv"] = argv
        return FakeJob()

    monkeypatch.setattr(google.jobs, "create", fake_create)
    google.login(_Req({"account": "work"}))
    assert captured["argv"] == ["run-tool.py", "google-mail", "auth-login", "--account", "work"]
    captured.clear()
    google.login(_Req({"account": "default"}))  # default -> no --account
    assert captured["argv"] == ["run-tool.py", "google-mail", "auth-login"]


def test_google_login_rejects_email_label():
    res = google.login(_Req({"account": "a@example.com"}))
    assert isinstance(res, tuple) and res[0] == 400


def test_google_remove_builds_logout_argv(monkeypatch):
    captured = {}

    def fake_run(tool, argv, timeout=30):
        captured["argv"] = argv
        return {"ok": True, "data": {"authenticated": False}, "error": None}

    monkeypatch.setattr(google.runner, "run_tool", fake_run)
    monkeypatch.setattr(google.inventory, "invalidate", lambda: None)
    google.remove(_Req({"account": "personal"}))
    assert captured["argv"] == ["auth-logout", "--account", "personal"]


def test_google_accounts_fast_no_email(monkeypatch):
    def fake_run(tool, argv, timeout=30):
        assert argv == ["auth-accounts"]  # the fast list makes no get-profile call
        return {"ok": True, "error": None, "data": {"active": "default", "accounts": [
            {"account": "default", "has_token": True},
            {"account": "personal", "has_token": True}]}}
    monkeypatch.setattr(google.runner, "run_tool", fake_run)
    out = google.accounts(_Req())
    assert out["ok"] and out["active"] == "default"
    assert [a["account"] for a in out["accounts"]] == ["default", "personal"]
    assert out["accounts"][0]["active"] and not out["accounts"][1]["active"]
    assert "email" not in out["accounts"][0]  # email is lazy, not in the list


# ---- in-process server: auth gate + routing -----------------------------
@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", security.token()
    srv.shutdown()


def _call(base, path, token=None, method="GET", body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Dashboard-Token"] = token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, method=method, data=data, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_requires_token(server):
    base, _ = server
    status, _ = _call(base, "/api/health")
    assert status == 401


def test_health_ok_with_token(server):
    base, tok = server
    status, body = _call(base, "/api/health", token=tok)
    assert status == 200 and body["ok"] is True


def test_static_index_served_without_token(server):
    base, _ = server
    req = urllib.request.Request(base + "/")
    r = urllib.request.urlopen(req, timeout=10)
    assert r.status == 200 and b"Setup" in r.read()


def test_unknown_api_route_404(server):
    base, tok = server
    status, _ = _call(base, "/api/nope", token=tok)
    assert status == 404


def test_routes_wired():
    for p in ("/api/inventory", "/api/config/list", "/api/context/inspect"):
        assert routes.resolve("GET", p) is not None
    for p in ("/api/credential/set", "/api/validate/one", "/api/copilot",
              "/api/test/tool"):
        assert routes.resolve("POST", p) is not None


# ---- inventory shape (real registry; slower integration check) ----------
def test_inventory_shape():
    inv = inventory.build(force=True)
    assert set(("summary", "tools", "agents", "skills", "providers")) <= set(inv)
    assert inv["summary"]["tools"]["total"] >= 1
    # every tool entry carries the annotations the UI relies on
    sample = inv["tools"][0]
    assert "secrets_status" in sample and "probe" in sample and "kind" in sample
