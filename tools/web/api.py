"""Public Python API for the web tool.

Other tools (e.g. the forthcoming ``whatsapp-personal`` tool) and the outreach
agent should drive saved sessions through THIS module rather than shelling out
to the CLI. Everything here is importable as::

    from tools.web import open_session, run_steps, get_text, screenshot
    # or, for the lower-level pieces:
    from tools.web.api import save_session, list_sessions, delete_session

Design
------
* ``open_session(name, ...)`` is the workhorse: it loads a saved session's
  storageState and returns a *started* ``PlaywrightDriver``. Use it as a context
  manager so the browser is always torn down::

      from tools.web import open_session
      with open_session("whatsapp") as d:
          d.goto("https://web.whatsapp.com")
          d.click("div[title='Search']")
          ...

* ``run_steps(name, steps, url=...)`` runs a declarative step list (see
  ``steps.py``) end-to-end against a saved session and returns the collected
  JSON-able outputs - convenient for one-shot scripted interactions.

* ``get_text`` / ``screenshot`` are thin one-call conveniences.

* ``save_session`` is the interactive capture (headed browser + human signal);
  the ``wait_for_signal`` callback is injectable so callers/tests control when
  the state is captured.

All functions accept ``driver_factory`` so tests can inject a FakeDriver and run
without a real browser; production defaults to ``PlaywrightDriver``.
"""
from __future__ import annotations

from typing import Any, Callable

from tools.web import sessions
from tools.web.driver import BrowserDriver, PlaywrightDriver
from tools.web.errors import UsageError
from tools.web.steps import run_steps as _interpret_steps

# Re-export the metadata-only helpers so callers get one import surface.
session_path = sessions.session_path
list_sessions = sessions.list_all
delete_session = sessions.delete


def _default_factory(*, storage_state=None, headless=True, channel=None,
                     user_data_dir=None, extra_args=None):
    return PlaywrightDriver(storage_state=storage_state, headless=headless,
                            channel=channel, user_data_dir=user_data_dir,
                            extra_args=extra_args)


def open_session(name: str, *, headless: bool = True, channel: str | None = None,
                 url: str | None = None, user_data_dir: str | None = None,
                 driver_factory: Callable = _default_factory,
                 extra_args: list | None = None) -> BrowserDriver:
    """Load a saved session and return a STARTED driver (use as a context mgr).

    Two modes: a storageState session (default) OR a PERSISTENT profile (for
    IndexedDB-auth sites like WhatsApp Web, or anti-bot-sensitive sites like
    Google — the on-disk profile carries the login, no storageState involved).
    The persistent mode is selected when ``user_data_dir`` is passed explicitly OR
    auto-detected when a ``<name>.profile`` directory exists for the session, so
    the CLI run/get-text/screenshot actions transparently use whichever mode the
    session was saved in. Raises SessionError if a storageState session is
    missing. Navigates to ``url`` first.
    """
    # Auto-detect a persistent profile saved via `save-session --persistent`:
    # prefer it over storageState so a profile session is usable, not write-only.
    if user_data_dir is None and sessions.profile_exists(name):
        user_data_dir = str(sessions.profile_dir(name))
    if user_data_dir is not None:
        driver = driver_factory(storage_state=None, headless=headless,
                                channel=channel, user_data_dir=user_data_dir,
                                extra_args=extra_args)
    else:
        state = sessions.load_state(name)
        driver = driver_factory(storage_state=state, headless=headless, channel=channel,
                                extra_args=extra_args)
    driver.start()
    # Persistent profiles drop SESSION-scoped cookies on close (Chromium never
    # writes them to disk), so a cookie-auth site (e.g. Ryver) reopens logged
    # out. If save-session captured a cookie sidecar, replay it into the fresh
    # context BEFORE navigating so the very first request carries the session.
    if user_data_dir is not None and sessions.cookies_exist(name):
        inject = getattr(driver, "add_cookies", None)
        cookies = sessions.load_cookies(name)
        if cookies and callable(inject):
            inject(cookies)
    if url:
        driver.goto(url)
    return driver


