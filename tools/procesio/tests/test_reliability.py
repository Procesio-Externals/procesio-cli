"""Unit tests for the request-reliability primitives (offline, no HTTP)."""
from __future__ import annotations

import random
import time

import pytest

from tools.procesio import reliability


# -- deadline resolution ----------------------------------------------------

def test_resolve_deadline_class_defaults():
    assert reliability.resolve_deadline("GET", reliability.DEFAULT) == reliability.READ_DEADLINE
    assert reliability.resolve_deadline("PUT", reliability.DEFAULT) == reliability.WRITE_DEADLINE
    assert reliability.resolve_deadline("POST", reliability.DEFAULT) == reliability.WRITE_DEADLINE


def test_resolve_deadline_none_is_exempt():
    assert reliability.resolve_deadline("GET", None) is None


def test_resolve_deadline_numeric_override():
    assert reliability.resolve_deadline("GET", 5) == 5.0


def test_resolve_deadline_env_optout(monkeypatch):
    monkeypatch.setenv(reliability.ENV_NO_DEADLINE, "1")
    assert reliability.resolve_deadline("GET", reliability.DEFAULT) is None
    assert reliability.resolve_deadline("PUT", 30) is None


# -- retry policy -----------------------------------------------------------

def test_is_retryable_get_only_transient():
    assert reliability.is_retryable("GET", 503, 0) is True
    assert reliability.is_retryable("GET", 429, 0) is True
    # 500 is deliberately excluded (may be deterministic, not transient)
    assert reliability.is_retryable("GET", 500, 0) is False
    # writes are NEVER retryable — the single structural guarantee
    assert reliability.is_retryable("POST", 503, 0) is False
    assert reliability.is_retryable("PUT", 503, 0) is False


def test_is_retryable_respects_attempt_budget():
    assert reliability.is_retryable("GET", 503, reliability.MAX_RETRIES) is False


def test_retry_env_optout(monkeypatch):
    monkeypatch.setenv(reliability.ENV_NO_RETRY, "true")
    assert reliability.is_retryable("GET", 503, 0) is False
    assert reliability.network_error_retryable("GET", 0) is False


def test_network_error_retryable_get_only():
    assert reliability.network_error_retryable("GET", 0) is True
    assert reliability.network_error_retryable("POST", 0) is False


def test_full_jitter_within_bounds():
    rng = random.Random(1234)
    for attempt in range(1, 12):
        ceiling = min(reliability.BACKOFF_CAP, reliability.BACKOFF_BASE * (2 ** attempt))
        v = reliability.full_jitter(attempt, rng)
        assert 0.0 <= v <= ceiling
    # large attempt is capped
    assert reliability.full_jitter(20, rng) <= reliability.BACKOFF_CAP


def test_parse_retry_after():
    assert reliability.parse_retry_after({"Retry-After": "3"}) == 3.0
    assert reliability.parse_retry_after({"retry-after": "2"}) == 2.0  # case-insensitive
    assert reliability.parse_retry_after({"Retry-After": "999"}) == reliability.BACKOFF_CAP
    assert reliability.parse_retry_after({"Retry-After": "Wed, 21 Oct"}) is None  # HTTP-date ignored
    assert reliability.parse_retry_after({}) is None
    assert reliability.parse_retry_after(None) is None


# -- total deadline ---------------------------------------------------------

def test_run_with_deadline_returns_value():
    assert reliability.run_with_deadline(lambda: 42, 1.0) == 42


def test_run_with_deadline_no_deadline_runs_inline():
    assert reliability.run_with_deadline(lambda: "ok", None) == "ok"


def test_run_with_deadline_trips_on_slow_fn():
    def slow():
        time.sleep(1.0)
        return "late"
    with pytest.raises(reliability.DeadlineHit):
        reliability.run_with_deadline(slow, 0.1)


def test_run_with_deadline_reraises_worker_exception():
    def boom():
        raise ValueError("kaboom")
    with pytest.raises(ValueError, match="kaboom"):
        reliability.run_with_deadline(boom, 1.0)


def test_run_with_deadline_zero_timeout_trips_immediately():
    with pytest.raises(reliability.DeadlineHit):
        reliability.run_with_deadline(lambda: 1, 0)
