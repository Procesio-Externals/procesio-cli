# Shared SQL Optimization Rules

These rules apply to **all modes** (A1, A2, B). Apply after mode-specific parameterization rules.

---

## C. FROM / JOIN Strategy

### C1. Join Order
- Start from the **smallest / most selective table**, then join outward to larger tables.
- INNER JOINs before LEFT/RIGHT/FULL — INNER joins reduce row count for downstream joins.
- Place restrictive predicates **in the ON clause** (not WHERE) when semantically safe.
- Remove unused joins entirely.

### C2. Join Count Limit
Keep joins to **≤5–6 per statement**. The SQL Server optimizer uses exhaustive search up to a threshold — beyond it, the engine switches to heuristic (greedy) plans because permutations grow factorially:

| Joins | Permutations | Optimizer behavior |
|-------|-------------|-------------------|
| 5 | 120 | Full optimization |
| 6 | 720 | Borderline |
| 7 | 5,040 | Heuristic only — often suboptimal |
| 8 | 40,320 | Guaranteed worst-case plan |

If joins exceed 5–6 or logic is complex: stage with CTE or #temp table.

### C3. Staging Heuristic
- **CTE**: single-use, improves readability, no materialization guarantee.
- **#temp table**: reused in multiple queries, benefits from intermediate indexing, forces materialization (useful for large row reduction before a complex join).
- Mention the choice and reason in Notes.

---

## D. WHERE / Predicate Quality

### D1. Selectivity Order
Order predicates most selective first:
- Equality on an indexed column → range filter → LIKE → computed/function conditions

### D2. Sargability
Never wrap columns in functions in WHERE or JOIN predicates — this prevents index seeks:
- ❌ `WHERE YEAR(I.IssueDate) = 2024` — non-sargable; full scan
- ✅ `WHERE I.IssueDate >= '2024-01-01' AND I.IssueDate < '2025-01-01'` — sargable; index seek

Apply functions to literals/params, not to columns.

### D3. Type Safety
Detect implicit conversions in joins and filters — they prevent index seeks and can cause incorrect results.

Fix by casting the **literal or parameter** to the column's type, never the column itself:
- ✅ `WHERE I.CustomerId = CAST(@p_CustomerId AS INT)` — column uncast, index usable
- ❌ `WHERE CAST(I.CustomerId AS NVARCHAR) = @p_CustomerId` — column cast kills index

Note the type assumption in Notes.

---

## E. Optional Filters

Canonical pattern — always:
```sql
WHERE (@Ref IS NULL OR Table.Column LIKE '%' + @Ref + '%')
```

Never simulate optional filters with row-level CASE:
- ❌ `WHERE Col LIKE CASE WHEN @Ref IS NULL THEN '%' ELSE '%' + @Ref + '%' END`

`LIKE '%x%'` always causes a full table scan regardless of pattern. If the target table is large: warn in Notes, suggest a filtered index or full-text search.

---

## F. Aggregation & Windowing

- Push filters **before** aggregation — filter rows, then GROUP BY.
- Use `GROUP BY` only on columns actually needed; do not include unreferenced columns.
- Use window functions (`ROW_NUMBER`, `RANK`, `SUM() OVER`, etc.) when they simplify logic or eliminate extra self-joins.
- For deduplication: prefer `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` over DISTINCT where order matters.

---

## G. Existence, Duplicates, Paging

- Prefer `EXISTS` over correlated `IN (SELECT ...)` — EXISTS short-circuits on first match.
- Use `DISTINCT` only when logically required and the join cannot be fixed.
- Paging pattern:
  ```sql
  ORDER BY <deterministic_column>
  OFFSET @p_Skip ROWS
  FETCH NEXT @p_Take ROWS ONLY;
  ```
- Always require a deterministic `ORDER BY` for paging. Warn if ORDER BY is missing or non-deterministic.

---

## H. Anti-patterns

- **SELECT \***: avoid unless explicitly required. If column list unknown: keep functional, add comment near SELECT, note it.
- **Scalar UDFs in WHERE/JOIN**: flag; inline when possible. Scalar UDFs execute per-row and prevent parallelism.
- **OR across different columns**: consider `UNION ALL` when each branch can use a separate index.
- **RBAR (Row By Agonizing Row)**: cursors and loops — replace with set-based logic unless unavoidable.
- **Heavy LIKE '%x%' on large tables**: always warn; suggest FTS or filtered index.
- **Dynamic SQL with concatenation**: flag; require `sp_executesql` with parameters.

---

## I. Index & Statistics Awareness (Notes-only)

- Suggest missing indexes or stats refresh **in Notes only** — never embed query hints in the SQL.
- Do not add `INDEX`, `FORCESEEK`, `NOLOCK`, or other hints unless the user explicitly requests them.

**Without schema context** (no export provided):
- Infer likely indexed columns from PK/FK naming conventions, join keys, and frequent filter column patterns.
- State assumptions explicitly: "assuming CustomerId is indexed as a PK — verify against schema."
- Give generic guidance: "consider an index on this filter column."

**With `export-indexes.sql` output provided:**
- Verify actual index coverage before suggesting any new index.
- Reference real index names when noting that a covering index already exists.
- Propose specific `CREATE INDEX` statements using actual column names and types from the schema.
- Flag redundant indexes: if a proposed key is a left-prefix of an existing index, note the overlap.
- Flag disabled indexes: if the relevant index exists but is disabled, note this instead of proposing a new one.

---

## K. DML — INSERT / UPDATE / DELETE

### K1. INSERT
Always specify the target column list:
```sql
INSERT INTO dbo.TableName (Col1, Col2, Col3)
VALUES (@Col1, @Col2, @Col3);
```
If columns are unknown: keep functional, add a nearby comment, note it — schema changes will break column-list-free INSERTs silently.

### K2. UPDATE with JOIN
When the UPDATE filter depends on another table, use the joined UPDATE pattern:
```sql
UPDATE I
SET I.Status = @NewStatus
FROM dbo.InvoicesFilesLinks AS IFL
    INNER JOIN dbo.Invoices AS I ON I.Id = IFL.InvoiceId
WHERE IFL.FileGUID = @FileGuid;
```

### K3. DELETE with JOIN
```sql
DELETE IFL
FROM dbo.InvoicesFilesLinks AS IFL
    INNER JOIN dbo.Invoices AS I ON I.Id = IFL.InvoiceId
WHERE I.CustomerId = @CustomerId
  AND IFL.FileGUID = @FileGuid;
```

Always preserve semantics — never update or delete from the wrong side of a join.

---

## L. Plan-First Intuition

- Reduce rows as early as possible in the execution path.
- Defer nonessential columns — avoid wide rows early in joins; project only what's needed downstream.
- Stage intermediate results when doing so improves cardinality estimation for subsequent operations.

---

## M. Assumptions Policy

If optimization depends on unknown data distribution, schema details, or business meaning:
- Proceed conservatively.
- Preserve original semantics.
- State all assumptions explicitly in Notes.
