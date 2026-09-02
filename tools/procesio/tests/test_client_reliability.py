"""Client-level reliability: total deadline, GET-only retry, run-process exemption.

Exercises the guardrails end-to-end through ProcesioClient with a fake session,
including the conflict-register assertions C1 (deadline vs long runs) and C4
(retry vs side effects)."""
from __future__ import annotations

import time

import pytest
import requests

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import DeadlineExceeded, ProcesioAPIError
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _client(session, profile=None):
    return ProcesioClient(
        profile=profile or {"type": "apikey", "key": "N", "value": "V"},
        name="t", session=session)


def _builder(profile, session):
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Make retry backoff instant so tests don't actually sleep."""
    monkeypatch.setattr("tools.procesio.reliability.full_jitter", lambda *a, **k: 0.0)


# -- C1: total deadline vs long runs ----------------------------------------

def test_get_trips_total_deadline_on_slow_response():
    def responder(method, url, kwargs):
        time.sleep(1.0)                 # server accepts then stalls
        return FakeResp(200, {"never": "seen"})
    c = _client(FakeSession(responder=responder))
    with pytest.raises(DeadlineExceeded) as ei:
        c.get("/api/FormTemplate/F1", deadline=0.15)
    assert ei.value.endpoint_class == "read"


def test_deadline_error_classifies_to_structured_envelope():
    err = DeadlineExceeded("/api/Projects/X", "read", 90.0, 91.2)
    code, msg, details, exit_code = errors.classify(err)
    assert code == "deadline_exceeded"
    assert exit_code == 1
    assert details["kind"] == "deadline"
    assert details["endpoint"] == "/api/Projects/X"
    assert details["outcome"] == "unknown"     # a write may or may not have landed


def test_run_process_is_exempt_from_the_deadline():
    # A synchronous run legitimately takes a long time; run-process passes
    # deadline=None so a slow response does NOT raise DeadlineExceeded.
    def responder(method, url, kwargs):
        time.sleep(0.3)
        return FakeResp(200, {"instanceId": "i1", "status": 50})
    out = main.dispatch(
        "run-process", ["--id", "PID", "--payload", "{}"],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"},
                                FakeSession(responder=responder)))
    assert out["result"]["status"] == 50


# -- C4: retry vs side effects ----------------------------------------------

def test_get_retries_transient_then_succeeds():
    sess = FakeSession(queue=[FakeResp(503, {"message": "busy"}),
                              FakeResp(200, {"ok": 1})])
    c = _client(sess)
    assert c.get("/api/Projects", deadline=5) == {"ok": 1}
    assert len(sess.calls) == 2                 # retried exactly once


def test_get_gives_up_after_max_retries():
    sess = FakeSession(queue=[FakeResp(503, {}) for _ in range(5)])
    c = _client(sess)
    with pytest.raises(ProcesioAPIError) as ei:
        c.get("/api/Projects", deadline=5)
    assert ei.value.status == 503
    assert len(sess.calls) == 1 + 2             # first attempt + MAX_RETRIES


def test_get_500_is_not_retried():
    sess = FakeSession(queue=[FakeResp(500, {"message": "boom"})])
    c = _client(sess)
    with pytest.raises(ProcesioAPIError):
        c.get("/api/Projects", deadline=5)
    assert len(sess.calls) == 1                 # 500 excluded from retry


def test_post_is_never_retried_even_on_503():
    sess = FakeSession(queue=[FakeResp(503, {}) for _ in range(5)])
    c = _client(sess)
    with pytest.raises(ProcesioAPIError):
        c.post("/api/Projects/PID/run", {"payload": {}})
    assert len(sess.calls) == 1                 # re-POSTing would double-execute


def test_run_process_post_makes_exactly_one_attempt():
    # The C4 guarantee end-to-end: an execution is structurally un-retryable.
    def responder(method, url, kwargs):
        return FakeResp(503, {"message": "queue full"})
    sess = FakeSession(responder=responder)
    with pytest.raises(ProcesioAPIError):
        main.dispatch("run-process", ["--id", "PID", "--payload", "{}"],
                      client_builder=_builder(
                          {"type": "apikey", "key": "N", "value": "V"}, sess))
    assert len(sess.calls) == 1


def test_get_retries_on_network_error():
    calls = {"n": 0}

    def responder(method, url, kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("reset")
        return FakeResp(200, {"ok": 1})
    c = _client(FakeSession(responder=responder))
    assert c.get("/api/Projects", deadline=5) == {"ok": 1}
    assert calls["n"] == 2


def test_post_network_error_propagates_without_retry():
    calls = {"n": 0}

    def responder(method, url, kwargs):
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("reset")
    c = _client(FakeSession(responder=responder))
    with pytest.raises(requests.exceptions.ConnectionError):
        c.post("/api/Projects/PID/run", {"payload": {}})
    assert calls["n"] == 1                      # cannot know if the POST landed
