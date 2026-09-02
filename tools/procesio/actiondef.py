"""ActionDef - dispatchable action unit for the procesio tool."""
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
    needs_client: bool = False  # True -> handler receives a ProcesioClient as 1st arg
    description: str = ""
