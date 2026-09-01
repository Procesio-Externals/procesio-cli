---
name: sql-server-optimizer
description: >
  SQL Server T-SQL optimizer for plain SQL and PROCESIO workflows. Rewrites queries, stored
  procedures, functions, and scripts into faster, cleaner, production-ready code. Detects
  PROCESIO inline variables and native param-style SQL, converting them correctly. Improves
  JOIN order, ensures sargability and type safety, forces READ UNCOMMITTED isolation and
  signature headers on all objects, and outputs a parameter mapping block plus concise notes.

  ALWAYS use this skill when the user:
  - Pastes any T-SQL, plain or containing PROCESIO variables
  - Asks to optimize, review, fix, clean up, rewrite, or improve SQL
  - Asks why a query is slow or how to make it faster
  - Asks about SQL Server indexes, parameter sniffing, or query plans
  - Uses phrases like "optimize this query", "review my proc", "rewrite this SQL",
    "fix this T-SQL", "make this faster", "parameterize this", or "PROCESIO SQL"
  - Asks about JOIN strategies, predicate quality, or sargability
  - Shares a SQL snippet for any reason and it could benefit from review
---

# SQL Server Optimizer

## Step 0 — Assess Database Context

Before classifying the query, assess whether schema context would improve the optimization.

Schema context enables: accurate type checking, correct JOIN ordering, precise index
suggestions with real column names, and validation of implicit conversions. Without it,
the optimizer proceeds on assumptions and can only give generic Notes.

Three export scripts are available in `references/scripts/`. Each targets a different
information layer:

| Script | Use when |
|--------|---------|
| `export-tables.sql` | Table structure, column types, constraints — always the first script to request |
| `export-indexes.sql` | Index coverage, covering indexes, filtered indexes — request whenever indexes are relevant |
| `export-procs-and-functions.sql` | Existing proc/function definitions — request when the query calls or is part of a proc/function |

**Ask the user to run the relevant scripts when:**
- The query references tables or columns whose structure is unknown
- 3+ JOINs are present and selectivity order cannot be confidently inferred
- Index recommendations are requested or sargability issues are suspected
- Type mismatches or implicit conversions are suspected
- The user reports unexpected query behavior or plan regression
- The query calls scalar UDFs, TVFs, or other procs

**Skip asking when:**
- The query is simple (1–2 tables, obvious structure, no type ambiguity)
- The user has provided table definitions inline or schema is clear from context
- The user says SSMS access is unavailable

**In agentic environments** (CoWork + database connector): execute all relevant scripts
directly. Run `export-tables.sql` and `export-indexes.sql` first, then
`export-procs-and-functions.sql` only if needed. See `references/db-context.md` for
the full agentic workflow and how to parse each output.

**How to ask the user** (adapt tone to context):
> "To give you the most accurate optimization, I need the structure and index coverage of the
> tables involved. Could you run two scripts on the target database and share the output?
>
> **How for each script:** Open SSMS → paste and run the script → click the **Messages** tab
> (not Results) → select all (Ctrl+A), copy, paste into a `.txt` file → share it here.
>
> Scripts needed: `export-tables.sql` + `export-indexes.sql`
> (also `export-procs-and-functions.sql` if the query references stored procedures or functions)"

See `references/db-context.md` for the full guide: per-script trigger conditions, Romanian
user instructions, and how to use each output once provided.

---

## Step 1 — Detect Mode

Classify the input using this decision tree:

**Does the SQL contain `<%VarName%>` tokens?**
→ Yes → **Mode A1** (PROCESIO inline variable injection)

**Does the user say this SQL runs inside a PROCESIO Execute Query or Execute Command action,
OR does the SQL have `@paramName` style params with no DECLARE block (mapped via PROCESIO Parameters config tab)?**
→ Yes → **Mode A2** (PROCESIO native parameter mapping)

**Otherwise** (plain T-SQL: literals, stored procs, functions, scripts, standalone queries)
→ **Mode B** (Generic SQL)

> When in doubt about PROCESIO context, ask the user: "Is this query used inside a PROCESIO Execute Query or Execute Command action?"

Read the appropriate reference file:
- Mode A1 or A2 → `references/procesio-mode.md`
- Mode B → `references/generic-mode.md`

Always also read `references/sql-rules.md` — shared optimization rules apply to all modes.

---

## Step 2 — Output Format

**All modes use the same SQL comment wrapper format.** Do not deviate.

```
/*Optimized SQL:*/
<final SQL>

/* Parameter Mapping:
@p_Name (type) -> original source / purpose
...

Notes:
- <bullet>
*/
```

If no parameterization applies:
```
/* Parameter Mapping:
- None (no changes)
*/
```

> Notes: 1–5 bullets for Mode A1/A2, 1–7 bullets for Mode B.
> Parameter Mapping block is always present, even if empty. Never omit it.

---

## Step 3 — Apply Rules

1. Run the mode-specific rules from the reference file.
2. Run the shared SQL optimization rules from `references/sql-rules.md`.
3. Run the universal object rules below (apply to ALL modes, ALL SQL object types).
4. Verify against the checklist in the reference file before outputting.

---

## Universal Object Rules (ALL modes)

These apply regardless of mode whenever the SQL contains or produces a stored procedure or function.

### Signature header — always required
Every stored procedure and function must have this header comment block:
```sql
-- =============================================
-- Author:      <Author,,Name>
-- Create date: <Create Date,,>
-- Description: <Description,,>
-- =============================================
```
If the input already has it, keep it. If missing, add it.

### Isolation level — always required
Every stored procedure and function body must begin with:
```sql
SET NOCOUNT ON
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED
```
Both lines, in that order, no exceptions. If already present, keep. If missing, add.

> Note in Notes: READ UNCOMMITTED allows dirty reads — acceptable for reporting/read-heavy queries. If the proc performs writes or transactional logic, flag this explicitly and suggest the user evaluate whether stricter isolation is needed.

---

## Reference Files

| File | Purpose |
|------|---------|
| `references/procesio-mode.md` | Modes A1 + A2: PROCESIO injection patterns, constraints, checklist, examples |
| `references/generic-mode.md` | Mode B: literal parameterization, proc/function templates, checklist, examples |
| `references/sql-rules.md` | Shared: JOIN strategy, WHERE quality, aggregation, anti-patterns, DML patterns |
| `references/db-context.md` | Schema export guide: when to request each script, how to run, how to use output, agentic workflow |
| `references/scripts/export-tables.sql` | Read-only: exports all tables, columns, types, constraints, triggers |
| `references/scripts/export-indexes.sql` | Read-only: exports all non-constraint indexes with key/include columns, filter clauses, type, fill factor |
| `references/scripts/export-procs-and-functions.sql` | Read-only: exports all stored procedures and user-defined functions |
