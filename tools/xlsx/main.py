"""xlsx tool entrypoint - read local Excel (.xlsx/.xlsm) files. Action-dispatched.

No credentials (local files only). Built from the original ad-hoc dump_xlsx.py,
per the "scripts become tools" directive.

Actions:
  list-sheets --path <f>
  read-sheet  --path <f> [--sheet NAME] [--max-rows N] [--raw]
  dump        --path <f> [--save OUT.txt] [--max-rows N]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TOOL_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = TOOL_ROOT.parents[1]
_VENV_PY = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from tools._lib.io import emit, fail  # noqa: E402
from tools.xlsx import reader  # noqa: E402


class UsageError(Exception):
    """Bad/invalid arguments -> invalid_argument, exit 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise UsageError(message)


@dataclass
class ActionDef:
    func: Callable
    add_args: Callable[[argparse.ArgumentParser], None]
    description: str = ""


def _list_sheets(args) -> dict:
    return {"path": args.path, "sheets": reader.list_sheets(args.path)}


def _read_sheet(args) -> dict:
    return reader.read_sheet(args.path, args.sheet, max_rows=args.max_results)


def _dump(args) -> dict:
    text = reader.dump_text(args.path, max_rows=args.max_results)
    if args.save:
        out = Path(args.save).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        return {"savedTo": str(out), "characters": len(text)}
    return {"text": text, "characters": len(text)}


def _path_arg(p):
    p.add_argument("--path", required=True, help="Local .xlsx/.xlsm file")


def _read_args(p):
    _path_arg(p)
    p.add_argument("--sheet", help="Sheet name (default: first/active)")
    p.add_argument("--max-results", type=int, help="Cap rows returned")


def _dump_args(p):
    _path_arg(p)
    p.add_argument("--save", help="Write text dump here instead of inline")
    p.add_argument("--max-results", type=int, help="Cap rows per sheet")


ACTIONS = {
    "list-sheets": ActionDef(_list_sheets, _path_arg,
                             "List a workbook's sheets with row/column counts."),
    "read-sheet": ActionDef(_read_sheet, _read_args,
                            "Read one sheet's rows as a JSON 2D array."),
    "dump": ActionDef(_dump, _dump_args,
                      "Dump the whole workbook to readable text (--save or inline)."),
}


def dispatch(action: str, argv: list[str]) -> dict:
    if action not in ACTIONS:
        raise UsageError(f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}")
    defn = ACTIONS[action]
    parser = _Parser(prog=f"xlsx {action}", description=defn.description)
    defn.add_args(parser)
    return defn.func(parser.parse_args(argv))


def _classify(exc: Exception):
    if isinstance(exc, UsageError):
        return "invalid_argument", str(exc), 2
    if isinstance(exc, FileNotFoundError):
        return "not_found", str(exc), 1
    if isinstance(exc, ValueError):
        return "invalid_argument", str(exc), 2
    return "error", str(exc) or exc.__class__.__name__, 1


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("Actions:", file=sys.stderr)
        for name in sorted(ACTIONS):
            print(f"  {name:<14} {ACTIONS[name].description}", file=sys.stderr)
        sys.exit(0)
    action, rest = argv[0], argv[1:]
    try:
        result = dispatch(action, rest)
    except Exception as exc:  # noqa: BLE001
        code, message, exit_code = _classify(exc)
        fail(code, message, {}, exit_code)
    emit(result)


if __name__ == "__main__":
    main()
