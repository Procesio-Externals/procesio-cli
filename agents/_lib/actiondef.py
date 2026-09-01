"""ActionDef - dispatchable action unit for agents.

Like the tool-side ActionDef, but instead of a `client` flag it has a `context`
flag: when True the dispatcher builds the agent's shared context (config + state
backend) and passes it as the first argument. Pure actions (status, version)
leave it False and just receive the parsed argparse namespace.
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
    context: bool = False  # True -> dispatch builds the agent context, passes it first
    description: str = ""
