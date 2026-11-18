"""Runtime metrics of the aat-mcp HTTP server, in the Prometheus text exposition format (0.0.4).

Hand-rolled on the standard library, like the MCP protocol itself: the runtime image carries no
metrics client, and a counter behind a lock does not justify a dependency.

What this module guarantees, so that a call site cannot get it wrong:

  - Off unless a listener runs. Every recording helper returns at once until `start_listener`
    has bound its port (AAT_METRICS_PORT; unset or 0 = off), so the stdio server and a local run
    pay nothing and resolve no label.
  - Recording never raises into the caller and never changes what the caller returns. A metric
    that cannot be recorded is dropped.
  - Every label value comes from a fixed set. A tool name, an action or an error code can come
    from a model or from a tool's own output, so each is checked against the set it belongs to
    and replaced by `unknown` / `other` when it is not in it. Workspace, user, turn and
    credential ids are never labels.
  - Samples live in this process only. Each tool call runs in a subprocess of its own; what is
    measured is what the server sees of the call, plus the HTTP requests the subprocess noted
    in the trace file the bridge gave it (tools/_lib/httptrace.py). That file is written by the
    tool, so it is read as untrusted input: capped, validated, and its paths reduced to routes.

The listener is a second HTTP server on its own port. It serves GET /metrics and nothing else,
without authentication, so the MCP port keeps its bearer token and its own network policy.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable, NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runtime_log  # noqa: E402  (sibling module, standard library only: the one writer of log lines)

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
PATH = "/metrics"
PORT_ENV = "AAT_METRICS_PORT"

# Stand-ins for a value outside the fixed set of its label.
UNKNOWN = "unknown"  # a name the caller sent that the set it is checked against does not hold
OTHER = "other"      # a code outside the fixed codes, or the overflow row of a capped metric
NONE = "none"        # nothing was named where a name is optional

OK, ERROR, REFUSED = "ok", "error", "refused"
KINDS = ("tool", "agent")
PROCESIO_KEY, TOOL_CREDENTIALS = "procesio_key", "tool_credentials"

# Seconds. The same boundaries as the other AAT services, so one dashboard reads all of them.
STEP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
# A tool call may run up to AAT_TOOL_TIMEOUT_SECONDS (180 by default), a delegated one longer.
CALL_BUCKETS = STEP_BUCKETS + (180, 300)

# The error codes this server's own code produces; a tool's own codes are an open set and count
# as `other`. Where each comes from:
#   dashboard.server.runner._normalize   timeout, no_json, nonzero_exit
#   bridge                               host_runner_unreachable, procesio_key_unavailable,
#                                        workspace_out_of_turn, managed_turn (a refusal's reason)
#   bridge._AUTH_FAILURE_CODES           auth_required, permission_denied, unauthorized, forbidden
#   here                                 exception (the call raised instead of answering)
ERROR_CODES = frozenset({
    "timeout", "no_json", "nonzero_exit",
    "host_runner_unreachable", "procesio_key_unavailable", "workspace_out_of_turn", "managed_turn",
    "auth_required", "permission_denied", "unauthorized", "forbidden",
    "exception",
})

# Why a call was answered without starting anything. `irreversible_denied` is the confirmed path
# under AAT_MCP_DENY_IRREVERSIBLE, which has no code of its own in the payload.
REFUSAL_CODES = frozenset({
    "approval_required", "irreversible_denied", "managed_turn",
    "workspace_out_of_turn", "procesio_key_unavailable",
})

_MCP_METHODS = frozenset({"initialize", "tools/list", "tools/call"})

# Distinct (kind, tool, action) rows the per-action metric keeps. Past it a new pair is counted on its
# tool's `other` row, so the total stays this many plus at most one row per registered capability.
ACTION_SERIES_CAP = 2000

# The HTTP requests a tool noted in its trace. A route is the request path with every id-like
# segment replaced, so `/api/Projects/<guid>/versions` and its siblings are one row.
HTTP_SERIES_CAP = 400          # distinct label sets per HTTP metric; past it the route is `other`
HTTP_TRACE_MAX_BYTES = 512 * 1024
HTTP_TRACE_MAX_EVENTS = 5000
HTTP_LOG_LINES_PER_CALL = 5
SLOW_LOG_ENV = "AAT_HTTP_SLOW_LOG_SECONDS"   # a request at least this slow is logged; default 30
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_HTTP_ERRORS = frozenset({"timeout", "connection", "error"})
UNFINISHED = "unfinished"
# Why a request has a start and no end in the trace.
CALL_KILLED = "call_killed"      # the whole tool call was stopped at its time limit
TOOL_GAVE_UP = "tool_gave_up"    # the tool stopped waiting (its own deadline) and carried on
_ROUTE_MAX_SEGMENTS = 12
_ROUTE_MAX_LENGTH = 120
_ID_SEGMENT = re.compile(
    r"^(?:\d+"                                     # a number
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"   # a GUID
    r"|[0-9a-fA-F]{16,}"                           # a long hex id
    r"|.{41,})$")                                  # anything too long to be a route word
_ROUTE_WORD = re.compile(r"^[A-Za-z0-9_.\-]+$")


# --- instruments ----------------------------------------------------------------------------

def _escape(value: str, quote: bool = True) -> str:
    value = value.replace("\\", "\\\\").replace("\n", "\\n")
    return value.replace('"', '\\"') if quote else value


def _num(value) -> str:
    if isinstance(value, int):
        return str(value)
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)


class Registry:
    """A set of metrics rendered together. One lock for all of them: an update is a few
    dictionary operations, and a scrape copies the numbers under the lock and formats outside it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: list[_Metric] = []
        self._before_render: list[Callable[[], None]] = []

    def before_render(self, refresh: Callable[[], None]) -> None:
        """Run `refresh` at the start of every scrape, for a gauge whose value is computed then
        (an age) instead of kept up to date."""
        self._before_render.append(refresh)

    def render(self) -> str:
        for refresh in self._before_render:
            try:
                refresh()
            except Exception:  # noqa: BLE001 - a gauge that cannot refresh keeps its last value
                pass
        with self._lock:
            snapshot = [(m, {key: list(slot) for key, slot in m._series.items()})
                        for m in self._metrics]
        lines: list[str] = []
        for metric, series in snapshot:
            lines.append(f"# HELP {metric.name} {_escape(metric.help, quote=False)}")
            lines.append(f"# TYPE {metric.name} {metric.kind}")
            for key in sorted(series):
                lines.extend(metric._samples(key, series[key]))
        return "\n".join(lines) + "\n"

    def clear(self) -> None:
        with self._lock:
            for metric in self._metrics:
                metric._series.clear()


