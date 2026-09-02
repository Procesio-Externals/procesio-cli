"""Map exceptions to the framework error envelope: (code, message, details, exit).

JSON in / JSON out: every uncaught exception becomes an {"error": {...}} object.
We classify by exception type so an auth failure, a bad argument, and an HTTP
4xx/5xx each surface with a distinct, stable code.
"""
from __future__ import annotations

from typing import Any


class UsageError(Exception):
    """Bad/invalid arguments. Maps to 'invalid_argument', exit 2."""


class CredentialError(Exception):
    """No usable credential (neither api-key nor username+password stored).
    Maps to 'auth_required', exit 1."""


class ApiError(Exception):
    """A non-2xx HTTP response from the connector-builder API.
    Maps to 'api_error', exit 1. Carries status + the server's detail."""

    def __init__(self, status_code: int, path: str, detail: str = "",
                 details: dict[str, Any] | None = None):
        self.status_code = status_code
        self.path = path
        self.detail = (detail or "")[:500]
        self.details = details or {}
        self.details.setdefault("status_code", status_code)
        self.details.setdefault("path", path)
        super().__init__(f"{status_code} on {path}: {self.detail}")


def classify(exc: Exception) -> tuple[str, str, dict, int]:
    if isinstance(exc, UsageError):
        return "invalid_argument", str(exc) or "invalid argument", {}, 2
    if isinstance(exc, CredentialError):
        return "auth_required", str(exc), {}, 1
    if isinstance(exc, ApiError):
        code = "auth_failed" if exc.status_code in (401, 403) else "api_error"
        return code, str(exc), exc.details, 1
    return "error", str(exc) or exc.__class__.__name__, {"type": type(exc).__name__}, 1
