"""audit action - static best-practice analysis of a process (no run). Surfaces
the inefficiency / UX / robustness smells so they get addressed: action count,
slow actions, missing error handling, missing description, possible inline secret,
plus the designer-vs-runtime parity correctness findings.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef
from agents.procesio import audit as auditlib
from agents.procesio import verifylib


def _audit(ctx, args) -> dict:
    scope = verifylib.scope_args(args.profile, args.workspace_id)
    flow = verifylib._flow_from(
        ctx.invoke("procesio", "get-process", "--id", args.process_id, *scope))
    report = auditlib.audit_process(flow)
    report["process_id"] = args.process_id
    return report


def _args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--process-id", dest="process_id", required=True,
                   help="process (project) id to audit")
    p.add_argument("--profile", help="procesio credential profile to use")
    p.add_argument("--workspace-id", dest="workspace_id",
                   help="workspace GUID the process lives in (required whenever it "
                        "is not the profile's default workspace)")


ACTIONS = {
    "audit": ActionDef(
        func=_audit, context=True, add_args=_args,
        description="Static best-practice + correctness audit of a process "
                    "(action count, slow actions, error handling, inline secrets, "
                    "designer-vs-runtime parity)."),
}
