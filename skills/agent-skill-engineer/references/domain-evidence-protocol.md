# Domain evidence and expert synthesis protocol

Use this reference before encoding specialized, high-consequence, or organization-specific expertise into a skill.

## Contents

1. What expert synthesis is
2. Decision inventory
3. Claim and evidence ledger
4. Source hierarchy
5. Eliciting tacit expertise
6. Selecting independent expert lenses
7. Shared evidence packet
8. Independent review contract
9. Resolving disagreement
10. Converting expertise into executable guidance
11. Calibration and refusal
12. Accountable human review
13. Maintenance and drift

## 1. What expert synthesis is

Expert synthesis is a method for exposing a proposed workflow to distinct professional failure models and evidence. It is not role-play, prestige language, or a claim that several model personas equal qualified practitioners.

The output is a calibrated decision model:

- what cues matter;
- which action or handoff follows;
- which invariants must hold;
- what evidence changes the decision;
- where uncertainty remains;
- who has authority to approve or overrule the result.

Choose reviewers because their lens can change a material design decision, not to maximize their count.

## 2. Decision inventory

Before collecting facts, enumerate the decisions the skill must support. For each decision, record:

- trigger and context;
- candidate actions or abstention;
- required inputs and observable state;
- irreversible or high-cost consequences;
- default under missing evidence;
- escalation owner;
- direct proof of a correct outcome.

Do not research a broad topic without tying evidence to a decision. Topic encyclopedias consume context while leaving the agent's choice ambiguous.

## 3. Claim and evidence ledger

Maintain a ledger with one row per material claim:

| Field | Meaning |
|---|---|
| `claim_id` | stable identifier |
| `claim` | one falsifiable statement |
| `class` | fact, invariant, heuristic, policy, preference, hypothesis, or unknown |
| `scope` | systems, versions, jurisdictions, populations, or conditions where it applies |
| `source` | primary artifact, observation, study, standard, or accountable owner |
| `observed_on` | date/version of evidence |
| `confidence` | calibrated level with reason |
| `disconfirming_evidence` | evidence that would weaken or reverse the claim |
| `decision_impact` | exact instruction, boundary, or evaluation criterion affected |
| `owner` | person or system responsible for refresh |

Never merge several claims under one citation. Distinguish a source's assertion from independent empirical confirmation. Mark local convention as policy, not universal domain truth.

## 4. Source hierarchy

Prefer evidence in this order, adjusted for the domain:

1. **Direct state and authoritative artifacts:** source code, schemas, contracts, controlled measurements, signed policy, primary records, and real user outcomes.
2. **Primary standards and research:** normative specifications, official guidance, peer-reviewed or directly inspectable studies, and regulator material.
3. **Expert demonstrations and critical incidents:** successful and failed cases with decision context and outcome evidence.
4. **Current first-party documentation:** product behavior, supported interfaces, and release-specific constraints.
5. **High-quality synthesis:** secondary reviews used to discover primary evidence or map disagreement.
6. **Anecdote or model memory:** hypothesis generation only, never the sole basis for a consequential invariant.

Check version, date, jurisdiction, incentives, sampling, and applicability. Absence of evidence is not evidence that a risky behavior is safe.

## 5. Eliciting tacit expertise

Generic interviews produce generic rules. Elicit decisions through concrete cases:

- Ask for the last successful case, the last failure, and a near miss.
- Reconstruct the timeline, information available at each moment, alternatives considered, and signals that changed the decision.
- Ask what a competent novice would likely miss.
- Compare superficially similar cases with different correct actions.
- Identify cues that were ignored, misleading, or discovered too late.
- Capture workarounds, exception ownership, and recovery behavior.
- Verify recalled explanations against artifacts and outcomes where possible.

Separate what the expert did from why it worked. A repeated practice may be habit, policy, environmental constraint, or causal mechanism; encode it only after classification.

## 6. Selecting independent expert lenses

Select every lens implicated by consequence and uncertainty. Typical lenses include:

- domain subject-matter correctness;
- cognitive and instruction design;
- information architecture and context economics;
- tool/API and systems architecture;
- security and privacy;
- reliability, idempotency, and observability;
- human factors and accessibility;
- evaluation design and statistics;
- portability and integration;
- adversarial misuse;
- future maintenance and source drift.

For high-consequence domains, add the accountable roles required by law, policy, or organizational authority. A model can simulate questions and failure modes; it cannot assume licensure, fiduciary duty, clinical responsibility, legal authority, or production ownership.

