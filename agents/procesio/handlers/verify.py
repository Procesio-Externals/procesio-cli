"""verify action - run the automatable self-test steps against a live process and
return a pass/fail report. The enforcement gate: it validates, audits config
parity, and (with --run) runs the process and reads the real instance status.
Manual steps it cannot run are listed so they are not silently skipped.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef
from agents.procesio import verifylib


def _verify(ctx, args) -> dict:
    return verifylib.verify_process(
        ctx.invoke, args.process_id, profile=args.profile,
        workspace_id=args.workspace_id,
        run=args.run, payload=args.payload, timeout=args.timeout)


def _args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--process-id", dest="process_id", required=True,
                   help="process (project) id to verify")
    p.add_argument("--run", action="store_true",
                   help="actually run the process and read the instance status")
    p.add_argument("--payload", help="input variables as a JSON object (with --run)")
    p.add_argument("--timeout", type=int, help="secondsTimeOut for the synchronous run")
    p.add_argument("--profile", help="procesio credential profile to use")
    p.add_argument("--workspace-id", dest="workspace_id",
                   help="workspace GUID the process lives in (required whenever it "
                        "is not the profile's default workspace)")


ACTIONS = {
    "verify": ActionDef(
        func=_verify, context=True, add_args=_args,
        description="Run the automatable self-test gate against a process (validate, "
                    "config-parity audit, and with --run execute + read instance status)."),
}
