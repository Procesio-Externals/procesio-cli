#!/usr/bin/env python3
"""Safely scaffold an evidence-ready Agent Skill package.

The command never overwrites an existing skill directory. It creates a draft
SKILL.md and fixed-rubric evaluation skeleton with explicit causal, boundary,
safety, progressive-disclosure, and release-proof placeholders. It makes no
model, network, repository, or secret-store calls.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
RESOURCE_CATEGORIES = ("references", "scripts", "assets")


def _yaml_string(value: str) -> str:
    """JSON string literals are valid YAML scalars and avoid quoting surprises."""
    return json.dumps(value, ensure_ascii=False)


def _title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def _validate_name(name: str) -> None:
    if len(name) > MAX_NAME or not NAME_RE.fullmatch(name):
        raise ValueError(
            "name must be <=64 lowercase letters, digits, and hyphens, "
            "with no leading, trailing, or repeated hyphen"
        )


def _validate_description(description: str) -> None:
    normalized = " ".join(description.split())
    if not normalized:
        raise ValueError("description must not be empty")
    if len(normalized) > MAX_DESCRIPTION:
        raise ValueError(f"description exceeds {MAX_DESCRIPTION} characters")


def _target(root: Path, name: str) -> tuple[Path, Path]:
    _validate_name(name)
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / name).resolve()
    if target.parent != root:
        raise ValueError("target escapes the requested root")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing path: {target}")
    return root, target


def _frontmatter(args: argparse.Namespace) -> str:
    description = " ".join(args.description.split())
    lines = ["---", f"name: {args.name}", f"description: {_yaml_string(description)}"]
    if args.compatibility:
        lines.append(f"compatibility: {_yaml_string(args.compatibility.strip())}")
    if args.license:
        lines.append(f"license: {_yaml_string(args.license.strip())}")

    if args.profile == "governed":
        if not args.owner:
            raise ValueError("--owner is required for --profile governed")
        if not args.baseline_version:
            raise ValueError("--baseline-version is required for --profile governed")
        if not args.trigger:
            raise ValueError("at least one --trigger is required for --profile governed")
        lines += [
            f"version: {_yaml_string(args.version)}",
            f"owner: {_yaml_string(args.owner.strip())}",
            f"last_verified: {args.last_verified}",
            f"baseline_version: {_yaml_string(args.baseline_version.strip())}",
            "eval_suite: evals/evals.json",
            f"source_policy: {args.source_policy}",
            "routing:",
            "  triggers:",
        ]
        lines.extend(f"    - {_yaml_string(item.strip())}" for item in args.trigger)
        lines += [
            "  primary_action: engineer",
            f"  example: get-skill.py {args.name} --content",
        ]
    elif args.trigger:
        lines += ["routing:", "  triggers:"]
        lines.extend(f"    - {_yaml_string(item.strip())}" for item in args.trigger)

    lines += [
        "metadata:",
        "  status: draft",
        f"  evidence-tier: {_yaml_string(str(args.evidence_tier))}",
        "---",
    ]
    return "\n".join(lines)


def _list_or_placeholder(values: list[str], placeholder: str) -> str:
    if values:
        return "\n".join(f"- {item.strip()}" for item in values)
    return f"- {{{{{placeholder}}}}}"


def _skill_body(args: argparse.Namespace) -> str:
    title = args.title.strip() if args.title else _title(args.name)
    triggers = _list_or_placeholder(args.trigger, "REPLACE_WITH_CONCRETE_TRIGGER")
    non_triggers = _list_or_placeholder(args.non_trigger, "REPLACE_WITH_NEAREST_NON_TRIGGER_AND_OWNER")
    clients = _list_or_placeholder(args.target_client, "REPLACE_WITH_TARGET_CLIENT_AND_VERSION")
    return f"""# {title}

## Outcome

{{{{REPLACE_WITH_OBSERVABLE_USER_OUTCOME}}}}

State the behavior this package changes relative to no skill or the immutable prior skill.

## Causal contract

- Baseline behavior: {{{{REPLACE_WITH_OBSERVED_BASELINE_BEHAVIOR}}}}
- Intervention hypothesis: {{{{REPLACE_WITH_SPECIFIC_CAUSAL_INSTRUCTION_OR_RESOURCE}}}}
- Protected successes: {{{{REPLACE_WITH_BASELINE_SUCCESSES_THAT_MUST_NOT_REGRESS}}}}
- Evidence tier: {args.evidence_tier}
- Direct outcome or preference proof: {{{{REPLACE_WITH_STRONGEST_AVAILABLE_PROOF}}}}

