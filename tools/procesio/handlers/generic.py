"""Generic, full-coverage actions.

`request` reaches ANY of the ~247 documented Web-API endpoints, so the tool
covers the whole API surface even where there is no curated wrapper.
`list-endpoints` browses the bundled Swagger-derived index to discover paths.
"""
from __future__ import annotations

import argparse

from tools.procesio import swagger
from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_profile_arg
from tools._lib.io import log

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def _unmangle_path(path: str) -> tuple[str, str | None]:
    """Recover a shell-mangled `--path` and return (clean_path, warning|None).

    On Windows, Git Bash / MSYS rewrites a leading-slash argument the moment it
    looks like a POSIX path: `--path /api/FormTemplate/{id}` reaches the tool as
    `/C:/Program Files/Git/api/FormTemplate/{id}`, so the client builds
    `…/C:/Program Files/Git/api/…` and the gateway answers 403 on the garbage
    path. A real Web-API path starts with `/api/`, contains `/api/` exactly once,
    and never contains a ':' — so when a ':' (a drive) shows up alongside an
    `/api/`, the intended path is unambiguously the `/api/…` tail. We recover it
    and warn (the fix is the caller's shell: pass `//api/…` or set
    MSYS_NO_PATHCONV=1). Clean paths are returned untouched, so callers on
    PowerShell/cmd are unaffected. A stray leading `//` (the `//api/…` MSYS
    workaround) is also collapsed to a single slash.
    """
    p = path
    warn = None
    low = p.lower()
    if ":" in p and "/api/" in low:
        tail = p[low.index("/api/"):]
        warn = (f"--path looked shell-mangled ({path!r}); recovered {tail!r}. "
                "Your shell (Git Bash/MSYS) rewrote the leading slash — pass "
                "'//api/...' or set MSYS_NO_PATHCONV=1 to prevent this.")
        p = tail
    if p.startswith("//"):
        p = p[1:]
    return p, warn


def _request_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--method", default="GET",
                   help="HTTP method (GET/POST/PUT/PATCH/DELETE). Default GET.")
    p.add_argument("--path", required=True,
                   help="endpoint path, e.g. /api/Projects or /api/Projects/{id}")
    p.add_argument("--query", help="query params as a JSON object")
    p.add_argument("--body", help="request body as JSON (object or array)")
    p.add_argument("--body-file", dest="body_file",
                   help="path to a UTF-8 JSON file for the request body "
                        "(use instead of --body for large payloads like full flow DTOs)")


def request(client, args) -> dict:
    method = (args.method or "GET").upper()
    if method not in _METHODS:
        raise UsageError(f"--method must be one of {', '.join(_METHODS)}")
    query = parse_json_arg(args.query, "query")
    if query is not None and not isinstance(query, dict):
        raise UsageError("--query must be a JSON object")
    body_file = getattr(args, "body_file", None)
    if body_file:
        if args.body:
            raise UsageError("pass either --body or --body-file, not both")
        import json as _json
        from pathlib import Path as _Path
        try:
            body = _json.loads(_Path(body_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise UsageError(f"--body-file could not be read as JSON: {e}") from e
    else:
        body = parse_json_arg(args.body, "body")
    path, warn = _unmangle_path(args.path)
    if warn:
        log(warn)
    result = client.request(method, path, query=query, body=body)
    return {"method": method, "path": path, "result": result}


def _list_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--filter", help="substring match on path/tag/summary")
    p.add_argument("--tag", help="exact tag filter, e.g. ProcessTemplate")
    p.add_argument("--method", help="filter by HTTP method")
    p.add_argument("--tags-only", action="store_true",
                   help="just list the available tags + counts")


def list_endpoints(args) -> dict:
    if args.tags_only:
        counts: dict[str, int] = {}
        for e in swagger.all_endpoints():
            counts[e["tag"]] = counts.get(e["tag"], 0) + 1
        return {"meta": swagger.meta(),
                "tags": [{"tag": t, "count": counts[t]} for t in sorted(counts)]}
    found = swagger.find(args.filter, args.tag, args.method)
    return {
        "meta": swagger.meta(),
        "count": len(found),
        "endpoints": found,
    }


ACTIONS = {
    "request": ActionDef(
        func=request, add_args=_request_args, needs_client=True,
        description="Call ANY Web-API endpoint: --method --path [--query JSON] [--body JSON].",
    ),
    "list-endpoints": ActionDef(
        func=list_endpoints, add_args=_list_args,
        description="Browse the bundled Swagger index of all PROCESIO endpoints.",
    ),
}
