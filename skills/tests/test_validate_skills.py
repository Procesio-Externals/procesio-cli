from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate-skills.py"
SPEC = importlib.util.spec_from_file_location("validate_skills", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _skill(root: Path, folder: str = "demo", name: str = "demo", body: str = "# Demo") -> Path:
    path = root / "skills" / folder / "SKILL.md"
    _write(path, f"---\nname: {name}\ndescription: Use when testing the demo skill.\n---\n\n{body}\n")
    return path


def test_valid_skill_has_no_blocking_findings(tmp_path):
    _skill(tmp_path)
    assert module.validate_repo(tmp_path / "skills", tmp_path) == []


def test_missing_reference_and_folder_mismatch_are_detected(tmp_path):
    _skill(tmp_path, folder="wrong", name="demo", body="Read `references/missing.md`.")
    codes = {finding.code for finding in module.validate_repo(tmp_path / "skills", tmp_path)}
    assert {"folder-name-mismatch", "missing-reference"} <= codes


def test_nested_scripts_are_rejected(tmp_path):
    _skill(tmp_path)
    _write(tmp_path / "skills" / "demo" / "references" / "scripts" / "dump.sql", "select 1")
    codes = {finding.code for finding in module.validate_repo(tmp_path / "skills", tmp_path)}
    assert {"nested-resource", "script-in-references"} <= codes


def test_python_bytecode_caches_are_ignored(tmp_path):
    _skill(tmp_path)
    _write(
        tmp_path
        / "skills"
        / "demo"
        / "scripts"
        / "__pycache__"
        / "helper.cpython-312.pyc",
        "transient bytecode fixture",
    )

    assert module.validate_repo(tmp_path / "skills", tmp_path) == []


def test_command_examples_must_name_real_actions(tmp_path):
    _write(tmp_path / "tools" / "widget" / "tool.yaml", """
name: widget
description: widgets
actions:
  - name: list-things
    args:
      - {name: limit, type: integer}
""".lstrip())
    _skill(tmp_path, body=(
        "`python scripts/run-tool.py widget list-things --limit 1`\n\n"
        "`python scripts/run-tool.py widget delete-world`"
    ))
    findings = module.validate_repo(tmp_path / "skills", tmp_path)
    assert any(finding.code == "unknown-action" and "delete-world" in finding.message
               for finding in findings)
    assert not any(finding.code == "unknown-action" and "list-things" in finding.message
                   for finding in findings)


def test_waiver_matches_only_the_declared_finding():
    finding = module.Finding("error", "missing-reference", "demo", "SKILL.md", "x")
    assert module._waived(finding, [{"skill": "demo", "code": "missing-*", "path": "*"}])
    assert not module._waived(finding, [{"skill": "other", "code": "missing-*"}])


def test_committed_waiver_file_is_valid_json():
    data = json.loads((ROOT / "skills" / "evals" / "validation-baseline.json").read_text(encoding="utf-8"))
    assert isinstance(data["allow"], list)
