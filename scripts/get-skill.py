"""Load a registered skill so an agent (or Claude) can use it.

A skill is instruction/reference content, not an executable. "Using" one means
loading its SKILL.md and following it. This is the programmatic entry point.

Usage:
  python scripts/get-skill.py <name>             # metadata only
  python scripts/get-skill.py <name> --content    # + full SKILL.md body & asset lists

Output (JSON, one object on stdout):
  { name, description, version, path, skill_md }
  with --content also: { body, references:[...], scripts:[...], assets:[...] }
On failure: { "error": { code, message, details } }, non-zero exit.
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

sys.path.insert(0, str(_PROJECT_ROOT))

from registry import get_skill  # noqa: E402
from tools._lib.io import emit, fail  # noqa: E402


def _strip_frontmatter(text: str) -> str:
    """Return the SKILL.md body with the leading `---`-delimited frontmatter removed."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[i + 1:]).lstrip("\n")
    return text  # no frontmatter -> return as-is


def _rel_files(root: Path, subdir: str) -> list[str]:
    d = root / subdir
    if not d.is_dir():
        return []
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in d.rglob("*") if p.is_file())


def main() -> int:
    args = [a for a in sys.argv[1:]]
    want_content = "--content" in args
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals or "-h" in args or "--help" in args:
        print(__doc__)
        return 0

    name = positionals[0]
    try:
        m = get_skill(name)
    except KeyError as e:
        fail("not_found", str(e), {"name": name}, exit_code=2)

    path = m.path
    skill_md = path / "SKILL.md"
    out = {
        "name": m.name,
        "description": m.description,
        "version": m.version,
        "path": str(path),
        "skill_md": str(skill_md),
    }
    if want_content:
        text = skill_md.read_text(encoding="utf-8")
        out["body"] = _strip_frontmatter(text)
        out["references"] = _rel_files(path, "references")
        out["scripts"] = _rel_files(path, "scripts")
        out["assets"] = _rel_files(path, "assets")
    emit(out)


if __name__ == "__main__":
    raise SystemExit(main())
