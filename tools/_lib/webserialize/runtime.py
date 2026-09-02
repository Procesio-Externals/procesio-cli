"""Process-level helpers shared by broker server and client: env parsing, the
venv python, the code stamp (stale-daemon detection) and the state file."""
from __future__ import annotations

import json
import os
from pathlib import Path

from tools._lib.webserialize.config import FRAMEWORK_ROOT, BrokerConfig


def env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() not in ("", "0", "false", "no")


def venv_python() -> Path | None:
    p = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
    if p.exists():
        return p
    p = FRAMEWORK_ROOT / ".venv" / "bin" / "python"
    return p if p.exists() else None


def code_stamp(cfg: BrokerConfig) -> str:
    """Signature of the code a broker's behavior depends on: the max mtime of
    the *.py files in the config's stamp dirs (tool + web tool + this lib).

    The SERVER must freeze this at startup; the client compares its live value
    and restarts the daemon on mismatch. (Computing it live on BOTH sides is a
    bug: they always match and the stale-restart never fires.)"""
    latest = 0
    for d in cfg.stamp_dirs():
        if not d.is_dir():
            continue
        for f in d.glob("*.py"):
            try:
                mt = f.stat().st_mtime_ns
            except OSError:
                continue
            latest = max(latest, mt)
    return str(latest)


def write_state(cfg: BrokerConfig, state: dict) -> None:
    cfg.service_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                              encoding="utf-8")


def read_state(cfg: BrokerConfig) -> dict | None:
    try:
        return json.loads(cfg.state_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def clear_state(cfg: BrokerConfig) -> None:
    try:
        cfg.state_path.unlink()
    except OSError:
        pass