def run_steps(name: str, steps: list[dict], *, url: str | None = None,
              headless: bool = True, channel: str | None = None,
              user_data_dir: str | None = None,
              hold_seconds: int | None = None,
              hold_until_selector: str | None = None,
              hold_until_url_excludes: str | None = None,
              driver_factory: Callable = _default_factory) -> dict:
    """Run a declarative step list against a saved session; return collected
    outputs ``{"session", "results", "screenshots", "final_url"}``.

    If ``url`` is given it is visited first (equivalent to a leading goto step).
    ``user_data_dir`` selects the persistent-profile mode. The driver is always
    closed before returning.

    ``hold_seconds`` keeps the HEADED browser open for up to that long after the
    last step, so a human can review what was staged and click the irreversible
    control themselves - the agent never presses Submit. ``hold_until_selector``
    / ``hold_until_url_excludes`` end the hold early once the human has acted.
    A hold that runs out is SUCCESS, not failure: the steps still ran, so the
    result carries ``hold.completed = False`` rather than raising. Adds a
    ``hold`` block to the output; ``final_url`` and ``diagnostics`` are read
    AFTER the hold so they reflect what the human did.
    """
    if hold_seconds is not None and hold_seconds <= 0:
        raise UsageError("--hold-seconds must be a positive number of seconds")
    if hold_seconds is not None and headless:
        raise UsageError("--hold-seconds requires --headed: holding a headless "
                         "browser open gives the human nothing to act on")
    if hold_seconds is None and (hold_until_selector or hold_until_url_excludes):
        raise UsageError("--hold-until-selector/--hold-until-url-excludes require "
                         "--hold-seconds")
    driver = open_session(name, headless=headless, channel=channel, url=url,
                          user_data_dir=user_data_dir, driver_factory=driver_factory)
    try:
        out = _interpret_steps(driver, steps)
        if hold_seconds is not None:
            out["hold"] = _run_hold(driver, hold_seconds, hold_until_selector,
                                    hold_until_url_excludes)
            # Re-read AFTER the hold: the whole point is what the human did.
            final = _safe_url(driver)
            if final is not None:
                out["final_url"] = final
        out["diagnostics"] = _diagnostics(driver)
    finally:
        _safe_close(driver)
    out["session"] = name
    return out


def get_text(name: str, url: str, *, selector: str | None = None,
             wait: str | None = None, headless: bool = True,
             channel: str | None = None,
             driver_factory: Callable = _default_factory) -> dict:
    """Load a session, navigate to ``url``, return visible text.

    With ``selector`` returns that element's text; otherwise the whole page body.
    ``wait`` (a selector) is awaited before reading - handy for SPA content.
    Returns ``{"session", "url", "selector", "text", "final_url"}``.
    """
    driver = open_session(name, headless=headless, channel=channel, url=url,
                          driver_factory=driver_factory)
    try:
        if wait:
            driver.wait_for(wait)
        text = driver.extract_text(selector)
        final = _safe_url(driver)
        diag = _diagnostics(driver)
    finally:
        _safe_close(driver)
    return {"session": name, "url": url, "selector": selector,
            "text": text, "final_url": final, "diagnostics": diag}


def screenshot(name: str, url: str, out: str, *, full_page: bool = True,
               wait: str | None = None, headless: bool = True,
               channel: str | None = None,
               driver_factory: Callable = _default_factory) -> dict:
    """Load a session, navigate to ``url``, save a screenshot to ``out``.

    Returns ``{"session", "url", "path", "final_url"}``.
    """
    driver = open_session(name, headless=headless, channel=channel, url=url,
                          driver_factory=driver_factory)
    try:
        if wait:
            driver.wait_for(wait)
        path = driver.screenshot(out, full_page=full_page)
        final = _safe_url(driver)
        diag = _diagnostics(driver)
    finally:
        _safe_close(driver)
    return {"session": name, "url": url, "path": path, "final_url": final, "diagnostics": diag}


