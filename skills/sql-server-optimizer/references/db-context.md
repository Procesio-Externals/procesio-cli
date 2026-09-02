# Database Context — Schema Export Scripts

The optimizer works better when it knows the actual database structure: table schemas, column
types, constraints, existing stored procedures, functions, and indexes. Three export scripts
are bundled in this skill for exactly this purpose.

---

## The Scripts

| Script | What it exports |
|--------|----------------|
| `scripts/export-tables.sql` | All user tables with columns, full data types (varchar/nvarchar length, decimal precision/scale, identity, computed columns), constraints (PK, UQ, FK, CHECK, DEFAULT), and triggers (DML + DDL) |
| `scripts/export-procs-and-functions.sql` | All user stored procedures and user-defined functions (scalar, inline TVF, multi-statement TVF) with their full `CREATE`/`ALTER` definition text |
| `scripts/export-indexes.sql` | All non-constraint indexes on user tables: key columns (with sort direction), included (non-key) columns, filtered index WHERE clauses, index type (CLUSTERED / NONCLUSTERED / COLUMNSTORE / XML / SPATIAL), UNIQUE flag, fill factor, disabled state |

**Relationship between scripts:**
- `export-tables.sql` covers PK and UQ constraint-backed indexes as part of the `ALTER TABLE ADD CONSTRAINT` output.
- `export-indexes.sql` covers all remaining standalone `CREATE INDEX` statements — these two are complementary; together they give the complete index picture for every table.
- `export-procs-and-functions.sql` is independent — run it only when the query references existing procs or functions.

These scripts are read-only — they query system catalog views and produce no changes to the database.

**Do not modify these scripts.** They are authoritative as provided.

---

## How to Run the Scripts and Get the Output

The output of these scripts is too large to copy from the SSMS **Results** tab. The scripts
are designed to write output to the **Messages** tab instead, using `PRINT` in chunks.

### Steps

1. Open **SQL Server Management Studio (SSMS)**
2. Connect to the database you want to analyze
3. Open a new query window and paste one of the scripts
4. Execute the script (F5)
5. Click the **Messages** tab (not Results) at the bottom of the query window

   > The Messages tab is next to the Results tab. It shows text output from `PRINT` and
   > `RAISERROR` statements. This is where the full schema definition appears.

6. Select all text in the Messages tab (Ctrl+A), copy it, and paste it into a `.txt` file
7. Provide that `.txt` file (or its content) to the optimizer

Run each script separately; save each output to its own `.txt` file.

### Romanian instruction for users (use when the user interacts in Romanian)

> Executia acestor scripturi genereaza definitiile dorite in fereastra **Messages** din SSMS
> (langa fereastra Results, in partea de jos). Selecteaza tot textul din Messages (Ctrl+A),
> copiaza-l si salveaza-l intr-un fisier `.txt`. Ruleaza fiecare script separat si salveaza
> fiecare rezultat intr-un fisier distinct. Apoi furnizeaza fisierele sau continutul lor
> pentru a continua optimizarea.

---

## When to Ask the User to Run Which Scripts

### `export-tables.sql` — ask when:
- The query references tables or columns whose structure is unknown
- Type mismatches or implicit conversions are suspected
- The query has JOINs and selectivity order cannot be inferred with confidence
- The user reports unexpected results or plan regression

### `export-indexes.sql` — ask when:
- Index recommendations are requested
- The query filters on columns that may or may not be indexed
- Sargability issues are suspected (function wrapping, implicit conversions on filter columns)
- The optimizer needs to confirm whether a covering index already exists before suggesting one
- The user asks why a query is slow and no schema context has been provided

### `export-procs-and-functions.sql` — ask when:
- The query calls scalar UDFs or TVFs that may be executed per-row
- The query is a stored procedure that calls other procs or functions
- The user asks to review or optimize an existing proc/function by name
- A nested proc chain is suspected as a performance contributor

### Skip asking when:
- The query is simple (1–2 tables, obvious column names, no type ambiguity)
- The user has provided table definitions inline
- The user explicitly says SSMS access is unavailable
- The query is a PROCESIO inline variable query with no complex joins or unknown tables

### How to ask (example phrasing — adapt to context)

For table + index context:
> "To give you the most accurate optimization, I need the structure and index coverage of
> the tables involved. Could you run two scripts on the target database?
>
> 1. `export-tables.sql` → Messages tab → save to `tables.txt`
> 2. `export-indexes.sql` → Messages tab → save to `indexes.txt`
>
> Share both files here and I'll give you a full analysis including accurate index suggestions."

For proc/function context (add when relevant):
> "If the query references stored procedures or functions, also run
> `export-procs-and-functions.sql` the same way and save to `procs.txt`."

---

## How to Use the Schema Output Once Provided

### From `export-tables.sql`:
1. **Parse table definitions** — extract column names, data types, nullability, identity columns, computed columns
2. **Identify PKs, UQs, FKs** — use constraint definitions to infer join keys and referential integrity
3. **Check type alignment** — verify that parameter types in the query match actual column types; flag implicit conversions with specific column names and types
4. **Refine JOIN order** — use FK relationships to confirm parent/child table direction; use identity seed values as a rough row-volume proxy

### From `export-indexes.sql`:
5. **Verify index coverage** — check whether filter columns, join keys, and ORDER BY columns are covered
6. **Identify missing indexes** — when a filter column has no index and the table is large, propose a specific `CREATE INDEX` with key and INCLUDE columns based on the actual query shape
7. **Identify redundant indexes** — flag indexes whose key columns are a prefix of another index on the same table
8. **Assess filtered indexes** — check if existing filtered indexes align with the query's WHERE predicates; if so, note that the optimizer may use them
9. **Confirm covering indexes** — verify whether a proposed INCLUDE column already exists in an existing index before suggesting it

### From `export-procs-and-functions.sql`:
10. **Validate scalar UDF usage** — if a scalar UDF is called in WHERE or JOIN, flag it and suggest inlining
11. **Trace nested proc chains** — follow EXEC calls to understand execution depth and identify redundant round-trips
12. **Check for parameter sniffing risk** — review proc signatures for wide-range date or ID params on large tables

---

## Agentic Use (CoWork / Multi-skill Workflows)

In agentic environments where tools can execute SQL against a connected database (e.g.,
CoWork with a database connector skill):

- All three scripts can be executed directly without manual user intervention
- Run them at the start of any complex optimization session; parse results into context
- After schema is loaded, proceed with optimization without asking the user to provide it

Recommended execution order:
1. `export-tables.sql` — table structure and constraints; always run first
2. `export-indexes.sql` — run immediately after tables; together they give the full index picture
3. `export-procs-and-functions.sql` — run only if the query references existing procs/functions

Parse all outputs into an internal schema map. Use specific column types, constraint names, and
index definitions when writing Notes — replace generic guidance ("consider an index on this column")
with precise statements ("column `InvoiceDate` on `dbo.Invoices` has no covering index; consider
`CREATE NONCLUSTERED INDEX IX_Invoices_InvoiceDate ON dbo.Invoices (InvoiceDate) INCLUDE (CustomerId, Total)`").

---

## What the Scripts Cannot Export

- **Encrypted modules** — procs/functions created with `WITH ENCRYPTION` will show a NOTE instead of their definition
- **Server-level triggers** — included only if the executing user has `CONTROL SERVER` permission
- **Data** — these are schema-only exports; no row data is included
- **Statistics** — index statistics (row counts, density, histograms) are not exported; use `DBCC SHOW_STATISTICS` or `sys.dm_db_index_usage_stats` separately for deep performance diagnosis
