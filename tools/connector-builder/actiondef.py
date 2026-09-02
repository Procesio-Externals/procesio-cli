"""ActionDef - dispatchable action unit for the connector-builder tool.

Mirrors the redmine/quickmail-web pattern. Actions that talk to the API receive
a live ``client`` first (so tests inject a fake and run with no network);
``needs_client`` decides that. Pure/local actions (none today, but kept for
parity) leave it False and receive only the parsed argparse namespace.
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
    needs_client: bool = True
    description: str = ""
