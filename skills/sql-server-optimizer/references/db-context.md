# SQL Server context collection

Collect only what can change the recommendation.

## Minimum context

- exact query/object definition;
- SQL Server version and database compatibility level;
- relevant table columns and data types;
- primary/foreign/unique keys;
- current indexes including key order, includes, filters, and usage where available;
- representative row counts and parameter values;
- actual execution plan and `STATISTICS IO/TIME` when safe;
- concurrency symptom: slow alone, blocked, blocking others, or intermittent.

## Agentic path

Use the registered `sqlserver` tool for bounded read-only metadata when a configured profile exists. Confirm the server, database, profile and access scope; configuration alone does not grant execution permission. Do not request credentials in chat or put them in SQL files.

An actual execution plan executes the statement; `SET STATISTICS IO, TIME ON` also measures a real execution. Inspect procedures, dynamic SQL and triggers before calling a workload read-only. Prefer existing Query Store/plan evidence or an estimated plan when execution is not approved; label missing runtime rows and metrics.

Obtain explicit approval of the exact workload, target, run count and side effects before potentially mutating or expensive execution or any production measurement. Use an isolated representative copy where possible. A transaction plus `ROLLBACK` is not a universal sandbox: execution can still lock shared data, consume resources, invoke external effects or consume identity/sequence values. Never clear shared caches or change isolation to manufacture a comparison.

After timeout or connection loss during a write/procedure call, record an unknown outcome. Reconcile by business key and transaction state through approved reads before retrying; a measurement failure is not permission to repeat the workload. Keep index/DDL changes as proposals until deployment and recovery are approved.

## User-provided path: pre-acquisition gate

Read-only metadata can disclose confidential code and embedded secrets. Before running an exporter or requesting its output, obtain explicit approval of the exact server/current database, object classes and breadth, confidential definition access, protected output destination/retention, and authorized recipients. Prefer a separately reviewed bounded metadata projection when whole-database scope is unnecessary or unapproved; stop rather than acquiring broadly and redacting afterward. Do not send raw definitions to an agent, transcript or shared artifact for redaction.

The bundled legacy inspection-only helpers have no object allowlist and cover the whole current database (subject to metadata visibility):

- `scripts/export-tables.sql`: user tables, constraints, computed/default expressions, DML and database DDL trigger definitions. `@p_Database` labels output only; it does not switch the connection's database. Server-wide trigger definitions extend beyond database scope and require separate approval plus explicit `@p_IncludeServerTriggers = 1`; the default is `0`, even with server permissions.
- `scripts/export-indexes.sql`: all visible non-constraint, non-hypothetical indexes on user tables, including filter literals. Its generic rowstore-shaped serializer is not valid for columnstore, XML, spatial, hash or other non-rowstore types. Do not automatically run it on mixed/unsupported types; request a bounded catalog projection instead. Never execute generated DDL as an automatic next step.
- `scripts/export-procs-and-functions.sql`: all visible user procedure and SQL function definitions (FN/IF/TF), not only modules called by the query. Definitions can contain sensitive literals; unavailable definitions do not prove absence.

### Qualification blockers retained from source

These are inspection aids, not qualified general-purpose DDL/backup or replay tools. Unsupported index-family serialization remains unrepaired; even rowstore output is not certified complete or replay-safe. Table/trigger concatenation can propagate NULL definitions into the output, so missing text is not evidence of an empty database. No live SQL compatibility or reconstruction validation accompanies this publication. Require DBA review and independent scoped catalog checks; keep automated extraction/replay qualification blocked until the owning runtime work supplies evidence. The only runtime change here is the server-trigger opt-in, not a general exporter repair.

After approved acquisition into a protected boundary, share only the relevant sanitized projection. Redact literals, customer data, and secret-bearing definitions before sharing. An estimated plan is useful for compile-time shape; an actual plan is needed for actual rows and runtime warnings.

## Baseline discipline

Use the same database state, parameters, cache policy, and capture method for before/after comparisons. Record whether the cache was warm or cold. Test at least two parameter shapes when skew or parameter sensitivity is plausible.
