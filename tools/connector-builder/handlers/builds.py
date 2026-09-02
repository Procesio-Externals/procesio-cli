"""Build lifecycle actions — the heart of the connector pipeline.

Stage flow (documentation/04-PIPELINE-ENGINE.md):
  create -> gather (GATHER+CLARIFY) -> answer (->PLAN) -> approve-plan (->GENERATE,
  pauses) -> approve-generate (->VALIDATE/COMPILE/FIX/DELIVER) -> artifact (.nupkg).
Feedback loops: revise-plan, regenerate / regenerate-file, validate-*, retry,
override-stage, post-message.
"""
from __future__ import annotations

import argparse

from actiondef import ActionDef
from client import build_is_settled
from errors import UsageError
from handlers.common import (add_build_id, add_pagination, add_wait_args,
                             parse_json, run_with_optional_wait)


# --------------------------------------------------------------------------- #
# Read / list
# --------------------------------------------------------------------------- #

def list_builds(client, args) -> dict:
    params = {"page": args.page, "per_page": args.per_page}
    if args.status:
        params["status"] = args.status
    if args.archive_status:
        params["archive_status"] = args.archive_status
    if args.created_by:
        params["created_by"] = args.created_by
    return client.get("/builds", params)


def get_build(client, args) -> dict:
    return client.get(f"/builds/{args.build_id}")


def stage_override_options(client, args) -> dict:
    return client.get("/builds/stage-override-options")


# --------------------------------------------------------------------------- #
# Create + run
# --------------------------------------------------------------------------- #

def create_build(client, args) -> dict:
    body: dict = {}
    if args.api_url:
        body["api_url"] = args.api_url
    if args.api_urls:
        body["api_urls"] = parse_json(args.api_urls, what="api-urls", expect=list)
    if args.api_docs_text:
        body["api_docs_text"] = args.api_docs_text
    if args.user_requirements:
        body["user_requirements"] = args.user_requirements
    if not (body.get("api_url") or body.get("api_urls") or body.get("api_docs_text")):
        raise UsageError("provide at least one of --api-url / --api-urls / --api-docs-text")
    return client.post("/builds", body)


def start_build(client, args) -> dict:
    """Launch the FULL pipeline as a background task (no per-stage pauses)."""
    return client.post(f"/builds/{args.build_id}/start")


def gather(client, args) -> dict:
    """Run GATHER + CLARIFY synchronously; returns api_profile + questions.
    With --wait, survives the proxy 504 by polling to the clarify pause."""
    return run_with_optional_wait(
        client, args.build_id,
        lambda: client.post(f"/builds/{args.build_id}/gather"), args)


def answer(client, args) -> dict:
    """Submit clarification answers; triggers PLAN. With --wait, polls to the
    plan-review pause (survives the proxy 504)."""
    answers = parse_json(args.answers, what="answers", expect=dict) or {}
    return run_with_optional_wait(
        client, args.build_id,
        lambda: client.post(f"/builds/{args.build_id}/answers", {"answers": answers}),
        args)


def approve_plan(client, args) -> dict:
    """Approve the plan; triggers GENERATE (pauses after generation)."""
    return client.post(f"/builds/{args.build_id}/approve")


def revise_plan(client, args) -> dict:
    """Send free-text feedback to revise the implementation plan. With --wait,
    polls back to the plan-review pause (survives the proxy 504)."""
    return run_with_optional_wait(
        client, args.build_id,
        lambda: client.post(f"/builds/{args.build_id}/revise-plan",
                            {"feedback": args.feedback}), args)


def wait_build(client, args) -> dict:
    """Poll get-build until the build settles (waiting_user or terminal), or
    only-terminal with --until terminal. Use after approve-generate/retry/
    start-build to block until compile finishes."""
    build = client.wait_for_settled(
        args.build_id, timeout=args.wait_timeout, interval=args.poll_interval,
        until=args.until)
    out = dict(build)
    out["waited"] = True
    out["settled"] = build_is_settled(build, args.until)
    return out


def approve_generate(client, args) -> dict:
    """Accept generated files; triggers VALIDATE -> COMPILE -> FIX -> DELIVER."""
    return client.post(f"/builds/{args.build_id}/generate/approve")


def regenerate(client, args) -> dict:
    """Regenerate with per-file and/or general instructions."""
    body: dict = {}
    if args.file_instructions:
        body["file_instructions"] = parse_json(
            args.file_instructions, what="file-instructions", expect=dict)
    if args.step_instructions:
        body["step_instructions"] = args.step_instructions
    return client.post(f"/builds/{args.build_id}/generate/regenerate", body)


