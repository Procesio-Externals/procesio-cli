---
name: agent-skill-engineer
description: >-
  Engineer reusable Agent Skill packages and SKILL.md routing and evaluation systems.
  Use when the primary deliverable is an Agent Skill: turn a repeated agent workflow
  into a skill, author or revise a SKILL.md or a domain skill such as the SQL optimizer
  skill, change a skill description or trigger boundary, split skill content into
  progressive references, scripts, or assets, build fixed-rubric baselines and A/A or
  A/B skill evaluations, or audit a skill package. Do not use for ordinary repository
  implementation, workspace operations, unrelated CLI design, image creation, or
  one-off content.
version: 2.0.4
compatibility: Agent Skills compatible clients; Python 3.11+ for bundled helpers.
owner: procesio-cli maintainers
last_verified: 2026-09-09
baseline_version: a47135373c4c0598391e808939397cd139234afd
eval_suite: evals/evals.json
source_policy: timestamped
routing:
  triggers:
    - create, update, split, merge, refactor, or audit an Agent Skill or SKILL.md package
    - optimize skill descriptions, routing boundaries, progressive disclosure, context cost, or safety
    - design fixed-rubric skill evaluations, baselines, A/A noise checks, A/B comparisons, or field trials
  primary_action: engineer
  example: get-skill.py agent-skill-engineer --content
---

# Engineer Agent Skills

Create the smallest skill package that reliably changes agent behavior and proves the change. Treat a skill as an auditable intervention on a frozen agent, not as a persuasive document, topic encyclopedia, or prestige persona.

## Boundary

- Use this skill when the primary artifact is an Agent Skill, its routing contract, its resources, or its evaluation and optimization system.
- Use `procesio-cli-maintainer` when the primary work is repository code, manifests, MCP, CI, or generated integration; return here for the skill-specific design and evidence.
- Use the domain skill when the user wants the domain task performed rather than encoded for reuse.
- Do not create a skill for a one-off answer, volatile facts, or behavior that a type, API, lint, test, script, permission boundary, or tool can enforce more reliably.

## Non-negotiables

1. **Evidence before prose.** Start from repeated trajectories, observed failures, costly risks, or validated examples. Do not invent a problem to justify a skill.
2. **Skill as intervention.** State the causal behavior the skill should change. Measure both repairs of baseline failures and regressions of baseline successes.
3. **One intent, one owner.** Give every trigger region a clear owner and explicit non-trigger neighbors. Avoid universal skills and duplicate workflows.
4. **Context is a budget.** Put only routing and always-needed decisions in `SKILL.md`; load conditional references on demand and move deterministic repetition into scripts.
5. **Match freedom to fragility.** Use judgment for open-ended work, structured templates for preferred patterns, and executable helpers for narrow error-prone operations.
6. **Freeze evidence contracts before results.** Lock cases, split membership, rubric IDs, pass conditions, objective hierarchy, edit budget, and stopping rules before formal optimization.
7. **Protect the holdout.** Optimize on training evidence, promote on held-out validation, and inspect the final test set only after choosing the candidate. Never edit evals to make a candidate win.
8. **Prefer bounded changes.** After the first grounded design, propose small add/delete/replace edits, preserve the best-known version, and record rejected edits so failures are not rediscovered.
9. **Safety is lexicographic.** Hard correctness, permission, privacy, and non-regression constraints pass before quality, token, latency, or elegance objectives are compared.
10. **Prove the real outcome.** Static validity and fluent output are proxies. Exercise the actual user path when the skill controls an executable or externally observable workflow.
11. **Encode recurring lessons structurally.** A repeated correction belongs in a validator, script, schema, test, runtime guard, or source-owned reference before it becomes another paragraph.
12. **Calibrate expertise.** Use independent expert lenses and evidence, preserve dissent, and require accountable human review where law, medicine, safety, finance, compliance, or organizational authority demands it.
13. **Never claim readiness without evidence.** Label unexecuted work as draft or provisional and name the missing proof.
14. **Field gates are fixed contracts.** Predeclare required check IDs, permitted gaps and fallbacks, cleanup, and the full causal side-effect budget. Host code—not the acting agent—decides pass; preserve a failed report and use separately approved remediation instead of relabeling it.

