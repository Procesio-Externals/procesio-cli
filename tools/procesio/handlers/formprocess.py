"""Run a process THROUGH A FORM, the way a browser submission does.

Why this exists (and why it is not the same as `run-process-with-file`): a form and the
process behind it are assembled separately, and nothing in the process API asserts that the
two agree. A form whose submit button is wired to nothing, or whose input reaches the engine
but is never consumed, passes every process-side assertion ever written. Both defects have
shipped. Exercising the FORM surface is what catches them.

The FormProcess controller is the public front-end route (anonymous, scoped entirely by the
`formTemplateWorkspaceId` header). The sequence mirrors the process side:

    publish (metadata only) -> upload each file (multipart) -> launch -> read variables

Two mechanics the generated `<method>-<path>` actions cannot reach, which is why this is a
curated handler: every call needs the `formTemplateWorkspaceId` header, and the file upload
is `multipart/form-data` with the field name `package`.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
import uuid

from tools._lib.io import log
from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg

_TERMINAL = {6, 40, 50}
_LABEL = {1: "starting", 6: "stopped", 40: "finished_with_errors", 50: "finished"}


def _json_call(client, method, path, *, query=None, body=None, headers=None):
    """A JSON request that can carry extra headers. client.request() cannot, and these
    endpoints are addressed by header, so everything here goes through request_bytes."""
    status, raw, _ = client.request_bytes(method, path, query=query, body=body, headers=headers)
    text = (raw or b"").decode("utf-8", "replace").strip()
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text
    if 200 <= status < 300:
        return parsed
    raise ProcesioAPIError(status, f"HTTP {status}",
                           parsed if isinstance(parsed, dict) else {"body": parsed})


def _instance_id(resp):
    """The published instance id, wherever this manager-defined shape puts it."""
    if isinstance(resp, str) and resp.count("-") == 4:
        return resp
    if isinstance(resp, dict):
        for k in ("id", "instanceId", "instanceID", "flowInstanceId"):
            v = resp.get(k)
            if isinstance(v, str) and v:
                return v
        flows = resp.get("flows")
        if isinstance(flows, list) and flows and isinstance(flows[0], dict):
            v = flows[0].get("id")
            if v:
                return v
        for key in ("result", "value", "data", "instance"):
            inner = resp.get(key)
            if isinstance(inner, (dict, str)):
                got = _instance_id(inner)
                if got:
                    return got
    return None


def run_form_with_files(client, args) -> dict:
    form_id = args.form_id
    process_id = args.process_id
    ws = args.workspace_id or (client.profile or {}).get("workspace_id")
    if not ws:
        raise UsageError("--workspace-id is required: FormProcess is scoped by the "
                         "formTemplateWorkspaceId header")
    hdr = {"formTemplateWorkspaceId": ws}

    payload = parse_json_arg(args.payload, "--payload") if args.payload else {}
    if not isinstance(payload, dict):
        raise UsageError("--payload must be a JSON object")

    # File inputs are staged as METADATA ONLY at publish; the bytes follow per file.
    staged = []
    for spec in (args.file or []):
        if "=" not in spec:
            raise UsageError(f"--file must be VARNAME=PATH, got {spec!r}")
        var, path = spec.split("=", 1)
        var, path = var.strip(), path.strip()
        if not os.path.isfile(path):
            raise UsageError(f"file not found for {var}: {path}")
        size = os.path.getsize(path)
        name = os.path.basename(path)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        fid = str(uuid.uuid4())
        staged.append({"var": var, "path": path, "name": name, "size": size,
                       "mime": mime, "file_id": fid})
        payload[var] = {"path": "", "size": size, "mimeType": mime,
                        "name": name, "id": fid, "hash": ""}

    log(f"publishing through form {form_id}")
    pub = _json_call(client, "POST",
                     f"/api/FormProcess/{form_id}/{process_id}/publish",
                     body=payload, headers=hdr)
    inst = _instance_id(pub)
    if not inst:
        raise ProcesioAPIError(0, "form publish returned no instance id",
                               {"response": pub})
    log(f"instance {inst}")

    for f in staged:
        with open(f["path"], "rb") as fh:
            content = fh.read()
        client.request_multipart(
            f"/api/FormProcess/{form_id}/{inst}/upload",
            files={"package": (f["name"], content, f["mime"])},
            headers={"flowTemplateId": process_id, "variableName": f["var"],
                     "fileId": f["file_id"], "formTemplateWorkspaceId": ws})
        log(f"uploaded {f['name']} ({f['size']} bytes) -> {f['var']}")

    # The launch route's second path segment is documented as processTemplateId, but the
    # body already carries flowTemplateId, so on the process side that slot is the INSTANCE.
    # Try the instance first and fall back, rather than guessing which the platform means.
    body = {"connectionId": None, "flowTemplateId": process_id}
    query = {"runSynchronous": "true" if args.synchronous else "false",
             "secondsTimeOut": args.timeout}
    launched, used = None, None
    for seg in (inst, process_id):
        try:
            launched = _json_call(client, "POST",
                                  f"/api/FormProcess/{form_id}/{seg}/launch",
                                  query=query, body=body, headers=hdr)
            used = seg
            break
        except ProcesioAPIError as e:
            if seg == process_id:
                raise
            log(f"launch with instance in path failed ({e}); retrying with template")
    log(f"launched (path segment used: {'instance' if used == inst else 'template'})")

    variables, status = None, None
    deadline = time.time() + max(int(args.timeout or 60), 5)
    while time.time() < deadline:
        try:
            variables = _json_call(
                client, "GET",
                f"/api/FormProcess/{form_id}/{process_id}/{inst}/variables",
                headers=hdr)
        except ProcesioAPIError:
            variables = None
        status = None
        if isinstance(variables, dict):
            for k in ("status", "instanceStatus"):
                if isinstance(variables.get(k), int):
                    status = variables[k]
            inner = variables.get("instance")
            if isinstance(inner, dict) and isinstance(inner.get("status"), int):
                status = inner["status"]
        if status in _TERMINAL or not args.synchronous:
            break
        time.sleep(3)

    # The variables endpoint returns flow-variable DEFINITIONS and carries the runtime value
    # in `defaultValue`, not `value`. Flatten to {name: value} so callers cannot misread an
    # empty `value` key as "the form produced nothing" -- which is exactly the false negative
    # this action exists to prevent.
    flat = {}
    if isinstance(variables, dict):
        for item in (variables.get("variables") or []):
            if isinstance(item, dict) and item.get("name"):
                flat[item["name"]] = item.get("defaultValue")

    return {"form_id": form_id, "process_id": process_id, "instance_id": inst,
            "launch_path_segment": "instance" if used == inst else "template",
            "files": [{"variable": f["var"], "name": f["name"], "size": f["size"]}
                      for f in staged],
            "status": status, "status_label": _LABEL.get(status, str(status)),
            "variable": flat, "variables": variables, "launch": launched}


def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--form-id", dest="form_id", required=True, help="form template id")
    p.add_argument("--process-id", dest="process_id", required=True,
                   help="process (flow template) id the form submits to")
    p.add_argument("--file", action="append",
                   help="VARNAME=PATH for a File input variable (repeatable)")
    p.add_argument("--payload", help="non-file input variables as a JSON object")
    p.add_argument("--synchronous", action="store_true", default=True,
                   help="wait for the flow to finish (default)")
    p.add_argument("--no-synchronous", dest="synchronous", action="store_false",
                   help="fire and forget")
    p.add_argument("--timeout", type=int, default=120,
                   help="synchronous wait, seconds (default 120)")


ACTIONS = {
    "run-form-with-files": ActionDef(
        func=run_form_with_files, add_args=_args, needs_client=True,
        description="Submit a form the way a browser does: publish -> upload files -> "
                    "launch -> read variables, through the public FormProcess endpoints. "
                    "Proves the form's own input/output maps carry values.",
    ),
}
