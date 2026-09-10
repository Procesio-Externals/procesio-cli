from __future__ import annotations

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "skills" / "agent-skill-engineer"
SKILL = META / "SKILL.md"
STANDARD = META / "references" / "field-gate-standard.md"


def _frontmatter(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = lines[1:].index("---") + 1
    value = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(value, dict)
    return value


def test_meta_skill_routes_field_trials_to_fixed_gate_standard():
    skill = SKILL.read_text(encoding="utf-8")
    frontmatter = _frontmatter(SKILL)

    # The field contract landed in 2.0.1; later repairs must retain it, not
    # keep an obsolete exact version merely to satisfy this regression test.
    version = tuple(int(part) for part in frontmatter["version"].split("."))
    assert len(version) == 3 and version >= (2, 0, 1)
    assert frontmatter["baseline_version"] == "a47135373c4c0598391e808939397cd139234afd"
    assert "`references/field-gate-standard.md`" in skill
    assert "Host code—not the acting agent—decides pass" in skill
    assert "full parent/child execution budget" in skill
    assert "Never weaken a completed gate" in skill


def test_field_gate_standard_is_general_and_host_enforced():
    text = STANDARD.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    for phrase in (
        "ordered required check IDs",
        "fingerprint of the complete skill package",
        "including `SKILL.md`, references, scripts, and assets",
        "The host computes the aggregate verdict",
        "complete causal execution tree",
        "A required outcome that fails is not converted into a gap",
        "A phase verdict covers only that phase's frozen obligations",
        "does not force every later phase to report `passed_with_gap`",
        "compute and preserve both verdict scopes separately",
        "Credential exposure is monotonic for the exposed credential",
        "does not make a completed `no_secret_exposure` check true",
        "prove the old value is rejected",
        "invalidate stale exports or reports",
        "preserve the original report",
        "separately approved versioned remediation contract",
        "Avoid case-specific overfitting",
        "Project-specific ID, title, payload, or workaround",
    ):
        assert phrase in normalized

    # General doctrine must not embed installation IDs or private evidence paths.
    assert not re.search(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", text)
    assert "scratchpad/" not in text


def test_review_and_evaluation_standards_fail_closed_on_field_gate_drift():
    review = (META / "references" / "review-standard.md").read_text(encoding="utf-8")
    evaluation = (META / "references" / "evaluation-standard.md").read_text(encoding="utf-8")

    assert "acting agent invent required checks" in review
    assert "complete causal execution counts" in review
    assert "failed required field outcome" in review
    assert "deterministic host code should validate exact IDs and order" in evaluation
    assert "does not retroactively permit a gap" in evaluation
    assert "full parent/child execution budget" in evaluation
