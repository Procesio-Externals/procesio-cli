"""Cross-build telemetry: GET /telemetry/logs (own builds; all builds for admin)."""
from __future__ import annotations

import argparse

from actiondef import ActionDef


def telemetry(client, args) -> dict:
    params: dict = {"page": args.page, "page_size": args.page_size}
    for f in ("build_id", "stage", "model", "model_search", "after", "before"):
        v = getattr(args, f)
        if v:
            params[f] = v
    if args.success is not None:
        params["success"] = str(args.success).lower()
    return client.get("/telemetry/logs", params)


def _telemetry_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", dest="page_size", type=int, default=100,
                   help="Max 500")
    p.add_argument("--build-id", dest="build_id",
                   help="Comma-separated build UUIDs to filter")
    p.add_argument("--stage", help="Comma-separated stage names")
    p.add_argument("--success", type=lambda v: v.lower() in ("1", "true", "yes"),
                   default=None, help="Filter by success true/false")
    p.add_argument("--model", help="Comma-separated model names")
    p.add_argument("--model-search", dest="model_search", help="Substring model search")
    p.add_argument("--after", help="ISO datetime lower bound")
    p.add_argument("--before", help="ISO datetime upper bound")


ACTIONS: dict[str, ActionDef] = {
    "telemetry": ActionDef(
        telemetry, _telemetry_args,
        description="Cross-build LLM telemetry (cost/tokens/latency), filterable."),
}
