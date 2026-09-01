"""Curated scheduler actions (run a process on a cron / recurrence).

Wraps the `/api/Schedules*` surface so a user or agent can list / get / create /
update / delete a schedule, enable or disable one, manage its notifications, and
list a project's schedules — without dropping to the untyped generic `request`.

Verified routes + methods (Web-API, tag Schedules; perms in parens):
  list           GET    /api/Schedules                              (Schedule.Read)
  get            GET    /api/Schedules/{scheduleId}                 (Schedule.Read)
  create         POST   /api/Schedules                              (Schedule.Write)
  update         PUT    /api/Schedules                              (Schedule.Update)
  delete         DELETE /api/Schedules/{scheduleId}                 (Schedule.Delete)
  set status     PATCH  /api/Schedules/{scheduleId}/status          (Schedule.Update)
  get notifs     GET    /api/Schedules/notifications/{scheduleId}    (Schedule.Read)
  set notifs     POST   /api/Schedules/notifications                 (Schedule.Update)
  project list   GET    /api/Projects/{id}/restricted/schedules      (Schedule.Read)

The create/update body shape is captured in PROCESIO-API-NOTES.md (Hard rule 6).
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.handlers.common import add_paging_args, add_profile_arg


# -- list / get -------------------------------------------------------------

def _list_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    add_paging_args(p)
    p.add_argument("--search", help="filter by schedule name (searchName)")


def list_schedules(client, args) -> dict:
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "searchName": args.search}
    return {"result": client.get("/api/Schedules", q)}


def _id_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="schedule id (scheduleId)")


def get_schedule(client, args) -> dict:
    return {"result": client.get(f"/api/Schedules/{args.id}")}


# -- create / update / delete ----------------------------------------------

# RecurrenceTypes enum (Domain/Enums/Scheduler/RecurrenceTypes.cs): NONE=0, ONCE=1,
# MINUTES=2, HOURS=3, DAILY=4, WEEKLY=5, MONTHLY=6, YEARLY=7, CRON=8. The crontab
# feature (PRC-3282) is recurrence type 8 with a RecurrenceCron block.
_RECURRENCE_CRON = 8


def _apply_cron(body: dict, args) -> dict:
    """When --cron is given, REPLACE the recurrence block with the crontab shape.

    Replace, not overlay. A cron recurrence carries only `recurrence: 8`,
    `cronExpression`, `timeZone`, `info`, `startDate` and `isEndDate` (plus `endDate` when
    the window really ends). Leaving the calendar-recurrence fields in place —
    `every` / `onDay` / `onThe` / `isOnThe` / `isWeekendExcluded` — is what earns the
    generic HTTP 400 `[{"statusCode":502,"value":"Invalid request due to missing or
    incorrect resource parameters.","target":"schedules"}]`. Captured from the designer's
    own PUT, which sends exactly the keys below and nothing else; the same body that fails
    with them present succeeds with them stripped, so this drops them rather than
    trusting a caller's --payload to be cron-shaped already.
    """
    if not getattr(args, "cron", None):
        return body
    src_rec = dict(body.get("recurrence") or {})
    rec = {"recurrence": _RECURRENCE_CRON,
           "cronExpression": args.cron,
           "info": (getattr(args, "recurrence_info", None)
                    or src_rec.get("info") or f"cron: {args.cron}"),
           "isEndDate": bool(src_rec.get("isEndDate"))}
    tz = getattr(args, "timezone", None) or src_rec.get("timeZone")
    if tz:
        rec["timeZone"] = tz
    # Only these two calendar fields survive: the activation window a cron may still carry.
    if src_rec.get("startDate"):
        rec["startDate"] = src_rec["startDate"]
    if rec["isEndDate"] and src_rec.get("endDate"):
        rec["endDate"] = src_rec["endDate"]
    body["recurrence"] = rec
    return body


def _payload_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--payload", required=True,
                   help="schedule as a JSON object (see PROCESIO-API-NOTES.md for the shape)")
    p.add_argument("--cron",
                   help="5-field crontab expression (min hour day month weekday); sets "
                        "the recurrence to CRON (type 8) over the --payload. Preview it "
                        "first with validate-crontab.")
    p.add_argument("--timezone", help="IANA timezone id for the cron (e.g. Europe/Bucharest)")
    p.add_argument("--recurrence-info", dest="recurrence_info",
                   help="human-readable recurrence label (optional)")


def create_schedule(client, args) -> dict:
    body = _apply_cron(parse_json_arg(args.payload, "payload"), args)
    return {"result": client.post("/api/Schedules", body)}


def update_schedule(client, args) -> dict:
    body = _apply_cron(parse_json_arg(args.payload, "payload"), args)
    return {"result": client.put("/api/Schedules", body)}


# -- crontab preview --------------------------------------------------------

def _validate_crontab_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--cron", required=True,
                   help="5-field crontab expression to validate (min hour day month weekday)")
    p.add_argument("--timezone", help="IANA timezone id (default server/UTC)")
    p.add_argument("--count", type=int,
                   help="how many upcoming occurrences to return (default 5, max 20)")
    p.add_argument("--start-date", dest="start_date", help="ISO-8601 activation start (optional)")
    p.add_argument("--end-date", dest="end_date", help="ISO-8601 activation end (optional)")


def validate_crontab(client, args) -> dict:
    body = {"cronExpression": args.cron, "timeZone": args.timezone,
            "count": args.count, "startDate": args.start_date, "endDate": args.end_date}
    body = {k: v for k, v in body.items() if v is not None}
    return {"result": client.post("/api/Schedules/validate-crontab", body)}


def delete_schedule(client, args) -> dict:
    return {"result": client.delete(f"/api/Schedules/{args.id}")}


# -- enable / disable -------------------------------------------------------

def _status_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="schedule id (scheduleId)")
    p.add_argument("--active", required=True, choices=["true", "false"],
                   help="true to enable the schedule, false to disable it")


def set_schedule_status(client, args) -> dict:
    # The API names the query flag `enable`; we expose it as --active per spec.
    q = {"enable": args.active}
    return {"result": client.patch(f"/api/Schedules/{args.id}/status", None, q)}


# -- notifications ----------------------------------------------------------

def _notif_id_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="schedule id (scheduleId)")


def get_schedule_notifications(client, args) -> dict:
    return {"result": client.get(f"/api/Schedules/notifications/{args.id}")}


def _notif_payload_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--payload", required=True,
                   help="notifications config as a JSON object")


def set_schedule_notifications(client, args) -> dict:
    body = parse_json_arg(args.payload, "payload")
    return {"result": client.post("/api/Schedules/notifications", body)}


# -- project schedules ------------------------------------------------------

def _project_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="project (process) id")


def list_project_schedules(client, args) -> dict:
    return {"result": client.get(f"/api/Projects/{args.id}/restricted/schedules")}


ACTIONS = {
    "list-schedules": ActionDef(
        func=list_schedules, add_args=_list_args, needs_client=True,
        description="List schedules (GET /api/Schedules).",
    ),
    "get-schedule": ActionDef(
        func=get_schedule, add_args=_id_args, needs_client=True,
        description="Get one schedule by id (GET /api/Schedules/{id}).",
    ),
    "create-schedule": ActionDef(
        func=create_schedule, add_args=_payload_args, needs_client=True,
        description="Create a schedule (POST /api/Schedules) from a JSON --payload; "
                    "--cron/--timezone sets a crontab recurrence.",
    ),
    "update-schedule": ActionDef(
        func=update_schedule, add_args=_payload_args, needs_client=True,
        description="Update a schedule (PUT /api/Schedules) from a JSON --payload; "
                    "--cron/--timezone sets a crontab recurrence.",
    ),
    "validate-crontab": ActionDef(
        func=validate_crontab, add_args=_validate_crontab_args, needs_client=True,
        description="Preview a crontab expression's next occurrences "
                    "(POST /api/Schedules/validate-crontab).",
    ),
    "delete-schedule": ActionDef(
        func=delete_schedule, add_args=_id_args, needs_client=True,
        description="Delete a schedule (DELETE /api/Schedules/{id}).",
    ),
    "set-schedule-status": ActionDef(
        func=set_schedule_status, add_args=_status_args, needs_client=True,
        description="Enable/disable a schedule (PATCH /api/Schedules/{id}/status --active true|false).",
    ),
    "get-schedule-notifications": ActionDef(
        func=get_schedule_notifications, add_args=_notif_id_args, needs_client=True,
        description="Get a schedule's notifications (GET /api/Schedules/notifications/{id}).",
    ),
    "set-schedule-notifications": ActionDef(
        func=set_schedule_notifications, add_args=_notif_payload_args, needs_client=True,
        description="Set a schedule's notifications (POST /api/Schedules/notifications) from a JSON --payload.",
    ),
    "list-project-schedules": ActionDef(
        func=list_project_schedules, add_args=_project_args, needs_client=True,
        description="List a project's schedules (GET /api/Projects/{id}/restricted/schedules).",
    ),
}
