"""Offline structural reader actions over a .procesio export / live flow DTO.

`read-flow-graph` returns the canonical node/edge graph model (the substrate the canvas
layout tool and inspect-flow build on). No network; reads a file, '-' (stdin), or a raw
JSON string.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio import errors
from tools.procesio.flowmodel import read_bundle, read_flow
from tools.procesio.flowmodel.inspect import inspect as _inspect


def _load_in(value: str) -> str:
    """Resolve --in to a JSON string: '-' = stdin, an existing path = file, else literal."""
    if value == "-":
        return sys.stdin.read()
    try:
        p = Path(value)
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return value


def _in_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")
    p.add_argument("--resource-map", dest="resource_map", action="store_true",
                   help="emit every flow + the cross-process (process→process) edge list")


def read_flow_graph(args) -> dict:
    raw = _load_in(args.in_path)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise errors.UsageError(f"--in is not valid JSON: {e}")
    if args.resource_map:
        return {"result": read_bundle(obj)}
    return {"result": read_flow(obj, flow_id=args.flow_id).to_dict()}


def _inspect_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")


def inspect_flow(args) -> dict:
    raw = _load_in(args.in_path)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise errors.UsageError(f"--in is not valid JSON: {e}")
    return {"result": _inspect(obj, flow_id=args.flow_id)}


ACTIONS = {
    "read-flow-graph": ActionDef(
        func=read_flow_graph, add_args=_in_args, needs_client=False,
        description="Parse a .procesio export/flow into a node/edge graph model "
                    "(offline). --resource-map for the cross-process graph.",
    ),
    "inspect-flow": ActionDef(
        func=inspect_flow, add_args=_inspect_args, needs_client=False,
        description="Structural summary of a flow (offline): counts, action families, "
                    "branches, subprocess calls, resources, variables, advisory smells.",
    ),
}
