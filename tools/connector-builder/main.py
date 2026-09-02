"""connector-builder tool entrypoint — action dispatch.

Drives the AI Connector Builder (connector-builder.procesio.app): the platform
that turns API documentation into compiled PROCESIO Custom Action `.nupkg`
connectors via an 8-stage LLM pipeline (gather → clarify → plan → generate →
validate → compile → fix → deliver).

Two auth modes, both resolving to an `Authorization: Bearer <token>` header
(see client.py): an `acb_...` API key, or username/password → POST /auth/login.

The dir name has a hyphen, so this tool's own modules are imported by BARE name
with the tool root on sys.path (mirrors quickmail-web / fgo-web); the shared libs
are imported as the valid package `tools._lib`.
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = TOOL_ROOT.parents[1]
_VENV_PY = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import argparse  # noqa: E402

for _p in (str(TOOL_ROOT), str(FRAMEWORK_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools._lib.io import emit, fail  # noqa: E402

import errors  # noqa: E402
from actiondef import ActionDef  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise errors.UsageError(message)


def collect_actions() -> dict[str, ActionDef]:
    from handlers import auth, builds, files, telemetry, admin, raw
    actions: dict[str, ActionDef] = {}
    for module in (auth, builds, files, telemetry, admin, raw):
        for name, defn in module.ACTIONS.items():
            if name in actions:
                raise RuntimeError(f"duplicate connector-builder action: {name}")
            actions[name] = defn
    return actions


ACTIONS = collect_actions()


def _default_client_factory():
    from client import ConnectorBuilderClient
    return ConnectorBuilderClient()


def dispatch(action: str, argv: list[str], *, client_factory=None) -> dict:
    if action not in ACTIONS:
        raise errors.UsageError(
            f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}")
    defn = ACTIONS[action]
    parser = _Parser(prog=f"connector-builder {action}", description=defn.description)
    defn.add_args(parser)
    parsed = parser.parse_args(argv)
    if defn.needs_client:
        factory = client_factory or _default_client_factory
        return defn.func(factory(), parsed)
    return defn.func(parsed)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("Actions:", file=sys.stderr)
        for name in sorted(ACTIONS):
            print(f"  {name:<28} {ACTIONS[name].description}", file=sys.stderr)
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
