"""Credential access - a facade over a pluggable backend (see ``creds_backends``).

Public API is unchanged: ``get`` / ``get_optional`` / ``has`` / ``set_secret`` /
``delete``. The backend is chosen once by the ``AAT_CREDS_BACKEND`` env var; the
default (unset) is ``windows`` = Windows Credential Manager, the historical
behaviour, so a local Claude Code session is never affected. Import-safe on any OS:
the Windows/keyring code loads only when the windows backend is selected, so this
module imports cleanly inside a Linux container.

Credentials are identified as ``agents-and-tools:<tool>:<secret>``.
"""
from __future__ import annotations

import os

from tools._lib import creds_backends

NAMESPACE = "agents-and-tools"

_backend = None


def _service(tool: str) -> str:
    return f"{NAMESPACE}:{tool}"


def _b():
    global _backend
    if _backend is None:
        _backend = creds_backends.make(os.environ.get("AAT_CREDS_BACKEND"))
    return _backend


def reset_backend() -> None:
    """Drop the cached backend. For tests, or after changing AAT_CREDS_BACKEND."""
    global _backend
    _backend = None


def get(tool: str, secret_name: str) -> str:
    """Return the secret value. Raises KeyError if missing."""
    value = _b().get_optional(tool, secret_name)
    if value is None:
        raise KeyError(f"missing credential: {_service(tool)} / {secret_name}")
    return value


def get_optional(tool: str, secret_name: str) -> str | None:
    """Return the secret value or None if missing. Never raises on absence."""
    return _b().get_optional(tool, secret_name)


def has(tool: str, secret_name: str) -> bool:
    return _b().get_optional(tool, secret_name) is not None


def set_secret(tool: str, secret_name: str, value: str) -> None:
    _b().set(tool, secret_name, value)


def delete(tool: str, secret_name: str) -> None:
    _b().delete(tool, secret_name)