## 7. Shared evidence packet

Give every reviewer the same immutable packet:

- user outcome and explicit non-goals;
- decision inventory and claim ledger;
- positive, negative, overlap, missing-context, pressure, and success cases;
- baseline behavior and known failures;
- target clients, tools, permissions, side effects, and evidence tier;
- candidate designs under opaque labels where comparison is required;
- fixed review questions and acceptance criteria;
- known source conflicts and uncertainties.

Do not prime reviewers with another reviewer's conclusion. Do not give one candidate a richer context or more favorable evidence.

## 8. Independent review contract

Each reviewer returns findings independently using:

```text
finding_id
lens
claim_or_invariant_at_issue
evidence
scope
confidence
failure_consequence
proposed_design_change
disconfirming_condition
severity: blocker | major | minor | preference
```

A finding without distinct evidence, consequence, or design impact is not counted as expert signal. Require reviewers to identify both false-positive and false-negative risks. Ask them to name what should remain unchanged.

Use adversarial pre-mortems:

- How could this skill confidently produce a wrong result?
- What prompt makes it cross a permission or ownership boundary?
- What baseline success could a new rule damage?
- What proxy could be mistaken for completion?
- What stale fact could remain plausible after the underlying system changes?
- What rare subgroup or edge state disappears in an average metric?

## 9. Resolving disagreement

Do not vote by reviewer count or status. Resolve conflicts in this order:

1. direct outcome evidence and authoritative constraints;
2. user objective and non-negotiable rights or safety boundaries;
3. applicability and scope of each claim;
4. reversible experiment capable of discriminating between hypotheses;
5. accountable human decision when evidence cannot resolve a policy or authority question.

Preserve unresolved dissent in the ledger. Narrow the skill's scope when experts disagree because conditions differ. Reject a blended compromise that violates both coherent models.

When a disagreement is empirical, design the smallest safe test. When it is normative, identify the authorized decision-maker rather than disguising preference as fact.

## 10. Converting expertise into executable guidance

Transform evidence into compact structures:

### Decision table

| Observable cue | Required evidence | Action | Do not do | Proof or handoff |
|---|---|---|---|---|

### State transition

```text
precondition → inspect → classify → preview → approve → execute once → observe → recover → report
```

### Invariant

```text
Must remain true before, during, and after the workflow; enforced by <script/schema/runtime/test> where possible.
```

### Escalation rule

```text
When <condition> or evidence confidence is below <registered level>, stop and hand off to <accountable owner> with <evidence packet>.
```

Encode stable recurring decisions in the body. Put detailed variants and dated facts in references. Put deterministic checks and transformations in scripts. Put permissions and invalid-state prevention in executable boundaries.

## 11. Calibration and refusal

Require the skill to distinguish:

- directly observed fact;
- source-supported fact;
- inference;
- estimate;
- local policy;
- recommendation;
- unresolved uncertainty.

Calibrate confidence to evidence quality, not prose fluency. State the scope in which a rule was validated. Define stop conditions where missing information would materially change the result.

A refusal or handoff is correct when:

- the skill lacks evidence for a consequential decision;
- a required licensed or authorized reviewer is absent;
- the target lies outside validated scope;
- a safety invariant cannot be enforced or verified;
- user instructions conflict with law, policy, consent, or protected rights;
- the requested certainty exceeds available evidence.

## 12. Accountable human review

Require human signoff when the skill affects legal rights, clinical care, regulated finance, public or physical safety, compliance attestation, employment decisions, security authorization, or other domains where accountability cannot be delegated to a model.

Record:

- reviewer role and authority;
- exact version and evidence reviewed;
- approved scope and exclusions;
- unresolved risks and monitoring plan;
- renewal condition and expiration date where relevant.

Human approval is not a substitute for testing. Model review is not a substitute for accountable approval. Use both when the consequence requires both.

## 13. Maintenance and drift

Assign every material source and policy an owner and refresh condition. Re-evaluate when:

- a standard, law, product, model, API, or organizational policy changes;
- a new critical incident contradicts an encoded rule;
- users repeatedly override the same recommendation;
- field outcomes diverge from synthetic evaluation;
- expert disagreement emerges in a previously stable area;
- the skill expands to a new jurisdiction, population, system, or risk tier.

Retire unsupported claims rather than burying caveats. Preserve the old package and evidence so maintainers can determine whether a change is true learning, changed conditions, or regression.
