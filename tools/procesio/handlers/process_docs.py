"""process-docs / workspace-docs: read the DOCUMENTED INTENT of processes.

A self-documenting process carries its purpose (the flow description), each action's purpose
in it (customData.description) and, past 3 actions besides Start/Stop, titled areas on the
canvas (see dto/process/selfdoc.py). These two actions read that back as knowledge: start the
analysis of a process, or of a workspace you do not know, here - before reading parameters -
and see at the same time which processes are not documented yet.
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.flowmodel import docs
from tools.procesio.handlers.common import add_profile_arg


def _flow(client, pid: str) -> dict:
    resp = client.get(f"/api/Projects/{pid}")
    return docs._flow(resp)


def _one_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")


def process_docs(client, args) -> dict:
    try:
        flow = _flow(client, args.id)
    except ProcesioAPIError as e:
        raise UsageError(f"could not read process {args.id}: {e}") from e
    return {"result": docs.read(flow)}


def _ws_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--search", help="only processes whose name contains this text")
    p.add_argument("--limit", type=int, default=300,
                   help="read at most this many processes (default 300)")
    p.add_argument("--purpose-only", dest="purpose_only", action="store_true",
                   help="one list call: title + purpose only, no per-process read (fast)")
    p.add_argument("--details", action="store_true",
                   help="include every action's purpose and area per process")


def _list_all(client, search: str | None, limit: int) -> list[dict]:
    items, page = [], 1
    while len(items) < limit:
        r = client.get("/api/Projects", {"pageNumber": page, "pageItemCount": 100,
                                         "searchName": search})
        batch = (r.get("pageItems") if isinstance(r, dict) else r) or []
        items.extend(batch)
        total = r.get("totalItemCount") if isinstance(r, dict) else None
        if not batch or (total is not None and len(items) >= total):
            break
        page += 1
    return items[:limit]


def workspace_docs(client, args) -> dict:
    procs = _list_all(client, args.search, args.limit)
    rows, unread = [], []
    for p in procs:
        row = {"id": p.get("id"), "title": p.get("title"),
               "purpose": (p.get("description") or "").strip()}
        if not args.purpose_only:
            try:
                d = docs.read(_flow(client, p.get("id")))
            except ProcesioAPIError as e:
                unread.append({"id": p.get("id"), "title": p.get("title"), "error": str(e)})
                rows.append(row)
                continue
            row.update({"documented": d["documented"], "coverage": d["coverage"],
                        "areas": [{"title": a["title"], "text": a["text"]} for a in d["areas"]],
                        "gaps": sorted({f["code"] for f in d["findings"] if f["severity"] == "error"})})
            if args.details:
                row["actions"] = [{"name": a["name"], "template": a["template"],
                                   "purpose": a["purpose"], "area": a["area"]} for a in d["actions"]]
        rows.append(row)
    summary = {"processes": len(rows), "with_purpose": sum(1 for r in rows if r["purpose"])}
    if not args.purpose_only:
        summary["documented"] = sum(1 for r in rows if r.get("documented"))
    out = {"workspace_id": client.workspace_id, "summary": summary, "processes": rows}
    if unread:
        out["unread"] = unread
    return {"result": out}


ACTIONS = {
    "process-docs": ActionDef(
        func=process_docs, add_args=_one_args, needs_client=True,
        description=("Read a process's DOCUMENTED INTENT: its purpose (description), each "
                     "action's purpose in it (customData.description; a template's stock caption "
                     "counts as undocumented), the titled areas on the canvas and which actions "
                     "they group, free canvas notes, and the documentation gaps (`findings`, "
                     "`documented`). Read this first when analysing a process."),
    ),
    "workspace-docs": ActionDef(
        func=workspace_docs, add_args=_ws_args, needs_client=True,
        description=("Documented intent across a WORKSPACE: every process with its purpose, "
                     "areas, documentation coverage and gaps (--details adds every action's "
                     "purpose; --purpose-only is one list call). The starting map for a "
                     "workspace you do not know, and the list of processes still undocumented. "
                     "Workspace-scoped: pass --workspace-id."),
    ),
}
