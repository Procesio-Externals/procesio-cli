---
name: sql-server-optimizer
description: >-
  Analyze and optimize SQL Server T-SQL, including SQL executed by PROCESIO. Use when
  reviewing a query, procedure, function, execution plan, index strategy, sargability,
  parameter sniffing, implicit conversions, logical reads, blocking, reporting-query
  performance, result semantics, isolation safety, or PROCESIO inline/native SQL
  parameters; do not use for PostgreSQL, MySQL, or repository maintenance.
version: 1.0.1
owner: database engineering
last_verified: 2026-09-05
baseline_version: da12de643c8a2355d019f40515766abf80a819df
eval_suite: evals/evals.json
source_policy: static
routing:
  triggers:
    - analyze or optimize SQL Server T-SQL, execution plans, indexes, logical reads, blocking, or parameter sniffing
    - review SQL used in a PROCESIO Execute Query or Execute Command action
    - replace unsafe PROCESIO inline SQL variables with native typed parameters
  primary_action: analyze
  example: get-skill.py sql-server-optimizer --content
---

# Optimize SQL Server with evidence

Optimize **measured bottlenecks while preserving semantics**. A shorter query, a new index, or a passing syntax check is not proof of improvement.

## Boundary

- PostgreSQL, MySQL, Oracle, or generic database design without SQL Server: do not use this skill.
- Operating the surrounding PROCESIO process belongs to `procesio-cli`; this skill owns the T-SQL analysis.
- Authoring or evaluating this skill belongs to `agent-skill-engineer`; repository code and skill integration belong to `procesio-cli-maintainer`.

## Required workflow

1. **Define correctness.** Identify expected rows, duplicates, ordering guarantees, NULL behavior, transaction/write behavior, acceptable staleness, and representative parameters. Preserve these unless the user explicitly changes them.
2. **Establish context.** Before acquisition, approve the server/database, object scope, confidential definitions, output destination and recipients. Collect only relevant table/column types, keys, current indexes, compatibility level, row counts/distribution, and called object definitions. Prefer bounded metadata queries through the registered `sqlserver` tool. The bundled read-only exporters scan the whole current database, not just relevant objects, and retrieve all visible definitions of their module classes; use the gate in `references/db-context.md`, not automatic execution.
3. **Capture a baseline.** Prefer actual execution plan plus `SET STATISTICS IO, TIME ON` on representative parameters. For production, use safe existing telemetry when an ad-hoc execution would be risky.
4. **Find the dominant bottleneck.** Examples: scan caused by a non-sargable predicate, cardinality error, spill, lookup amplification, implicit conversion, blocking, parameter sensitivity, or excessive result width.
5. **Change one lever.** Rewrite one predicate/join/aggregation, adjust parameter handling, or propose one index. Keep speculative alternatives separate.
6. **Re-measure.** Compare logical reads, CPU, elapsed time, rows, spills, memory grant, and plan shape under the same conditions and more than one representative parameter set when sensitivity matters.
7. **Verify semantics and concurrency.** Compare result sets or invariants and review lock/isolation implications. Reject a faster result that is wrong, stale beyond the requirement, or more dangerous under concurrency.

Tuning permission is not deployment permission. Default to analysis and candidate SQL; require explicit approval of the target and side effects before DDL, DML, procedure execution, production measurement, or isolation/cache changes. Apply the execution and unknown-outcome rules in `references/db-context.md` before collecting a new plan or measurement.

Read `references/db-context.md`, then the relevant mode:

- `references/procesio-mode.md` for PROCESIO SQL actions and parameter mapping.
- `references/generic-mode.md` for standalone queries, procedures, and functions.
- `references/sql-rules.md` for evidence-driven rewrite and index checks.

When metadata cannot be queried through the registered tool, request an approved, bounded safe projection. The legacy inspection-only helpers `scripts/export-tables.sql`, `scripts/export-indexes.sql`, and `scripts/export-procs-and-functions.sql` require pre-acquisition scope/confidentiality approval for whole-database extraction; post-read redaction is not that gate. Table export includes trigger definitions, with server-wide triggers disabled unless separately approved and explicitly opted in. The index helper does not correctly serialize all index types: do not automatically run it on mixed/unsupported types or execute its generated DDL. Review the qualification blockers in `references/db-context.md` before using any exporter; inspect protected output for sensitive literals before sharing.

## Isolation and correctness rule

**Never add `READ UNCOMMITTED` or `NOLOCK` as a generic performance optimization.** They permit dirty and internally inconsistent observations and do not solve the underlying access-path or blocking design. Preserve the existing isolation level unless the workload's consistency contract is explicit and the user authorizes a change. Consider row-versioning or transaction/query design only after measuring the actual blocking problem.

Do not add boilerplate signature headers, hints, forced join order, recompilation, indexes, or parameterization merely because a template says so. Every change must have a reason tied to evidence or a clearly labeled hypothesis.

## PROCESIO parameter rule

Native typed parameter mapping is the preferred boundary. Inline `<%Variable%>` substitution is text generation, not parameterization. Do not claim that wrapping an inline token in `DECLARE` removes injection or typing risk. Rewrite the SQL to native `@parameter` placeholders and provide the exact mapping the PROCESIO action must configure. When native mapping is unavailable, state the residual risk and require the platform's exact escaping/serialization contract before proposing a fallback.

## Output contract

### Verdict
Name the dominant issue and whether a measured optimization is possible with the supplied evidence.

### Context and assumptions
List schema/plan/parameter facts received and what is missing.

### Proposed SQL or index
Provide the smallest defensible change. Preserve the original when evidence is insufficient.

### PROCESIO parameter mapping
When applicable, list `@parameter → process variable`, SQL type, nullability, and required action configuration.

### Before/after evidence
Show comparable metrics or a reproducible measurement plan. Never fabricate a gain.

### Correctness and operational risks
State result-set, transaction, isolation, deployment, rollback, and plan-variance risks.

## Completion verification

Do not say “optimized” unless there is before/after evidence and semantic verification. Without a runnable database, label the result **candidate rewrite** and name the exact tests needed.
