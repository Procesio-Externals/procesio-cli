"""The serializing broker SERVER, generalized from whatsapp-personal v0.2.0.

Why: two processes driving the same persistent Chromium profile concurrently
contend on the profile's SingletonLock; the web app (WhatsApp, Ryver, FGO,
Mirro) sees a wedged/duplicated client and can invalidate the session. The fix
is exactly one process per profile: this broker owns it, everyone else asks.

Per tool there is ONE broker process:

  * It binds ``127.0.0.1:<cfg.port>`` (fixed port = single-instance guard).
  * Clients submit commands over the JSONL protocol (framing.py); each
    connection carries ONE request and blocks until its response is ready.
  * A single WORKER executes strictly in arrival order — one at a time.
  * Two job kinds: ``run`` (the tool's own action via its main.dispatch with
    an injected driver factory) and ``web-steps`` (a generic web-tool step
    list against an OWNED session — how `web run/get-text/screenshot` stay
    serialized too).
  * The SharedDriverManager keeps the browser warm between commands (rapid
    open/close cycles are a logout risk) and closes it after an idle period so
    the profile frees up for login / --direct.

Playwright's sync API is thread-bound: every browser op (open/use/idle-close)
happens on the worker thread. Connection handler threads only enqueue + wait.
"""
from __future__ import annotations

import os
import queue
import socket
import socketserver
import sys
import threading
import time
import traceback
from typing import Callable

from tools._lib.webserialize import framing, runtime
from tools._lib.webserialize.config import HOST, PROTO, BrokerConfig

_LOG_MAX_BYTES = 2 * 1024 * 1024


