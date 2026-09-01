"""Local-only access gate for the dashboard.

Threat model: single user, own laptop, server bound to 127.0.0.1. The token stops
another local process (or a random browser tab hitting localhost) from driving the
API. It is NOT multi-user auth - that is out of scope until the shared/remote mode
is built.

Secrets never pass through here on the way out: no GET ever returns a stored
credential value, and set-credential receives values only over loopback POST which
are piped straight to the credential store (see runner.set_credential).
"""
from __future__ import annotations

import hmac
import secrets as _secrets  # stdlib


_TOKEN = _secrets.token_urlsafe(24)


def token() -> str:
    return _TOKEN


def token_ok(candidate: str | None) -> bool:
    """Constant-time compare so a wrong token leaks no timing signal."""
    if not candidate:
        return False
    return hmac.compare_digest(candidate, _TOKEN)