def regenerate_file(client, args) -> dict:
    return client.post(
        f"/builds/{args.build_id}/generate/regenerate-file",
        {"filename": args.filename, "instructions": args.instructions})


def validate_autofix(client, args) -> dict:
    return client.post(f"/builds/{args.build_id}/validate/autofix")


def validate_continue(client, args) -> dict:
    return client.post(f"/builds/{args.build_id}/validate/continue")


def validate_return_to_generate(client, args) -> dict:
    return client.post(f"/builds/{args.build_id}/validate/return-to-generate")


def retry(client, args) -> dict:
    body: dict = {}
    if args.from_step is not None:
        body["from_step"] = args.from_step
    return client.post(f"/builds/{args.build_id}/retry", body)


def override_stage(client, args) -> dict:
    return client.post(
        f"/builds/{args.build_id}/override-stage",
        {"target_step": args.target_step, "target_status": args.target_status})


def reset(client, args) -> dict:
    return client.post(f"/builds/{args.build_id}/reset")


def set_version(client, args) -> dict:
    return client.patch(
        f"/builds/{args.build_id}/version",
        {"major": args.major, "minor": args.minor, "patch": args.patch})


def archive(client, args) -> dict:
    return client.patch(f"/builds/{args.build_id}/archive")


def unarchive(client, args) -> dict:
    return client.patch(f"/builds/{args.build_id}/unarchive")


# --------------------------------------------------------------------------- #
# Logs / events / messages
# --------------------------------------------------------------------------- #

def logs(client, args) -> dict:
    params = {"page": args.page, "page_size": args.page_size}
    for f in ("stage", "model", "model_search", "after", "before"):
        v = getattr(args, f)
        if v:
            params[f] = v
    if args.success is not None:
        params["success"] = str(args.success).lower()
    return client.get(f"/builds/{args.build_id}/logs", params)


def events(client, args) -> dict:
    params = {"page": args.page, "per_page": args.per_page}
    for f in ("step", "level", "event_type"):
        v = getattr(args, f)
        if v:
            params[f] = v
    return client.get(f"/builds/{args.build_id}/events", params)


def list_messages(client, args) -> dict:
    params = {"page": args.page, "per_page": args.per_page}
    if args.step:
        params["step"] = args.step
    return client.get(f"/builds/{args.build_id}/messages", params)


def post_message(client, args) -> dict:
    return client.post(f"/builds/{args.build_id}/messages",
                       {"step": args.step, "content": args.content})


# --------------------------------------------------------------------------- #
# argparse
# --------------------------------------------------------------------------- #

def _list_builds_args(p: argparse.ArgumentParser) -> None:
    add_pagination(p)
    p.add_argument("--status", help="Filter by pipeline status")
    p.add_argument("--archive-status", dest="archive_status",
                   help="active | archived | all")
    p.add_argument("--created-by", dest="created_by",
                   help="UUID CSV (admin only)")


def _create_build_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--api-url", dest="api_url", help="Single API docs URL")
    p.add_argument("--api-urls", dest="api_urls", help="JSON array of doc URLs")
    p.add_argument("--api-docs-text", dest="api_docs_text",
                   help="Pasted API documentation text")
    p.add_argument("--user-requirements", dest="user_requirements",
                   help="What the connector should do")


def _gather_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    add_wait_args(p)


def _answer_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--answers", required=True,
                   help='JSON object {"q1":"a1","q2":"a2"}')
    add_wait_args(p)


def _revise_plan_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--feedback", required=True, help="Plan revision feedback")
    add_wait_args(p)


def _wait_build_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--wait-timeout", dest="wait_timeout", type=int, default=600,
                   help="Max seconds to poll (default 600)")
    p.add_argument("--poll-interval", dest="poll_interval", type=int, default=8,
                   help="Seconds between polls (default 8)")
    p.add_argument("--until", default="settled",
                   help="settled (waiting_user or terminal) | terminal (only completed/failed/...)")


def _regenerate_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--file-instructions", dest="file_instructions",
                   help='JSON object {"File.cs":"instructions"}')
    p.add_argument("--step-instructions", dest="step_instructions",
                   help="General feedback for the whole generation step")


def _regenerate_file_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--filename", required=True, help="File to regenerate")
    p.add_argument("--instructions", required=True, help="Instructions for the file")


def _retry_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--from-step", dest="from_step", type=int,
                   help="Stage number to retry from (default: last failed)")


def _override_stage_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--target-step", dest="target_step", type=int, required=True,
                   help="Target stage 1-8")
    p.add_argument("--target-status", dest="target_status", required=True,
                   help="running | waiting_user")