def render_pdf(html: str, out: str, *, fmt: str = "A4",
               driver_factory: Callable = _default_factory) -> dict:
    """Render an HTML string to a PDF file — no session, no navigation.

    Launches a throwaway headless Chromium (Chromium's ``page.pdf()`` is
    headless-only), sets the page content to ``html``, writes the PDF to ``out``,
    and tears the browser down. Reusable HTML→PDF for deterministic document
    generation (e.g. the invoice-collector reconstructing a Ryver invoice).
    Returns ``{"out": path, "bytes": n}``.
    """
    import os

    driver = driver_factory(storage_state=None, headless=True)
    driver.start()
    try:
        driver.render_pdf(html, out, fmt=fmt)
    finally:
        _safe_close(driver)
    try:
        size = os.path.getsize(out)
    except OSError:
        size = 0
    return {"out": out, "bytes": size}


def save_session(name: str, url: str, *,
                 wait_for_signal: Callable[[], Any] | None = None,
                 channel: str | None = None, persistent: bool = False,
                 wait_seconds: int | None = None,
                 wait_until_url_excludes: str | None = None,
                 driver_factory: Callable = _default_factory) -> dict:
    """Interactively capture a session.

    Launches a HEADED browser at ``url``, lets a human log in, then - after
    ``wait_for_signal()`` returns - persists the auth. Two modes:

    * default: capture the context's storageState to ``sessions/<name>.json``.
    * ``persistent=True``: drive a persistent Chromium profile at
      ``sessions/<name>.profile`` — the login is already saved on disk in that
      dir, so we just close. Use for IndexedDB-auth sites (WhatsApp Web).

    ``wait_for_signal`` defaults to blocking on a line from stdin (ENTER).

    ``wait_seconds`` selects a NON-STDIN wait instead: hold the browser open for
    up to that long while the human logs in. Required when an agent launches the
    flow — agent stdin is EOF, so the ENTER wait returns instantly and saves a
    half-authenticated profile (see WEB-AUTOMATION-NOTES.md). With
    ``wait_until_url_excludes`` the wait ends early, as soon as the address bar
    leaves the login host (e.g. ``accounts.google.com``), then settles briefly.
    """
    sessions.validate_name(name)
    if not url:
        raise UsageError("save_session requires a --url to open for login")
    if wait_seconds is not None and wait_seconds <= 0:
        raise UsageError("--wait-seconds must be a positive number of seconds")
    if wait_for_signal is None and wait_seconds is None:
        wait_for_signal = _block_on_enter

    if persistent:
        profile = sessions.profile_dir(name)
        profile.mkdir(parents=True, exist_ok=True)
        driver = driver_factory(storage_state=None, headless=False,
                                channel=channel, user_data_dir=str(profile))
        driver.start()
        cookies_saved = 0
        try:
            driver.goto(url)
            # human logs in; the profile auto-persists to disk
            waited = _run_wait(driver, wait_for_signal, wait_seconds,
                               wait_until_url_excludes)
            # Snapshot live cookies (incl. session-scoped ones) BEFORE close.
            # The profile persists localStorage/IndexedDB but NOT session
            # cookies, so this sidecar is the only durable copy for cookie-auth
            # sites. Re-injected by open_session on every subsequent run.
            grab = getattr(driver, "get_cookies", None)
            if callable(grab):
                cookies = grab() or []
                if cookies:
                    sessions.write_cookies(name, cookies)
                    cookies_saved = len(cookies)
        finally:
            _safe_close(driver)
        out = {"session": name, "profile": str(profile), "url": url,
               "persistent": True, "cookies_saved": cookies_saved}
        out.update(waited)
        return out

    driver = driver_factory(storage_state=None, headless=False, channel=channel)
    driver.start()
    try:
        driver.goto(url)
        waited = _run_wait(driver, wait_for_signal, wait_seconds,
                           wait_until_url_excludes)
        state = driver.storage_state()
    finally:
        _safe_close(driver)
    path = sessions.write_state(name, state)
    out = {"session": name, "path": str(path), "url": url}
    out.update(waited)
    return out


# --- internals ------------------------------------------------------------

_POLL_SECONDS = 2      # how often the login poller re-reads the address bar
_SETTLE_SECONDS = 8    # post-redirect settle so auth cookies land before snapshot
_HOLD_PROBE_MS = 500   # per-poll selector probe during a human-handoff hold


