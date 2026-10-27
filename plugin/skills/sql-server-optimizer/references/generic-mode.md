# Standalone T-SQL mode

Use this mode for ad-hoc queries, stored procedures, functions, and scripts outside a PROCESIO action.

## Preserve the contract

Before editing, identify result columns/types, duplicate behavior, ordering, NULL semantics, error/transaction behavior, side effects, and consumers that may depend on rowcount messages or multiple result sets.

## Parameters

- Preserve existing public parameter names and types unless the API change is intentional.
- Do not mutate input parameters merely to normalize them; use a local value when that clarifies semantics.
- Parameterize dynamic SQL with `sp_executesql`; never concatenate untrusted values.
- Do not parameterize identifiers as values. Whitelist identifier choices when dynamic identifiers are unavoidable.
- Treat parameter sniffing as a measured distribution/plan-reuse problem. Do not reflexively add `RECOMPILE`, local-variable masking, or optimize-for hints.

## Procedures and functions

- Add `SET NOCOUNT ON` only when rowcount messages are not part of the consumer contract.
- Preserve transaction and isolation behavior unless requirements and evidence justify a change.
- Prefer inline table-valued logic over row-by-row scalar or multi-statement functions when equivalence and measurements support it.
- Keep deployment settings required by the target environment, but do not add ceremonial headers as an optimization.

## Candidate review checklist

- Same result semantics on representative and edge cases.
- No implicit conversion on the indexed side of important predicates.
- Predicates remain searchable where possible.
- Index proposal matches equality/range/order/output needs and considers write cost.
- No blanket `NOLOCK`, `READ UNCOMMITTED`, forced join, or query hint.
- Before/after plan and IO/time comparison is specified or captured.
- Deployment and rollback are explicit.
