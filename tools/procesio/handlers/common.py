"""Shared argparse helpers for client-backed actions."""
from __future__ import annotations

import argparse

# Update-timestamp / version fields a resource may expose, in preference order. The
# FormTemplate and Projects GETs return created*/updated* (see PROCESIO-API-NOTES.md),
# so one of these is the optimistic-concurrency token; matched case-insensitively.
_TOKEN_FIELDS = (
    "updatedon", "updatedat", "modifiedon", "modifieddate", "lastmodified",
    "lastmodifiedon", "updated", "version", "rowversion", "concurrencystamp",
)


def concurrency_token(dto):
    """A best-effort optimistic-concurrency token for a resource DTO: its update
    timestamp or version. Returns (field, value) or None when the DTO exposes no such
    field (then the guard is inert — a safe no-op, never a false conflict)."""
    if not isinstance(dto, dict):
        return None
    low = {str(k).strip().lower(): v for k, v in dto.items()}
    for f in _TOKEN_FIELDS:
        v = low.get(f)
        if v not in (None, "", 0):
            return (f, v)
    return None


# Web-Api v2.79.1+ (PRC-5587): uploads to one owner (a flow instance and variable, a form
# instance, a schedule, a test action) take a lock, and one that cannot get it answers
# coded error 215 FILE_LIST_LOCKED and writes NOTHING, so retrying it is safe.
FILE_LIST_LOCKED = 215
_UPLOAD_BACKOFF_S = (0.5, 1.0, 2.0, 4.0)


def upload_retrying_lock(client, path: str, *, files: dict, headers: dict | None = None,
                         sleep=None, log=None):
    """`client.request_multipart`, retried with backoff while the server answers 215
    FILE_LIST_LOCKED (another upload to the same owner holds the file list). Any other
    error, or a lock that outlasts the backoff, is raised as it came."""
    import time

    from tools.procesio.errors import ProcesioAPIError, procesio_error_items

    sleep = sleep or time.sleep
    for attempt, wait in enumerate((*_UPLOAD_BACKOFF_S, None)):
        try:
            return client.request_multipart(path, files=files, headers=headers)
        except ProcesioAPIError as e:
            locked = any(i.get("statusCode") == FILE_LIST_LOCKED
                         for i in procesio_error_items(e.details))
            if not locked or wait is None:
                raise
            if log:
                log(f"file list locked by another upload; retrying in {wait:g}s "
                    f"(attempt {attempt + 2})")
            sleep(wait)


def add_force_arg(p: argparse.ArgumentParser) -> None:
    """--force skips the optimistic-concurrency check (see guard_unchanged)."""
    p.add_argument(
        "--force", action="store_true",
        help="overwrite even if the resource changed since it was read (skip the "
             "optimistic-concurrency check)",
    )


def guard_unchanged(refetch, baseline, *, force):
    """Optimistic-concurrency guard for a surgical read-modify-write.

    A surgical action GETs the live resource, changes one thing, and PUTs the WHOLE
    DTO back — last-write-wins. Right before the PUT this re-reads the resource
    (``refetch()``) and refuses to overwrite if its concurrency token moved since
    ``baseline`` was read (another CLI call or a designer "Save" landed in between).

    Inert when the resource exposes no update-timestamp/version field: it returns
    without re-reading, so it never blocks and never issues an extra GET. ``--force``
    skips the check. Residual race: a write between this re-read and the PUT is still
    not caught (the API has no If-Match/ETag) — this closes the wide window, not the
    instant. Returns a small status dict for the action's result.
    """
    from tools.procesio.errors import UsageError
    tok = concurrency_token(baseline)
    if force:
        return {"checked": False, "forced": True, "token": tok[1] if tok else None}
    if tok is None:
        return {"checked": False,
                "note": "resource exposes no updatedOn/version field; concurrency guard inactive"}
    cur = concurrency_token(refetch())
    if cur and cur[1] != tok[1]:
        raise UsageError(
            f"the resource changed since it was read ({tok[0]} {tok[1]!r} -> {cur[1]!r}) "
            f"— re-run to pick up the newer version, or pass --force to overwrite the "
            f"concurrent change")
    return {"checked": True, "token": tok[1]}


def add_profile_arg(p: argparse.ArgumentParser) -> None:
    """Every client-backed action accepts --profile to pick the credential and
    --workspace-id to set/override the active workspace (the `workspaceid`
    header). --workspace-id is what scopes a userpass session to a workspace and
    overrides an api-key profile's own workspace."""
    p.add_argument(
        "--profile",
        help="credential profile name (defaults to the stored default profile)",
    )
    p.add_argument(
        "--workspace-id", dest="workspace_id",
        help="workspace GUID to scope this call (sets/overrides the workspaceid header)",
    )
    p.add_argument(
        "--environment", dest="environment",
        help="PROCESIO environment for this call, e.g. Main-QA (defaults to the "
             "credential's binding, else the default environment / Main-PROD)",
    )


def add_paging_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--page", type=int, help="page number (1-based)")
    p.add_argument("--page-size", dest="page_size", type=int, help="items per page")
