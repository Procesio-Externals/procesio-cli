"""next-step action — the executable pipeline doctrine.

Given a build's (status, step_status) — passed in, or read LIVE from the
`connector-builder` tool via --build-id — recommend the next tool call(s). This
turns the 8-stage state machine (documentation/04-PIPELINE-ENGINE.md) into a
single "what do I run now?" answer, including the hand-off to PROCESIO once the
connector is built.

Pure heuristic over the state pair; the only live call is the optional get-build
lookup. No secrets of its own.
"""
from __future__ import annotations

import argparse

from agents._lib.actiondef import ActionDef
from agents._lib.errors import AgentError

_T = "connector-builder"  # the tool name, for the suggested commands


def _cmd(action: str, extra: str = "") -> str:
    base = f"python scripts/run-tool.py {_T} {action} --build-id <ID>"
    return f"{base} {extra}".strip()


# Recommendations keyed by overall status. Where step_status matters
# (waiting_user vs running) the value is a dict of step_status -> plan.
_RUNNING = {
    "phase": "running",
    "poll": True,
    "recommended": [{"action": "get-build", "why": "stage is executing; poll until it pauses or finishes",
                     "command": _cmd("get-build")}],
}


def _compile_failure_diagnosis(error_message: str | None) -> dict | None:
    """Triage a COMPILE failure from its error text (the live-run learning).

    NuGet RESTORE failures (NU1301 / can't reach the source/package index) are a
    PLATFORM config problem — the compiler can't pull the PROCESIO SDK from GitHub
    Packages — NOT a code problem, so regenerating is useless. A MISSING VERSION
    (NU1102) IS a code problem: the .csproj pinned a version that doesn't exist,
    fixable with update-file. Real C# errors are code problems the FIX loop or a
    regenerate handles.
    """
    e = (error_message or "").lower()
    if not e:
        return None
    if "nu1301" in e or ("restore" in e and "nuget" in e) or "retrieve information about" in e:
        return {
            "kind": "platform_nuget_restore",
            "not_your_code": True,
            "why": ("NU1301 = the compiler could not reach the package source/index "
                    "(the PROCESIO SDK on GitHub Packages). This is a server-side NuGet "
                    "config issue, NOT the generated code — regenerating will not help."),
            "fix": [
                "python scripts/run-tool.py connector-builder get-config --which compilation   # inspect nuget_sources",
                "MSYS_NO_PATHCONV=1 python scripts/run-tool.py connector-builder api --method POST --path /admin/platform-settings/test-nuget   # validate PAT",
                "Fix platform-side: grant the GitHub Packages PAT read access to Ringhel.Procesio.Action.Core (or mirror the SDK to a reachable feed).",
                _cmd("retry", "--from-step 6") + "   # once the source is reachable",
            ],
        }
    if "nu1102" in e or "unable to find package" in e:
        return {
            "kind": "bad_package_version",
            "not_your_code": False,
            "why": "NU1102 = the .csproj pinned a package version that does not exist.",
            "fix": [
                _cmd("get-file-version", "--filename <name>.csproj --version 1") + "   # read the pin",
                _cmd("update-file", "--filename <name>.csproj --content-file fixed.csproj") + "   # fix the version",
                _cmd("retry", "--from-step 6"),
            ],
        }
    return {
        "kind": "code_error",
        "not_your_code": False,
        "why": "Looks like a C#/compile error in the generated code.",
        "fix": [
            _cmd("logs", "--stage compile --success false") + "   # read the exact errors",
            _cmd("retry", "--from-step 6") + "   # let the FIX loop attempt a correction",
            "OR override-stage back to generate and regenerate-file the offending file.",
        ],
    }


