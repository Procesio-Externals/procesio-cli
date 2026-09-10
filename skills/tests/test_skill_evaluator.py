from __future__ import annotations

import importlib.util
import json
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "evaluate-skills.py"
SPEC = importlib.util.spec_from_file_location("evaluate_skills", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_target_corpus_has_unique_cases_and_all_job_families():
    cases = module._load_cases(ROOT / "skills" / "evals" / "routing.json")
    assert len(cases) >= 40
    assert {case.get("kind") for case in cases} >= {
        "operational", "advisory", "sql", "maintainer", "negative", "overlap"
    }


def test_frozen_baseline_is_reproducible():
    catalog = module.load_catalog(ROOT / "skills" / "evals" / "baseline-catalog.json")
    cases = module._load_cases(ROOT / "skills" / "evals" / "routing.json")
    report = module.evaluate(catalog, cases)
    expected = json.loads((ROOT / "skills" / "evals" / "baseline.json").read_text(encoding="utf-8"))
    assert module._baseline_projection(report) == expected


def test_selector_abstains_when_no_description_matches():
    skills = [module.SkillEntry("sql-server-optimizer", "Use for SQL Server T-SQL query plans")]
    selected, scores = module.select_skill("paint a watercolor bicycle", skills)
    assert selected is None
    assert scores["sql-server-optimizer"] == 0


def test_real_observation_grading_captures_selection_success_and_cost():
    cases = [{"id": "x", "prompt": "x", "expected_skill": "a"}]
    report = module.grade_observations([
        {"case_id": "x", "selected_skill": "a", "task_success": True,
         "total_tokens": 100, "duration_ms": 250}
    ], cases)
    assert report["selection_accuracy"] == 1
    assert report["task_success_rate"] == 1
    assert report["mean_total_tokens"] == 100
    assert report["mean_duration_ms"] == 250


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_observation_success_must_be_boolean(value):
    with pytest.raises(ValueError, match="task_success must be Boolean"):
        module.grade_observations(
            [{"case_id": "x", "selected_skill": "a", "task_success": value}],
            [{"id": "x", "expected_skill": "a"}],
        )


def test_false_observation_does_not_become_a_success():
    report = module.grade_observations(
        [{"case_id": "x", "selected_skill": "a", "task_success": False}],
        [{"id": "x", "expected_skill": "a"}],
    )
    assert report["task_success_rate"] == 0
