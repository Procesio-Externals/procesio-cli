"""Browser driver abstraction for the web tool.

The whole point of this layer is testability: the declarative step interpreter
(``steps.py``) and the high-level API (``api.py``) talk only to the small
``BrowserDriver`` interface below. Tests inject a ``FakeDriver`` (see
``tests/conftest.py``) and run the entire tool with ZERO real browser.

``PlaywrightDriver`` is the production implementation. Playwright is imported
**lazily inside methods** so importing this module (and running the hermetic
test suite) never requires the browser binaries to be installed.

Lifecycle
---------
A driver wraps one Playwright *browser context* (optionally seeded from a saved
``storageState``) and one *page*. Use it as a context manager::

    with PlaywrightDriver(storage_state=state, headless=True) as d:
        d.goto("https://example.com")
        text = d.extract_text("h1")

``__exit__`` always closes the page, context, browser, and Playwright runtime.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from tools.web.errors import BrowserError

DEFAULT_TIMEOUT_MS = 15000
DEFAULT_NAV_TIMEOUT_MS = 30000

# Chromium flag that drops the most common automation fingerprint. Applied to
# every launch (harmless when already headed). Paired with the UA cleanup in
# ``_apply_stealth`` so consumer web apps (notably WhatsApp Web, which gates on
# a "HeadlessChrome" UA) load normally instead of the "update Chrome" page.
_STEALTH_ARGS = ("--disable-blink-features=AutomationControlled",)


@runtime_checkable
class BrowserDriver(Protocol):
    """The surface every action/step relies on. Implemented for real by
    ``PlaywrightDriver`` and faked in tests. Keep this minimal and stable -
    other tools import against this contract."""

    def goto(self, url: str, *, timeout: int | None = None) -> None: ...

    def click(self, selector: str, *, timeout: int | None = None,
              force: bool = False) -> None: ...

    def hover(self, selector: str, *, timeout: int | None = None) -> None: ...

    def context_click(self, selector: str, *, timeout: int | None = None) -> None: ...

    def mouse_click(self, x: float, y: float, *, button: str = "left",
                    move_first: bool = True) -> None: ...

    def capture_download(self, resolve_path, trigger,
                         *, timeout: int | None = None) -> dict: ...

    def fill(self, selector: str, text: str, *, timeout: int | None = None) -> None: ...

    def press(self, key: str, *, selector: str | None = None) -> None: ...

    def type_text(self, text: str, *, selector: str | None = None,
                  timeout: int | None = None) -> None: ...

    def wait(self, ms: int) -> None: ...

    def wait_for(self, selector: str, *, timeout: int | None = None) -> None: ...

    def extract_text(self, selector: str | None = None,
                     *, timeout: int | None = None) -> str: ...

    def extract_attr(self, selector: str, attr: str,
                     *, timeout: int | None = None) -> str | None: ...

    def inner_html(self, selector: str, *, timeout: int | None = None) -> str: ...

    def eval_js(self, script: str, *, arg: Any = None) -> Any: ...

    def set_input_files(self, selector: str, files: Any,
                        *, timeout: int | None = None) -> None: ...

    def set_files_via_chooser(self, trigger_selector: str, files: Any,
                              *, timeout: int | None = None) -> None: ...

    def screenshot(self, path: str, *, full_page: bool = True) -> str: ...

    def render_pdf(self, html: str, path: str, *, fmt: str = "A4") -> str: ...

    def current_url(self) -> str: ...

    def get_cookies(self) -> list: ...

    def add_cookies(self, cookies: list) -> None: ...


class PlaywrightDriver:
    """Production ``BrowserDriver`` backed by Playwright's sync API.

    Parameters
    ----------
    storage_state:
        A Playwright storageState dict (from a saved session) or None for an
        anonymous context.
    headless:
        Run without a visible window. Defaults True. ``save-session`` passes
        False so the human can log in.
    channel:
        Optional Chromium channel ("chrome", "msedge"). When None, the bundled
        Chromium build is used.
    default_timeout:
        Per-action default timeout in ms (selectors, fills, clicks).
    """

    def __init__(self, *, storage_state: dict | None = None, headless: bool = True,
                 channel: str | None = None, user_data_dir: str | None = None,
                 default_timeout: int = DEFAULT_TIMEOUT_MS,
                 nav_timeout: int = DEFAULT_NAV_TIMEOUT_MS,
                 extra_args: list | None = None):
        self._storage_state = storage_state
        # Extra Chromium launch flags (e.g. fake-mic for voice notes).
        self._extra_args = list(extra_args or [])
        self._headless = headless
        self._channel = channel
        # When set, use a PERSISTENT context (Chromium user-data-dir) instead of
        # launch()+new_context(storage_state). Required for IndexedDB-auth sites
        # like WhatsApp Web. Mutually exclusive with storage_state.
        self._user_data_dir = user_data_dir
        self._default_timeout = default_timeout
        self._nav_timeout = nav_timeout
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        # runtime diagnostics collected during a session: console errors/warnings,
        # uncaught page errors, failed requests, and HTTP error responses (>=400).
        # This is the observability that lets verification SEE runtime failures
        # (a 400 launch, a JS exception) instead of only guessing from a screenshot.
        self._diag = {"console": [], "page_errors": [], "failed_requests": [], "bad_responses": []}

    # --- lifecycle --------------------------------------------------------
    def start(self) -> "PlaywrightDriver":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - env without playwright
            raise BrowserError(
                "playwright is not installed. Run: uv add playwright"
            ) from exc
        try:
            self._pw = sync_playwright().start()
            if self._user_data_dir is not None:
                # Persistent profile: one call returns a context (no separate
                # browser object). The native on-disk profile carries the login.
                ctx_kwargs: dict[str, Any] = {"headless": self._headless,
                                              "args": list(_STEALTH_ARGS) + self._extra_args}
                if self._channel:
                    ctx_kwargs["channel"] = self._channel
                self._context = self._pw.chromium.launch_persistent_context(
                    self._user_data_dir, **ctx_kwargs)
                self._browser = None
            else:
                launch_kwargs: dict[str, Any] = {"headless": self._headless,
                                                 "args": list(_STEALTH_ARGS) + self._extra_args}
                if self._channel:
                    launch_kwargs["channel"] = self._channel
                self._browser = self._pw.chromium.launch(**launch_kwargs)
                ctx_kwargs = {}
                if self._storage_state is not None:
                    ctx_kwargs["storage_state"] = self._storage_state
                self._context = self._browser.new_context(**ctx_kwargs)
            self._context.set_default_timeout(self._default_timeout)
            self._context.set_default_navigation_timeout(self._nav_timeout)
            # A persistent context opens with one page already; reuse it.
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
            self._attach_diagnostics()
            # Strip the headless/automation fingerprint so consumer web apps
            # load (WhatsApp Web rejects the "HeadlessChrome" UA). Best-effort.
            self._apply_stealth()
        except Exception as exc:  # noqa: BLE001
            self.close()
            raise _wrap(exc)
        return self

    def _attach_diagnostics(self) -> None:
        """Listen for console errors/warnings, uncaught page errors, failed requests
        and HTTP >=400 responses. Best-effort; capping each list keeps memory bounded."""
        d = self._diag

        def _cap(key, item):
            if len(d[key]) < 100:
                d[key].append(item)

        def _console(msg):
            try:
                if msg.type in ("error", "warning"):
                    _cap("console", {"type": msg.type, "text": (msg.text or "")[:500]})
            except Exception:  # noqa: BLE001
                pass

        def _pageerror(err):
            try:
                _cap("page_errors", str(err)[:500])
            except Exception:  # noqa: BLE001
                pass

        def _reqfailed(req):
            try:
                _cap("failed_requests", {"url": (req.url or "")[:200], "method": req.method,
                                         "failure": str(getattr(req, "failure", "") or "")[:200]})
            except Exception:  # noqa: BLE001
                pass

        def _response(resp):
            try:
                if resp.status >= 400:
                    _cap("bad_responses", {"url": (resp.url or "")[:200], "status": resp.status})
            except Exception:  # noqa: BLE001
                pass
        try:
            self._page.on("console", _console)
            self._page.on("pageerror", _pageerror)
            self._page.on("requestfailed", _reqfailed)
            self._page.on("response", _response)
        except Exception:  # noqa: BLE001 - diagnostics must never break a launch
            pass

    def diagnostics(self) -> dict:
        """Snapshot of runtime issues seen so far: console errors/warnings, uncaught
        page errors, failed requests, HTTP >=400 responses. Empty lists = clean run."""
        return {k: list(v) for k, v in self._diag.items()}

    def _apply_stealth(self) -> None:
        """Make automated Chromium pass as a normal browser.

        Two fingerprints break consumer web apps under automation: the
        User-Agent (default headless Chromium reports "HeadlessChrome", which
        WhatsApp Web's browser-support gate rejects, so it never reaches the
        chat list) and ``navigator.webdriver``. We drop "Headless" from the UA
        via CDP's ``Network.setUserAgentOverride`` (dynamic — no hard-coded
        version) and shadow ``navigator.webdriver`` for future navigations.
        Every step is guarded: stealth must never break a launch."""
        try:
            self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        except Exception:  # noqa: BLE001 - best-effort hardening
            pass
        try:
            ua = self._page.evaluate("navigator.userAgent")
            if ua and "Headless" in ua:
                clean = ua.replace("HeadlessChrome", "Chrome")
                client = self._context.new_cdp_session(self._page)
                client.send("Network.setUserAgentOverride", {"userAgent": clean})
        except Exception:  # noqa: BLE001 - best-effort hardening
            pass

    def __enter__(self) -> "PlaywrightDriver":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        for obj, meth in (
            (self._context, "close"),
            (self._browser, "close"),
            (self._pw, "stop"),
        ):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        self._page = self._context = self._browser = self._pw = None

    # --- helpers ----------------------------------------------------------
    @property
    def page(self):
        if self._page is None:
            raise BrowserError("driver not started; call start() or use as a context manager")
        return self._page

    def storage_state(self, *, indexed_db: bool = True) -> dict:
        """Capture the current context's cookies + localStorage (+ IndexedDB).

        IndexedDB capture (Playwright >=1.51) is ON by default: sites like
        WhatsApp Web keep their auth/session in IndexedDB, so a cookies+
        localStorage-only snapshot does NOT restore the login. Restoration is
        automatic — `new_context(storage_state=...)` replays IndexedDB too."""
        if self._context is None:
            raise BrowserError("driver not started")
        try:
            return self._context.storage_state(indexed_db=indexed_db)
        except TypeError:
            # Older Playwright without the indexed_db kwarg — degrade gracefully.
            return self._context.storage_state()

    # --- BrowserDriver surface -------------------------------------------
    def goto(self, url: str, *, timeout: int | None = None) -> None:
        try:
            self.page.goto(url, timeout=timeout or self._nav_timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"url": url})

    def click(self, selector: str, *, timeout: int | None = None,
              force: bool = False) -> None:
        """``force`` skips the actionability wait. Some frameworks paint a
        container over their own controls, so the hit test at the element's
        centre returns that container and the click is refused even though a
        person can press the control. Use it only when that is what is
        happening: it also skips the visibility check, so a genuinely hidden
        element will be "clicked" with no effect and no error."""
        try:
            self.page.click(selector, timeout=timeout or self._default_timeout,
                            force=force)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector, "force": force})

    def hover(self, selector: str, *, timeout: int | None = None) -> None:
        """Move the mouse over the element - for UIs that reveal controls on
        hover (e.g. WhatsApp Web's per-message context-menu chevron)."""
        try:
            self.page.hover(selector, timeout=timeout or self._default_timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def context_click(self, selector: str, *, timeout: int | None = None) -> None:
        """Right-click the element - for app-rendered context menus (e.g.
        WhatsApp Web's per-message menu, which opens on right-click)."""
        try:
            self.page.click(selector, button="right",
                            timeout=timeout or self._default_timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def fill(self, selector: str, text: str, *, timeout: int | None = None) -> None:
        try:
            self.page.fill(selector, text, timeout=timeout or self._default_timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def press(self, key: str, *, selector: str | None = None) -> None:
        try:
            if selector:
                self.page.press(selector, key)
            else:
                self.page.keyboard.press(key)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"key": key, "selector": selector})

    def type_text(self, text: str, *, selector: str | None = None,
                  timeout: int | None = None) -> None:
        """Type ``text`` via real keyboard events into the focused element.

        Unlike ``fill`` (which sets the value of a DOM <input>/<textarea> by
        selector), this drives ``keyboard.type`` so the keystrokes reach targets
        that are NOT addressable in the DOM - e.g. a <canvas>-rendered grid like
        Google Sheets, where you first jump to a cell via the Name Box and then
        type into the now-focused canvas. If ``selector`` is given it is clicked
        first to take focus; otherwise typing goes to whatever is focused."""
        try:
            if selector:
                self.page.click(selector, timeout=timeout or self._default_timeout)
            self.page.keyboard.type(text)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def wait(self, ms: int) -> None:
        """Sleep ``ms`` milliseconds (fixed delay).

        For settling after an async action with no selector to await - e.g.
        letting a debounced autosave flush before reading back. Prefer
        ``wait_for`` on a selector when one exists; this is the blunt fallback."""
        try:
            self.page.wait_for_timeout(ms)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"ms": ms})

    def wait_for(self, selector: str, *, timeout: int | None = None) -> None:
        try:
            self.page.wait_for_selector(selector, timeout=timeout or self._default_timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    # --- frame-aware helpers ---------------------------------------------
    # Some SPA overlays (e.g. LinkedIn's message compose bubble) render their
    # input into a CHILD frame and/or seconds after the click, so a main-frame
    # page.evaluate snapshot misses them. These poll the main frame AND every
    # child frame with auto-waiting locators until the selector shows up.

    def find_in_frames(self, selector: str, *, timeout: int | None = None,
                       step_ms: int = 400) -> int:
        """Index of the first frame (0 = main) with ``selector`` VISIBLE, polling
        until ``timeout``; -1 if none. Frame order matches ``self.page.frames``."""
        t = timeout or self._default_timeout
        waited = 0
        while True:
            for i, fr in enumerate(self.page.frames):
                try:
                    loc = fr.locator(selector).first
                    if loc.count() > 0 and loc.is_visible():
                        return i
                except Exception:  # noqa: BLE001 - a frame may be detached mid-poll
                    continue
            if waited >= t:
                return -1
            self.page.wait_for_timeout(step_ms)
            waited += step_ms

    def frame_click(self, frame_index: int, selector: str,
                    *, timeout: int | None = None) -> None:
        t = timeout or self._default_timeout
        loc = self.page.frames[frame_index].locator(selector).first
        try:
            try:
                loc.click(timeout=t)
            except Exception:  # noqa: BLE001 - actionability check failed; scroll + force
                try:
                    loc.scroll_into_view_if_needed(timeout=t)
                except Exception:  # noqa: BLE001
                    pass
                loc.click(timeout=t, force=True)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"frame": frame_index, "selector": selector})

    def frame_type(self, frame_index: int, selector: str, text: str,
                   *, timeout: int | None = None) -> None:
        """Focus ``selector`` in a frame then type via keyboard so the keystrokes
        reach a contenteditable that ``fill`` can't set. Uses ``focus()`` (no
        pointer-event actionability check, which the compose box in a child frame
        can fail), falling back to a forced click."""
        t = timeout or self._default_timeout
        loc = self.page.frames[frame_index].locator(selector).first
        try:
            # locator.evaluate runs JS on the EXACT element Playwright matched -
            # shadow-DOM aware AND with no viewport actionability check, so it works
            # even when the compose box renders inside a web component / off-viewport
            # (a plain document.querySelector can't see into an open shadow root).
            try:
                loc.evaluate("el => { try { el.scrollIntoView({block:'center'}); } catch(e){} el.focus(); }")
            except Exception:  # noqa: BLE001 - fall back to the actionable path
                loc.focus(timeout=t)
            self.page.keyboard.type(text)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"frame": frame_index, "selector": selector})

    def frame_el_click(self, frame_index: int, selector: str,
                       *, timeout: int | None = None) -> bool:
        """Click the matched element via ``locator.evaluate`` - shadow-DOM aware and
        with no viewport actionability check, for a Send button that renders
        off-viewport or inside a web component. Returns True if clicked (not disabled)."""
        try:
            return bool(self.page.frames[frame_index].locator(selector).first.evaluate(
                "el => { if (el.disabled) return false; el.click(); return true; }"))
        except Exception:  # noqa: BLE001
            return False

    def frame_count(self, frame_index: int, selector: str) -> int:
        """Count elements matching ``selector`` in a frame via a Playwright
        locator (shadow-DOM aware). Used to detect stale/extra compose bubbles."""
        try:
            return int(self.page.frames[frame_index].locator(selector).count())
        except Exception:  # noqa: BLE001
            return 0

    def _scoped(self, frame_index: int, container_sel: str, has_text: str, inner_sel: str):
        """Locator for ``inner_sel`` inside the ``container_sel`` element that
        CONTAINS ``has_text`` - e.g. the compose box inside the conversation bubble
        addressed to a specific person. filter(has_text=...) is Unicode-safe and
        shadow-DOM aware, so it targets the RIGHT box even when stale bubbles are open."""
        fr = self.page.frames[frame_index]
        return fr.locator(container_sel).filter(has_text=has_text).locator(inner_sel)

    def frame_scoped_count(self, frame_index: int, container_sel: str, has_text: str,
                           inner_sel: str) -> int:
        try:
            return int(self._scoped(frame_index, container_sel, has_text, inner_sel).count())
        except Exception:  # noqa: BLE001
            return 0

    def frame_scoped_text(self, frame_index: int, container_sel: str, has_text: str,
                          inner_sel: str) -> str:
        try:
            return self._scoped(frame_index, container_sel, has_text, inner_sel).first.inner_text(
                timeout=self._default_timeout) or ""
        except Exception:  # noqa: BLE001
            return ""

    def frame_scoped_type(self, frame_index: int, container_sel: str, has_text: str,
                          inner_sel: str, text: str, *, timeout: int | None = None) -> None:
        loc = self._scoped(frame_index, container_sel, has_text, inner_sel).first
        try:
            try:
                loc.evaluate("el => { try { el.scrollIntoView({block:'center'}); } catch(e){} el.focus(); }")
            except Exception:  # noqa: BLE001
                loc.focus(timeout=timeout or self._default_timeout)
            self.page.keyboard.type(text)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"frame": frame_index, "container": container_sel, "has_text": has_text})

    def frame_scoped_click(self, frame_index: int, container_sel: str, has_text: str,
                           inner_sel: str) -> bool:
        try:
            return bool(self._scoped(frame_index, container_sel, has_text, inner_sel).first.evaluate(
                "el => { if (el.disabled) return false; el.click(); return true; }"))
        except Exception:  # noqa: BLE001
            return False

    def frame_bubble_recipients(self, frame_index: int, container_sel: str,
                                inner_sels: list) -> list:
        """For EACH container matching ``container_sel``, the first non-empty
        inner_text among ``inner_sels`` (tried in order). Returns a list aligned to
        container index - lets the caller pick the bubble addressed to a person with
        diacritic-insensitive matching in Python (Playwright has_text cannot)."""
        try:
            bubbles = self.page.frames[frame_index].locator(container_sel)
            out = []
            for i in range(bubbles.count()):
                txt = ""
                for sel in inner_sels:
                    loc = bubbles.nth(i).locator(sel)
                    if loc.count():
                        txt = loc.first.inner_text(timeout=self._default_timeout) or ""
                        if txt.strip():
                            break
                out.append(txt)
            return out
        except Exception:  # noqa: BLE001
            return []

    def frame_nth_text(self, frame_index: int, container_sel: str, index: int,
                       inner_sel: str) -> str:
        try:
            return self.page.frames[frame_index].locator(container_sel).nth(index).locator(
                inner_sel).first.inner_text(timeout=self._default_timeout) or ""
        except Exception:  # noqa: BLE001
            return ""

    def frame_nth_type(self, frame_index: int, container_sel: str, index: int,
                       inner_sel: str, text: str, *, timeout: int | None = None) -> None:
        loc = self.page.frames[frame_index].locator(container_sel).nth(index).locator(inner_sel).first
        try:
            try:
                loc.evaluate("el => { try { el.scrollIntoView({block:'center'}); } catch(e){} el.focus(); }")
            except Exception:  # noqa: BLE001
                loc.focus(timeout=timeout or self._default_timeout)
            self.page.keyboard.type(text)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"frame": frame_index, "container": container_sel, "index": index})

    def frame_nth_click(self, frame_index: int, container_sel: str, index: int,
                        inner_sel: str) -> bool:
        try:
            return bool(self.page.frames[frame_index].locator(container_sel).nth(index).locator(
                inner_sel).first.evaluate("el => { if (el.disabled) return false; el.click(); return true; }"))
        except Exception:  # noqa: BLE001
            return False

    def frame_text(self, frame_index: int, selector: str,
                   *, timeout: int | None = None) -> str:
        try:
            return self.page.frames[frame_index].locator(selector).first.inner_text(
                timeout=timeout or self._default_timeout) or ""
        except Exception:  # noqa: BLE001 - best-effort read for the recipient gate
            return ""

    def frame_eval(self, frame_index: int, script: str, *, arg: Any = None) -> Any:
        """Evaluate JS inside a specific frame. Used to click a button that renders
        off-viewport (a JS ``.click()`` ignores Playwright's viewport actionability
        check, and a real <button> fires its handler)."""
        try:
            return self.page.frames[frame_index].evaluate(script, arg)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"frame": frame_index, "script": script[:120]})

    def extract_text(self, selector: str | None = None,
                     *, timeout: int | None = None) -> str:
        try:
            if selector:
                el = self.page.wait_for_selector(
                    selector, timeout=timeout or self._default_timeout
                )
                return (el.inner_text() if el else "") or ""
            return self.page.inner_text("body") or ""
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def extract_attr(self, selector: str, attr: str,
                     *, timeout: int | None = None) -> str | None:
        try:
            el = self.page.wait_for_selector(
                selector, timeout=timeout or self._default_timeout
            )
            return el.get_attribute(attr) if el else None
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector, "attr": attr})

    def inner_html(self, selector: str, *, timeout: int | None = None) -> str:
        """Return the innerHTML of the first element matching ``selector``.

        Useful for structured extraction (e.g. reading a rendered <table>'s rows
        and cells) where the joined inner_text of ``extract_text`` loses the cell
        boundaries. Waits for the element first.
        """
        try:
            el = self.page.wait_for_selector(
                selector, timeout=timeout or self._default_timeout
            )
            return (el.inner_html() if el else "") or ""
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def eval_js(self, script: str, *, arg: Any = None) -> Any:
        """Evaluate a JS expression/function in the page and return its result.

        ``script`` may be a JS expression or an arrow/function body; ``arg`` is
        passed through to Playwright's ``page.evaluate``. Returns the JSON-able
        result. Escape hatch for DOM reads not covered by the typed methods.
        """
        try:
            return self.page.evaluate(script, arg)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"script": script[:120]})

    def set_input_files(self, selector: str, files: Any,
                        *, timeout: int | None = None) -> None:
        """Set files on an ``<input type=file>`` (for uploads / media attach).

        ``files`` is a path or list of paths. The input is often hidden, so we
        set files directly rather than clicking - the standard Playwright way to
        drive a file picker (e.g. WhatsApp Web's attach -> document/photo input)."""
        try:
            self.page.set_input_files(selector, files,
                                      timeout=timeout or self._default_timeout)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": selector})

    def set_files_via_chooser(self, trigger_selector: str, files: Any,
                              *, timeout: int | None = None) -> None:
        """Attach files that live behind a NATIVE file chooser: click
        ``trigger_selector`` (e.g. a WhatsApp 'Photos & videos' menu item)
        WHILE expecting the chooser, then hand it ``files``. The only reliable
        way to attach on sites whose real ``<input type=file>`` exists only
        transiently for the chooser (WhatsApp Web) — set_input_files on a
        selector can't see it."""
        t = timeout or self._default_timeout
        try:
            with self.page.expect_file_chooser(timeout=t) as fc:
                self.page.click(trigger_selector, timeout=t)
            fc.value.set_files(files, timeout=t)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"selector": trigger_selector})

    def mouse_click(self, x: float, y: float, *, button: str = "left",
                    move_first: bool = True) -> None:
        """Click at absolute viewport COORDINATES (not a selector).

        For a target a CSS selector can't address cleanly - e.g. right-clicking
        a WhatsApp Web media bubble to open its context menu, where the Download
        control lives only in that menu. ``move_first`` mimics a human pointer
        (move, settle, then click), which some SPA menus need to register."""
        try:
            if move_first:
                self.page.mouse.move(x, y)
                self.page.wait_for_timeout(120)
            self.page.mouse.click(x, y, button=button)
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"x": x, "y": y, "button": button})

    def capture_download(self, resolve_path, trigger,
                         *, timeout: int | None = None) -> dict:
        """Capture a browser DOWNLOAD started by ``trigger`` and save it.

        ``trigger`` is a zero-arg callable that performs the click which starts
        the download (e.g. clicking a context-menu 'Download' item); it MUST run
        inside Playwright's ``expect_download`` scope, because the listener is
        armed before the click and resolves when the transfer begins. Once the
        download object exists we know its ``suggested_filename``, so
        ``resolve_path(suggested) -> final_path`` lets the caller decide the
        destination (a directory + the WhatsApp filename, or an explicit path).
        The parent dir is created; returns
        ``{suggested_filename, saved_path, trigger_result}``. Downloads work
        headless too - accept_downloads defaults True on launch() and
        launch_persistent_context()."""
        import os as _os
        t = timeout or self._nav_timeout
        try:
            with self.page.expect_download(timeout=t) as dl:
                trigger_result = trigger()
            download = dl.value
            suggested = download.suggested_filename
            final = resolve_path(suggested)
            parent = _os.path.dirname(_os.path.abspath(final))
            if parent:
                _os.makedirs(parent, exist_ok=True)
            download.save_as(final)
            return {"suggested_filename": suggested, "saved_path": str(final),
                    "trigger_result": trigger_result}
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"download": True})

    def screenshot(self, path: str, *, full_page: bool = True) -> str:
        try:
            self.page.screenshot(path=path, full_page=full_page)
            return path
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"path": path})

    def render_pdf(self, html: str, path: str, *, fmt: str = "A4") -> str:
        """Render an HTML string to a PDF file via Chromium's print engine.

        ``page.pdf()`` is Chromium/headless-only (the driver's default); it lays
        the HTML out with print CSS and writes ``path``. Used for deterministic
        document generation (e.g. reconstructing an invoice) with no live site.
        """
        try:
            self.page.set_content(html, wait_until="load")
            self.page.pdf(
                path=path, format=fmt, print_background=True,
                margin={"top": "12mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
            )
            return path
        except Exception as exc:  # noqa: BLE001
            raise _wrap(exc, {"path": path})

    def current_url(self) -> str:
        return self.page.url

    # --- cookies ----------------------------------------------------------
    def get_cookies(self) -> list:
        """Return ALL cookies in the current context (every domain).

        Crucially this includes *session-scoped* cookies (no Expires/Max-Age)
        while the browser is alive — exactly the ones Chromium will NOT write to
        a persistent profile on disk. ``save_session`` snapshots these so they
        can be re-injected on the next open. Returns [] if the context is gone."""
        if self._context is None:
            return []
        try:
            return list(self._context.cookies())
        except Exception:  # noqa: BLE001 - best-effort; never break a save
            return []

    def add_cookies(self, cookies: list) -> None:
        """Inject cookies into the current context (before navigating).

        Accepts the same dicts ``get_cookies`` returns (domain+path+value+...),
        so a saved sidecar round-trips. Best-effort: a bad cookie list must not
        prevent the profile from opening — we drop entries Playwright rejects."""
        if self._context is None or not cookies:
            return
        try:
            self._context.add_cookies(cookies)
        except Exception:  # noqa: BLE001
            # Fall back to injecting valid entries one-by-one so one malformed
            # cookie can't sink the whole (still-authenticating) batch.
            for c in cookies:
                try:
                    self._context.add_cookies([c])
                except Exception:  # noqa: BLE001
                    pass


def _wrap(exc: Exception, details: dict | None = None) -> BrowserError:
    """Normalize any Playwright exception into a BrowserError with details."""
    if isinstance(exc, BrowserError):
        return exc
    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return BrowserError(msg, details or {})
