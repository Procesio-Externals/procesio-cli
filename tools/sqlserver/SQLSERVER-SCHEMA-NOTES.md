# sqlserver — schema-extract / schema-diff / migrate notes

Durable learnings for the three schema actions added to the `sqlserver` tool.
Code: `tools/sqlserver/schema.py` (engine SQL + migrate engine), the actions in
`tools/sqlserver/main.py`, the shared pure core in `tools/_lib/dbschema.py`
(FROZEN — do not edit from the tool). Tests: `tests/test_sqlserver_schema.py`.

## Architecture (where the seams are)

- `tools/_lib/dbschema.py` is the **engine-agnostic, pure** core: `mirror_relpath`,
  `write_mirror` (incremental, manifest, `--full`, `--dry-run`), `diff_mirrors`,
  `discover_migrations`, `pending`, `danger_warnings`, `split_go_batches`,
  `sha256_file/_text`. A "record" is `{type, schema, name, definition}` where
  `type` is the **directory label** ("Procedures"/"Functions"/"Views"/"Triggers"/
  "Tables"), NOT the SQL Server type letter.
- `tools/sqlserver/schema.py` is the only driver-touching half: `extract_objects`,
  the table-DDL generator, and the migrate engine (`ensure_migrations_table`,
  `fetch_applied`, `record_applied`, `apply_migration_sql`).

## extract_objects

- Module objects (`P`, `FN`, `IF`, `TF`, `V`, `TR`) come **verbatim** from
  `sys.sql_modules.definition` via a single `LEFT JOIN sys.objects`. Encrypted
  (`WITH ENCRYPTION`) or permission-denied objects return a NULL body — we still
  emit a record, with a `-- NOTE: definition unavailable` placeholder, rather than
  dropping it silently.
- Bodies are normalised CRLF/CR → LF before hashing/writing. SQL Server returns
  CRLF; without normalising, Windows text-mode writes would double the CR
  (`\r\r\n`) and the manifest sha would never match disk → every run rewrites.
- Tables (`U`) have no stored CREATE text, so DDL is generated from the catalog
  (sys.columns/identity_columns/computed_columns/default_constraints, key_constraints
  PK, indexes, foreign_keys, check_constraints). Length types convert byte length →
  char count for `n*` types (`max_length // 2`); `-1` → `(MAX)`.
- **`--types` filters by object FAMILY, not sub-kind.** The on-disk label
  "Functions" maps to {FN, IF, TF}; you cannot ask for only inline TVFs. Asking for
  any one of a family's letters keeps the whole family. Documented in
  `schema._record_letters_wanted`.

## migrate engine

- Tracking table `dbo.__schema_migrations` (migration_id PK, filename, sha256,
  applied_at DEFAULT SYSUTCDATETIME(), applied_by DEFAULT SUSER_SNAME(),
  duration_ms, notes). Created idempotently via `IF NOT EXISTS` on first
  `fetch_applied`.
- `apply_migration_sql` wraps each file in an **explicit** `BEGIN TRANSACTION` /
  `COMMIT` (or `ROLLBACK` for dry-run / on error) because `connection.connect()`
  opens pyodbc with `autocommit=True`. This gives file-level atomicity AND a no-op
  validation mode without adding an autocommit=False connect path.
- `migrate --mode list` and the whole extract/diff surface are READ-ONLY.
  `--mode apply` is the only writer and REQUIRES `--apply` (UsageError otherwise);
  it refuses on drift (an applied file whose disk sha changed) unless
  `--accept-drift`. Pending applied in numeric order; stop on first error.

## Limitations / deferred (v1)

- GO-batch split (`dbschema.split_go_batches`) is line-based: a `GO` alone on a line
  **inside a string literal or block comment** is still treated as a separator.
  Documented; matches the pyodbc-only approach used elsewhere (no go-sqlcmd dependency).
- Exotic objects NOT extracted yet (port from a sibling extractor
  `DB_ringhel_DeployCenter/tools/extract.py` when needed): CLR assemblies,
  user-defined scalar/table/CLR types, authored schemas (CREATE SCHEMA),
  database-scope DDL triggers (parent_class=0), partitioning/filegroups/XML schema
  collections/full-text, sequences, synonyms, Service Broker, extended properties.
- No down/rollback migrations — write a new forward migration to reverse.

## Testing

- All unit tests use FAKE cursors/connections — no live DB, no pyodbc. The
  `FakeCursor` in `test_sqlserver_schema.py` replays a QUEUE of (description, rows)
  results across `execute()` calls, because `schema._emit_table` reuses one cursor
  for five sequential queries (columns → pk → index → fk → check).
- `migrate` apply was NEVER run against a live DB during development (spec safety
  rule). Live extract/diff is safe via read-only profiles only.
- `dispatch` injects `conn_factory`; `schema-diff` is `needs_conn=False` and gets
  the factory passed through specially (it opens its own per-side connections).

## Field learnings (first live migrate run — chatbotai W1, 2026-07-02)

- **`THROW` in migration-applied proc bodies needs `;THROW;`** — a THROW following
  `END` (or any unterminated statement) fails the batch with "Incorrect syntax near
  'THROW'". Always write `;THROW;`, and wrap a bare `IF … THROW` in
  `BEGIN ;THROW; END`.
