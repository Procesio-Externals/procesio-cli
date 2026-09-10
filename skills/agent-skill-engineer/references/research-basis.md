# Research basis and source register

Verified on 2026-09-04. Use this reference when refreshing the methodology or resolving disagreement about why a control exists.

## Contents

1. Source policy
2. Standards and official authoring systems
3. Optimization research
4. Mechanisms adopted
5. Mechanisms kept separate
6. Refresh triggers

## 1. Source policy

Prefer normative specifications, official skill creators, primary source repositories, and original research papers. A source contributes a mechanism or falsifiable result; it does not become a universal rule merely because it is prominent.

Record the target client and version when applying client-specific advice. Re-check every source before changing compatibility, frontmatter, evaluation, or optimizer assumptions.

## 2. Standards and official authoring systems

### Agent Skills specification

- Source: https://agentskills.io/specification
- Role: portable package contract.
- Adopted: required `SKILL.md`; `name` and `description` constraints; progressive loading of body and optional `scripts/`, `references/`, and `assets/`; relative resource links; shallow references; validation.
- Limitation: the specification defines package shape, not proof that instructions improve behavior.

### OpenAI skill creator

- Source: https://github.com/openai/skills/tree/main/skills/.system/skill-creator
- Role: official Codex-oriented authoring method.
- Adopted: context as a shared budget; match instruction freedom to task fragility; concrete examples; minimal package contents; progressive disclosure; execute and test bundled scripts; validate and iterate.
- Limitation: client-specific interface metadata and runtime conventions are not assumed portable.

### Anthropic skill creator

- Source: https://github.com/anthropics/skills/tree/main/skills/skill-creator
- Role: official Claude-oriented creation and evaluation workflow.
- Adopted: discovery descriptions as a first-class interface; realistic trigger/non-trigger queries; output evaluation; blind comparison; iterative improvement from observed use.
- Limitation: under-trigger guidance, packaging, subagent, and authentication behavior are client-specific and must be tested rather than copied universally.

### Cursor pstack

- Source: https://github.com/cursor/plugins/tree/main/pstack
- Marketplace: https://cursor.com/marketplace/cursor/pstack
- Role: prominent workflow and verification system for coding agents.
- Adopted: bounded playbooks, explicit delegation, independent candidate comparison, design-space exploration, blast-radius thinking, structural encoding of lessons, and verification-first completion.
- Limitation: pstack's full portfolio and stylistic conventions are not a template for every skill. Adopt mechanisms that solve an observed failure.

## 3. Optimization research

### SkillOpt

- Source repository: https://github.com/microsoft/SkillOpt
- Paper: https://arxiv.org/abs/2605.23904
- Role: validation-gated optimization of skills as trainable external state for frozen agents.
- Adopted: bounded add/delete/replace edits; textual learning-rate budgets; rollout and reflection; strict held-out promotion; best-so-far snapshots; rejected-edit memory; plateau/meta consolidation; transfer testing.

### SkillOpt-Lite and HarnessOpt

- Source: https://github.com/EvolvingLMMs-Lab/SkillOpt-Lite
- Role: minimal file-based optimization loop and explicit separation of skill-only from skill-plus-harness optimization.
- Adopted: train → patch → validation gate → keep or rollback; durable history; allowlisted editable files; smoke tests; separate experiment when the harness itself may change.

### SkillGen

- Paper: https://arxiv.org/abs/2605.10999
- Role: verified skill synthesis from successful and failed trajectories.
- Adopted: contrastive induction; skills as interventions; paired same-instance comparison; explicit repairs and regressions; held-out and cross-model evaluation.

### SkillMOO

- Paper: https://arxiv.org/abs/2604.09297
- Role: multi-objective optimization of task success, cost, and runtime.
- Adopted: preserve a non-dominated set after hard constraints; measure cost and runtime; prefer pruning and substitution when accumulation adds context without effect.

### Self-Supervised Skill Optimization

- Paper: https://arxiv.org/abs/2607.28777
- Role: optimization when reliable ground truth is unavailable.
- Adopted: pairwise comparison of trajectories or artifacts; independent behavior extraction; evidence aggregation; held-out validation gating; explicit uncertainty and human review of discordant consequential cases.

### Cost-aware skill rewriting

- Paper: https://arxiv.org/abs/2606.09421
- Role: quality-cost trade-offs in skill compression and rewriting.
- Adopted: do not optimize raw length alone; preserve sparse API, workflow, rule, formula, debugging, and recovery anchors when they reduce downstream exploration cost; measure total execution cost under fixed tasks and verifiers.

## 4. Mechanisms adopted

This meta-skill combines mechanisms only where their invariants are compatible:

1. **Portable package:** standards-compliant discovery and progressive resources.
2. **Causal brief:** observable behavior to change, counterfactual baseline, boundary, and direct proof.
3. **Evidence model:** claim ledger, expert demonstrations, primary sources, critical incidents, and calibrated uncertainty.
4. **Structural design:** smallest coherent package with one trigger owner and strongest enforceable artifact per requirement.
5. **Deterministic integrity:** path confinement, schema checks, secret scans, no-overwrite scaffolding, and stable machine output.
6. **Fixed evaluation:** immutable cases and atomic criteria, paired fresh contexts, opaque labels, host-computed verdicts, and A/A noise checks.
7. **Optimization:** bounded edits, contrastive trajectory analysis, strict validation promotion, rejected-edit memory, and final untouched test.
8. **Multi-objective release:** hard constraints first, then task effect, regression protection, execution cost, and maintainability.
9. **Field proof:** real target state or artifact when the skill controls an operational workflow.
10. **Continuous learning:** field incidents become sanitized training candidates; final test data stays protected.

## 5. Mechanisms kept separate

Do not collapse these distinctions:

- Skill optimization and model fine-tuning change different state and need different baselines.
- Skill-only optimization and harness/tool optimization are separate experiments.
- Routing evaluation and task-quality evaluation answer different questions.
- Model-simulated expert lenses and accountable professional approval are not equivalent.
- Objective verification and subjective preference require different evidence.
- Static validation, synthetic model evaluation, and field proof are cumulative, not interchangeable.
- Shorter text, fewer files, lower tokens, and lower latency are secondary unless the skill remains correct and effective.

## 6. Refresh triggers

Revisit this register when:

- the Agent Skills specification or a target client's accepted frontmatter changes;
- a creator system changes its routing, resource, or evaluation contract;
- new optimizer evidence contradicts strict promotion, bounded edits, or split discipline;
- a target model or harness changes skill-loading behavior;
- field data shows a recurring failure not represented in the current methodology;
- a cited result cannot be reproduced under its published conditions.

Update `last_verified`, state the changed assumption, and rerun the affected structural, routing, behavioral, transfer, and field evidence. Do not refresh citations without checking whether the design decision still follows.
