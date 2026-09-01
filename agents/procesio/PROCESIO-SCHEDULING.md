# PROCESIO Scheduling — run a process unattended

A **schedule** runs a process on a recurrence without a caller. Manage them with the
tool's curated actions (`procesio list-schedules` / `get-schedule` / `create-schedule` /
`update-schedule` / `delete-schedule` / `set-schedule-status` / the notifications pair /
`list-project-schedules`) over `/api/Schedules*` — not the untyped `request`.

## Recurrence types

`RecurrenceTypes`: `NONE=0, ONCE=1, MINUTES=2, HOURS=3, DAILY=4, WEEKLY=5, MONTHLY=6,
YEARLY=7, CRON=8`. The recurrence lives in the schedule body's nested `recurrence` block
(`recurrence` = the type enum, plus the type-specific fields).

## Crontab schedules (the new capability)

Type **`CRON = 8`** lets you express the recurrence as a standard **5-field crontab**
(`minute hour day month weekday`, `L`/`W`/`#` tokens supported) with an IANA
**time zone**.

- **Preview before you commit:** `procesio validate-crontab --cron "0 6 * * *" --timezone
  Europe/Bucharest [--count N]` calls `POST /api/Schedules/validate-crontab` and returns
  a human description + the next occurrences (in UTC). Always preview a cron string this
  way before creating the schedule — it catches an inverted field order or a timezone
  mistake without creating a live schedule.
- **Set it:** `create-schedule` / `update-schedule` accept `--cron` + `--timezone`, which
  set the recurrence to CRON (type 8) over the JSON `--payload` (name, target process,
  process inputs, notifications). The raw `--payload` remains the authoritative path.

## Gotchas (carried from live runs)

- **The write body must mirror the read DTO closely.** A hand-simplified recurrence block
  returns HTTP 400 "missing or incorrect resource parameters". When unsure of a
  non-cron recurrence, `get-schedule` an existing one and adapt its exact shape rather
  than build from scratch.
- **`status:false` is ignored on create** — a schedule is created active. To land a
  disabled schedule, create then `set-schedule-status --active false` (two steps).
- **`notification.emailList` is a single comma/semicolon-separated string**, not a list.
- The exact camelCase field names of the cron recurrence block are confirmed against the
  launched platform — verify a created cron schedule with `get-schedule` before relying
  on it in production.

## Verify

`validate-crontab` to confirm the occurrences, then `create-schedule`, then
`get-schedule` to confirm the stored recurrence, then (optionally) let it fire once or
trigger the target process directly to confirm it runs. Clean up test schedules
(`delete-schedule`) — a stray active schedule keeps launching instances.
