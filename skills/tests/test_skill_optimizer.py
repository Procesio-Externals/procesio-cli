from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "agent-skill-engineer" / "scripts" / "optimize_skill.py"
SPEC = importlib.util.spec_from_file_location("agent_skill_optimizer", SCRIPT)
assert SPEC and SPEC.loader
OPT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = OPT
SPEC.loader.exec_module(OPT)


def _write_skill(root: Path, body: str = "Use stable IDs.\n") -> Path:
    root.mkdir(parents=True)
    (root / "references").mkdir()
    (root / "evals").mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Use when testing a demo skill.\n---\n\n"
        "# Demo Skill\n\n## Workflow\n\n" + body,
        encoding="utf-8",
    )
    (root / "references" / "guide.md").write_text("# Guide\n\nStable detail.\n", encoding="utf-8")
    (root / "evals" / "evals.json").write_text('{"immutable":true}\n', encoding="utf-8")
    return root


def _objective(path: Path, **overrides) -> Path:
    value = {
        "schema_version": 1,
        "primary_metric": "task_success_rate",
        "direction": "maximize",
        "min_delta": 0.05,
        "minimum_valid_pairs": 4,
        "plateau_limit": 2,
        "edit_budget": {
            "max_changed_files": 2,
            "max_added_lines": 8,
            "max_deleted_lines": 8,
            "max_total_line_changes": 12,
            "max_binary_bytes": 0,
        },
        "allowed_paths": ["SKILL.md", "references/*.md", "scripts/*.py", "assets/*"],
        "forbidden_paths": [],
        "hard_constraints": [
            {"metric": "collision_rate", "op": "<=", "value": 0},
            {"metric": "safety_violations", "op": "==", "value": 0},
            {"metric": "regression_rate", "op": "<=", "value": 0},
        ],
        "secondary_metrics": [
            {
                "metric": "median_tokens",
                "direction": "minimize",
                "max_relative_regression": 0.15,
            }
        ],
    }
    value.update(overrides)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _identity(corpus: str = "validation-corpus") -> dict[str, str]:
    return {
        "corpus_fingerprint": corpus,
        "rubric_fingerprint": "rubric-v1",
        "model_fingerprint": "model-v1",
        "harness_fingerprint": "harness-v1",
        "pairing_fingerprint": f"pairs-{corpus}",
    }


def _metrics(success: float, *, tokens: float = 100, regression: float = 0) -> dict[str, float]:
    return {
        "task_success_rate": success,
        "collision_rate": 0,
        "safety_violations": 0,
        "regression_rate": regression,
        "median_tokens": tokens,
    }


def _baseline_report(path: Path, skill: Path, *, corpus: str = "validation-corpus") -> Path:
    report = {
        "schema_version": 1,
        "report_type": "baseline",
        "split": "validation",
        "skill_fingerprint": OPT.tree_fingerprint(skill),
        **_identity(corpus),
        "valid_pairs": 4,
        "infrastructure_failures": 0,
        "metrics": _metrics(0.5),
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _pair_report(
    path: Path,
    candidate: str,
    parent: str,
    *,
    split: str = "validation",
    corpus: str = "validation-corpus",
    candidate_success: float = 0.75,
    parent_success: float = 0.5,
    candidate_tokens: float = 105,
    regression: float = 0,
    outcomes: dict[str, int] | None = None,
) -> Path:
    report = {
        "schema_version": 1,
        "report_type": "paired",
        "split": split,
        "candidate_fingerprint": candidate,
        "parent_fingerprint": parent,
        **_identity(corpus),
        "valid_pairs": 4,
        "infrastructure_failures": 0,
        "candidate_metrics": _metrics(candidate_success, tokens=candidate_tokens, regression=regression),
        "parent_metrics": _metrics(parent_success),
        "paired_outcomes": outcomes
        or {"repairs": 1, "regressions": 0, "preserved_successes": 2, "unresolved_failures": 1},
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _init(tmp_path: Path) -> tuple[Path, Path, Path]:
    skill = _write_skill(tmp_path / "demo-skill")
    objective = _objective(tmp_path / "objective.json")
    baseline = _baseline_report(tmp_path / "baseline.json", skill)
    workspace = tmp_path / "workspace"
    result = OPT.command_init(
        argparse.Namespace(
            skill_root=skill,
            workspace=workspace,
            objective=objective,
            baseline_report=baseline,
        )
    )
    assert result["event"] == "initialized"
    return skill, workspace, objective


def _candidate(tmp_path: Path, skill: Path, text: str = "Use stable IDs.\nReconcile unknown writes.\n") -> Path:
    candidate = tmp_path / "candidate"
    shutil.copytree(skill, candidate)
    path = candidate / "SKILL.md"
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("Use stable IDs.\n", text), encoding="utf-8")
    return candidate


def _stage(tmp_path: Path, skill: Path, workspace: Path) -> tuple[Path, dict]:
    candidate = _candidate(tmp_path, skill)
    result = OPT.command_stage(
        argparse.Namespace(
            workspace=workspace,
            candidate_root=candidate,
            hypothesis="Reconcile unknown writes before retrying.",
        )
    )
    assert result["candidate_id"] == "c0001"
    return candidate, result


def test_init_freezes_identical_baseline_and_best_snapshots(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))

    assert state["baseline_fingerprint"] == OPT.tree_fingerprint(skill)
    assert OPT.tree_fingerprint(workspace / "snapshots" / "baseline") == state["baseline_fingerprint"]
    assert OPT.tree_fingerprint(workspace / "snapshots" / "best") == state["best_fingerprint"]
    assert (workspace / "ledger.jsonl").read_text(encoding="utf-8").count("initialized") == 1


