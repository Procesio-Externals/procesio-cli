"""Curated CRUD-parity + verification-oracle actions.

Closes the ergonomic gaps the capability audit found: every resource had curated
create/edit but raw-only get/delete/list, and the verification oracles the notes
champion (validate, credential test, custom-action test) were only reachable
internally. Naming mirrors the existing `<resource>-create`/`-edit` pairs.

JSON in / JSON out; impure (live client). Thin wrappers over documented endpoints:
  form/document/webhook/credential   -get / -delete   (+ -list for form/document)
  process   -delete / -validate / -toggle-activation
  form      -duplicate
  webhook   -launch
  credential-test        POST /api/Credentials/test  (builds the DTO, returns the probe)
  customaction-test      POST /api/Actions/test
  import                 POST /api/Transport/import  (multipart .procesio, mirrors `export`)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg


def _id_args(p: argparse.ArgumentParser, help_text: str) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help=help_text)


# -- factories for the thin get / delete / list / post-by-id wrappers ---------

def _get_action(path_tpl: str, help_text: str) -> ActionDef:
    def fn(client, args):
        return {"result": client.get(path_tpl.format(id=args.id))}
    return ActionDef(func=fn, add_args=lambda p: _id_args(p, help_text), needs_client=True,
                     description=f"Get one resource by id (GET {path_tpl}).")


def _delete_action(path_tpl: str, help_text: str) -> ActionDef:
    def fn(client, args):
        client.request("DELETE", path_tpl.format(id=args.id))
        return {"deleted": True, "id": args.id}
    return ActionDef(func=fn, add_args=lambda p: _id_args(p, help_text), needs_client=True,
                     description=f"Delete a resource by id (DELETE {path_tpl}).")


def _list_action(path: str, desc: str) -> ActionDef:
    def fn(client, args):
        r = client.get(path)
        items = r.get("pageItems") if isinstance(r, dict) and "pageItems" in r else r
        return {"count": len(items) if isinstance(items, list) else None, "items": items}
    return ActionDef(func=fn, add_args=add_profile_arg, needs_client=True, description=desc)


def _post_by_id_action(path_tpl: str, help_text: str, result_key: str) -> ActionDef:
    def fn(client, args):
        resp = client.post(path_tpl.format(id=args.id))
        return {result_key: True, "id": args.id, "result": resp}
    return ActionDef(func=fn, add_args=lambda p: _id_args(p, help_text), needs_client=True,
                     description=f"POST {path_tpl}.")


# -- verification oracles + import (bespoke bodies) ---------------------------

def validate_process(client, args) -> dict:
    """Run PROCESIO's own validator on an existing process (POST /api/Projects/validate
    with the flow DTO). An EMPTY 200 response means VALID; validation failures come back
    as an error list (surfaced whether the platform returns 200-with-errors or a 4xx)."""
    flow = client.get(f"/api/Projects/{args.id}")
    flow = flow.get("flow") if isinstance(flow, dict) and "flow" in flow else flow
    try:
        res = client.post("/api/Projects/validate", flow)
    except ProcesioAPIError as e:
        det = e.details if isinstance(e.details, dict) else {"body": e.details}
        return {"id": args.id, "isValid": False, "errors": det.get("body", det)}
    empty = (not res) or (isinstance(res, dict) and list(res.keys()) == ["raw_text"] and not res["raw_text"])
    if empty:
        return {"id": args.id, "isValid": True, "errors": []}
    errs = (res.get("errors") or res.get("validationErrors")) if isinstance(res, dict) else None
    valid = res.get("isValid") if isinstance(res, dict) else None
    return {"id": args.id, "isValid": valid if valid is not None else (not errs), "errors": errs, "result": res}


def credential_test(client, args) -> dict:
    """Build a credential DTO from a config and run the live connection probe
    (POST /api/Credentials/test) WITHOUT saving it — the notes' 'connection oracle'."""
    from tools.procesio.dto.credential import builder as cb
    cfg = parse_json_arg(args.config, "config") if args.config else \
        json.loads(Path(args.config_file).read_text(encoding="utf-8"))
    ctx = cb.prepare_ctx(client, cfg)          # resolves the template (+ probes)
    dto = cb.build(cfg, ctx)
    res = client.post("/api/Credentials/test", dto)
    ok = isinstance(res, dict) and res.get("isSuccess") is True
    return {"tested": True, "isSuccess": ok, "result": res}


