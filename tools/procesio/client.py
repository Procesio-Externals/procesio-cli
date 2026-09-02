"""ProcesioClient - thin REST wrapper over the PROCESIO Web API.

One instance per CLI invocation, bound to a single credential profile. Every
request is authenticated by tools.procesio.auth (Bearer for userpass profiles,
key/value/workspaceid headers for apikey profiles). The HTTP session is
injectable so the whole test suite runs with zero live calls.

`request()` is the universal entrypoint - it can reach any of the ~247
documented endpoints. The curated handlers (processes, instances, ...) are thin
wrappers over it for ergonomics; they add nothing the generic `request` action
can't do.
"""
from __future__ import annotations

import json
import time
from typing import Any

from tools.procesio import auth, config, environments, profiles, reliability
from tools.procesio.errors import DeadlineExceeded, ProcesioAPIError

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _require_session(session):
    if session is not None:
        return session
    import requests  # already a project dependency

    return requests.Session()


class ProcesioClient:
    def __init__(self, profile_name: str | None = None, *, session=None,
                 profile: dict | None = None, name: str | None = None,
                 workspace_id: str | None = None, environment: str | None = None):
        # Allow tests to inject a profile directly; otherwise resolve from store.
        # Copy so folding the environment URLs in never mutates the caller's dict.
        if profile is not None:
            self.name = name or profile_name or "(injected)"
            self.profile = dict(profile)
        else:
            self.name, resolved = profiles.resolve(profile_name)
            self.profile = dict(resolved)
        # Resolve the active environment (explicit flag > credential binding >
        # default env > Internal-PROD) and fold its host URLs into the profile so
        # config.web_base/app_base/forms_base/auth_base pick them up. An explicit
        # per-profile URL override (rare) still wins via setdefault.
        self.env = environments.resolve(environment, self.profile)
        for key in environments.URL_KEYS:
            val = self.env.get(key)
            if val:
                self.profile.setdefault(key, val)
        self._session = _require_session(session)
        # Per-call override of the active-workspace header. Wins over a profile's
        # own workspace_id, and scopes a userpass cookie session to a workspace.
        self.workspace_id = workspace_id
        # Metadata of the last HTTP round-trip (status / elapsed_s / body_len /
        # headers). Lets a handler report on a write whose empty body can lie
        # (put-projects; see O4 in PROCESIO-API-NOTES.md).
        self.last_meta: dict | None = None

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _parse_body(resp) -> Any:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"raw_text": getattr(resp, "text", "")}

    def _headers(self) -> dict[str, str]:
        base = {"User-Agent": _BROWSER_UA, "Accept": "application/json",
                # REQUIRED by the prod gateway on main routes; omitting -> 401.
                "x-version": config.api_version(self.profile)}
        base.update(auth.auth_headers(self.name, self.profile, self._session))
        if self.workspace_id:
            base["workspaceid"] = self.workspace_id   # override / set active WS
        return base

    def _clear_jar(self) -> None:
        """Drop any cookies the requests Session accumulated. We authenticate via
        an explicit `Cookie` header (auth_headers); if the Session jar also holds
        a (possibly stale) `__Host-procesio.access`, requests sends BOTH and the
        gateway intermittently rejects the request (401). Keeping the jar empty
        guarantees only our managed cookie is sent."""
        try:
            self._session.cookies.clear()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _body_len(resp) -> int:
        text = getattr(resp, "text", None)
        if isinstance(text, str):
            return len(text)
        content = getattr(resp, "content", b"") or b""
        return len(content)

    def _do_http(self, method: str, url: str, params, body,
                 read_timeout, deadline_at: float | None) -> tuple[int, Any]:
        """One HTTP round-trip, under the TOTAL wall-clock deadline. `read_timeout`
        is the per-read inactivity guard handed to requests (None = wait
        indefinitely, for a synchronous run). `deadline_at` is an absolute
        monotonic timestamp (None = exempt); the send runs on a daemon thread so a
        dribbling/held connection cannot outlive it. Records `last_meta`."""
        def _once() -> tuple[int, Any]:
            headers = self._headers()
            if body is not None:
                headers["Content-Type"] = "application/json"
            self._clear_jar()
            t0 = time.monotonic()
            resp = self._session.request(
                method.upper(), url, params=params, json=body,
                headers=headers, timeout=read_timeout,
            )
            status = getattr(resp, "status_code", 0)
            parsed = self._parse_body(resp)
            self.last_meta = {
                "status": status,
                "elapsed_s": round(time.monotonic() - t0, 3),
                "body_len": self._body_len(resp),
                "headers": dict(getattr(resp, "headers", {}) or {}),
            }
            return status, parsed

        remaining = None if deadline_at is None else deadline_at - time.monotonic()
        return reliability.run_with_deadline(_once, remaining)

    # Statuses that can mean "your session is no longer good" rather than "you
    # are not allowed". 401 is the obvious one; 403 is NOT — measured against the
    # prod gateway, a rejected access cookie comes back 403 (a MISSING one comes
    # back 401). Treating 403 as final left a stale session raising a permission
    # error that a re-auth would have fixed. The cost of including it is one cheap
    # refresh round-trip on a genuine permission denial, and it is one-shot.
    _REAUTH_STATUSES = frozenset({401, 403})

    def _send_once(self, method: str, url: str, params, body, read_timeout,
                   deadline_at, _retry_on_auth: bool) -> tuple[int, Any]:
        """A single logical attempt: the HTTP round-trip PLUS the one-shot
        re-authentication for userpass. Retries (GET-only) live one layer up, in
        request()."""
        status, parsed = self._do_http(method, url, params, body, read_timeout,
                                       deadline_at)
        if (status in self._REAUTH_STATUSES and _retry_on_auth
                and self.profile.get("type") == "userpass"):
            auth.reauthenticate(self.name, self.profile, self._session)
            self._clear_jar()
            return self._send_once(method, url, params, body, read_timeout,
                                   deadline_at, False)
        return status, parsed

    # -- universal request --------------------------------------------------

    def request(self, method: str, path: str, *, query: dict | None = None,
                body: Any = None, _retry_on_auth: bool = True,
                read_timeout=reliability.DEFAULT, deadline=reliability.DEFAULT) -> Any:
        """Call any Web-API endpoint. `path` starts with '/api/...'. Returns the
        parsed JSON body on 2xx; raises ProcesioAPIError on a non-2xx, or
        DeadlineExceeded if the TOTAL wall-clock deadline elapses.

        A total deadline (class-aware: reads ~90s, writes ~180s) makes a stalled
        call SURFACE instead of hanging until SIGKILL. GET is retried on transient
        statuses / network errors; POST/PUT/PATCH/DELETE are NEVER retried (an
        execution would double-run; a timed-out write may already have applied).
        run-process passes `deadline=None` (exempt) + its own `read_timeout`.
        """
        import requests  # for its exception types; already a project dependency

        method_u = method.upper()
        if read_timeout is reliability.DEFAULT:
            read_timeout = reliability.READ_TIMEOUT
        deadline_s = reliability.resolve_deadline(method_u, deadline)
        cls = reliability.endpoint_class(method_u)
        if not path.startswith("/"):
            path = "/" + path
        url = f"{config.web_base(self.profile)}{path}"
        clean = {k: v for k, v in (query or {}).items() if v is not None}

        start = time.monotonic()
        deadline_at = None if deadline_s is None else start + deadline_s
        attempt = 0
        while True:
            try:
                status, parsed = self._send_once(
                    method_u, url, clean, body, read_timeout, deadline_at,
                    _retry_on_auth)
            except reliability.DeadlineHit:
                raise DeadlineExceeded(path, cls, deadline_s or 0.0,
                                       time.monotonic() - start)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as exc:
                if reliability.network_error_retryable(method_u, attempt) \
                        and self._budget_ok(deadline_at):
                    attempt += 1
                    self._backoff(attempt, None, deadline_at,
                                  f"{method_u} {path}: {exc.__class__.__name__}")
                    continue
                raise
            if 200 <= status < 300:
                return parsed
            if reliability.is_retryable(method_u, status, attempt) \
                    and self._budget_ok(deadline_at):
                attempt += 1
                retry_after = reliability.parse_retry_after(
                    (self.last_meta or {}).get("headers")) if status == 429 else None
                self._backoff(attempt, retry_after, deadline_at,
                              f"{method_u} {path}: HTTP {status}")
                continue
            details = parsed if isinstance(parsed, dict) else {"body": parsed}
            raise ProcesioAPIError(int(status or 0), f"HTTP {status}", details)

    @staticmethod
    def _budget_ok(deadline_at: float | None) -> bool:
        """Is there enough wall-clock left to justify another attempt? A retry that
        cannot fit inside the total deadline is pointless — fail now with the real
        status instead of after a doomed backoff."""
        if deadline_at is None:
            return True
        return (deadline_at - time.monotonic()) > 0.5

    def _backoff(self, attempt: int, retry_after, deadline_at, why: str) -> None:
        wait = retry_after if retry_after is not None else reliability.full_jitter(attempt)
        if deadline_at is not None:
            wait = min(wait, max(0.0, deadline_at - time.monotonic()))
        from tools._lib.io import log
        log(f"procesio: retry {attempt} in {wait:.2f}s ({why})")
        time.sleep(wait)

    # -- verb helpers -------------------------------------------------------

    def get(self, path, query=None, **kw):
        return self.request("GET", path, query=query, **kw)

    def post(self, path, body=None, query=None, **kw):
        return self.request("POST", path, query=query, body=body, **kw)

    def put(self, path, body=None, query=None, **kw):
        return self.request("PUT", path, query=query, body=body, **kw)

    def patch(self, path, body=None, query=None, **kw):
        return self.request("PATCH", path, query=query, body=body, **kw)

    def delete(self, path, query=None, **kw):
        return self.request("DELETE", path, query=query, **kw)

    def request_bytes(self, method: str, path: str, *, query: dict | None = None,
                      body: Any = None, headers: dict | None = None) -> tuple[int, bytes, dict]:
        """Like request() but returns (status, raw_bytes, headers) without JSON
        parsing — for binary/file responses such as the Transport `.procesio`
        export (application/octet-stream) or the flow-instance file download
        (identified by extra request HEADERS passed via `headers=`)."""
        if not path.startswith("/"):
            path = "/" + path
        url = f"{config.web_base(self.profile)}{path}"
        clean = {k: v for k, v in (query or {}).items() if v is not None}
        hdrs = self._headers()
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update({k: v for k, v in headers.items() if v is not None})
        self._clear_jar()
        resp = self._session.request(method.upper(), url, params=clean, json=body,
                                     headers=hdrs, timeout=120)
        return (getattr(resp, "status_code", 0),
                getattr(resp, "content", b""),
                dict(getattr(resp, "headers", {}) or {}))

    def request_multipart(self, path: str, *, files: dict, query: dict | None = None,
                          headers: dict | None = None, _retry_on_auth: bool = True) -> Any:
        """POST a multipart/form-data body (e.g. a custom-action `.nupkg` package
        upload). `files` is requests' `files=` dict
        `{field: (filename, bytes, content_type)}`. Content-Type is left UNSET so
        requests writes the multipart boundary itself. Returns parsed JSON on 2xx."""
        if not path.startswith("/"):
            path = "/" + path
        url = f"{config.web_base(self.profile)}{path}"
        clean = {k: v for k, v in (query or {}).items() if v is not None}
        hdrs = self._headers()                      # NO Content-Type -> requests sets multipart
        if headers:
            hdrs.update({k: v for k, v in headers.items() if v is not None})
        self._clear_jar()
        resp = self._session.request("POST", url, params=clean, files=files,
                                     headers=hdrs, timeout=300)
        status = getattr(resp, "status_code", 0)
        parsed = self._parse_body(resp)
        if 200 <= status < 300:
            return parsed
        if (status in self._REAUTH_STATUSES and _retry_on_auth
                and self.profile.get("type") == "userpass"):
            auth.reauthenticate(self.name, self.profile, self._session)
            self._clear_jar()
            return self.request_multipart(path, files=files, query=query,
                                          headers=headers, _retry_on_auth=False)
        details = parsed if isinstance(parsed, dict) else {"body": parsed}
        raise ProcesioAPIError(int(status or 0), f"HTTP {status}", details)


