"""connector-builder agent entrypoint — action dispatch.

Orchestrates the `connector-builder` tool (the AI Connector Builder REST client)
and the `procesio` tool to run the full loop: build a connector from API docs →
download the .nupkg → upload it to PROCESIO → test it live → feed failures back
to improve the connector (and, for systemic issues, the builder's own knowledge).

It is the executable side of CONNECTOR-BUILDER-PLAYBOOK.md. Invoked like any
action-dispatch tool: action name first, JSON in / JSON out.

The agent dir name has a hyphen, so this agent's own modules are imported by BARE
name with the agent root on sys.path (mirrors the hyphenated tools); the shared
agent libs are imported as the valid package `agents._lib`.
"""
from __future__ import annotations

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = AGENT_ROOT.parents[1]
_VENV_PY = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import argparse  # noqa: E402

for _p in (str(AGENT_ROOT), str(FRAMEWORK_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools._lib.io import emit, fail  # noqa: E402
from agents._lib import errors  # noqa: E402
from agents._lib.actiondef import ActionDef  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise errors.UsageError(message)


def collect_actions() -> dict[str, ActionDef]:
    from handlers import status, guidance, nextstep, checklist
    actions: dict[str, ActionDef] = {}
    for module in (status, guidance, nextstep, checklist):
        for name, defn in module.ACTIONS.items():
            if name in actions:
                raise RuntimeError(f"duplicate connector-builder agent action: {name}")
            actions[name] = defn
    return actions


ACTIONS = collect_actions()


def _build_context():
    from context import ConnectorBuilderContext
    return ConnectorBuilderContext.create()


def dispatch(action: str, argv: list[str], *, context_builder=None) -> dict:
    if action not in ACTIONS:
        raise errors.UsageError(
            f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}")
    defn = ACTIONS[action]
    parser = _Parser(prog=f"connector-builder {action}", description=defn.description)
    defn.add_args(parser)
    parsed = parser.parse_args(argv)
    if defn.context:
        builder = context_builder or _build_context
        return defn.func(builder(), parsed)
    return defn.func(parsed)


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
        code, message, details, exit_code = errors.classify(exc)
        fail(code, message, details, exit_code)
    emit(result)


if __name__ == "__main__":
    main()
