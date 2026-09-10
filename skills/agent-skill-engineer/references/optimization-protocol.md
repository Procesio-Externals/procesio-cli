# Skill optimization protocol

Use this reference when a skill already exists or when the initial design is strong enough to enter formal iterative optimization.

## Contents

1. Optimization contract
2. Data and split discipline
3. Outcome vector
4. Trajectory collection
5. Contrastive diagnosis
6. Candidate generation
7. Bounded textual learning rate
8. Validation promotion
9. Rejected-edit memory and plateau handling
10. Statistical interpretation
11. No-ground-truth evaluation
12. Transfer and field proof
13. Reproducible controller

## 1. Optimization contract

Treat the skill package as external trainable state for a frozen target agent. Keep the target model, tool surface, system instructions, generation settings, and evaluator fixed during one experiment unless the experiment explicitly studies transfer.

Freeze before optimization:

- immutable baseline package and fingerprint;
- target task distribution and exclusions;
- train, validation, test, and field ownership;
- primary metric and direction;
- hard correctness, safety, permission, privacy, and collision constraints;
- secondary token, latency, tool-call, and maintenance costs;
- minimum meaningful effect;
- edit budget and allowed paths;
- maximum rounds, plateau limit, and infrastructure retry policy;
- fixed behavioral rubrics and evaluator version.

Changing one of these creates a new experiment. Do not reinterpret an old run under a new contract.

## 2. Data and split discipline

Use four logically distinct evidence sets:

| Set | Purpose | Permitted use |
|---|---|---|
| Train | discover failure modes and generate edit hypotheses | may be inspected repeatedly |
| Validation | decide whether a candidate replaces the current best | scores may be used for promotion; case content should not drive hand-written patching |
| Test | estimate final generalization after candidate selection | inspect once per final candidate; never optimize on it |
| Field | verify real tools, artifacts, side effects, and user outcomes | controlled execution with approval and cleanup |

Split by causal family rather than random text alone. Paraphrases, near-duplicate incidents, shared source documents, and variants of the same underlying task belong in one split. Keep a split manifest and fingerprint.

Do not place rubrics, expected answers, evaluator rationales, or validation/test outcomes in the skill package. Do not regenerate the split until a new experiment version is declared.

## 3. Outcome vector

Use lexicographic evaluation rather than a single weighted score:

1. **Eligibility:** structural validity, security, required permissions, hard correctness, no forbidden routing collisions, and mandatory field invariants.
2. **Primary effect:** task success, direct user preference, or another registered outcome.
3. **Non-regression:** preserve baseline successes and critical subgroups.
4. **Efficiency:** token use, latency, tool calls, retries, and context loaded.
5. **Maintainability:** package size, duplicate rules, source freshness, and extension cost.

A candidate failing eligibility is rejected even if its average task score is high. Weights may summarize trade-offs among already eligible candidates; they must not compensate for a safety or correctness violation.

For each paired item, classify the transition:

| Baseline | Candidate | Classification |
|---|---|---|
| fail | pass | repair |
| pass | fail | regression |
| pass | pass | preserved success |
| fail | fail | unresolved failure |

Publish repair and regression counts, not only the net average.

## 4. Trajectory collection

For every run preserve a sanitized record of:

- case and split identifiers;
- package, rubric, evaluator, model, harness, and settings fingerprints;
- selected skill and resources loaded;
- response, tool calls, errors, retries, and direct observations;
- criterion booleans and evidence spans;
- token, latency, and cost measures when available;
- infrastructure failures kept separate from task failures.

Use fresh contexts. Interleave baseline and candidate runs through opaque labels so provider drift and load do not align with one variant. Checkpoint each completed observation.

Collect successful trajectories as actively as failures. An optimizer that sees only failure examples tends to add rules that repair narrow cases while damaging concise successful behavior.

## 5. Contrastive diagnosis

Before editing, compare at least these groups:

- baseline success versus baseline failure;
- repaired failure versus unresolved failure;
- preserved success versus candidate regression;
- low-cost success versus high-cost success;
- near-success versus hard failure.

Extract the smallest repeated difference that could causally alter a decision. State one intervention hypothesis:

```text
When <observable cue>, the agent currently <failure behavior> because <supported mechanism>.
Changing <specific instruction/resource/control> should produce <observable state> without breaking <named baseline successes>.
```

Reject diagnoses that merely restate the score, rely on one anecdote, or propose adding generic caution everywhere. Attribute tool, environment, observation, or evaluator defects to their own layer.

## 6. Candidate generation

For the first design or a major boundary failure, compare structurally different candidates. After a coherent base exists, generate local alternatives around one causal hypothesis.

Candidate operations are:

- **add:** introduce a missing discriminator, invariant, handoff, or proof requirement;
- **delete:** remove misleading, redundant, over-broad, or costly content;
- **replace:** substitute a more precise decision rule, example, resource route, or executable control;
- **move:** shift conditional detail from the always-loaded body into a direct reference or script;
- **split/merge:** redesign portfolio ownership only when routing evidence requires it.