def customaction_test(client, args) -> dict:
    """Test a custom action (POST /api/Actions/test). --body is the DetailedTestAction
    request {variables, gid, testValues, action, connectionId}."""
    body = parse_json_arg(args.body, "body") if args.body else \
        json.loads(Path(args.body_file).read_text(encoding="utf-8"))
    return {"result": client.post("/api/Actions/test", body)}


def webhook_launch(client, args) -> dict:
    """Fire a webhook-triggered process with a payload (POST /api/Webhooks/launch/{id})."""
    payload = parse_json_arg(args.payload, "payload") if args.payload else None
    return {"launched": True, "id": args.id,
            "result": client.post(f"/api/Webhooks/launch/{args.id}", payload)}


# `POST /api/Transport/import` takes SEVEN required boolean headers, one per
# entity category plus the overwrite switch. They default to including
# everything, because a pack is normally imported whole and a silently skipped
# category is the failure this endpoint is worst at reporting.
_IMPORT_FLAGS = {
    "override_data": "overrideData",
    "data_types": "importDataTypes",
    "flows": "importFlows",
    "credentials": "importCredentials",
    "documents": "importDocuments",
    "forms": "importForms",
    "data_stores": "importDataStores",
}


def import_bundle(client, args) -> dict:
    """Import components from a .procesio bundle (POST /api/Transport/import,
    multipart). Mirrors the curated `export`.

    ⚠ TWO THINGS THIS ENDPOINT IS UNFORGIVING ABOUT, both learned the hard way:

    * the file part is named **`importedData`**, not `file`. A wrongly named
      part is not reported as such.
    * the seven boolean headers are **required** (`[FromHeader]` value types).
      Omitting them is a malformed request.

    ⚠ AND IT ANSWERS `403 Forbidden` WITH THE BODY `MIGRATE` ON *ANY* ERROR -
    a malformed request and a genuine permission failure are indistinguishable
    from the response alone. It also requires `Workspace:Admin`. So the result
    below ECHOES the headers that were sent: without that, a 403 cannot be read
    against the request that caused it, and the obvious reading ("we lack the
    permission") may simply be wrong.
    """
    path = Path(args.file)
    if not path.is_file():
        raise UsageError(f"bundle file not found: {args.file}")
    data = path.read_bytes()
    headers = {}
    for dest, wire in _IMPORT_FLAGS.items():
        off = getattr(args, "no_" + dest, False)
        headers[wire] = "false" if off else "true"
    try:
        resp = client.request_multipart(
            "/api/Transport/import",
            files={"importedData": (path.name, data,
                                    "application/octet-stream")},
            headers=headers)
    except ProcesioAPIError as e:
        # surface the request alongside the opaque refusal
        raise ProcesioAPIError(
            getattr(e, "status", None) or 0,
            "import failed. ⚠ This endpoint returns 403/MIGRATE on ANY error, "
            "including a malformed request, and requires Workspace:Admin — a "
            "403 here is not by itself evidence of a permission problem",
            {"headers_sent": headers, "file": path.name,
             "bytes": len(data), "underlying": str(e)[:300]}) from e
    return {"imported": True, "file": path.name, "bytes": len(data),
            "headers_sent": headers, "result": resp}


def _import_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--file", required=True,
                   help="path to the .procesio bundle to import")
    for dest, wire in _IMPORT_FLAGS.items():
        p.add_argument("--no-" + dest.replace("_", "-"),
                       dest="no_" + dest, action="store_true",
                       help="send %s=false (default true)" % wire)


def _cred_test_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--config", help="credential config as a JSON object")
    p.add_argument("--config-file", dest="config_file", help="path to a credential JSON config file")


def _ca_test_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--body", help="DetailedTestAction request as a JSON object")
    p.add_argument("--body-file", dest="body_file", help="path to the request JSON")


def _launch_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="webhook id")
    p.add_argument("--payload", help="JSON payload to send to the webhook")


def _read_active(client, pid: str):
    """The ONLY trustworthy activation read: the `active` field of the list projection.

    Best-effort by design - a process past page 1 of a large workspace is simply not
    found, and that has to read as "unknown" rather than "inactive".
    """
    try:
        listing = client.get("/api/Projects") or {}
        row = next((p for p in (listing.get("pageItems") or [])
                    if str(p.get("id")) == str(pid)), None)
        return row.get("active") if row is not None else None
    except Exception:  # noqa: BLE001 - advisory read; never mask the caller's own call
        return None


