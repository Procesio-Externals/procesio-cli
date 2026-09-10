"""Exercise installed upstream skills through real CLI subprocesses."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _run(script, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=30)


def _get(*args):
    result = _run("get-skill.py", *args)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


@pytest.mark.parametrize("name", ["procesio-expert", "sql-server-optimizer"])
def test_original_skills_metadata_content_index_and_retrieval(name):
    metadata = _get(name)
    assert {"name", "description", "version", "path", "skill_md"} <= metadata.keys()
    assert metadata["name"] == name
    assert "body" not in metadata and "resources" not in metadata
    content = _get(name, "--content")
    index = _get(name, "--index")
    assert "body" not in index
    assert content["body"] and not content["body"].startswith("---")
    for category in ("references", "scripts", "assets", "resources"):
        assert content[category] == index[category]
    for item in index["resources"]:
        assert "content" not in item
        expected = ROOT / "skills" / name / item["path"]
        try:
            text = expected.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Original export-tables.sql is not UTF-8: indexed, not transcoded.
            result = _run("get-skill.py", name, "--resource", item["path"])
            assert result.returncode == 2 and result.stderr == ""
            assert json.loads(result.stdout)["error"]["code"] == "skill_resource_not_text"
            continue
        resource = _get(name, "--resource", item["path"])
        assert "body" not in resource and "resources" not in resource
        assert resource["resource"]["content"] == text
        assert resource["resource"]["size"] == expected.stat().st_size
    if name == "sql-server-optimizer":
        assert "references/scripts/export-tables.sql" in index["references"]


def test_list_skills_json_retains_original_skills():
    result = _run("list-skills.py", "--json")
    assert result.returncode == 0 and result.stderr == ""
    entries = json.loads(result.stdout)
    assert {e["name"] for e in entries} >= {"procesio-expert", "sql-server-optimizer"}
    assert all(e["ready"] for e in entries)


@pytest.mark.parametrize("args,code", [
    (["missing-skill"], "not_found"),
    (["procesio-expert", "--resource", "references/missing.md"], "skill_resource_not_found"),
    (["procesio-expert", "--resource", "../outside"], "invalid_skill_resource"),
    (["procesio-expert", "--resource", ""], "invalid_skill_resource"),
    (["procesio-expert", "--content", "--index"], "invalid_args"),
    (["procesio-expert", "--resource"], "invalid_args"),
])
def test_cli_failures_are_one_json_object(args, code):
    result = _run("get-skill.py", *args)
    assert result.returncode == 2 and result.stderr == ""
    error = json.loads(result.stdout)["error"]
    assert error["code"] == code
    assert {"code", "message", "details"} == error.keys()


@pytest.mark.parametrize("args", [[], ["--help"]])
def test_cli_help_remains_successful(args):
    result = _run("get-skill.py", *args)
    assert result.returncode == 0 and result.stderr == ""
    assert "--content" in result.stdout
