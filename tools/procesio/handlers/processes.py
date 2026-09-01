"""Curated process + instance actions (the heart of PROCESIO automation).

Paths are the exact Web-API v1.19 routes (tag ProcessTemplate/ProcessInstance):
  list      GET    /api/Projects
  get       GET    /api/Projects/{id}
  payload   GET    /api/Projects/{id}/payload
  run       POST   /api/Projects/{id}/run
  instances GET    /api/Projects/{id}/instances
  status    GET    /api/Projects/instances/{id}/status
  output    GET    /api/Projects/instances/{id}/output
  stop      POST   /api/Projects/instances/{id}/stop
"""
from __future__ import annotations

import argparse

from tools._lib.io import log
from tools.procesio import reliability
from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_paging_args, add_profile_arg


# -- list / get -------------------------------------------------------------

def _list_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    add_paging_args(p)
    p.add_argument("--search", help="filter by process name (searchName)")


def list_processes(client, args) -> dict:
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "searchName": args.search}
    return {"result": client.get("/api/Projects", q)}


def _id_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")


def get_process(client, args) -> dict:
    return {"result": client.get(f"/api/Projects/{args.id}")}


def get_process_payload(client, args) -> dict:
    """The input-variable shape expected by run-process for this process."""
    return {"result": client.get(f"/api/Projects/{args.id}/payload")}


# -- run --------------------------------------------------------------------

def _run_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id to run")
    p.add_argument("--payload", help="input variables as a JSON object")
    p.add_argument("--connection-id", dest="connection_id",
                   help="connectionid value (default null)")
    p.add_argument("--synchronous", action="store_true",
                   help="wait for completion (runSynchronous=true)")
    p.add_argument("--timeout", type=int, help="secondsTimeOut for synchronous runs")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="show the request that WOULD be sent; do not run")


def run_process(client, args) -> dict:
    payload = parse_json_arg(args.payload, "payload") or {}
    body = {"payload": payload, "connectionid": args.connection_id}
    query = {"runSynchronous": "true" if args.synchronous else None,
             "secondsTimeOut": args.timeout}
    query = {k: v for k, v in query.items() if v is not None}
    if args.dry_run:
        return {"dry_run": True, "method": "POST",
                "path": f"/api/Projects/{args.id}/run", "query": query, "body": body}
    # An execution is EXEMPT from the client's total wall-clock deadline: a
    # synchronous run of a many-action process legitimately takes minutes, and
    # aborting it client-side does NOT stop the server run (it keeps executing and
    # writing its side effects). Instead give the socket a per-read timeout matched
    # to the requested --timeout (+buffer), or no read timeout at all when a
    # synchronous run has no --timeout (wait for it). See PROCESIO-API-NOTES.md.
    read_timeout = reliability.READ_TIMEOUT
    if args.synchronous:
        read_timeout = (args.timeout + 30) if args.timeout else None
    return {"result": client.post(f"/api/Projects/{args.id}/run", body, query,
                                  deadline=None, read_timeout=read_timeout)}


# -- run with FILE inputs ---------------------------------------------------
#
# The one-call /run endpoint cannot carry file bytes: its body is JSON, and a File
# process variable expects a materialised file behind a fileId. So a run with a file
# input is a four-step sequence against three endpoints (verified live 2026-07-03,
# and again 10/08/2026):
#
#   publish  POST /api/Projects/{id}/instances/publish   file var = METADATA only,
#                                                        carrying a client-made GUID
#   upload   POST /api/File/upload/flow                  bytes in multipart 'package',
#                                                        ids in HEADERS (variableNAME)
#   launch   POST /api/Projects/instances/{iid}/launch
#   poll     GET  /api/Projects/instances/{iid}/status -> /output
#
# Publishing WITHOUT launching leaves a zombie instance in "starting", so the launch
# leg is not optional once publish has run.

_STATUS_LABELS = {1: "starting", 5: "inactive", 6: "stopped_by_user",
                  15: "initializing", 30: "running",
                  40: "finished_with_errors", 50: "finished"}
_TERMINAL_STATUSES = {6, 40, 50}


def _parse_file_bindings(raw: "list[str] | None") -> "dict[str, str]":
    """`--file VARNAME=PATH` (repeatable) -> {variable name: local path}."""
    out: "dict[str, str]" = {}
    for item in raw or []:
        name, sep, path = (item or "").partition("=")
        if not sep or not name.strip() or not path.strip():
            raise UsageError(f"--file expects VARNAME=PATH, got {item!r}")
        out[name.strip()] = path.strip()
    return out