def parse_json_arg(raw: str | None, what: str) -> Any:
    """Parse a --query/--body/--payload JSON argument from the CLI.

    Accepts either JSON inline, or ``@path`` to read the JSON from a file.

    ⚠ WHY ``@path`` EXISTS, AND IT IS NOT A CONVENIENCE. Windows caps a command
    line at roughly 32 KB. A real PROCESIO flow definition is larger than that:
    the UC-7 detection flow's captured definition is ~37 KB, and the E-2 gateway
    flows are comparable. So passing one inline raises

        FileNotFoundError: [WinError 206] The filename or extension is too long

    before the tool is even started, which means **this tool could not write a
    real process definition at all** - and a definition write is exactly what a
    rollback restore and an engine deployment both are. Found by E-13 A2 while
    trying to restore a duplicated gateway process.

    The ``@path`` convention is the one `tools/_lib/_atlassian_cli.py` already
    uses, so this is the framework's existing spelling rather than a new one.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, str) and raw.startswith("@"):
        from pathlib import Path as _Path

        from tools.procesio.errors import UsageError

        p = _Path(raw[1:])
        if not p.is_file():
            raise UsageError(f"--{what} points at {p}, which is not a file")
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        from tools.procesio.errors import UsageError

        raise UsageError(f"--{what} must be valid JSON: {e}") from e