## Boundary

Use this skill when:

{triggers}

Do not use this skill when:

{non_triggers}

Target clients and environments:

{clients}

## Evidence and uncertainty

- Authoritative sources or artifacts: {{{{REPLACE_WITH_SOURCE_OWNERS_AND_VERSIONS}}}}
- Stable invariants: {{{{REPLACE_WITH_PROVEN_INVARIANTS}}}}
- Heuristics and scope: {{{{REPLACE_WITH_CALIBRATED_HEURISTICS}}}}
- Unknowns and escalation owner: {{{{REPLACE_WITH_STOP_OR_HANDOFF_CONDITIONS}}}}

## Non-negotiables

- {{{{REPLACE_WITH_INVARIANT_THAT_PREVENTS_THE_COSTLIEST_FAILURE}}}}
- {{{{REPLACE_WITH_PERMISSION_RETRY_PRIVACY_OR_SAFETY_RULE}}}}
- Do not claim completion from a proxy when direct observation is available.

## Workflow

1. {{{{REPLACE_WITH_GROUNDING_AND_PRECONDITION_STEP}}}}
2. {{{{REPLACE_WITH_CORE_CLASSIFICATION_OR_DECISION}}}}
3. {{{{REPLACE_WITH_ACTION_OR_HANDOFF}}}}
4. {{{{REPLACE_WITH_DIRECT_VERIFICATION_AND_RECOVERY}}}}
5. Report the result, evidence, uncertainty, and proof that remains unavailable.

## Resources

Create only resources that alter execution. Link each one here with an explicit load or run condition.

- `references/`: stable or conditional knowledge and source-owned detail.
- `scripts/`: deterministic, repeated, fragile, or safety-critical operations.
- `assets/`: output templates or media, never hidden instructions.

Delete empty resource directories before publication when the target repository prefers a minimal package.

## Verification

{{{{REPLACE_WITH_REAL_ARTIFACT_STATE_OUTPUT_OR_BLINDED_PREFERENCE_THAT_PROVES_SUCCESS}}}}

Required evidence:

- structural and security validation;
- positive, negative, overlap, and pressure routing behavior;
- paired baseline/candidate task evidence with fixed atomic criteria;
- repairs and regressions on the same cases;
- held-out validation and untouched final test appropriate to evidence tier {args.evidence_tier};
- controlled field proof for operational or high-consequence workflows.

## Release conditions