def _instance_id_from_publish(published) -> str:
    """The publish response carries the new instance id at the TOP level as `id`;
    older shapes nested it under `flows`. Try both before giving up."""
    if isinstance(published, dict):
        for key in ("id", "instanceId", "instanceID"):
            if published.get(key):
                return str(published[key])
        flows = published.get("flows")
        if isinstance(flows, list) and flows and isinstance(flows[0], dict):
            for key in ("id", "instanceId"):
                if flows[0].get(key):
                    return str(flows[0][key])
    raise ProcesioAPIError(0, "could not find the instance id in the publish response",
                           {"response": published})


def _run_with_files_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id to run")
    p.add_argument("--file", action="append", metavar="VARNAME=PATH",
                   help="bind a local file to a File input variable; repeatable")
    p.add_argument("--payload", help="the NON-file input variables as a JSON object")
    p.add_argument("--timeout", type=int, default=300,
                   help="seconds to wait for a terminal status (default 300)")
    p.add_argument("--poll-interval", dest="poll_interval", type=float, default=3.0,
                   help="seconds between status polls (default 3)")
    p.add_argument("--no-wait", dest="no_wait", action="store_true",
                   help="launch and return the instance id without polling")


def run_process_with_files(client, args) -> dict:
    """Run a process that takes one or more File input variables."""
    import mimetypes
    import os
    import time
    import uuid

    bindings = _parse_file_bindings(args.file)
    if not bindings:
        raise UsageError("run-process-with-file needs at least one --file VARNAME=PATH "
                         "(a run with no file input is just run-process)")

    payload = parse_json_arg(args.payload, "payload") or {}
    staged = []
    for var_name, path in bindings.items():
        if not os.path.isfile(path):
            raise UsageError(f"--file {var_name}: no such file: {path}")
        name = os.path.basename(path)
        size = os.path.getsize(path)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        file_id = str(uuid.uuid4())
        # The publish payload carries METADATA ONLY; the bytes follow in step 2.
        payload[var_name] = {"path": "", "size": size, "mimeType": mime,
                             "name": name, "id": file_id, "hash": ""}
        staged.append({"var": var_name, "path": path, "name": name,
                       "size": size, "mime": mime, "file_id": file_id})

    published = client.post(f"/api/Projects/{args.id}/instances/publish", payload)
    instance_id = _instance_id_from_publish(published)
    log(f"published instance {instance_id}")

    for f in staged:
        with open(f["path"], "rb") as fh:
            content = fh.read()
        client.request_multipart(
            "/api/File/upload/flow",
            files={"package": (f["name"], content, f["mime"])},
            headers={"flowInstanceId": instance_id, "flowTemplateId": args.id,
                     "variableName": f["var"], "fileId": f["file_id"]})
        log(f"uploaded {f['name']} ({f['size']} bytes) -> {f['var']}")

    client.post(f"/api/Projects/instances/{instance_id}/launch",
                {"flowTemplateId": args.id, "connectionId": None})
    log("launched")

    result = {"instance_id": instance_id,
              "files": [{"variable": f["var"], "name": f["name"], "size": f["size"]}
                        for f in staged]}
    if args.no_wait:
        return {"result": {**result, "status": None, "status_label": "launched"}}

    deadline = time.monotonic() + args.timeout
    status_val = None
    while True:
        st = client.get(f"/api/Projects/instances/{instance_id}/status",
                        {"flowTemplateId": args.id})
        inst = st.get("instance") if isinstance(st, dict) else None
        status_val = (inst or st or {}).get("status")
        if status_val in _TERMINAL_STATUSES:
            break
        if time.monotonic() > deadline:
            raise ProcesioAPIError(
                0, f"instance {instance_id} did not reach a terminal status within "
                   f"{args.timeout}s; read it later with get-instance-output",
                {"instance_id": instance_id, "last_status": status_val})
        time.sleep(args.poll_interval)

    output = client.get(f"/api/Projects/instances/{instance_id}/output",
                        {"flowTemplateId": args.id})
    inst = output.get("instance") if isinstance(output, dict) else None
    return {"result": {**result,
                       "status": status_val,
                       "status_label": _STATUS_LABELS.get(status_val, str(status_val)),
                       "variable": (inst or {}).get("variable"),
                       "error": (inst or {}).get("error"),
                       "output": output}}


# -- instances --------------------------------------------------------------

def _instances_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    add_paging_args(p)
    p.add_argument("--status", dest="filter_status", help="filterStatus value")


def list_instances(client, args) -> dict:
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "filterStatus": args.filter_status}
    return {"result": client.get(f"/api/Projects/{args.id}/instances", q)}


def _instance_status_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="instance id")
    p.add_argument("--flow-template-id", dest="flow_template_id",
                   help="flowTemplateId (the process id)")
    p.add_argument("--variables", action="store_true",
                   help="include variables (getVariables=true)")
    p.add_argument("--actions", action="store_true",
                   help="include actions (getActions=true)")