def test_stage_rejects_evaluation_tampering(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    candidate = _candidate(tmp_path, skill)
    (candidate / "evals" / "evals.json").write_text('{"immutable":false}\n', encoding="utf-8")

    with pytest.raises(OPT.OptimizationError) as error:
        OPT.command_stage(
            argparse.Namespace(workspace=workspace, candidate_root=candidate, hypothesis="Cheat")
        )
    assert error.value.code == "forbidden_path_changed"


def test_stage_enforces_textual_edit_budget(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    candidate = _candidate(tmp_path, skill, "\n".join(f"Rule {index}" for index in range(30)) + "\n")

    with pytest.raises(OPT.OptimizationError) as error:
        OPT.command_stage(
            argparse.Namespace(workspace=workspace, candidate_root=candidate, hypothesis="Too broad")
        )
    assert error.value.code == "edit_budget_exceeded"
    assert "added_lines" in error.value.details


def test_strict_paired_validation_accepts_and_replaces_best(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    _candidate_root, staged = _stage(tmp_path, skill, workspace)
    report = _pair_report(
        tmp_path / "candidate-report.json",
        staged["candidate_fingerprint"],
        staged["parent_fingerprint"],
    )

    result = OPT.command_decide(
        argparse.Namespace(workspace=workspace, candidate_id="c0001", report=report)
    )
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))

    assert result["accepted"] is True
    assert state["best_candidate_id"] == "c0001"
    assert state["best_fingerprint"] == staged["candidate_fingerprint"]
    assert "Reconcile unknown writes" in (workspace / "snapshots" / "best" / "SKILL.md").read_text(encoding="utf-8")


def test_non_improvement_is_rejected_and_best_remains_immutable(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    _candidate_root, staged = _stage(tmp_path, skill, workspace)
    report = _pair_report(
        tmp_path / "candidate-report.json",
        staged["candidate_fingerprint"],
        staged["parent_fingerprint"],
        candidate_success=0.52,
    )

    result = OPT.command_decide(
        argparse.Namespace(workspace=workspace, candidate_id="c0001", report=report)
    )
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))

    assert result["accepted"] is False
    assert state["best_candidate_id"] == "baseline"
    assert state["best_fingerprint"] == state["baseline_fingerprint"]
    assert "primary improvement" in result["reasons"][0]
    assert "candidate_rejected" in (workspace / "ledger.jsonl").read_text(encoding="utf-8")