def make_logger(cfg: BrokerConfig) -> Callable[[str], None]:
    """A timestamped append-to-file logger (stderr is detached in a daemon)."""
    lock = threading.Lock()

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] {msg}\n"
        with lock:
            try:
                cfg.service_dir.mkdir(parents=True, exist_ok=True)
                p = cfg.log_path
                if p.exists() and p.stat().st_size > _LOG_MAX_BYTES:
                    keep = p.read_bytes()[-_LOG_MAX_BYTES // 4:]
                    p.write_bytes(b"...truncated...\n" + keep)
                with p.open("a", encoding="utf-8") as f:
                    f.write(line)
            except OSError:
                pass

    return log


def _noop_log(_msg: str) -> None:
    return None


def generic_classify(exc: Exception) -> tuple[str, str, dict, int]:
    """Fallback envelope mapper (same name-based scheme every tool uses)."""
    name = exc.__class__.__name__
    details = getattr(exc, "details", None) or {}
    if name == "ServiceRemoteError":
        return (getattr(exc, "code", "error") or "error", str(exc) or name,
                details, int(getattr(exc, "exit_code", 1) or 1))
    if name == "ServiceError":
        return "service_error", str(exc) or name, details, 1
    if name == "UsageError":
        return "invalid_argument", str(exc) or name, details, 2
    if name == "SessionError":
        return "session_not_found", str(exc) or name, details, 1
    if name == "BrowserError":
        return "browser_error", str(exc) or name, details, 1
    return "error", str(exc) or name, {}, 1


# --------------------------------------------------------------------------- #
# Shared driver: one warm browser, leased per command, really closed only by
# the manager (idle timeout / recycle / shutdown).
# --------------------------------------------------------------------------- #
class LeasedDriver:
    """Proxy handed to ``web.open_session``: ``start()`` is idempotent and
    ``close()`` releases the lease WITHOUT closing the browser. The manager
    owns the real lifecycle. Everything else delegates to the inner driver."""

    def __init__(self, inner):
        self._inner = inner
        self._started = False

    def start(self):
        if not self._started:
            self._inner.start()
            self._started = True
        return self

    def close(self):  # lease release — the manager closes for real
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


class SharedDriverManager:
    """Caches ONE live persistent-profile driver across commands.

    Reuse rule: same (user_data_dir, headless, channel) AND the page still
    answers ``current_url()`` — otherwise the old browser is really closed and
    a fresh one is built. storageState-based requests (no user_data_dir) are
    never cached. Thread-affinity: only call from the worker thread."""

    def __init__(self, driver_cls=None, *, log: Callable[[str], None] = _noop_log):
        self._driver_cls = driver_cls   # injectable for tests
        self._log = log
        self._proxy: LeasedDriver | None = None
        self._key = None
        self.opened = 0
        self.recycled = 0

    def _cls(self):
        if self._driver_cls is not None:
            return self._driver_cls
        from tools.web.driver import PlaywrightDriver
        return PlaywrightDriver

    def _alive(self) -> bool:
        if self._proxy is None:
            return False
        if not self._proxy._started:
            return True  # built but never started — reusable as-is
        try:
            self._proxy._inner.current_url()
            return True
        except Exception:  # noqa: BLE001 - any failure means recycle
            return False

    def factory(self, *, storage_state=None, headless=True, channel=None,
                user_data_dir=None, extra_args=None):
        if user_data_dir is None:
            # Not a persistent-profile session: no sharing, behave like direct.
            return self._cls()(storage_state=storage_state, headless=headless,
                               channel=channel, user_data_dir=None, extra_args=extra_args)
        key = (user_data_dir, headless, channel, tuple(extra_args or ()))
        if self._proxy is not None:
            if key == self._key and self._alive():
                return self._proxy
            self.close(reason="recycle (settings changed or browser dead)")
            self.recycled += 1
        inner = self._cls()(storage_state=None, headless=headless,
                            channel=channel, user_data_dir=user_data_dir, extra_args=extra_args)
        self._proxy = LeasedDriver(inner)
        self._key = key
        self.opened += 1
        self._log(f"driver: new browser for profile={user_data_dir} headless={headless}")
        return self._proxy

    @property
    def browser_open(self) -> bool:
        return self._proxy is not None and self._proxy._started

    def close(self, reason: str = "") -> None:
        if self._proxy is not None:
            self._log(f"driver: closing browser ({reason or 'shutdown'})")
            try:
                self._proxy._inner.close()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        self._proxy = None
        self._key = None


# --------------------------------------------------------------------------- #
# The serializing core: a queue + ONE worker.
# --------------------------------------------------------------------------- #
class _Job:
    __slots__ = ("kind", "payload", "done", "response", "enqueued_at")

    def __init__(self, kind: str, payload: dict):
        self.kind = kind            # "run" | "web-steps"
        self.payload = payload
        self.done = threading.Event()
        self.response: dict | None = None
        self.enqueued_at = time.time()

    @property
    def label(self) -> str:
        if self.kind == "run":
            return self.payload.get("action", "?")
        return f"web-steps:{self.payload.get('session', '?')}"


_STOP = object()

# A connection thread will not wait on a single job forever (wedged worker).
_JOB_WAIT_CAP_S = 3600


def default_web_runner(session: str, steps: list, *, url=None, headless=True,
                       driver_factory=None) -> dict:
    """Execute a generic web-tool step list against an owned session, with the
    broker's shared driver. No explicit user_data_dir: ``open_session``
    auto-detects a ``<name>.profile`` dir (persistent) vs a storageState
    session, exactly like a direct `web run` would. Late import keeps the lib
    import-light."""
    from tools.web import api as web_api
    return web_api.run_steps(session, steps, url=url, headless=headless,
                             driver_factory=driver_factory)


class ServiceCore:
    """Queue + single worker. ``submit*()`` is called from connection threads;
    ``run_worker()`` runs on the main thread and is the ONLY place commands
    (and therefore Playwright) execute — that is the serialization guarantee."""

    def __init__(self, cfg: BrokerConfig, dispatcher=None,
                 manager: SharedDriverManager | None = None, *,
                 classify=None, web_runner=None,
                 idle_close_s: float | None = None,
                 exit_idle_s: float | None = None,
                 log: Callable[[str], None] = _noop_log):
        self.cfg = cfg
        self._dispatcher = dispatcher   # callable(action, argv, driver_factory)
        self._classify = classify or generic_classify
        self._web_runner = web_runner or default_web_runner
        self.manager = manager or SharedDriverManager(log=log)
        self.log = log
        self.queue: "queue.Queue[object]" = queue.Queue()
        self.stop_event = threading.Event()
        self.busy = False
        self.served = 0
        self.failed = 0
        self.started_at = time.time()
        self.last_activity = time.time()
        from tools._lib.webserialize.config import (DEFAULT_EXIT_IDLE_S,
                                                    DEFAULT_IDLE_CLOSE_S)
        if idle_close_s is None:
            idle_close_s = float(os.environ.get(cfg.idle_close_env)
                                 or DEFAULT_IDLE_CLOSE_S)
        if exit_idle_s is None:
            exit_idle_s = float(os.environ.get(cfg.exit_idle_env)
                                or DEFAULT_EXIT_IDLE_S)
        self.idle_close_s = idle_close_s
        self.exit_idle_s = exit_idle_s
        # FROZEN at startup: a long-lived daemon must report the code it
        # LOADED, not what is on disk now — that difference is exactly what
        # the client's stale-restart check needs to see.
        self.code_stamp = runtime.code_stamp(cfg)

    # -- called from connection threads -------------------------------------
    def _submit(self, job: _Job) -> dict:
        if self.stop_event.is_set():
            return _err("service_stopping",
                        "service is shutting down; retry to auto-start a fresh one")
        self.queue.put(job)
        if not job.done.wait(timeout=_JOB_WAIT_CAP_S):
            return _err("service_timeout",
                        f"job not finished after {_JOB_WAIT_CAP_S}s; it may still "
                        "be running — check service-status",
                        details={"job": job.label})
        return job.response or _err("service_error", "worker produced no response")

    def submit_run(self, action: str, argv: list[str]) -> dict:
        return self._submit(_Job("run", {"action": action, "argv": argv}))

    def submit_web_steps(self, session: str, steps: list, *, url=None,
                         headless: bool = True) -> dict:
        if session not in self.cfg.sessions:
            return _err("bad_request",
                        f"session {session!r} is not owned by the "
                        f"{self.cfg.tool} broker (owned: {list(self.cfg.sessions)})",
                        exit_code=2)
        return self._submit(_Job("web-steps", {
            "session": session, "steps": steps, "url": url, "headless": headless}))

    def request_stop(self) -> None:
        self.stop_event.set()
        self.queue.put(_STOP)

    def status(self) -> dict:
        return {
            "running": True,
            "tool": self.cfg.tool,
            "pid": os.getpid(),
            "proto": PROTO,
            "code_stamp": self.code_stamp,
            "uptime_s": round(time.time() - self.started_at, 1),
            "idle_s": round(time.time() - self.last_activity, 1),
            "busy": self.busy,
            "queue_depth": self.queue.qsize(),
            "served": self.served,
            "failed": self.failed,
            "browser_open": self.manager.browser_open,
            "browsers_opened": self.manager.opened,
            "browsers_recycled": self.manager.recycled,
            "idle_close_s": self.idle_close_s,
            "log": str(self.cfg.log_path),
        }

    # -- worker (main thread) ------------------------------------------------
    def run_worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.queue.get(timeout=2.0)
            except queue.Empty:
                self._on_idle_tick()
                continue
            if job is _STOP:
                break
            self._run(job)  # type: ignore[arg-type]
        self.manager.close(reason="service stopping")
        # Unblock anything still queued behind the stop sentinel.
        while True:
            try:
                j = self.queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(j, _Job):
                j.response = _err("service_stopping",
                                  "service stopped before this job ran; retry")
                j.done.set()

    def _on_idle_tick(self) -> None:
        idle = time.time() - self.last_activity
        if (self.idle_close_s and self.manager.browser_open
                and idle > self.idle_close_s):
            self.manager.close(reason=f"idle {int(idle)}s > {int(self.idle_close_s)}s")
        if self.exit_idle_s and idle > self.exit_idle_s:
            self.log(f"idle {int(idle)}s > exit threshold; shutting down")
            self.request_stop()

    def _run(self, job: _Job) -> None:
        self.busy = True
        queue_wait_ms = int((time.time() - job.enqueued_at) * 1000)
        t0 = time.time()
        self.log(f"run: {job.label} (queued {queue_wait_ms}ms)")
        try:
            if job.kind == "run":
                result = self._dispatch(job.payload["action"], job.payload["argv"])
            else:
                result = self._web_runner(
                    job.payload["session"], job.payload["steps"],
                    url=job.payload.get("url"),
                    headless=bool(job.payload.get("headless", True)),
                    driver_factory=self.manager.factory)
            job.response = {"ok": True, "result": result}
            self.served += 1
        except Exception as exc:  # noqa: BLE001 - the envelope IS the contract
            code, message, details, exit_code = self._classify(exc)
            job.response = {"ok": False, "exit_code": exit_code, "error": {
                "code": code, "message": message, "details": details}}
            self.failed += 1
            self.log(f"run: {job.label} FAILED {code}: {message[:300]}")
            self.log(traceback.format_exc(limit=5))
        finally:
            exec_ms = int((time.time() - t0) * 1000)
            job.response["queue_wait_ms"] = queue_wait_ms  # type: ignore[index]
            job.response["exec_ms"] = exec_ms              # type: ignore[index]
            self.busy = False
            self.last_activity = time.time()
            job.done.set()
            self.log(f"run: {job.label} done ok={job.response.get('ok')} in {exec_ms}ms")

    def _dispatch(self, action: str, argv: list[str]):
        if self._dispatcher is None:
            raise RuntimeError("ServiceCore has no dispatcher wired")
        return self._dispatcher(action, argv, self.manager.factory)


def _err(code: str, message: str, *, details: dict | None = None,
         exit_code: int = 1) -> dict:
    return {"ok": False, "exit_code": exit_code,
            "error": {"code": code, "message": message, "details": details or {}}}


# --------------------------------------------------------------------------- #
# TCP front-end: one request per connection, handler threads only enqueue.
# --------------------------------------------------------------------------- #
class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        core: ServiceCore = self.server.core  # type: ignore[attr-defined]
        log = getattr(self.server, "log", _noop_log)
        try:
            self.request.settimeout(30)
            raw = framing.recv_line(self.request)
            if not raw.strip():
                return
            req = framing.decode(raw)
        except Exception as exc:  # noqa: BLE001 - protocol boundary
            self._reply(_err("bad_request", f"unreadable request: {exc}",
                             exit_code=2))
            return
        op = req.get("op")
        if op == "ping":
            resp = {"ok": True, "result": {
                "pong": True, "pid": os.getpid(), "proto": PROTO,
                "tool": core.cfg.tool, "code_stamp": core.code_stamp}}
        elif op == "status":
            resp = {"ok": True, "result": core.status()}
        elif op == "stop":
            log("stop requested")
            core.request_stop()
            resp = {"ok": True, "result": {"stopping": True, "pid": os.getpid()}}
        elif op == "run":
            action = req.get("action")
            argv = req.get("argv")
            if not isinstance(action, str) or not isinstance(argv, list):
                resp = _err("bad_request",
                            "run op needs a string 'action' and list 'argv'",
                            exit_code=2)
            else:
                self.request.settimeout(None)  # long-running; no read left
                resp = core.submit_run(action, [str(a) for a in argv])
        elif op == "web-steps":
            session = req.get("session")
            steps = req.get("steps")
            if not isinstance(session, str) or not isinstance(steps, list):
                resp = _err("bad_request",
                            "web-steps op needs a string 'session' and list 'steps'",
                            exit_code=2)
            else:
                self.request.settimeout(None)
                resp = core.submit_web_steps(
                    session, steps, url=req.get("url"),
                    headless=bool(req.get("headless", True)))
        else:
            resp = _err("bad_request", f"unknown op {op!r}", exit_code=2)
        self._reply(resp)

    def _reply(self, resp: dict) -> None:
        try:
            self.request.sendall(framing.encode(resp))
        except OSError:
            pass  # client went away; the command outcome is in the log


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False  # a failed bind is HOW we stay single-instance

    def __init__(self, addr, handler, *, cfg: BrokerConfig | None = None,
                 log: Callable[[str], None] = _noop_log):
        self.cfg = cfg
        self.log = log
        self.core: ServiceCore | None = None
        super().__init__(addr, handler)


def other_instance_alive(cfg: BrokerConfig, *, attempts: int = 10) -> bool:
    port = cfg.effective_port()
    for _ in range(attempts):
        try:
            with socket.create_connection((HOST, port), timeout=1) as s:
                s.sendall(framing.encode({"op": "ping"}))
                s.settimeout(2)
                resp = framing.decode(framing.recv_line(s))
                if resp.get("ok") and (resp.get("result") or {}).get("pong"):
                    return True
        except (OSError, ValueError):
            time.sleep(0.5)
    return False


def run_service(cfg: BrokerConfig, build_dispatcher, *, classify=None,
                port: int | None = None) -> int:
    """The broker main loop. ``build_dispatcher()`` is called once and must
    return ``callable(action, argv, driver_factory) -> dict`` (typically the
    tool's own main.dispatch partially applied). Returns the exit code."""
    port = port or cfg.effective_port()
    log = make_logger(cfg)
    try:
        server = _Server((HOST, port), _Handler, cfg=cfg, log=log)
    except OSError:
        if other_instance_alive(cfg):
            log(f"another instance already serves port {port}; exiting")
            return 0
        log(f"cannot bind {HOST}:{port} and no instance answers")
        return 1

    core = ServiceCore(cfg, build_dispatcher(), classify=classify, log=log)
    server.core = core
    runtime.write_state(cfg, {
        "tool": cfg.tool, "pid": os.getpid(), "port": port, "proto": PROTO,
        "code_stamp": core.code_stamp,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python": sys.executable,
    })
    log(f"service up on {HOST}:{port} (tool={cfg.tool}, "
        f"idle-close {core.idle_close_s}s, exit-idle {core.exit_idle_s}s)")

    t = threading.Thread(target=server.serve_forever, name="tcp-accept", daemon=True)
    t.start()
    try:
        core.run_worker()          # blocks until stop
    except KeyboardInterrupt:
        core.stop_event.set()
        core.manager.close(reason="KeyboardInterrupt")
    finally:
        server.shutdown()
        server.server_close()
        runtime.clear_state(cfg)
        log("service stopped")
    return 0
