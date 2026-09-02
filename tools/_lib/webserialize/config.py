"""BrokerConfig — everything that parameterizes one tool's serializing broker.

One broker per tool, one fixed localhost port per broker (binding the port IS
the single-instance guard), one `.service/` runtime dir under the tool root.
The env-var names are derived from ``env_prefix`` so every tool gets the same
knobs (`<PREFIX>_DIRECT`, `<PREFIX>_SERVICE_PORT`, ...) — for
``whatsapp-personal`` the prefix is ``WHATSAPP``, which keeps the original
variable names working unchanged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROTO = 1
HOST = "127.0.0.1"

DEFAULT_IDLE_CLOSE_S = 120     # close the warm browser after this much idle
DEFAULT_EXIT_IDLE_S = 86400    # exit the service process after this much idle

# tools/_lib/webserialize/config.py -> repo root
FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
TOOLS_ROOT = FRAMEWORK_ROOT / "tools"
LIB_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class BrokerConfig:
    tool: str                      # registry key, e.g. "whatsapp-personal"
    port: int                      # fixed default port (env can override)
    env_prefix: str                # "WHATSAPP" -> WHATSAPP_DIRECT, ...
    sessions: tuple[str, ...]      # persistent-profile session names it OWNS
    code_dirs: tuple[Path, ...] = field(default=())  # *.py dirs for code_stamp

    # --- paths --------------------------------------------------------------
    @property
    def tool_root(self) -> Path:
        return TOOLS_ROOT / self.tool

    @property
    def service_py(self) -> Path:
        return self.tool_root / "service.py"

    @property
    def service_dir(self) -> Path:
        return self.tool_root / ".service"

    @property
    def state_path(self) -> Path:
        return self.service_dir / "state.json"

    @property
    def log_path(self) -> Path:
        return self.service_dir / "service.log"

    @property
    def spawn_err_path(self) -> Path:
        return self.service_dir / "spawn-err.log"

    # --- env knobs ------------------------------------------------------------
    @property
    def direct_env(self) -> str:
        return f"{self.env_prefix}_DIRECT"

    @property
    def worker_env(self) -> str:
        return f"{self.env_prefix}_SERVICE_WORKER"

    @property
    def port_env(self) -> str:
        return f"{self.env_prefix}_SERVICE_PORT"

    @property
    def timeout_env(self) -> str:
        return f"{self.env_prefix}_SERVICE_TIMEOUT_S"

    @property
    def idle_close_env(self) -> str:
        return f"{self.env_prefix}_SERVICE_IDLE_S"

    @property
    def exit_idle_env(self) -> str:
        return f"{self.env_prefix}_SERVICE_EXIT_S"

    def effective_port(self) -> int:
        raw = os.environ.get(self.port_env, "")
        try:
            return int(raw) if raw.strip() else self.port
        except ValueError:
            return self.port

    def stamp_dirs(self) -> tuple[Path, ...]:
        """Dirs whose *.py mtimes form the code stamp. The lib itself is always
        included: a webserialize change must restart every broker."""
        return tuple(self.code_dirs) + (LIB_DIR,)
