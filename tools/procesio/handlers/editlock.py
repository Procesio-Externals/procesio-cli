"""One writer at a time on a live process.

A surgical edit reads the whole process, changes one thing, and saves the whole process.
Two edits that run together both read the same version, and the second save discards the
first change. Both report success. A caller that sends several edits in one step (an
assistant does) keeps the last one and loses the rest without being told.

So a writer holds a lock from its read to its save. The lock is a file named after the
process id. It orders the writers that run on THIS machine, which is where the calls of one
caller run. It does not see a save made in the Process Designer, or a writer on another
machine: for those the platform still keeps the last write.

WHERE THE FILE IS decides whether the lock is one. Two writers exclude each other only when
both look in the same folder, and the temp folder is not that folder everywhere: a server
that isolates tool calls gives each call a temp folder of its own, and a lock taken there
is seen by nobody. So the folder is a setting, AAT_LOCK_DIR: one path that every tool call
on the machine is given and can write. Without the setting the temp folder is used, which
is right on a machine where every call has the same one.

WHAT IS COVERED: the writers of handlers/nodeparams.py. process-edit, the layout actions and
process-docs also save a whole process, and do not take this lock.

Nothing here may stop an edit that could have run. A folder that cannot be written means
the edit runs without the lock, as it did before the lock existed, and its result says so.
A lock left behind by a writer that was stopped is taken over once it is older than any
writer can be.
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import os
import tempfile
import time
from pathlib import Path

from tools.procesio.errors import ProcessBusy

LOCK_DIR_ENV = "AAT_LOCK_DIR"
WAIT_SECONDS = 120.0    # how long a writer waits for the one before it
STALE_SECONDS = 300.0   # a lock older than this was left by a writer that no longer runs
POLL_SECONDS = 0.1
FOLDER = "procesio-edit-locks"


def lock_root() -> Path:
    """The folder the locks of this machine are kept under: AAT_LOCK_DIR when it is set, else
    the temp folder. Read at every call, never kept: one process can serve calls that were
    given different environments."""
    configured = (os.environ.get(LOCK_DIR_ENV) or "").strip()
    return Path(configured) if configured else Path(tempfile.gettempdir())


def lock_path(process_id: str) -> Path:
    """The lock file of one process. The id is hashed: it comes from a caller, and a name
    built from it must not be able to leave the folder."""
    name = hashlib.sha256(str(process_id).strip().lower().encode("utf-8")).hexdigest()[:32]
    return lock_root() / FOLDER / f"{name}.lock"


def _age_seconds(path: Path) -> float | None:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None   # gone since we looked: the next attempt takes it


@contextlib.contextmanager
def process_lock(process_id: str, *, wait: float = WAIT_SECONDS, stale: float = STALE_SECONDS,
                 poll: float = POLL_SECONDS, sleep=time.sleep, clock=time.monotonic):
    """Hold the writer lock of `process_id` for the body. Yields True when the lock is held and
    False when it could not be set up, in which case the body runs unserialized.

    Raises ProcessBusy when another writer still holds it after `wait` seconds."""
    path = lock_path(process_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        yield False
        return
    deadline = clock() + wait
    handle = None
    while handle is None:
        try:
            handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = _age_seconds(path)
            if age is None or age > stale:
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            if clock() >= deadline:
                raise ProcessBusy(
                    f"another edit of process {process_id} is still running after {wait:g} s. "
                    f"Nothing was read or written by this call; repeat it.",
                    {"process_id": process_id, "waited_s": wait}) from None
            sleep(poll)
        except OSError:
            yield False
            return
    try:
        with contextlib.suppress(OSError):
            os.write(handle, str(os.getpid()).encode("ascii"))
        yield True
    finally:
        with contextlib.suppress(OSError):
            os.close(handle)
        with contextlib.suppress(OSError):
            path.unlink()


UNSERIALIZED = ("the writer lock could not be set up, so this edit ran without it: the lock "
                f"folder ({LOCK_DIR_ENV}, or the temp folder) cannot be written. Another edit of "
                "this process that runs at the same time can overwrite this one.")


def serialized(handler):
    """Wrap a writer `handler(client, args)` so that it holds the lock of `args.id` from its
    read to its save. A call without an id runs as it is and fails on its own terms.

    An edit that had to run without the lock says so in its result. Running it is right;
    running it silently is how a lock that orders nobody goes unnoticed."""
    @functools.wraps(handler)
    def run(client, args):
        process_id = getattr(args, "id", None)
        if not process_id:
            return handler(client, args)
        with process_lock(process_id) as held:
            result = handler(client, args)
        if not held and isinstance(result, dict):
            result["unserialized"] = UNSERIALIZED
        return result
    return run
