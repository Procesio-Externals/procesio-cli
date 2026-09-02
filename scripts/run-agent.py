"""Generic agent runner. Forwards all trailing args to the agent's entrypoint.

Usage:
  python scripts/run-agent.py <agent-name> <action> [--arg=value ...]

Example:
  python scripts/run-agent.py outreach status
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

from registry import get_agent  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0

    agent_name = sys.argv[1]
    forwarded = sys.argv[2:]

    try:
        m = get_agent(agent_name)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if m.path is None:
        print(f"error: manifest for {agent_name} has no path", file=sys.stderr)
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