def _recommend(status: str, step_status: str | None,
               error_message: str | None = None, last_failed_step=None) -> dict:
    s = (status or "").strip().lower()
    ss = (step_status or "").strip().lower() or None

    if s in ("", "pending"):
        return {"phase": "pending", "poll": False, "recommended": [
            {"action": "start-build", "why": "run the entire pipeline as one background task",
             "command": _cmd("start-build")},
            {"action": "gather", "why": "OR drive it manually, one stage at a time (synchronous GATHER+CLARIFY)",
             "command": _cmd("gather")},
        ]}

    if s in ("gathering", "compiling", "fixing", "delivering"):
        return dict(_RUNNING, phase=s)

    if s == "clarifying":
        return {"phase": "clarify", "poll": False, "recommended": [
            {"action": "answer", "why": "submit answers to the clarification questions (keys are the question ids); triggers PLAN",
             "command": _cmd("answer", "--answers '{\"q1\":\"...\"}'")},
        ], "also": [{"action": "get-build", "why": "re-read clarification_questions if you don't have them",
                     "command": _cmd("get-build")}]}

    if s == "planning":
        if ss == "running":
            return dict(_RUNNING, phase="planning")
        return {"phase": "plan-review", "poll": False, "recommended": [
            {"action": "approve-plan", "why": "plan looks right → generate code (pauses after)",
             "command": _cmd("approve-plan")},
            {"action": "revise-plan", "why": "OR change the plan first",
             "command": _cmd("revise-plan", "--feedback '...'")},
        ], "also": [{"action": "set-version", "why": "optionally set Major.Minor.Patch (only valid here)",
                     "command": _cmd("set-version", "--major 1 --minor 0 --patch 0")}]}

    if s == "generating":
        if ss == "running":
            return dict(_RUNNING, phase="generating")
        return {"phase": "generate-review", "poll": False, "recommended": [
            {"action": "approve-generate", "why": "files look right → VALIDATE→COMPILE→FIX→DELIVER",
             "command": _cmd("approve-generate")},
            {"action": "regenerate-file", "why": "OR fix one file",
             "command": _cmd("regenerate-file", "--filename X.cs --instructions '...'")},
            {"action": "regenerate", "why": "OR regenerate with general/per-file instructions",
             "command": _cmd("regenerate", "--step-instructions '...'")},
        ], "also": [{"action": "list-file-versions", "why": "inspect what was generated first",
                     "command": _cmd("list-file-versions")}]}

    if s == "validating":
        if ss == "running":
            return dict(_RUNNING, phase="validating")
        return {"phase": "validate-review", "poll": False, "recommended": [
            {"action": "validate-continue", "why": "accept findings and proceed to COMPILE",
             "command": _cmd("validate-continue")},
            {"action": "validate-autofix", "why": "OR let the LLM auto-fix the findings",
             "command": _cmd("validate-autofix")},
            {"action": "validate-return-to-generate", "why": "OR go back to GENERATE",
             "command": _cmd("validate-return-to-generate")},
        ]}

    if s in ("completed", "delivered", "succeeded"):
        return {"phase": "deliver", "poll": False, "recommended": [
            {"action": "download-artifact", "why": "download the compiled .nupkg",
             "command": _cmd("download-artifact", "--out connector.nupkg")},
        ], "handoff": [
            {"tool": "procesio", "action": "customaction-upload",
             "why": "install the connector in PROCESIO to test it live",
             "command": "python scripts/run-tool.py procesio customaction-upload --file connector.nupkg"},
            {"tool": "procesio (agent)", "action": "verify",
             "why": "exercise the action in a real process per the build-and-test playbook",
             "command": "python scripts/run-agent.py procesio verify --process-id <ID>"},
        ]}

    if s == "failed":
        out = {"phase": "failed", "poll": False, "recommended": [
            {"action": "logs", "why": "read the failing stage logs first (filter --success false)",
             "command": _cmd("logs", "--success false")},
            {"action": "retry", "why": "retry from the last failed step (or --from-step N: ≥6 = compile→deliver)",
             "command": _cmd("retry")},
            {"action": "reset", "why": "OR wipe pipeline state back to pending (only from failed/clarifying/planning)",
             "command": _cmd("reset")},
        ], "also": [{"action": "get-issue", "why": "if an issue case was recorded, read its snapshot",
                     "command": f"python scripts/run-tool.py {_T} list-issues --build-id <ID>"}]}
        # Step 6 = compile: triage restore-vs-code so you don't regenerate a
        # platform NuGet problem (the live-run learning).
        if last_failed_step in (6, "6") or "compil" in (error_message or "").lower() \
                or "nuget" in (error_message or "").lower() or "nu13" in (error_message or "").lower():
            diag = _compile_failure_diagnosis(error_message)
            if diag:
                out["diagnosis"] = diag
        return out

    raise AgentError("unknown_status", f"unrecognised build status: {status!r}",
                     {"known_statuses": ["pending", "gathering", "clarifying", "planning",
                                         "generating", "validating", "compiling", "fixing",
                                         "completed", "failed"]})


def _next_step(ctx, args) -> dict:
    status = args.status
    step_status = args.step_status
    build = None
    error_message = None
    last_failed_step = None
    if args.build_id:
        build = ctx.invoke(_T, "get-build", "--build-id", args.build_id)
        status = build.get("status", status)
        step_status = build.get("step_status", step_status)
        error_message = build.get("error_message")
        last_failed_step = build.get("last_failed_step")
    if not status:
        raise AgentError("missing_input",
                         "provide --status (and optional --step-status) or --build-id",
                         {})
    plan = _recommend(status, step_status, error_message, last_failed_step)
    plan["build_status"] = status
    plan["step_status"] = step_status
    if args.build_id:
        plan["build_id"] = args.build_id
    return plan


def _next_step_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--build-id", dest="build_id",
                   help="Read live status from the connector-builder tool")
    p.add_argument("--status", help="Build overall status (if not using --build-id)")
    p.add_argument("--step-status", dest="step_status",
                   help="running | waiting_user (refines the recommendation)")


ACTIONS = {
    "next-step": ActionDef(
        func=_next_step, add_args=_next_step_args, context=True,
        description="Recommend the next pipeline action for a build's state (live via --build-id).",
    ),
}
