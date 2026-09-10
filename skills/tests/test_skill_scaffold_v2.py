from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "agent-skill-engineer" / "scripts" / "scaffold_skill.py"
SPEC = importlib.util.spec_from_file_location("agent_skill_scaffold_v2", SCRIPT)
assert SPEC and SPEC.loader
SCAFFOLD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SCAFFOLD
SPEC.loader.exec_module(SCAFFOLD)


def _frontmatter(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = lines[1:].index("---") + 1
    value = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(value, dict)
    return value


def test_governed_scaffold_preserves_v1_contract_and_adds_causal_evidence_fields(tmp_path):
    args = SCAFFOLD._parser().parse_args(
        [
            "incident-triage",
            "--root",
            str(tmp_path),
            "--description",
            "Triage recurring incidents. Use when an incident report needs a bounded diagnostic workflow.",
            "--profile",
            "governed",
            "--owner",
            "platform team",
            "--baseline-version",
            "abc123",
            "--trigger",
            "triage a recurring production incident",
            "--non-trigger",
            "implement the incident-management product itself",
            "--target-client",
            "Agent Skills compatible coding agents",
            "--evidence-tier",
            "3",
        ]
    )
    result = SCAFFOLD.scaffold(args)
    target = tmp_path / "incident-triage"
    frontmatter = _frontmatter(target / "SKILL.md")
    body = (target / "SKILL.md").read_text(encoding="utf-8")
    suite = json.loads((target / "evals" / "evals.json").read_text(encoding="utf-8"))

    assert result["schema_version"] == 2
    assert result["evidence_tier"] == 3
    assert frontmatter["name"] == "incident-triage"
    assert frontmatter["owner"] == "platform team"
    assert frontmatter["eval_suite"] == "evals/evals.json"
    assert frontmatter["metadata"]["status"] == "draft"
    assert "## Causal contract" in body
    assert "Protected successes" in body
    assert "repairs and regressions" in body
    assert "implement the incident-management product itself" in body
    assert suite["rubric_contract"] == "fixed-jury-rubric-v2"
    assert suite["evidence_tier"] == 3
    assert suite["experiment_contract"]["test"].startswith("untouched")
    assert {case["kind"] for case in suite["cases"]} == {
        "positive",
        "negative",
        "overlap",
        "pressure",
    }


def test_scaffold_still_refuses_overwrite_and_escape(tmp_path):
    parser = SCAFFOLD._parser()
    args = parser.parse_args(
        [
            "demo-skill",
            "--root",
            str(tmp_path),
            "--description",
            "Create a demo. Use when a reusable demo workflow is requested.",
        ]
    )
    SCAFFOLD.scaffold(args)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        SCAFFOLD.scaffold(args)
    with pytest.raises(ValueError, match="lowercase"):
        SCAFFOLD.scaffold(argparse.Namespace(**{**vars(args), "name": "../escape"}))


def test_failed_governed_scaffold_leaves_no_partial_directory(tmp_path):
    args = SCAFFOLD._parser().parse_args(
        [
            "governed-skill",
            "--root",
            str(tmp_path),
            "--description",
            "Govern work. Use when the governed workflow is required.",
            "--profile",
            "governed",
            "--owner",
            "team",
            "--baseline-version",
            "abc",
        ]
    )
    with pytest.raises(ValueError, match="--trigger"):
        SCAFFOLD.scaffold(args)
    assert not (tmp_path / "governed-skill").exists()
