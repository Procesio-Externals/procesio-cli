"""Fetch a turn's PROCESIO credentials from Web-Api.

Two calls, in this order:

1. ``GET {AAT_WEBAPI_URL}/internal/aat/procesio-key`` - the turn user's AI assistant API key.
   Headers: ``prc-service`` (AAT_WEBAPI_SERVICE_NAME, default AatRuntime) and ``prc-code``
   (AAT_WEBAPI_SERVICE_CODE) say who is calling; ``X-AAT-Turn-Token`` says whose key. Web-Api
   decides the workspace and user from the token alone. A 404 is Web-Api refusing the call (bad
   service code, or a token that is unknown, expired or revoked) - it deliberately looks the same
   as a missing route, so it is reported as "could not be resolved", not "not configured".

2. ``GET {AAT_WEBAPI_URL}/api/aat/tool-credentials/{templateId}?host=`` - a tool's credentials,
   authenticated with that key (``key`` / ``value`` / ``workspaceId`` headers), so Web-Api answers
   with exactly what the key's user can see: ``[{id, name, values: {be_id: value}}]``. It carries
   the same ``prc-service`` / ``prc-code`` pair as call 1, for Web-Api's [SecureHttpRequest].

One turn makes many tool calls, so what a turn has resolved is kept for that turn: IN MEMORY only,
keyed by a hash of its turn token, and gone after AAT_TURN_CACHE_IDLE_SECONDS (default 120) with no
call, or when the token expires, whichever is first. This server is not told when a turn ends, so
the idle window is what bounds how long a key outlives its turn. A refused key is kept too: a model
that ignores "do not retry" would otherwise send Web-Api one request per tool call for the rest of
the turn. A key generated or revoked mid-turn takes effect on the next turn. Nothing here logs or
writes a secret. Every
outcome comes back as a result object; nothing raises - a tool that needs no credential must still
run when Web-Api is down.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import metrics
import turn_token as turn_token_reader

_KEY_ROUTE = "internal/aat/procesio-key"
_TOOL_ROUTE = "api/aat/tool-credentials/"
_TIMEOUT_SECONDS = 10


@dataclass
class ProcesioKey:
    """The turn user's PROCESIO API key, or why there is none."""

    key: str | None = None
    value: str | None = None
    workspace_id: str | None = None
    # Set whenever key is None: the sentence the model should read. It names the fix, so the model
    # does not go looking for one.
    message: str | None = None

    def __repr__(self) -> str:  # never print the value, whatever ends up formatting this object
        return f"ProcesioKey(key={'set' if self.key else None}, workspace_id={self.workspace_id!r})"


@dataclass
class ToolCredentials:
    """A tool's candidate credentials: [{id, name, values}], or why they could not be read."""

    items: list[dict] = field(default_factory=list)
    message: str | None = None
    # PROCESIO refused the key itself (401/403): what the turn remembers must be dropped.
    refused: bool = False

    def __repr__(self) -> str:
        return f"ToolCredentials(count={len(self.items)}, message={self.message!r})"


def configured() -> bool:
    """True when this server knows how to reach Web-Api for credentials."""
    return bool(os.environ.get("AAT_WEBAPI_URL") and os.environ.get("AAT_WEBAPI_SERVICE_CODE"))


def _service_headers() -> dict:
    """Who is calling Web-Api: ``prc-service`` (AAT_WEBAPI_SERVICE_NAME, default AatRuntime) and
    ``prc-code`` (AAT_WEBAPI_SERVICE_CODE). Web-Api's SecureInternalRequests answers 404 to a
    secured endpoint called without a pair it knows. Only called once configured() holds."""
    return {"prc-service": os.environ.get("AAT_WEBAPI_SERVICE_NAME", "AatRuntime"),
            "prc-code": os.environ["AAT_WEBAPI_SERVICE_CODE"]}


def _base() -> str:
    return os.environ["AAT_WEBAPI_URL"].rstrip("/") + "/"


def _lowered(body) -> dict:
    # Web-Api's JSON casing is its serializer's choice; read it either way.
    return {str(k).lower(): v for k, v in body.items()} if isinstance(body, dict) else {}


@dataclass
class _TurnEntry:
    key: ProcesioKey
    tools: dict = field(default_factory=dict)  # (template_id, host) -> ToolCredentials
    expires_at: float = 0.0  # the turn token's own expiry: never kept past it
    idle_until: float = 0.0


