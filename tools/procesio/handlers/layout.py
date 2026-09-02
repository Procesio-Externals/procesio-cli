"""Deterministic canvas auto-layout actions (offline).

`layout-flow` recomputes tidy positions for a flow's actions and writes them back into a
re-importable .procesio bundle. `layout-resource-map` positions the cross-process call
graph. Both are pure/offline (no network).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio import errors
from tools.procesio.handlers.common import add_profile_arg
from tools.procesio.handlers.flowgraph import _load_in
from tools.procesio.layout import adapter, report


def _flow_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")
    p.add_argument("--out", dest="out_path",
                   help="write the re-laid-out bundle here (omit to print it)")
    p.add_argument("--only", dest="only",
                   help="comma-separated action ids to reposition WITHOUT reshuffling the "
                        "rest (re-tidy just these; everything else stays byte-identical)")
    p.add_argument("--cluster", action="store_true",
                   help="cluster consecutive horizontal actions: fold a long run (>=5 "
                        "1-in/1-out actions, outside a For-Each) into a compact serpentine "
                        "grid to conserve space. Opt-in.")
    p.add_argument("--min-crossings", dest="min_crossings", action="store_true",
                   help="best-effort edge-crossing reduction: nudge movable actions to cut "
                        "line crossings (minimizes, not guaranteed zero). Opt-in.")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="emit the computed positions only; write/print nothing else")


def layout_flow(args) -> dict:
    obj = _parse(args.in_path)
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    res = adapter.layout_flow(obj, flow_id=args.flow_id, only=only, cluster=args.cluster,
                              minimize_crossings=args.min_crossings)
    summary = {"flow_id": res["flow_id"], "nodes_moved": res["nodes_moved"],
               "areas_resized": res["areas_resized"], "bbox": res["bbox"]}
    if args.dry_run:
        return {"result": {**summary, "positions": res["positions"], "areas": res["areas"]}}
    if args.out_path:
        Path(args.out_path).write_text(json.dumps(res["bundle"]), encoding="utf-8")
        return {"result": {**summary, "out": args.out_path}}
    return {"result": res["bundle"]}


def _verify_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")


def verify_layout(args) -> dict:
    return {"result": adapter.verify_render(_parse(args.in_path), flow_id=args.flow_id)}


def _rmap_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export bundle: a path, '-' for stdin, or raw JSON")
    p.add_argument("--root-flow-id", dest="root_flow_id",
                   help="the LVL0 process to center the map on (optional)")
    p.add_argument("--levels", type=int, help="max depth each side (default: unlimited)")


def layout_resource_map(args) -> dict:
    obj = _parse(args.in_path)
    return {"result": adapter.layout_resource_map(
        obj, root_flow_id=args.root_flow_id, levels=args.levels)}


def _report_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)   # --profile / --workspace-id (for live --id fetch)
    p.add_argument("--in", dest="in_path",
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON "
                        "(offline). Omit and pass --id to verify a LIVE process instead.")
    p.add_argument("--id", dest="process_id",
                   help="verify a LIVE process by id (needs --workspace-id); alternative to --in")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")


def layout_report(client, args) -> dict:
    """Engine-agnostic layout verification: measure a laid-out flow's readability (overlaps,
    children-outside-frame, crossings, edge lengths, vertical rows, For-Each padding/size).
    Works on the OUTPUT of ANY layout engine (legacy or elk)."""
    if args.in_path:
        obj = _parse(args.in_path)
    elif args.process_id:
        resp = client.get(f"/api/Projects/{args.process_id}")
        obj = resp.get("flow") if isinstance(resp, dict) and "flow" in resp else resp
    else:
        raise errors.UsageError("pass --in <flow/export> or --id <process-id> (+ --workspace-id)")
    return {"result": report.build_report(obj, flow_id=args.flow_id)}


def _parse(in_path: str) -> dict:
    raw = _load_in(in_path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise errors.UsageError(f"--in is not valid JSON: {e}")


ACTIONS = {
    "layout-flow": ActionDef(
        func=layout_flow, add_args=_flow_args, needs_client=False,
        description="Recompute tidy canvas positions for a flow (deterministic, offline). "
                    "Writes positions back into a re-importable bundle (--out) or prints it.",
    ),
    "layout-resource-map": ActionDef(
        func=layout_resource_map, add_args=_rmap_args, needs_client=False,
        description="Position the cross-process (process→process) call graph from a "
                    "bundle (offline).",
    ),
    "verify-layout": ActionDef(
        func=verify_layout, add_args=_verify_args, needs_client=False,
        description="Simulate the designer's rendering of a flow's positions and report "
                    "problems (container children outside their frame, node overlaps).",
    ),
    "layout-report": ActionDef(
        func=layout_report, add_args=_report_args, needs_client=True,
        description="Engine-agnostic layout verification: readability report for a laid-out "
                    "flow (hard issues + crossings, edge lengths, vertical rows, For-Each "
                    "padding/size). Works for ANY layout engine. Offline via --in, or LIVE "
                    "via --id + --workspace-id.",
    ),
}
