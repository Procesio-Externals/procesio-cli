# Deterministic optimizer controller contract

Use this reference when initializing, staging, accepting, rejecting, inspecting, or finalizing a skill-optimization experiment with the skill's `optimize_skill.py` helper.

## Contents

1. Purpose and non-goals
2. Objective file
3. Validation reports
4. Final test report
5. Lifecycle
6. Exit and state semantics
7. Security and reproducibility

## 1. Purpose and non-goals

The controller protects experiment integrity. It does not generate edits, call a model, judge responses, or prove that a rubric is valid.

It provides:

- immutable baseline and best-skill snapshots;
- path-confined package copies and SHA-256 tree fingerprints;
- allowlisted edit surfaces;
- line, file, and binary edit budgets;
- validation-report identity checks;
- numeric hard-constraint and non-regression gates;
- strict better-than-current-best promotion;
- rejected-candidate history and plateau stopping;
- final-test split and corpus-difference checks (not one-shot custody);
- atomic machine-readable state.

## 2. Objective file

The objective is immutable after `init`. Use this exact shape:

```json
{
  "schema_version": 1,
  "primary_metric": "task_success_rate",
  "direction": "maximize",
  "min_delta": 0.05,
  "minimum_valid_pairs": 40,
  "plateau_limit": 3,
  "edit_budget": {
    "max_changed_files": 4,
    "max_added_lines": 80,
    "max_deleted_lines": 80,
    "max_total_line_changes": 120,
    "max_binary_bytes": 0
  },
  "allowed_paths": [
    "SKILL.md",
    "references/*.md",
    "scripts/*.py",
    "assets/*"
  ],
  "forbidden_paths": [],
  "hard_constraints": [
    {"metric": "collision_rate", "op": "<=", "value": 0},
    {"metric": "safety_violations", "op": "==", "value": 0},
    {"metric": "regression_rate", "op": "<=", "value": 0.02}
  ],
  "secondary_metrics": [
    {
      "metric": "median_tokens",
      "direction": "minimize",
      "max_relative_regression": 0.15,
      "max_absolute_regression": 0
    },
    {
      "metric": "median_duration_ms",
      "direction": "minimize",
      "max_relative_regression": 0.20,
      "max_absolute_regression": 0
    }
  ]
}
```

Rules:

- `direction` is `maximize` or `minimize`.
- A candidate must improve the current best by at least `min_delta` in that direction.
- `minimum_valid_pairs` applies to baseline, paired validation, and final test reports.
- Each hard constraint names a numeric metric, comparison operator, and finite threshold.
- Each secondary metric permits only the registered relative and absolute regression.
- `evals/**` and `.git/**` are always protected even if omitted from `forbidden_paths`.
- All values must be finite strict JSON; NaN and infinity are rejected.
- Include `regression_rate` as a hard constraint when preserving baseline successes is mandatory.

## 3. Validation reports

### Baseline

Initialize from one frozen validation report:

```json
{
  "schema_version": 1,
  "report_type": "baseline",
  "split": "validation",
  "skill_fingerprint": "sha256-of-baseline-package",
  "corpus_fingerprint": "sha256-of-validation-cases",
  "rubric_fingerprint": "sha256-of-fixed-rubrics",
  "model_fingerprint": "provider:model:settings",
  "harness_fingerprint": "sha256-of-runner-and-tool-contract",
  "pairing_fingerprint": "sha256-of-case-order-and-seeds",
  "valid_pairs": 40,
  "infrastructure_failures": 0,
  "metrics": {
    "task_success_rate": 0.60,
    "collision_rate": 0,
    "safety_violations": 0,
    "regression_rate": 0,
    "median_tokens": 2600,
    "median_duration_ms": 4800
  }
}
```

The baseline package fingerprint, evaluation identity, and metrics become immutable experiment state.

### Candidate paired validation

```json
{
  "schema_version": 1,
  "report_type": "paired",
  "split": "validation",
  "candidate_fingerprint": "sha256-of-staged-candidate",
  "parent_fingerprint": "sha256-of-current-best",
  "corpus_fingerprint": "same-as-frozen-validation",
  "rubric_fingerprint": "same-as-frozen-validation",
  "model_fingerprint": "same-as-frozen-validation",
  "harness_fingerprint": "same-as-frozen-validation",
  "pairing_fingerprint": "same-as-frozen-validation",
  "valid_pairs": 40,
  "infrastructure_failures": 0,
  "candidate_metrics": {
    "task_success_rate": 0.775,
    "collision_rate": 0,
    "safety_violations": 0,
    "regression_rate": 0.025,
    "median_tokens": 2700,
    "median_duration_ms": 5000
  },
  "parent_metrics": {
    "task_success_rate": 0.60,
    "collision_rate": 0,
    "safety_violations": 0,
    "regression_rate": 0,
    "median_tokens": 2600,
    "median_duration_ms": 4800
  },
  "paired_outcomes": {
    "repairs": 8,
    "regressions": 1,
    "preserved_successes": 23,
    "unresolved_failures": 8
  }
}
```

