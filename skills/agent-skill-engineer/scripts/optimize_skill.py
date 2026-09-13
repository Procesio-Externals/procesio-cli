#!/usr/bin/env python3
"""Enforce a reproducible, held-out Agent Skill optimization loop.

The controller makes no model or network calls. It snapshots packages, confines
candidate changes, enforces a textual edit budget, verifies evaluation identity,
promotes only strict paired-validation improvements and records rejected hypotheses.
Final-test checks do not enforce one-shot custody: finalize permits resubmission
and overwrites its saved report. An external evidence owner must prevent retries.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCHEMA_VERSION = 1
IGNORED_PARTS = {".git", ".venv", "__pycache__", "node_modules"}
ALWAYS_FORBIDDEN = ("evals", "evals/*", "evals/**", ".git", ".git/*", ".git/**")
DIRECTIONS = {"maximize", "minimize"}
OPS = {"<", "<=", "==", "!=", ">=", ">"}
CANDIDATE_ID_RE = re.compile(r"^c[0-9]{4,}$")
IDENTITY_FIELDS = (
    "corpus_fingerprint",
    "rubric_fingerprint",
    "model_fingerprint",
    "harness_fingerprint",
    "pairing_fingerprint",
)
OUTCOME_FIELDS = ("repairs", "regressions", "preserved_successes", "unresolved_failures")


class OptimizationError(ValueError):
    """Stable user-correctable experiment failure."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class DiffSummary:
    changed_files: int
    added_lines: int
    deleted_lines: int
    total_line_changes: int
    binary_bytes: int
    paths: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed_files": self.changed_files,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "total_line_changes": self.total_line_changes,
            "binary_bytes": self.binary_bytes,
            "paths": list(self.paths),
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _json_read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except FileNotFoundError as exc:
        raise OptimizationError("file_not_found", f"file does not exist: {path}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise OptimizationError("invalid_json", f"invalid strict JSON in {path}: {exc}") from exc


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _append_ledger(workspace: Path, event: dict[str, Any]) -> None:
    row = {"recorded_at": _now(), **event}
    path = workspace / "ledger.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _fingerprint_json(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_ignored(relative: PurePosixPath) -> bool:
    return relative.suffix == ".pyc" or any(part in IGNORED_PARTS for part in relative.parts)


def _files(root: Path) -> dict[str, Path]:
    root = root.expanduser().resolve()
    if not (root / "SKILL.md").is_file():
        raise OptimizationError("invalid_skill_root", f"SKILL.md is missing under {root}")
    result: dict[str, Path] = {}
    for path in root.rglob("*"):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _is_ignored(relative):
            continue
        if path.is_symlink():
            raise OptimizationError(
                "symlink_not_allowed",
                f"skill packages under optimization may not contain symlinks: {relative}",
            )
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise OptimizationError("path_escape", f"file resolves outside the skill root: {relative}") from exc
        result[relative.as_posix()] = resolved
    return result


def tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, path in sorted(_files(root).items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        raise OptimizationError("destination_exists", f"destination already exists: {destination}")
    files = _files(source)
    destination.mkdir(parents=True)
    try:
        for relative, source_file in sorted(files.items()):
            target = destination.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target, follow_symlinks=False)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _replace_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.parent / f".{destination.name}.replacement"
    previous = destination.parent / f".{destination.name}.previous"
    shutil.rmtree(temp, ignore_errors=True)
    shutil.rmtree(previous, ignore_errors=True)
    _copy_tree(source, temp)
    if destination.exists():
        destination.replace(previous)
    try:
        temp.replace(destination)
    except Exception:
        if previous.exists() and not destination.exists():
            previous.replace(destination)
        raise
    else:
        shutil.rmtree(previous, ignore_errors=True)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.expanduser().resolve().relative_to(parent.expanduser().resolve())
        return True
    except ValueError:
        return False


def _safe_patterns(label: str, value: Any, *, required: bool) -> list[str]:
    if not isinstance(value, list) or (required and not value) or not all(isinstance(item, str) for item in value):
        qualifier = "non-empty " if required else ""
        raise OptimizationError("invalid_objective", f"{label} must be a {qualifier}string list")
    patterns: list[str] = []
    for raw in value:
        pattern = raw.replace("\\", "/").strip()
        posix = PurePosixPath(pattern)
        if not pattern or posix.is_absolute() or ".." in posix.parts:
            raise OptimizationError("invalid_objective", f"unsafe {label} pattern: {raw}")
        patterns.append(pattern)
    return patterns


def _validate_objective(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OptimizationError("invalid_objective", "objective must be a JSON object")
    objective = dict(raw)
    if objective.get("schema_version") != SCHEMA_VERSION:
        raise OptimizationError("invalid_objective", f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(objective.get("primary_metric"), str) or not objective["primary_metric"].strip():
        raise OptimizationError("invalid_objective", "primary_metric must be a non-empty string")
    if objective.get("direction") not in DIRECTIONS:
        raise OptimizationError("invalid_objective", "direction must be maximize or minimize")
    if not _finite_number(objective.get("min_delta")) or objective["min_delta"] < 0:
        raise OptimizationError("invalid_objective", "min_delta must be a finite non-negative number")

    minimum_pairs = objective.get("minimum_valid_pairs", 1)
    plateau_limit = objective.get("plateau_limit", 3)
    for key, value in (("minimum_valid_pairs", minimum_pairs), ("plateau_limit", plateau_limit)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise OptimizationError("invalid_objective", f"{key} must be an integer >= 1")

    budget = objective.get("edit_budget")
    budget_keys = (
        "max_changed_files",
        "max_added_lines",
        "max_deleted_lines",
        "max_total_line_changes",
        "max_binary_bytes",
    )
    if not isinstance(budget, dict):
        raise OptimizationError("invalid_objective", "edit_budget must be an object")
    for key in budget_keys:
        value = budget.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise OptimizationError("invalid_objective", f"edit_budget.{key} must be an integer >= 0")

    constraints = objective.get("hard_constraints", [])
    if not isinstance(constraints, list):
        raise OptimizationError("invalid_objective", "hard_constraints must be a list")
    for index, rule in enumerate(constraints):
        if not isinstance(rule, dict) or not isinstance(rule.get("metric"), str) or rule.get("op") not in OPS:
            raise OptimizationError("invalid_objective", f"hard_constraints[{index}] is invalid")
        if not _finite_number(rule.get("value")):
            raise OptimizationError("invalid_objective", f"hard_constraints[{index}].value must be finite")

    secondary = objective.get("secondary_metrics", [])
    if not isinstance(secondary, list):
        raise OptimizationError("invalid_objective", "secondary_metrics must be a list")
    for index, rule in enumerate(secondary):
        if not isinstance(rule, dict) or not isinstance(rule.get("metric"), str):
            raise OptimizationError("invalid_objective", f"secondary_metrics[{index}] is invalid")
        if rule.get("direction") not in DIRECTIONS:
            raise OptimizationError("invalid_objective", f"secondary_metrics[{index}].direction is invalid")
        relative = rule.get("max_relative_regression", 0)
        absolute = rule.get("max_absolute_regression", 0)
        if not _finite_number(relative) or relative < 0:
            raise OptimizationError(
                "invalid_objective", f"secondary_metrics[{index}].max_relative_regression is invalid"
            )
        if not _finite_number(absolute) or absolute < 0:
            raise OptimizationError(
                "invalid_objective", f"secondary_metrics[{index}].max_absolute_regression is invalid"
            )

    objective["minimum_valid_pairs"] = minimum_pairs
    objective["plateau_limit"] = plateau_limit
    objective["allowed_paths"] = _safe_patterns("allowed_paths", objective.get("allowed_paths"), required=True)
    objective["forbidden_paths"] = _safe_patterns(
        "forbidden_paths", objective.get("forbidden_paths", []), required=False
    )
    objective["hard_constraints"] = constraints
    objective["secondary_metrics"] = secondary
    return objective


def _report_identity(report: dict[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    for field in IDENTITY_FIELDS:
        value = report.get(field)
        if not isinstance(value, str) or not value.strip():
            raise OptimizationError("invalid_report", f"report.{field} must be a non-empty string")
        identity[field] = value
    return identity


def _validate_metrics(raw: Any, objective: dict[str, Any], label: str) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise OptimizationError("invalid_report", f"{label} must be an object")
    required = {objective["primary_metric"]}
    required.update(rule["metric"] for rule in objective["hard_constraints"])
    required.update(rule["metric"] for rule in objective["secondary_metrics"])
    metrics: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _finite_number(value):
            raise OptimizationError("invalid_report", f"{label}.{key} must be a finite number")
        metrics[key] = float(value)
    missing = sorted(required - metrics.keys())
    if missing:
        raise OptimizationError("missing_metric", f"{label} is missing metrics: {', '.join(missing)}")
    return metrics


def _validate_common_report(raw: Any, *, split: str, objective: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(raw, dict):
        raise OptimizationError("invalid_report", "evaluation report must be a JSON object")
    report = dict(raw)
    if report.get("schema_version") != SCHEMA_VERSION:
        raise OptimizationError("invalid_report", f"report schema_version must be {SCHEMA_VERSION}")
    if report.get("split") != split:
        raise OptimizationError("wrong_report_split", f"expected {split!r}, got {report.get('split')!r}")
    valid_pairs = report.get("valid_pairs")
    if not isinstance(valid_pairs, int) or isinstance(valid_pairs, bool) or valid_pairs < objective["minimum_valid_pairs"]:
        raise OptimizationError(
            "insufficient_pairs",
            f"report.valid_pairs must be an integer >= {objective['minimum_valid_pairs']}",
        )
    failures = report.get("infrastructure_failures", 0)
    if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
        raise OptimizationError("invalid_report", "infrastructure_failures must be an integer >= 0")
    report["infrastructure_failures"] = failures
    return report, _report_identity(report)


def _validate_baseline_report(
    raw: Any,
    *,
    split: str,
    skill_fingerprint: str,
    objective: dict[str, Any],
) -> dict[str, Any]:
    report, _identity = _validate_common_report(raw, split=split, objective=objective)
    if report.get("report_type") != "baseline":
        raise OptimizationError("invalid_report", "baseline report_type must be 'baseline'")
    if report.get("skill_fingerprint") != skill_fingerprint:
        raise OptimizationError(
            "skill_fingerprint_mismatch",
            "baseline report does not belong to the expected package",
            {"expected": skill_fingerprint, "actual": report.get("skill_fingerprint")},
        )
    report["metrics"] = _validate_metrics(report.get("metrics"), objective, "metrics")
    if report["infrastructure_failures"]:
        raise OptimizationError("unstable_baseline", "baseline report contains infrastructure failures")
    return report


def _validate_paired_outcomes(raw: Any, valid_pairs: int) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise OptimizationError("invalid_report", "paired_outcomes must be an object")
    outcomes: dict[str, int] = {}
    for field in OUTCOME_FIELDS:
        value = raw.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise OptimizationError("invalid_report", f"paired_outcomes.{field} must be an integer >= 0")
        outcomes[field] = value
    if sum(outcomes.values()) != valid_pairs:
        raise OptimizationError(
            "invalid_report",
            "paired outcome counts must sum exactly to valid_pairs",
            {"outcomes": outcomes, "valid_pairs": valid_pairs},
        )
    return outcomes


def _validate_pair_report(
    raw: Any,
    *,
    split: str,
    candidate_fingerprint: str,
    parent_fingerprint: str,
    objective: dict[str, Any],
    expected_identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    report, identity = _validate_common_report(raw, split=split, objective=objective)
    if report.get("report_type") != "paired":
        raise OptimizationError("invalid_report", "candidate report_type must be 'paired'")
    expected_fingerprints = {
        "candidate_fingerprint": candidate_fingerprint,
        "parent_fingerprint": parent_fingerprint,
    }
    for field, expected in expected_fingerprints.items():
        if report.get(field) != expected:
            raise OptimizationError(
                f"{field}_mismatch",
                f"report {field} does not match the staged comparison",
                {"expected": expected, "actual": report.get(field)},
            )
    if expected_identity is not None and identity != expected_identity:
        raise OptimizationError(
            "evaluation_identity_mismatch",
            "corpus, rubric, model, harness, or pairing differs from the frozen evaluation identity",
            {"expected": expected_identity, "actual": identity},
        )
    report["candidate_metrics"] = _validate_metrics(
        report.get("candidate_metrics"), objective, "candidate_metrics"
    )
    report["parent_metrics"] = _validate_metrics(
        report.get("parent_metrics"), objective, "parent_metrics"
    )
    report["paired_outcomes"] = _validate_paired_outcomes(
        report.get("paired_outcomes"), report["valid_pairs"]
    )
    return report


def _path_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or PurePosixPath(path).match(pattern)
        for pattern in patterns
    )


def _text_lines(path: Path | None) -> list[str] | None:
    if path is None:
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return None


def diff_summary(parent: Path, candidate: Path) -> DiffSummary:
    before = _files(parent)
    after = _files(candidate)
    changed: list[str] = []
    added = deleted = binary_bytes = 0
    for relative in sorted(set(before) | set(after)):
        old = before.get(relative)
        new = after.get(relative)
        if old is not None and new is not None and old.read_bytes() == new.read_bytes():
            continue
        changed.append(relative)
        old_lines = _text_lines(old)
        new_lines = _text_lines(new)
        if old_lines is None or new_lines is None:
            binary_bytes += new.stat().st_size if new is not None else 0
            continue
        matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in {"replace", "delete"}:
                deleted += i2 - i1
            if tag in {"replace", "insert"}:
                added += j2 - j1
    return DiffSummary(
        changed_files=len(changed),
        added_lines=added,
        deleted_lines=deleted,
        total_line_changes=added + deleted,
        binary_bytes=binary_bytes,
        paths=tuple(changed),
    )


def _enforce_diff(summary: DiffSummary, objective: dict[str, Any]) -> None:
    forbidden = tuple(ALWAYS_FORBIDDEN) + tuple(objective["forbidden_paths"])
    for path in summary.paths:
        if _path_matches(path, forbidden):
            raise OptimizationError("forbidden_path_changed", f"candidate changes protected path: {path}")
        if not _path_matches(path, objective["allowed_paths"]):
            raise OptimizationError("path_not_allowed", f"candidate changes path outside allowed_paths: {path}")
    observed = summary.as_dict()
    budget = objective["edit_budget"]
    keys = {
        "changed_files": "max_changed_files",
        "added_lines": "max_added_lines",
        "deleted_lines": "max_deleted_lines",
        "total_line_changes": "max_total_line_changes",
        "binary_bytes": "max_binary_bytes",
    }
    exceeded = {
        metric: {"observed": observed[metric], "limit": budget[limit]}
        for metric, limit in keys.items()
        if observed[metric] > budget[limit]
    }
    if exceeded:
        raise OptimizationError("edit_budget_exceeded", "candidate exceeds the edit budget", exceeded)


def _compare(actual: float, op: str, target: float) -> bool:
    if op == "<":
        return actual < target
    if op == "<=":
        return actual <= target
    if op == "==":
        return actual == target
    if op == "!=":
        return actual != target
    if op == ">=":
        return actual >= target
    return actual > target


def _eligibility(report: dict[str, Any], objective: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    candidate = report["candidate_metrics"]
    parent = report["parent_metrics"]
    reasons: list[str] = []
    checks: dict[str, Any] = {"hard_constraints": [], "secondary_metrics": []}

    for rule in objective["hard_constraints"]:
        actual = candidate[rule["metric"]]
        target = float(rule["value"])
        passed = _compare(actual, rule["op"], target)
        checks["hard_constraints"].append({**rule, "actual": actual, "passed": passed})
        if not passed:
            reasons.append(
                f"hard constraint failed: {rule['metric']} {rule['op']} {target} (actual {actual})"
            )

    metric = objective["primary_metric"]
    current, previous = candidate[metric], parent[metric]
    improvement = current - previous if objective["direction"] == "maximize" else previous - current
    primary_passed = improvement >= float(objective["min_delta"])
    checks["primary"] = {
        "metric": metric,
        "direction": objective["direction"],
        "candidate": current,
        "parent": previous,
        "improvement": improvement,
        "minimum": float(objective["min_delta"]),
        "passed": primary_passed,
    }
    if not primary_passed:
        reasons.append(f"primary improvement {improvement} is below required {objective['min_delta']}")

    for rule in objective["secondary_metrics"]:
        metric = rule["metric"]
        current, previous = candidate[metric], parent[metric]
        relative = float(rule.get("max_relative_regression", 0))
        absolute = float(rule.get("max_absolute_regression", 0))
        if rule["direction"] == "minimize":
            boundary = previous * (1 + relative) + absolute
            passed = current <= boundary
        else:
            boundary = previous * (1 - relative) - absolute
            passed = current >= boundary
        checks["secondary_metrics"].append(
            {**rule, "candidate": current, "parent": previous, "permitted_boundary": boundary, "passed": passed}
        )
        if not passed:
            reasons.append(f"secondary metric regressed beyond tolerance: {metric}")

    checks["paired_outcomes"] = report["paired_outcomes"]
    checks["infrastructure_failures"] = report["infrastructure_failures"]
    if report["infrastructure_failures"]:
        reasons.append("paired report contains infrastructure failures")
    return not reasons, reasons, checks


def _load_workspace(path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    workspace = path.expanduser().resolve()
    state = _json_read(workspace / "state.json")
    objective = _validate_objective(_json_read(workspace / "objective.json"))
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise OptimizationError("invalid_workspace", f"invalid state file under {workspace}")
    if state.get("objective_fingerprint") != _fingerprint_json(objective):
        raise OptimizationError("objective_drift", "objective.json changed after initialization")
    baseline = workspace / "snapshots" / "baseline"
    best = workspace / "snapshots" / "best"
    if tree_fingerprint(baseline) != state.get("baseline_fingerprint"):
        raise OptimizationError("snapshot_drift", "baseline snapshot changed after initialization")
    if tree_fingerprint(best) != state.get("best_fingerprint"):
        raise OptimizationError("snapshot_drift", "best snapshot changed outside the controller")
    return workspace, state, objective


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    skill_root = args.skill_root.expanduser().resolve()
    workspace = args.workspace.expanduser().resolve()
    if workspace.exists():
        raise OptimizationError("workspace_exists", f"refusing to overwrite workspace: {workspace}")
    if _inside(workspace, skill_root) or _inside(skill_root, workspace):
        raise OptimizationError("overlapping_roots", "workspace and skill root must not contain one another")
    objective = _validate_objective(_json_read(args.objective.expanduser().resolve()))
    baseline_fingerprint = tree_fingerprint(skill_root)
    baseline_report = _validate_baseline_report(
        _json_read(args.baseline_report.expanduser().resolve()),
        split="validation",
        skill_fingerprint=baseline_fingerprint,
        objective=objective,
    )

    try:
        (workspace / "snapshots").mkdir(parents=True)
        (workspace / "candidates").mkdir()
        (workspace / "reports").mkdir()
        _copy_tree(skill_root, workspace / "snapshots" / "baseline")
        _copy_tree(skill_root, workspace / "snapshots" / "best")
        _atomic_json(workspace / "objective.json", objective)
        _atomic_json(workspace / "reports" / "baseline-validation.json", baseline_report)
        state = {
            "schema_version": SCHEMA_VERSION,
            "status": "optimizing",
            "created_at": _now(),
            "skill_name": skill_root.name,
            "source_root": str(skill_root),
            "objective_fingerprint": _fingerprint_json(objective),
            "validation_identity": _report_identity(baseline_report),
            "baseline_fingerprint": baseline_fingerprint,
            "best_fingerprint": baseline_fingerprint,
            "best_candidate_id": "baseline",
            "next_candidate": 1,
            "accepted_candidates": 0,
            "rejected_candidates": 0,
            "consecutive_rejections": 0,
        }
        _atomic_json(workspace / "state.json", state)
        _append_ledger(
            workspace,
            {
                "event": "initialized",
                "baseline_fingerprint": baseline_fingerprint,
                "objective_fingerprint": state["objective_fingerprint"],
                "validation_identity": state["validation_identity"],
            },
        )
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    return {
        "ok": True,
        "event": "initialized",
        "workspace": str(workspace),
        "baseline_fingerprint": baseline_fingerprint,
        "objective_fingerprint": _fingerprint_json(objective),
    }


def command_stage(args: argparse.Namespace) -> dict[str, Any]:
    workspace, state, objective = _load_workspace(args.workspace)
    if state.get("status") != "optimizing":
        raise OptimizationError("experiment_not_open", f"experiment status is {state.get('status')!r}")
    hypothesis = " ".join(args.hypothesis.split())
    if not hypothesis:
        raise OptimizationError("missing_hypothesis", "candidate hypothesis must not be empty")
    candidate_root = args.candidate_root.expanduser().resolve()
    if _inside(candidate_root, workspace / "snapshots") or _inside(candidate_root, workspace / "candidates"):
        raise OptimizationError("unsafe_candidate_root", "candidate_root points into controller-owned state")
    summary = diff_summary(workspace / "snapshots" / "best", candidate_root)
    if not summary.changed_files:
        raise OptimizationError("no_candidate_change", "candidate is byte-identical to the current best")
    _enforce_diff(summary, objective)
    candidate_id = f"c{int(state['next_candidate']):04d}"
    destination = workspace / "candidates" / candidate_id
    fingerprint = tree_fingerprint(candidate_root)
    try:
        destination.mkdir()
        _copy_tree(candidate_root, destination / "skill")
        proposal = {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "status": "staged",
            "staged_at": _now(),
            "hypothesis": hypothesis,
            "parent_candidate_id": state["best_candidate_id"],
            "parent_fingerprint": state["best_fingerprint"],
            "candidate_fingerprint": fingerprint,
            "diff": summary.as_dict(),
        }
        _atomic_json(destination / "proposal.json", proposal)
        state["next_candidate"] = int(state["next_candidate"]) + 1
        _atomic_json(workspace / "state.json", state)
        _append_ledger(workspace, {"event": "candidate_staged", **proposal})
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "ok": True,
        "event": "candidate_staged",
        "candidate_id": candidate_id,
        "parent_fingerprint": state["best_fingerprint"],
        "candidate_fingerprint": fingerprint,
        "diff": summary.as_dict(),
    }


def _candidate_id(value: str) -> str:
    if not CANDIDATE_ID_RE.fullmatch(value):
        raise OptimizationError("invalid_candidate_id", f"invalid candidate id: {value!r}")
    return value


def command_decide(args: argparse.Namespace) -> dict[str, Any]:
    workspace, state, objective = _load_workspace(args.workspace)
    candidate_id = _candidate_id(args.candidate_id)
    candidate_dir = workspace / "candidates" / candidate_id
    proposal_path = candidate_dir / "proposal.json"
    proposal = _json_read(proposal_path)
    if not isinstance(proposal, dict) or proposal.get("candidate_id") != candidate_id:
        raise OptimizationError("invalid_candidate", f"invalid candidate record: {candidate_id}")
    if proposal.get("status") != "staged":
        raise OptimizationError("candidate_already_decided", f"candidate status is {proposal.get('status')!r}")
    if proposal.get("parent_fingerprint") != state.get("best_fingerprint"):
        raise OptimizationError(
            "stale_candidate", "candidate parent is no longer current best; restage the hypothesis"
        )
    candidate_root = candidate_dir / "skill"
    if tree_fingerprint(candidate_root) != proposal.get("candidate_fingerprint"):
        raise OptimizationError("candidate_drift", "staged candidate changed after staging")

    report = _validate_pair_report(
        _json_read(args.report.expanduser().resolve()),
        split="validation",
        candidate_fingerprint=proposal["candidate_fingerprint"],
        parent_fingerprint=proposal["parent_fingerprint"],
        objective=objective,
        expected_identity=state["validation_identity"],
    )
    accepted, reasons, checks = _eligibility(report, objective)
    _atomic_json(candidate_dir / "validation.json", report)
    proposal.update(
        {
            "decided_at": _now(),
            "decision_checks": checks,
            "decision_reasons": reasons,
            "status": "accepted" if accepted else "rejected",
        }
    )

    if accepted:
        _replace_tree(candidate_root, workspace / "snapshots" / "best")
        state["best_fingerprint"] = proposal["candidate_fingerprint"]
        state["best_candidate_id"] = candidate_id
        state["accepted_candidates"] = int(state["accepted_candidates"]) + 1
        state["consecutive_rejections"] = 0
        event = "candidate_accepted"
    else:
        state["rejected_candidates"] = int(state["rejected_candidates"]) + 1
        state["consecutive_rejections"] = int(state["consecutive_rejections"]) + 1
        if state["consecutive_rejections"] >= objective["plateau_limit"]:
            state["status"] = "plateau"
        event = "candidate_rejected"

    _atomic_json(proposal_path, proposal)
    _atomic_json(workspace / "state.json", state)
    _append_ledger(
        workspace,
        {
            "event": event,
            "candidate_id": candidate_id,
            "hypothesis": proposal["hypothesis"],
            "parent_fingerprint": proposal["parent_fingerprint"],
            "candidate_fingerprint": proposal["candidate_fingerprint"],
            "diff": proposal["diff"],
            "checks": checks,
            "reasons": reasons,
            "best_candidate_id": state["best_candidate_id"],
            "best_fingerprint": state["best_fingerprint"],
        },
    )
    return {
        "ok": True,
        "event": event,
        "accepted": accepted,
        "candidate_id": candidate_id,
        "checks": checks,
        "reasons": reasons,
        "best_candidate_id": state["best_candidate_id"],
        "best_fingerprint": state["best_fingerprint"],
        "experiment_status": state["status"],
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    workspace, state, objective = _load_workspace(args.workspace)
    return {"ok": True, "event": "status", "workspace": str(workspace), "state": state, "objective": objective}


def command_finalize(args: argparse.Namespace) -> dict[str, Any]:
    workspace, state, objective = _load_workspace(args.workspace)
    report = _validate_pair_report(
        _json_read(args.report.expanduser().resolve()),
        split="test",
        candidate_fingerprint=state["best_fingerprint"],
        parent_fingerprint=state["baseline_fingerprint"],
        objective=objective,
    )
    identity = _report_identity(report)
    if identity["corpus_fingerprint"] == state["validation_identity"]["corpus_fingerprint"]:
        raise OptimizationError("test_validation_leakage", "test corpus matches the validation corpus")
    passed, reasons, checks = _eligibility(report, objective)
    result = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": _now(),
        "baseline_fingerprint": state["baseline_fingerprint"],
        "candidate_fingerprint": state["best_fingerprint"],
        "best_candidate_id": state["best_candidate_id"],
        "test_identity": identity,
        "passed": passed,
        "checks": checks,
        "reasons": reasons,
    }
    _atomic_json(workspace / "reports" / "final-test.json", {**report, "decision": result})
    _append_ledger(workspace, {"event": "final_test_passed" if passed else "final_test_failed", **result})
    if not passed:
        state["status"] = "test_failed"
        _atomic_json(workspace / "state.json", state)
        return {"ok": True, "event": "final_test_failed", **result}

    output = args.output.expanduser().resolve()
    if output.exists():
        raise OptimizationError("output_exists", f"refusing to overwrite final output: {output}")
    if _inside(output, workspace):
        raise OptimizationError("unsafe_output", "final output must be outside the optimizer workspace")
    _copy_tree(workspace / "snapshots" / "best", output)
    state.update({"status": "finalized", "finalized_at": _now(), "final_output": str(output)})
    _atomic_json(workspace / "state.json", state)
    return {"ok": True, "event": "finalized", "output": str(output), **result}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="freeze the baseline, objective, and validation identity")
    init.add_argument("--skill-root", type=Path, required=True)
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--objective", type=Path, required=True)
    init.add_argument("--baseline-report", type=Path, required=True)
    init.set_defaults(handler=command_init)

    stage = sub.add_parser("stage", help="stage one bounded candidate against current best")
    stage.add_argument("--workspace", type=Path, required=True)
    stage.add_argument("--candidate-root", type=Path, required=True)
    stage.add_argument("--hypothesis", required=True)
    stage.set_defaults(handler=command_stage)

    decide = sub.add_parser("decide", help="accept or reject from a paired held-out validation report")
    decide.add_argument("--workspace", type=Path, required=True)
    decide.add_argument("--candidate-id", required=True)
    decide.add_argument("--report", type=Path, required=True)
    decide.set_defaults(handler=command_decide)

    status = sub.add_parser("status", help="inspect immutable fingerprints and experiment state")
    status.add_argument("--workspace", type=Path, required=True)
    status.set_defaults(handler=command_status)

    finalize = sub.add_parser("finalize", help="gate and export the best package on untouched paired test data")
    finalize.add_argument("--workspace", type=Path, required=True)
    finalize.add_argument("--report", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    finalize.set_defaults(handler=command_finalize)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = args.handler(args)
    except OptimizationError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": str(exc), "details": exc.details}},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2
    except Exception as exc:  # noqa: BLE001 - stable standalone boundary
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "internal_error",
                        "message": f"{type(exc).__name__}: {exc}",
                        "details": {},
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
