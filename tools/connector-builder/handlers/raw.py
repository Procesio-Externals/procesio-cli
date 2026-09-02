"""Generic escape hatch: call ANY connector-builder endpoint not first-classed.

Keeps the tool complete as the API evolves — new endpoints are reachable via
`api --method ... --path ...` without a code change, while the common workflow
stays ergonomic through the dedicated actions.
"""
from __future__ import annotations

import argparse

from actiondef import ActionDef
from handlers.common import parse_json


def api(client, args) -> dict:
    params = parse_json(args.query, what="query", expect=dict)
    body = parse_json(args.body, what="body", expect=(dict, list)) if args.body else None
    if args.out:
        # Binary / file response: stream to disk (GET only makes sense here).
        return client.download(args.path, args.out, params=params)
    result = client.request(args.method, args.path, params=params, json_body=body)
    return {"path": args.path, "method": args.method.upper(), "response": result}


def _api_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--method", default="GET",
                   help="HTTP method (GET/POST/PUT/PATCH/DELETE)")
    p.add_argument("--path", required=True,
                   help="Endpoint path, e.g. /builds or /admin/users")
    p.add_argument("--query", help="Query params as a JSON object")
    p.add_argument("--body", help="Request body as JSON (object or array)")
    p.add_argument("--out", help="If set, stream the response to this file (binary)")


ACTIONS: dict[str, ActionDef] = {
    "api": ActionDef(api, _api_args,
                     description="Call any endpoint (method/path/query/body); --out streams binary."),
}
