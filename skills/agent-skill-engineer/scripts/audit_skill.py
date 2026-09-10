#!/usr/bin/env python3
"""Deterministically audit one or more Agent Skill packages.

The audit checks portable structure, frontmatter, discovery descriptions,
progressive resources, local references, common secret signatures, governed
metadata, and fixed-rubric evaluation cases. It makes no model or network calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover - actionable dependency failure
    raise SystemExit("audit_skill.py requires PyYAML (`python -m pip install pyyaml`)") from exc

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CRITERION_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CODE_PATH_RE = re.compile(
    r"`((?:(?:references|scripts|assets)/)[^`\n]+)`", re.IGNORECASE
)
PLACEHOLDER_RE = re.compile(
    r"\{\{\s*REPLACE[^}]*\}\}|\b(?:TODO|TBD|FIXME|YOUR_[A-Z0-9_]+)\b",
    re.IGNORECASE,
)
TRIGGER_RE = re.compile(r"\b(?:use when|use for|use to|when users?|when the user)\b", re.I)
HYPE_RE = re.compile(
    r"\b(?:ultimate|world[- ]class|unparalleled|best[- ]in[- ]class|"
    r"0\.0*1%|genius|superhuman|omniscient)\b",
    re.I,
)
TOC_RE = re.compile(r"^##?\s+(?:contents|table of contents)\b", re.I | re.M)
ALLOWED_FRONTMATTER = {
    "name",
    "description",
    "version",
    "compatibility",
    "license",
    "allowed-tools",
    "disable-model-invocation",
    "argument-hint",
    "routing",
    "metadata",
    "owner",
    "last_verified",
    "baseline_version",
    "eval_suite",
    "source_policy",
}
GOVERNED_FIELDS = {
    "version",
    "owner",
    "last_verified",
    "baseline_version",
    "eval_suite",
    "source_policy",
    "routing",
}
REQUIRED_BODY_SECTIONS = ("boundary", "workflow", "verification")
CASE_KINDS = {"positive", "negative", "overlap", "pressure"}
IGNORED_PARTS = {"__pycache__", ".git", ".venv", "node_modules"}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github-token", re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{24,}=*\b", re.I)),
)


@dataclass(frozen=True, order=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str
    remedy: str


def _finding(
    severity: str,
    code: str,
    path: Path | str,
    message: str,
    remedy: str,
) -> Finding:
    return Finding(
        severity=severity,
        code=code,
        path=str(path).replace("\\", "/"),
        message=message,
        remedy=remedy,
    )


def _split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML delimiter `---`")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = yaml.safe_load("\n".join(lines[1:index]))
            if not isinstance(raw, dict):
                raise ValueError("frontmatter must be a YAML mapping")
            return raw, "\n".join(lines[index + 1 :])
    raise ValueError("missing closing YAML delimiter `---`")


def _ignored(path: Path) -> bool:
    return path.suffix == ".pyc" or any(part in IGNORED_PARTS for part in path.parts)


def _safe_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _candidate_reference(raw: str, source: Path, root: Path) -> Path | None:
    cleaned = raw.strip().split("#", 1)[0].split("?", 1)[0]
    if not cleaned or cleaned.startswith(("http://", "https://", "mailto:", "#")):
        return None
    posix = PurePosixPath(cleaned)
    if posix.is_absolute() or ".." in posix.parts:
        return root.parent / "__unsafe_reference__"
    # Category-prefixed resources are skill-root-relative, including when
    # referenced from another resource. Bare links remain document-relative.
    base = root if posix.parts and posix.parts[0] in {"references", "scripts", "assets"} else source.parent
    candidate = (base / Path(*posix.parts)).resolve()
    if not candidate.exists() and len(posix.parts) == 1:
        alternatives = [
            (root / cleaned).resolve(),
            (root / "references" / cleaned).resolve(),
            (root / "scripts" / cleaned).resolve(),
            (root / "assets" / cleaned).resolve(),
        ]
        candidate = next((item for item in alternatives if item.exists()), candidate)
    return candidate


def _scan_links(root: Path, markdown_files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    mentioned: set[Path] = set()
    for source in markdown_files:
        text = source.read_text(encoding="utf-8")
        raw_refs = [match.group(1).strip().split()[0] for match in MARKDOWN_LINK_RE.finditer(text)]
        raw_refs += [match.group(1).strip() for match in CODE_PATH_RE.finditer(text)]
        for raw in sorted(set(raw_refs)):
            candidate = _candidate_reference(raw, source, root)
            if candidate is None:
                continue
            rel_source = source.relative_to(root)
            if "__unsafe_reference__" in candidate.parts or not _safe_relative(candidate, root):
                findings.append(
                    _finding(
                        "error",
                        "unsafe-reference",
                        rel_source,
                        f"reference escapes the skill root: {raw}",
                        "Use a path-confined relative reference inside this skill package.",
                    )
                )
            elif not candidate.exists():
                findings.append(
                    _finding(
                        "error",
                        "missing-reference",
                        rel_source,
                        f"referenced resource does not exist: {raw}",
                        "Create the referenced file or remove the stale pointer.",
                    )
                )
            elif candidate.is_file():
                mentioned.add(candidate.resolve())

    resources = [
        path
        for category in ("references", "scripts", "assets")
        for path in (root / category).glob("*")
        if path.is_file() and not path.name.startswith(".") and not _ignored(path.relative_to(root))
    ]
    for path in resources:
        if path.resolve() not in mentioned:
            findings.append(
                _finding(
                    "warning",
                    "unreferenced-resource",
                    path.relative_to(root),
                    "resource is not discoverable from the skill's Markdown",
                    "Link it from SKILL.md with a clear load/run condition or remove it.",
                )
            )
    return findings


def _scan_secret_signatures(root: Path, files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for code, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    _finding(
                        "error",
                        f"secret-signature-{code}",
                        path.relative_to(root),
                        f"content matches a {code} secret signature",
                        "Remove and rotate the secret; keep only secret names or placeholders.",
                    )
                )
    return findings


def _criterion_findings(
    criteria: Any,
    *,
    path: str,
    case_id: str,
) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(criteria, list) or not 2 <= len(criteria) <= 8:
        return [
            _finding(
                "error",
                "invalid-fixed-rubric-size",
                path,
                f"case {case_id!r} must contain 2 to 8 atomic criteria",
                "Split the expected behavior into fixed binary criteria before evaluation.",
            )
        ]

    seen: set[str] = set()
    for index, entry in enumerate(criteria, 1):
        if not isinstance(entry, dict):
            findings.append(
                _finding(
                    "error",
                    "invalid-criterion",
                    path,
                    f"case {case_id!r} criterion {index} is not an object",
                    "Use {id, description, required} for every criterion.",
                )
            )
            continue
        criterion_id = entry.get("id")
        description = entry.get("description")
        required = entry.get("required")
        if not isinstance(criterion_id, str) or not CRITERION_RE.fullmatch(criterion_id):
            findings.append(
                _finding(
                    "error",
                    "invalid-criterion-id",
                    path,
                    f"case {case_id!r} criterion {index} needs descriptive snake_case id",
                    "Give every juror the same stable, descriptive criterion ID.",
                )
            )
        elif criterion_id in seen:
            findings.append(
                _finding(
                    "error",
                    "duplicate-criterion-id",
                    path,
                    f"case {case_id!r} repeats criterion id {criterion_id!r}",
                    "Use each atomic criterion ID exactly once.",
                )
            )
        else:
            seen.add(criterion_id)
        if not isinstance(description, str) or not description.strip():
            findings.append(
                _finding(
                    "error",
                    "missing-criterion-description",
                    path,
                    f"case {case_id!r} criterion {criterion_id!r} has no pass condition",
                    "Write one binary `Pass only when ...` description.",
                )
            )
        elif not description.strip().startswith("Pass only when"):
            findings.append(
                _finding(
                    "warning",
                    "nonbinary-criterion-description",
                    path,
                    f"case {case_id!r} criterion {criterion_id!r} is not phrased as a binary pass condition",
                    "Start with `Pass only when` and test one observable requirement.",
                )
            )
        if not isinstance(required, bool):
            findings.append(
                _finding(
                    "error",
                    "invalid-criterion-required",
                    path,
                    f"case {case_id!r} criterion {criterion_id!r} required flag is not Boolean",
                    "Set required to true or false explicitly.",
                )
            )
    return findings


def _scan_eval_suite(root: Path, frontmatter: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    raw_path = frontmatter.get("eval_suite")
    if not raw_path:
        findings.append(
            _finding(
                "warning",
                "missing-eval-suite",
                "SKILL.md",
                "no evaluation suite is declared",
                "Add a fixed-rubric suite for objective or operational skills, or document a human review method.",
            )
        )
        return findings

    eval_path = (root / str(raw_path)).resolve()
    if not _safe_relative(eval_path, root):
        return [
            _finding(
                "error",
                "unsafe-eval-suite-path",
                "SKILL.md",
                f"eval_suite escapes the skill root: {raw_path}",
                "Use a relative path inside the skill package.",
            )
        ]
    if not eval_path.is_file():
        return [
            _finding(
                "error",
                "missing-eval-suite-file",
                "SKILL.md",
                f"eval_suite does not exist: {raw_path}",
                "Create the declared evaluation file or correct the path.",
            )
        ]

    try:
        data = json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            _finding(
                "error",
                "invalid-eval-suite-json",
                eval_path.relative_to(root),
                str(exc),
                "Write valid UTF-8 JSON using a versioned evaluation schema.",
            )
        ]
    if not isinstance(data, dict):
        return [
            _finding(
                "error",
                "invalid-eval-suite-shape",
                eval_path.relative_to(root),
                "evaluation suite must be a JSON object",
                "Use an object containing skill_name and cases/evals.",
            )
        ]

    if data.get("skill_name") not in (None, frontmatter.get("name")):
        findings.append(
            _finding(
                "error",
                "eval-skill-name-mismatch",
                eval_path.relative_to(root),
                f"skill_name {data.get('skill_name')!r} does not match frontmatter",
                "Use the exact skill name in both files.",
            )
        )
    if data.get("status") == "draft":
        findings.append(
            _finding(
                "warning",
                "draft-eval-suite",
                eval_path.relative_to(root),
                "evaluation suite is still marked draft",
                "Replace placeholders, run the cases, and remove draft status before publication.",
            )
        )

    cases = data.get("cases") if isinstance(data.get("cases"), list) else data.get("evals")
    if not isinstance(cases, list) or not cases:
        findings.append(
            _finding(
                "error",
                "missing-eval-cases",
                eval_path.relative_to(root),
                "evaluation suite has no cases",
                "Add realistic positive, negative, overlap, and pressure cases.",
            )
        )
        return findings

    ids: set[str] = set()
    kinds: set[str] = set()
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            findings.append(
                _finding(
                    "error",
                    "invalid-eval-case",
                    eval_path.relative_to(root),
                    f"case {index} is not an object",
                    "Use an object with id, prompt, kind, routing expectation, and fixed rubric.",
                )
            )
            continue
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            findings.append(
                _finding(
                    "error",
                    "missing-eval-case-id",
                    eval_path.relative_to(root),
                    f"case {index} has no id",
                    "Assign a stable descriptive ID.",
                )
            )
            case_id = f"<case-{index}>"
        elif case_id in ids:
            findings.append(
                _finding(
                    "error",
                    "duplicate-eval-case-id",
                    eval_path.relative_to(root),
                    f"duplicate case id {case_id!r}",
                    "Use each case ID exactly once.",
                )
            )
        ids.add(case_id)

        prompt = case.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            findings.append(
                _finding(
                    "error",
                    "missing-eval-prompt",
                    eval_path.relative_to(root),
                    f"case {case_id!r} has no realistic prompt",
                    "Add the exact task a real user would submit.",
                )
            )
        kind = case.get("kind")
        if isinstance(kind, str):
            kinds.add(kind)
            if kind not in CASE_KINDS:
                findings.append(
                    _finding(
                        "warning",
                        "unknown-eval-kind",
                        eval_path.relative_to(root),
                        f"case {case_id!r} uses unrecognized kind {kind!r}",
                        "Use positive, negative, overlap, or pressure, or document the extension.",
                    )
                )
        else:
            findings.append(
                _finding(
                    "warning",
                    "missing-eval-kind",
                    eval_path.relative_to(root),
                    f"case {case_id!r} has no kind",
                    "Classify the case so corpus coverage can be audited.",
                )
            )

        expected = case.get("expected_output")
        if isinstance(expected, str):
            findings.append(
                _finding(
                    "error",
                    "dynamic-jury-rubric",
                    eval_path.relative_to(root),
                    f"case {case_id!r} stores only prose expected_output",
                    "Freeze ordered atomic criterion IDs, descriptions, and required flags for every juror.",
                )
            )
            continue
        if not isinstance(expected, dict):
            findings.append(
                _finding(
                    "error",
                    "missing-fixed-rubric",
                    eval_path.relative_to(root),
                    f"case {case_id!r} has no fixed rubric object",
                    "Add expected_output.rubric_version and expected_output.criteria.",
                )
            )
            continue
        if not isinstance(expected.get("rubric_version"), int):
            findings.append(
                _finding(
                    "error",
                    "missing-rubric-version",
                    eval_path.relative_to(root),
                    f"case {case_id!r} has no integer rubric_version",
                    "Version the fixed rubric so completed evidence cannot be silently reinterpreted.",
                )
            )
        findings.extend(
            _criterion_findings(
                expected.get("criteria"),
                path=str(eval_path.relative_to(root)),
                case_id=case_id,
            )
        )

    missing_kinds = sorted(CASE_KINDS - kinds)
    if missing_kinds:
        findings.append(
            _finding(
                "warning",
                "incomplete-eval-case-coverage",
                eval_path.relative_to(root),
                "missing case kinds: " + ", ".join(missing_kinds),
                "Cover positive, negative, nearest-overlap, and shortcut-pressure behavior.",
            )
        )
    return findings


def audit_skill(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    skill_md = root if root.name == "SKILL.md" else root / "SKILL.md"
    if root.name == "SKILL.md":
        root = root.parent
    findings: list[Finding] = []

    if not skill_md.is_file():
        findings.append(
            _finding(
                "error",
                "missing-skill-md",
                "SKILL.md",
                f"no SKILL.md found under {root}",
                "Create a skill directory containing SKILL.md.",
            )
        )
        return _report(root, None, findings)

    try:
        frontmatter, body = _split_frontmatter(skill_md)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        findings.append(
            _finding(
                "error",
                "invalid-frontmatter",
                "SKILL.md",
                str(exc),
                "Repair the YAML delimiters and mapping before any other review.",
            )
        )
        return _report(root, None, findings)

    name = str(frontmatter.get("name") or "").strip()
    description = " ".join(str(frontmatter.get("description") or "").split())
    if not name:
        findings.append(_finding("error", "missing-name", "SKILL.md", "name is required", "Add a portable skill name."))
    elif len(name) > 64 or not NAME_RE.fullmatch(name):
        findings.append(
            _finding(
                "error",
                "invalid-name",
                "SKILL.md",
                "name must be <=64 lowercase letters, digits, and hyphens",
                "Normalize the name and make the folder match it.",
            )
        )
    elif root.name != name:
        findings.append(
            _finding(
                "error",
                "folder-name-mismatch",
                "SKILL.md",
                f"folder {root.name!r} does not match name {name!r}",
                "Rename the folder or frontmatter so they match exactly.",
            )
        )

    if not description:
        findings.append(_finding("error", "missing-description", "SKILL.md", "description is required", "Describe capability and concrete trigger conditions."))
    else:
        if len(description) > 1024:
            findings.append(
                _finding(
                    "error",
                    "description-too-long",
                    "SKILL.md",
                    f"description is {len(description)} characters; maximum is 1024",
                    "Keep only capability, trigger context, and nearest exclusion.",
                )
            )
        if not TRIGGER_RE.search(description):
            findings.append(
                _finding(
                    "warning",
                    "description-missing-trigger-context",
                    "SKILL.md",
                    "description does not clearly say when to use the skill",
                    "Add concrete `Use when ...` or equivalent trigger language.",
                )
            )
        if HYPE_RE.search(description):
            findings.append(
                _finding(
                    "warning",
                    "description-hype",
                    "SKILL.md",
                    "description contains promotional or persona language",
                    "Replace self-praise with concrete capability and boundary terms.",
                )
            )

    unknown = sorted(set(frontmatter) - ALLOWED_FRONTMATTER)
    for key in unknown:
        findings.append(
            _finding(
                "warning",
                "unknown-frontmatter-key",
                "SKILL.md",
                f"frontmatter key may be host-specific or unsupported: {key}",
                "Confirm every target client accepts it or move it under documented metadata.",
            )
        )

    governed = bool(set(frontmatter) & GOVERNED_FIELDS)
    if governed:
        for key in sorted(GOVERNED_FIELDS):
            if frontmatter.get(key) in (None, "", [], {}):
                findings.append(
                    _finding(
                        "error",
                        f"missing-governed-{key.replace('_', '-')}",
                        "SKILL.md",
                        f"governed skill is missing {key}",
                        "Complete the repository governance metadata or use a portable profile consistently.",
                    )
                )
        if frontmatter.get("last_verified"):
            try:
                verified = date.fromisoformat(str(frontmatter["last_verified"]))
                if verified > date.today():
                    findings.append(
                        _finding(
                            "warning",
                            "future-last-verified",
                            "SKILL.md",
                            "last_verified is in the future",
                            "Use the date on which sources and behavior were actually checked.",
                        )
                    )
            except ValueError:
                findings.append(
                    _finding(
                        "error",
                        "invalid-last-verified",
                        "SKILL.md",
                        "last_verified must be YYYY-MM-DD",
                        "Use an ISO calendar date.",
                    )
                )
        routing = frontmatter.get("routing")
        if isinstance(routing, dict):
            triggers = routing.get("triggers")
            if not isinstance(triggers, list) or not all(
                isinstance(item, str) and item.strip() for item in triggers
            ):
                findings.append(
                    _finding(
                        "error",
                        "invalid-routing-triggers",
                        "SKILL.md",
                        "routing.triggers must be a non-empty list of strings",
                        "Add concrete curated trigger phrases.",
                    )
                )

    metadata = frontmatter.get("metadata")
    if isinstance(metadata, dict) and metadata.get("status") == "draft":
        findings.append(
            _finding(
                "warning",
                "draft-skill",
                "SKILL.md",
                "skill metadata is still marked draft",
                "Remove draft status only after placeholders and required proof are complete.",
            )
        )

    body_lines = len(body.splitlines())
    if body_lines > 500:
        findings.append(
            _finding(
                "error",
                "body-too-long",
                "SKILL.md",
                f"body has {body_lines} lines; maximum is 500",
                "Move optional detail into directly linked references.",
            )
        )
    elif body_lines > 250:
        findings.append(
            _finding(
                "warning",
                "body-context-heavy",
                "SKILL.md",
                f"body has {body_lines} lines; target is <=250",
                "Keep only always-needed decisions and progressively disclose the rest.",
            )
        )

    headings = {
        match.group(1).strip().lower()
        for match in re.finditer(r"^##\s+(.+?)\s*$", body, re.M)
    }
    for required in REQUIRED_BODY_SECTIONS:
        if not any(required in heading for heading in headings):
            findings.append(
                _finding(
                    "warning",
                    f"missing-body-{required}",
                    "SKILL.md",
                    f"no H2 section communicates the {required} contract",
                    f"Add a concise {required.title()} section or make the equivalent section explicit.",
                )
            )

    if PLACEHOLDER_RE.search(body):
        findings.append(
            _finding(
                "error",
                "draft-placeholder",
                "SKILL.md",
                "body contains an unresolved placeholder or TODO marker",
                "Replace every placeholder with grounded instructions before publication.",
            )
        )

    all_files = [
        path for path in root.rglob("*") if path.is_file() and not _ignored(path.relative_to(root))
    ]
    for path in root.rglob("*"):
        if _ignored(path.relative_to(root)):
            continue
        rel = path.relative_to(root)
        if path.is_symlink():
            findings.append(
                _finding(
                    "error",
                    "symlink-resource",
                    rel,
                    "skill packages must not use symlinks",
                    "Copy or generate a path-confined resource instead.",
                )
            )
        if rel.parts and rel.parts[0] in {"references", "scripts", "assets"} and len(rel.parts) > 2:
            findings.append(
                _finding(
                    "error",
                    "nested-resource",
                    rel,
                    "resource is nested more than one level below its category",
                    "Flatten the resource and link it directly from SKILL.md.",
                )
            )

    markdown_files: list[Path] = []
    for path in all_files:
        if path.suffix.lower() in {".md", ".markdown"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                findings.append(
                    _finding(
                        "error",
                        "unreadable-markdown",
                        path.relative_to(root),
                        str(exc),
                        "Store the resource as readable UTF-8 text.",
                    )
                )
                continue
            markdown_files.append(path)
            if path.parent.name == "references" and len(text.splitlines()) > 100 and not TOC_RE.search(text):
                findings.append(
                    _finding(
                        "warning",
                        "long-reference-without-contents",
                        path.relative_to(root),
                        "reference exceeds 100 lines without a contents heading",
                        "Add a concise contents list so the reader can navigate selectively.",
                    )
                )
            if path != skill_md and PLACEHOLDER_RE.search(text):
                findings.append(
                    _finding(
                        "error",
                        "resource-placeholder",
                        path.relative_to(root),
                        "resource contains an unresolved placeholder or TODO marker",
                        "Replace the placeholder or mark the whole skill as a draft outside publication paths.",
                    )
                )

    for path in (root / "scripts").glob("*") if (root / "scripts").is_dir() else []:
        if not path.is_file():
            continue
        if path.suffix.lower() in {".py", ".sh"}:
            try:
                first = path.read_text(encoding="utf-8").splitlines()[0]
            except (OSError, UnicodeError, IndexError):
                first = ""
            if not first.startswith("#!"):
                findings.append(
                    _finding(
                        "warning",
                        "script-missing-shebang",
                        path.relative_to(root),
                        "executable helper has no shebang",
                        "Add an interpreter shebang and document dependencies.",
                    )
                )
        if os.name != "nt" and path.suffix.lower() in {".py", ".sh"} and not os.access(path, os.X_OK):
            findings.append(
                _finding(
                    "warning",
                    "script-not-executable",
                    path.relative_to(root),
                    "helper is not executable on this filesystem",
                    "Set the executable bit when the repository and target client preserve it.",
                )
            )

    findings.extend(_scan_links(root, markdown_files))
    findings.extend(_scan_secret_signatures(root, all_files))
    findings.extend(_scan_eval_suite(root, frontmatter))
    return _report(root, name or None, findings)


def _report(root: Path, name: str | None, findings: list[Finding]) -> dict[str, Any]:
    unique = sorted(set(findings))
    errors = sum(item.severity == "error" for item in unique)
    warnings = sum(item.severity == "warning" for item in unique)
    score = max(0, 100 - errors * 20 - warnings * 3)
    return {
        "schema_version": 1,
        "skill": name or root.name,
        "root": str(root),
        "passed": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "quality_score": score,
        "findings": [asdict(item) for item in unique],
    }


def _discover(inputs: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for raw in inputs:
        path = raw.expanduser().resolve()
        if path.name == "SKILL.md" and path.is_file():
            roots.append(path.parent)
        elif (path / "SKILL.md").is_file():
            roots.append(path)
        elif path.is_dir():
            roots.extend(sorted(item.parent for item in path.glob("*/SKILL.md")))
        else:
            roots.append(path)
    ordered: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            seen.add(root)
            ordered.append(root)
    return ordered


def _render_text(reports: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for report in reports:
        lines.append(
            f"{report['skill']}: {report['errors']} error(s), "
            f"{report['warnings']} warning(s), score {report['quality_score']}"
        )
        for item in report["findings"]:
            lines.append(
                f"  {item['severity'].upper()} {item['code']} "
                f"{item['path']}: {item['message']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat warnings as blocking")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args(argv)

    roots = _discover(args.paths)
    if not roots:
        payload = {
            "schema_version": 1,
            "passed": False,
            "error": {"code": "no_skills_found", "message": "no skill packages found"},
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 1

    reports = [audit_skill(root) for root in roots]
    total_errors = sum(report["errors"] for report in reports)
    total_warnings = sum(report["warnings"] for report in reports)
    passed = total_errors == 0 and (not args.strict or total_warnings == 0)
    payload = {
        "schema_version": 1,
        "passed": passed,
        "strict": args.strict,
        "skill_count": len(reports),
        "errors": total_errors,
        "warnings": total_warnings,
        "reports": reports,
    }

    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.format == "text":
        print(_render_text(reports))
    else:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
