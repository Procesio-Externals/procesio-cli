"""Error classification -> framework envelope (code, message, details, exit)."""
from __future__ import annotations

from tools.web.errors import (
    BrowserError,
    SessionError,
    UsageError,
    classify,
)


def test_usage_error_maps_to_invalid_argument_exit_2():
    code, msg, details, exit_code = classify(UsageError("bad arg"))
    assert code == "invalid_argument"
    assert exit_code == 2
    assert msg == "bad arg"


def test_session_error_maps_to_session_not_found():
    code, msg, details, exit_code = classify(SessionError("no session"))
    assert code == "session_not_found"
    assert exit_code == 1


def test_browser_error_carries_details():
    code, msg, details, exit_code = classify(
        BrowserError("nav timeout", {"url": "https://x"})
    )
    assert code == "browser_error"
    assert exit_code == 1
    assert details == {"url": "https://x"}


def test_generic_exception_maps_to_error():
    code, msg, details, exit_code = classify(RuntimeError("boom"))
    assert code == "error"
    assert exit_code == 1
    assert msg == "boom"


def test_empty_message_falls_back_to_class_name():
    code, msg, _details, _exit = classify(ValueError())
    assert code == "error"
    assert msg == "ValueError"


class _FakePlaywrightTimeout(Exception):
    pass


_FakePlaywrightTimeout.__module__ = "playwright._impl._errors"
_FakePlaywrightTimeout.__name__ = "TimeoutError"


def test_playwright_error_classname_maps_to_browser_error():
    # Simulate a raw playwright error reaching classify without our wrapper.
    exc = _FakePlaywrightTimeout("Timeout 30000ms exceeded")
    code, msg, _details, exit_code = classify(exc)
    assert code == "browser_error"
    assert exit_code == 1