class _Metric:
    kind = ""

    def __init__(self, registry: Registry, name: str, help_text: str, labels: Iterable[str] = (),
                 *, max_series: int = 0, overflow: Callable[[tuple], tuple] | None = None) -> None:
        self.name, self.help, self.labels = name, help_text, tuple(labels)
        self._lock = registry._lock
        self._max, self._overflow = max_series, overflow
        self._series: dict[tuple, list] = {}
        registry._metrics.append(self)

    def _new(self) -> list:
        return [0.0]

    def _slot(self, values: tuple) -> list:
        """The numbers of one label set, created on first use. Caller holds the lock.

        A capped metric that is full sends a NEW label set to its overflow row instead; the rows
        it already has keep counting as before."""
        key = tuple(str(v) for v in values)
        if len(key) != len(self.labels):
            raise ValueError(f"{self.name} takes {len(self.labels)} label values, got {len(key)}")
        slot = self._series.get(key)
        if slot is None:
            if self._max and self._overflow is not None and len(self._series) >= self._max:
                key = tuple(self._overflow(key))
                slot = self._series.get(key)
            if slot is None:
                slot = self._series[key] = self._new()
        return slot

    def _sample(self, key: tuple, value, suffix: str = "", extra: tuple = ()) -> str:
        pairs = list(zip(self.labels, key)) + list(extra)
        labels = "{" + ",".join(f'{n}="{_escape(v)}"' for n, v in pairs) + "}" if pairs else ""
        return f"{self.name}{suffix}{labels} {_num(value)}"

    def _samples(self, key: tuple, slot: list) -> list[str]:
        return [self._sample(key, slot[0])]


