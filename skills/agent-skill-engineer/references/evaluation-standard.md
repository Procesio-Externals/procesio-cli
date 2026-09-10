# Agent Skill evaluation standard

Use this reference before writing evaluation cases, jury prompts, baselines, or performance claims.

## Contents

1. What to measure
2. Build the corpus
3. Choose the baseline
4. Freeze a fixed rubric
5. Run paired evaluations
6. Establish evaluator noise
7. Field proof
8. Diagnose failures
9. Report honestly

## 1. What to measure

Separate these outcomes:

- **Selection:** did the router select the intended skill or abstain?
- **Collision:** did it select a specifically forbidden neighboring skill?
- **Task behavior:** did the response satisfy the fixed behavioral criteria?
- **Safety:** did it avoid prohibited actions, false claims, or unsafe retries?
- **Verification:** did it demand or produce direct evidence of the real outcome?
- **Efficiency:** tokens, latency, tool calls, retries, and unnecessary context.
- **Field success:** did the actual external artifact or system reach the expected state?

Do not let a jury infer objective selection accuracy. Compute it from `selected_skill` and `expected_skill` in host code.

## 2. Build the corpus

Use realistic prompts, not instructions written to reveal the expected answer. Include:

- positive/core cases;
- negative and abstention cases;
- nearest-neighbor overlap cases;
- missing-context cases;
- pressure or adversarial shortcut cases;
- common paraphrases and terse user language;
- at least one real field task when the skill is operational.

Keep a holdout set for later changes when the corpus is large enough. Add production failures only after removing sensitive data and preserving the causal shape.

## 3. Choose the baseline

- **New skill:** compare with no skill loaded.
- **Existing skill:** compare with an immutable old-skill snapshot.
- **Description-only change:** keep the body byte-identical and compare discovery behavior.
- **Portfolio redesign:** snapshot the entire old portfolio, not one isolated skill.
- **Evaluator change:** run A/A with byte-identical corpora before interpreting A/B.

Record corpus fingerprints, model, provider, settings, seed, prompt files, and evaluator version. Do not silently update a baseline during a run.

## 4. Freeze a fixed rubric

Write atomic binary criteria before viewing candidate results. Every criterion needs:

```json
{
  "id": "descriptive_snake_case_id",
  "description": "Pass only when the response ...",
  "required": true
}
```

Use two to eight criteria per case. Each criterion should test one observable requirement and be usable without imagining what a better answer might have said.

The complete rubric object is:

```json
{
  "rubric_version": 1,
  "criteria": [
    {
      "id": "checks_precondition_before_mutation",
      "description": "Pass only when the response requires the named precondition before any write.",
      "required": true
    },
    {
      "id": "verifies_the_real_outcome",
      "description": "Pass only when the response requires direct inspection of the resulting state or output.",
      "required": true
    }
  ]
}
```

### Jury contract

Every juror for the case receives the same canonical rubric bytes or equivalent canonical serialization. The juror must:

- return every supplied criterion ID exactly once and in the supplied order;
- return no additional, renamed, merged, or split IDs;
- use JSON booleans only;
- mark absent or ambiguous evidence false;
- provide brief evidence for review;
- never choose the aggregate verdict.

Host code validates the returned IDs and computes:

```text
task_success = valid_contract AND all(required criterion booleans)
```

Store the rubric fingerprint with every observation. A prose expectation that asks each juror to derive its own checks is not a fixed rubric.

## 5. Run paired evaluations

For every case and repetition:

1. use fresh response contexts;
2. use the same task and input files for both variants;
3. hold model, provider, settings, tools, and timeouts constant;
4. mount each corpus at a neutral path;
5. randomize opaque labels;
6. keep the rubric hidden from the response-producing candidate;
7. judge each response independently against the frozen rubric;
8. checkpoint every completed observation;
9. preserve raw sanitized outputs and machine-readable grades.

Do not launch all candidate runs before all baseline runs. Interleave or randomize them so time, load, and provider drift do not align with one variant.

## 6. Establish evaluator noise

Before A/B, run A/A against two byte-identical copies. Pre-register:

- minimum repetitions;
- maximum acceptable selection, task-success, and collision deltas;
- minimum A/B effect worth detecting;
- number of consecutive passing rounds;
- stop and retry policy for quota or infrastructure failures.

If A/A fails, do not loosen the threshold or proceed to A/B. Pair disagreements by case and repetition. Determine whether variation came from response generation, rubric ambiguity, juror interpretation, host aggregation, or execution environment. Version the correction and start a new A/A run from zero.

A fixed rubric reduces decomposition drift; it does not eliminate borderline interpretation or response variance. Keep direct human review of discordant pairs.

## 7. Field proof

Synthetic response grading cannot prove that a skill successfully controls a real tool or platform. For operational skills, add a controlled field trial:

1. isolate a disposable or otherwise explicitly bounded target;
2. confirm authentication and scope;
3. record the before-state;
4. preview and validate the intended mutation;
5. obtain explicit approval;
6. execute exactly once per registered acceptance claim;
7. capture stable resource and execution IDs;
8. inspect the actual output and side effects;
9. perform approved safety containment even if output verification fails; preserve evidence before authorized destructive cleanup;
10. prove the baseline state was restored where cleanup is expected.

Before the first mutation, apply `field-gate-standard.md`: freeze ordered acceptance check IDs, their direct proof boundary, permitted gaps and equivalent fallbacks, resource and write caps, the full parent/child execution budget, cleanup, unknown-outcome handling, and host-side promotion rules.

The execution agent may supply evidence for each check, but deterministic host code should validate exact IDs and order, Boolean values, budgets, unknown outcomes, cleanup, and gap eligibility. The acting agent's own `passed` or `passed_with_gap` label is not the aggregate verdict.

A platform limitation discovered after execution does not retroactively permit a gap. Preserve the original blocked/failed report, classify the causal layer, and use a separately approved versioned remediation contract to rerun only missing claims. Archive the original evidence and disclose the remediation's additional mutations and full causal execution count.

A status code, “finished” flag, screenshot, or agent self-report is not enough when the user’s actual output can be read directly.

## 8. Diagnose failures

Classify before editing:

- **routing defect:** wrong owner or abstention;
- **instruction defect:** selected skill omits or misorders a required decision;
- **resource defect:** stale or missing reference/script/asset;
- **tool defect:** executable contract, API, auth, or environment failure;
- **observation defect:** test checks a proxy or wrong state;
- **rubric defect:** criterion is ambiguous, bundled, or impossible in the test context;
- **juror defect:** exact rubric is inconsistently applied;
- **host defect:** IDs, booleans, pairing, aggregation, field checks, budgets, or promotion are accepted incorrectly;
- **field-contract defect:** required outcomes, allowed gaps, nested side effects, or cleanup were not frozen before mutation.

Change only the causal layer. Do not add skill prose to solve a tool, jury, controller, or one-off project problem.

## 9. Report honestly

Publish:

- exact corpus and rubric versions;
- baseline identity and fingerprints;
- model and settings;
- repetitions, dropouts, timeouts, and quota interruptions;
- per-case selection, collisions, criterion booleans, and field results;
- aggregate rates with variance or confidence intervals where meaningful;
- field acceptance check IDs, permitted gaps, complete causal execution counts, cleanup, and remediation lineage;
- regressions and unresolved discordant pairs;
- limitations of synthetic, judge-based, and field evidence.

Use “candidate,” “draft,” or “provisional” until the registered proof is complete. Never convert a partial run, failed A/A, or failed required field outcome into evidence of superiority or completion.
