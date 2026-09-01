"""A cron schedule's recurrence block must carry the cron keys and NOTHING else.

The defect: `--cron` overlaid the crontab keys on top of whatever recurrence the caller's
`--payload` already had. That payload is normally cloned from a live schedule (the API's
own documented advice, because the write body is validated for shape), so it arrives
carrying the calendar-recurrence fields `every` / `onDay` / `onThe` / `isOnThe` /
`isWeekendExcluded`. With those still present the create/update is refused with the
generic

    [{"statusCode":502,"value":"Invalid request due to missing or incorrect resource
      parameters.","target":"schedules"}]

which names no field, so the failure reads as "cron is not supported here" rather than
"you sent five keys too many". `POST /api/Schedules/validate-crontab` accepts the very
same expression happily, which makes the wrong conclusion easy to reach.

The expected shape below was captured from the designer's own PUT.
"""
from __future__ import annotations

import argparse

from tools.procesio.handlers import schedules


CRON_ONLY = {"recurrence", "cronExpression", "timeZone", "info", "isEndDate", "startDate",
             "endDate"}
CALENDAR_ONLY = {"every", "onDay", "onThe", "isOnThe", "isWeekendExcluded"}


def _args(**kw):
    base = {"cron": None, "timezone": None, "recurrence_info": None}
    return argparse.Namespace(**{**base, **kw})


def _legacy_payload() -> dict:
    """A payload cloned from a live MINUTES schedule, as a caller would build one."""
    return {"name": "S", "targetProcess": "p", "processInputs": [],
            "recurrence": {"info": "every 2 minutes", "every": 2, "onDay": 0,
                           "onThe": [2, 1], "endDate": "2027-12-31T00:00:00Z",
                           "isOnThe": False, "isEndDate": False,
                           "startDate": "2026-08-30T06:00:00", "recurrence": 2,
                           "isWeekendExcluded": False}}


def test_the_calendar_recurrence_fields_are_dropped():
    body = schedules._apply_cron(_legacy_payload(),
                                 _args(cron="*/2 * * * *", timezone="Europe/Bucharest"))
    leftover = CALENDAR_ONLY & set(body["recurrence"])
    assert not leftover, (
        f"{sorted(leftover)} survived into a cron recurrence; the API refuses the whole "
        f"body without naming them")


def test_the_block_carries_the_cron_keys():
    body = schedules._apply_cron(_legacy_payload(),
                                 _args(cron="*/2 * * * *", timezone="Europe/Bucharest"))
    rec = body["recurrence"]
    assert rec["recurrence"] == 8
    assert rec["cronExpression"] == "*/2 * * * *"
    assert rec["timeZone"] == "Europe/Bucharest"


def test_no_key_outside_the_captured_shape_is_emitted():
    body = schedules._apply_cron(_legacy_payload(),
                                 _args(cron="0 9 * * 1", timezone="UTC"))
    assert set(body["recurrence"]) <= CRON_ONLY


def test_the_activation_start_survives():
    """The only calendar field a cron schedule legitimately keeps."""
    body = schedules._apply_cron(_legacy_payload(), _args(cron="*/5 * * * *"))
    assert body["recurrence"]["startDate"] == "2026-08-30T06:00:00"


def test_an_end_date_is_dropped_unless_the_window_really_ends():
    """isEndDate false with an endDate still set is the shape the designer never sends."""
    body = schedules._apply_cron(_legacy_payload(), _args(cron="*/5 * * * *"))
    assert body["recurrence"]["isEndDate"] is False
    assert "endDate" not in body["recurrence"]


def test_an_end_date_is_kept_when_the_window_does_end():
    payload = _legacy_payload()
    payload["recurrence"]["isEndDate"] = True
    body = schedules._apply_cron(payload, _args(cron="*/5 * * * *"))
    assert body["recurrence"]["endDate"] == "2027-12-31T00:00:00Z"


def test_the_timezone_from_the_payload_is_used_when_no_flag_is_given():
    payload = _legacy_payload()
    payload["recurrence"]["timeZone"] = "Europe/Bucharest"
    body = schedules._apply_cron(payload, _args(cron="*/5 * * * *"))
    assert body["recurrence"]["timeZone"] == "Europe/Bucharest"


def test_an_explicit_label_wins_over_the_payload_one():
    body = schedules._apply_cron(_legacy_payload(),
                                 _args(cron="*/2 * * * *", recurrence_info="Every 2 minutes"))
    assert body["recurrence"]["info"] == "Every 2 minutes"


def test_everything_outside_the_recurrence_is_untouched():
    body = schedules._apply_cron(_legacy_payload(), _args(cron="*/2 * * * *"))
    assert body["name"] == "S" and body["targetProcess"] == "p"


def test_without_cron_the_payload_passes_through_verbatim():
    payload = _legacy_payload()
    before = dict(payload["recurrence"])
    assert schedules._apply_cron(payload, _args())["recurrence"] == before
