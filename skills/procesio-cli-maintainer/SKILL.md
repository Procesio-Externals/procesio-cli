---
name: procesio-cli-maintainer
description: >-
  Change or review the procesio-cli repository source code. Use to add a new CLI
  action, edit a CLI manifest or implementation, change a registry or MCP server,
  modify an agent runtime, generated capability router, CLAUDE.md synchronization,
  CI gate, tests, credential handling, JSON contract, or reversibility policy; use
  for repository implementation, diffs, broken integration references, and
  manifest-to-skill synchronization. Do not use for PROCESIO workspace operations
  or when the primary deliverable is an Agent Skill package, SKILL.md authoring,
  skill routing boundaries, or skill behavioral evaluation.
version: 1.1.1
owner: procesio-cli maintainers
last_verified: 2026-09-05
baseline_version: aa9f94d385e211aab6e1491bcbcc9bdef701e5a2
eval_suite: evals/evals.json
source_policy: generated
routing:
  triggers:
    - change or review the procesio-cli repository source, manifests, tools, agents, MCP, registry, CI, or tests
    - add an action or capability while preserving JSON, credentials, routing, generation, and reversibility contracts
    - integrate an already-designed Agent Skill into repository generation, translations, governance, or release controls
  primary_action: maintain
  example: get-skill.py procesio-cli-maintainer --content
---

# Maintain procesio-cli

Treat tools, agents, skills, generated documentation, and tests as one versioned contract. Make the smallest independently verifiable change that preserves existing clients.

## Boundary

- Using the repository to operate a workspace belongs to `procesio-cli`.
- Product advice belongs to `procesio-platform-advisor`.
- Optimizing a user's SQL belongs to `sql-server-optimizer`.
- Creating, refactoring, auditing, or behaviorally evaluating an Agent Skill as the primary artifact belongs to `agent-skill-engineer`. Return here for repository-specific integration, generation, CI, translations, or release controls.

## Sources of truth

- A tool or agent manifest defines its executable public surface.
- The registry discovers manifests; avoid hardcoded capability inventories.
- Generated router/manual files must be reproducible from structural sources.
- A skill's frontmatter defines discovery; its body defines the decision workflow; references hold detail; scripts enforce deterministic work.
- Runtime behavior and stable JSON output are stronger evidence than prose.

Read `references/change-contract.md` before changing a capability, `references/mcp-compatibility.md` before changing MCP, and `references/skill-authoring.md` when integrating an already-designed skill into this repository. Load `agent-skill-engineer` for the skill-specific design and evaluation method.

## Change workflow

1. **Reproduce or record the baseline.** Add a failing test or evaluation before changing behavior. For code, exercise the real contract boundary. For a skill integration, preserve the immutable skill baseline and evidence supplied by `agent-skill-engineer`.
2. **Trace ownership.** Identify manifest, dispatcher, implementation, generated outputs, callers, safety classification, tests, translations, and documentation affected by the change.
3. **Design the public shape first.** Set action name, typed arguments, output/error shape, mutability, idempotency, and verification path before implementation.
4. **Implement one verifiable unit.** Avoid unrelated cleanup and broad renames.
5. **Regenerate structural outputs.** Never hand-edit generated action manuals or router blocks as the sole source of change.
6. **Run focused tests, then the full suite.** Include platform-neutral tests; credentials and live infrastructure must not be required for unit tests.
7. **Verify the actual surface.** Invoke the command or MCP operation through the same path a client uses and inspect its JSON, stderr, exit code, and side effects.
8. **Review security and compatibility.** Check secret handling, path confinement, irreversible-action classification, retry behavior, and old client calls.
9. **Commit only a green unit.** State evidence and any live check that remains unavailable.

## Repository gates

Run these offline gates from the configured source checkout with its dependencies already installed; installed skill directories are not repository roots. Coding agents read package references natively relative to the skill root. CLI/MCP resource retrieval and bounded query extensions are optional installed capabilities, not prerequisites for loading skills.

The portfolio migration requires maintainer merge approval; publication is not approval or proof of behavioral improvement. It includes offline structural/catalog/routing/governance checks, not behavioral runners, live field examples or historical receipt documents. Historical catalog fixtures are not a current-package pass: the new extraction gate remains blocked pending fresh qualification evidence.

```bash
python -m pytest tools agents dashboard webplatform skills -q
python scripts/validate-skills.py --strict-warnings
python scripts/evaluate-skills.py --catalog skills/evals/baseline-catalog.json --verify-baseline skills/evals/baseline.json
python scripts/evaluate-skill-routing.py --min-accuracy 0.95 --max-collision-rate 0
python scripts/check-skill-governance.py
python scripts/secret_scan.py
python scripts/build-router.py --check
```

Run generators appropriate to the changed manifest before `--check`.

## Completion verification

- No new action without manifest arguments, stable output/error behavior, tests, discoverability, and reversibility classification.
- No skill integration without the fixed-rubric and baseline evidence required by `agent-skill-engineer`.
- No reference-heavy skill unless the client can read its path-confined relative files safely; native file reads suffice. CLI/MCP resource retrieval is optional and must be verified against the installed schema.
- No mutation workflow that ends without direct state verification.
- No “CI is green” claim unless the actual workflow run or full local command set was observed.
