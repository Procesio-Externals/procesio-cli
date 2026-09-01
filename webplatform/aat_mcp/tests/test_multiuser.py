"""Multi-user isolation seams (spec 08): per-request user threading + per-user
userdata + per-user file credentials. No real subprocess."""
from __future__ import annotations

import bridge  # adds repo root to sys.path


def test_bridge_threads_user_into_subprocess_env(monkeypatch):
    seen = {}
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)  # force the local path
    monkeypatch.setattr(bridge.runner, "run_tool",
                        lambda tool, argv, **k: seen.update(env=k.get("env")) or {"ok": True, "data": {}})
    tok = bridge.set_user("alice")
    try:
        bridge.run_tool("hello-world", None, {"name": "X"})
        assert seen["env"] == {"AAT_USER_ID": "alice"}
    finally:
        bridge.reset_user(tok)
    # after reset -> single-user (no per-user env)
    seen.clear()
    bridge.run_tool("hello-world", None, {"name": "X"})
    assert seen["env"] is None


def test_delegation_forwards_user_header(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true, "data": {}}'

    def fake_urlopen(req, timeout=None):
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp()

    monkeypatch.setenv("AAT_HOST_RUNNER_URL", "http://host.docker.internal:8904")
    monkeypatch.setenv("AAT_HOST_RUNNER_TOKEN", "rtok")
    monkeypatch.setattr(bridge.urllib.request, "urlopen", fake_urlopen)
    tok = bridge.set_user("bob")
    try:
        bridge.run_tool("web", "get-text", {"url": "https://example.com"})
    finally:
        bridge.reset_user(tok)
    assert captured["headers"].get("x-aat-user") == "bob"
    assert captured["headers"].get("authorization") == "Bearer rtok"


def test_userdata_isolates_per_user(monkeypatch, tmp_path):
    from tools._lib import userdata
    monkeypatch.setenv("AAT_USERDATA_DIR", str(tmp_path))
    monkeypatch.setenv("AAT_USER_ID", "alice")
    a = userdata.base()
    monkeypatch.setenv("AAT_USER_ID", "bob")
    b = userdata.base()
    assert a == tmp_path / "alice"
    assert b == tmp_path / "bob"
    assert a != b
    monkeypatch.delenv("AAT_USER_ID")
    assert userdata.base() == tmp_path  # single-user root, unchanged behaviour


def test_userdata_rejects_traversal(monkeypatch, tmp_path):
    from tools._lib import userdata
    monkeypatch.setenv("AAT_USERDATA_DIR", str(tmp_path))
    monkeypatch.setenv("AAT_USER_ID", "../evil")
    # sanitized to a safe single segment under the root - never escapes
    assert tmp_path in userdata.base().parents or userdata.base().parent == tmp_path


def test_file_creds_isolate_per_user(monkeypatch, tmp_path):
    from tools._lib import creds_backends
    (tmp_path / "alice").mkdir()
    (tmp_path / "bob").mkdir()
    (tmp_path / "alice" / "hello__key").write_text("AAA", encoding="utf-8")
    (tmp_path / "bob" / "hello__key").write_text("BBB", encoding="utf-8")
    (tmp_path / "hello__shared").write_text("SHARED", encoding="utf-8")
    monkeypatch.setenv("AAT_SECRETS_DIR", str(tmp_path))
    be = creds_backends.FileSecretBackend()
    monkeypatch.setenv("AAT_USER_ID", "alice")
    assert be.get_optional("hello", "key") == "AAA"
    monkeypatch.setenv("AAT_USER_ID", "bob")
    assert be.get_optional("hello", "key") == "BBB"
    # a secret only in the shared dir resolves for any user (fallback)
    assert be.get_optional("hello", "shared") == "SHARED"
    assert be.get_optional("hello", "missing") is None
