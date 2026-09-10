---
name: procesio-platform-advisor
description: >-
  Assess whether PROCESIO can support a workflow and which architecture fits. Use for
  product capability, feasibility, use-case evaluation, integration limits, PROCESIO
  pricing, cost calculation, how many EEs are needed for a daily volume, execution
  environment capacity sizing, comparisons
  with Zapier, Make, MuleSoft, or Workato, on-prem versus cloud, compliance evidence,
  RPA strategy, and deciding which business processes to automate before implementation.
version: 1.0.2
compatibility: Python 3.11+ for the optional offline capacity calculator.
owner: PROCESIO product and solution architecture
last_verified: 2026-09-05
baseline_version: da12de643c8a2355d019f40515766abf80a819df
eval_suite: evals/evals.json
source_policy: timestamped
routing:
  triggers:
    - assess PROCESIO product fit, feasibility, architecture, pricing, sizing, or compliance
    - compare PROCESIO with another automation or integration platform
    - decide which processes to automate without changing a workspace
  primary_action: advise
  example: get-skill.py procesio-platform-advisor --content
---

# Advise on PROCESIO

Use this skill for a decision about PROCESIO, not for operating a workspace. Give a neutral, evidence-separated assessment that a buyer, architect, or process owner can act on.

## Boundary

- A request to create, edit, run, inspect, or verify a platform resource belongs to `procesio-cli`.
- A request to optimize T-SQL belongs to `sql-server-optimizer`.
- A request to change this repository belongs to `procesio-cli-maintainer`.

## Advisory workflow

1. **State the decision.** Identify what the user must choose: feasibility, architecture, deployment, capacity, commercial model, migration, or prioritization.
2. **Collect material constraints.** Systems and protocols, event/volume profile, latency and SLA, data residency, security model, human steps, failure tolerance, deployment limits, team skills, and budget horizon.
3. **Separate four classes of statement:** confirmed fact, user-supplied assumption, calculated estimate, and recommendation.
4. **Evaluate the end-to-end process.** A platform action existing is not proof that the use case works. Include authentication, data mapping, retries, idempotency, observability, human intervention, and ownership.
5. **Present options and trade-offs.** Include at least one credible alternative where material. Do not force a PROCESIO-positive conclusion.
6. **Name the proof needed next.** Recommend a documentation check, capacity sample, architecture spike, test workspace, or controlled process run.

Read:

- `references/capability-map.md` for stable product areas and CLI-verifiable surfaces.
- `references/fit-framework.md` for feasibility and prioritization.
- `references/sizing-method.md` for capacity estimates without inventing prices.
- `scripts/estimate_capacity.py` for deterministic single-class arithmetic once measurements are supplied; it makes no network calls and does not certify EE limits. Read the sizing reference for its JSON input contract.
- `references/freshness-policy.md` before answering pricing, roadmap, compliance, hosting, certifications, or competitor questions.

## Answer shape

### Decision
A direct recommendation or qualified verdict.

### Confirmed facts
Only claims supported by current first-party material or live CLI evidence. Cite the source and verification date for volatile facts.

### Assumptions and estimates
List missing values and show calculations with units and ranges.

### Trade-offs and risks
Explain what could make the recommendation wrong.

### Next proof
Name the cheapest concrete test or evidence that resolves the largest uncertainty.

## Verification

If current sources are unavailable, give a provisional assessment, separate stable reasoning from unverified claims, and name the exact documentation, quote or measurement still needed. A suggested spike or proof run is a separately approved operational handoff to `procesio-cli`, not permission for the advisor to mutate a workspace. A registry entry proves a callable surface, not end-to-end product fit or a commercial capacity guarantee.

## Non-negotiable rules

- Do not expose private prices, internal plans, credentials, or customer details from stale skill prose.
- Do not present roadmap items as shipped features.
- Do not equate infrastructure certification with automatic compliance of a customer's complete solution.
- Do not claim a percentage cost advantage without a current, comparable workload and source.
- Do not answer a current commercial, compliance, roadmap, or competitor claim from memory when it can be verified.
