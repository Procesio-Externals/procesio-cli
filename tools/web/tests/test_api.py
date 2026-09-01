"""The public Python API other tools import: open_session, run_steps, get_text,
screenshot, save_session - all with an injected FakeDriver (no real browser)."""
from __future__ import annotations

import pytest

from tools.web import api, sessions
from tools.web.errors import SessionError, UsageError


def _seed(name="linkedin"):
    sessions.write_state(name, {"cookies": [{"name": "sid", "value": "v"}], "origins": []})


def test_render_pdf_sessionless_writes_pdf(tmp_path, driver_factory):
    out = tmp_path / "invoice.pdf"
    res = api.render_pdf("<h1>hi</h1>", str(out), fmt="Letter",
                         driver_factory=driver_factory)
    d = driver_factory.built[0]
    # session-less: no storageState, no user_data_dir, headless
    assert d.init["storage_state"] is None and d.init["user_data_dir"] is None
    assert d.init["headless"] is True
    call = [kw for m, kw in d.calls if m == "render_pdf"][0]
    assert call["html"] == "<h1>hi</h1>" and call["fmt"] == "Letter"
    assert d.closed is True                      # browser always torn down
    assert res["out"] == str(out) and res["bytes"] > 0
    assert out.read_bytes().startswith(b"%PDF")


def test_open_session_loads_state_and_starts(isolated_sessions, driver_factory):
    _seed()
    d = api.open_session("linkedin", url="https://x.test", driver_factory=driver_factory)
    assert d.started is True
    # storageState from the saved file was handed to the factory
    assert d.init["storage_state"]["cookies"][0]["value"] == "v"
    # url -> a goto happened
    assert ("goto", {"url": "https://x.test", "timeout": None}) in d.calls


def test_open_session_missing_raises(isolated_sessions, driver_factory):
    with pytest.raises(SessionError):
        api.open_session("nope", driver_factory=driver_factory)


def test_open_session_auto_detects_persistent_profile(isolated_sessions, driver_factory):
    # A `<name>.profile` dir (saved via --persistent) is used WITHOUT any
    # storageState — and without the caller passing user_data_dir.
    prof = sessions.profile_dir("gprof")
    prof.mkdir()
    (prof / "Default").write_text("x", encoding="utf-8")  # non-empty
    d = api.open_session("gprof", driver_factory=driver_factory)
    assert d.started is True
    assert d.init["user_data_dir"] == str(prof)
    assert d.init["storage_state"] is None


def test_run_steps_end_to_end_and_closes(isolated_sessions, driver_factory):
    _seed()
    out = api.run_steps(
        "linkedin",
        [{"do": "extract_text", "selector": "h1", "name": "title"}],
        url="https://x.test",
        driver_factory=driver_factory,
    )
    assert out["session"] == "linkedin"
    assert "title" in out["results"]
    d = driver_factory.built[0]
    assert d.closed is True  # always torn down


def test_run_steps_headed_flag_threads_through(isolated_sessions, driver_factory):
    _seed()
    api.run_steps("linkedin", [], headless=False, driver_factory=driver_factory)
    assert driver_factory.built[0].init["headless"] is False


def test_get_text_with_wait_and_selector(isolated_sessions, driver_factory):
    _seed()
    out = api.get_text("linkedin", "https://x.test", selector="main",
                       wait="#ready", driver_factory=driver_factory)
    assert out["session"] == "linkedin"
    assert out["selector"] == "main"
    d = driver_factory.built[0]
    methods = d.methods()
    assert "wait_for" in methods and "extract_text" in methods
    assert d.closed is True


def test_screenshot_full_page_default(isolated_sessions, driver_factory):
    _seed()
    out = api.screenshot("linkedin", "https://x.test", "shot.png",
                         driver_factory=driver_factory)
    assert out["path"] == "shot.png"
    shot = [kw for m, kw in driver_factory.built[0].calls if m == "screenshot"][0]
    assert shot["full_page"] is True


