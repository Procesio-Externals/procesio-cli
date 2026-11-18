"""ProcesioClient notes its HTTP requests in the trace file when one is given (httptrace).

The trace is what lets the server that started the tool see which request was slow, was retried,
or never came back. These tests prove the client feeds it, and that the answers are unchanged.
"""
from __future__ import annotations

import json
import os

import pytest

from tools._lib import httptrace
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession

PROFILE = {"type": "apikey", "key": "N", "value": "V", "workspace_id": "WS"}


@pytest.fixture
def trace(tmp_path, monkeypatch):
    path = tmp_path / "trace.jsonl"
    path.write_bytes(b"")
    monkeypatch.setenv(httptrace.ENV, str(path))
    return path


def _events(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_without_a_trace_file_the_session_is_left_alone(monkeypatch):
    monkeypatch.delenv(httptrace.ENV, raising=False)
    session = FakeSession(queue=[FakeResp(200, {"ok": True})])
    client = ProcesioClient(profile=PROFILE, name="t", session=session)
    assert client.get("/api/Workspaces") == {"ok": True}
    assert "request" not in vars(session)


def test_a_request_is_traced_and_its_answer_is_unchanged(trace):
    session = FakeSession(queue=[FakeResp(200, {"ok": True})])
    client = ProcesioClient(profile=PROFILE, name="t", session=session)

    assert client.get("/api/Projects/3fa85f64-5717-4562-b3fc-2c963f66afa6", query={"q": "x"}) == {"ok": True}

    start, end = _events(trace)
    assert (start["e"], start["m"]) == ("start", "GET")
    assert start["p"].endswith("/api/Projects/3fa85f64-5717-4562-b3fc-2c963f66afa6")
    assert (end["e"], end["s"]) == ("end", 200)
    # The request is named by this process and one number, the same on both lines.
    assert start["pid"] == end["pid"] == os.getpid()
    assert start["id"] == end["id"]
    assert len(session.calls) == 1


def test_a_retried_get_leaves_a_retry_line_between_its_two_requests(trace, monkeypatch):
    monkeypatch.setattr("tools.procesio.client.time.sleep", lambda seconds: None)
    session = FakeSession(queue=[FakeResp(503, {"message": "busy"}), FakeResp(200, {"ok": True})])
    client = ProcesioClient(profile=PROFILE, name="t", session=session)

    assert client.get("/api/Workspaces") == {"ok": True}

    events = _events(trace)
    assert [e["e"] for e in events] == ["start", "end", "retry", "start", "end"]
    assert [e["s"] for e in events if e["e"] == "end"] == [503, 200]
    assert events[2] == {"e": "retry", "m": "GET", "p": "/api/Workspaces"}  # no pid: it is not paired
    # Two requests of one process: the same pid, and a number of its own for each.
    assert {e["pid"] for e in events if e["e"] != "retry"} == {os.getpid()}
    assert events[0]["id"] == events[1]["id"] != events[3]["id"] == events[4]["id"]
