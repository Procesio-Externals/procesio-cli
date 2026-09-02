"""Map exceptions to the framework error envelope: (code, message, details, exit_code).

PROCESIO's Web API is ASP.NET/Kestrel behind a Kong gateway, so a request can
fail at three layers: argument validation (UsageError), missing/invalid
credentials before any HTTP call (AuthError), or a non-2xx HTTP response
(ProcesioAPIError). classify() turns each into a stable string code so callers
(and the outreach agent) can branch without parsing prose.

Notable status semantics observed against the live gateway:
  401  Bearer/api-key rejected by the Web API (Kestrel).
  403  authenticated but not permitted in this workspace.
  404  Kong "no Route matched" OR a real not-found from the app.
  407  the Web API could not complete the upstream Proxy-API auth leg
       (its own /api/Authentication proxies to the Authentication Service).
"""
from __future__ import annotations

from typing import Any


class UsageError(Exception):
    """Bad/invalid arguments. Maps to 'invalid_argument', exit code 2."""


class AuthError(Exception):
    """Missing/invalid credentials before any HTTP call. -> auth_required."""


class ProcesioAPIError(Exception):
    """A non-2xx HTTP response from PROCESIO. Carries status + parsed body."""

    def __init__(self, status: int, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


class ValidationBlocked(Exception):
    """A save was blocked because front-end (designer) and/or back-end validation found
    errors. Carries the full report so the caller can see exactly what to fix. Maps to
    'validation_failed', exit code 2. Bypassable with --force."""

    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


class DeadlineExceeded(Exception):
    """A request exceeded its TOTAL wall-clock deadline (see reliability.py). The
    old client had no total deadline — a stalled call ran until SIGKILL. This makes
    the stall a structured, machine-readable failure instead. `outcome` is always
    'unknown' for a write: the request MAY have applied server-side, so the caller
    must verify behaviourally, never assume it did or did not land."""

    def __init__(self, path: str, endpoint_class: str, deadline_s: float,
                 elapsed_s: float):
        super().__init__(
            f"request exceeded the {endpoint_class} deadline of "
            f"{deadline_s:.0f}s (elapsed {elapsed_s:.1f}s): {path}")
        self.path = path
        self.endpoint_class = endpoint_class
        self.deadline_s = deadline_s
        self.elapsed_s = elapsed_s


_HTTP_CODES = {
    400: ("invalid_argument", "bad request - check the parameters/body"),
    401: ("auth_required", "authentication failed - token or api-key rejected"),
    403: ("permission_denied", "not permitted in this workspace"),
    404: ("not_found", "not found (or Kong route not matched)"),
    405: ("invalid_argument", "method not allowed for this path"),
    407: ("proxy_auth_failed",
          "the Web API could not authenticate against the Proxy API "
          "(check the auth_base host and credentials)"),
    409: ("conflict", "conflict"),
    422: ("invalid_argument", "unprocessable - validation failed"),
    429: ("rate_limited", "rate limit exceeded - back off and retry"),
    500: ("server_error", "PROCESIO server error"),
    502: ("server_error", "bad gateway"),
    503: ("server_error", "service unavailable"),
}


def map_http_error(status: int, reason: str = "") -> tuple[str, str, int]:
    code, default_msg = _HTTP_CODES.get(status, ("procesio_api_error", f"HTTP {status}"))
    exit_code = 2 if code == "invalid_argument" else 1
    return code, reason or default_msg, exit_code


def _reason_from_body(details: Any) -> str:
    """PROCESIO error bodies vary: {"message": ...}, {"error": ...},
    {"errors": {...}}, or an ASP.NET ProblemDetails {"title": ..., "errors": {...}}."""
    if not isinstance(details, dict):
        return ""
    for key in ("message", "error", "error_message", "reason", "title", "detail"):
        val = details.get(key)
        if isinstance(val, str) and val:
            return val
    errs = details.get("errors")
    if isinstance(errs, list) and errs:
        first = errs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("message") or first.get("error") or ""
    if isinstance(errs, dict):
        for val in errs.values():
            if isinstance(val, list) and val and isinstance(val[0], str):
                return val[0]
            if isinstance(val, str) and val:
                return val
    return ""


def classify(exc: Exception) -> tuple[str, str, dict, int]:
    if isinstance(exc, AuthError):
        return "auth_required", str(exc), {}, 1
    if isinstance(exc, UsageError):
        return "invalid_argument", str(exc), {}, 2
    if isinstance(exc, ValidationBlocked):
        return "validation_failed", str(exc), exc.report, 2
    if isinstance(exc, DeadlineExceeded):
        return "deadline_exceeded", str(exc), {
            "kind": "deadline",
            "endpoint": exc.path,
            "class": exc.endpoint_class,
            "deadline_s": exc.deadline_s,
            "elapsed_s": round(exc.elapsed_s, 2),
            "outcome": "unknown",
        }, 1
    if isinstance(exc, ProcesioAPIError):
        reason = _reason_from_body(exc.details) or str(exc)
        code, msg, exit_code = map_http_error(exc.status, reason)
        return code, msg, {"status": exc.status, "body": exc.details}, exit_code
    return "error", str(exc) or exc.__class__.__name__, {}, 1
