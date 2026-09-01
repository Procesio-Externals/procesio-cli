"""Per-work-unit accounting hooks (spec P0.0-05).

On the PROCESIO platform, each span of *active* agent processing is a **work-unit**
that must feed the licensing meter: acquire an execution-environment (EE) slot on the
shared Redis semaphore (Thread licenses) and emit a ``TrackAction``-shaped consume
event with the measured ``ExecutionTime`` and ``Multiplicator`` (Time licenses). See
``todo/on-hold/procesio-aat-module/03-execution-licensing-and-tracing.md``.

Locally there is nothing to bill, so this module is a **no-op by default** - but the
*emit seam* exists now, wrapped around every AAT execution, so the platform injects a
real sink (one that speaks the semaphore + TrackAction protocols) without touching a
single call site. Build the hook, not the feature.

Design rules:
  - **Zero overhead when unused.** Default sink swallows events; no output, no import
    of anything heavy. Local Claude Code is unaffected.
  - **Active processing only.** A work-unit span covers PROCESSING; a WAITING span is
    simply not opened (the caller opens a fresh span on resume), so idle bills nothing.
  - **Exceptions still close the span** - ``consume`` is emitted on the ``finally`` so a
    failed action is still accounted for its partial time, matching PROCESIO's
    per-action TrackAction-on-finish semantics.
  - **No PROCESIO dependency.** The sink is an interface; timing uses a monotonic clock.
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from typing import Callable

# A sink is: (event: dict) -> None. Default = no-op.
_sink: Callable[[dict], None] | None = None


def _debug_sink(event: dict) -> None:
    """Optional visibility for local debugging: one JSON line per event to stderr when
    AAT_ACCOUNTING_DEBUG is truthy. Never on by default."""
    import json
    sys.stderr.write("[accounting] " + json.dumps(event, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def set_sink(sink: Callable[[dict], None] | None) -> None:
    """Install the accounting sink (the platform injects one that acquires/releases the
    EE semaphore and publishes TrackAction). ``None`` restores the default no-op."""
    global _sink
    _sink = sink


def _resolve_sink() -> Callable[[dict], None] | None:
    if _sink is not None:
        return _sink
    if os.environ.get("AAT_ACCOUNTING_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
        return _debug_sink
    return None


def emit(event: dict) -> None:
    """Send one accounting event to the configured sink (no-op if none). Never raises -
    accounting must never break an agent run."""
    sink = _resolve_sink()
    if sink is None:
        return
    try:
        sink(dict(event))
    except Exception:  # noqa: BLE001 - accounting is best-effort, never fatal
        pass


def _ctx() -> dict:
    """Active (workspace, user) from the server-established env (item P0.0-01)."""
    return {
        "ws": os.environ.get("AAT_WORKSPACE_ID") or None,
        "user": os.environ.get("AAT_USER_ID") or None,
    }


@contextmanager
def work_unit(kind: str, *, ws: str | None = None, user: str | None = None,
              run_id: str | None = None, multiplicator: float = 1.0):
    """Mark a span of ACTIVE agent processing.

    On enter: emit ``acquire`` (the platform acquires an EE slot). On exit (incl. on
    exception): emit ``consume`` with the measured ``execution_ms`` and the work-unit's
    ``multiplicator`` (the billing weight; default 1.0). The event shape mirrors
    PROCESIO's ``TrackActionDto`` so a platform sink maps it 1:1.

    Yields a small mutable dict the caller may annotate (e.g. set ``action`` / ``tool``);
    those fields ride along on the ``consume`` event.

    Usage::

        with accounting.work_unit("tool", run_id=rid) as wu:
            wu["tool"] = "ryver"
            ... do the work ...
    """
    c = _ctx()
    base = {
        "kind": kind,
        "ws": ws if ws is not None else c["ws"],
        "user": user if user is not None else c["user"],
        "run_id": run_id,
        "multiplicator": float(multiplicator),
    }
    info: dict = {}
    emit({**base, "event": "acquire", "ts": _clock_iso()})
    start = time.monotonic()
    try:
        yield info
    finally:
        execution_ms = int((time.monotonic() - start) * 1000)
        emit({**base, **info, "event": "consume", "execution_ms": execution_ms,
              "ts": _clock_iso()})


def _clock_iso() -> str:
    # Wall-clock timestamp for the event. Kept local so the module has no other deps.
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
