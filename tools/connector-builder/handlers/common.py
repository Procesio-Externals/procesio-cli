"""Shared argparse + JSON-parsing helpers for connector-builder handlers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import requests

from client import build_is_settled
from errors import ApiError, UsageError


def parse_json(raw: str | None, *, what: str = "value", expect: type | None = None) -> Any:
    """Parse a JSON CLI argument; raise UsageError with a helpful message."""
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"--{what} must be valid JSON, got: {e}") from e
    if expect is not None and not isinstance(data, expect):
        names = expect.__name__ if isinstance(expect, type) else " or ".join(
            t.__name__ for t in expect)
        raise UsageError(f"--{what} must be a JSON {names}")
    return data


def load_text_or_file(inline: str | None, file_path: str | None, *, what: str) -> str | None:
    """Return inline text, or read it from a file (file wins precedence check is
    XOR-ish: at most one). Used for content / config payloads that may be large."""
    if inline is not None and file_path is not None:
        raise UsageError(f"pass either --{what} or --{what}-file, not both")
    if file_path is not None:
        p = Path(file_path)
        if not p.is_file():
            raise UsageError(f"--{what}-file not found: {file_path}")
        return p.read_text(encoding="utf-8")
    return inline


def add_build_id(p: argparse.ArgumentParser) -> None:
    p.add_argument("--build-id", dest="build_id", required=True,
                   help="Build UUID")


def add_pagination(p: argparse.ArgumentParser, default_per_page: int = 20) -> None:
    p.add_argument("--page", type=int, default=1, help="Page number (default 1)")
    p.add_argument("--per-page", dest="per_page", type=int, default=default_per_page,
                   help=f"Items per page (default {default_per_page})")


def add_wait_args(p: argparse.ArgumentParser) -> None:
    """Opt-in polling for a synchronous LLM stage that 504s at the proxy but
    completes server-side."""
    p.add_argument("--wait", action="store_true",
                   help="Poll get-build until the stage settles (survives the proxy 504)")
    p.add_argument("--wait-timeout", dest="wait_timeout", type=int, default=600,
                   help="Max seconds to poll when --wait (default 600)")
    p.add_argument("--poll-interval", dest="poll_interval", type=int, default=8,
                   help="Seconds between polls when --wait (default 8)")


# Proxy/gateway statuses that mean "the backend is still working" rather than a
# real failure — swallow these under --wait and fall through to polling.
_TRANSIENT_HTTP = {502, 503, 504}


def run_with_optional_wait(client, build_id: str, trigger: Callable[[], Any],
                           args, *, until: str = "settled") -> dict:
    """Run a stage-triggering call. Without --wait, return its result verbatim.
    With --wait: record the build's updated_at, fire the trigger (swallowing a
    502/503/504 or a client-side timeout — the stage keeps running server-side),
    then poll get-build until settled. Returns the settled build detail plus
    ``waited``/``settled`` markers (and ``trigger_note`` if the trigger 504'd)."""
    if not getattr(args, "wait", False):
        return trigger()

    baseline = None
    try:
        baseline = client.get_build(build_id).get("updated_at")
    except Exception:  # noqa: BLE001 - baseline is best-effort
        baseline = None

    note = None
    try:
        trigger()
    except ApiError as e:
        if e.status_code not in _TRANSIENT_HTTP:
            raise
        note = f"trigger returned HTTP {e.status_code}; polled for completion"
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        note = "trigger timed out client-side; polled for completion"

    build = client.wait_for_settled(
        build_id, timeout=args.wait_timeout, interval=args.poll_interval,
        until=until, baseline_updated_at=baseline)
    out = dict(build)
    out["waited"] = True
    out["settled"] = build_is_settled(build, until)
    if note:
        out["trigger_note"] = note
    return out
