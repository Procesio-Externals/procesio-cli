"""The broker registry: which tools run a serializing broker, on which port,
owning which persistent-profile/storageState session names.

This is INFRASTRUCTURE config (ports must be unique and stable across tools),
not a discoverable tool list — tools still register through their manifests.
The web tool uses ``owner_of_session`` to route its generic run/get-text/
screenshot commands through the broker that owns the target session, so even
ad-hoc web commands cannot race a tool's profile.
"""
from __future__ import annotations

from tools._lib.webserialize.config import TOOLS_ROOT, BrokerConfig


def _cfg(tool: str, port: int, env_prefix: str, sessions: tuple[str, ...]) -> BrokerConfig:
    root = TOOLS_ROOT / tool
    web = TOOLS_ROOT / "web"
    return BrokerConfig(
        tool=tool, port=port, env_prefix=env_prefix, sessions=sessions,
        code_dirs=(root, root / "handlers", web, web / "handlers"),
    )


CONFIGS: dict[str, BrokerConfig] = {
    # whatsapp-personal keeps its original port + env names (WHATSAPP_DIRECT...)
    "whatsapp-personal": _cfg("whatsapp-personal", 47611, "WHATSAPP", ("whatsapp",)),
    "ryver-web":         _cfg("ryver-web",         47612, "RYVER_WEB", ("ryver",)),
    "fgo-web":           _cfg("fgo-web",           47613, "FGO_WEB",   ("fgo",)),
    "mirro":             _cfg("mirro",             47614, "MIRRO",     ("mirro",)),
    # google-meet registers its broker for future use; v1 join runs direct (one
    # long blocking capture per meeting) so the LeasedDriver proxy does not sit
    # between the capture loop and the page. See todo/google-meet-assistant.md.
    "google-meet":       _cfg("google-meet",       47615, "GOOGLE_MEET", ("google-meet",)),
}


def get(tool: str) -> BrokerConfig:
    return CONFIGS[tool]


def owner_of_session(session: str) -> BrokerConfig | None:
    """The broker that owns a session/profile name, or None (unowned sessions
    — e.g. 'google' — keep the direct behavior)."""
    for cfg in CONFIGS.values():
        if session in cfg.sessions:
            return cfg
    return None
