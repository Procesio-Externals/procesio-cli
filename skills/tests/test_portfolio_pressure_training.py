"""Validate new development cases without modifying or scoring frozen Gate 5."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_development_cases_are_explicit_fixed_and_separate():
    path = ROOT / "skills/evals/portfolio-pressure-training-v1.json"
    suite = json.loads(path.read_text(encoding="utf-8"))
    assert suite["schema_version"] == 2
    assert suite["evidence_role"] == "development_only_not_holdout"
    assert suite["rubric_contract"] == "fixed-jury-rubric-v2"
    cases = suite["cases"]
    assert len(cases) == 6
    assert len({case["id"] for case in cases}) == 6
    for case in cases:
        assert case["kind"] == "pressure"
        assert case["prompt"]
        assert (ROOT / "skills" / case["expected_skill"] / "SKILL.md").is_file()
        rubric = case["expected_output"]
        assert rubric["rubric_version"] == 1
        assert 2 <= len(rubric["criteria"]) <= 8
        ids = [item["id"] for item in rubric["criteria"]]
        assert len(set(ids)) == len(ids)
        for criterion in rubric["criteria"]:
            assert re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", criterion["id"])
            assert criterion["description"].startswith("Pass only when")
            assert criterion["required"] is True
    virtual = next(case for case in cases if case["id"] == "copied-resource-root-and-escape")
    assert "references/context.md" in virtual["prompt"]
    assert "references/nested/" not in virtual["prompt"]
    historical = json.loads((ROOT / "skills/evals/behavioral.json").read_text(encoding="utf-8"))
    assert not {case["id"] for case in cases} & {case["id"] for case in historical["cases"]}
