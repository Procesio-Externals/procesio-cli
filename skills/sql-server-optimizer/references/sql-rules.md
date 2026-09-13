# Evidence-driven SQL rules

## Access paths

- Keep functions and conversions off indexed columns in selective predicates where an equivalent boundary expression exists.
- Match parameter and column data types, lengths, precision, scale, and collation where relevant.
- Avoid leading-wildcard search for high-volume paths unless full-text or another search design is intended.
- Push selective predicates early only when semantics are unchanged; the optimizer, not textual order, chooses physical join order.

## Joins and cardinality

- Prove join keys and relationship cardinality before changing join type or deduplicating.
- Do not convert `LEFT JOIN` to `INNER JOIN`, move predicates between `ON` and `WHERE`, or add `DISTINCT` without proving equivalence.
- Investigate actual-versus-estimated row gaps, stale statistics, correlation, skew, and table-variable/function estimates.
- Avoid forced join order or join hints until a reproducible optimizer failure and safer fixes have been ruled out.

## Result shape

- Replace `SELECT *` when a stable narrow contract is known; do not guess required columns.
- Remove sorts only when ordering is not a consumer requirement.
- Check spills, memory grants, key lookups, residual predicates, parallelism, and row goals in context—not as isolated red icons.

## Indexes

An index recommendation must include:

- exact key order and rationale;
- included columns and why they cover the path;
- optional filter and its semantics;
- current overlapping/redundant indexes;
- expected read benefit;
- write, storage, maintenance, and locking cost;
- before/after measurement and rollback statement.

Do not infer selectivity from a column name. Use data distribution or label the proposal a hypothesis.

## Concurrency

Measure blockers, waits, transaction duration, access order, and isolation before changing concurrency behavior. `NOLOCK` and `READ UNCOMMITTED` trade correctness for weaker observations; they are not default tuning tools.

## DML

For writes, verify affected rows, uniqueness/business keys, transaction scope, retry safety, trigger behavior, and output needed by callers. Prefer set-based operations when they preserve error and transaction semantics.
