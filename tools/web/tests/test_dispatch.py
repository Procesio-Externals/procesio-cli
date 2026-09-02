"""Dispatcher: action routing, arg parsing, driver injection vs not, and the
--actions / --actions-file handling in the run handler."""
from __future__ import annotations

import json

import pytest

from tools.web import main, sessions
from tools.web.errors import UsageError


def _seed(name="linkedin"):
    sessions.write_state(name, {"cookies": [{"name": "sid", "value": "v"}], "origins": []})


def test_unknown_action_raises_usage_error():
    with pytest.raises(UsageError) as e:
        main.dispatch("frobnicate", [])
    assert "unknown action" in str(e.value)


def test_all_manifest_actions_registered():
    # every advertised action exists in the dispatcher
    for name in ["save-session", "list-sessions", "delete-session",
                 "run", "get-text", "screenshot"]:
        assert name in main.ACTIONS


def test_list_sessions_needs_no_driver(isolated_sessions):
    _seed("a")
    out = main.dispatch("list-sessions", [])
    assert out["count"] == 1
    assert out["sessions"][0]["name"] == "a"


def test_delete_session_dispatch_requires_confirm(isolated_sessions):
    _seed("gone")
    preview = main.dispatch("delete-session", ["--name", "gone"])
    assert preview["deleted"] is False and preview["confirmation_required"] is True

    out = main.dispatch("delete-session", ["--name", "gone", "--confirm"])
    assert out["deleted"] is True and out["removed"] == ["state"]


def test_run_dispatch_injects_driver(isolated_sessions, driver_factory):
    _seed()
    steps = [{"do": "extract_text", "selector": "h1", "name": "t"}]
    out = main.dispatch(
        "run",
        ["--session", "linkedin", "--actions", json.dumps(steps)],
        driver_factory=driver_factory,
    )
    assert out["session"] == "linkedin"
    assert "t" in out["results"]
    assert driver_factory.built  # a driver was built and injected


def test_run_headed_flag(isolated_sessions, driver_factory):
    _seed()
    main.dispatch(
        "run",
        ["--session", "linkedin", "--actions", "[]", "--headed"],
        driver_factory=driver_factory,
    )
    assert driver_factory.built[0].init["headless"] is False


def test_run_actions_file(isolated_sessions, driver_factory, tmp_path):
    _seed()
    f = tmp_path / "steps.json"
    f.write_text(json.dumps([{"do": "goto", "url": "https://x.test"}]), encoding="utf-8")
    out = main.dispatch(
        "run",
        ["--session", "linkedin", "--actions-file", str(f)],
        driver_factory=driver_factory,
    )
    assert "goto" in driver_factory.built[0].methods()
    assert out["session"] == "linkedin"


def test_run_both_actions_and_file_rejected(isolated_sessions, driver_factory, tmp_path):
    _seed()
    f = tmp_path / "s.json"
    f.write_text("[]", encoding="utf-8")
    with pytest.raises(UsageError):
        main.dispatch(
            "run",
            ["--session", "linkedin", "--actions", "[]", "--actions-file", str(f)],
            driver_factory=driver_factory,
        )


def test_run_missing_actions_rejected(isolated_sessions, driver_factory):
    _seed()
    with pytest.raises(UsageError):
        main.dispatch("run", ["--session", "linkedin"], driver_factory=driver_factory)


def test_run_bad_json_rejected(isolated_sessions, driver_factory):
    _seed()
    with pytest.raises(UsageError):
        main.dispatch("run", ["--session", "linkedin", "--actions", "{not json"],
                      driver_factory=driver_factory)


def test_get_text_dispatch(isolated_sessions, driver_factory):
    _seed()
    out = main.dispatch(
        "get-text",
        ["--session", "linkedin", "--url", "https://x.test", "--selector", "main"],
        driver_factory=driver_factory,
    )
    assert out["selector"] == "main"
    assert out["url"] == "https://x.test"


def test_screenshot_dispatch(isolated_sessions, driver_factory, tmp_path):
    _seed()
    out = main.dispatch(
        "screenshot",
        ["--session", "linkedin", "--url", "https://x.test",
         "--out", str(tmp_path / "s.png")],
        driver_factory=driver_factory,
    )
    assert out["path"].endswith("s.png")


def test_missing_required_arg_raises_usage_error(isolated_sessions, driver_factory):
    with pytest.raises(UsageError):
        main.dispatch("get-text", ["--session", "linkedin"],
                      driver_factory=driver_factory)  # missing --url
