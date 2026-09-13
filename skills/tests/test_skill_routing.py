from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "evaluate-skill-routing.py"
SPEC = importlib.util.spec_from_file_location("evaluate_skill_routing", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

from tools._lib.manifest import load_skill


def _governed_names(skills_root: Path) -> set[str]:
    """Skills that opt into the governance/eval discipline, by the `source_policy`
    marker. The routing corpus is authored for this portfolio universe; AAT also
    hosts imported/portable skills whose prompts legitimately fall outside it, so
    the live routing gate is scored over the governed set, not the whole tree
    (procesio-cli's `skills/` IS the portfolio, so there the two coincide)."""
    names: set[str] = set()
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        try:
            manifest = load_skill(skill_md)
        except Exception:  # noqa: BLE001 - a broken skill is validate-skills' job
            continue
        if manifest.source_policy:
            names.add(manifest.name)
    return names


def test_frozen_v2_baseline_is_reproducible():
    report = module.evaluate(
        module.load_catalog(ROOT / "skills" / "evals" / "baseline-catalog.json"),
        module.load_cases(ROOT / "skills" / "evals" / "routing.json"),
    )
    expected = json.loads((ROOT / "skills" / "evals" / "baseline-routing-v2.json").read_text(encoding="utf-8"))
    assert module.projection(report) == expected


def test_live_skill_descriptions_clear_gate_three():
    governed = _governed_names(ROOT / "skills")
    assert governed, "no governed skills found (source_policy marker missing?)"
    live = [s for s in module.load_skills(ROOT / "skills") if s.name in governed]
    report = module.evaluate(
        live,
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
