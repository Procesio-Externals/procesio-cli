# Skill decision and portfolio framework

Use this reference before creating, splitting, merging, or retiring skills.

## Contents

1. Leverage test
2. Choose the strongest artifact
3. Set the degree of freedom
4. Design portfolio boundaries
5. Choose an evidence tier
6. Stop conditions

## 1. Leverage test

A skill is justified when most of these are true:

- **Recurring:** the workflow or failure appears repeatedly, or its first failure would be costly enough to justify prevention.
- **Model gap:** success depends on organization-specific knowledge, tool usage, decision order, or failure handling that a capable general model will not reliably infer.
- **Stable core:** the governing workflow is stable enough to encode. Volatile facts can remain in references with an explicit freshness owner.
- **Behavioral effect:** a reader can name which decision, action, or output should change after the skill loads.
- **Observable outcome:** success can be inspected in an artifact, state, output, or defensible human preference comparison.
- **Context leverage:** loading the skill costs less than repeatedly rediscovering or re-explaining the workflow.
- **Bounded ownership:** the trigger region can be separated from neighboring skills without vague arbitration.

Fail the leverage test when the proposed skill is merely a topic summary, a one-time prompt, a personality claim, or a duplicate of an existing tool or skill.

## 2. Choose the strongest artifact

Use the strongest mechanism that can own the requirement:

| Need | Preferred artifact |
|---|---|
| Make an invalid state impossible | type, schema, API boundary, permission, or runtime guard |
| Repeat a deterministic transformation | script or tool |
| Store volatile facts, schemas, or policy detail | reference with owner and freshness rule |
| Guide context-dependent decisions and sequencing | skill |
| Coordinate multiple specialized executors | agent or orchestrator, with skills for method |
| Explain something to humans | documentation |
| Apply a one-time instruction | prompt, not a new skill |

A skill may point to these artifacts. It should not reproduce their full contents.

## 3. Set the degree of freedom

Match instruction precision to the cost of variation:

- **High freedom:** use principles and decision criteria when several approaches are valid and the environment decides which is best.
- **Medium freedom:** use a checklist, pseudocode, or parameterized template when the shape is stable but details vary.
- **Low freedom:** use an executable helper or exact sequence when operations are fragile, destructive, security-sensitive, format-sensitive, or repeatedly misimplemented.

Do not use prose to simulate determinism. Do not use a rigid script where expert judgment is the actual work.

## 4. Design portfolio boundaries

### One-intent ownership test

For every realistic prompt, identify one primary skill owner. Composition may call another skill later, but discovery should not require a tie-breaker between two descriptions.

### Split a skill when

- separate user intents activate unrelated workflows;
- most requests load large irrelevant sections;
- different parts require different permissions, evidence tiers, or freshness owners;
- one description becomes a list of loosely related nouns;
- negative routing cases cannot be expressed without suppressing valid triggers.

### Merge skills when

- they compete for the same prompts and always execute the same core workflow;
- one is only a thin preamble to the other;
- users cannot predict which skill owns the outcome;
- separate packages duplicate invariants, references, or evaluation cases.

### Compose rather than copy when

- a domain workflow needs a general verification or writing method;
- a repository maintainer must integrate a skill after the skill engineer designs it;
- an operational skill invokes a specialized optimizer and then returns to verify the surrounding system.

Name the handoff and the return condition. Do not paste the downstream skill into the caller.

## 5. Choose an evidence tier

| Tier | Typical skill | Minimum evidence |
|---|---|---|
| 0 — subjective | personal style, ideation tone | representative examples plus blinded human preference review |
| 1 — guidance | low-risk research or drafting workflow | positive/negative/overlap routing cases and qualitative output review |
| 2 — operational | code, data, CLI, API, or artifact workflow | immutable baseline, fixed atomic rubrics, paired fresh contexts, deterministic structural checks |
| 3 — high consequence | mutations, credentials, security, compliance, finance, production operations | Tier 2 plus A/A noise measurement, pre-registered A/B thresholds, approval gates, and controlled field proof |

Increase rigor with consequence and ambiguity. Do not force fake quantitative scoring onto genuinely subjective work.

## 6. Stop conditions

Stop and recommend a different artifact when:

- the user cannot name any repeated task or costly failure;
- the requested content is mostly current facts better retrieved from a source;
- a script, schema, or permission boundary can enforce the behavior completely;
- the proposed description would overlap most of the portfolio;
- there is no observable outcome and no credible human comparison method;
- the author wants to skip baseline evidence and still claim improvement;
- the workflow requires secret material inside the skill;
- the package needs hidden behavior not disclosed by its description.

When the leverage case is promising but evidence is incomplete, create a clearly marked draft and state the next proof. Do not inflate the skill to compensate for uncertainty.