class Counter(_Metric):
    kind = "counter"

    def add(self, amount: float, *labels) -> None:
        if amount < 0:
            raise ValueError("a counter only goes up")
        with self._lock:
            self._slot(labels)[0] += amount


class Gauge(_Metric):
    kind = "gauge"

    def add(self, amount: float, *labels) -> None:
        with self._lock:
            self._slot(labels)[0] += amount

    def set(self, value: float, *labels) -> None:
        with self._lock:
            self._slot(labels)[0] = value

    def replace(self, values: dict[tuple, float]) -> None:
        """Swap every row for `values` ({label values: number}): a row that is not in it is gone.
        For a gauge recomputed whole at scrape time, so a label set that no longer applies does
        not linger at 0."""
        with self._lock:
            self._series.clear()
            for labels, value in values.items():
                self._slot(labels)[0] = value


class Summary(_Metric):
    """Sum and count only, no quantiles: enough for a rate and a mean per label set, at two
    numbers each - the reason the per-action metric is this and not a histogram."""
    kind = "summary"

    def _new(self) -> list:
        return [0.0, 0]

    def observe(self, value: float, *labels) -> None:
        with self._lock:
            slot = self._slot(labels)
            slot[0] += value
            slot[1] += 1

    def _samples(self, key: tuple, slot: list) -> list[str]:
        return [self._sample(key, slot[0], "_sum"), self._sample(key, slot[1], "_count")]


class Histogram(_Metric):
    kind = "histogram"

    def __init__(self, registry: Registry, name: str, help_text: str, labels: Iterable[str] = (),
                 *, buckets: Iterable[float], **cap) -> None:
        super().__init__(registry, name, help_text, labels, **cap)
        self.buckets = tuple(sorted(buckets))

    def _new(self) -> list:
        # [sum, count, one count per bucket..., the count above the last bound]
        return [0.0, 0] + [0] * (len(self.buckets) + 1)

    def observe(self, value: float, *labels) -> None:
        # `le` is inclusive: a value equal to a bound belongs to that bound's bucket.
        index = bisect.bisect_left(self.buckets, value)
        with self._lock:
            slot = self._slot(labels)
            slot[0] += value
            slot[1] += 1
            slot[2 + index] += 1

    def _samples(self, key: tuple, slot: list) -> list[str]:
        lines, running = [], 0
        for bound, count in zip(self.buckets + (math.inf,), slot[2:]):
            running += count  # buckets are cumulative on the wire
            lines.append(self._sample(key, running, "_bucket", (("le", _num(bound)),)))
        lines.append(self._sample(key, slot[0], "_sum"))
        lines.append(self._sample(key, slot[1], "_count"))
        return lines


# --- the runtime's metrics -------------------------------------------------------------------

REGISTRY = Registry()

# Every metric that names a tool also carries `kind` (tool or agent): several names are both a
# tool and an agent, and without it their calls would share one row.
TOOL_CALL_DURATION = Histogram(
    REGISTRY, "procesio_aat_runtime_tool_call_duration_seconds",
    "Time one run_tool or run_agent call took in the bridge, by registered capability and outcome.",
    ("kind", "tool", "outcome"), buckets=CALL_BUCKETS)
ACTION_DURATION = Summary(
    REGISTRY, "procesio_aat_runtime_action_duration_seconds",
    "Time and number of run_tool and run_agent calls per declared action.",
    ("kind", "tool", "action"), max_series=ACTION_SERIES_CAP,
    overflow=lambda key: (key[0], key[1], OTHER))
MCP_REQUEST_DURATION = Histogram(
    REGISTRY, "procesio_aat_runtime_mcp_request_duration_seconds",
    "Time one JSON-RPC request posted to /mcp took to dispatch, by method and MCP tool.",
    ("method", "mcp_tool", "outcome"), buckets=CALL_BUCKETS)
