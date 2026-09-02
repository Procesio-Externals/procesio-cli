"""web tool entrypoint - action dispatch (Playwright-driven, no HTTP API).

Drives web apps that have no API, reusing saved login sessions (Playwright
storageState). Sessions are sensitive auth material stored in the central
git-ignored user-data folder (context-state-knowledge/sessions/) - see
sessions.py and tools/web/sessions/README.md.

Actions:
  save-session      capture a login session interactively (headed browser)
  list-sessions     list saved sessions (metadata only)
  delete-session    remove a saved session
  run               run a declarative step list against a saved session
  get-text          load a session, open a URL, return visible text
  screenshot        load a session, open a URL, save a screenshot

Playwright is imported lazily (inside the driver) so this tool and its tests
load even before the browser binaries are installed.
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

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from tools._lib.io import emit, fail  # noqa: E402
from tools.web import errors  # noqa: E402
from tools.web.actiondef import ActionDef  # noqa: E402
from tools.web.driver import PlaywrightDriver  # noqa: E402


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise errors.UsageError(message)


def collect_actions() -> dict[str, ActionDef]:
    actions: dict[str, ActionDef] = {}
    from tools.web.handlers import browse, sessmgmt
    actions.update(sessmgmt.ACTIONS)
    actions.update(browse.ACTIONS)
    return actions


ACTIONS = collect_actions()


def _default_driver_factory(*, storage_state=None, headless=True, channel=None,
                            user_data_dir=None, extra_args=None):
    """Production factory injected into driver-based handlers. Returns an
    UNSTARTED PlaywrightDriver; the API layer calls .start().

    Accepts ``user_data_dir`` so the API layer can drive a PERSISTENT profile
    session (auto-detected from a ``<name>.profile`` dir) through the CLI, not
    just storageState sessions. Also accepts ``extra_args`` because the
    persistent-profile path in ``api.open_session`` forwards it to the factory
    (matches ``api._default_factory``); without it, ``web run/get-text/screenshot``
    on any persistent profile raised an unexpected-keyword TypeError."""
    return PlaywrightDriver(storage_state=storage_state, headless=headless,
                            channel=channel, user_data_dir=user_data_dir,
                            extra_args=extra_args)


def dispatch(action: str, argv: list[str], *, driver_factory=None,
             allow_service: bool = True) -> dict:
    if action not in ACTIONS:
        raise errors.UsageError(
            f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}"
        )
    defn = ACTIONS[action]
    parser = _Parser(prog=f"web {action}", description=defn.description)
    defn.add_args(parser)
    parsed = parser.parse_args(argv)

    # BROKER-OWNED SESSIONS: when the target session belongs to a serializing
    # broker (whatsapp/ryver/fgo/mirro — see tools/_lib/webserialize/registry),
    # the generic browser actions are translated to a step list and executed
    # INSIDE that broker, serialized with the owning tool's own commands. A
    # direct run against an owned profile could race the broker's warm browser
    # and invalidate the session. Unowned sessions behave exactly as before.
    if defn.needs_driver:
        from tools.web import brokered
        cfg = brokered.eligible(parsed, driver_factory=driver_factory,
                                allow_service=allow_service)
        if cfg is not None:
            return brokered.route(
                cfg, action, parsed,
                dispatch_direct=lambda: dispatch(action, argv,
                                                 allow_service=False),
            )

    if defn.needs_driver:
        factory = driver_factory or _default_driver_factory
        return defn.func(factory, parsed)
    return defn.func(parsed)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("Actions:", file=sys.stderr)
        for name in sorted(ACTIONS):
            print(f"  {name:<16} {ACTIONS[name].description}", file=sys.stderr)
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
