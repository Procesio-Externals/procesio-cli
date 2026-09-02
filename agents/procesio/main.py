"""procesio agent entrypoint - action dispatch.

Drives the `procesio` tool (and, in later slices, web + google-* for forms and
deliverables) to create, verify, and audit PROCESIO resources. Invoked exactly
like an action-dispatch tool: action name first, JSON in / JSON out. It is the
executable side of the build-and-test playbook in this folder.
"""
from __future__ import annotations

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = AGENT_ROOT.parents[1]
# .venv layout is per-OS: Scripts/python.exe on Windows, bin/python everywhere else.
_VENV_PY = (FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe" if sys.platform == "win32"
            else FRAMEWORK_ROOT / ".venv" / "bin" / "python")
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import argparse  # noqa: E402

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from tools._lib.io import emit, fail  # noqa: E402
from agents._lib import errors  # noqa: E402
from agents._lib.actiondef import ActionDef  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise errors.UsageError(message)


def collect_actions() -> dict[str, ActionDef]:
    actions: dict[str, ActionDef] = {}
    from agents.procesio.handlers import (status, guidance, checklist as checklist_h,
                                          verify as verify_h, audit as audit_h)
    actions.update(status.ACTIONS)
    actions.update(guidance.ACTIONS)
    actions.update(checklist_h.ACTIONS)
    actions.update(verify_h.ACTIONS)
    actions.update(audit_h.ACTIONS)
    return actions


ACTIONS = collect_actions()


def _build_context():
    from agents.procesio.context import ProcesioContext
    return ProcesioContext.create()


def dispatch(action: str, argv: list[str], *, context_builder=None) -> dict:
    if action not in ACTIONS:
        raise errors.UsageError(
            f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}")
    defn = ACTIONS[action]
    parser = _Parser(prog=f"procesio {action}", description=defn.description)
    defn.add_args(parser)
    parsed = parser.parse_args(argv)
    if defn.context:
        builder = context_builder or _build_context
        ctx = builder()
        return defn.func(ctx, parsed)
    return defn.func(parsed)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("Actions:", file=sys.stderr)
        for name in sorted(ACTIONS):
            print(f"  {name:<12} {ACTIONS[name].description}", file=sys.stderr)
        sys.exit(0)
    action, rest = argv[0], argv[1:]
    try:
        result = dispatch(action, rest)
    except Exception as exc:  # noqa: BLE001
        code, message, details, exit_code = errors.classify(exc)
        fail(code, message, details, exit_code)
    emit(result)


if __name__ == "__main__":
    main()