CREDENTIAL_FETCH_DURATION = Histogram(
    REGISTRY, "procesio_aat_runtime_credential_fetch_duration_seconds",
    "Time one credential request to Web-Api took (a lookup the turn's memory could not answer).",
    ("source", "outcome"), buckets=STEP_BUCKETS)
CREDENTIAL_CACHE = Counter(
    REGISTRY, "procesio_aat_runtime_credential_cache_total",
    "Credential lookups, by whether the turn's memory answered (hit) or Web-Api was asked (miss).",
    ("source", "result"))
TOOL_CALLS_IN_PROGRESS = Gauge(
    REGISTRY, "procesio_aat_runtime_tool_calls_in_progress",
    "run_tool and run_agent calls running now.", ("kind",))
TOOL_ERRORS = Counter(
    REGISTRY, "procesio_aat_runtime_tool_errors_total",
    "run_tool and run_agent calls that did not succeed, by error code.", ("kind", "tool", "code"))
REFUSALS = Counter(
    REGISTRY, "procesio_aat_runtime_refusals_total",
    "Calls answered with a refusal before any tool or agent was started, by reason.", ("code",))

ACTION_ERRORS = Counter(
    REGISTRY, "procesio_aat_runtime_action_errors_total",
    "run_tool and run_agent calls that did not succeed, by declared action and error code.",
    ("kind", "tool", "action", "code"), max_series=ACTION_SERIES_CAP,
    overflow=lambda key: (key[0], key[1], OTHER, key[3]))
ACTION_IN_PROGRESS = Gauge(
    REGISTRY, "procesio_aat_runtime_action_in_progress",
    "run_tool and run_agent calls running now, by declared action. A row exists only while a "
    "call of that action runs.", ("kind", "tool", "action"))
ACTION_OLDEST_AGE = Gauge(
    REGISTRY, "procesio_aat_runtime_action_oldest_in_progress_age_seconds",
    "Seconds the longest-running call of each action has been running. A row exists only while "
    "a call of that action runs.", ("kind", "tool", "action"))
HTTP_REQUEST_DURATION = Histogram(
    REGISTRY, "procesio_aat_runtime_http_request_duration_seconds",
    "Time one HTTP request made inside a tool call took, by route and status. status is the "
    "HTTP code, or timeout / connection / error when no answer came, or unfinished when the "
    "request was still waiting as the call ended.",
    ("kind", "tool", "method", "route", "status"), buckets=CALL_BUCKETS,
    max_series=HTTP_SERIES_CAP, overflow=lambda key: (key[0], key[1], key[2], OTHER, key[4]))
HTTP_RETRIES = Counter(
    REGISTRY, "procesio_aat_runtime_http_retries_total",
    "HTTP requests a tool sent again after a failure, by route.",
    ("kind", "tool", "method", "route"), max_series=HTTP_SERIES_CAP,
    overflow=lambda key: (key[0], key[1], key[2], OTHER))
HTTP_UNFINISHED = Counter(
    REGISTRY, "procesio_aat_runtime_http_unfinished_total",
    "HTTP requests that were sent and never answered before the call ended, by action and "
    "route. reason: call_killed (the call hit its time limit) or tool_gave_up (the tool's own "
    "deadline).",
    ("kind", "tool", "action", "method", "route", "reason"), max_series=HTTP_SERIES_CAP,
    overflow=lambda key: (key[0], key[1], OTHER, key[3], OTHER, key[5]))

_enabled = False

# The calls running now: {id: (kind, tool, action, when it started)}. The two per-action gauges
# are computed from it at scrape time, because an age cannot be kept up to date between scrapes.
_RUNNING: dict[int, tuple[str, str, str, float]] = {}
_RUNNING_LOCK = threading.Lock()
_running_ids = iter(range(1, sys.maxsize))


