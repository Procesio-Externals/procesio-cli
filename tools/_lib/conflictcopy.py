"""The name machine-sync gives the losing side of a file conflict, and how to spot one.

A file changed on both machines keeps the newer write and saves the other beside it as
``<stem>.conflict-<machine>-<YYYYMMDDTHHMMSS><suffix>``. The copy keeps its extension on
purpose, so it still opens in an editor, which also means a reader that lists a synced
folder by extension picks it up as live data. Any such reader skips these names through
``is_conflict_copy``.

Both halves live here so the name and the check cannot drift apart, and in
``tools/_lib`` so a component can check a name without importing a tool. The check
matches the whole name, stamp included, so a file someone merely called
``x.conflict-notes.yaml`` is still their file.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

MARK = ".conflict-"
_STAMP = "%Y%m%dT%H%M%S"
_NAME_RE = re.compile(r"^(?P<stem>.+)\.conflict-.+-\d{8}T\d{6}(?P<suffix>\.[^.]+)?$")


def name_for(rel: str, machine: str, now: datetime | None = None) -> str:
    """The path of the copy of ``rel`` that keeps ``machine``'s version."""
    stamp = (now or datetime.now()).strftime(_STAMP)
    p = Path(rel)
    return str(p.with_name(f"{p.stem}{MARK}{machine}-{stamp}{p.suffix}")).replace("\\", "/")


def is_conflict_copy(name: str) -> bool:
    """True when a bare file name is one ``name_for`` produces."""
    return _NAME_RE.match(name) is not None


def original_name(name: str) -> str | None:
    """The file a copy lost to, beside it in the same folder. None when not a copy."""
    m = _NAME_RE.match(name)
    return f"{m['stem']}{m['suffix'] or ''}" if m else None
