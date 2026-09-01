"""Client side of a serializing broker. Every function takes the tool's
BrokerConfig first; tools call these from their dispatch routing.

Safety rules (they matter for message/state-changing commands):

  * FALLBACK TO DIRECT happens ONLY when the request was never submitted —
    no service answered and one could not be started. Running direct then is
    safe because the failed service never opened a browser.
  * Once a request has been SENT, a lost connection NEVER falls back: the
    command may be mid-flight, and re-running could double-send.
  * A running service built from STALE code (the tool was edited since it
    started) is detected via ``code_stamp`` and transparently restarted.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from tools._lib.webserialize import framing, runtime
from tools._lib.webserialize.config import HOST, PROTO, FRAMEWORK_ROOT, BrokerConfig
from tools._lib.webserialize.errors import ServiceError, ServiceRemoteError

_CONNECT_TIMEOUT_S = 5
_SPAWN_WAIT_S = 25
_STOP_WAIT_S = 60


# --------------------------------------------------------------------------- #
# Routing decision
# --------------------------------------------------------------------------- #
def enabled(cfg: BrokerConfig) -> bool:
    """Routing is ON unless explicitly disabled or we ARE the service worker."""
    if runtime.env_truthy(cfg.direct_env):
        return False
    if runtime.env_truthy(cfg.worker_env):
        return False
    return True


# --------------------------------------------------------------------------- #
# Wire helpers
# --------------------------------------------------------------------------- #
def _request(cfg: BrokerConfig, obj: dict, *, read_timeout: float,
             port: int | None = None) -> dict:
    """Send one framed request, wait for the one framed response.

    Connect+send failures raise OSError (caller may safely fall back: nothing
    was accepted). After the request is on the wire, read failures raise
    ServiceError (NOT safe to fall back)."""
    port = port or cfg.effective_port()
    s = socket.create_connection((HOST, port), timeout=_CONNECT_TIMEOUT_S)
    try:
        s.sendall(framing.encode(obj))            # OSError here -> not submitted
        s.settimeout(read_timeout)
        try:
            raw = framing.recv_line(s)
        except (OSError, ValueError) as exc:
            raise ServiceError(
                f"lost the {cfg.tool} service mid-request "
                f"({exc.__class__.__name__}: {exc}). The command MAY still be "
                "executing — check `service-status` and the target system "
                "before retrying a state-changing command."
            ) from exc
        if not raw.strip():
            raise ServiceError(
                f"the {cfg.tool} service closed the connection without a "
                "response. The command MAY have executed — verify before retrying."
            )
        return framing.decode(raw)
    finally:
        try:
            s.close()
        except OSError:
            pass


def ping(cfg: BrokerConfig, *, timeout: float = 2.0,
         port: int | None = None) -> dict | None:
    try:
        resp = _request(cfg, {"op": "ping"}, read_timeout=timeout, port=port)
    except (OSError, ServiceError, ValueError):
        return None
    if resp.get("ok") and (resp.get("result") or {}).get("pong"):
        return resp["result"]
    return None


def request_status(cfg: BrokerConfig, *, port: int | None = None) -> dict | None:
    try:
        resp = _request(cfg, {"op": "status"}, read_timeout=10, port=port)
    except (OSError, ServiceError, ValueError):
        return None
    return resp.get("result") if resp.get("ok") else None


def stop(cfg: BrokerConfig, *, wait_s: float = _STOP_WAIT_S,
         port: int | None = None) -> bool:
    """Ask the service to stop; True when it is gone (or was never running)."""
    if ping(cfg, port=port) is None:
        return True
    try:
        _request(cfg, {"op": "stop"}, read_timeout=10, port=port)
    except (OSError, ServiceError, ValueError):
        pass
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if ping(cfg, port=port) is None:
            return True
        time.sleep(0.3)
    return False


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def spawn(cfg: BrokerConfig) -> int:
    """Start the tool's service DETACHED. Startup errors land in
    .service/spawn-err.log; runtime logs in service.log."""
    py = runtime.venv_python() or Path(sys.executable)
    cfg.service_dir.mkdir(parents=True, exist_ok=True)
    err = open(cfg.spawn_err_path, "ab")
    kwargs: dict = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=err, close_fds=True, cwd=str(FRAMEWORK_ROOT))
    if os.name == "nt":
        # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x08000000 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen([str(py), str(cfg.service_py)], **kwargs)
    finally:
        err.close()
    return proc.pid


def ensure_running(cfg: BrokerConfig, *, port: int | None = None) -> dict | None:
    """Make sure a CURRENT-code service is up. Returns its ping payload, or
    None when one could not be started (caller falls back to direct)."""
    pong = ping(cfg, port=port)
    if pong is not None:
        stale = (pong.get("proto") != PROTO
                 or pong.get("code_stamp") != runtime.code_stamp(cfg))
        if not stale:
            return pong
        # Stale daemon: restart. If it will not die, keep using it (it still
        # serializes correctly; it just runs older code).
        if not stop(cfg, port=port):
            return pong
    try:
        spawn(cfg)
    except OSError:
        return None
    deadline = time.time() + _SPAWN_WAIT_S
    while time.time() < deadline:
        pong = ping(cfg, port=port)
        if pong is not None:
            return pong
        time.sleep(0.25)
    return None


# --------------------------------------------------------------------------- #
# The calls used by tool dispatchers
# --------------------------------------------------------------------------- #
def _timeout_for(cfg: BrokerConfig, parsed) -> float:
    """Generous per-request wait: the action's own waits plus queue allowance
    (other sessions' commands run first). Env override wins."""
    raw = os.environ.get(cfg.timeout_env, "")
    if raw.strip():
        try:
            return float(raw)
        except ValueError:
            pass
    wait_ms = getattr(parsed, "wait", 0) or 0
    reply_ms = getattr(parsed, "timeout", 0) or 0
    est = 120 + 2 * (wait_ms / 1000.0) + (reply_ms / 1000.0)
    return max(900.0, est + 600.0)


def _tag(result, resp: dict, via: str):
    if isinstance(result, dict):
        result.setdefault("via", via)
        if "queue_wait_ms" in resp:
            result.setdefault("service_queue_wait_ms", resp["queue_wait_ms"])
    return result


def _raise_remote(resp: dict):
    err = resp.get("error") or {}
    raise ServiceRemoteError(
        err.get("code") or "error",
        err.get("message") or "service reported an error",
        err.get("details") or {},
        int(resp.get("exit_code") or 1),
    )


def call(cfg: BrokerConfig, action: str, argv: list[str], parsed, *,
         dispatch_direct) -> dict:
    """Run a TOOL ACTION through the broker. ``dispatch_direct(action, argv)``
    is the in-process fallback, used ONLY when nothing was ever submitted."""
    pong = ensure_running(cfg)
    if pong is None:
        result = dispatch_direct(action, argv)
        if isinstance(result, dict):
            result.setdefault("via", "direct-fallback")
            result.setdefault(
                "service_fallback",
                f"the {cfg.tool} serializing service could not be started; "
                f"executed in-process instead (see {cfg.spawn_err_path})")
        return result
    try:
        resp = _request(cfg, {"op": "run", "action": action, "argv": list(argv)},
                        read_timeout=_timeout_for(cfg, parsed))
    except OSError as exc:
        # Connect/send failed AFTER a good ping — the service just died and
        # nothing was submitted, so direct is still safe.
        result = dispatch_direct(action, argv)
        if isinstance(result, dict):
            result.setdefault("via", "direct-fallback")
            result.setdefault("service_fallback",
                              f"service vanished before accepting the request "
                              f"({exc.__class__.__name__}); executed in-process")
        return result
    if resp.get("ok"):
        return _tag(resp.get("result"), resp, "service")
    _raise_remote(resp)


def web_steps(cfg: BrokerConfig, session: str, steps: list, *, url=None,
              headless: bool = True, read_timeout: float | None = None,
              dispatch_direct=None) -> dict:
    """Run a GENERIC web-tool step list through the broker owning ``session``
    (how `web run/get-text/screenshot` stay serialized). Same fallback rules
    as ``call``: ``dispatch_direct()`` (no args) only when never submitted."""
    pong = ensure_running(cfg)
    if pong is None:
        if dispatch_direct is None:
            raise ServiceError(
                f"the {cfg.tool} service (owner of session {session!r}) could "
                f"not be started; see {cfg.spawn_err_path}")
        result = dispatch_direct()
        if isinstance(result, dict):
            result.setdefault("via", "direct-fallback")
        return result
    req = {"op": "web-steps", "session": session, "steps": steps,
           "url": url, "headless": headless}
    try:
        resp = _request(cfg, req, read_timeout=read_timeout or 900.0)
    except OSError:
        if dispatch_direct is None:
            raise ServiceError(
                f"the {cfg.tool} service vanished before accepting the request")
        result = dispatch_direct()
        if isinstance(result, dict):
            result.setdefault("via", "direct-fallback")
        return result
    if resp.get("ok"):
        return _tag(resp.get("result"), resp, "service")
    _raise_remote(resp)