def _refresh_running() -> None:
    now = time.perf_counter()
    with _RUNNING_LOCK:
        running = list(_RUNNING.values())
    counts: dict[tuple, float] = {}
    oldest: dict[tuple, float] = {}
    for kind, tool, action, started in running:
        key = (kind, tool, action)
        counts[key] = counts.get(key, 0) + 1
        oldest[key] = max(oldest.get(key, 0.0), now - started)
    ACTION_IN_PROGRESS.replace(counts)
    ACTION_OLDEST_AGE.replace(oldest)


REGISTRY.before_render(_refresh_running)


def enabled() -> bool:
    return _enabled


def enable(on: bool = True) -> None:
    """Turn recording on or off. `start_listener` turns it on once its port is bound."""
    global _enabled
    _enabled = bool(on)


def reset() -> None:
    """Forget every sample. The in-progress gauge starts at 0 for both kinds, so the series
    exists before the first call."""
    REGISTRY.clear()
    with _RUNNING_LOCK:
        _RUNNING.clear()
    for kind in KINDS:
        TOOL_CALLS_IN_PROGRESS.set(0, kind)


reset()


def render() -> str:
    return REGISTRY.render()


# --- recording --------------------------------------------------------------------------------

clock = time.perf_counter


class _Off:
    """What a measurement is while metrics are off: takes the same attributes, keeps nothing."""
    __slots__ = ()
    result = response = property(lambda self: None, lambda self, value: None)
    tool = action = UNKNOWN

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


_OFF = _Off()


def _fixed(value, allowed: frozenset, fallback: str) -> str:
    # isinstance first: a model can send a list where a name belongs, and a list is not hashable.
    return value if isinstance(value, str) and value in allowed else fallback


def _error_code(result, raised: bool) -> str:
    if raised:
        return "exception"
    code = None
    if isinstance(result, dict):
        error, refused = result.get("error"), result.get("refused")
        if isinstance(error, dict):
            code = error.get("code")
        elif isinstance(refused, dict):  # the bridge's own refusal carries a reason, not an error
            code = refused.get("reason")
    return _fixed(code, ERROR_CODES, OTHER)


class _ToolCall:
    __slots__ = ("_kind", "_labels", "_started", "_id", "tool", "action", "result")

    def __init__(self, kind: str, labels: Callable[[], tuple[str, str]]) -> None:
        self._kind, self._labels, self.result = kind, labels, None
        self._id, self.tool, self.action = 0, UNKNOWN, UNKNOWN

    def __enter__(self):
        try:
            # Resolved before the clock starts: looking the name up is not part of the call.
            self.tool, self.action = self._labels()
        except Exception:  # noqa: BLE001 - metrics are best-effort, never fatal
            self.tool, self.action = UNKNOWN, UNKNOWN
        try:
            TOOL_CALLS_IN_PROGRESS.add(1, self._kind)
            self._id = next(_running_ids)
            with _RUNNING_LOCK:
                _RUNNING[self._id] = (self._kind, self.tool, self.action, time.perf_counter())
        except Exception:  # noqa: BLE001
            pass
        self._started = clock()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        seconds = clock() - self._started
        try:
            with _RUNNING_LOCK:
                _RUNNING.pop(self._id, None)
            TOOL_CALLS_IN_PROGRESS.add(-1, self._kind)
            raised = exc_type is not None
            failed = raised or not (isinstance(self.result, dict) and self.result.get("ok", False))
            TOOL_CALL_DURATION.observe(seconds, self._kind, self.tool, ERROR if failed else OK)
            ACTION_DURATION.observe(seconds, self._kind, self.tool, self.action)
            if failed:
                code = _error_code(self.result, raised)
                TOOL_ERRORS.add(1, self._kind, self.tool, code)
                ACTION_ERRORS.add(1, self._kind, self.tool, self.action, code)
        except Exception:  # noqa: BLE001
            pass
        return False


def tool_call(kind: str, labels: Callable[[], tuple[str, str]]):
    """Measure one run_tool / run_agent call: `with tool_call(...) as seen: seen.result = ...`.

    `kind` is "tool" or "agent". `labels` returns the (tool, action) label values and is the
    caller's promise that both come from the registry; it runs once, before the call, and the
    values are then readable as `seen.tool` / `seen.action`. `seen.result` is write-only for the
    caller: while metrics are off it keeps nothing."""
    return _ToolCall(kind, labels) if _enabled else _OFF


