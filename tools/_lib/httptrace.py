"""A trace of the HTTP requests one tool run makes, for whoever started the run.

A tool runs in a process of its own, so the server that started it sees one call go in and one
answer come out - not which request inside it was slow, was retried, or never came back. When the
starter sets AAT_HTTP_TRACE_FILE to a file it created, a tool that wraps its HTTP session with
`wrap_session` appends one line per event to that file:

    {"e":"start","pid":4711,"id":1,"m":"GET","p":"/api/Projects","t":1763380000.12}
    {"e":"end","pid":4711,"id":1,"s":200,"d":0.184}
    {"e":"end","pid":4711,"id":2,"x":"timeout","d":60.002}
    {"e":"retry","m":"GET","p":"/api/Projects"}

A request is named by the process that sent it and a number that process counts from 1. The
file is shared by every process of the run - a tool started by the run inherits the variable -
so the number alone would name two requests at once.

The start line is written BEFORE the request is sent, so a run that is killed while it waits
leaves a start with no end: that is the request it was stuck on.

Rules this module keeps:

  - Off unless the variable is set, and then it only ever appends to a file that already
    exists. It never creates one, so a stray value cannot make a tool write somewhere new.
  - Only the method, the URL path, the status and the time are written. Never the query string,
    a header or a body: those carry ids, keys and user data.
  - Tracing never changes a request, its answer or its exception, and a trace line that cannot
    be written is dropped.
"""
from __future__ import annotations

import itertools
import json
import os
import time
from urllib.parse import urlsplit

ENV = "AAT_HTTP_TRACE_FILE"

_MAX_PATH = 300
_ids = itertools.count(1)


def enabled() -> bool:
    return bool(os.environ.get(ENV))


def _write(event: dict) -> None:
    path = os.environ.get(ENV)
    if not path:
        return
    try:
        line = (json.dumps(event, separators=(",", ":")) + "\n").encode("utf-8")
        # O_APPEND without O_CREAT: one short write lands whole at the end of an existing file.
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 - a trace is best-effort, never fatal
        pass


def _path_of(url) -> str:
    try:
        return (urlsplit(str(url)).path or "/")[:_MAX_PATH]
    except Exception:  # noqa: BLE001
        return "/"


def _error_kind(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connection" in name or "ssl" in name or "proxy" in name:
        return "connection"
    return "error"


def start(method, url) -> tuple[int, float]:
    """Note that a request is about to be sent. Returns what `end` needs."""
    request_id = next(_ids)
    # The pid is read here, not once at import: a forked child keeps the parent's module state.
    _write({"e": "start", "pid": os.getpid(), "id": request_id, "m": str(method).upper()[:10],
            "p": _path_of(url), "t": round(time.time(), 3)})
    return request_id, time.monotonic()


def end(started: tuple[int, float], *, status=None, error: BaseException | None = None) -> None:
    """Note how the request ended: with an HTTP status, or with an exception."""
    request_id, t0 = started
    event: dict = {"e": "end", "pid": os.getpid(), "id": request_id,
                   "d": round(time.monotonic() - t0, 3)}
    if error is not None:
        event["x"] = _error_kind(error)
    else:
        try:
            event["s"] = int(status)
        except (TypeError, ValueError):
            event["x"] = "error"
    _write(event)


def retry(method, path) -> None:
    """Note that a request is going to be sent again after a failure."""
    if enabled():
        _write({"e": "retry", "m": str(method).upper()[:10], "p": _path_of(path)})


def wrap_session(session):
    """Trace every request of a `requests`-style session. Returns the same session.

    Does nothing when tracing is off or the session is already traced. `Session.get`, `.post` and
    the others go through `Session.request`, so wrapping that one method covers them all."""
    if not enabled() or getattr(session, "_aat_http_traced", False):
        return session
    try:
        inner = session.request
    except AttributeError:
        return session

    def request(method, url, *args, **kwargs):
        started = start(method, url)
        try:
            response = inner(method, url, *args, **kwargs)
        except BaseException as exc:
            end(started, error=exc)
            raise
        end(started, status=getattr(response, "status_code", None))
        return response

    try:
        session.request = request
        session._aat_http_traced = True
    except Exception:  # noqa: BLE001 - a session that cannot be wrapped is used as it is
        pass
    return session
