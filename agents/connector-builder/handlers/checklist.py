"""checklist action — emit the end-to-end build → upload → test → improve
checklist as structured steps, so a session can execute the loop deterministically.

Pure (no live calls); optionally stamps a --goal into the first step's note.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef

_STEPS = [
    {"phase": "scope", "tool": "connector-builder", "action": "create-build",
     "do": "Create the build from the API docs URL(s) or pasted text + clear user-requirements.",
     "command": "create-build --api-url <docs> --user-requirements '...'"},
    {"phase": "gather", "tool": "connector-builder", "action": "gather",
     "do": "Run GATHER+CLARIFY; read the api_profile and clarification_questions.",
     "command": "gather --build-id <ID>"},
    {"phase": "clarify", "tool": "connector-builder", "action": "answer",
     "do": "Answer every clarification question (keys = question ids). Triggers PLAN.",
     "command": "answer --build-id <ID> --answers '{...}'"},
    {"phase": "plan", "tool": "connector-builder", "action": "approve-plan / revise-plan",
     "do": "Review the implementation plan. revise-plan until right, then approve-plan.",
     "command": "revise-plan --feedback '...'  |  approve-plan --build-id <ID>"},
    {"phase": "generate", "tool": "connector-builder", "action": "approve-generate / regenerate-file",
     "do": "Review generated files; regenerate any wrong file; then approve-generate.",
     "command": "regenerate-file --filename X.cs --instructions '...'  |  approve-generate"},
    {"phase": "validate+compile", "tool": "connector-builder", "action": "validate-* / retry",
     "do": "Clear validation findings; let it compile. On compile failure, retry --from-step 6.",
     "command": "validate-continue  |  retry --from-step 6"},
    {"phase": "deliver", "tool": "connector-builder", "action": "download-artifact",
     "do": "Download the compiled .nupkg.",
     "command": "download-artifact --build-id <ID> --out connector.nupkg"},
    {"phase": "install", "tool": "procesio", "action": "customaction-upload",
     "do": "Install the connector into the PROCESIO workspace.",
     "command": "procesio customaction-upload --file connector.nupkg"},
    {"phase": "test", "tool": "procesio (agent)", "action": "verify",
     "do": "Exercise the action in a real process (inputs/outputs, errors) per the procesio build-and-test playbook.",
     "command": "run-agent.py procesio verify --process-id <ID>"},
    {"phase": "improve", "tool": "connector-builder", "action": "revise-plan / regenerate-file / knowledge-update",
     "do": "Feed PROCESIO failures back: fix the plan/code for this connector; for systemic generation issues edit the builder's knowledge (prompt/spec_module/example) then reload-config. Re-compile and re-upload.",
     "command": "regenerate-file ...  |  knowledge-update --module-type spec_module ...; reload-config"},
    {"phase": "cleanup", "tool": "procesio", "action": "customaction-delete",
     "do": "Before re-uploading a new build of the same connector, uninstall the old one.",
     "command": "procesio customaction-delete --id <actionId>"},
]


def _checklist(args) -> dict:
    steps = [dict(s, n=i + 1) for i, s in enumerate(_STEPS)]
    out = {
        "title": "Connector build → PROCESIO test → improve loop",
        "loop": "Steps 8-11 repeat until the action passes its PROCESIO tests.",
        "steps": steps,
    }
    if args.goal:
        out["goal"] = args.goal
        steps[0]["note"] = f"Goal: {args.goal}"
    return out


def _checklist_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--goal", help="Optional one-line connector goal to stamp in")


ACTIONS = {
    "checklist": ActionDef(
        func=_checklist, add_args=_checklist_args,
        description="Emit the end-to-end build→upload→test→improve checklist.",
    ),
}
