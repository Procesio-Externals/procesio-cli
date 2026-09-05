"""The `verify` gate: run the automatable self-test steps against a live process.

Turns the playbook checklist from prose into an executable gate. It drives the
`procesio` tool (never the API directly) and is defensive: a tool error or an
unexpected response shape downgrades a check to `skip` with the reason, so the
gate reports the truth instead of crashing or lying. Manual steps it cannot run
are returned in `manual_checks` so they cannot be silently skipped.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from agents._lib.toolrunner import ToolError
from agents.procesio import audit, checklist


def scope_args(profile: str | None, workspace_id: str | None = None) -> list[str]:
    """The credential-scope flags that EVERY inner `procesio` call must forward.

    Forwarding `--profile` alone is not enough: a session is bound to one default
    workspace, so a resource living in any other workspace answers HTTP 400
    `{"statusCode": 501, "value": "User is not authorized for the requested
    resource."}` unless the `workspaceid` header is set per call, which is what
    `--workspace-id` does. Only an api-key profile can carry a workspace of its
    own, so for a user/password profile there is no fallback - the flag is the
    only way to reach another workspace. Build the flags here and splat them into
    every invoke, so a new inner call cannot forget one.
    """
    args: list[str] = []
    if profile:
        args += ["--profile", profile]
    if workspace_id:
        args += ["--workspace-id", workspace_id]
    return args


def _flow_from(data: dict) -> dict:
    """Unwrap get-process. Live API and tests both nest the flow under result.flow
    (camelCase live, but ci() is case-insensitive)."""
    res = data.get("result") if isinstance(data, dict) else None
    if isinstance(res, dict):
        f = audit.ci(res, "flow")
        return f if isinstance(f, dict) else res
    return data if isinstance(data, dict) else {}


def _check(cid: str, phase: str, status: str, detail: Any) -> dict:
    return {"id": cid, "phase": phase, "status": status, "detail": detail}


def _instance_ids(res: dict) -> tuple[str | None, Any]:
    if not isinstance(res, dict):
        return None, None
    inst = audit.ci(res, "instance")
    inst = inst if isinstance(inst, dict) else res
    iid = audit.ci(inst, "id", "instanceId", "flowInstanceId") or \
        audit.ci(res, "instanceId", "id")
    status = audit.ci(inst, "status")
    if status is None:
        status = audit.ci(res, "status")
    return (str(iid) if iid else None), status


def _validation_messages(details: dict):
    """PROCESIO's /api/Projects/validate returns HTTP 400 with a list of
    {statusCode, value, target} when a process is invalid (the tool surfaces that
    as an error envelope). Return that list (possibly empty = valid) for a real
    validation response, or None when this is not one (e.g. a 500 / wrong shape)."""
    if not isinstance(details, dict) or details.get("status") != 400:
        return None
    body = details.get("body")
    inner = body.get("body") if isinstance(body, dict) else body
    return inner if isinstance(inner, list) else None


def _action_errors(status_res: dict) -> list[dict]:
    inst = audit.ci(status_res, "instance")
    inst = inst if isinstance(inst, dict) else status_res
    actions = audit.ci(inst, "actions")
    out = []
    for a in actions or []:
        if isinstance(a, dict) and audit.ci(a, "errorMessage"):
            out.append({"action": audit.ci(a, "actionName", "name"),
                        "errorMessage": audit.ci(a, "errorMessage")})
    return out


def verify_process(invoke: Callable, process_id: str, *, profile: str | None = None,
                   workspace_id: str | None = None,
                   run: bool = False, payload: str | None = None,
                   timeout: int | None = None) -> dict:
    checks: list[dict] = []
    scope = scope_args(profile, workspace_id)

    # 1. fetch -----------------------------------------------------------------
    try:
        flow = _flow_from(invoke("procesio", "get-process", "--id", process_id, *scope))
    except ToolError as e:
        return {"process_id": process_id, "verdict": "fail",
                "checks": [_check("fetch", "validate", "fail",
                                  {"code": e.code, "message": e.message})],
                "manual_checks": checklist.manual_steps()}
    title = audit.ci(flow, "title", "name")
    checks.append(_check("fetch", "validate", "pass", {"title": title}))

    # 2. validate --------------------------------------------------------------
    try:
        vd = invoke("procesio", "request", "--method", "POST",
                    "--path", "/api/Projects/validate",
                    "--body", json.dumps(flow), *scope)
        res = vd.get("result")
        errors = None
        if isinstance(res, dict):
            errors = audit.ci(res, "validationErrors", "errors", "messages")
            valid = audit.ci(res, "isValid", "valid")
        else:
            valid = None
        if errors:
            checks.append(_check("validate-process", "validate", "warn",
                                 {"errors": errors}))
        elif valid is False:
            checks.append(_check("validate-process", "validate", "warn",
                                 {"valid": False, "raw": res}))
        else:
            checks.append(_check("validate-process", "validate", "pass",
                                 {"valid": True if valid else "no errors reported"}))
    except ToolError as e:
        msgs = _validation_messages(e.details)
        if msgs is not None:
            checks.append(_check("validate-process", "validate",
                                 "warn" if msgs else "pass",
                                 {"errors": msgs} if msgs else {"valid": True}))
        else:
            checks.append(_check("validate-process", "validate", "skip",
                                 {"reason": "validate endpoint not callable",
                                  "code": e.code, "message": e.message,
                                  "detail": e.details}))

    # 3. config parity (gating correctness audit) ------------------------------
    cf = audit.correctness_findings(flow)
    blocking = [f for f in cf if f["severity"] in ("warn", "fail")]
    if blocking:
        # a correctness finding marked `fail` (e.g. a Call-API node masquerading as a
        # Data Store/cache op) is a hard defect, not a smell - fail the gate outright.
        hard = any(f["severity"] == "fail" for f in blocking)
        checks.append(_check("config-parity-audit", "validate",
                             "fail" if hard else "warn",
                             {"findings": blocking}))
    else:
        checks.append(_check("config-parity-audit", "validate", "pass",
                             {"findings": cf}))

    # 4. run + instance status -------------------------------------------------
    if run:
        try:
            args = ["run-process", "--id", process_id, "--synchronous"]
            if payload:
                args += ["--payload", payload]
            if timeout:
                args += ["--timeout", str(timeout)]
            rd = invoke("procesio", *args, *scope)
            iid, status_code = _instance_ids(rd.get("result") or {})
            action_errors: list[dict] = []
            if iid:
                try:
                    sd = invoke("procesio", "get-instance-status", "--id", iid,
                                "--flow-template-id", process_id, "--actions", *scope)
                    sres = sd.get("result") or {}
                    s2 = _instance_ids(sres)[1]
                    status_code = s2 if s2 is not None else status_code
                    action_errors = _action_errors(sres)
                except ToolError:
                    pass
            if status_code == 50 and not action_errors:
                checks.append(_check("run-instance", "run", "pass",
                                     {"instance_id": iid, "status": 50}))
            elif status_code == 40 or action_errors:
                checks.append(_check("run-instance", "run", "fail",
                                     {"instance_id": iid, "status": status_code,
                                      "action_errors": action_errors}))
            else:
                checks.append(_check("run-instance", "run", "warn",
                                     {"instance_id": iid, "status": status_code,
                                      "note": "unrecognized status; inspect manually"}))
        except ToolError as e:
            checks.append(_check("run-instance", "run", "fail",
                                 {"code": e.code, "message": e.message}))
    else:
        checks.append(_check("run-instance", "run", "skip",
                             {"reason": "not run; pass --run to execute the process"}))

    # practice findings (non-gating) + verdict ---------------------------------
    full = audit.audit_process(flow)
    practice = [f for f in full["findings"] if f["kind"] == "practice"]
    statuses = [c["status"] for c in checks]
    verdict = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "pass")

    return {
        "process_id": process_id,
        "title": title,
        "verdict": verdict,
        "ran": run,
        "checks": checks,
        "practice_findings": practice,
        "manual_checks": checklist.manual_steps(),
        "summary": full["summary"],
    }