def _run_wait(driver, wait_for_signal, wait_seconds, url_excludes) -> dict:
    """Hold the browser open while the human logs in.

    Returns a small report merged into the action output so the caller can tell
    a completed login from a timeout — never trust ``cookies_saved`` for that.
    """
    if wait_seconds is None:
        wait_for_signal()
        return {"waited_for": "enter"}

    import sys
    import time

    print(f"\n>>> Browser open. Log in - saving automatically once you are "
          f"through (up to {wait_seconds}s).", file=sys.stderr, flush=True)

    deadline = time.monotonic() + wait_seconds
    detected = False
    while time.monotonic() < deadline:
        time.sleep(_POLL_SECONDS)
        if not url_excludes:
            continue
        try:
            current = driver.current_url() or ""
        except Exception:  # noqa: BLE001 - browser may be mid-navigation
            continue
        if url_excludes not in current:
            detected = True
            break

    report = {"waited_for": "url" if url_excludes else "timer",
              "login_detected": detected}
    if detected:
        # Let post-redirect cookies/localStorage settle before we snapshot.
        print(">>> Login detected - settling before save...",
              file=sys.stderr, flush=True)
        time.sleep(_SETTLE_SECONDS)
        try:
            report["final_url"] = driver.current_url()
        except Exception:  # noqa: BLE001
            pass
    elif url_excludes:
        print(">>> Timed out still on the login host — session NOT confirmed.",
              file=sys.stderr, flush=True)
    return report


def _run_hold(driver, hold_seconds: int, until_selector: str | None,
              until_url_excludes: str | None) -> dict:
    """Hold a headed browser open after the steps so a human can finish the job.

    Distinct from ``_run_wait`` (which serves save-session's login capture and
    reports ``login_detected``): this one also polls for a SELECTOR, and a
    timeout here is a normal outcome rather than a suspect one - the human is
    allowed to walk away. Returns
    ``{"held_seconds", "completed", "reason"}`` with reason
    ``selector`` | ``url`` | ``timeout``.

    ``completed`` is ADVISORY, not proof - same caveat as ``login_detected``.
    The authoritative check stays ``final_url`` + ``diagnostics``.
    """
    import sys
    import time

    print(f"\n>>> Steps done. Browser stays open up to {hold_seconds}s - review "
          f"and complete the action yourself.", file=sys.stderr, flush=True)

    started = time.monotonic()
    deadline = started + hold_seconds
    reason = "timeout"
    while time.monotonic() < deadline:
        time.sleep(_POLL_SECONDS)
        if until_selector:
            try:
                driver.wait_for(until_selector, timeout=_HOLD_PROBE_MS)
                reason = "selector"
                break
            except Exception:  # noqa: BLE001 - not there yet is the normal case
                pass
        if until_url_excludes:
            try:
                current = driver.current_url() or ""
            except Exception:  # noqa: BLE001 - may be mid-navigation
                continue
            if until_url_excludes not in current:
                reason = "url"
                break

    held = round(time.monotonic() - started, 1)
    completed = reason != "timeout"
    if completed:
        print(f">>> Human action detected ({reason}) after {held}s.",
              file=sys.stderr, flush=True)
    else:
        print(f">>> Hold expired after {held}s with no action detected - the "
              f"steps still ran.", file=sys.stderr, flush=True)
    return {"held_seconds": held, "completed": completed, "reason": reason}


def _block_on_enter() -> None:
    import sys
    print(
        "\n>>> Log in to the site in the opened browser window. "
        "When you are fully logged in, return here and press ENTER to save "
        "the session...",
        file=sys.stderr, flush=True,
    )
    try:
        sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        pass


def _diagnostics(driver) -> dict:
    """Collect runtime diagnostics (console/page errors, failed/4xx-5xx requests) if the
    driver supports it. Defensive: a driver without diagnostics() (e.g. test FakeDriver)
    yields an empty dict and never breaks the call."""
    fn = getattr(driver, "diagnostics", None)
    try:
        return fn() if callable(fn) else {}
    except Exception:  # noqa: BLE001
        return {}


def _safe_close(driver) -> None:
    close = getattr(driver, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001
            pass


def _safe_url(driver) -> str | None:
    try:
        return driver.current_url()
    except Exception:  # noqa: BLE001
        return None
