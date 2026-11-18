"""Diagnose why Playwright's bundled Chromium cannot START on this machine.

Some Windows machines run a security policy that blocks executing binaries from
under ``%LOCALAPPDATA%`` - which is exactly where Playwright installs its browsers
by default (``%LOCALAPPDATA%\\ms-playwright``). The launch then fails with an
opaque ``spawn UNKNOWN`` or Windows' ``The application has failed to start because
its side-by-side configuration is incorrect`` (Win32 error 14001).

The trap: the headless SHELL (a different, smaller binary) may still start, so
every headless test passes and only a HEADED launch - a login window, a
``--headed`` run, a persistent profile - fails, at the user's first real use.

Remedy that works: install the browsers under a NON-AppData path by setting the
user environment variable ``PLAYWRIGHT_BROWSERS_PATH`` (e.g. ``C:\\ms-playwright``)
and re-installing there. Playwright reads that variable at install AND launch time,
so it must be set before both - open a new shell after setting it.

Used two ways:
  * ``launch_hint(message)`` - the web driver appends the remedy to a launch
    browser_error whose text looks like this failure.
  * ``python -m tools._lib.browserlaunch --headed`` - the machine-requirement
    check (``requires:`` in tools/web/tool.yaml, run by
    scripts/check-requirements.py): actually launches headed Chromium for a
    moment and exits non-zero, remedy on the last line, when it cannot start.
"""
from __future__ import annotations

import os
import sys

ENV_VAR = "PLAYWRIGHT_BROWSERS_PATH"
SUGGESTED_PATH = r"C:\ms-playwright"

# Lower-cased substrings that identify the blocked-execution launch failure.
_SXS_MARKERS = (
    "spawn unknown",
    "side-by-side configuration",
    "side by side configuration",
    "sxstrace",
    "error 14001",
)

REMEDY = (
    "Playwright's Chromium cannot start from its install folder (Windows "
    "'side-by-side configuration is incorrect' / spawn UNKNOWN: a security policy "
    "blocks executables under %LOCALAPPDATA%\\ms-playwright). Install the browsers "
    f"under a non-AppData path: set the user env var {ENV_VAR} (e.g. "
    f"setx {ENV_VAR} {SUGGESTED_PATH}), open a NEW shell, then run: "
    "uv run playwright install chromium"
)


def looks_like_blocked_launch(message: str | None) -> bool:
    low = (message or "").lower()
    return any(m in low for m in _SXS_MARKERS)


def launch_hint(message: str | None) -> str | None:
    """The remedy when ``message`` looks like the blocked-launch failure, else None.

    When the env var is already set and the launch STILL fails this way, say so:
    the browsers were probably installed before it was set (or the process was
    started from a shell that predates it)."""
    if not looks_like_blocked_launch(message):
        return None
    current = os.environ.get(ENV_VAR)
    appdata = os.environ.get("LOCALAPPDATA") or ""
    if current and appdata and os.path.normcase(current).startswith(
            os.path.normcase(appdata)):
        return (f"{REMEDY}. Note: {ENV_VAR} is set to {current!r}, which is still "
                "under %LOCALAPPDATA% - point it at a folder outside AppData.")
    if current:
        return (f"{REMEDY}. Note: {ENV_VAR} is already set to {current!r} in this "
                "process - re-run the install so the browsers actually live there.")
    return REMEDY


def probe_headed(timeout_ms: int = 30000) -> tuple[bool, str]:
    """Launch headed Chromium briefly (window parked off-screen). (ok, detail)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright is not installed (uv sync)"
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            browser = p.chromium.launch(
                headless=False, timeout=timeout_ms,
                args=["--window-position=-32000,-32000", "--window-size=1,1"])
            browser.close()
            return True, f"headed chromium started ({exe})"
    except Exception as exc:  # noqa: BLE001 - the whole point is to report it
        text = str(exc).strip()
        first = text.splitlines()[0] if text else exc.__class__.__name__
        hint = launch_hint(text)
        return False, f"{first[:200]} || {hint}" if hint else first[:300]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--headed" not in args:
        print("usage: python -m tools._lib.browserlaunch --headed", file=sys.stderr)
        return 2
    if sys.platform != "win32" and "--force" not in args:
        # The failure is Windows-policy specific; a headless CI box has no display
        # to open a headed window on, so probing there only yields false alarms.
        print("skipped: headed-launch probe runs on Windows only (--force to run)")
        return 0
    ok, detail = probe_headed()
    # check-requirements.py shows the LAST output line, so the remedy goes last.
    if ok:
        print(detail)
        return 0
    head, _, hint = detail.partition(" || ")
    print(head, file=sys.stderr)
    print(hint or ("If the error mentions spawn UNKNOWN or side-by-side: "
                   + REMEDY), file=sys.stderr)
    # check-requirements.py keeps only the last line, cut at 160 chars.
    if hint:
        print(f"headed chromium blocked (spawn UNKNOWN/side-by-side): set {ENV_VAR} "
              "to a non-AppData path and reinstall", file=sys.stderr)
    else:
        print(f"headed chromium failed to launch: {head[:110]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