def _set_version_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--major", type=int, required=True)
    p.add_argument("--minor", type=int, required=True)
    p.add_argument("--patch", type=int, required=True)


def _post_message_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--step", required=True, help="Pipeline step, e.g. clarify | plan")
    p.add_argument("--content", required=True, help="Message text")


def _logs_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", dest="page_size", type=int, default=100,
                   help="Max 500")
    p.add_argument("--stage", help="Comma-separated stage names")
    p.add_argument("--success", type=lambda v: v.lower() in ("1", "true", "yes"),
                   default=None, help="Filter by success true/false")
    p.add_argument("--model", help="Comma-separated model names")
    p.add_argument("--model-search", dest="model_search", help="Substring model search")
    p.add_argument("--after", help="ISO datetime lower bound")
    p.add_argument("--before", help="ISO datetime upper bound")


def _events_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    add_pagination(p, 100)
    p.add_argument("--step", help="Filter by step")
    p.add_argument("--level", help="Filter by level")
    p.add_argument("--event-type", dest="event_type", help="Filter by event type")


def _messages_args(p: argparse.ArgumentParser) -> None:
    add_build_id(p)
    add_pagination(p, 100)
    p.add_argument("--step", help="Filter by step")


def _build_id_only(p: argparse.ArgumentParser) -> None:
    add_build_id(p)


ACTIONS: dict[str, ActionDef] = {
    "list-builds": ActionDef(list_builds, _list_builds_args,
                             description="List builds (paginated, filterable)."),
    "get-build": ActionDef(get_build, _build_id_only,
                           description="Full build detail (all JSONB fields)."),
    "stage-override-options": ActionDef(
        stage_override_options,
        description="Valid stage-override targets for override-stage."),
    "create-build": ActionDef(create_build, _create_build_args,
                              description="Create a build from URL(s) / pasted docs."),
    "start-build": ActionDef(start_build, _build_id_only,
                             description="Run the FULL pipeline as a background task."),
    "gather": ActionDef(gather, _gather_args,
                        description="Run GATHER+CLARIFY (profile+questions); --wait survives the 504."),
    "wait-build": ActionDef(wait_build, _wait_build_args,
                            description="Poll get-build until settled/terminal (use after approve-generate/retry)."),
    "answer": ActionDef(answer, _answer_args,
                        description="Submit clarification answers; triggers PLAN."),
    "approve-plan": ActionDef(approve_plan, _build_id_only,
                              description="Approve plan; triggers GENERATE (then pauses)."),
    "revise-plan": ActionDef(revise_plan, _revise_plan_args,
                             description="Revise the plan with free-text feedback."),
    "approve-generate": ActionDef(
        approve_generate, _build_id_only,
        description="Accept generated files; runs VALIDATE->COMPILE->FIX->DELIVER."),
    "regenerate": ActionDef(regenerate, _regenerate_args,
                            description="Regenerate files with per-file/general instructions."),
    "regenerate-file": ActionDef(regenerate_file, _regenerate_file_args,
                                 description="Regenerate a single file with instructions."),
    "validate-autofix": ActionDef(validate_autofix, _build_id_only,
                                  description="Auto-fix validation findings."),
    "validate-continue": ActionDef(validate_continue, _build_id_only,
                                   description="Continue past validation to COMPILE."),
    "validate-return-to-generate": ActionDef(
        validate_return_to_generate, _build_id_only,
        description="Return from VALIDATE back to GENERATE."),
    "retry": ActionDef(retry, _retry_args,
                       description="Retry the pipeline from a step (or last failed)."),
    "override-stage": ActionDef(override_stage, _override_stage_args,
                                description="Jump the build to a target step/status."),
    "reset": ActionDef(reset, _build_id_only,
                       description="Reset a failed/clarifying/planning build to pending."),
    "set-version": ActionDef(set_version, _set_version_args,
                             description="Set Major.Minor.Patch (at Plan/waiting_user)."),
    "archive": ActionDef(archive, _build_id_only, description="Archive a build (admin)."),
    "unarchive": ActionDef(unarchive, _build_id_only,
                           description="Unarchive a build (admin)."),
    "logs": ActionDef(logs, _logs_args,
                      description="Per-build stage logs (model/cost/token breakdown)."),
    "events": ActionDef(events, _events_args, description="Per-build pipeline events."),
    "list-messages": ActionDef(list_messages, _messages_args,
                               description="Chat/system messages for a build."),
    "post-message": ActionDef(post_message, _post_message_args,
                              description="Post a chat message to a build/step."),
}
