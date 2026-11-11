"""One browser per persistent profile, across processes.

Two Chromium instances on the same user-data-dir corrupt it: the second one
cannot open the quota database, Chromium resets it, and the reset deletes the
sites' stored data. For WhatsApp Web that is the login itself, so the linked
device is gone minutes after a scan (seen 2026-11-08: the service, a ``--direct``
call and a ``relink`` window opened the profile at the same time).

``ProfileLock`` takes an exclusive OS lock on ``<profile>.aat-lock`` (a sibling
file, so Chromium never touches it) before a persistent context starts and
holds it until the context closes. A second opener waits up to ``wait_s`` and
then fails with a ``BrowserError`` that names the holder, instead of opening
alongside. The OS drops the lock when the holding process dies, so a crash
cannot leave the profile stuck.
"""
from __future__ import annotations

import os
import time

from tools.web.errors import BrowserError

DEFAULT_WAIT_S = 180.0
_POLL_S = 0.5


def _wait_from_env() -> float:
    raw = os.environ.get("AAT_PROFILE_LOCK_WAIT_S")
    try:
        return float(raw) if raw else DEFAULT_WAIT_S
    except ValueError:
        return DEFAULT_WAIT_S


def lock_path(user_data_dir: str) -> str:
    return os.path.normpath(user_data_dir).rstrip("\\/") + ".aat-lock"


class ProfileLock:
    def __init__(self, user_data_dir: str, *, wait_s: float | None = None):
        self.path = lock_path(user_data_dir)
        self.wait_s = _wait_from_env() if wait_s is None else wait_s
        self._fh = None

    def _try_lock(self) -> bool:
        if os.name == "nt":
            import msvcrt
            try:
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        import fcntl
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _holder(self) -> str:
        try:
            with open(self.path, encoding="utf-8") as f:
                return f.read(200).strip() or "unknown"
        except OSError:
            return "unknown"

    def acquire(self) -> "ProfileLock":
        self._fh = open(self.path, "a+", encoding="utf-8")
        deadline = time.monotonic() + max(0.0, self.wait_s)
        while not self._try_lock():
            if time.monotonic() >= deadline:
                holder = self._holder()
                self._fh.close()
                self._fh = None
                raise BrowserError(
                    f"browser profile is in use by another process ({holder}); "
                    f"waited {self.wait_s:.0f}s. Only one browser may open a profile "
                    f"at a time, or the profile's stored data gets wiped. Lock: {self.path}")
            time.sleep(_POLL_S)
        # Record the holder after the lock is ours (Windows locks byte 0 only).
        try:
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(f"pid {os.getpid()} since {time.strftime('%Y-%m-%d %H:%M:%S')}")
            self._fh.flush()
        except OSError:
            pass
        return self

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