## Select the mode

- **Create:** qualify a repeatable capability, acquire domain truth, define its boundary, then build and test a new package.
- **Improve:** snapshot the old package, reproduce a concrete failure, and change the smallest causal instruction or resource.
- **Optimize:** train the package through bounded trajectory-driven edits, held-out promotion, rejected-edit memory, and an immutable final test.
- **Description tune:** preserve body behavior; optimize discovery only with positive, negative, overlap, pressure, and portfolio collision cases.
- **Audit:** inspect structure, routing, safety, portability, evaluation validity, and real-proof coverage without rewriting by default.
- **Portfolio design:** split, merge, retire, or compose skills so each user intent has one bounded owner.
- **Domain synthesis:** turn primary sources, expert demonstrations, critical incidents, and operational evidence into a calibrated decision model before authoring instructions.

## Read only what the current mode needs

- Read `references/decision-framework.md` before deciding whether a skill should exist or how a portfolio should be divided.
- Read `references/domain-evidence-protocol.md` before encoding specialized or high-consequence expertise.
- Read `references/authoring-standard.md` before drafting or restructuring a skill package.
- Read `references/optimization-protocol.md` before iterative or automated skill optimization.
- Read `references/optimizer-contract.md` before operating the deterministic optimizer controller or producing its reports.
- Read `references/evaluation-standard.md` before writing cases, rubrics, baselines, juries, or performance claims.
- Read `references/field-gate-standard.md` before designing a staged field trial, acceptance gate, execution budget, degraded mode, or remediation.
- Read `references/review-standard.md` before approval, publication, or a production-ready claim.
- Read `references/expert-lenses.md` for non-trivial or cross-domain review.
- Read `references/portability-standard.md` when the skill must work across clients, operating systems, or repositories.
- Read `references/research-basis.md` when refreshing this methodology or resolving disagreement about its design choices.

Use the bundled helpers when appropriate:

- Run `scripts/scaffold_skill.py` to create a path-confined draft without overwriting an existing package.
- Run `scripts/audit_skill.py` for deterministic structure, resource, secret, metadata, and fixed-rubric checks.
- Run `scripts/optimize_skill.py` for fingerprinted snapshots, bounded edits, paired validation and rejected-edit history; final test separation requires external one-shot custody, not just this helper.

```bash
python skills/agent-skill-engineer/scripts/scaffold_skill.py <name> \
  --root skills --description "<capability and trigger boundary>"

python skills/agent-skill-engineer/scripts/audit_skill.py \
  skills/<name> --strict

python skills/agent-skill-engineer/scripts/optimize_skill.py init \
  --skill-root skills/<name> \
  --workspace .skill-optimization/<name> \
  --objective objective.json \
  --baseline-report baseline-validation.json
```

The scaffold never overwrites an existing path. The audit is deterministic. The optimizer controller makes no model or network calls; it checks snapshot fingerprints, path allowlists, edit budgets and validation promotion. It does **not** enforce one-shot final test custody: `finalize` permits resubmission and overwrites its saved final-test report. An external owner must freeze test identity, hold the untouched cases, authorize one final run after selection, archive the first report immutably and block retries after either pass or failure. Treat autonomous one-shot enforcement as a qualification blocker, not a runtime guarantee; see `references/optimizer-contract.md`.

## Workflow

### 1. Ground the need

Inspect the repository, artifacts, transcripts, tool schemas, current skill behavior, and existing portfolio before asking for information already available. Collect realistic examples in these classes:

