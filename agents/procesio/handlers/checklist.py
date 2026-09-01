"""checklist action - emit the self-test checklist as structured steps. The single
source `verify` runs and any session follows, so a test layer cannot be skipped
by forgetting it exists.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef
from agents.procesio import checklist as cl


def _checklist(args) -> dict:
    steps = cl.steps(phase=args.phase, automatable_only=args.automatable_only)
    return {
        "phases": cl.PHASES,
        "count": len(steps),
        "steps": steps,
        "manual_steps": [s["id"] for s in cl.manual_steps()],
    }


def _args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--phase", help="filter to one phase: " + " | ".join(cl.PHASES))
    p.add_argument("--automatable-only", dest="automatable_only",
                   action="store_true", help="only steps `verify` can run")


ACTIONS = {
    "checklist": ActionDef(
        func=_checklist, add_args=_args,
        description="Emit the rigorous self-test checklist (structured). "
                    "--phase to filter, --automatable-only for verify-runnable steps."),
}
