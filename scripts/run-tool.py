"""Generic tool runner. Forwards all trailing args to the tool's entrypoint.

Usage:
  python scripts/run-tool.py <tool-name> [--arg=value ...]

Example:
  python scripts/run-tool.py hello-world --name World

Fast path (default ON): the call is routed to the persistent toolrunner daemon
(tools/_lib/toolrunner) which keeps a warm worker pool, so Python startup and the
registry walk are paid once instead of on every call. AAT_RUNNER=0 disables it
and AAT_RUNNER_DIRECT=1 is the per-call escape hatch — either uses the classic
fresh-subprocess path below. The browser-owning tools always take the classic
path. The routing is transparent: a tool cannot tell which path ran it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Auto-switch to the project's .venv Python if we were launched with a different one.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# .venv layout is per-OS: Scripts/python.exe on Windows, bin/python everywhere
# else. Hardcoding the Windows path made this a silent no-op on macOS/Linux,
# where the script then ran on whatever interpreter happened to invoke it.
_VENV_PY = (_PROJECT_ROOT / ".venv" / "Scripts" / "python.exe" if sys.platform == "win32"
            else _PROJECT_ROOT / ".venv" / "bin" / "python")
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

sys.path.insert(0, str(_PROJECT_ROOT))

# Non-ASCII tool output (Ryver text, names, calendar titles) must survive the
# Windows cp1252 default when we relay a runner's captured stdout.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _emit_error(code: str, message: str, exit_code: int) -> int:
    """Print a tool-style error envelope to stdout (keeps JSON-out for callers
    that parse it) and return the exit code."""
    import json
    json.dump({"error": {"code": code, "message": message, "details": {}}},
              sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return exit_code


def _try_runner(tool_name: str, forwarded: list[str]) -> int | None:
    """Route through the persistent daemon when enabled. Returns an exit code
    when the runner handled the call, or None to fall back to the classic path
    (the call was NEVER submitted, so a fresh subprocess is safe)."""
    from tools._lib.toolrunner import client
    if not client.enabled(tool_name):
        return None
    outcome = client.run(tool_name, forwarded)
    disp = outcome.get("disposition")
    if disp == "ran":
        sys.stdout.write(outcome.get("stdout", ""))
        sys.stdout.flush()
        sys.stderr.write(outcome.get("stderr", ""))
        sys.stderr.flush()
        return int(outcome.get("exit_code", 0))
    if disp == "error":
        if outcome.get("code") == "tool_not_found":
            print(f"error: {outcome.get('message')}", file=sys.stderr)
            return 2
        return _emit_error(outcome.get("code", "runner_error"),
                           outcome.get("message", "runner error"),
                           int(outcome.get("exit_code", 1)))
    return None  # fallback


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0

    tool_name = sys.argv[1]
    forwarded = sys.argv[2:]

    try:
        handled = _try_runner(tool_name, forwarded)
        if handled is not None:
            return handled
    except ModuleNotFoundError:
        # The warm-process pool is optional and is not shipped in every
        # distribution of this framework. Absent is the documented state, not a
        # fault: warn on it and every single call prints a line of noise.
        pass
    except Exception as exc:  # noqa: BLE001 - the runner must never be an outage
        print(f"warning: toolrunner unavailable ({exc}); running direct",
              file=sys.stderr)

    from registry import get_tool  # noqa: E402

    try:
        m = get_tool(tool_name)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if m.path is None:
        print(f"error: manifest for {tool_name} has no path", file=sys.stderr)
        return 2

    entry = m.path / m.entrypoint
    if not entry.exists():
        print(f"error: entrypoint not found: {entry}", file=sys.stderr)
        return 2

    cmd = [sys.executable, str(entry), *forwarded]
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
