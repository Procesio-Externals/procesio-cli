"""Session-management handlers: save-session, list-sessions, delete-session.

These do NOT receive an injected driver (``needs_driver=False``):
  * ``save-session`` is interactive - it launches its own HEADED browser via the
    public API and blocks for a human ENTER before saving storageState.
  * ``list-sessions`` / ``delete-session`` only touch the sessions directory.
"""
from __future__ import annotations

import argparse

from tools.web import api, sessions
from tools.web.actiondef import ActionDef


def _release_owning_broker(name: str) -> str | None:
    """If a serializing broker owns this session (whatsapp/ryver/fgo/mirro),
    stop it first: its warm browser may hold the profile, and capturing or
    deleting a session under it would race the broker. Returns the owning
    tool's name when a running broker was stopped, else None. Best-effort —
    a broker that cannot be reached must not block a login capture."""
    try:
        from tools._lib.webserialize import client as ws_client
        from tools._lib.webserialize import registry as ws_registry
    except Exception:  # noqa: BLE001 - lib unavailable must never block
        return None
    cfg = ws_registry.owner_of_session(name)
    if cfg is None:
        return None
    try:
        if ws_client.ping(cfg) is None:
            return None
        ws_client.stop(cfg)
        return cfg.tool
    except Exception:  # noqa: BLE001
        return None


def save_session(args) -> dict:
    """Capture a login session interactively (headed browser + ENTER signal)."""
    stopped = _release_owning_broker(args.name)
    out = api.save_session(args.name, args.url, channel=args.channel,
                           persistent=args.persistent,
                           wait_seconds=getattr(args, "wait_seconds", None),
                           wait_until_url_excludes=getattr(
                               args, "wait_until_url_excludes", None))
    if stopped:
        out["broker_stopped"] = stopped
        out["note"] = (f"the {stopped} serializing broker was stopped to free "
                       "the session; it auto-restarts on that tool's next command")
    return out


def _save_session_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True,
                   help="Session name (letters/digits/._-; how you'll reference it later)")
    p.add_argument("--url", required=True,
                   help="Login URL to open in the headed browser")
    p.add_argument("--channel", default=None,
                   help="Optional Chromium channel: 'chrome' or 'msedge' "
                        "(use a real browser instead of the bundled Chromium)")
    p.add_argument("--persistent", action="store_true",
                   help="Save a PERSISTENT browser profile (user-data-dir) instead "
                        "of a storageState snapshot. Required for IndexedDB-auth "
                        "sites like WhatsApp Web whose login a snapshot can't restore.")
    p.add_argument("--wait-seconds", type=int, default=None,
                   help="Wait this long for the login instead of blocking on ENTER. "
                        "REQUIRED when an agent launches this flow: agent stdin is "
                        "EOF, so the ENTER wait returns instantly and saves a "
                        "half-authenticated profile.")
    p.add_argument("--wait-until-url-excludes", default=None,
                   help="With --wait-seconds, finish as soon as the address bar "
                        "leaves this host (e.g. 'accounts.google.com'), instead of "
                        "waiting the full time.")


def list_sessions(args) -> dict:
    items = sessions.list_all()
    return {
        "sessions": items,
        "count": len(items),
        "dir": str(sessions.sessions_dir()),
    }


def delete_session(args) -> dict:
    sessions.validate_name(args.name)
    confirm = getattr(args, "confirm", False)
    # Only disturb the broker when we are actually going to delete; a preview
    # must not have side effects.
    stopped = _release_owning_broker(args.name) if confirm else None
    out = sessions.delete(args.name, confirm=confirm)
    if stopped:
        out["broker_stopped"] = stopped
    return out


def _delete_session_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="Session name to delete")
    p.add_argument("--confirm", action="store_true",
                   help="Actually delete. Without it this only PREVIEWS what "
                        "would be removed - deleting a session destroys a login "
                        "that only a human at a browser can re-establish.")


ACTIONS = {
    "save-session": ActionDef(
        save_session, _save_session_args, needs_driver=False,
        description="Interactively capture a login session (headed browser; press ENTER to save).",
    ),
    "list-sessions": ActionDef(
        list_sessions, needs_driver=False,
        description="List saved sessions (names + metadata only, never contents).",
    ),
    "delete-session": ActionDef(
        delete_session, _delete_session_args, needs_driver=False,
        description="Delete ALL of a saved session's artifacts (storageState + "
                    "persistent profile + cookie sidecar). Previews unless --confirm.",
    ),
}
