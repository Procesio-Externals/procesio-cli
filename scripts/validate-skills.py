#!/usr/bin/env python3
"""Validate registered Agent Skills and their repository integrations.

The validator enforces what prose cannot: portable frontmatter, bounded skill
bodies, resolvable bundled resources, shallow resource layout, and command
examples that name real tools, agents, actions, and arguments. A baseline file
may temporarily waive known findings; it never hides new findings.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS = REPO / "skills"
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_CODE_PATH_RE = re.compile(
    r"`((?:(?:references|scripts|assets)/)?[^`\n]+\.(?:md|sql|py|sh|ps1|js|ts|json|yaml|yml|html))`",
    re.IGNORECASE,
)
_RUN_RE = re.compile(
    r"python\s+scripts/run-(tool|agent)\.py\s+([a-z0-9-]+)(?:\s+([a-z0-9-]+))?",
    re.IGNORECASE,
)
_OPTION_RE = re.compile(r"--([a-z0-9][a-z0-9-]*)", re.IGNORECASE)
_ALLOWED_FRONTMATTER = {
    "name", "description", "version", "compatibility", "license", "allowed-tools",
    "disable-model-invocation", "argument-hint", "routing", "metadata", "owner",
    "last_verified", "baseline_version", "eval_suite", "source_policy",
}


@dataclass(frozen=True, order=True)
class Finding:
    severity: str
    code: str
    skill: str
    path: str
    message: str


def _split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening ---")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = yaml.safe_load("\n".join(lines[1:index]))
            if not isinstance(raw, dict):
                raise ValueError("frontmatter must be a mapping")
            return raw, "\n".join(lines[index + 1:])
    raise ValueError("missing closing ---")


def _load_capabilities(repo: Path) -> dict[str, dict[str, dict[str, set[str]]]]:
    result: dict[str, dict[str, dict[str, set[str]]]] = {"tool": {}, "agent": {}}
    for kind, folder, manifest_name in (
        ("tool", "tools", "tool.yaml"), ("agent", "agents", "agent.yaml")
    ):
        root = repo / folder
        if not root.exists():
            continue
        for path in sorted(root.glob(f"*/{manifest_name}")):
            if path.parent.name.startswith("_"):
                continue
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            actions: dict[str, set[str]] = {}
            for action in raw.get("actions") or []:
                if not isinstance(action, dict) or not action.get("name"):
                    continue
                actions[str(action["name"])] = {
                    str(arg["name"])
                    for arg in (action.get("args") or [])
                    if isinstance(arg, dict) and arg.get("name")
                }
            result[kind][str(raw["name"])] = actions
    return result


def _finding(code: str, skill: str, path: Path | str, message: str,
             severity: str = "error") -> Finding:
    return Finding(severity=severity, code=code, skill=skill,
                   path=str(path).replace("\\", "/"), message=message)


def _candidate_paths(raw: str, source: Path, root: Path) -> list[Path]:
    cleaned = raw.strip().split("#", 1)[0].split("?", 1)[0]
    posix = PurePosixPath(cleaned)
    if not cleaned or cleaned.startswith(("#", "http://", "https://", "mailto:")):
        return []
    if posix.is_absolute() or ".." in posix.parts:
        return [root.parent / "__unsafe_reference__"]
    path = Path(*posix.parts)
    candidates = [source.parent / path]
    if len(posix.parts) == 1:
        candidates += [root / path, root / "references" / path,
                       root / "scripts" / path, root / "assets" / path]
    else:
        candidates.append(root / path)
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _scan_references(skill: str, root: Path, source: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    refs = [match.group(1).strip().split()[0] for match in _MARKDOWN_LINK_RE.finditer(text)]
    refs += [match.group(1).strip() for match in _CODE_PATH_RE.finditer(text)]
    for raw in sorted(set(refs)):
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        candidates = _candidate_paths(raw, source, root)
        if not candidates:
            continue
        if any("__unsafe_reference__" in candidate.parts for candidate in candidates):
            findings.append(_finding("unsafe-reference", skill, source.relative_to(root),
                                     f"reference escapes the skill root: {raw}"))
            continue
        if not any(candidate.exists() for candidate in candidates):
            findings.append(_finding("missing-reference", skill, source.relative_to(root),
                                     f"referenced resource does not exist: {raw}"))
    return findings


def _scan_commands(skill: str, root: Path, source: Path, text: str,
                   capabilities: dict[str, dict[str, dict[str, set[str]]]]) -> list[Finding]:
    findings: list[Finding] = []
    for match in _RUN_RE.finditer(text):
        kind, name, action = (value.lower() if value else value for value in match.groups())
        catalog = capabilities[kind]
        if name not in catalog:
            findings.append(_finding("unknown-capability", skill, source.relative_to(root),
                                     f"unknown {kind}: {name}"))
            continue
        if not action or action.startswith("<"):
            continue
        actions = catalog[name]
        if actions and action not in actions:
            findings.append(_finding("unknown-action", skill, source.relative_to(root),
                                     f"unknown {kind} action: {name} {action}"))
            continue
        if action in actions:
            invocation = match.string[match.start():match.string.find("\n", match.start())]
            for option in _OPTION_RE.findall(invocation):
                if option not in actions[action] and option not in {"help"}:
                    findings.append(_finding(
                        "unknown-argument", skill, source.relative_to(root),
                        f"unknown argument --{option} for {name} {action}", severity="warning"
                    ))
    return findings


def validate_skill(skill_md: Path, repo: Path,
                   capabilities: dict[str, dict[str, dict[str, set[str]]]]) -> list[Finding]:
    root = skill_md.parent
    folder_name = root.name
    findings: list[Finding] = []
    try:
        frontmatter, body = _split_frontmatter(skill_md)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        return [_finding("invalid-frontmatter", folder_name, "SKILL.md", str(exc))]

    name = str(frontmatter.get("name") or "").strip()
    description = " ".join(str(frontmatter.get("description") or "").split())
    skill = name or folder_name
    if not name:
        findings.append(_finding("missing-name", skill, "SKILL.md", "frontmatter name is required"))
    elif not _NAME_RE.fullmatch(name) or len(name) > 64:
        findings.append(_finding("invalid-name", skill, "SKILL.md",
                                 "name must be <=64 lowercase letters, digits, and hyphens"))
    if name and name != folder_name:
        findings.append(_finding("folder-name-mismatch", skill, "SKILL.md",
                                 f"folder {folder_name!r} does not match name {name!r}"))
    if not description:
        findings.append(_finding("missing-description", skill, "SKILL.md",
                                 "frontmatter description is required"))
    elif len(description) > 1024:
        findings.append(_finding("description-too-long", skill, "SKILL.md",
                                 f"description is {len(description)} characters; maximum is 1024"))
    body_lines = len(body.splitlines())
    if body_lines > 500:
        findings.append(_finding("body-too-long", skill, "SKILL.md",
                                 f"SKILL.md body has {body_lines} lines; maximum is 500"))

    for key in sorted(set(frontmatter) - _ALLOWED_FRONTMATTER):
        findings.append(_finding("unknown-frontmatter-key", skill, "SKILL.md",
                                 f"unrecognized frontmatter key: {key}", severity="warning"))

    if frontmatter.get("last_verified"):
        try:
            date.fromisoformat(str(frontmatter["last_verified"]))
        except ValueError:
            findings.append(_finding("invalid-last-verified", skill, "SKILL.md",
                                     "last_verified must be YYYY-MM-DD"))
    if frontmatter.get("eval_suite"):
        target = root / str(frontmatter["eval_suite"])
        if not target.is_file():
            findings.append(_finding("missing-eval-suite", skill, "SKILL.md",
                                     f"eval_suite does not exist: {frontmatter['eval_suite']}"))

    # Python imports performed by tests can create bytecode caches inside a
    # skill's scripts directory. They are transient interpreter artifacts, not
    # bundled skill resources, and must not turn test order into validation state.
    files = (
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() != ".pyc"
        and "__pycache__" not in path.relative_to(root).parts
    )
    for file in sorted(files):
        rel = file.relative_to(root)
        if rel.parts[0] in {"references", "scripts", "assets"} and len(rel.parts) > 2:
            findings.append(_finding("nested-resource", skill, rel,
                                     "bundled resources must stay one level below their category"))
        if rel.parts[0] == "scripts" and file.suffix.lower() in {".html", ".svg", ".png", ".jpg", ".jpeg"}:
            findings.append(_finding("asset-in-scripts", skill, rel,
                                     "output templates and media belong under assets/"))
        if rel.parts[0] == "references" and "scripts" in rel.parts[1:-1]:
            findings.append(_finding("script-in-references", skill, rel,
                                     "executable helpers belong directly under scripts/"))
        if file.suffix.lower() in {".md", ".markdown"}:
            try:
                text = file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                findings.append(_finding("unreadable-resource", skill, rel, str(exc)))
                continue
            findings.extend(_scan_references(skill, root, file, text))
            findings.extend(_scan_commands(skill, root, file, text, capabilities))

    return sorted(set(findings))


def validate_repo(skills_root: Path = DEFAULT_SKILLS, repo: Path = REPO) -> list[Finding]:
    capabilities = _load_capabilities(repo)
    findings: list[Finding] = []
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        if skill_md.parent.name.startswith("_") or skill_md.parent.name == "tests":
            continue
        findings.extend(validate_skill(skill_md, repo, capabilities))
    if not list(skills_root.glob("*/SKILL.md")):
        findings.append(_finding("no-skills", "<repository>", skills_root,
                                 "no skills/*/SKILL.md files found"))
    return sorted(set(findings))


def _load_waivers(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("allow", []) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected an allow list")
    return [{key: str(value) for key, value in row.items()} for row in rows]


def _waived(finding: Finding, waivers: Iterable[dict[str, str]]) -> bool:
    payload = asdict(finding)
    for waiver in waivers:
        if all(fnmatch.fnmatch(payload.get(key, ""), pattern) for key, pattern in waiver.items()):
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--baseline", type=Path,
                        help="JSON waiver file for known findings; new findings still fail")
    parser.add_argument("--strict-warnings", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    findings = validate_repo(args.skills_root, args.repo)
    waivers = _load_waivers(args.baseline)
    rows = []
    blocking = []
    for finding in findings:
        waived = _waived(finding, waivers)
        row = {**asdict(finding), "waived": waived}
        rows.append(row)
        if not waived and (finding.severity == "error" or args.strict_warnings):
            blocking.append(row)

    report = {
        "schema_version": 1,
        "skills_root": str(args.skills_root),
        "finding_count": len(rows),
        "blocking_count": len(blocking),
        "findings": rows,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for row in rows:
            marker = "WAIVED" if row["waived"] else row["severity"].upper()
            print(f"{marker}: {row['skill']}:{row['path']}: {row['code']}: {row['message']}")
        print(f"{len(rows)} finding(s), {len(blocking)} blocking")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