def get_instance_status(client, args) -> dict:
    q = {"flowTemplateId": args.flow_template_id,
         "getVariables": "true" if args.variables else None,
         "getActions": "true" if args.actions else None}
    return {"result": client.get(f"/api/Projects/instances/{args.id}/status", q)}


def _instance_id_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="instance id")
    p.add_argument("--flow-template-id", dest="flow_template_id",
                   help="flowTemplateId (the process id)")


def get_instance_output(client, args) -> dict:
    q = {"flowTemplateId": args.flow_template_id}
    return {"result": client.get(f"/api/Projects/instances/{args.id}/output", q)}


def stop_instance(client, args) -> dict:
    q = {"flowTemplateId": args.flow_template_id}
    return {"result": client.post(f"/api/Projects/instances/{args.id}/stop", None, q)}


# -- put-projects (curated: empty-body echo hardening) ----------------------

_EMPTY_PUT_WARNING = (
    "PUT /api/Projects returned a SUCCESS status with an EMPTY body. An empty-body "
    "success has been observed to LIE: the response looked fine while the change did "
    "NOT land server-side (see PROCESIO-API-NOTES.md 'Empirical reliability profile', "
    "O4). Do NOT trust this echo — verify behaviourally: run the process "
    "(run-process) and observe the effect, or re-read the definition and compare."
)


def _put_projects_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--body", help="request body as JSON (object or array)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="compose and return the request without sending it")


def _is_empty_echo(parsed) -> bool:
    """The PROCESIO empty-body shape: no JSON body -> _parse_body returns
    {"raw_text": ""}; also treat {} / None as empty."""
    if parsed is None or parsed == {}:
        return True
    if isinstance(parsed, dict) and set(parsed) <= {"raw_text"}:
        return not parsed.get("raw_text")
    return False


def put_projects(client, args) -> dict:
    """Curated PUT /api/Projects: same passthrough as the generated action, but it
    reports the HTTP status/elapsed/body-length and WARNS when the body is empty,
    because an empty-body success can silently fail to persist (O4). Shadows the
    autogenerated put-projects (curated names win in main.collect_actions)."""
    body = parse_json_arg(args.body, "body")
    if args.dry_run:
        return {"dry_run": True, "method": "PUT", "path": "/api/Projects", "body": body}
    result = client.put("/api/Projects", body)
    meta = client.last_meta or {}
    out = {
        "result": result,
        "http": {"status": meta.get("status"),
                 "elapsed_s": meta.get("elapsed_s"),
                 "body_len": meta.get("body_len")},
    }
    if _is_empty_echo(result) or meta.get("body_len") == 0:
        out["warning"] = _EMPTY_PUT_WARNING
    return out


ACTIONS = {
    "list-processes": ActionDef(
        func=list_processes, add_args=_list_args, needs_client=True,
        description="List processes (GET /api/Projects).",
    ),
    "get-process": ActionDef(
        func=get_process, add_args=_id_args, needs_client=True,
        description="Get one process by id (GET /api/Projects/{id}).",
    ),
    "get-process-payload": ActionDef(
        func=get_process_payload, add_args=_id_args, needs_client=True,
        description="Get a process's input-variable payload shape for run-process.",
    ),
    "run-process": ActionDef(
        func=run_process, add_args=_run_args, needs_client=True,
        description="Run a process (POST /api/Projects/{id}/run). Supports --dry-run.",
    ),
    "run-process-with-file": ActionDef(
        func=run_process_with_files, add_args=_run_with_files_args, needs_client=True,
        description="Run a process that takes File input variable(s): publish -> upload "
                    "bytes -> launch -> poll -> output. --file VARNAME=PATH (repeatable).",
    ),
    "list-instances": ActionDef(
        func=list_instances, add_args=_instances_args, needs_client=True,
        description="List a process's run instances (GET /api/Projects/{id}/instances).",
    ),
    "get-instance-status": ActionDef(
        func=get_instance_status, add_args=_instance_status_args, needs_client=True,
        description="Get an instance's status/variables (GET /api/Projects/instances/{id}/status).",
    ),
    "get-instance-output": ActionDef(
        func=get_instance_output, add_args=_instance_id_args, needs_client=True,
        description="Get an instance's output (GET /api/Projects/instances/{id}/output).",
    ),
    "stop-instance": ActionDef(
        func=stop_instance, add_args=_instance_id_args, needs_client=True,
        description="Stop a running instance (POST /api/Projects/instances/{id}/stop).",
    ),
    "put-projects": ActionDef(
        func=put_projects, add_args=_put_projects_args, needs_client=True,
        description="Update a process (PUT /api/Projects). Reports HTTP status/elapsed "
                    "and WARNS on an empty-body success (which can silently not persist).",
    ),
}
