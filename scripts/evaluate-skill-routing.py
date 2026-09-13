#!/usr/bin/env python3
"""Deterministic lint for skill-description routing boundaries.

This is a cheap regression gate, not a model benchmark. It evaluates the same
versioned prompt corpus against either the live skills or a frozen catalog.
Release decisions need independently validated behavioral evidence. The optional
observation summaries in evaluate-skills.py are not an acceptance gate.
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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS = ROOT / "skills"
DEFAULT_CORPUS = DEFAULT_SKILLS / "evals" / "routing.json"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:\+[a-z0-9]+|#[a-z0-9]*)?", re.I)
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from",
    "how", "i", "in", "is", "it", "me", "my", "no", "not", "of", "on", "or",
    "our", "please", "s", "should", "the", "their", "this", "through", "to",
    "use", "user", "we", "when", "with", "you",
}
NEGATIVE_MARKERS = (
    "do not use", "not when", "rather than", "instead of", "excluding", "except for",
)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str


def _frontmatter(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: missing YAML frontmatter")
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            raw = yaml.safe_load("\n".join(lines[1:index]))
            if isinstance(raw, dict):
                return raw
            raise ValueError(f"{path}: frontmatter must be a mapping")
    raise ValueError(f"{path}: unterminated YAML frontmatter")


def load_skills(root: Path) -> list[Skill]:
    result = []
    for path in sorted(root.glob("*/SKILL.md")):
        raw = _frontmatter(path)
        name = str(raw.get("name") or "").strip()
        description = " ".join(str(raw.get("description") or "").split())
        if not name or not description:
            raise ValueError(f"{path}: name and description are required")
        result.append(Skill(name, description))
    if not result:
        raise ValueError(f"no skills found under {root}")
    return result


def load_catalog(path: Path) -> list[Skill]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("skills") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: expected a non-empty skills list")
    return [Skill(str(row["name"]), " ".join(str(row["description"]).split())) for row in rows]


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: expected a non-empty cases list")
    ids = [str(row.get("id") or "") for row in rows]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{path}: case ids must be non-empty and unique")
    return rows


def tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOP]


def phrases(items: list[str]) -> set[str]:
    return {
        " ".join(items[index:index + width])
        for width in (2, 3)
        for index in range(max(0, len(items) - width + 1))
    }


def split_description(text: str) -> tuple[str, str]:
    positive, negative = [], []
    for clause in re.split(r"[.;\n]+", text):
        lowered = clause.lower()
        cuts = [lowered.index(marker) for marker in NEGATIVE_MARKERS if marker in lowered]
        if not cuts:
            positive.append(clause)
            continue
        cut = min(cuts)
        positive.append(clause[:cut])
        negative.append(clause[cut:])
    return " ".join(positive), " ".join(negative)


def score(prompt: str, skill: Skill) -> float:
    prompt_tokens = tokens(prompt)
    positive, negative = split_description(skill.description)
    positive_tokens, negative_tokens = tokens(positive), tokens(negative)
    if not prompt_tokens or not positive_tokens:
        return 0.0
    prompt_counts, positive_counts = Counter(prompt_tokens), Counter(positive_tokens)
    overlap = sum(min(count, positive_counts[token]) for token, count in prompt_counts.items())
    prompt_phrases = phrases(prompt_tokens)
    positive_text, negative_text = " ".join(positive_tokens), " ".join(negative_tokens)
    positive_phrase_hits = sum(phrase in positive_text for phrase in prompt_phrases)
    negative_hits = sum(token in set(negative_tokens) for token in set(prompt_tokens))
    negative_phrase_hits = sum(phrase in negative_text for phrase in prompt_phrases)
    exact_bonus = 8 if " ".join(prompt_tokens) in positive_text else 0
    return max(0.0, float(
        overlap + 2 * positive_phrase_hits + exact_bonus
        - 4 * negative_hits - 8 * negative_phrase_hits
    ))


def select(prompt: str, skills: Iterable[Skill]) -> tuple[str | None, dict[str, float]]:
    scores = {skill.name: score(prompt, skill) for skill in skills}
    best = max(scores.values(), default=0.0)
    if best <= 0:
        return None, scores
    return sorted(name for name, value in scores.items() if value == best)[0], scores


def evaluate(skills: list[Skill], cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows, confusion = [], defaultdict(Counter)
    correct = collisions = 0
    for case in cases:
        selected, scores = select(str(case.get("prompt") or ""), skills)
        expected = case.get("expected_skill")
        is_correct = selected == expected
        collision = selected in set(case.get("forbidden_skills") or [])
        correct += int(is_correct)
        collisions += int(collision)
        confusion[str(expected)][str(selected)] += 1
        rows.append({
            "id": case["id"], "expected_skill": expected, "selected_skill": selected,
            "correct": is_correct, "collision": collision,
            "scores": dict(sorted(scores.items(), key=lambda item: (-item[1], item[0]))),
        })
    catalog = [{"name": item.name, "description": item.description} for item in skills]
    fingerprint = lambda value: hashlib.sha256(  # noqa: E731
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    total = len(cases)
    return {
        "schema_version": 2,
        "catalog_fingerprint": fingerprint(catalog),
        "corpus_fingerprint": fingerprint(cases),
        "skill_count": len(skills), "case_count": total, "correct": correct,
        "routing_accuracy": correct / total, "collisions": collisions,
        "collision_rate": collisions / total,
        "confusion": {key: dict(value) for key, value in sorted(confusion.items())},
        "cases": rows,
    }


def projection(report: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version", "catalog_fingerprint", "corpus_fingerprint", "skill_count",
        "case_count", "correct", "routing_accuracy", "collisions", "collision_rate", "confusion",
    )
    return {key: report[key] for key in keys}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--write-report", type=Path)
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    parser.add_argument("--max-collision-rate", type=float, default=1.0)
    args = parser.parse_args(argv)

    skills = load_catalog(args.catalog) if args.catalog else load_skills(args.skills_root)
    report = evaluate(skills, load_cases(args.corpus))
    if args.verify:
        expected = json.loads(args.verify.read_text(encoding="utf-8"))
        if projection(report) != expected:
            print(json.dumps({"error": "report_mismatch", "expected": expected,
                              "actual": projection(report)}, indent=2), file=sys.stderr)
            return 2
    if report["routing_accuracy"] < args.min_accuracy:
        return 3
    if report["collision_rate"] > args.max_collision_rate:
        return 4
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
