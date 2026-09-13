# Skill repository integration contract

Use `agent-skill-engineer` for the primary design, refactoring, routing, evaluation, and field-proof method. This reference owns only the procesio-cli repository integration that follows an already-designed skill change.

## Required handoff evidence

Before integration, obtain:

- skill name, version, owner, compatibility, source policy, and last-verified date;
- trigger and nearest non-trigger boundary;
- immutable old-skill or no-skill baseline;
- positive, negative, overlap, and pressure cases;
- fixed ordered jury criteria with required flags;
- deterministic audit result;
- behavioral and field evidence available, with missing proof labeled;
- files to add, update, retire, or deliberately leave unchanged.

Do not invent missing evidence in the integration step. Return to `agent-skill-engineer` when the skill contract itself is still undecided.

## Repository integration checklist

1. Put the package at `skills/<frontmatter-name>/`; make the folder and name identical.
2. Keep `SKILL.md` under 500 body lines and resources one level below `references/`, `scripts/`, or `assets/`.
3. Resolve every local link and reject traversal or symlink escape.
4. Declare `owner`, `last_verified`, `baseline_version`, `eval_suite`, `source_policy`, and curated `routing.triggers`.
5. Keep every published per-skill evaluation suite on the repository's fixed-rubric contract.
6. Add portfolio-wide routing cases for the new positive region, nearest competing owner, abstention, and pressure boundary.
7. Update the global behavioral corpus only when the new skill or changed behavior must be measured there; increment its suite version and invalidate prior formal runs.
8. Add or update Romanian framework-map skill descriptions so the live inventory remains fully translated.
9. Update the README skill table and inventory tree.
10. Regenerate the capability router from the registry; do not treat a hand-edited router as the source of truth.
11. Update the Gate 5 ledger honestly. A new corpus or jury contract requires fresh A/A and A/B evidence. A reference or helper change also changes the loaded package: compare the evaluated package fingerprint, not just its version or `SKILL.md`. Preserve the historical pass and keep current release eligibility blocked until the changed package is revalidated.
12. Run the new skill's deterministic audit, focused tests, all repository tests, strict skill validation, routing evaluation, governance, secret scan, and generated-file check.

## Commands

Run from the configured source checkout in its already-installed Python environment. Read referenced files natively relative to the skill root; no CLI resource flag or MCP resource extension is required. The included gates are offline structure, catalog-baseline integrity, routing and governance checks, not behavioral A/A or A/B runners or live field proof. Historical catalog fixtures do not qualify extracted package bytes; preserve the old evidence and keep the new extraction gate blocked. Live field examples and historical receipt documents are not shipped here; the meta-skill's causal field guidance remains methodology, not an included runner.

```bash
python skills/agent-skill-engineer/scripts/audit_skill.py skills/<name> --strict
python -m pytest skills -q
python scripts/validate-skills.py --strict-warnings
python scripts/evaluate-skills.py --catalog skills/evals/baseline-catalog.json --verify-baseline skills/evals/baseline.json
python scripts/evaluate-skill-routing.py --min-accuracy 0.95 --max-collision-rate 0
python scripts/check-skill-governance.py
python scripts/secret_scan.py
python scripts/build-router.py
python scripts/build-router.py --check
```

Run the full cross-platform CI matrix after focused checks pass. Do not claim behavioral superiority from static routing or a single candidate-only smoke test.
