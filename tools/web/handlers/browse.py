"""Browser-action handlers: run, get-text, screenshot.

Each receives a ``driver_factory`` (injected by the dispatcher) as its first
argument, then the parsed args. The factory builds a BrowserDriver from kwargs
(``storage_state=``, ``headless=``, ``channel=``); in production it is
``PlaywrightDriver``, in tests it is a FakeDriver constructor. The handlers call
into ``tools.web.api`` passing the factory through, so the whole flow is
exercised without a real browser.
"""
from __future__ import annotations

import argparse
import json

from tools.web import api
from tools.web.actiondef import ActionDef
from tools.web.errors import UsageError


def _load_steps(args) -> list:
    """Resolve the step list from --actions (inline JSON) or --actions-file."""
    if args.actions and args.actions_file:
        raise UsageError("provide either --actions or --actions-file, not both")
    raw = None
    if args.actions:
        raw = args.actions
    elif args.actions_file:
        try:
            with open(args.actions_file, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            raise UsageError(f"cannot read --actions-file {args.actions_file!r}: {exc}")
    else:
        raise UsageError("provide --actions (JSON array) or --actions-file")
    try:
        steps = json.loads(raw)
    except ValueError as exc:
        raise UsageError(f"--actions is not valid JSON: {exc}")
    if not isinstance(steps, list):
        raise UsageError("--actions must be a JSON array of step objects")
    return steps


def run(driver_factory, args) -> dict:
    steps = _load_steps(args)
    return api.run_steps(
        args.session, steps, url=args.url,
        headless=not args.headed, channel=args.channel,
        hold_seconds=args.hold_seconds,
        hold_until_selector=args.hold_until_selector,
        hold_until_url_excludes=args.hold_until_url_excludes,
        driver_factory=driver_factory,
    )


def _run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--session", required=True, help="Saved session name to load")
    p.add_argument("--url", default=None,
                   help="Optional URL to visit before running the steps")
    p.add_argument("--actions", default=None,
                   help="Inline JSON array of steps (see README for the step schema)")
    p.add_argument("--actions-file", default=None,
                   help="Path to a JSON file containing the steps array")
    p.add_argument("--headed", action="store_true",
                   help="Show the browser window (default: headless)")
    p.add_argument("--channel", default=None,
                   help="Chromium channel: 'chrome' or 'msedge'")
    p.add_argument("--hold-seconds", type=int, default=None,
                   help="After the last step, keep the (headed) browser open up "
                        "to N seconds so a human can review and complete the "
                        "action themselves. Requires --headed. A hold that "
                        "expires is still a successful run")
    p.add_argument("--hold-until-selector", default=None,
                   help="End the hold early once this selector appears (i.e. "
                        "the human acted). Requires --hold-seconds")
    p.add_argument("--hold-until-url-excludes", default=None,
                   help="End the hold early once the address bar leaves this "
                        "host. Requires --hold-seconds")
    p.add_argument("--direct", action="store_true",
                   help="Bypass the owning tool's serializing broker and drive "
                        "the browser in-process (backup; only safe when that "
                        "broker is stopped / idle-closed)")


def get_text(driver_factory, args) -> dict:
    return api.get_text(
        args.session, args.url, selector=args.selector, wait=args.wait,
        headless=not args.headed, channel=args.channel,
        driver_factory=driver_factory,
    )


def _get_text_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--session", required=True, help="Saved session name to load")
    p.add_argument("--url", required=True, help="URL to navigate to")
    p.add_argument("--selector", default=None,
                   help="Optional CSS selector; default reads the whole page body")
    p.add_argument("--wait", default=None,
                   help="Optional selector to await before reading (for SPAs)")
    p.add_argument("--headed", action="store_true", help="Show the browser window")
    p.add_argument("--channel", default=None, help="Chromium channel: 'chrome'|'msedge'")
    p.add_argument("--direct", action="store_true",
                   help="Bypass the owning tool's serializing broker and drive "
                        "the browser in-process (backup; only safe when that "
                        "broker is stopped / idle-closed)")


def screenshot(driver_factory, args) -> dict:
    return api.screenshot(
        args.session, args.url, args.out, full_page=not args.viewport_only,
        wait=args.wait, headless=not args.headed, channel=args.channel,
        driver_factory=driver_factory,
    )


def _screenshot_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--session", required=True, help="Saved session name to load")
    p.add_argument("--url", required=True, help="URL to capture")
    p.add_argument("--out", required=True, help="Output image path (.png)")
    p.add_argument("--viewport-only", action="store_true",
                   help="Capture only the viewport (default: full page)")
    p.add_argument("--wait", default=None, help="Optional selector to await first")
    p.add_argument("--headed", action="store_true", help="Show the browser window")
    p.add_argument("--channel", default=None, help="Chromium channel: 'chrome'|'msedge'")
    p.add_argument("--direct", action="store_true",
                   help="Bypass the owning tool's serializing broker and drive "
                        "the browser in-process (backup; only safe when that "
                        "broker is stopped / idle-closed)")


def render_pdf(driver_factory, args) -> dict:
    if bool(args.html) == bool(args.html_file):
        raise UsageError("provide exactly one of --html or --html-file")
    if args.html_file:
        try:
            with open(args.html_file, encoding="utf-8") as fh:
                html = fh.read()
        except OSError as exc:
            raise UsageError(f"cannot read --html-file {args.html_file!r}: {exc}")
    else:
        html = args.html
    return api.render_pdf(html, args.out, fmt=args.format,
                          driver_factory=driver_factory)


def _render_pdf_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--html", default=None, help="Inline HTML string to render")
    p.add_argument("--html-file", dest="html_file", default=None,
                   help="Path to an HTML file to render")
    p.add_argument("--out", required=True, help="Output PDF path (.pdf)")
    p.add_argument("--format", default="A4",
                   help="Paper size: A4 (default) / Letter / Legal ...")


ACTIONS = {
    "run": ActionDef(
        run, _run_args,
        description="Load a session and run a declarative step list; return collected JSON.",
    ),
    "render-pdf": ActionDef(
        render_pdf, _render_pdf_args,
        description="Render an HTML string/file to a PDF (session-less, headless Chromium).",
    ),
    "get-text": ActionDef(
        get_text, _get_text_args,
        description="Load a session, open a URL, return visible text (whole page or a selector).",
    ),
    "screenshot": ActionDef(
        screenshot, _screenshot_args,
        description="Load a session, open a URL, save a screenshot.",
    ),
}