def test_report_identity_and_pair_counts_are_enforced(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    _candidate_root, staged = _stage(tmp_path, skill, workspace)
    report = _pair_report(
        tmp_path / "bad-report.json",
        staged["candidate_fingerprint"],
        staged["parent_fingerprint"],
        corpus="different-validation-corpus",
    )
    with pytest.raises(OPT.OptimizationError) as identity_error:
        OPT.command_decide(
            argparse.Namespace(workspace=workspace, candidate_id="c0001", report=report)
        )
    assert identity_error.value.code == "evaluation_identity_mismatch"

    bad_counts = json.loads(report.read_text(encoding="utf-8"))
    bad_counts.update(_identity("validation-corpus"))
    bad_counts["paired_outcomes"]["repairs"] = 4
    report.write_text(json.dumps(bad_counts), encoding="utf-8")
    with pytest.raises(OPT.OptimizationError) as count_error:
        OPT.command_decide(
            argparse.Namespace(workspace=workspace, candidate_id="c0001", report=report)
        )
    assert count_error.value.code == "invalid_report"


def test_hard_constraint_rejects_apparent_average_gain(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    _candidate_root, staged = _stage(tmp_path, skill, workspace)
    report = _pair_report(
        tmp_path / "unsafe-report.json",
        staged["candidate_fingerprint"],
        staged["parent_fingerprint"],
        candidate_success=0.9,
        regression=0.25,
        outcomes={"repairs": 2, "regressions": 1, "preserved_successes": 1, "unresolved_failures": 0},
    )

    result = OPT.command_decide(
        argparse.Namespace(workspace=workspace, candidate_id="c0001", report=report)
    )
    assert result["accepted"] is False
    assert any("hard constraint failed" in item for item in result["reasons"])


def test_finalize_requires_untouched_paired_test_and_no_overwrite(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    _candidate_root, staged = _stage(tmp_path, skill, workspace)
    validation = _pair_report(
        tmp_path / "candidate-report.json",
        staged["candidate_fingerprint"],
        staged["parent_fingerprint"],
    )
    OPT.command_decide(argparse.Namespace(workspace=workspace, candidate_id="c0001", report=validation))
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))

    leaked = _pair_report(
        tmp_path / "leaked-test.json",
        state["best_fingerprint"],
        state["baseline_fingerprint"],
        split="test",
        corpus="validation-corpus",
    )
    with pytest.raises(OPT.OptimizationError) as leakage:
        OPT.command_finalize(
            argparse.Namespace(workspace=workspace, report=leaked, output=tmp_path / "final")
        )
    assert leakage.value.code == "test_validation_leakage"

    test_report = _pair_report(
        tmp_path / "test-report.json",
        state["best_fingerprint"],
        state["baseline_fingerprint"],
        split="test",
        corpus="untouched-test-corpus",
        candidate_success=0.8,
    )
    output = tmp_path / "final"
    result = OPT.command_finalize(
        argparse.Namespace(workspace=workspace, report=test_report, output=output)
    )

    assert result["event"] == "finalized"
    assert OPT.tree_fingerprint(output) == state["best_fingerprint"]
    with pytest.raises(OPT.OptimizationError) as overwrite:
        OPT.command_finalize(
            argparse.Namespace(workspace=workspace, report=test_report, output=output)
        )
    assert overwrite.value.code == "output_exists"


def test_secondary_cost_regression_blocks_promotion(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    _candidate_root, staged = _stage(tmp_path, skill, workspace)
    report = _pair_report(
        tmp_path / "expensive-report.json",
        staged["candidate_fingerprint"],
        staged["parent_fingerprint"],
        candidate_success=0.9,
        candidate_tokens=130,
    )

    result = OPT.command_decide(
        argparse.Namespace(workspace=workspace, candidate_id="c0001", report=report)
    )
    assert result["accepted"] is False
    assert "secondary metric regressed beyond tolerance: median_tokens" in result["reasons"]


def test_plateau_closes_the_experiment_after_registered_rejections(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    for index in range(2):
        candidate = tmp_path / f"candidate-{index}"
        shutil.copytree(skill, candidate)
        path = candidate / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + f"\nCandidate {index}.\n", encoding="utf-8")
        staged = OPT.command_stage(
            argparse.Namespace(workspace=workspace, candidate_root=candidate, hypothesis=f"Rejected {index}")
        )
        report = _pair_report(
            tmp_path / f"rejected-{index}.json",
            staged["candidate_fingerprint"],
            staged["parent_fingerprint"],
            candidate_success=0.5,
        )
        result = OPT.command_decide(
            argparse.Namespace(workspace=workspace, candidate_id=staged["candidate_id"], report=report)
        )
        assert result["accepted"] is False

    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "plateau"
    new_candidate = _candidate(tmp_path / "later", skill)
    with pytest.raises(OPT.OptimizationError) as error:
        OPT.command_stage(
            argparse.Namespace(workspace=workspace, candidate_root=new_candidate, hypothesis="Too late")
        )
    assert error.value.code == "experiment_not_open"


def test_objective_and_snapshot_drift_are_detected(tmp_path):
    _skill, workspace, _objective_path = _init(tmp_path)
    objective = json.loads((workspace / "objective.json").read_text(encoding="utf-8"))
    objective["min_delta"] = 0
    (workspace / "objective.json").write_text(json.dumps(objective), encoding="utf-8")
    with pytest.raises(OPT.OptimizationError) as objective_error:
        OPT.command_status(argparse.Namespace(workspace=workspace))
    assert objective_error.value.code == "objective_drift"

    objective["min_delta"] = 0.05
    (workspace / "objective.json").write_text(json.dumps(objective), encoding="utf-8")
    best = workspace / "snapshots" / "best" / "SKILL.md"
    best.write_text(best.read_text(encoding="utf-8") + "\nOut-of-band edit.\n", encoding="utf-8")
    with pytest.raises(OPT.OptimizationError) as snapshot_error:
        OPT.command_status(argparse.Namespace(workspace=workspace))
    assert snapshot_error.value.code == "snapshot_drift"


def test_symlink_and_invalid_candidate_id_cannot_escape_controller(tmp_path):
    skill, workspace, _objective_path = _init(tmp_path)
    candidate = _candidate(tmp_path, skill)
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    link = candidate / "references" / "outside.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(OPT.OptimizationError) as link_error:
        OPT.command_stage(
            argparse.Namespace(workspace=workspace, candidate_root=candidate, hypothesis="Escape")
        )
    assert link_error.value.code == "symlink_not_allowed"

    with pytest.raises(OPT.OptimizationError) as id_error:
        OPT.command_decide(
            argparse.Namespace(workspace=workspace, candidate_id="../../outside", report=tmp_path / "x")
        )
    assert id_error.value.code == "invalid_candidate_id"


def test_ignored_environment_files_do_not_enter_fingerprint_or_snapshot(tmp_path):
    skill = _write_skill(tmp_path / "demo-skill")
    (skill / ".venv" / "cache").mkdir(parents=True)
    (skill / ".venv" / "cache" / "secret.bin").write_bytes(b"not package state")
    initial = OPT.tree_fingerprint(skill)
    (skill / ".venv" / "cache" / "secret.bin").write_bytes(b"changed")
    assert OPT.tree_fingerprint(skill) == initial

    objective = _objective(tmp_path / "objective.json")
    baseline = _baseline_report(tmp_path / "baseline.json", skill)
    workspace = tmp_path / "workspace"
    OPT.command_init(
        argparse.Namespace(skill_root=skill, workspace=workspace, objective=objective, baseline_report=baseline)
    )
    assert not (workspace / "snapshots" / "baseline" / ".venv").exists()


def test_strict_json_rejects_non_finite_metrics(tmp_path):
    skill = _write_skill(tmp_path / "demo-skill")
    objective = _objective(tmp_path / "objective.json")
    fingerprint = OPT.tree_fingerprint(skill)
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"schema_version":1,"report_type":"baseline","split":"validation",'
        f'"skill_fingerprint":"{fingerprint}",'
        '"corpus_fingerprint":"c","rubric_fingerprint":"r",'
        '"model_fingerprint":"m","harness_fingerprint":"h",'
        '"pairing_fingerprint":"p","valid_pairs":4,"metrics":{'
        '"task_success_rate":NaN,"collision_rate":0,"safety_violations":0,'
        '"regression_rate":0,"median_tokens":100}}',
        encoding="utf-8",
    )
    with pytest.raises(OPT.OptimizationError) as error:
        OPT.command_init(
            argparse.Namespace(
                skill_root=skill,
                workspace=tmp_path / "workspace",
                objective=objective,
                baseline_report=path,
            )
        )
    assert error.value.code == "invalid_json"