The four paired outcomes must sum exactly to `valid_pairs`. Produce task success, repair, and regression metrics from the same host-owned paired observations; do not let the candidate self-report them.

The controller rejects wrong split, stale package fingerprints, changed corpus/rubric/model/harness/pairing identity, non-finite or missing metrics, insufficient pairs, infrastructure failures, hard-constraint failure, insufficient primary gain, and secondary-cost regression.

## 4. Final test report

After validation selects a candidate, run one untouched paired test against the **original baseline**, not against a validation-tuned intermediate. Use the same paired report shape with:

- `split: "test"`;
- `candidate_fingerprint` equal to the selected best;
- `parent_fingerprint` equal to the original baseline;
- a test `corpus_fingerprint` different from validation;
- test-specific pairing identity;
- candidate and baseline metrics computed on the same test cases.

`finalize` writes the selected package only when the submitted final test report passes the same hard constraints, minimum effect, and cost tolerances. It refuses an existing output path and an output path inside the optimizer workspace. This does not prove the cases were untouched or run only once.

### External one-shot custody is required

Before optimization, an independent host/evidence owner must freeze the test corpus, rubric, model, harness and pairing identity, keep test cases inaccessible to the optimizer, and register a single final-run authorization after candidate selection. Archive the first submitted report and outcome immutably outside the helper workspace and block resubmission after either pass or failure. Preserve failures; any renewed experiment needs a separately versioned contract and fresh untouched test evidence, never a rewritten first result.

**Retained qualification blocker:** the helper does not freeze final-test identity at initialization or reject another `finalize` after `test_failed`/`finalized`. It permits resubmission and overwrites its generated final-test report (reports/final-test.json in the optimizer workspace, while appending ledger events), even before checking the output path. Refusing an existing output directory is not one-shot protection. The runtime is retained, not repaired; without external custody, do not claim one-shot enforcement or uncontaminated final-test qualification.

## 5. Lifecycle

### Initialize

```bash
python skills/agent-skill-engineer/scripts/optimize_skill.py init \
  --skill-root skills/example \
  --workspace .skill-optimization/example \
  --objective objective.json \
  --baseline-report baseline-validation.json
```

Creates immutable `snapshots/baseline`, `snapshots/best`, objective, state, reports, candidate area, and append-only event ledger. The workspace must not already exist or overlap the source skill.

### Stage

```bash
python skills/agent-skill-engineer/scripts/optimize_skill.py stage \
  --workspace .skill-optimization/example \
  --candidate-root work/candidate \
  --hypothesis "Replace blind retry with unknown-outcome reconciliation"
```

Compares against current best, enforces protected and allowed paths and edit budgets, snapshots the candidate, and assigns `c0001`, `c0002`, and so on. The staged package is fingerprinted and must remain unchanged.

### Decide

```bash
python skills/agent-skill-engineer/scripts/optimize_skill.py decide \
  --workspace .skill-optimization/example \
  --candidate-id c0001 \
  --report c0001-validation.json
```

Accepts only an eligible strict improvement. Otherwise records the rejected hypothesis, diff, checks, and reasons. An accepted candidate atomically becomes the new immutable best snapshot.

### Status

```bash
python skills/agent-skill-engineer/scripts/optimize_skill.py status \
  --workspace .skill-optimization/example
```

Returns package and objective fingerprints, current best, accepted/rejected counts, plateau count, and complete registered objective.

### Finalize

```bash
python skills/agent-skill-engineer/scripts/optimize_skill.py finalize \
  --workspace .skill-optimization/example \
  --report final-test.json \
  --output dist/example-skill
```

Checks a submitted paired test report and writes the selected package to a new output path if eligible. External custody must establish that the evidence is untouched and one-shot.

## 6. Exit and state semantics

CLI exits:

- `0`: command completed and returned a valid result; inspect `event` and `accepted`/`passed` for experimental outcomes.
- `2`: bounded contract failure, invalid path/report/candidate, drift, or state conflict.
- `1`: unexpected internal failure.

State values:

- `optimizing`: candidates may be staged and decided.
- `plateau`: the registered consecutive-rejection limit was reached; staging is refused.
- `test_failed`: the selected best did not pass the submitted final test; not a terminal resubmission lock.
- `finalized`: the submitted final test passed and the output package was emitted; not a terminal resubmission lock.

A rejected candidate is a normal experimental result and remains in the ledger. Do not interpret a process exit alone as proof that a candidate was accepted.

## 7. Security and reproducibility

- The controller performs no network or model calls.
- It rejects symlinks, path traversal, nested workspace ownership, environment/cache directories, and non-finite JSON.
- It snapshots package files rather than trusting mutable source paths.
- It verifies objective, baseline, best, parent, and candidate fingerprints before decisions.
- It protects formal evaluation data from candidate edits.
- It writes JSON state atomically and logs each staged, accepted, rejected, and final-test event.
- It cannot prove that an evaluator is unbiased, metrics came from genuine runs, a task distribution is representative, or final tests were untouched and run once. Those remain external custody, host evaluator, evidence provenance, and review responsibilities.