def test_save_session_writes_state_after_signal(isolated_sessions, driver_factory):
    signalled = {"v": False}

    def wait_for_signal():
        signalled["v"] = True

    out = api.save_session("newsite", "https://login.test",
                           wait_for_signal=wait_for_signal,
                           driver_factory=driver_factory)
    assert signalled["v"] is True            # human signal was awaited
    assert out["session"] == "newsite"
    # storageState captured from the (headed) driver and persisted
    assert sessions.exists("newsite")
    saved = sessions.load_state("newsite")
    assert saved["cookies"][0]["name"] == "sid"
    # headed browser was requested
    assert driver_factory.built[0].init["headless"] is False
    assert driver_factory.built[0].closed is True


def test_save_session_persistent_captures_cookie_sidecar(isolated_sessions, driver_factory):
    """A persistent save snapshots live cookies (incl. session-scoped) to a
    sidecar, because the on-disk profile won't persist them itself."""
    out = api.save_session("ryv", "https://example.ryver.com",
                           wait_for_signal=lambda: None, persistent=True,
                           driver_factory=driver_factory)
    assert out["persistent"] is True
    assert out["cookies_saved"] == 1                 # FakeDriver returns one cookie
    assert sessions.cookies_exist("ryv")
    saved = sessions.load_cookies("ryv")
    assert saved[0]["name"] == "sid" and saved[0]["expires"] == -1
    # cookies captured AFTER the human signal and BEFORE close
    methods = driver_factory.built[0].methods()
    assert methods.index("get_cookies") < methods.index("close")


def test_open_session_persistent_reinjects_cookies_before_navigation(isolated_sessions, driver_factory):
    """Opening a persistent profile that has a cookie sidecar must re-inject the
    cookies into the fresh context BEFORE navigating, so the first request is
    authenticated."""
    prof = sessions.profile_dir("ryv")
    prof.mkdir()
    (prof / "Default").write_text("x", encoding="utf-8")
    sessions.write_cookies("ryv", [{"name": "sid", "value": "z",
                                    "domain": ".ringhel.ryver.com", "path": "/",
                                    "expires": -1}])
    d = api.open_session("ryv", url="https://example.ryver.com",
                         driver_factory=driver_factory)
    assert d.injected_cookies and d.injected_cookies[0]["value"] == "z"
    methods = d.methods()
    assert methods.index("add_cookies") < methods.index("goto")  # inject, THEN navigate


def test_open_session_persistent_without_sidecar_skips_injection(isolated_sessions, driver_factory):
    """No sidecar -> no add_cookies call (back-compat for IndexedDB-auth
    profiles like WhatsApp that never had one)."""
    prof = sessions.profile_dir("wa")
    prof.mkdir()
    (prof / "Default").write_text("x", encoding="utf-8")
    d = api.open_session("wa", url="https://web.whatsapp.com",
                         driver_factory=driver_factory)
    assert "add_cookies" not in d.methods()
    assert d.injected_cookies == []


def test_save_session_signal_order(isolated_sessions, driver_factory):
    """storage_state must be captured AFTER the human signal, not before."""
    order = []

    def wait_for_signal():
        order.append("signal")

    # wrap the factory to record when storage_state is read
    base = driver_factory

    def factory(**kw):
        d = base(**kw)
        orig = d.storage_state

        def traced():
            order.append("capture")
            return orig()
        d.storage_state = traced
        return d

    api.save_session("ordered", "https://login.test",
                     wait_for_signal=wait_for_signal, driver_factory=factory)
    assert order == ["signal", "capture"]


# --- non-stdin login wait (agent-driven save-session) -----------------------

def test_save_session_wait_seconds_detects_login(isolated_sessions, driver_factory,
                                                 monkeypatch):
    """With --wait-seconds the browser is held open WITHOUT touching stdin, and
    the wait ends as soon as the address bar leaves the login host."""
    monkeypatch.setattr(api, "_POLL_SECONDS", 0)
    monkeypatch.setattr(api, "_SETTLE_SECONDS", 0)

    def boom():                       # stdin must never be consulted
        raise AssertionError("save_session must not block on stdin")
    monkeypatch.setattr(api, "_block_on_enter", boom)

    out = api.save_session("goog", "https://drive.google.com/drive/my-drive",
                           persistent=True, wait_seconds=30,
                           wait_until_url_excludes="accounts.google.com",
                           driver_factory=driver_factory)
    assert out["waited_for"] == "url"
    assert out["login_detected"] is True          # FakeDriver url is off the login host
    assert out["final_url"] == "https://example.com/after"   # FakeDriver post-nav url


