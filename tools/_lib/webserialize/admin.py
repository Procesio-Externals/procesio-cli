"""The three service-admin actions every broker-backed tool exposes.

These are plain functions over a BrokerConfig; each tool wraps them in its own
ActionDef (needs_driver/needs_client False) so they never route and always
work — even when the service is wedged.
"""
from __future__ import annotations

from tools._lib.webserialize import client, runtime
from tools._lib.webserialize.config import BrokerConfig
from tools._lib.webserialize.errors import ServiceError


def service_status(cfg: BrokerConfig) -> dict:
    pong = client.ping(cfg)
    if pong is None:
        return {
            "running": False,
            "tool": cfg.tool,
            "port": cfg.effective_port(),
            "note": "no service is listening; it auto-starts on the next "
                    "browser action (or run service-start)",
            "stale_state_file": runtime.read_state(cfg),
            "log": str(cfg.log_path),
        }
    status = client.request_status(cfg) or {}
    status.setdefault("running", True)
    status["port"] = cfg.effective_port()
    status["code_current"] = pong.get("code_stamp") == runtime.code_stamp(cfg)
    if not status["code_current"]:
        status["note"] = ("service runs STALE code (tool edited since it "
                          "started); the next routed command restarts it "
                          "automatically, or run service-stop + service-start")
    return status


def service_start(cfg: BrokerConfig) -> dict:
    pong = client.ensure_running(cfg)
    if pong is None:
        raise ServiceError(
            f"could not start the {cfg.tool} service; check "
            f"{cfg.spawn_err_path} and {cfg.log_path}"
        )
    status = client.request_status(cfg) or {}
    return {"running": True, "pid": pong.get("pid"),
            "port": cfg.effective_port(), "status": status}


def service_stop(cfg: BrokerConfig, *, wait_s: float = 60) -> dict:
    was_running = client.ping(cfg) is not None
    stopped = client.stop(cfg, wait_s=wait_s)
    out = {"was_running": was_running, "stopped": stopped,
           "tool": cfg.tool, "port": cfg.effective_port()}
    if not stopped:
        out["note"] = ("service did not exit within the wait window "
                       "(a long command may be mid-flight); re-run, or check "
                       f"{cfg.log_path}")
    else:
        out["note"] = ("profile released — safe to log in "
                       "(web save-session) or use --direct")
    return out