_CACHE: dict[str, _TurnEntry] = {}
_CACHE_LOCK = threading.Lock()


def _idle_seconds() -> int:
    try:
        return max(0, int(os.environ.get("AAT_TURN_CACHE_IDLE_SECONDS", "120")))
    except ValueError:
        return 120


def _turn_id(turn_token: str) -> str:
    # The token itself is never a dict key: a hash identifies the turn without holding it.
    return hashlib.sha256(turn_token.encode("utf-8")).hexdigest()


def _purge(now: float) -> None:
    """Drop every turn past its idle window or its token's expiry. Caller holds the lock."""
    for stale in [k for k, e in _CACHE.items() if e.expires_at <= now or e.idle_until <= now]:
        del _CACHE[stale]


_SWEEP_SECONDS = 15
_sweeper: threading.Thread | None = None


def _sweep_forever() -> None:
    while True:
        time.sleep(_SWEEP_SECONDS)
        with _CACHE_LOCK:
            _purge(time.time())


def _ensure_sweeper() -> None:
    """Expiry must not wait for the next request: a turn that ends quietly would otherwise keep its
    key in memory until someone else calls. A daemon thread purges on its own clock."""
    global _sweeper
    with _CACHE_LOCK:
        if _sweeper is None or not _sweeper.is_alive():
            _sweeper = threading.Thread(target=_sweep_forever, name="turn-credentials-sweeper", daemon=True)
            _sweeper.start()


def _entry(turn_id: str, now: float) -> _TurnEntry | None:
    """The live entry of a turn, touched; expired entries of every turn are dropped on the way."""
    with _CACHE_LOCK:
        _purge(now)
        entry = _CACHE.get(turn_id)
        if entry is not None:
            entry.idle_until = min(entry.expires_at, now + _idle_seconds())
        return entry


def refuse(turn_token: str, message: str) -> None:
    """PROCESIO refused this turn's key mid-turn (revoked, say): drop what the turn resolved and
    answer every later call of the turn with `message`, without asking Web-Api again."""
    turn_id = _turn_id(turn_token)
    with _CACHE_LOCK:
        entry = _CACHE.get(turn_id)
        if entry is not None:
            entry.key = ProcesioKey(message=message)
            entry.tools.clear()


def recheck_key(turn_token: str) -> ProcesioKey:
    """A tool that holds the key was refused (401/403): ask Web-Api again whether the key still
    stands. A revoked key turns the rest of the turn into a refusal; a 403 that was only a missing
    permission leaves the key in place. One request per refused call, never per call."""
    fresh = _request_key(turn_token)
    if fresh.key:
        with _CACHE_LOCK:
            entry = _CACHE.get(_turn_id(turn_token))
            if entry is not None:
                entry.key = fresh
        return fresh
    refuse(turn_token, fresh.message or "The AI assistant's PROCESIO API key is no longer valid.")
    return ProcesioKey(message=fresh.message)


def fetch_key(turn_token: str) -> ProcesioKey:
    """The turn user's key: from this turn's memory when it has asked before, else from Web-Api."""
    now = time.time()
    turn_id = _turn_id(turn_token)
    entry = _entry(turn_id, now)
    metrics.credential_cache(metrics.PROCESIO_KEY, entry is not None)
    if entry is not None:
        return entry.key

    key = _request_key(turn_token)
    idle = _idle_seconds()
    if idle:
        claims = turn_token_reader.read(turn_token)
        expires_at = float(claims["expires_at"]) if claims else now + idle
        with _CACHE_LOCK:
            _CACHE[turn_id] = _TurnEntry(key=key, expires_at=expires_at,
                                         idle_until=min(expires_at, now + idle))
        _ensure_sweeper()
    return key


def fetch_tool_credentials(key: ProcesioKey, template_id: str, host: str | None,
                           turn_token: str | None = None) -> ToolCredentials:
    """A tool's credentials: from this turn's memory when another call already read them."""
    entry = _entry(_turn_id(turn_token), time.time()) if turn_token else None
    metrics.credential_cache(metrics.TOOL_CREDENTIALS, entry is not None and (template_id, host) in entry.tools)
    if entry is not None and (template_id, host) in entry.tools:
        return entry.tools[(template_id, host)]

    found = _request_tool_credentials(key, template_id, host)
    if found.refused and turn_token:
        refuse(turn_token, found.message)  # a revoked key must not be served from memory again
    elif entry is not None and not found.message:
        with _CACHE_LOCK:
            entry.tools[(template_id, host)] = found
    return found