class _McpRequest:
    __slots__ = ("_method", "_tool", "_started", "response")

    def __init__(self, message, tool_names: frozenset) -> None:
        self._method, self._tool, self.response = OTHER, NONE, None
        try:
            method = message.get("method")
            self._method = _fixed(method, _MCP_METHODS, OTHER)
            if method == "tools/call":
                params = message.get("params")
                name = params.get("name") if isinstance(params, dict) else None
                self._tool = _fixed(name, tool_names, UNKNOWN)
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self):
        self._started = clock()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        seconds = clock() - self._started
        try:
            response = self.response
            failed = exc_type is not None
            if not failed and isinstance(response, dict):
                result = response.get("result")
                failed = "error" in response or (isinstance(result, dict) and bool(result.get("isError")))
            MCP_REQUEST_DURATION.observe(seconds, self._method, self._tool, ERROR if failed else OK)
        except Exception:  # noqa: BLE001
            pass
        return False


def mcp_request(message, tool_names: frozenset):
    """Measure the dispatch of one JSON-RPC message: `with mcp_request(m, names) as seen:
    seen.response = handle(m)`. A JSON-RPC error and a tool result marked isError are errors;
    a notification (no response) is ok."""
    return _McpRequest(message, tool_names) if _enabled else _OFF


def refusal(code: str) -> None:
    """Count one call that was answered without starting a tool or an agent."""
    if not _enabled:
        return
    try:
        REFUSALS.add(1, _fixed(code, REFUSAL_CODES, OTHER))
    except Exception:  # noqa: BLE001
        pass


def credential_cache(source: str, hit: bool) -> None:
    """Count one credential lookup: answered from the turn's memory, or not."""
    if not _enabled:
        return
    try:
        CREDENTIAL_CACHE.add(1, source, "hit" if hit else "miss")
    except Exception:  # noqa: BLE001
        pass


def credential_fetch(source: str, started: float, failure, refused: tuple = ()) -> None:
    """Record one request to Web-Api that began at `started` (from `clock()`).

    `failure` is what the request ended with: None (answered), or the error. An HTTP status in
    `refused` means Web-Api turned the caller away, which is the caller's problem and not an
    outage; any other failure is an error. An answer that holds no key is still `ok` here - the
    request worked - and shows up as a refused call instead."""
    if not _enabled:
        return
    try:
        if failure is None:
            outcome = OK
        elif isinstance(failure, urllib.error.HTTPError) and failure.code in refused:
            outcome = REFUSED
        else:
            outcome = ERROR
        CREDENTIAL_FETCH_DURATION.observe(clock() - started, source, outcome)
    except Exception:  # noqa: BLE001
        pass


# --- the HTTP trace of one call ---------------------------------------------------------------

def http_route(path) -> str:
    """The route of a request path: every id-like segment becomes `{id}`, the rest is lower-cased
    (the PROCESIO API matches paths without regard to case). The path comes from a tool, so it is
    cut to a fixed number of segments and a fixed length."""
    if not isinstance(path, str):
        return UNKNOWN
    segments = [seg for seg in path.split("?", 1)[0].split("/") if seg][:_ROUTE_MAX_SEGMENTS]
    route = "/" + "/".join(
        "{id}" if _ID_SEGMENT.match(seg) or not _ROUTE_WORD.match(seg) else seg.lower()
        for seg in segments)
    return route[:_ROUTE_MAX_LENGTH]


def _slow_log_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get(SLOW_LOG_ENV, "30")))
    except ValueError:
        return 30.0


def _trace_events(text: str) -> list[dict]:
    events = []
    for line in text[:HTTP_TRACE_MAX_BYTES].splitlines()[:HTTP_TRACE_MAX_EVENTS]:
        try:
            event = json.loads(line)
        except ValueError:
            continue  # a line cut off by the kill, or not ours
        if isinstance(event, dict):
            events.append(event)
    return events