def test_save_session_wait_seconds_reports_timeout(isolated_sessions, monkeypatch):
    """Still on the login host when time runs out -> login_detected False, so a
    half-authenticated save is never mistaken for success. This is the exact
    case that silently produced a broken `google` session (see
    WEB-AUTOMATION-NOTES.md)."""
    from tools.web.tests.conftest import FakeDriver

    monkeypatch.setattr(api, "_POLL_SECONDS", 0)
    monkeypatch.setattr(api, "_SETTLE_SECONDS", 0)

    def stuck_factory(**kwargs):
        # never leaves the login host, however long we wait
        return FakeDriver(url="https://accounts.google.com/signin", **kwargs)

    out = api.save_session("goog2", "https://accounts.google.com/signin",
                           persistent=True, wait_seconds=1,
                           wait_until_url_excludes="accounts.google.com",
                           driver_factory=stuck_factory)
    assert out["login_detected"] is False
    assert "final_url" not in out


def test_save_session_rejects_nonpositive_wait(isolated_sessions, driver_factory):
    with pytest.raises(UsageError):
        api.save_session("goog3", "https://example.test", wait_seconds=0,
                         driver_factory=driver_factory)


# --- human-handoff hold (agent stages, human commits) ----------------------

def _steps():
    return [{"do": "fill", "selector": "#name", "text": "x"}]


def test_run_hold_ends_early_when_selector_appears(isolated_sessions, driver_factory,
                                                   monkeypatch):
    """The hold exists so a human can click Submit. FakeDriver.wait_for always
    resolves, i.e. the confirmation element is already there -> reason
    'selector', completed True."""
    monkeypatch.setattr(api, "_POLL_SECONDS", 0)

    _seed()
    out = api.run_steps("linkedin", _steps(), headless=False, hold_seconds=30,
                        hold_until_selector="text=Thank",
                        driver_factory=driver_factory)
    assert out["hold"]["completed"] is True
    assert out["hold"]["reason"] == "selector"


def test_run_hold_ends_early_when_url_leaves_host(isolated_sessions, driver_factory,
                                                  monkeypatch):
    monkeypatch.setattr(api, "_POLL_SECONDS", 0)

    _seed()
    out = api.run_steps("linkedin", _steps(), headless=False, hold_seconds=30,
                        hold_until_url_excludes="form.example.test",
                        driver_factory=driver_factory)
    assert out["hold"]["completed"] is True
    assert out["hold"]["reason"] == "url"


def test_run_hold_timeout_is_success_not_failure(isolated_sessions, monkeypatch):
    """The regression this feature exists for: an idle human must NOT turn a
    successful fill into a failed run. No raise, steps' results intact."""
    from tools.web.tests.conftest import FakeDriver

    monkeypatch.setattr(api, "_POLL_SECONDS", 0)

    class NeverDriver(FakeDriver):
        def wait_for(self, selector, *, timeout=None):
            raise RuntimeError("selector never appears")

    _seed()
    out = api.run_steps("linkedin", _steps(), headless=False, hold_seconds=1,
                        hold_until_selector="text=Thank",
                        driver_factory=lambda **kw: NeverDriver(**kw))
    assert out["hold"]["completed"] is False
    assert out["hold"]["reason"] == "timeout"
    assert out["hold"]["held_seconds"] >= 0
    assert "results" in out          # the steps still ran


def test_run_hold_requires_headed(isolated_sessions, driver_factory):
    with pytest.raises(UsageError):
        api.run_steps("linkedin", _steps(), headless=True, hold_seconds=30,
                      driver_factory=driver_factory)


def test_run_hold_rejects_nonpositive(isolated_sessions, driver_factory):
    with pytest.raises(UsageError):
        api.run_steps("linkedin", _steps(), headless=False, hold_seconds=0,
                      driver_factory=driver_factory)


def test_run_hold_conditions_require_hold_seconds(isolated_sessions, driver_factory):
    with pytest.raises(UsageError):
        api.run_steps("linkedin", _steps(), headless=False,
                      hold_until_selector="text=Thank",
                      driver_factory=driver_factory)


def test_run_without_hold_has_no_hold_block(isolated_sessions, driver_factory):
    _seed()
    out = api.run_steps("linkedin", _steps(), driver_factory=driver_factory)
    assert "hold" not in out