def _get(url: str, headers: dict, empty: str):
    """GET `url`. Returns (body, None) or (None, HTTPError | other error)."""
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310 (in-cluster)
            return json.loads(resp.read().decode("utf-8") or empty), None
    except urllib.error.HTTPError as e:
        return None, e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return None, e


def _request_key(turn_token: str) -> ProcesioKey:
    if not configured():
        return ProcesioKey(message=(
            "PROCESIO credentials cannot be resolved: this AAT runtime is not connected to PROCESIO "
            "(AAT_WEBAPI_URL / AAT_WEBAPI_SERVICE_CODE are not set). This is a platform configuration "
            "issue - do not retry."))

    started = metrics.clock()
    body, failure = _get(_base() + _KEY_ROUTE, {
        **_service_headers(),
        "X-AAT-Turn-Token": turn_token,
        "Accept": "application/json",
    }, "{}")
    metrics.credential_fetch(metrics.PROCESIO_KEY, started, failure, refused=(404,))
    if isinstance(failure, urllib.error.HTTPError):
        if failure.code == 404:
            return ProcesioKey(message=(
                "PROCESIO credentials could not be resolved: PROCESIO did not accept this turn's "
                "authorization (the turn may have ended or expired). Do not retry in this turn."))
        return ProcesioKey(message=f"PROCESIO credentials could not be resolved: PROCESIO answered {failure.code}. "
                                   "Do not retry in this turn.")
    if failure is not None:
        return ProcesioKey(message=f"PROCESIO credentials could not be resolved: PROCESIO is unreachable "
                                   f"({type(failure).__name__}). Do not retry in this turn.")

    lowered = _lowered(body)
    if lowered.get("configured") and lowered.get("key") and lowered.get("value"):
        return ProcesioKey(key=str(lowered["key"]), value=str(lowered["value"]),
                           workspace_id=str(lowered.get("workspaceid") or "") or None)
    return ProcesioKey(message=lowered.get("message") or (
        "The AI assistant has no PROCESIO API key for this user. Do not retry: the user has to "
        "generate one in the AI assistant settings first."))


def _request_tool_credentials(key: ProcesioKey, template_id: str, host: str | None) -> ToolCredentials:
    """The key's user's credentials of one template, optionally only those on `host`."""
    url = _base() + _TOOL_ROUTE + urllib.parse.quote(template_id, safe="")
    if host:
        url += "?" + urllib.parse.urlencode({"host": host})
    # The service pair says the caller is this runtime (the endpoint is [SecureHttpRequest]); the
    # key says whose credentials, so Web-Api still answers only with what the key's user can see.
    headers = {**_service_headers(), "key": key.key or "", "value": key.value or "",
               "Accept": "application/json"}
    if key.workspace_id:
        headers["workspaceId"] = key.workspace_id
    started = metrics.clock()
    body, failure = _get(url, headers, "[]")
    metrics.credential_fetch(metrics.TOOL_CREDENTIALS, started, failure, refused=(401, 403))
    if isinstance(failure, urllib.error.HTTPError):
        if failure.code in (401, 403):
            return ToolCredentials(refused=True, message=(
                "PROCESIO refused to show this user's credentials (the user lacks permission to read "
                "credentials in this workspace, or the AI assistant's API key was revoked). Do not retry: "
                "the user has to fix this in PROCESIO."))
        return ToolCredentials(message=f"PROCESIO credentials could not be read: PROCESIO answered {failure.code}. "
                                       "Do not retry in this turn.")
    if failure is not None:
        return ToolCredentials(message=f"PROCESIO credentials could not be read: PROCESIO is unreachable "
                                       f"({type(failure).__name__}). Do not retry in this turn.")

    items = []
    for raw in body if isinstance(body, list) else []:
        lowered = _lowered(raw)
        values = lowered.get("values")
        if isinstance(values, dict):
            items.append({"id": str(lowered.get("id") or ""), "name": str(lowered.get("name") or ""),
                          "values": {str(k): str(v) for k, v in values.items() if v is not None}})
    return ToolCredentials(items=items)
