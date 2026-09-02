"""web tool - drive web apps that have no API via Playwright with saved sessions.

Public Python API for other tools/agents is re-exported here for convenience:

    from tools.web import open_session, run_steps, get_text, screenshot, BrowserDriver

See tools/web/api.py for the full surface and README.md for examples.
"""
from __future__ import annotations

from tools.web.api import (  # noqa: F401
    delete_session,
    get_text,
    list_sessions,
    open_session,
    run_steps,
    save_session,
    screenshot,
    session_path,
)
from tools.web.driver import BrowserDriver, PlaywrightDriver  # noqa: F401
