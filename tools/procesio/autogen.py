"""Spec-driven actions — one per PROCESIO Web-API endpoint (full 1:1 coverage).

Every operation in the bundled Swagger index (data/endpoints.json) becomes a
dispatchable action so the tool covers the *entire* API surface, not just the
curated shortcuts. Generation rules:

  * **name** = `<method>-<path-slug>`, where the path is stripped of `/api/`,
    `/` -> `-`, and `{param}` -> `by-param`. e.g.
      GET  /api/Projects/{id}/payload        -> get-projects-by-id-payload
      POST /api/Projects/instances/{id}/stop -> post-projects-instances-by-id-stop
    Method-prefixing makes names unique (OpenAPI guarantees one op per
    method+path) and predictable.

  * **args**: `--profile` + one required `--<name>` per PATH param + one optional
    `--<name>` per QUERY param + `--body` (JSON) when the operation takes a
    request body + `--dry-run` (compose & return the request without sending).

Path params are taken from the `{...}` in the path itself; query params are the
rest of the recorded parameter list. Complex request bodies are passed through
as raw JSON for now; structured builders ("create a process/form/datatype/…")
will be layered on later as sub-tools without changing these endpoints.

The curated, ergonomically-named actions (list-processes, run-process, …) live
alongside these and take precedence on the (non-colliding) name space.
"""
from __future__ import annotations

import re

from tools.procesio import swagger
from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.handlers.common import add_profile_arg

# Arg names the generator owns; a spec param must never collide with these.
_RESERVED_ARGS = {"profile", "body", "dry-run", "help"}

_PATH_PARAM = re.compile(r"\{([^}]+)\}")


def action_name(method: str, path: str) -> str:
    p = path[5:] if path.startswith("/api/") else path.lstrip("/")
    segs = []
    for seg in p.split("/"):
        if not seg:
            continue
        m = _PATH_PARAM.fullmatch(seg)
        segs.append(f"by-{m.group(1)}" if m else seg)
    slug = "-".join(segs)
    name = f"{method.lower()}-{slug}"
    name = re.sub(r"[^a-zA-Z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-").lower()
    return name


def _path_params(path: str) -> list[str]:
    return _PATH_PARAM.findall(path)


def _make(method: str, path: str, path_params: list[str],
          query_params: list[str], has_body: bool):
    def add_args(p):
        add_profile_arg(p)
        for pp in path_params:
            p.add_argument(f"--{pp}", required=True, help=f"path segment {{{pp}}}")
        for qp in query_params:
            p.add_argument(f"--{qp}", help="query parameter")
        if has_body:
            p.add_argument("--body", help="request body as JSON (object or array)")
        p.add_argument("--dry-run", dest="dry_run", action="store_true",
                       help="compose and return the request without sending it")

    def func(client, args):
        resolved = path
        for pp in path_params:
            resolved = resolved.replace("{" + pp + "}", str(getattr(args, pp)))
        query = {qp: getattr(args, qp) for qp in query_params}
        query = {k: v for k, v in query.items() if v is not None}
        body = parse_json_arg(getattr(args, "body", None), "body") if has_body else None
        if getattr(args, "dry_run", False):
            return {"dry_run": True, "method": method, "path": resolved,
                    "query": query, "body": body}
        return {"result": client.request(method, resolved, query=query, body=body)}

    return add_args, func


def _describe(ep: dict) -> str:
    base = f"{ep['method']} {ep['path']}  [{ep.get('tag', '')}]"
    summary = (ep.get("summary") or "").strip()
    if summary and summary.lower() not in base.lower():
        base = f"{base} - {summary}"
    return base[:240]


def build_actions(reserved: set[str] | None = None) -> dict[str, ActionDef]:
    """Build one ActionDef per endpoint. `reserved` names (curated/profile/auth)
    are skipped so the curated actions win; method-prefixing means this never
    actually drops an endpoint in practice."""
    reserved = reserved or set()
    out: dict[str, ActionDef] = {}
    for ep in swagger.all_endpoints():
        method, path = ep["method"], ep["path"]
        pparams = _path_params(path)
        qparams = [q for q in ep.get("params", [])
                   if q not in pparams and q not in _RESERVED_ARGS]
        # A param colliding with a reserved arg name would break argparse; skip
        # the body (rare) rather than crash, and note it in the description.
        bad = [q for q in ep.get("params", []) if q in _RESERVED_ARGS]
        has_body = bool(ep.get("body"))
        name = action_name(method, path)
        if name in reserved or name in out:
            # extremely unlikely; disambiguate deterministically.
            name = f"{name}-{method.lower()}"
        add_args, func = _make(method, path, pparams, qparams, has_body)
        desc = _describe(ep)
        if bad:
            desc += f"  (note: spec params {bad} reachable via `request`)"
        out[name] = ActionDef(func=func, add_args=add_args, needs_client=True,
                              description=desc)
    return out