Freeze cases, split membership, rubric IDs, objective hierarchy, minimum effect, edit budget, and stopping rules before formal evaluation. Mark this package draft until every applicable hard constraint passes. Preserve the baseline, reports, rejected hypotheses, residual risks, and rollback or retirement path.
"""


def _criterion(identifier: str, description: str) -> dict[str, Any]:
    return {"id": identifier, "description": description, "required": True}


def _eval_skeleton(name: str, evidence_tier: int) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "skill_name": name,
        "suite_version": 1,
        "rubric_contract": "fixed-jury-rubric-v2",
        "status": "draft",
        "evidence_tier": evidence_tier,
        "experiment_contract": {
            "baseline": "no-skill for a new capability; immutable prior package for an existing skill",
            "train": "failure discovery and hypothesis generation only",
            "validation": "strict promotion of bounded candidates",
            "test": "untouched until final candidate selection",
            "field": "direct user-path proof when operational or consequential",
            "report_repairs_and_regressions": True,
        },
        "cases": [
            {
                "id": "core-success",
                "kind": "positive",
                "prompt": "{{REPLACE_WITH_REALISTIC_CORE_USER_PROMPT}}",
                "expected_skill": name,
                "forbidden_skills": [],
                "expected_output": {
                    "rubric_version": 1,
                    "criteria": [
                        _criterion(
                            "produces_the_required_outcome",
                            "Pass only when {{REPLACE_WITH_ONE_ATOMIC_CORE_OUTCOME}}.",
                        ),
                        _criterion(
                            "provides_direct_verification",
                            "Pass only when {{REPLACE_WITH_THE_DIRECT_PROOF_REQUIREMENT}}.",
                        ),
                        _criterion(
                            "preserves_a_baseline_success",
                            "Pass only when {{REPLACE_WITH_ONE_SUCCESS_THAT_MUST_NOT_REGRESS}}.",
                        ),
                    ],
                },
            },
            {
                "id": "clear-non-trigger",
                "kind": "negative",
                "prompt": "{{REPLACE_WITH_NEARBY_PROMPT_THAT_MUST_NOT_USE_THIS_SKILL}}",
                "expected_skill": None,
                "forbidden_skills": [name],
                "expected_output": {
                    "rubric_version": 1,
                    "criteria": [
                        _criterion(
                            "does_not_apply_the_skill_outside_scope",
                            "Pass only when the response does not apply this skill outside its stated boundary.",
                        ),
                        _criterion(
                            "uses_the_correct_alternative_or_abstains",
                            "Pass only when {{REPLACE_WITH_CORRECT_ALTERNATIVE_OR_ABSTENTION}}.",
                        ),
                    ],
                },
            },
            {
                "id": "nearest-owner-overlap",
                "kind": "overlap",
                "prompt": "{{REPLACE_WITH_PROMPT_NEAR_THE_CLOSEST_COMPETING_SKILL}}",
                "expected_skill": "{{REPLACE_WITH_EXPECTED_OWNER_OR_NULL}}",
                "forbidden_skills": [name],
                "expected_output": {
                    "rubric_version": 1,
                    "criteria": [
                        _criterion(
                            "respects_the_primary_owner_boundary",
                            "Pass only when {{REPLACE_WITH_THE_OWNER_BOUNDARY_DECISION}}.",
                        ),
                        _criterion(
                            "preserves_any_explicit_handoff",
                            "Pass only when {{REPLACE_WITH_HANDOFF_AND_RETURN_CONDITION}}.",
                        ),
                    ],
                },
            },
            {
                "id": "unsafe-shortcut-pressure",
                "kind": "pressure",
                "prompt": "{{REPLACE_WITH_PROMPT_PRESSURING_AN_UNSAFE_OR_FALSE_SHORTCUT}}",
                "expected_skill": name,
                "forbidden_skills": [],
                "expected_output": {
                    "rubric_version": 1,
                    "criteria": [
                        _criterion(
                            "rejects_the_unsafe_shortcut",
                            "Pass only when {{REPLACE_WITH_EXACT_SHORTCUT_TO_REJECT}}.",
                        ),
                        _criterion(
                            "uses_the_safe_verifiable_path",
                            "Pass only when {{REPLACE_WITH_SAFE_SEQUENCE_AND_DIRECT_PROOF}}.",
                        ),
                    ],
                },
            },
        ],
    }


def scaffold(args: argparse.Namespace) -> dict[str, Any]:
    _validate_description(args.description)
    _root, target = _target(args.root, args.name)
    created: list[str] = []
    try:
        (target / "evals").mkdir(parents=True)
        for category in RESOURCE_CATEGORIES:
            (target / category).mkdir()

        skill_md = target / "SKILL.md"
        skill_md.write_text(
            _frontmatter(args) + "\n\n" + _skill_body(args),
            encoding="utf-8",
            newline="\n",
        )
        created.append(str(skill_md))

        evals = target / "evals" / "evals.json"
        evals.write_text(
            json.dumps(_eval_skeleton(args.name, args.evidence_tier), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        created.append(str(evals))
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise

    return {
        "schema_version": 2,
        "created": True,
        "status": "draft",
        "profile": args.profile,
        "evidence_tier": args.evidence_tier,
        "skill_name": args.name,
        "skill_root": str(target),
        "created_files": created,
        "next_actions": [
            "replace every {{REPLACE...}} placeholder from real evidence",
            "remove unused resource directories or add only directly linked resources",
            "run audit_skill.py with --strict and the host repository validators",
            "freeze train, validation, test, field, rubrics, objective, edit budget, and stopping rules",
            "compare against no skill or the immutable prior package before claiming improvement",
            "record repairs, regressions, costs, uncertainty, and direct field proof appropriate to the evidence tier",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--root", type=Path, default=Path("skills"))
    parser.add_argument("--description", required=True)
    parser.add_argument("--title")
    parser.add_argument("--profile", choices=("portable", "governed"), default="portable")
    parser.add_argument("--compatibility")
    parser.add_argument("--license")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--owner")
    parser.add_argument("--baseline-version")
    parser.add_argument("--last-verified", default=date.today().isoformat())
    parser.add_argument(
        "--source-policy",
        choices=("generated", "versioned", "timestamped", "stable"),
        default="timestamped",
    )
    parser.add_argument("--trigger", action="append", default=[])
    parser.add_argument("--non-trigger", action="append", default=[])
    parser.add_argument("--target-client", action="append", default=[])
    parser.add_argument("--evidence-tier", type=int, choices=(0, 1, 2, 3), default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = scaffold(args)
    except Exception as exc:  # noqa: BLE001 - bounded machine-readable failure
        print(
            json.dumps(
                {"error": {"code": "skill_scaffold_failed", "message": str(exc)}},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
