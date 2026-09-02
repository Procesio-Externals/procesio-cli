"""Web-session lifecycle abstraction: hydrate / dehydrate / lease (spec P0.0-09).

The PROCESIO web-tool service hosts per-(workspace, user) browser profiles: hydrate a
profile from object storage -> run -> dehydrate it back, with a per-session lease so one
profile is driven by one browser at a time (the single-owner ``SingletonLock`` reality
of a persistent Chrome profile - memory ``web-profile-no-parallel``; the local
serialize-web-profile broker). See
``todo/on-hold/procesio-aat-module/09-web-tool-service.md``.

This module factors that lifecycle into a reusable abstraction with a **local
filesystem** implementation, so the platform swaps the storage + lease backends
(object storage + a distributed lease) without changing any caller. P0.0 delivers the
shape + the local impl + the object-store swap point - NOT a hosted browser fleet.

Metadata mirrors the CSK session pointer: {name, site, kind, created, rotated, health}.
"""
from __future__ import annotations

import json
import os
import sys
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools._lib import userdata  # noqa: E402


class LeaseTimeout(RuntimeError):
    """Raised when a per-session lease cannot be acquired within the timeout - the
    session is in use by another browser (serialized single-owner access)."""


class WebSessionStore(ABC):
    """Persistence + lease contract for web-login profiles. Backends are dumb: the
    caller decides when to hydrate/dehydrate; the store moves bytes and guards leases."""

    @abstractmethod
    def hydrate(self, ws: str | None, user: str | None, name: str) -> Path:
        """Materialize the session's profile locally and return its directory."""

    @abstractmethod
    def dehydrate(self, ws: str | None, user: str | None, name: str, profile_dir: Path) -> None:
        """Persist profile changes back to durable storage."""

    @abstractmethod
    def list_sessions(self, ws: str | None, user: str | None) -> list[dict]:
        ...

    @abstractmethod
    def pointer(self, ws: str | None, user: str | None, name: str) -> dict | None:
        ...

    @abstractmethod
    def _lock_path(self, ws: str | None, user: str | None, name: str) -> Path:
        ...

    @contextmanager
    def lease(self, ws: str | None, user: str | None, name: str, *,
              timeout: float = 30.0, poll: float = 0.1):
        """Acquire exclusive use of one session, hydrate it, yield the profile dir, then
        dehydrate + release. Serializes same-session access (a second acquirer waits up
        to ``timeout`` then raises ``LeaseTimeout``); different sessions run in parallel.
        The platform swaps this for a distributed lease with identical semantics."""
        lock = self._lock_path(ws, user, name)
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = _acquire_lock(lock, timeout=timeout, poll=poll)
        try:
            profile_dir = self.hydrate(ws, user, name)
            try:
                yield profile_dir
            finally:
                self.dehydrate(ws, user, name, profile_dir)
        finally:
            _release_lock(fd, lock)


class LocalWebSessionStore(WebSessionStore):
    """Filesystem implementation. Profiles live under ``userdata.sessions_dir()`` which
    is already per-(workspace, user) once ``AAT_WORKSPACE_ID`` / ``AAT_USER_ID`` are set
    (item P0.0-01), so tenant isolation is automatic. Hydrate/dehydrate are in-place
    (the durable copy IS the local dir); the object-store impl overrides them to move
    bytes to/from S3/MinIO."""

    def _root(self, ws: str | None, user: str | None) -> Path:
        # sessions_dir() derives from userdata.base(), which already folds in (ws,user).
        return userdata.sessions_dir()

    def _session_dir(self, ws, user, name: str) -> Path:
        return self._root(ws, user) / userdata._safe_component(name)

    def _index_path(self, ws, user) -> Path:
        return self._root(ws, user) / "sessions_index.json"

    def _lock_path(self, ws, user, name: str) -> Path:
        return self._session_dir(ws, user, name).with_suffix(".lock")

    def hydrate(self, ws, user, name: str) -> Path:
        d = self._session_dir(ws, user, name)
        (d / "profile").mkdir(parents=True, exist_ok=True)
        return d / "profile"

    def dehydrate(self, ws, user, name: str, profile_dir: Path) -> None:
        # Local: the profile dir IS durable; just touch the pointer's rotated time.
        self._touch_pointer(ws, user, name)

    def _load_index(self, ws, user) -> dict:
        p = self._index_path(ws, user)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return {}
        return {}

    def _save_index(self, ws, user, idx: dict) -> None:
        p = self._index_path(ws, user)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    def put_pointer(self, ws, user, name: str, *, site: str = "",
                    kind: str = "profile", health: str = "unknown") -> dict:
        idx = self._load_index(ws, user)
        now = _now_iso()
        meta = idx.get(name) or {"name": name, "created": now}
        meta.update({"name": name, "site": site or meta.get("site", ""),
                     "kind": kind, "health": health, "rotated": now})
        meta.setdefault("created", now)
        idx[name] = meta
        self._save_index(ws, user, idx)
        return meta

    def _touch_pointer(self, ws, user, name: str) -> None:
        idx = self._load_index(ws, user)
        if name in idx:
            idx[name]["rotated"] = _now_iso()
            self._save_index(ws, user, idx)

    def pointer(self, ws, user, name: str) -> dict | None:
        return self._load_index(ws, user).get(name)

    def list_sessions(self, ws, user) -> list[dict]:
        return list(self._load_index(ws, user).values())


class ObjectStoreWebSessionStore(WebSessionStore):
    """Swap point for the platform: hydrate/dehydrate move the profile between an
    ephemeral local dir and object storage (S3/MinIO) per (workspace, user); the lease
    is a distributed lock. Not implemented in P0.0 - the hosted browser fleet + object
    storage + streamed login-capture are platform-phase, highest-risk (SPIKE 3)."""

    def __init__(self, *_a, **_k) -> None:
        raise NotImplementedError(
            "ObjectStoreWebSessionStore is the platform-phase swap point (spec P0.0-09 / "
            "procesio-aat-module/09); use LocalWebSessionStore locally.")

    def hydrate(self, ws, user, name): ...
    def dehydrate(self, ws, user, name, profile_dir): ...
    def list_sessions(self, ws, user): ...
    def pointer(self, ws, user, name): ...
    def _lock_path(self, ws, user, name): ...


# -- lease primitives (local lockfile; the platform swaps a distributed lease) --------

def _acquire_lock(lock: Path, *, timeout: float, poll: float) -> int:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LeaseTimeout(f"session lock held: {lock.name}")
            time.sleep(poll)


def _release_lock(fd: int, lock: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
