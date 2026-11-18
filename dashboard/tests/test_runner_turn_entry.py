"""A tool or agent run inside a PROCESIO turn (`inherit_env=False`) starts its entry point itself.

Outside a turn nothing changes: the call goes through scripts/run-tool.py, which may hand it to
the warm runner. Inside a turn that script only added a second interpreter and a second registry
lookup to every call, and the warm runner is something a turn must never reach.
"""
from __future__ import annotations

import sys

import pytest

from dashboard.server import runner

# The tool these tests start: one that ships both here and in the public procesio-cli tree, so the
# tests run in both. A tool that exists in only one of them fails the other's CI.
TOOL = "xlsx"
ARGS = ["list-sheets", "--path", "book.xlsx"]


@pytest.fixture
def commands(monkeypatch):
    """Capture what would be started, without starting it."""
    seen: list[dict] = []

    def fake(cmd, *, stdin_text=None, timeout=60.0, env=None, inherit_env=True):
        seen.append({"cmd": cmd, "env": env, "inherit_env": inherit_env, "timeout": timeout})
        return {"returncode": 0, "stdout": '{"ok": true}', "stderr": "", "timed_out": False, "cmd": cmd}

    monkeypatch.setattr(runner, "_run_command", fake)
    monkeypatch.delenv("AAT_TOOLS_HIDE", raising=False)
    return seen


def test_a_turn_starts_the_tool_s_entry_point_directly(commands):
    runner.run_tool(TOOL, ARGS, env={"AAT_USER_ID": "u"}, inherit_env=False, timeout=42)

    (call,) = commands
    entry = runner.PROJECT_ROOT / "tools" / TOOL / "main.py"
    assert call["cmd"] == [runner.python_exe(), str(entry), *ARGS]
    assert call["inherit_env"] is False
    assert call["env"] == {"AAT_USER_ID": "u"}
    assert call["timeout"] == 42


def test_a_turn_starts_the_agent_s_entry_point_directly(commands):
    runner.run_agent("procesio", ["guidance"], env={}, inherit_env=False)

    (call,) = commands
    entry = runner.PROJECT_ROOT / "agents" / "procesio" / "main.py"
    assert call["cmd"] == [runner.python_exe(), str(entry), "guidance"]
    assert call["inherit_env"] is False


def test_outside_a_turn_the_launcher_scripts_are_still_used(commands):
    runner.run_tool(TOOL, ARGS)
    runner.run_agent("procesio", ["guidance"])

    scripts = [call["cmd"][1].replace("\\", "/").rsplit("/", 1)[-1] for call in commands]
    assert scripts == ["run-tool.py", "run-agent.py"]
    assert [call["cmd"][2] for call in commands] == [TOOL, "procesio"]
    assert all(call["inherit_env"] is True for call in commands)


@pytest.mark.parametrize("kind, call, message", [
    ("tool", lambda: runner.run_tool("no-such-tool", [], env={}, inherit_env=False),
     "error: 'tool not found: no-such-tool'"),
    ("agent", lambda: runner.run_agent("no-such-agent", [], env={}, inherit_env=False),
     "error: 'agent not found: no-such-agent'"),
])
def test_an_unknown_name_answers_as_the_launcher_script_did(commands, kind, call, message):
    result = call()

    assert commands == []  # nothing was started
    assert result["ok"] is False
    assert result["returncode"] == 2
    assert result["error"] == {"code": "no_json", "message": message}


def test_a_tool_hidden_from_the_server_is_refused_in_a_turn(commands, monkeypatch):
    """The tool process starts from a filtered environment and never sees AAT_TOOLS_HIDE, so the
    refusal has to come from the server, which does."""
    monkeypatch.setenv("AAT_TOOLS_HIDE", TOOL)

    result = runner.run_tool(TOOL, ARGS, env={}, inherit_env=False)

    assert commands == []
    assert result["ok"] is False
    assert f"tool not found: {TOOL}" in result["error"]["message"]


def test_a_turn_never_reaches_the_warm_runner(monkeypatch):
    """AAT_RUNNER=0 reaches the process whatever the caller's environment or `env` says."""
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "{}", ""

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return Done()

    monkeypatch.setattr(runner, "_isolation", lambda: None)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("AAT_RUNNER", "1")

    runner._run_command([sys.executable, "-c", "pass"], env={"AAT_RUNNER": "1", "KEEP": "me"}, inherit_env=False)

    assert seen["env"]["AAT_RUNNER"] == "0"
    assert seen["env"]["KEEP"] == "me"


def test_outside_a_turn_the_warm_runner_setting_is_left_alone(monkeypatch):
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "{}", ""

    monkeypatch.setattr(runner.subprocess, "run", lambda cmd, **kwargs: seen.update(kwargs) or Done())

    monkeypatch.setenv("AAT_RUNNER", "1")

    runner._run_command([sys.executable, "-c", "pass"], env={"KEEP": "me"})

    assert seen["env"]["AAT_RUNNER"] == "1"
    assert seen["env"]["KEEP"] == "me"


@pytest.mark.parametrize("platform, relative", [
    ("win32", ".venv/Scripts/python.exe"),
    ("linux", ".venv/bin/python"),
    ("darwin", ".venv/bin/python"),
])
def test_the_project_venv_is_looked_for_where_the_system_puts_it(platform, relative):
    assert runner._venv_python(platform) == runner.PROJECT_ROOT / relative


def test_the_project_venv_is_preferred_and_its_absence_is_not_an_error(tmp_path, monkeypatch):
    """A turn starts the entry point with this interpreter and nothing switches it afterwards."""
    venv_python = tmp_path / "python"
    monkeypatch.setattr(runner, "VENV_PY", venv_python)
    assert runner.python_exe() == sys.executable  # no project venv: the server's own interpreter

    venv_python.write_text("", encoding="utf-8")
    assert runner.python_exe() == str(venv_python)


def test_the_launcher_scripts_look_for_the_venv_in_the_same_two_places():
    """Outside a turn the scripts re-run themselves under the venv. Both sides have to agree on
    where it is, or a call lands on a different interpreter depending on how it was started."""
    for script in ("run-tool.py", "run-agent.py"):
        text = (runner.PROJECT_ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert '".venv" / "Scripts" / "python.exe" if sys.platform == "win32"' in text
        assert '".venv" / "bin" / "python"' in text


def test_a_turn_runs_a_real_tool_end_to_end(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    book.active.title = "Sheet A"
    book.save(tmp_path / "book.xlsx")

    result = runner.run_tool(TOOL, ["list-sheets", "--path", str(tmp_path / "book.xlsx")],
                             env={}, inherit_env=False)

    assert result["ok"] is True
    assert [sheet["title"] for sheet in result["data"]["sheets"]] == ["Sheet A"]
