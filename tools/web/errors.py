"""Map exceptions to the framework error envelope: (code, message, details, exit_code).

The web tool raises:
  - UsageError       bad/missing CLI args or a malformed step    -> invalid_argument, exit 2
  - SessionError     a named session file is missing/corrupt     -> session_not_found, exit 1
  - BrowserError     Playwright failed (nav timeout, missing      -> browser_error,      exit 1
                     browser binary, selector not found, etc.)
Anything else -> generic 'error', exit 1.

Playwright is imported lazily everywhere so this module (and the tests) load
even when the browser binaries are not installed yet.
"""
from __future__ import annotations

from typing import Any


class UsageError(Exception):
    """Bad/invalid arguments or step schema. Maps to 'invalid_argument', exit 2."""


class SessionError(Exception):
    """A named session is missing or its storageState file is unreadable.

    Maps to 'session_not_found', exit 1.
    """


class BrowserError(Exception):
    """A Playwright operation failed (navigation, selector, missing binary, ...).

    ``details`` is surfaced under the error envelope's details when present.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.details = details or {}
        super().__init__(message)


def classify(exc: Exception) -> tuple[str, str, dict, int]:
    if isinstance(exc, UsageError):
        return "invalid_argument", str(exc), {}, 2
    if isinstance(exc, SessionError):
        return "session_not_found", str(exc), {}, 1
    if isinstance(exc, BrowserError):
        return "browser_error", str(exc) or exc.__class__.__name__, exc.details, 1
    # Playwright raises its own Error/TimeoutError types. Map them generically
    # to browser_error by class-name sniffing so we never import playwright here.
    cls = exc.__class__.__name__
    if cls in {"Error", "TimeoutError"} and "playwright" in (
        type(exc).__module__ or ""
    ):
        return "browser_error", str(exc) or cls, {}, 1
    return "error", str(exc) or cls, {}, 1