- clear positive trigger;
- clear negative or abstention;
- nearest overlap with another skill;
- missing-context case;
- pressure case inviting an unsafe shortcut or false completion;
- representative successful outcome;
- baseline success that the new skill must not break.

Record the no-skill behavior for a new capability or preserve an immutable old-portfolio snapshot for an existing one.

### 2. Acquire and calibrate domain truth

For specialized work, build a claim-and-decision ledger before writing instructions. Separate facts, invariants, heuristics, local policy, preferences, unknowns, and decision rights. Prefer primary sources, real artifacts, successful and failed trajectories, and critical incidents over generic summaries.

Select independent expert lenses by failure consequence, not prestige. Give them the same evidence packet. Require each finding to name evidence, scope, confidence, disconfirming conditions, and the design decision it changes. Preserve unresolved dissent and escalate to an accountable human when simulation is not sufficient.

### 3. Freeze the contract and experiment

Write a compact skill brief containing:

- observable user outcome and non-goals;
- trigger and explicit non-trigger boundary;
- inputs, outputs, dependencies, permissions, and side effects;
- invariants, unknown-outcome semantics, and irreversible failure modes;
- source ownership and freshness policy;
- target clients and compatibility assumptions;
- evidence tier and direct proof;
- training, validation, test, and field-case ownership;
- primary metric, hard constraints, secondary costs, minimum effect, edit budget, and stopping rule.

Turn behavioral requirements into ordered atomic criterion IDs with binary pass conditions. Keep routing selection separate from task quality. Keep formal rubrics hidden from the response-producing candidate.

For operational field work, also freeze ordered acceptance check IDs, permitted degraded modes, cleanup, resource/write/trigger limits, and the full parent/child execution budget. Make the controller validate reports and compute promotion; do not let the acting agent choose its own pass criteria.

### 4. Explore the design space

For non-trivial skills, produce at least two structurally distinct designs from the same brief. Vary package boundary, degree of freedom, control flow, and resource split—not cosmetic wording. Include a minimal design and a plausible alternative.

Review candidates independently through the selected expert lenses and an adversarial pre-mortem. Choose one coherent base using the frozen objective hierarchy. Graft only compatible strengths. Record rejected alternatives and the evidence that ruled them out.

If candidates diverge wildly, the brief or domain model is underspecified. Re-ground instead of averaging incompatible designs.

### 5. Build the minimum package

Create only files that improve execution:

- `SKILL.md`: discovery metadata, boundary, invariants, core decisions, workflow, resource router, and completion contract;
- `references/`: stable detail, variants, schemas, or domain evidence loaded only when needed;
- `scripts/`: deterministic, repeated, safety-critical, or format-fragile operations with bounded interfaces;
- `assets/`: templates or media used in outputs, never hidden instructions;
- `evals/`: realistic cases with fixed rubrics, split ownership, and immutable baseline intent.

Target fewer than 250 body lines and treat 500 as a hard ceiling. Remove generic advice the model already knows, duplicated source material, research diaries, decorative personas, and instructions that cannot affect a decision.

### 6. Prove structure, routing, and security

Run the local audit and the host repository's native validator. Resolve every reference, validate frontmatter and resource confinement, scan for secrets and placeholders, and execute scripts on supported platforms. Treat downloaded skills and scripts as supply-chain code: inspect provenance, permissions, network behavior, and mutation scope.

Run discovery cases against the full portfolio, not the candidate in isolation. Include equivalent paraphrases and irrelevant-detail variants. Zero forbidden collisions is the default bar.

### 7. Optimize behavior without contaminating the test

Collect paired trajectories from the frozen target agent. Contrast baseline successes, baseline failures, candidate repairs, candidate regressions, and near-successes. Convert repeated evidence into one explicit intervention hypothesis.

After the initial design, use a bounded textual learning rate: small add/delete/replace edits with an exact file and line budget. Screen on training cases, then promote only when held-out validation strictly clears the registered improvement and every hard constraint. Preserve the best version and add rejected edits with their hypotheses and failure evidence to the ledger.