def _seconds(value, limit: float = 86400.0) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= limit else None


def _named(msg) -> str | None:
    """A turn's message id as a JSON log line holds it: the id, or nothing when the caller
    passed the `-` a text line writes for a turn without one."""
    return msg if isinstance(msg, str) and msg not in ("", "-") else None


def _printable(path) -> str:
    """A request path as it may be logged: no query string, no control characters, capped."""
    if not isinstance(path, str):
        return "?"
    return "".join(ch if ch.isprintable() else "?" for ch in path.split("?", 1)[0])[:300]


class HttpSummary(NamedTuple):
    """What one call's HTTP trace held, for the caller's own log line about the call."""
    requests: int                                   # answered or failed, plus the unfinished ones
    slowest: tuple[str, str, float, str] | None     # (method, route, seconds, status)
    unfinished: int                                 # sent and never answered before the call ended


def _request_key(event: dict) -> tuple | None:
    """What pairs a start line with its end line: the process that wrote it and the number that
    process gave the request, or None for a line without a usable number.

    The number alone is not enough. Every process counts its requests from 1, and a call's trace
    file is shared by all the processes of the call: an agent's tools inherit it. A line written
    by a tool that does not give its process is paired by number alone."""
    number = event.get("id")
    if not isinstance(number, int) or isinstance(number, bool):
        return None
    pid = event.get("pid")
    return (pid if isinstance(pid, int) and not isinstance(pid, bool) else None, number)


def http_trace(text: str | None, kind: str, tool: str, action: str, call_killed: bool,
               msg: str = "-") -> HttpSummary | None:
    """Record the HTTP requests one tool call noted in its trace file (tools/_lib/httptrace.py).

    `kind` says whether the call was a tool or an agent call; it comes from the bridge, not from
    the caller. `tool` and `action` are the call's label values, already checked against the
    registry.
    `call_killed` says the call was stopped at its time limit, which is why a request may have
    a start and no end. Everything in `text` was written by the tool and is validated here; a
    line that does not fit is skipped. A request that never ended, and one slower than
    AAT_HTTP_SLOW_LOG_SECONDS, is also logged with its real path - the route alone does not say
    which resource it was. `msg` is the turn's message id as a log line writes it; it ends those
    two lines, so they are found by the same search as the call's own line, and it is never a
    label.

    Returns a summary of the trace - how many requests, the slowest one by route, how many never
    ended - or None when nothing was recorded."""
    if not _enabled or not text:
        return None
    try:
        slow = _slow_log_seconds()
        logged = 0
        requests = 0
        slowest: tuple[str, str, float, str] | None = None
        open_requests: dict = {}
        never_ended: list[dict] = []
        for event in _trace_events(text):
            what = event.get("e")
            if what == "start":
                key = _request_key(event)
                if key is not None:
                    # A second start under the same key means the first one will never get its
                    # end: its process is gone and the key was used again. It stays a request
                    # that never ended instead of being replaced.
                    if key in open_requests:
                        never_ended.append(open_requests[key])
                    open_requests[key] = event
            elif what == "end":
                key = _request_key(event)
                started = open_requests.pop(key, None) if key is not None else None
                seconds = _seconds(event.get("d"))
                if started is None or seconds is None:
                    continue
                method = _fixed(started.get("m"), _HTTP_METHODS, OTHER)
                route = http_route(started.get("p"))
                status = event.get("s")
                if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
                    outcome = str(status)
                else:
                    outcome = _fixed(event.get("x"), _HTTP_ERRORS, ERROR)
                HTTP_REQUEST_DURATION.observe(seconds, kind, tool, method, route, outcome)
                requests += 1
                if slowest is None or seconds > slowest[2]:
                    slowest = (method, route, seconds, outcome)
                if seconds >= slow > 0 and logged < HTTP_LOG_LINES_PER_CALL:
                    logged += 1
                    _log(f"slow http request: {tool} {action}: {method} "
                         f"{_printable(started.get('p'))} -> {outcome} in {seconds:.1f}s msg={msg}",
                         {"Event": "slow_http_request", "MessageId": _named(msg), "Kind": kind, "Tool": tool,
                          "Action": action, "RequestMethod": method,
                          "RequestPath": _printable(started.get("p")), "Outcome": outcome,
                          "Seconds": round(seconds, 1)}, runtime_log.WARNING)
            elif what == "retry":
                HTTP_RETRIES.add(1, kind, tool, _fixed(event.get("m"), _HTTP_METHODS, OTHER),
                                 http_route(event.get("p")))
        reason = CALL_KILLED if call_killed else TOOL_GAVE_UP
        now = time.time()
        unfinished = never_ended + list(open_requests.values())
        for started in unfinished:
            method = _fixed(started.get("m"), _HTTP_METHODS, OTHER)
            route = http_route(started.get("p"))
            HTTP_UNFINISHED.add(1, kind, tool, action, method, route, reason)
            sent_at = _seconds(started.get("t"), limit=float("inf"))
            waited = _seconds(now - sent_at) if sent_at is not None else None
            if waited is not None:
                HTTP_REQUEST_DURATION.observe(waited, kind, tool, method, route, UNFINISHED)
                if slowest is None or waited > slowest[2]:
                    slowest = (method, route, waited, UNFINISHED)
            if logged < HTTP_LOG_LINES_PER_CALL:
                logged += 1
                age = f" after {waited:.1f}s" if waited is not None else ""
                _log(f"http request never answered ({reason}): {tool} {action}: {method} "
                     f"{_printable(started.get('p'))}{age} msg={msg}",
                     {"Event": "http_request_never_answered", "MessageId": _named(msg), "Kind": kind,
                      "Tool": tool, "Action": action, "RequestMethod": method,
                      "RequestPath": _printable(started.get("p")), "Reason": reason,
                      "Seconds": round(waited, 1) if waited is not None else None}, runtime_log.WARNING)
        return HttpSummary(requests + len(unfinished), slowest, len(unfinished))
    except Exception:  # noqa: BLE001
        return None


