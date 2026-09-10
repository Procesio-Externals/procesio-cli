"""ActionDef - dispatchable action unit for the procesio tool."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Callable


def _no_args(_parser: argparse.ArgumentParser) -> None:
    return None


@dataclass
class ActionDef:
    func: Callable
    add_args: Callable[[argparse.ArgumentParser], None] = _no_args
    needs_client: bool = False  # True -> handler receives a ProcesioClient as 1st arg
    description: str = ""
    # Payload documentation for actions whose real contract is a structured argument
    # rather than its flags. argparse can only carry a one-line `help=`, which is enough
    # to say `--config` takes JSON and not enough to say what goes in it. These travel to
    # the manifest (gen_manifest) and from there to any caller that reads it.
    #   arg_schemas: arg name -> JSON Schema, taken from the file the tool VALIDATES
    #                against, so the published contract cannot drift from the enforced one.
    #   examples:    whole configs that are known to work - the fixtures the tests use.
    arg_schemas: dict = field(default_factory=dict)
    examples: list = field(default_factory=list)
