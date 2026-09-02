"""JSON I/O contract for tools.

Success:  emit({...})            -> one JSON object to stdout, exit 0
Failure:  fail("code", "msg")    -> error envelope to stdout, non-zero exit
Logs:     log(...)                -> stderr only (never pollutes stdout)
"""
from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

# Windows terminals default to cp1252. Force UTF-8 so tools can emit
# non-ASCII (Ryver messages, calendar titles, names) without mojibake.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def emit(data: dict[str, Any]) -> NoReturn:
    """Print one JSON object to stdout and exit 0."""
    json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(0)


def fail(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    exit_code: int = 1,
) -> NoReturn:
    """Print error envelope to stdout and exit non-zero."""
    json.dump(
        {"error": {"code": code, "message": message, "details": details or {}}},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(exit_code)


def log(*args: Any) -> None:
    """Write to stderr. Use for progress, debug, anything non-JSON."""
    print(*args, file=sys.stderr, flush=True)


def read_stdin_json() -> dict[str, Any]:
    """For tools that accept JSON on stdin instead of CLI args."""
    return json.load(sys.stdin)