def toggle_activation(client, args) -> dict:
    """Arm/disarm a process's triggers (PATCH /api/Projects/{id}/toggle-activation).

    The PATCH LIES: it answers ``{"value": null, "errors": []}`` whether or not the write
    landed, and ``GET /api/Projects/{id}.status`` is NOT the activation flag either (see
    PROCESIO-API-NOTES.md). The only trustworthy read is the ``active`` field of the
    list-processes projection, so re-read it after the PATCH and report the ACTUAL state
    instead of the always-success echo. The re-read is best-effort (a process past page 1
    of a large workspace may be missed): when it cannot confirm, say so rather than imply
    success. Platform-side this is B-048 cluster 4b — the PATCH should report its outcome.
    """
    before = _read_active(client, args.id)
    patch = client.request("PATCH", f"/api/Projects/{args.id}/toggle-activation")
    active = _read_active(client, args.id)
    out = {"toggled": bool(before is not None and active is not None and before != active),
           "id": args.id, "active": active, "active_before": before, "patch_result": patch}
    if active is None:
        out["toggled"] = None
        out["warning"] = (
            "could not confirm activation from the list-processes projection; the PATCH "
            "response is NOT a reliable signal (it reports success either way) — verify "
            "in the designer or re-run list-processes and read `active`.")
    elif before == active:
        out["warning"] = (
            f"the endpoint answered success but `active` is still {active}. Measured "
            "behaviour: this endpoint only ever sets active to FALSE - it deactivates, and "
            "never activates, whatever its name says. To activate, PUT the process with "
            "active=true. See PROCESIO-API-NOTES.md.")
    return out


ACTIONS = {
    # -- get by id (parity with get-process) --
    "form-get": _get_action("/api/FormTemplate/{id}", "form template id"),
    "document-get": _get_action("/api/DocumentTemplate/{id}", "document template id"),
    "webhook-get": _get_action("/api/Webhooks/{id}", "webhook id"),
    "credential-get": _get_action("/api/Credentials/{id}", "credential id"),
    # -- delete by id (teardown parity) --
    "process-delete": _delete_action("/api/Projects/{id}", "process (project) id"),
    "form-delete": _delete_action("/api/FormTemplate/{id}", "form template id"),
    "document-delete": _delete_action("/api/DocumentTemplate/{id}", "document template id"),
    "webhook-delete": _delete_action("/api/Webhooks/{id}", "webhook id"),
    "credential-delete": _delete_action("/api/Credentials/{id}", "credential id"),
    # -- list (parity with list-processes / list-datatypes) --
    "form-list": _list_action("/api/FormTemplate/all/basic", "List forms (GET /api/FormTemplate/all/basic)."),
    "document-list": _list_action("/api/DocumentTemplate", "List documents (GET /api/DocumentTemplate)."),
    # -- duplicate / activation --
    "form-duplicate": _post_by_id_action("/api/FormTemplate/{id}/duplicate", "form template id", "duplicated"),
    "process-toggle-activation": ActionDef(
        func=toggle_activation,
        add_args=lambda p: _id_args(p, "process (project) id"), needs_client=True,
        description="DEACTIVATE a process (PATCH /api/Projects/{id}/toggle-activation). Despite "
                    "the name it is not a toggle: measured, it only ever sets `active` to FALSE, "
                    "and answers success either way - including when it changed nothing. To "
                    "ACTIVATE, PUT the process with active=true. This action reads `active` "
                    "before and after, reports `toggled` from that comparison rather than from "
                    "the echo, and warns when nothing changed."),
    # -- verification oracles --
    "process-validate": ActionDef(
        func=validate_process, add_args=lambda p: _id_args(p, "process (project) id"), needs_client=True,
        description="Validate a process with PROCESIO's own validator (POST /api/Projects/validate)."),
    "credential-test": ActionDef(
        func=credential_test, add_args=_cred_test_args, needs_client=True,
        description="Live-test a credential config without saving it (POST /api/Credentials/test)."),
    "customaction-test": ActionDef(
        func=customaction_test, add_args=_ca_test_args, needs_client=True,
        description="Test a custom action (POST /api/Actions/test)."),
    "webhook-launch": ActionDef(
        func=webhook_launch, add_args=_launch_args, needs_client=True,
        description="Fire a webhook-triggered process with a payload (POST /api/Webhooks/launch/{id})."),
    "import": ActionDef(
        func=import_bundle, add_args=_import_args, needs_client=True,
        description="Import components from a .procesio bundle (POST /api/Transport/import); mirrors export."),
}
