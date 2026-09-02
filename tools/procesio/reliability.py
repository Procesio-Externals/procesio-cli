"""Request-reliability primitives for the PROCESIO client.

Encodes, in one place, the empirical rules learned driving the live Web API (see
PROCESIO-API-NOTES.md "Empirical reliability profile" and the `procesio` agent's
`guidance --topic reliability`):

* **The client had no TOTAL deadline.** `requests`' scalar timeout is a *per-read
  inactivity* guard, not a wall-clock ceiling: a connection that is accepted and
  then dribbles bytes (or where the server holds it open) never trips it, so a
  stalled call runs until the process is killed. `run_with_deadline` adds a real
  total deadline on a daemon thread so a stall SURFACES as a structured error.
* **Retries are safe for GET only.** Re-POSTing an execution double-runs a
  process with real side effects; a timed-out PUT may already have applied. So the
  retry policy is GET-only, on transient statuses + network errors.

Everything here is stdlib-only (no new dependency) and provider-neutral.
"""
from __future__ import annotations

import os
import random
import threading

# -- knobs ------------------------------------------------------------------

# Per-read (inactivity) timeout handed to `requests` — a socket that sends no
# bytes for this long trips requests' own timeout. Kept as defense-in-depth
# UNDER the total deadline below.
READ_TIMEOUT = 60

# Total wall-clock deadlines, by endpoint class. A definition read (~120-420KB
# GET) should never legitimately take this long; a definition write (PUT) is
# given more headroom. run-process is EXEMPT (deadline=None) — a synchronous run
# of a many-action process legitimately takes minutes.
READ_DEADLINE = 90.0
WRITE_DEADLINE = 180.0

# GET-only retry policy. 500 is deliberately EXCLUDED (may be a deterministic
# server error, not transient). 429 is honoured via Retry-After when present.
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
MAX_RETRIES = 2
BACKOFF_BASE = 0.5   # seconds
BACKOFF_CAP = 8.0    # seconds

ENV_NO_DEADLINE = "AAT_PROCESIO_NO_DEADLINE"
ENV_NO_RETRY = "AAT_PROCESIO_NO_RETRY"

# Sentinel: "no explicit value passed — pick the class default". Distinct from
# None, which for a deadline means "exempt" and for a read timeout means "wait
# indefinitely" (used by synchronous run-process).
DEFAULT = object()


class DeadlineHit(Exception):
    """Raised by run_with_deadline when the total wall-clock deadline elapses.
    The client translates it into errors.DeadlineExceeded with full context."""


# -- env opt-outs -----------------------------------------------------------

def _truthy(val: str | None) -> bool:
    return bool(val) and val.strip().lower() not in ("", "0", "false", "no", "off")


def deadline_disabled() -> bool:
    return _truthy(os.environ.get(ENV_NO_DEADLINE))


def retry_disabled() -> bool:
    return _truthy(os.environ.get(ENV_NO_RETRY))


# -- deadline resolution ----------------------------------------------------

def endpoint_class(method_upper: str) -> str:
    """The deadline class of a verb: reads are cheap-and-bounded, writes get
    more headroom."""
    return "read" if method_upper == "GET" else "write"


def resolve_deadline(method_upper: str, deadline) -> float | None:
    """Turn the caller's `deadline` argument into a concrete seconds value or
    None (exempt). `DEFAULT` -> the class default; None -> exempt; a number ->
    that many seconds. The env opt-out forces exempt."""
    if deadline is None:
        return None
    if deadline_disabled():
        return None
    if deadline is DEFAULT:
        return READ_DEADLINE if method_upper == "GET" else WRITE_DEADLINE
    return float(deadline)


# -- retry policy -----------------------------------------------------------

def is_retryable(method_upper: str, status: int, attempt: int) -> bool:
    """A response is retryable only for GET, only on a transient status, and only
    while retries remain. This is the SINGLE gate — a POST/PUT can never satisfy
    it, so an execution is structurally un-retryable."""
    if retry_disabled():
        return False
    return (
        method_upper == "GET"
        and status in RETRYABLE_STATUSES
        and attempt < MAX_RETRIES
    )


def network_error_retryable(method_upper: str, attempt: int) -> bool:
    """Connection/read errors are retryable for GET only (we cannot know whether
    a POST/PUT reached the server)."""
    if retry_disabled():
        return False
    return method_upper == "GET" and attempt < MAX_RETRIES


def full_jitter(attempt: int, rng: random.Random | None = None) -> float:
    """AWS-style full jitter: uniform(0, min(cap, base * 2**attempt)). `attempt`
    is 1-based (the delay before the Nth retry)."""
    ceiling = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** attempt))
    r = rng or random
    return r.uniform(0.0, ceiling)


def parse_retry_after(headers: dict | None) -> float | None:
    """Retry-After in delta-seconds form (the only form PROCESIO/Kong emit).
    Ignores HTTP-date form. Returns a capped seconds value or None."""
    if not headers:
        return None
    # Header lookup is case-insensitive on real responses; be lenient.
    raw = None
    for k, v in headers.items():
        if k.lower() == "retry-after":
            raw = v
            break
    if raw is None:
        return None
    try:
        secs = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if secs < 0:
        return None
    return min(secs, BACKOFF_CAP)


# -- total deadline ---------------------------------------------------------

def run_with_deadline(fn, timeout: float | None):
    """Run `fn()` under a TOTAL wall-clock deadline.

    `timeout` None -> run inline (no deadline). Otherwise run `fn` on a DAEMON
    thread and wait at most `timeout` seconds. On expiry raise `DeadlineHit`; the
    worker is abandoned (daemon => the interpreter never joins it, and the OS
    reclaims the leaked socket when this short-lived CLI process exits). Any
    exception raised by `fn` is re-raised in the caller.

    Why a raw daemon thread and not `ThreadPoolExecutor`: the executor's worker
    threads are joined by an interpreter atexit hook, which would HANG process
    exit on a stuck HTTP read — exactly the failure we are eliminating.

    CAVEAT — long-lived hosts (AAT_RUNNER worker pool). "The OS reclaims the
    socket on process exit" holds for the normal short-lived CLI, but NOT under
    the persistent tool-runner pool (`AAT_RUNNER=1`, tools/_lib/toolrunner),
    whose worker process outlives the call. There an abandoned worker stays
    parked on the stuck read, leaking one thread + one socket per deadline-hit
    for the pool's lifetime. Deadline-hits are rare (a true stall), so this is a
    slow leak, not a hot path — but a flapping endpoint under the pool will
    accumulate. If that ever bites, bound it (recycle the pool worker after N
    deadline-hits, or move the read onto a cancellable transport).
    """
    if timeout is None:
        return fn()
    if timeout <= 0:
        raise DeadlineHit()
    box: dict = {}
    done = threading.Event()

    def _worker():
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            box["exc"] = exc
        finally:
            done.set()

    t = threading.Thread(target=_worker, name="procesio-http", daemon=True)
    t.start()
    if not done.wait(timeout):
        raise DeadlineHit()
    if "exc" in box:
        raise box["exc"]
    return box["result"]