Prefer deletion and substitution over accumulation. When several candidates trade quality, cost, and latency, retain only non-dominated candidates after hard constraints; do not hide safety inside a weighted average. Stop on plateau, exhausted budget, evaluator instability, or evidence that the problem belongs to another layer.

When trustworthy ground truth is unavailable, use blinded pairwise comparison plus an independent behavior extractor, validation gating, and human review of discordant pairs. Do not convert self-preference into certainty.

### 8. Prove the final candidate

Run the untouched test set once after candidate selection. Report repairs and regressions, paired effect size, uncertainty, cost, and all hard-constraint outcomes. Then test at least one adjacent model or target client when portability is claimed.

For operational skills, run a controlled end-to-end task through the same surface a real agent uses. Preview mutations, obtain approval, execute once, and observe the actual resulting state or output. Perform approved safety containment even when output verification fails; preserve evidence before authorized destructive cleanup. A screenshot, HTTP success, compile, lint, or self-report is insufficient when stronger direct observation exists.

When a required field outcome fails, keep the original report blocked or failed. Classify the causal layer, archive the evidence, version a narrower remediation contract with fresh approval, rerun only the missing claims, and let deterministic host validation promote the result. Never weaken a completed gate after seeing a platform limitation.

For subjective skills, use blinded human comparison and concrete preference evidence instead of fabricated objective assertions.

### 9. Release and learn

Keep a change only when it fixes a demonstrated integrity defect or improves the frozen objective beyond measured noise without unacceptable regressions. Update version, ownership, freshness, routing corpus, fixed rubrics, generated indexes, translations, governance records, and source register as required by the host repository.

After release, collect sanitized field trajectories and explicit user corrections. Route each signal to its causal layer. Reopen optimization only with a new versioned experiment contract; never silently train on the final test set.

## Failure attribution

Before changing instructions, classify the failure:

| Layer | Typical evidence | Correct response |
|---|---|---|
| Need/ownership | capability is one-off, duplicated, or better enforced elsewhere | retire, merge, or choose a stronger artifact |
| Domain model | source conflict, expert disagreement, wrong invariant, missing edge condition | repair evidence and decision model |
| Routing | wrong skill or no skill selected | tune metadata or portfolio boundary |
| Instruction | right skill, wrong decision or sequence | change the smallest causal instruction |
| Resource | missing, stale, or over-loaded reference, helper, or template | repair source ownership or resource routing |
| Tool/runtime | command, API, auth, or environment failure | fix the executable system, not skill prose |
| Observation | proxy proof disagrees with real state | strengthen direct verification |
| Evaluation | leakage, unstable jury, wrong counterfactual, or ambiguous criterion | repair the experiment and restart affected evidence |
| Field contract | acting agent invents checks, grants an unregistered gap, or ignores nested side effects | fix host-enforced checks and budgets; preserve the result and remediate |
| Optimization | edit overfits training, regresses a baseline success, or only adds length | reject, record, and try a bounded alternative |

## Verification

A publishable result must identify:

- mode, skill boundary, target clients, and evidence tier;
- baseline fingerprint and reproduced failure or leverage case;
- domain evidence, uncertainties, expert-lens findings, and accountable signoffs where required;
- files created, changed, retired, or deliberately omitted;
- structural, routing, security, behavioral, test, transfer, and field evidence appropriate to the tier;
- fixed rubric and experiment versions, edit budget, accepted and rejected hypotheses, and stopping rule;
- field acceptance check IDs, permitted gaps, complete causal execution counts, cleanup, and any remediation lineage;
- repairs, regressions, effect size, uncertainty, context and runtime costs;
- residual risk and proof that remains unavailable;
- exact commands, artifacts, and fingerprints a maintainer can rerun.

A concise draft with honest missing evidence is acceptable. An unverified claim of exceptional quality is not.
