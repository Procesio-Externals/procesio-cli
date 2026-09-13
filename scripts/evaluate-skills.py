#!/usr/bin/env python3
"""Measure skill discovery against a versioned prompt corpus.

The default run evaluates the repository's current ``skills/*/SKILL.md``
frontmatter. ``--catalog`` evaluates a frozen catalog instead, which lets CI
compare a candidate corpus with the original baseline without keeping two
checkouts. ``--observations`` additionally summarizes externally supplied model/run
selections captured as JSON or JSONL; it does not authenticate those observations.

This is deliberately a measurement harness, not a claim that token overlap is a
model. The deterministic scorer catches description regressions cheaply; real
observations require independent provenance, fixed-rubric and completeness checks
before any release decision. This summary command is not an acceptance gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS = REPO / "skills"
DEFAULT_CORPUS = DEFAULT_SKILLS / "evals" / "routing.json"

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#_-]*", re.IGNORECASE)
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from",
    "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "please",
    "the", "this", "to", "use", "we", "with", "you",
}


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str


def _frontmatter(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: missing YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            data = yaml.safe_load("\n".join(lines[1:index]))
            if not isinstance(data, dict):
                raise ValueError(f"{path}: frontmatter must be a mapping")
            return data
    raise ValueError(f"{path}: unterminated YAML frontmatter")


def load_skills(root: Path) -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        data = _frontmatter(skill_md)
        name = str(data.get("name") or "").strip()
        description = " ".join(str(data.get("description") or "").split())
        if not name or not description:
            raise ValueError(f"{skill_md}: name and description are required")
        entries.append(SkillEntry(name=name, description=description))
    if not entries:
        raise ValueError(f"no skills found under {root}")
    return entries


def load_catalog(path: Path) -> list[SkillEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("skills") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a list or {{'skills': [...]}}")
    entries = [
        SkillEntry(name=str(row["name"]), description=" ".join(str(row["description"]).split()))
        for row in rows
    ]
    if not entries:
        raise ValueError(f"{path}: catalog is empty")
    return entries


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text) if token.lower() not in _STOP]


def _phrases(tokens: list[str]) -> set[str]:
    out: set[str] = set()
    for width in (2, 3):
        out.update(" ".join(tokens[index:index + width])
                   for index in range(0, max(0, len(tokens) - width + 1)))
    return out


def score(prompt: str, skill: SkillEntry) -> float:
    prompt_tokens = _tokens(prompt)
    description_tokens = _tokens(skill.description)
    if not prompt_tokens or not description_tokens:
        return 0.0

    prompt_counts = Counter(prompt_tokens)
    description_counts = Counter(description_tokens)
    overlap = sum(min(count, description_counts[token]) for token, count in prompt_counts.items())

    prompt_phrases = _phrases(prompt_tokens)
    description_text = " ".join(description_tokens)
    phrase_hits = sum(1 for phrase in prompt_phrases if phrase in description_text)

    name_tokens = set(_tokens(skill.name.replace("-", " ")))
    name_hits = len(name_tokens.intersection(prompt_counts))
    return float(overlap + (2 * phrase_hits) + (3 * name_hits))


def select_skill(prompt: str, skills: Iterable[SkillEntry]) -> tuple[str | None, dict[str, float]]:
    scores = {skill.name: score(prompt, skill) for skill in skills}
    if not scores:
        return None, {}
    best = max(scores.values())
    if best <= 0:
        return None, scores
    winners = sorted(name for name, value in scores.items() if value == best)
    return winners[0], scores


def _load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: expected a non-empty cases list")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError(f"{path}: each case must be an object")
        case_id = str(case.get("id") or "")
        if not case_id or case_id in seen:
            raise ValueError(f"{path}: case ids must be non-empty and unique")
        if not str(case.get("prompt") or "").strip():
            raise ValueError(f"{path}: {case_id} has no prompt")
        seen.add(case_id)
    return cases


def evaluate(skills: list[SkillEntry], cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    correct = collisions = 0

    for case in cases:
        selected, scores = select_skill(str(case["prompt"]), skills)
        expected = case.get("expected_skill")
        forbidden = set(case.get("forbidden_skills") or [])
        is_correct = selected == expected
        collision = selected in forbidden
        correct += int(is_correct)
        collisions += int(collision)
        confusion[str(expected)][str(selected)] += 1
        rows.append({
            "id": case["id"],
            "kind": case.get("kind", "unspecified"),
            "prompt": case["prompt"],
            "expected_skill": expected,
            "selected_skill": selected,
            "correct": is_correct,
            "collision": collision,
            "scores": dict(sorted(scores.items(), key=lambda item: (-item[1], item[0]))),
        })

    total = len(cases)
    catalog_payload = [{"name": item.name, "description": item.description} for item in skills]
    catalog_fingerprint = hashlib.sha256(
        json.dumps(catalog_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    corpus_fingerprint = hashlib.sha256(
        json.dumps(cases, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "catalog_fingerprint": catalog_fingerprint,
        "corpus_fingerprint": corpus_fingerprint,
        "skill_count": len(skills),
        "case_count": total,
        "correct": correct,
        "routing_accuracy": correct / total,
        "collisions": collisions,
        "collision_rate": collisions / total,
        "confusion": {expected: dict(counter) for expected, counter in sorted(confusion.items())},
        "cases": rows,
    }


def _load_observations(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    raw = json.loads(text)
    rows = raw.get("observations") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError(f"{path}: observations must be a list")
    return rows


def grade_observations(observations: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(case["id"]): case for case in cases}
    graded: list[dict[str, Any]] = []
    tokens: list[int] = []
    durations: list[int] = []
    selection_correct = task_success = 0

    for row in observations:
        case_id = str(row.get("case_id") or row.get("id") or "")
        if case_id not in by_id:
            raise ValueError(f"observation refers to unknown case {case_id!r}")
        case = by_id[case_id]
        selected = row.get("selected_skill")
        selection_ok = selected == case.get("expected_skill")
        succeeded = row.get("task_success", False)
        if type(succeeded) is not bool:
            raise ValueError("task_success must be Boolean")
        selection_correct += int(selection_ok)
        task_success += int(succeeded)
        if row.get("total_tokens") is not None:
            tokens.append(int(row["total_tokens"]))
        if row.get("duration_ms") is not None:
            durations.append(int(row["duration_ms"]))
        graded.append({
            "case_id": case_id,
            "expected_skill": case.get("expected_skill"),
            "selected_skill": selected,
            "selection_correct": selection_ok,
            "task_success": succeeded,
        })

    total = len(graded)
    return {
        "observation_count": total,
        "selection_accuracy": (selection_correct / total) if total else None,
        "task_success_rate": (task_success / total) if total else None,
        "mean_total_tokens": (sum(tokens) / len(tokens)) if tokens else None,
        "mean_duration_ms": (sum(durations) / len(durations)) if durations else None,
        "observations": graded,
    }


def _baseline_projection(report: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version", "catalog_fingerprint", "corpus_fingerprint", "skill_count",
        "case_count", "correct", "routing_accuracy", "collisions", "collision_rate",
        "confusion",
    )
    return {key: report[key] for key in keys}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--catalog", type=Path,
                        help="Frozen JSON catalog to evaluate instead of skills/*/SKILL.md")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--observations", type=Path,
                        help="Optional real-run JSON/JSONL selections and outcomes")
    parser.add_argument("--write-report", type=Path,
                        help="Write the full JSON report to this path")
    parser.add_argument("--verify-baseline", type=Path,
                        help="Compare summary fields with a committed baseline JSON")
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    parser.add_argument("--max-collision-rate", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    skills = load_catalog(args.catalog) if args.catalog else load_skills(args.skills_root)
    cases = _load_cases(args.corpus)
    report = evaluate(skills, cases)
    if args.observations:
        report["behavioral_observations"] = grade_observations(
            _load_observations(args.observations), cases
        )

    if args.verify_baseline:
        expected = json.loads(args.verify_baseline.read_text(encoding="utf-8"))
        actual = _baseline_projection(report)
        if actual != expected:
            print(json.dumps({"error": "baseline_mismatch", "expected": expected,
                              "actual": actual}, indent=2), file=sys.stderr)
            return 2

    if report["routing_accuracy"] < args.min_accuracy:
        print(json.dumps({"error": "accuracy_below_threshold",
                          "actual": report["routing_accuracy"],
                          "minimum": args.min_accuracy}, indent=2), file=sys.stderr)
        return 3
    if report["collision_rate"] > args.max_collision_rate:
        print(json.dumps({"error": "collision_rate_above_threshold",
                          "actual": report["collision_rate"],
                          "maximum": args.max_collision_rate}, indent=2), file=sys.stderr)
        return 4

    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
