from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "evaluate-skill-routing.py"
SPEC = importlib.util.spec_from_file_location("evaluate_skill_routing", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_frozen_v2_baseline_is_reproducible():
    report = module.evaluate(
        module.load_catalog(ROOT / "skills" / "evals" / "baseline-catalog.json"),
        module.load_cases(ROOT / "skills" / "evals" / "routing.json"),
    )
    expected = json.loads((ROOT / "skills" / "evals" / "baseline-routing-v2.json").read_text(encoding="utf-8"))
    assert module.projection(report) == expected


def test_live_skill_descriptions_clear_gate_three():
    report = module.evaluate(
        module.load_skills(ROOT / "skills"),
        module.load_cases(ROOT / "skills" / "evals" / "routing.json"),
    )
    assert report["routing_accuracy"] >= 0.95
    assert report["collision_rate"] == 0


def test_explicit_exclusion_prevents_postgresql_false_positive():
    skills = [module.Skill(
        "sql-server-optimizer",
        "Analyze SQL Server T-SQL; do not use for PostgreSQL or MySQL.",
    )]
    assert module.select("Tune this PostgreSQL query", skills)[0] is None


def test_hyphenated_tsql_matches():
    skills = [module.Skill(
        "sql-server-optimizer",
        "Analyze SQL Server T-SQL predicates and sargability.",
    )]
    assert module.select(
        "Why is this T-SQL predicate not sargable?", skills
    )[0] == "sql-server-optimizer"
