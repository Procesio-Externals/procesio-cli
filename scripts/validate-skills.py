#!/usr/bin/env python3
"""Validate registered Agent Skills and their repository integrations.

WHAT THIS ENFORCES
------------------
Two guards in one script, dispatched by where a SKILL.md lives.

`skills/*/SKILL.md` (hand-written skills) get the full check: portable
frontmatter, a name that matches its folder, a bounded body, resolvable bundled
resources, shallow resource layout, and command examples that name real tools,
agents, actions, and arguments. A `--baseline` file may temporarily waive known
findings; it never hides new ones.

`tools/*/SKILL.md` and `agents/*/SKILL.md` (GENERATED manuals) get only the
loadability check: the frontmatter must parse and carry a name and description
within the length caps. The stricter skill rules are deliberately NOT applied to
them, because a generated manual legitimately declares a manifest name that can
differ from its folder and a body far longer than a hand-written skill. This is
the read-back the generated-manual pipeline never had: the generator built its
YAML frontmatter by string interpolation, so any manifest description carrying a
colon-space ended the key and produced a document no loader could read. It held
for roughly half the manuals in the tree and hit the best-described tools first.

HOOK CONTRACT
-------------
`scripts/hook-lib.sh :: hook_run_skill_validate` calls this as
`validate-skills.py --staged` and keys on the exit code: 0 pass, 1 block, 2
could-not-run (nothing checked, so nothing cleared). The staged set is
VCS-aware, exactly like `scripts/secret_scan.py`: git's staged set where there
is a `.git`, SVN's locally-modified set otherwise, because this repo is
published through both.

Spec: https://agentskills.io/specification

Usage:
  python scripts/validate-skills.py                 # the whole tree
  python scripts/validate-skills.py --staged        # only changed SKILL.md (hook path)
  python scripts/validate-skills.py path/to/SKILL.md ...
  python scripts/validate-skills.py --json          # machine-readable report

Exit codes:
  0  clean
  1  at least one blocking finding
  2  could not run (bad usage, unreadable tree, unenumerable staged set)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not a finding
    print("validate-skills: PyYAML is not installed - nothing checked.", file=sys.stderr)
    raise SystemExit(2)

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
    "last_verified", "baseline_version", "eval_suite", "source_policy", "tier",
}

MAX_NAME = 64
MAX_DESCRIPTION = 1024


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
    elif not _NAME_RE.fullmatch(name) or len(name) > MAX_NAME:
        findings.append(_finding("invalid-name", skill, "SKILL.md",
                                 "name must be <=64 lowercase letters, digits, and hyphens"))
    if name and name != folder_name:
        findings.append(_finding("folder-name-mismatch", skill, "SKILL.md",
                                 f"folder {folder_name!r} does not match name {name!r}"))
    if not description:
        findings.append(_finding("missing-description", skill, "SKILL.md",
                                 "frontmatter description is required"))
    elif len(description) > MAX_DESCRIPTION:
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


def loadability(skill_md: Path, repo: Path) -> list[Finding]:
    """The generated-manual guard: the file must parse and carry a name and
    description within the caps. Deliberately no folder/name, body-length, or
    resource rules - a generated manual legitimately breaks those."""
    try:
        rel = skill_md.relative_to(repo).as_posix()
    except ValueError:
        rel = skill_md.name
    folder = skill_md.parent.name
    try:
        frontmatter, _ = _split_frontmatter(skill_md)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        return [_finding("invalid-frontmatter", folder, rel, str(exc))]
    findings: list[Finding] = []
    name = str(frontmatter.get("name") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    skill = name or folder
    if not name:
        findings.append(_finding("missing-name", skill, rel, "frontmatter name is required"))
    elif len(name) > MAX_NAME:
        findings.append(_finding("invalid-name", skill, rel,
                                 f"name is {len(name)} chars, limit {MAX_NAME}"))
    if not description:
        findings.append(_finding("missing-description", skill, rel,
                                 "frontmatter description is required"))
    elif len(description) > MAX_DESCRIPTION:
        over = len(description) - MAX_DESCRIPTION
        findings.append(_finding("description-too-long", skill, rel,
                                 f"description is {len(description)} chars, limit "
                                 f"{MAX_DESCRIPTION} (over by {over})"))
    return findings


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


def _is_skill_path(path: Path, repo: Path) -> bool:
    try:
        parts = path.resolve().relative_to(repo.resolve()).parts
    except ValueError:
        return "skills" in path.parts
    return bool(parts) and parts[0] == "skills"


def governed_folders(skills_root: Path) -> set[str]:
    """Skill folders that opt into the governance/eval discipline, by the
    `source_policy` marker. The full rubric (folder/name, body length, resolvable
    and shallow resources, resolvable command examples) is authored for these.
    Imported/portable skills and generated tool manuals omit the marker and get
    only the loadability guard, so a legitimate imported skill - one that runs
    long, references a repo file outside its own folder, or ships nested fonts -
    is not blocked by a rubric it was never written to. In procesio-cli, whose
    `skills/` IS the portfolio, every skill is governed and the two coincide."""
    names: set[str] = set()
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        if skill_md.parent.name.startswith("_") or skill_md.parent.name == "tests":
            continue
        try:
            frontmatter, _ = _split_frontmatter(skill_md)
        except (OSError, UnicodeError, yaml.YAMLError, ValueError):
            continue
        if frontmatter.get("source_policy"):
            names.add(skill_md.parent.name)
    return names


def check_path(path: Path, repo: Path,
               capabilities: dict[str, dict[str, dict[str, set[str]]]],
               governed: set[str]) -> list[Finding]:
    """Dispatch one SKILL.md: the full skill rubric for a governed skill, the
    loadability guard for an imported skill or a generated manual (tools/, agents/)."""
    if _is_skill_path(path, repo) and path.parent.name in governed:
        return validate_skill(path, repo, capabilities)
    return loadability(path, repo)


def _all_manual_files(repo: Path) -> list[Path]:
    manuals: list[Path] = []
    for folder in ("tools", "agents"):
        root = repo / folder
        if root.exists():
            manuals += [p for p in sorted(root.glob("*/SKILL.md"))
                        if not p.parent.name.startswith("_")]
    return manuals


def _changed_skill_files(repo: Path) -> list[Path]:
    """The SKILL.md files this commit would carry, VCS-aware (git staged set, or
    SVN locally-modified set). A path that no longer exists (a delete) is skipped."""
    is_git = (repo / ".git").exists()
    if is_git:
        cmd = ["git", "-C", str(repo), "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    else:
        cmd = ["svn", "status", str(repo)]
    try:
        raw = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=120).stdout
    except Exception as exc:  # noqa: BLE001 - cannot enumerate means cannot clear
        print(f"validate-skills: could not list changed files ({exc}).", file=sys.stderr)
        raise SystemExit(2)

    out: list[str] = []
    for line in raw.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if is_git:
            path = line
        else:
            if line[:1] not in ("A", "M"):
                continue
            path = line[1:].strip()
        if path.replace("\\", "/").endswith("SKILL.md"):
            out.append(path)

    files: list[Path] = []
    for p in out:
        candidate = Path(p)
        if not candidate.is_absolute():
            candidate = repo / p
        if candidate.exists():
            files.append(candidate)
    return sorted(set(files))


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
    parser = argparse.ArgumentParser(description="Validate registered Agent Skills.")
    parser.add_argument("paths", nargs="*", help="SKILL.md files (default: the whole tree)")
    parser.add_argument("--staged", action="store_true",
                        help="check only the SKILL.md files this commit would carry")
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--baseline", type=Path,
                        help="JSON waiver file for known findings; new findings still fail")
    parser.add_argument("--strict-warnings", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = args.repo
    capabilities = _load_capabilities(repo)
    governed = governed_folders(args.skills_root)

    if args.paths:
        files = [Path(p) if Path(p).is_absolute() else repo / p for p in args.paths]
        findings = [f for path in files for f in check_path(path, repo, capabilities, governed)]
    elif args.staged:
        files = _changed_skill_files(repo)
        if not files:
            print("validate-skills: no SKILL.md in scope - nothing to check.")
            return 0
        findings = [f for path in files for f in check_path(path, repo, capabilities, governed)]
    else:
        findings = []
        skill_files = sorted(args.skills_root.glob("*/SKILL.md"))
        for skill_md in skill_files:
            if skill_md.parent.name.startswith("_") or skill_md.parent.name == "tests":
                continue
            findings.extend(check_path(skill_md, repo, capabilities, governed))
        if not skill_files:
            findings.append(_finding("no-skills", "<repository>", args.skills_root,
                                     "no skills/*/SKILL.md files found"))
        for manual in _all_manual_files(repo):
            findings.extend(loadability(manual, repo))

    findings = sorted(set(findings))
    try:
        waivers = _load_waivers(args.baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validate-skills: could not read baseline ({exc}).", file=sys.stderr)
        return 2

    rows = []
    blocking = []
    for finding in findings:
        waived = _waived(finding, waivers)
        row = {**asdict(finding), "waived": waived}
        rows.append(row)
        if not waived and (finding.severity == "error" or args.strict_warnings):
            blocking.append(row)

    if args.json:
        report = {
            "schema_version": 1,
            "finding_count": len(rows),
            "blocking_count": len(blocking),
            "findings": rows,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not rows:
        print("validate-skills: clean")
    else:
        for row in rows:
            marker = "WAIVED" if row["waived"] else row["severity"].upper()
            print(f"{marker}: {row['skill']}:{row['path']}: {row['code']}: {row['message']}")
        print(f"{len(rows)} finding(s), {len(blocking)} blocking")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
