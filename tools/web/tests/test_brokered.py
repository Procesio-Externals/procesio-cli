"""web-tool broker routing tests: generic run/get-text/screenshot against a
broker-OWNED session are translated to a web-steps op on the owning broker;
unowned sessions, --direct, --channel and injected factories stay in-process.
save-session/delete-session stop the owning broker first. No real broker is
ever spawned (conftest autouse sets all *_DIRECT; tests stub the lib client)."""
from __future__ import annotations

import pytest

from tools._lib.webserialize import client as ws_client
from tools.web import brokered
from tools.web.main import dispatch


def _unroute(monkeypatch):
    for env in ("WHATSAPP_DIRECT", "RYVER_WEB_DIRECT",
                "FGO_WEB_DIRECT", "MIRRO_DIRECT"):
        monkeypatch.delenv(env, raising=False)


@pytest.fixture
def captured_web_steps(monkeypatch):
    """Stub the lib's web_steps; records the submission and returns a canned
    run_steps-shaped result tagged as served by the broker."""
    seen = {}

    def fake(cfg, session, steps, *, url=None, headless=True,
             read_timeout=None, dispatch_direct=None):
        seen.update(tool=cfg.tool, session=session, steps=steps,
                    url=url, headless=headless)
        return {"session": session,
                "results": {"text": "PAGE TEXT"}, "screenshots": ["x.png"],
                "final_url": "https://final/", "diagnostics": {},
                "via": "service", "service_queue_wait_ms": 3}

    monkeypatch.setattr(ws_client, "web_steps", fake)
    return seen


def test_run_routes_to_owning_broker(monkeypatch, captured_web_steps):
    _unroute(monkeypatch)
    out = dispatch("run", ["--session", "ryver", "--url", "https://r/",
                           "--actions", '[{"do": "extract_text", "name": "t"}]'])
    assert captured_web_steps["tool"] == "ryver-web"
    assert captured_web_steps["session"] == "ryver"
    assert captured_web_steps["steps"] == [{"do": "extract_text", "name": "t"}]
    assert out["via"] == "service"


def test_get_text_translation_and_reshape(monkeypatch, captured_web_steps):
    _unroute(monkeypatch)
    out = dispatch("get-text", ["--session", "whatsapp", "--url", "https://w/",
                                "--selector", "#main", "--wait", "#pane-side"])
    assert captured_web_steps["steps"] == [
        {"do": "wait_for", "selector": "#pane-side"},
        {"do": "extract_text", "name": "text", "selector": "#main"},
    ]
    assert out["text"] == "PAGE TEXT" and out["session"] == "whatsapp"
    assert out["final_url"] == "https://final/" and out["via"] == "service"


def test_screenshot_translation(monkeypatch, captured_web_steps, tmp_path):
    _unroute(monkeypatch)
    target = str(tmp_path / "shot.png")
    out = dispatch("screenshot", ["--session", "fgo", "--url", "https://f/",
                                  "--out", target, "--viewport-only"])
    assert captured_web_steps["steps"] == [
        {"do": "screenshot", "path": target, "full_page": False}]
    assert out["path"] == target and out["via"] == "service"


def test_unowned_session_stays_direct(monkeypatch, driver_factory, isolated_sessions):
    _unroute(monkeypatch)
    monkeypatch.setattr(ws_client, "web_steps",
                        lambda *a, **k: pytest.fail("unowned must not route"))
    (isolated_sessions / "google.json").write_text('{"cookies": [], "origins": []}',
                                                   encoding="utf-8")
    out = dispatch("get-text", ["--session", "google", "--url", "https://g/"],
                   driver_factory=driver_factory)
    assert "text" in out


def test_direct_and_channel_and_env_stay_local(monkeypatch):
    _unroute(monkeypatch)
    from types import SimpleNamespace as NS
    base = dict(direct=False, channel=None, session="whatsapp")
    assert brokered.eligible(NS(**base), driver_factory=None,
                             allow_service=True) is not None
    assert brokered.eligible(NS(**{**base, "direct": True}),
                             driver_factory=None, allow_service=True) is None
    assert brokered.eligible(NS(**{**base, "channel": "chrome"}),
                             driver_factory=None, allow_service=True) is None
    assert brokered.eligible(NS(**base), driver_factory=object(),
                             allow_service=True) is None
    assert brokered.eligible(NS(**{**base, "session": "google"}),
                             driver_factory=None, allow_service=True) is None
    monkeypatch.setenv("WHATSAPP_DIRECT", "1")   # owning tool's kill switch
    assert brokered.eligible(NS(**base), driver_factory=None,
                             allow_service=True) is None
    monkeypatch.delenv("WHATSAPP_DIRECT")
    monkeypatch.setenv("WHATSAPP_SERVICE_WORKER", "1")  # inside the worker
    assert brokered.eligible(NS(**base), driver_factory=None,
                             allow_service=True) is None


def test_fallback_result_is_not_reshaped(monkeypatch):
    """When the broker can't start, web_steps falls back to the DIRECT handler
    whose result is already final — route() must return it untouched."""
    _unroute(monkeypatch)
    monkeypatch.setattr(ws_client, "ensure_running", lambda cfg, **k: None)
    from types import SimpleNamespace as NS
    parsed = NS(session="ryver", url="https://r/", selector=None, wait=None,
                headed=False, direct=False, channel=None)
    cfg = brokered.eligible(parsed, driver_factory=None, allow_service=True)
    result = brokered.route(cfg, "get-text", parsed,
                            dispatch_direct=lambda: {"text": "DIRECT",
                                                     "session": "ryver"})
    assert result["text"] == "DIRECT" and result["via"] == "direct-fallback"


def test_save_session_stops_owning_broker(monkeypatch, isolated_sessions):
    from tools.web.handlers import sessmgmt
    stopped = {}
    monkeypatch.setattr(ws_client, "ping", lambda cfg, **k: {"pong": True})
    monkeypatch.setattr(ws_client, "stop",
                        lambda cfg, **k: stopped.setdefault("tool", cfg.tool) or True)
    monkeypatch.setattr(sessmgmt.api, "save_session",
                        lambda name, url, channel=None, persistent=False, **kw:
                        {"session": name, "url": url, "persistent": persistent})
    from types import SimpleNamespace as NS
    out = sessmgmt.save_session(NS(name="whatsapp", url="https://w/",
                                   channel=None, persistent=True))
    assert stopped["tool"] == "whatsapp-personal"
    assert out["broker_stopped"] == "whatsapp-personal"

    out = sessmgmt.save_session(NS(name="google", url="https://g/",
                                   channel=None, persistent=False))
    assert "broker_stopped" not in out