Prefer deletion, replacement, and structural enforcement over accumulation. Generate at least one minimal candidate. More candidates are useful only when the validation process accounts for the larger search.

## 7. Bounded textual learning rate

Every candidate proposal must declare:

- parent fingerprint;
- hypothesis and affected cases;
- files permitted to change;
- added, deleted, and total changed-line limits;
- forbidden paths, especially formal evaluation data;
- expected repair and protected successes;
- rollback condition.

Use a small budget after each round. If the required edit exceeds the budget, stop and classify the need as a redesign rather than silently expanding the patch.

Never let the optimizer modify validation/test cases, rubrics, thresholds, evaluator code, or the result parser in the same experiment. Harness optimization is a separate experiment with its own immutable counterfactual.

## 8. Validation promotion

A candidate may replace the current best only when:

1. package and security checks pass;
2. report fingerprints match the candidate, parent, split, rubric, and evaluator;
3. every hard constraint passes;
4. primary validation performance strictly exceeds the registered threshold relative to the current best;
5. protected subgroups and baseline-success retention meet their floors;
6. secondary costs remain within registered tolerances;
7. the run contains enough valid paired observations.

Compare against the **current best**, not merely the original baseline. Copy the accepted package into a new immutable best snapshot. Never edit the best snapshot in place.

A tie is not an improvement unless a pre-registered secondary objective resolves it. Do not lower the threshold after seeing a result.

## 9. Rejected-edit memory and plateau handling

Record every rejected candidate with:

- parent and candidate fingerprints;
- hypothesis and exact patch summary;
- validation metrics and hard-constraint failures;
- repaired and regressed case families;
- rejection reason;
- evidence that would justify revisiting the idea.

Before generating a proposal, search this ledger for equivalent failed interventions. Reusing a rejected idea requires new evidence, not new wording.

Stop when any condition holds:

- plateau limit reached;
- edit or model-call budget exhausted;
- A/A evaluator noise exceeds the detectable effect;
- validation gains come only from one overrepresented family;
- complexity grows faster than task success;
- remaining failures belong to the tool, data, environment, observation, or evaluator;
- the final candidate cannot meet a hard constraint.

A later meta-update may consolidate repeatedly accepted lessons into a shorter decision model. Validate the consolidation exactly like any other candidate.

## 10. Statistical interpretation

Use paired analysis because baseline and candidate see the same cases. Report sample size, missing pairs, repairs, regressions, and the paired effect. For binary task success, include a confidence interval for the paired difference and use a matched-pair test such as McNemar's test when inferential claims matter.

Do not use significance as the only promotion rule. A tiny but statistically detectable gain may be operationally irrelevant; a large uncertain gain may need more repetitions. Pre-register both a minimum effect and an uncertainty rule appropriate to consequence.

When searching many candidates, validation becomes progressively selected. Preserve an untouched final test and disclose candidate count and stopping behavior. Analyze critical subgroups separately rather than trusting a global mean to expose a rare safety regression.

## 11. No-ground-truth evaluation

When exact answers are unavailable:

1. define observable behavioral attributes independently of candidate outputs;
2. compare baseline and candidate responses under opaque labels;
3. use multiple independent judgments or a calibrated evaluator where consequence justifies it;
4. extract criterion-level evidence rather than one holistic score;
5. gate promotion on held-out validation;
6. send discordant, ambiguous, and high-consequence pairs to accountable human review.

Self-preference by the same model that produced the answer is weak evidence. Pairwise preference is useful only when the preference question, evidence packet, and conflict handling are frozen.

## 12. Transfer and field proof

After final selection, test the untouched set and at least one adjacent model, client, or harness when portability is claimed. A skill that wins only on one optimizer-model combination may have learned harness-specific cues.

Operational skills also require a controlled field task. Record before-state, exact target, approval, execution ID, direct outcome, cleanup, and restored state. Synthetic grades cannot substitute for the actual artifact or external system.

## 13. Reproducible controller

Use the skill's `optimize_skill.py` helper to enforce local experiment state:

```bash
python skills/agent-skill-engineer/scripts/optimize_skill.py init \
  --skill-root skills/example \
  --workspace .skill-optimization/example \
  --objective objective.json \
  --baseline-report baseline-validation.json

python skills/agent-skill-engineer/scripts/optimize_skill.py stage \
  --workspace .skill-optimization/example \
  --candidate-root work/candidate \
  --hypothesis "Replace the ambiguous retry rule with unknown-outcome reconciliation"

python skills/agent-skill-engineer/scripts/optimize_skill.py decide \
  --workspace .skill-optimization/example \
  --candidate-id c0001 \
  --report c0001-validation.json
```

The controller does not invent edits or score model responses. It checks snapshots, path allowlists, bounded diffs, report fingerprints and held-out promotion, and records rejected candidates. Final test separation needs the external one-shot custody in `references/optimizer-contract.md`: the helper permits final-report resubmission and overwrites, so it does not enforce an untouched single final test.
