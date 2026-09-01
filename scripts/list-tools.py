"""Print all discoverable tools and their readiness status.

Usage:
  python scripts/list-tools.py           # human-readable table
  python scripts/list-tools.py --json    # full registry as JSON
"""
from __future__ import annotations

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
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import json  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(_PROJECT_ROOT))

from registry import list_tools  # noqa: E402


def main() -> int:
    tools = list_tools()
    if "--json" in sys.argv:
        json.dump(tools, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if not tools:
        print("No tools found.")
        print("Add a tool under tools/<name>/ with a tool.yaml manifest.")
        return 0

    name_w = max(len(t.get("name", "?")) for t in tools)
    print(f"{'TOOL':<{name_w}}  VERSION  STATUS                DESCRIPTION")
    print("-" * (name_w + 60))
    for t in tools:
        name = t.get("name", "?")
        if "error" in t:
            print(f"{name:<{name_w}}  {'-':<7}  ERROR                 {t['error']}")
            continue
        # "authorized, but not for this tool" needs its own line: the fix is
        # re-running auth-login, not storing another secret.
        if t.get("readiness") == "needs-scopes":
            short = [s.rstrip("/").rsplit("/", 1)[-1] for s in t.get("missing_scopes", [])]
            status = "needs scope: " + ",".join(short)
        elif t["ready"]:
            status = "ready"
        else:
            status = "missing: " + ",".join(t["missing_secrets"])
        print(f"{name:<{name_w}}  v{t['version']:<6}  {status:<20}  {t['description']}")
        actions = t.get("actions", [])
        if actions:
            names = ", ".join(a["name"] for a in actions)
            print(f"{'':<{name_w}}  actions ({len(actions)}): {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
