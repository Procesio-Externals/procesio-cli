"""Tests for --wait / wait-build polling (survives the proxy 504, no network)."""
from __future__ import annotations

import types

import pytest

import cb_client as client
import cb_errors as errors
import cb_handlers_common as common


# -- build_is_settled --------------------------------------------------------

def test_settled_on_waiting_user():
    assert client.build_is_settled({"status": "planning", "step_status": "waiting_user"})


def test_settled_on_terminal():
    assert client.build_is_settled({"status": "completed", "step_status": "completed"})
    assert client.build_is_settled({"status": "failed"})


def test_running_is_not_settled():
    assert not client.build_is_settled({"status": "planning", "step_status": "running"})


def test_until_terminal_ignores_waiting_user():
    b = {"status": "validating", "step_status": "waiting_user"}
    assert client.build_is_settled(b, until="settled")
    assert not client.build_is_settled(b, until="terminal")


# -- wait_for_settled --------------------------------------------------------

def _client_returning(sequence):
    c = client.ConnectorBuilderClient(token="t")
    it = iter(sequence)
    c.get_build = lambda _bid: next(it)  # type: ignore[method-assign]
    return c


def test_wait_polls_until_settled():
    c = _client_returning([
        {"status": "planning", "step_status": "running", "updated_at": "t0"},
        {"status": "planning", "step_status": "running", "updated_at": "t0"},
        {"status": "planning", "step_status": "waiting_user", "updated_at": "t1"},
    ])
    ticks = iter([0, 1, 2, 3, 4])
    b = c.wait_for_settled("B", timeout=100, interval=0,
                           sleep=lambda _s: None, clock=lambda: next(ticks))
    assert b["step_status"] == "waiting_user" and b["updated_at"] == "t1"


def test_wait_respects_baseline_updated_at():
    # A stale read (same updated_at as baseline) must NOT count as settled.
    c = _client_returning([
        {"status": "clarifying", "step_status": "waiting_user", "updated_at": "T0"},  # stale
        {"status": "planning", "step_status": "waiting_user", "updated_at": "T1"},    # fresh
    ])
    ticks = iter([0, 1, 2, 3])
    b = c.wait_for_settled("B", timeout=100, interval=0, baseline_updated_at="T0",
                           sleep=lambda _s: None, clock=lambda: next(ticks))
    assert b["updated_at"] == "T1"


def test_wait_returns_last_on_timeout():
    c = _client_returning([{"status": "planning", "step_status": "running", "updated_at": "t0"}] * 5)
    ticks = iter([0, 100, 200])  # already past deadline on first check
    b = c.wait_for_settled("B", timeout=10, interval=0,
                           sleep=lambda _s: None, clock=lambda: next(ticks))
    assert b["step_status"] == "running"  # returned last-seen, not settled


# -- run_with_optional_wait --------------------------------------------------

class _FakeClient:
    def __init__(self, settled_build, raise_on_trigger=None):
        self._settled = settled_build
        self._raise = raise_on_trigger
        self.trigger_calls = 0

    def get_build(self, _bid):
        return {"status": "clarifying", "step_status": "waiting_user", "updated_at": "T0"}

    def wait_for_settled(self, _bid, **_kw):
        return self._settled


def _args(**kw):
    base = {"wait": False, "wait_timeout": 600, "poll_interval": 8}
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_no_wait_returns_trigger_verbatim():
    c = _FakeClient({"status": "planning", "step_status": "waiting_user"})
    out = common.run_with_optional_wait(
        c, "B", lambda: {"status": "planning", "raw": True}, _args(wait=False))
    assert out == {"status": "planning", "raw": True}


def test_wait_swallows_504_and_polls():
    settled = {"status": "planning", "step_status": "waiting_user", "updated_at": "T1"}
    c = _FakeClient(settled)

    def trigger():
        raise errors.ApiError(504, "/builds/B/answers", "gateway timeout")

    out = common.run_with_optional_wait(c, "B", trigger, _args(wait=True))
    assert out["waited"] is True and out["settled"] is True
    assert out["status"] == "planning"
    assert "trigger_note" in out


def test_wait_reraises_real_4xx():
    c = _FakeClient({"status": "planning", "step_status": "waiting_user"})

    def trigger():
        raise errors.ApiError(400, "/builds/B/answers", "bad state")

    with pytest.raises(errors.ApiError):
        common.run_with_optional_wait(c, "B", trigger, _args(wait=True))
