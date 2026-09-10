"""Load a registered skill or one of its bundled resources.

A skill is instruction/reference content, not an executable. "Using" one means
loading its SKILL.md and following it, then retrieving only the referenced
resource needed for the current task.

Usage:
  python scripts/get-skill.py <name>                         # metadata only
  python scripts/get-skill.py <name> --content               # body + resource index
  python scripts/get-skill.py <name> --index                 # resource index only
  python scripts/get-skill.py <name> --resource references/x.md

Output is one JSON object on stdout. Failures use the repository's stable error
envelope and a non-zero exit code.
"""
from __future__ import annotations

import argparse
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
from tools._lib.skill_resources import (  # noqa: E402
    SkillResourceError,
    SkillResourceNotFound,
    SkillResourceNotText,
    read_text_resource,
    resource_index,
)


def _strip_frontmatter(text: str) -> str:
    """Return the SKILL.md body with the leading `---`-delimited frontmatter removed."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[i + 1:]).lstrip("\n")
    return text  # no frontmatter -> return as-is


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        fail("invalid_args", message, {}, exit_code=2)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("name", help="registered skill name")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--content", action="store_true",
                       help="include SKILL.md body and resource index")
    group.add_argument("--index", action="store_true",
                       help="include resource index without the body")
    group.add_argument("--resource", metavar="PATH",
                       help="read one UTF-8 file below references/, scripts/, or assets/")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 0
    args = _parser().parse_args(argv)
    try:
        manifest = get_skill(args.name)
    except KeyError as exc:
        fail("not_found", str(exc), {"name": args.name}, exit_code=2)
    except ValueError as exc:
        fail("invalid_skill", str(exc), {"name": args.name}, exit_code=2)

    path = manifest.path
    skill_md = path / "SKILL.md"
    out = {
        "name": manifest.name,
        "description": manifest.description,
        "version": manifest.version,
        "tier": manifest.tier,
        "owner": manifest.owner or None,
        "last_verified": (manifest.last_verified.isoformat()
                          if manifest.last_verified else None),
        "baseline_version": manifest.baseline_version or None,
        "eval_suite": manifest.eval_suite or None,
        "source_policy": manifest.source_policy,
        "ready": True,
        "path": str(path),
        "skill_md": str(skill_md),
    }

    if args.resource is not None:
        try:
            out["resource"] = read_text_resource(path, args.resource)
        except SkillResourceNotFound as exc:
            fail(exc.code, str(exc), {"name": args.name, "path": args.resource}, exit_code=2)
        except SkillResourceNotText as exc:
            fail(exc.code, str(exc), {"name": args.name, "path": args.resource}, exit_code=2)
        except SkillResourceError as exc:
            fail(exc.code, str(exc), {"name": args.name, "path": args.resource}, exit_code=2)
    elif args.content or args.index:
        index = resource_index(path)
        # Preserve the legacy top-level lists while adding richer metadata.
        out["references"] = index["references"]
        out["scripts"] = index["scripts"]
        out["assets"] = index["assets"]
        out["resources"] = index["resources"]
        if args.content:
            out["body"] = _strip_frontmatter(skill_md.read_text(encoding="utf-8"))

    emit(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