# --- the listener -----------------------------------------------------------------------------

def _log(message: str, fields: dict | None = None, level: str = runtime_log.INFO) -> None:
    runtime_log.write("aat-metrics", message, level=level, fields=fields)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 10  # a scraper that stops reading must not hold a thread

    def log_message(self, fmt, *args):  # a scrape every few seconds is not worth a log line
        pass

    def _answer(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if code != 200:
            self.send_header("Connection", "close")  # a request body, if any, is never read
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        self._answer(404, b"not found\n", "text/plain; charset=utf-8")

    def do_GET(self):
        if self.path.split("?", 1)[0] != PATH:
            return self._not_found()
        self._answer(200, render().encode("utf-8"), CONTENT_TYPE)

    # Nothing but GET /metrics exists here, whatever the method.
    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _not_found


def serve(host: str, port: int) -> ThreadingHTTPServer:
    """Bind `host:port` and serve /metrics from a daemon thread. Raises OSError when the port
    cannot be bound. The thread dies with the process; `shutdown()` on the result stops it."""
    httpd = ThreadingHTTPServer((host, port), _Handler)
    threading.Thread(target=httpd.serve_forever, name="aat-metrics", daemon=True).start()
    return httpd


def start_listener(host: str = "127.0.0.1") -> ThreadingHTTPServer | None:
    """Serve metrics on AAT_METRICS_PORT and turn recording on. Unset, empty or 0 = off.

    Never raises: a port that is taken or not a number is logged and the caller carries on
    without metrics, because the MCP server must come up either way."""
    raw = (os.environ.get(PORT_ENV) or "").strip()
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError:
        _log(f"{PORT_ENV}={raw!r} is not a port; metrics are off", level=runtime_log.WARNING)
        return None
    if port <= 0:
        return None
    try:
        httpd = serve(host, port)
    except (OSError, OverflowError) as e:
        _log(f"cannot listen on {host}:{port} ({e}); metrics are off", level=runtime_log.WARNING)
        return None
    enable()
    _log(f"listening on http://{host}:{port}{PATH}")
    return httpd
