"""Print all discoverable skills.

Usage:
  python scripts/list-skills.py           # human-readable table
  python scripts/list-skills.py --json    # full skills registry as JSON
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

from registry import list_skills  # noqa: E402


def _short(text: str, cap: int = 80) -> str:
    text = " ".join((text or "").split())
    return (text[: cap - 1] + "…") if len(text) > cap else text


def main() -> int:
    skills = list_skills()
    if "--json" in sys.argv:
        json.dump(skills, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if not skills:
        print("No skills found.")
        print("Add a skill under skills/<name>/ with a SKILL.md (frontmatter = manifest).")
        return 0

    name_w = max(len(s.get("name", "?")) for s in skills)
    print(f"{'SKILL':<{name_w}}  VERSION  STATUS   DESCRIPTION")
    print("-" * (name_w + 60))
    for s in skills:
        name = s.get("name", "?")
        if "error" in s:
            print(f"{name:<{name_w}}  {'-':<7}  ERROR    {s['error']}")
            continue
        status = "ready" if s.get("ready") else "?"
        print(f"{name:<{name_w}}  v{s['version']:<6}  {status:<7}  {_short(s['description'])}")
        if s.get("warning"):
            print(f"{'':<{name_w}}  ⚠ {s['warning']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