- **Apply one file at a time when needed** (e.g. heap→clustered conversions with
  row-count checks between): the runner applies ALL pending in order, but applied
  state is keyed by `migration_id` + sha256 in `dbo.__schema_migrations`, NOT by
  directory — so copy files one-by-one into a staging dir, `migrate --dir <staging>
  --apply` per file, then point back at the real dir; identical files show as
  already applied.
- **`query` needs `--write` to EXEC even read-only procs** — the read-only guard is
  keyword-based and `EXEC` is on the write list.
- `migrate` ignores subdirectories and non-`NNNN_*.sql` files inside `--dir`
  (an `evidence/` subfolder and a `W1-REPORT.md` coexist fine; not even listed in
  `skipped_files`).

## Field learnings (multi-database sync, 2026-10)

- **`migrate --mode list` and `--dry-run` are not fully read-only:** both create
  `dbo.__schema_migrations` on first contact (via `fetch_applied`). Expect that table
  to appear in every database you only inspected.
- **`--dry-run` doubles as a behaviour test harness.** Append assertion batches after
  the migration (old-style calls, new parameters, expected rows; `;THROW` on any
  mismatch) and dry-run the combined file: the change plus the proof run in one
  transaction and are rolled back. `query` returns only the first result that has
  columns, so capture procedure output with `INSERT @t EXEC ...` instead of letting
  it print. Prove the assertions are live with a negative control (see below).
- **An `ALTER COLUMN ... WITH (ONLINE = ON)` must be the first operation of its
  transaction** when the table's clustered index carries a LOB column (`nvarchar(max)`
  etc.); otherwise SQL Server raises error 10635. Since `migrate` wraps a file in one
  transaction, put the online ALTER alone in its own `NNNN_*.sql`, and put any
  `DROP STATISTICS` it needs (a type change fails while column statistics exist) in an
  EARLIER file. The failure is conditional: it only appears where statistics exist on
  the column, so the same file can pass on one database and fail on the next.
- **Online vs offline size-of-data changes:** widening a column on a ~350k-row table
  took ~220 s ONLINE (table usable throughout) versus ~30-40 s offline under a
  schema-modification lock that blocks every reader, `READ UNCOMMITTED` included.
  On a live table prefer ONLINE, as its own file.
- **Comparing databases:** compare tables from the catalog (name-independent), not
  from generated DDL, or auto-named constraints (`DF__Tbl__col__1A2B3C`) show up as
  differences. Respect the database collation (a `_CI_` collation makes `Id` and
  `id` the same column), and leave out automatic-tuning indexes (`nci_msft_*`,
  `nci_wi_*`), which are per-database workload artefacts.

## Field learnings (errors after a row count, wide changes on busy tables, 2026-10)

- **Every `execute` is drained (`dbquery.drain_results`).** SQL Server sends a batch's
  results in order and pyodbc raises a statement's error only when the cursor reaches it
  with `nextset()`. Before the drain, a statement that failed after one that returned
  "N rows affected" was silently lost: in `migrate`, `XACT_ABORT` rolled the file back on
  the server while the tool committed nothing, reported the file as applied and recorded
  it in `dbo.__schema_migrations`; in a `--dry-run` test, every `;THROW` that followed an
  INSERT never fired, so the test passed whatever the data said. The error surfaces as
  `... (SQLMoreResults)`. A test fake without `nextset()` cannot show this, so the tests
  use a multi-result fake that raises from `nextset()`.
- **Run a negative control for every assertion file.** Dry-run the assertions without
  the change and require them to fail. That is how the swallowed errors were found: an
  assertion file that passed with and without the change it was meant to prove.
- **`query --write` returns the first result that has columns**, stepping past
  row-count-only results, so a multi-statement batch without `SET NOCOUNT ON` still
  returns its final SELECT (before, it returned nothing).
- **`max_length` in `sys.columns` and `sys.parameters` is in bytes**: `nvarchar(100)`
  reports 200. Read it as characters and a too-narrow parameter looks wide enough.
- **A parameter and an `OPENJSON ... WITH` column cut a longer string without an error**;
  only an INSERT or UPDATE into a narrower column raises (2628, "String or binary data
  would be truncated"). Widen a column together with every parameter, variable and
  OPENJSON column that carries its value, or the value is still cut, silently. Find them
  in `sys.parameters` and by scanning `OBJECT_DEFINITION` for the column's names next to
  a declared length.
- **Growing a varchar/nvarchar within the same type is a metadata change**, also when
  the column is in nonclustered indexes: a few milliseconds per column on a table with
  about a million rows. A type change (varchar to nvarchar) rewrites every row.
- **Order a migration so the table lock comes last.** `ALTER TABLE` holds a schema
  lock that blocks every reader, `READ UNCOMMITTED` included, until COMMIT. Put the
  `ALTER PROCEDURE` batches first and the column changes just before the final check:
  the tables are then held for milliseconds, and only callers of the altered procedures
  wait while they recompile.
- **A dry-run test holds every lock it takes until the rollback.** Calling procedures
  inside it on large tables with a cold cache once held four busy tables for about
  50 seconds. On large production databases, keep the dry-run to schema assertions and
  run the procedure calls in the post-apply check, which alters nothing and so locks
  only its own test rows. `SET LOCK_TIMEOUT` makes a busy object fail the file fast
  instead of queueing the application behind it; rerun later.
- **Guard each `ALTER PROCEDURE` with the procedure's `modify_date`** as read when the
  migration was built (`CONVERT(varchar(23), modify_date, 121)`), and `;THROW` if it
  moved: a procedure changed by someone in between is rebuilt from the new text, never
  overwritten.
