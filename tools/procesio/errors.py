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


class RemovalBlocked(Exception):
    """A desired-state save was blocked because it would REMOVE actions or variables
    that exist on the live resource. Carries what would disappear so the caller can see
    it before paying for it. Maps to 'removal_blocked', exit code 2. Intentional
    removals pass --allow-remove.

    Separate from ValidationBlocked on purpose: --force answers "save it even though it
    is invalid", which is a different question from "yes, delete those". A half-built
    process is a legitimate thing to force-save WITHOUT wanting to drop anything.
    """

    def __init__(self, message: str, removed: dict | None = None):
        super().__init__(message)
        self.removed = removed or {}


class DocumentationMissing(Exception):
    """A process save was refused because the process does not document itself: no process
    purpose (`description`), an action with no purpose of its own (`description` on the action,
    stored as customData.description) or one still carrying the template's stock caption, or,
    on a process with more than 3 actions besides Start and Stop, actions that sit in no area
    (`groups`, drawn as canvas shapes). An edit also stops here when an action changed what it
    does and its description was not restated. Maps to 'documentation_missing', exit 2.
    `--allow-undocumented` saves anyway and reports the gaps."""

    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


class DesignerUnrenderable(Exception):
    """A process save was refused because the designer could not draw the result: a node
    without a `customData.configuration` key, or with a canvas shape the engine does not know.
    The runtime would still run it, so nothing else catches this; the designer and every
    instance view would load forever with no error. Maps to 'designer_unrenderable', exit 2.
    Fix the nodes (`procesio node-repair-designer`) instead of saving them."""

    def __init__(self, message: str, nodes: list | None = None):
        super().__init__(message)
        self.nodes = nodes or []


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


class NotPersisted(Exception):
    """A write returned 2xx but a read-back shows the server kept the OLD value. PROCESIO does
    this silently in places (a FormTemplate write that drops Data: the PUT succeeds, updatedOn
    moves, the previous content stays). Maps to 'not_persisted', exit code 1. Carries what was
    sent vs what is stored."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


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


# PROCESIO's own coded refusals (the Web API's error_config codes) arrive as a JSON LIST,
# `[{"statusCode": <code>, "value": "<message>", "target": <field or feature>}]`, which the
# client wraps as {"body": [...]}. 1013 FEATURE_DISABLED is the one a caller can act on
# without reading the message: the installation switched that optional module off.
_FEATURE_DISABLED = 1013


def procesio_error_items(details: Any) -> list[dict]:
    """The coded error items of a PROCESIO error body, or [] when it has none."""
    body = details.get("body") if isinstance(details, dict) else details
    if not isinstance(body, list):
        return []
    return [i for i in body if isinstance(i, dict) and "statusCode" in i]


def _reason_from_items(items: list[dict]) -> str:
    parts = []
    for i in items:
        text = str(i.get("value") or "").strip() or "refused"
        target = i.get("target")
        where = f" [{target}]" if target not in (None, "", []) else ""
        parts.append(f"{text} (code {i.get('statusCode')}){where}")
    return "; ".join(parts)


def _reason_from_body(details: Any) -> str:
    """PROCESIO error bodies vary: {"message": ...}, {"error": ...},
    {"errors": {...}}, an ASP.NET ProblemDetails {"title": ..., "errors": {...}}, or
    the Web API's coded list [{"statusCode", "value", "target"}] (wrapped as {"body": [...]})."""
    items = procesio_error_items(details)
    if items:
        return _reason_from_items(items)
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
    if isinstance(exc, NotPersisted):
        return "not_persisted", str(exc), exc.details, 1
    if isinstance(exc, RemovalBlocked):
        return "removal_blocked", str(exc), exc.removed, 2
    if isinstance(exc, DocumentationMissing):
        return "documentation_missing", str(exc), exc.report, 2
    if isinstance(exc, DesignerUnrenderable):
        return "designer_unrenderable", str(exc), {
            "nodes": exc.nodes, "fix": "procesio node-repair-designer --id <process id>"}, 2
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
        out = {"status": exc.status, "body": exc.details}
        items = procesio_error_items(exc.details)
        if items:
            out["procesio_codes"] = [i.get("statusCode") for i in items]
        disabled = [i.get("target") for i in items if i.get("statusCode") == _FEATURE_DISABLED]
        if disabled:
            # Not a malformed request: this installation has the module switched off, so
            # retrying with other arguments cannot help. Name it and point at the check.
            out["features_disabled"] = disabled
            out["hint"] = ("this PROCESIO environment has that optional feature switched off; "
                           "`procesio features` shows which modules are on")
            return "feature_disabled", msg, out, 1
        return code, msg, out, exit_code
    return "error", str(exc) or exc.__class__.__name__, {}, 1
