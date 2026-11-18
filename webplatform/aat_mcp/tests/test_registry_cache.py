"""When the bridge scans the registry again, and when it does not.

A scan parses and re-reports every manifest: seconds of CPU on a large registry, in the thread of
whoever asked. It used to be repeated every 30 seconds whether or not anything could have
changed, and by every caller that arrived while one was already running.
"""
from __future__ import annotations

import threading
import time

import pytest

import bridge


@pytest.fixture
def scans(monkeypatch):
    """Count the scans, and control the clock, the stamp and the credential backend."""
    state = {"count": 0, "now": 1000.0, "stamp": ("v1",)}

    def scan_now():
        state["count"] += 1
        return ([{"name": f"tool-{state['count']}"}], [], [])

    monkeypatch.setattr(bridge, "_scan_registry_now", scan_now)
    monkeypatch.setattr(bridge, "_registry_stamp", lambda: state["stamp"])
    monkeypatch.setattr(bridge.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(bridge, "_REG_CACHE", {})
    monkeypatch.setenv("AAT_REGISTRY_TTL", "30")
    monkeypatch.setenv("AAT_CREDS_BACKEND", "env")
    return state


def test_a_second_call_inside_the_window_does_not_scan(scans):
    first = bridge._scan_registry()
    scans["now"] += 29
    assert bridge._scan_registry() is first
    assert scans["count"] == 1


def test_after_the_window_an_unchanged_registry_is_not_scanned_again(scans):
    first = bridge._scan_registry()
    for _ in range(5):
        scans["now"] += 31
        assert bridge._scan_registry() is first
    assert scans["count"] == 1


def test_a_changed_manifest_is_scanned_once_the_window_is_over(scans):
    bridge._scan_registry()
    scans["stamp"] = ("v2",)

    scans["now"] += 10
    assert bridge._scan_registry()[0] == [{"name": "tool-1"}]  # still inside the window

    scans["now"] += 31
    assert bridge._scan_registry()[0] == [{"name": "tool-2"}]
    assert scans["count"] == 2


@pytest.mark.parametrize("backend", ["windows", "bridge", "file", ""])
def test_where_credentials_can_appear_the_window_still_ends_in_a_scan(scans, monkeypatch, backend):
    """Readiness is part of a scan and is not in the manifest files: a credential stored on a
    workstation has to show up in the next listing."""
    monkeypatch.setenv("AAT_CREDS_BACKEND", backend)
    bridge._scan_registry()
    scans["now"] += 31
    bridge._scan_registry()
    assert scans["count"] == 2


def test_a_window_of_zero_scans_on_every_call(scans, monkeypatch):
    monkeypatch.setenv("AAT_REGISTRY_TTL", "0")
    bridge._scan_registry()
    bridge._scan_registry()
    assert scans["count"] == 2


def test_callers_that_arrive_together_share_one_scan(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    count = {"scans": 0}

    def slow_scan():
        count["scans"] += 1
        started.set()
        release.wait(timeout=10)
        return (["tools"], [], [])

    monkeypatch.setattr(bridge, "_scan_registry_now", slow_scan)
    monkeypatch.setattr(bridge, "_registry_stamp", lambda: ("v1",))
    monkeypatch.setattr(bridge, "_REG_CACHE", {})
    monkeypatch.setenv("AAT_REGISTRY_TTL", "30")

    results: list = []
    callers = [threading.Thread(target=lambda: results.append(bridge._scan_registry())) for _ in range(6)]
    for caller in callers:
        caller.start()
    assert started.wait(timeout=10)
    time.sleep(0.2)  # let the other five reach the lock
    release.set()
    for caller in callers:
        caller.join(timeout=10)

    assert count["scans"] == 1
    assert len(results) == 6 and all(result is results[0] for result in results)


def test_the_stamp_follows_the_files_and_the_hidden_names(tmp_path, monkeypatch):
    tools, agents, skills = tmp_path / "tools", tmp_path / "agents", tmp_path / "skills"
    for folder in (tools / "alpha", agents / "beta", skills / "gamma"):
        folder.mkdir(parents=True)
    manifest_file = tools / "alpha" / "tool.yaml"
    manifest_file.write_text("name: alpha\n", encoding="utf-8")
    (agents / "beta" / "agent.yaml").write_text("name: beta\n", encoding="utf-8")
    (skills / "gamma" / "SKILL.md").write_text("---\nname: gamma\n---\n", encoding="utf-8")
    monkeypatch.setattr(bridge.registry, "TOOLS_DIR", tools)
    monkeypatch.setattr(bridge.registry, "AGENTS_DIR", agents)
    monkeypatch.setattr(bridge.registry, "SKILLS_DIR", skills)
    monkeypatch.setenv("AAT_TOOLS_HIDE", "")

    before = bridge._registry_stamp()
    assert bridge._registry_stamp() == before
    assert len(before[1]) == 3

    manifest_file.write_text("name: alpha\ndescription: longer now\n", encoding="utf-8")
    changed = bridge._registry_stamp()
    assert changed != before

    monkeypatch.setenv("AAT_TOOLS_HIDE", "alpha")
    assert bridge._registry_stamp() != changed


def test_warming_up_fills_the_cache_and_never_raises(monkeypatch):
    monkeypatch.setattr(bridge, "_REG_CACHE", {})
    monkeypatch.setattr(bridge, "_registry_stamp", lambda: ("v1",))
    monkeypatch.setattr(bridge, "_scan_registry_now", lambda: (["tools"], [], []))
    monkeypatch.setenv("AAT_REGISTRY_TTL", "30")

    bridge.warm_registry().join(timeout=10)
    assert bridge._REG_CACHE["data"][0] == (["tools"], [], [])

    def broken():
        raise RuntimeError("no registry")

    monkeypatch.setattr(bridge, "_REG_CACHE", {})
    monkeypatch.setattr(bridge, "_scan_registry_now", broken)
    thread = bridge.warm_registry()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert bridge._REG_CACHE == {}
