"""Download a flow-instance file (e.g. a Generate-Document PDF output) to local disk.

`GET /api/File/download` identifies the file by request **HEADERS** (HAR-verified),
NOT query params — a query-only call returns NRE "Object reference not set":

  uploadFilePath  the file DTO `path`
                  (flow/flow-<flowId>/flow-instance-<instanceId>/variable-<varId>/<fileId>)
  variableId      the output variable id
  instanceId      the flow instance id
  flowTemplateId  the process (flow template) id
  workspaceId     the workspace

Query: `?isArchived=false`. Returns raw bytes (`content-disposition: attachment`).
See `tools/procesio/PROCESIO-API-NOTES.md`. JSON in / JSON out; impure (live client).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg

# flow/flow-<flowId>/flow-instance-<instanceId>/variable-<varId>/<fileId>
_PATH_RE = re.compile(
    r"flow-(?P<flow>[0-9a-fA-F-]{36})/"
    r"flow-instance-(?P<instance>[0-9a-fA-F-]{36})/"
    r"variable-(?P<variable>[0-9a-fA-F-]{36})/")


def _ids_from_path(path: str) -> dict:
    m = _PATH_RE.search(path or "")
    return {"flow": m.group("flow"), "instance": m.group("instance"),
            "variable": m.group("variable")} if m else {}


def _filename_from_disposition(cd: str) -> str | None:
    if not cd:
        return None
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd)          # RFC 5987 form wins
    if m:
        return unquote(m.group(1)).strip().strip('"')
    m = re.search(r'filename="?([^";]+)"?', cd)
    return m.group(1).strip() if m else None


def file_download(client, args) -> dict:
    """Download one flow-instance file. Identify it either explicitly
    (--file-path + --variable-id + --instance-id + --flow-template-id) or with
    --from-run pointing at a run-process result JSON (the ids are derived from the
    file DTO's `path` and the result's instanceId)."""
    file_path = args.file_path
    variable_id = args.variable_id
    instance_id = args.instance_id
    flow_template_id = args.flow_template_id
    name = None

    if args.from_run:
        try:
            data = json.loads(Path(args.from_run).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise UsageError(f"--from-run: cannot read JSON ({e})") from e
        res = data.get("result", data) if isinstance(data, dict) else {}
        variables = res.get("variable") or {}
        if args.var:
            picked = variables.get(args.var)
            if not isinstance(picked, dict) or not picked.get("path"):
                raise UsageError(f"--from-run: variable {args.var!r} is not a file in the run result")
        else:
            picked = next((v for v in variables.values()
                           if isinstance(v, dict) and v.get("path")), None)
            if picked is None:
                raise UsageError("--from-run: no file variable (with a 'path') found in the run result")
        ids = _ids_from_path(picked.get("path") or "")
        file_path = file_path or picked.get("path")
        name = picked.get("name")
        flow_template_id = flow_template_id or ids.get("flow")
        instance_id = instance_id or res.get("instanceId") or ids.get("instance")
        variable_id = variable_id or ids.get("variable")

    missing = [n for n, v in (("file-path", file_path), ("variable-id", variable_id),
                              ("instance-id", instance_id), ("flow-template-id", flow_template_id))
               if not v]
    if missing:
        raise UsageError("missing " + ", ".join("--" + m for m in missing)
                         + " (or pass --from-run with a run-process result JSON)")

    workspace_id = client.workspace_id or args.workspace_id
    if not workspace_id:
        raise UsageError("a workspace id is required: pass --workspace-id")

    headers = {"uploadFilePath": file_path, "variableId": variable_id,
               "instanceId": instance_id, "flowTemplateId": flow_template_id,
               "workspaceId": workspace_id}
    status, content, resp_headers = client.request_bytes(
        "GET", "/api/File/download",
        query={"isArchived": "true" if args.is_archived else "false"},
        headers=headers)
    if not (200 <= status < 300):
        body = content[:300].decode("utf-8", "replace") if content else ""
        raise ProcesioAPIError(int(status or 0), f"HTTP {status} downloading file", {"body": body})

    rh = {str(k).lower(): v for k, v in (resp_headers or {}).items()}
    out_name = (_filename_from_disposition(rh.get("content-disposition", "")) or name
                or (file_path.rsplit("/", 1)[-1] if file_path else "download.bin"))
    out = Path(args.out) if args.out else Path.cwd() / out_name
    if out.is_dir():
        out = out / out_name
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)
    return {"downloaded": True, "path": str(out), "size": len(content),
            "mimeType": rh.get("content-type"), "name": out.name}


def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--from-run", dest="from_run",
                   help="path to a run-process result JSON; derive the file + ids from it")
    p.add_argument("--var", help="with --from-run: the output variable name to download "
                                 "(default: the first file variable)")
    p.add_argument("--file-path", dest="file_path",
                   help="the file DTO 'path' (flow/flow-<id>/flow-instance-<id>/variable-<id>/<fileId>)")
    p.add_argument("--variable-id", dest="variable_id", help="output variable id")
    p.add_argument("--instance-id", dest="instance_id", help="flow instance id")
    p.add_argument("--flow-template-id", dest="flow_template_id", help="process (flow template) id")
    p.add_argument("--out", help="output file path or directory (default: the filename in the cwd)")
    p.add_argument("--is-archived", dest="is_archived", action="store_true",
                   help="fetch from archived storage")


ACTIONS = {
    "file-download": ActionDef(
        func=file_download, add_args=_args, needs_client=True,
        description="Download a flow-instance file (Generate-Document output etc.) "
                    "via the header-based GET /api/File/download."),
}
