"""HTTP client for the AI Connector Builder API (connector-builder.procesio.app).

Both supported auth modes resolve to the SAME wire shape: an
``Authorization: Bearer <token>`` header (verified against the backend's
``app/core/permissions.py`` — an API key is just a bearer token that starts with
``acb_``). So the client only ever sets one header; how the token is obtained is
the only difference between the two modes:

  1. **API key** (default, simplest): the ``acb_...`` key, stored under
     ``agents-and-tools:connector-builder:api-key``. Used verbatim as the bearer.
  2. **Username / password**: ``username`` + ``password`` secrets → ``POST
     /auth/login`` → ``access_token`` (a JWT) → used as the bearer. This is the
     "web-tool" login the user referred to, done over the REST API instead of a
     browser (the app exposes the same backend at ``/api/*``).

Selection order (override with env ``CONNECTOR_BUILDER_AUTH=apikey|userpass``):
api-key if stored, else username+password. Base URL defaults to the production
host and is overridable via env ``CONNECTOR_BUILDER_BASE_URL``.

See CONNECTOR-BUILDER-API-NOTES.md for the wire details.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

from errors import ApiError, CredentialError

# A build is "done for now" when it pauses for the user or reaches a terminal
# state. The sync LLM stages (gather/answer/revise-plan) 504 at the proxy but
# keep running server-side, so --wait polls get-build until one of these holds.
TERMINAL_STATUSES = {"completed", "failed", "delivered", "succeeded", "cancelled"}


def build_is_settled(build: dict, until: str = "settled") -> bool:
    """until='terminal' → only completed/failed/... ; 'settled' → also a
    waiting_user pause (a stage finished and is waiting for the next action)."""
    status = (build.get("status") or "").lower()
    step = (build.get("step_status") or "").lower()
    if status in TERMINAL_STATUSES:
        return True
    if until == "settled" and step == "waiting_user":
        return True
    return False

TOOL = "connector-builder"

# Production: Caddy strips the /api/* prefix and forwards to the backend, so the
# REST surface documented in documentation/03-API-REFERENCE.md lives under /api.
DEFAULT_BASE_URL = "https://connector-builder.procesio.app/api"

TIMEOUT_CONNECT = 10
TIMEOUT_READ = 180  # pipeline gather/plan calls can be slow; downloads stream


def get_base_url() -> str:
    return os.environ.get("CONNECTOR_BUILDER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _cred(name: str) -> Optional[str]:
    # Env override first (handy for CI / tests), then Credential Manager.
    env = os.environ.get(f"CONNECTOR_BUILDER_{name.upper().replace('-', '_')}")
    if env:
        return env
    import sys
    framework_root = Path(__file__).resolve().parents[2]
    if str(framework_root) not in sys.path:
        sys.path.insert(0, str(framework_root))
    from tools._lib import creds
    return creds.get_optional(TOOL, name)


def resolve_token() -> str:
    """Resolve the bearer token per the configured/derived auth mode."""
    mode = os.environ.get("CONNECTOR_BUILDER_AUTH", "").strip().lower()
    api_key = _cred("api-key")
    username = _cred("username")
    password = _cred("password")

    if not mode:
        mode = "apikey" if api_key else ("userpass" if username and password else "")

    if mode == "apikey":
        if not api_key:
            raise CredentialError(
                "auth mode 'apikey' but no api-key stored. Store it with:\n"
                "    python scripts/set-credential.py connector-builder api-key")
        return api_key
    if mode == "userpass":
        if not (username and password):
            raise CredentialError(
                "auth mode 'userpass' but username/password not both stored. Set:\n"
                "    python scripts/set-credential.py connector-builder username\n"
                "    python scripts/set-credential.py connector-builder password")
        return login(username, password)
    raise CredentialError(
        "no connector-builder credential found. Store an API key:\n"
        "    python scripts/set-credential.py connector-builder api-key\n"
        "or a username + password:\n"
        "    python scripts/set-credential.py connector-builder username\n"
        "    python scripts/set-credential.py connector-builder password")


def login(username: str, password: str, base_url: Optional[str] = None) -> str:
    """POST /auth/login → access_token (JWT). Used by the userpass auth mode."""
    base = (base_url or get_base_url()).rstrip("/")
    r = requests.post(
        f"{base}/auth/login",
        json={"email": username, "password": password},
        timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
    )
    if r.status_code >= 400:
        raise ApiError(r.status_code, "/auth/login", _detail(r))
    tok = r.json().get("access_token")
    if not tok:
        raise ApiError(r.status_code, "/auth/login", "login returned no access_token")
    return tok


def _detail(resp: "requests.Response") -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return str(body.get("detail") or body.get("message") or body)
        return str(body)
    except ValueError:
        return (resp.text or "")[:500]


class ConnectorBuilderClient:
    """Thin REST wrapper. One method per HTTP verb, plus multipart + binary
    download. Every response is JSON except the binary download helpers."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None,
                 session: Any = None):
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self._token = token  # lazily resolved on first use if None
        self._s = session or requests.Session()

    # -- auth ---------------------------------------------------------------
    @property
    def token(self) -> str:
        if self._token is None:
            self._token = resolve_token()
        return self._token

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "agents-and-tools-connector-builder/0.1",
        }
        if extra:
            h.update(extra)
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    # -- verbs --------------------------------------------------------------
    def request(self, method: str, path: str, *, params: Optional[dict] = None,
                json_body: Any = None) -> Any:
        r = self._s.request(
            method.upper(), self._url(path),
            params=params, json=json_body,
            headers=self._headers(),
            timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
        )
        if r.status_code >= 400:
            raise ApiError(r.status_code, path, _detail(r))
        if r.status_code == 204 or not (r.content or b"").strip():
            return {}
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json_body: Any = None, params: Optional[dict] = None) -> Any:
        return self.request("POST", path, params=params, json_body=json_body)

    def put(self, path: str, json_body: Any = None) -> Any:
        return self.request("PUT", path, json_body=json_body)

    def patch(self, path: str, json_body: Any = None) -> Any:
        return self.request("PATCH", path, json_body=json_body)

    def delete(self, path: str, params: Optional[dict] = None) -> Any:
        return self.request("DELETE", path, params=params)

    # -- polling ------------------------------------------------------------
    def get_build(self, build_id: str) -> dict:
        return self.get(f"/builds/{build_id}")

    def wait_for_settled(self, build_id: str, *, timeout: int = 600,
                         interval: int = 8, until: str = "settled",
                         baseline_updated_at: Optional[str] = None,
                         sleep=time.sleep, clock=time.monotonic) -> dict:
        """Poll get-build until the build is settled (per `until`) AND — when a
        baseline is given — its updated_at has advanced past it (so we never
        return the pre-trigger state on a fast poll). Returns the last build seen
        even if the timeout is hit (caller checks build_is_settled)."""
        deadline = clock() + max(0, timeout)
        build = self.get_build(build_id)
        while True:
            advanced = baseline_updated_at is None or \
                build.get("updated_at") != baseline_updated_at
            if advanced and build_is_settled(build, until):
                return build
            if clock() >= deadline:
                return build
            sleep(interval)
            build = self.get_build(build_id)

    # -- binary download ----------------------------------------------------
    def download(self, path: str, out_path: str, params: Optional[dict] = None) -> dict:
        """Stream a binary endpoint (artifact / file download / zip) to disk.
        Returns {out, bytes, filename, content_type}."""
        r = self._s.get(
            self._url(path), params=params, headers=self._headers(),
            timeout=(TIMEOUT_CONNECT, TIMEOUT_READ), stream=True,
        )
        if r.status_code >= 400:
            raise ApiError(r.status_code, path, _detail(r))
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        return {
            "out": str(out),
            "bytes": total,
            "filename": _content_disposition_filename(r) or out.name,
            "content_type": r.headers.get("Content-Type"),
        }


def _content_disposition_filename(resp: "requests.Response") -> Optional[str]:
    cd = resp.headers.get("Content-Disposition", "")
    if "filename=" in cd:
        return cd.split("filename=", 1)[1].strip().strip('"').split(";", 1)[0]
    return None
