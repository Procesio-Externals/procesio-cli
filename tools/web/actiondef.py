"""ActionDef - dispatchable action unit for the web tool.

Unlike the HTTP tools (which inject an API client), web actions receive a
``BrowserDriver``. ``needs_driver`` decides whether the dispatcher builds and
injects one. Interactive / session-management actions (save-session,
list-sessions, delete-session) manage their own resources and set it False.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable


def _no_args(_parser: argparse.ArgumentParser) -> None:
    return None


@dataclass
class ActionDef:
    func: Callable
    add_args: Callable[[argparse.ArgumentParser], None] = _no_args
    needs_driver: bool = True  # True -> dispatcher builds a BrowserDriver, passes it first
    description: str = ""
