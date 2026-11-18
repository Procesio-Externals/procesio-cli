"""Read the per-turn token Web-Api mints for one AAT turn (a chat message or a run step).

Format: ``aat1.<payload>.<secret>.<signature>``, every part Base64Url without padding.
The payload is JSON ``{"ws", "u", "m", "exp"}`` - workspace, user, message, expiry (unix s).

This module only READS the payload: it is encoded, not encrypted, and the signature is an
HMAC whose key only Web-Api holds. So what is read here is a claim, not a proof. It is
good for LOCAL scoping (which user-data folder a tool subprocess uses); anything that
unlocks a credential is decided by Web-Api, which verifies the signature and the stored
row before answering (see turn_credentials).
"""
from __future__ import annotations

import base64
import json
import time
import uuid

PREFIX = "aat1"
HEADER = "X-AAT-Turn-Token"

# PROCESIO's personal workspace is Guid.Empty. For user data it means "no workspace
# dimension" (userdata keys it <root>/<user>), so it is returned as None.
_PERSONAL_WORKSPACE = str(uuid.UUID(int=0))

# A real token is ~280 chars. Anything far beyond that is not ours.
_MAX_LENGTH = 512


def read(token: str | None) -> dict | None:
    """The token's claims as ``{"workspace", "user", "message", "expires_at"}``, or None
    when the value is missing, malformed, or already past its expiry.

    ``workspace`` is None for the personal workspace. Never raises."""
    if not token or len(token) > _MAX_LENGTH:
        return None
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != PREFIX:
        return None
    try:
        raw = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
        user = str(uuid.UUID(str(payload["u"])))
        workspace = str(uuid.UUID(str(payload["ws"])))
        message = str(uuid.UUID(str(payload["m"])))
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError):
        return None
    if expires_at <= int(time.time()):
        return None
    return {
        "workspace": None if workspace == _PERSONAL_WORKSPACE else workspace,
        "user": user,
        "message": message,
        "expires_at": expires_at,
    }
