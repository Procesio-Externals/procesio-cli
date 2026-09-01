"""Pytest fixtures + sys.path for the web tool.

FakeDriver records every BrowserDriver call (method + args) and returns canned
values for the extract_* / current_url reads. Tests inject it everywhere a real
browser would be used, so the suite is fully hermetic - ZERO real browser, and
it runs even when Playwright's browser binaries are not installed.

The ``isolated_sessions`` fixture redirects ``tools.web.sessions.SESSIONS_DIR``
to a temp directory so session read/write/list/delete tests never touch the real
sessions folder.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))


class FakeDriver:
    """A BrowserDriver test double.

    Records calls in ``self.calls`` as (method, kwargs) tuples. Read methods
    return values from ``self.texts`` / ``self.attrs`` / ``self.url`` so tests
    can assert on the interpreter's collected results. ``storage_state()``
    returns ``self.state`` (used by save-session tests).
    """

    def __init__(self, *, storage_state=None, headless=True, channel=None,
                 user_data_dir=None, texts=None, attrs=None, htmls=None, evals=None,
                 extra_args=None, url="https://example.com/after"):
        self.init = {"storage_state": storage_state, "headless": headless,
                     "channel": channel, "user_data_dir": user_data_dir,
                     "extra_args": list(extra_args or [])}
        self.calls: list[tuple[str, dict]] = []
        self.texts = texts or {}          # selector(or None) -> text
        self.attrs = attrs or {}          # (selector, attr) -> value
        self.htmls = htmls or {}          # selector -> innerHTML
        self.evals = evals or {}          # script -> result
        self.url = url
        self.started = False
        self.closed = False
        # what storage_state() returns after an interactive capture
        self.state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
        # what get_cookies() returns (incl. session-scoped); add_cookies records here
        self.cookies = [{"name": "sid", "value": "abc", "domain": ".example.com",
                         "path": "/", "expires": -1}]
        self.injected_cookies: list[dict] = []

    # lifecycle
    def start(self):
        self.started = True
        self.calls.append(("start", {}))
        return self

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.close()

    def close(self):
        self.closed = True
        self.calls.append(("close", {}))

    def storage_state(self):
        self.calls.append(("storage_state", {}))
        return self.state

    # surface
    def goto(self, url, *, timeout=None):
        self.calls.append(("goto", {"url": url, "timeout": timeout}))

    def click(self, selector, *, timeout=None, force=False):
        self.calls.append(("click", {"selector": selector, "timeout": timeout,
                                     "force": force}))

    def hover(self, selector, *, timeout=None):
        self.calls.append(("hover", {"selector": selector, "timeout": timeout}))

    def context_click(self, selector, *, timeout=None):
        self.calls.append(("context_click", {"selector": selector, "timeout": timeout}))

    def fill(self, selector, text, *, timeout=None):
        self.calls.append(("fill", {"selector": selector, "text": text, "timeout": timeout}))

    def press(self, key, *, selector=None):
        self.calls.append(("press", {"key": key, "selector": selector}))

    def type_text(self, text, *, selector=None, timeout=None):
        self.calls.append(("type_text", {"text": text, "selector": selector, "timeout": timeout}))

    def wait(self, ms):
        self.calls.append(("wait", {"ms": ms}))

    def wait_for(self, selector, *, timeout=None):
        self.calls.append(("wait_for", {"selector": selector, "timeout": timeout}))

    def extract_text(self, selector=None, *, timeout=None):
        self.calls.append(("extract_text", {"selector": selector, "timeout": timeout}))
        return self.texts.get(selector, f"text:{selector}")

    def extract_attr(self, selector, attr, *, timeout=None):
        self.calls.append(("extract_attr", {"selector": selector, "attr": attr, "timeout": timeout}))
        return self.attrs.get((selector, attr), f"attr:{selector}:{attr}")

    def inner_html(self, selector, *, timeout=None):
        self.calls.append(("inner_html", {"selector": selector, "timeout": timeout}))
        return self.htmls.get(selector, f"<i>html:{selector}</i>")

    def eval_js(self, script, *, arg=None):
        self.calls.append(("eval_js", {"script": script, "arg": arg}))
        return self.evals.get(script)

    def set_input_files(self, selector, files, *, timeout=None):
        self.calls.append(("set_input_files", {"selector": selector, "files": files, "timeout": timeout}))

    def set_files_via_chooser(self, trigger_selector, files, *, timeout=None):
        self.calls.append(("set_files_via_chooser",
                           {"selector": trigger_selector, "files": files, "timeout": timeout}))

    def screenshot(self, path, *, full_page=True):
        self.calls.append(("screenshot", {"path": path, "full_page": full_page}))
        return path

    def render_pdf(self, html, path, *, fmt="A4"):
        self.calls.append(("render_pdf", {"html": html, "path": path, "fmt": fmt}))
        # Write a minimal stub so callers that stat the output see bytes.
        with open(path, "wb") as fh:
            fh.write(b"%PDF-1.4 fake\n")
        return path

    def current_url(self):
        self.calls.append(("current_url", {}))
        return self.url

    def get_cookies(self):
        self.calls.append(("get_cookies", {}))
        return list(self.cookies)

    def add_cookies(self, cookies):
        self.calls.append(("add_cookies", {"cookies": cookies}))
        self.injected_cookies.extend(cookies or [])

    # convenience for assertions
    def methods(self):
        return [m for m, _ in self.calls]


@pytest.fixture
def fake_driver():
    return FakeDriver()


@pytest.fixture
def driver_factory():
    """Returns (factory, holder). factory(**kwargs) builds a FakeDriver and
    appends it to holder so tests can inspect what was built/called."""
    built: list[FakeDriver] = []

    def factory(*, storage_state=None, headless=True, channel=None, user_data_dir=None,
                extra_args=None):
        d = FakeDriver(storage_state=storage_state, headless=headless,
                       channel=channel, user_data_dir=user_data_dir, extra_args=extra_args)
        built.append(d)
        return d

    factory.built = built  # type: ignore[attr-defined]
    return factory


@pytest.fixture
def isolated_sessions(tmp_path, monkeypatch):
    """Point the sessions module at a temp dir for the duration of a test."""
    from tools.web import sessions

    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(sessions, "SESSIONS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def _no_broker_routing(monkeypatch):
    """Default every test to the in-process path: a test targeting an OWNED
    session name (whatsapp/ryver/fgo/mirro) must never talk to — or spawn — a
    real serializing broker. Routing tests delete these selectively."""
    for env in ("WHATSAPP_DIRECT", "RYVER_WEB_DIRECT", "FGO_WEB_DIRECT", "MIRRO_DIRECT"):
        monkeypatch.setenv(env, "1")
