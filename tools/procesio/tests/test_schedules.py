"""Scheduler curated actions — faked client boundary (zero live HTTP).

Mirrors tests/test_transport.py / test_dispatch.py: a FakeSession records every
HTTP call and serves canned responses, so we assert the method, URL, query, and
body each curated schedule action emits.
"""
from __future__ import annotations

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(profile, session):
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


APIKEY = {"type": "apikey", "key": "N", "value": "V"}


def _last(sess):
    return sess.calls[-1]


# -- list / get -------------------------------------------------------------

def test_list_schedules_hits_endpoint():
    sess = FakeSession(queue=[FakeResp(200, {"pageItems": []})])
    out = main.dispatch("list-schedules", [], client_builder=_builder(APIKEY, sess))
    assert out["result"] == {"pageItems": []}
    c = _last(sess)
    assert c["method"] == "GET"
    assert c["url"].endswith("/api/Schedules")


def test_list_schedules_maps_paging():
    sess = FakeSession(queue=[FakeResp(200, [])])
    main.dispatch("list-schedules",
                  ["--page", "2", "--page-size", "25", "--search", "nightly"],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["params"] == {"pageNumber": 2, "pageItemCount": 25,
                                     "searchName": "nightly"}


def test_get_schedule_uses_id_in_path():
    sess = FakeSession(queue=[FakeResp(200, {"id": "S1"})])
    out = main.dispatch("get-schedule", ["--id", "S1"],
                        client_builder=_builder(APIKEY, sess))
    assert out["result"] == {"id": "S1"}
    c = _last(sess)
    assert c["method"] == "GET"
    assert c["url"].endswith("/api/Schedules/S1")


def test_get_schedule_requires_id():
    with pytest.raises(errors.UsageError):
        main.dispatch("get-schedule", [], client_builder=_builder(APIKEY, FakeSession()))


# -- create / update --------------------------------------------------------

def test_create_schedule_posts_payload():
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEW"})])
    body = '{"name":"nightly","flowId":"P1","isActive":false}'
    out = main.dispatch("create-schedule", ["--payload", body],
                        client_builder=_builder(APIKEY, sess))
    assert out["result"] == {"id": "NEW"}
    c = _last(sess)
    assert c["method"] == "POST"
    assert c["url"].endswith("/api/Schedules")
    assert c["json"] == {"name": "nightly", "flowId": "P1", "isActive": False}


def test_update_schedule_puts_payload():
    sess = FakeSession(queue=[FakeResp(200, {"ok": True})])
    body = '{"id":"S1","name":"nightly-v2"}'
    main.dispatch("update-schedule", ["--payload", body],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "PUT"
    assert c["url"].endswith("/api/Schedules")
    assert c["json"] == {"id": "S1", "name": "nightly-v2"}


def test_create_schedule_cron_sets_recurrence_block():
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEW"})])
    body = '{"name":"nightly","targetProcess":"P1"}'
    main.dispatch("create-schedule",
                  ["--payload", body, "--cron", "0 6 * * *", "--timezone", "Europe/Bucharest"],
                  client_builder=_builder(APIKEY, sess))
    rec = _last(sess)["json"]["recurrence"]
    assert rec["recurrence"] == 8              # RecurrenceTypes.CRON
    assert rec["cronExpression"] == "0 6 * * *"
    assert rec["timeZone"] == "Europe/Bucharest"


def test_create_schedule_cron_drops_the_calendar_recurrence_fields():
    """This test asserted the OPPOSITE until the designer's own PUT was captured.

    Carrying a calendar field such as `isWeekendExcluded` into a cron recurrence makes the
    API refuse the whole body with a generic 400 that names no field. The contract is a
    REPLACEMENT, not an overlay — see tests/test_schedule_cron_shape.py.
    """
    sess = FakeSession(queue=[FakeResp(200, {})])
    body = '{"name":"n","recurrence":{"isWeekendExcluded":true}}'
    main.dispatch("create-schedule", ["--payload", body, "--cron", "*/5 * * * *"],
                  client_builder=_builder(APIKEY, sess))
    rec = _last(sess)["json"]["recurrence"]
    assert "isWeekendExcluded" not in rec
    assert rec["recurrence"] == 8


def test_create_schedule_without_cron_posts_verbatim():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("create-schedule", ["--payload", '{"name":"n"}'],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["json"] == {"name": "n"}   # no recurrence injected


def test_validate_crontab_posts_body():
    sess = FakeSession(queue=[FakeResp(200, {"occurrences": []})])
    main.dispatch("validate-crontab",
                  ["--cron", "0 9 * * 1-5", "--timezone", "UTC", "--count", "3"],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "POST"
    assert c["url"].endswith("/api/Schedules/validate-crontab")
    assert c["json"] == {"cronExpression": "0 9 * * 1-5", "timeZone": "UTC", "count": 3}


def test_create_schedule_requires_payload():
    with pytest.raises(errors.UsageError):
        main.dispatch("create-schedule", [],
                      client_builder=_builder(APIKEY, FakeSession()))


def test_create_schedule_rejects_bad_json():
    with pytest.raises(errors.UsageError):
        main.dispatch("create-schedule", ["--payload", "{bad"],
                      client_builder=_builder(APIKEY, FakeSession()))


# -- delete -----------------------------------------------------------------

def test_delete_schedule_uses_id_in_path():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("delete-schedule", ["--id", "S9"],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "DELETE"
    assert c["url"].endswith("/api/Schedules/S9")


# -- enable / disable -------------------------------------------------------

def test_set_status_maps_active_to_enable_query():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("set-schedule-status", ["--id", "S1", "--active", "false"],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "PATCH"
    assert c["url"].endswith("/api/Schedules/S1/status")
    assert c["params"] == {"enable": "false"}   # API param is `enable`
    assert c["json"] is None


def test_set_status_active_true():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("set-schedule-status", ["--id", "S1", "--active", "true"],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["params"] == {"enable": "true"}


def test_set_status_rejects_non_bool_active():
    with pytest.raises(errors.UsageError):
        main.dispatch("set-schedule-status", ["--id", "S1", "--active", "yes"],
                      client_builder=_builder(APIKEY, FakeSession()))


# -- notifications ----------------------------------------------------------

def test_get_notifications_uses_id_in_path():
    sess = FakeSession(queue=[FakeResp(200, {"emails": []})])
    main.dispatch("get-schedule-notifications", ["--id", "S1"],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "GET"
    assert c["url"].endswith("/api/Schedules/notifications/S1")


def test_set_notifications_posts_payload():
    sess = FakeSession(queue=[FakeResp(200, {})])
    body = '{"scheduleId":"S1","emails":["a@example.com"]}'
    main.dispatch("set-schedule-notifications", ["--payload", body],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "POST"
    assert c["url"].endswith("/api/Schedules/notifications")
    assert c["json"] == {"scheduleId": "S1", "emails": ["a@example.com"]}


# -- project schedules ------------------------------------------------------

def test_list_project_schedules_uses_id_in_path():
    sess = FakeSession(queue=[FakeResp(200, [])])
    main.dispatch("list-project-schedules", ["--id", "P1"],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "GET"
    assert c["url"].endswith("/api/Projects/P1/restricted/schedules")


def test_list_project_schedules_requires_id():
    with pytest.raises(errors.UsageError):
        main.dispatch("list-project-schedules", [],
                      client_builder=_builder(APIKEY, FakeSession()))
