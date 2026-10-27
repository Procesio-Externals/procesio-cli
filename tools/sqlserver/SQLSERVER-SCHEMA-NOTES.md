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

## Field learnings (deadlocks and catch-all predicates, 2026-10)

- **Azure SQL keeps every deadlock graph for about a month**, readable from `master`:
  `SELECT event_data FROM sys.fn_xe_telemetry_blob_target_read_file('dl', NULL, NULL, NULL)`
  (one `xml_deadlock_report` per row, with `database_name`), and per-database counts in
  `master.sys.event_log WHERE event_type = 'deadlock'`. Both lag by tens of minutes. Group the
  graphs by database, then by the statements in `executionStack/frame` (for ad-hoc batches the
  frame is `unknown`: read `inputbuf` and the frame's line number).
- **`exchangeEvent` + `pagelock` among the resources = an intra-query parallelism deadlock**: the
  threads of ONE parallel scan blocking each other, not two clients. The cure is to stop the
  scan (seekable predicate, index), not to retry or serialize callers.
- **A catch-all predicate on a variable defeats the index**: `WHERE id = @id AND (@flag = 1 OR
  CUI = @CUI)` cannot seek on `(CUI, id)`, because one cached plan must serve both values of
  `@flag`. Split it into `IF @flag = 1 <statement A> ELSE <statement B>`: each branch gets its
  own seekable plan and the behaviour is identical. Seen as ~20k reads and 0.8 s per call
  dropping to 3-50 reads and 0 ms. The same applies to `(@p IS NULL OR col = @p)` filters.
- **An nvarchar column compared with a numeric literal is converted, row by row**
  (`CONVERT_IMPLICIT(bigint, col)`), so its index is unusable and the statement scans. Fix it
  at the caller (`= N'123'` or a typed nvarchar parameter). An index on a computed
  `CONVERT(bigint, col)` would match it but makes every non-numeric value fail on insert.
- **Query Store hints need a stable `query_id`.** An ad-hoc statement with literals gets a new
  `query_id` per value (check `sys.query_store_query_text`), so no hint can target it.
- **`READ UNCOMMITTED` switches off lock-after-qualification** even when optimized locking and
  RCSI are on: an UPDATE then holds U locks while it qualifies rows, which is what point
  updates of the same pages deadlock against.
- **Ranking a shared elastic pool:** `master.sys.resource_stats` (5-minute samples, 14 days) per
  database shows who consumes the pool; then Query Store per database
  (`sys.query_store_runtime_stats` x `count_executions`) for the top statements, including
  `count_compiles` and `avg_compile_duration`, which expose procedures that recompile on every
  statistics update.
- **A range on ISNULL bounds is NOT a reliable fix for a catch-all filter.**
  `id BETWEEN ISNULL(@id, MIN) AND ISNULL(@id, MAX)` returns the right rows, but the cached plan
  is compiled for whichever call came first: compiled for the NULL (batch) case it scans, and every
  single-row call then scans too (seen: ~5k reads became ~25k). Two statements under
  `IF @id IS NOT NULL ... ELSE ...` are the plan-stable form. Measure the deployed plan, not the idea.
- **Prove an equivalence before shipping a performance change:** run the current object and a
  temporary copy (`CREATE PROCEDURE #name_new ...`, built from the live definition) with the same
  parameters on real data and compare the rows, inside a transaction you roll back when the object
  writes. Rows that differ only because production wrote between the two runs show up as
  "old == old2 == new" on an old/new/old rerun.
- **`OPTION (RECOMPILE)` on a list query with many optional filters** lets the optimizer drop the
  unused ones (seen: 3.25M -> 84k reads for one page). It costs a compile per call, which on a
  near-empty database can exceed the query itself; worth it only where the data is large.

## Field learnings (index parity across databases that share one code base, 2026-10)

- **Azure automatic tuning creates and drops indexes per database** (`CREATE_INDEX` / `DROP_INDEX`
  in `sys.database_automatic_tuning_options`; names `nci_msft_*`, `nci_wi_*`). Databases that run the
  same procedures therefore drift: the same query seeks in one and scans in another. Make every
  index the code relies on an explicit, named index in the reference database and propagate it like
  any other schema change; keep automatic tuning as a source of suggestions.
- **Adopt instead of rebuilding:** where an automatic-tuning index already has exactly the wanted
  keys and included columns, `EXEC sp_rename 'dbo.T.nci_msft_...', 'IX_...', 'INDEX'` is instant;
  build only where it is missing. Copy the canonical definition from the most-used existing one, so
  the big databases mostly rename.
- **ONLINE index builds through `migrate`:** one index per file (each file is one transaction, and the
  build's final schema lock is held until COMMIT), `WITH (ONLINE = ON (WAIT_AT_LOW_PRIORITY
  (MAX_DURATION = 1 MINUTES, ABORT_AFTER_WAIT = SELF)))` works inside that transaction, and a
  multi-gigabyte build outlasts the profile's 300 s statement timeout: run `main.dispatch("migrate",
  ..., conn_factory=...)` in-process with `statement_timeout: 0` instead of copying the credential
  into a second profile.
- **A self-check inside a migration must not match its own comments:** a `LIKE '%pattern%'` or an
  occurrence count over `OBJECT_DEFINITION` also sees the header comment the migration added.
  Match the exact old predicate or keep the phrase out of the comment.

## Field learnings (byte-identical modules and type changes across databases, 2026-10)

- **`migrate` stores modules with the file's line endings.** It CRLF-normalizes each file, and
  `split_go_batches` now keeps each line's own ending. Before that fix it rejoined lines with "\n",
  so every module deployed through `migrate` was stored LF-only next to CRLF originals, and SSMS
  reported "Inconsistent Line Endings" on script-out. Normalizing an existing module to CRLF is safe
  only when no string literal in it spans lines (check before re-deploying).
- **Prove text alignment by hash:** `CONVERT(varchar(64), HASHBYTES('SHA2_256', OBJECT_DEFINITION(OBJECT_ID('dbo.X'))), 2)`
  equals the SHA-256 of the canonical text encoded UTF-16LE. SQL Server stores an `ALTER PROCEDURE/FUNCTION`
  back as `CREATE ...`, so the hash of the CREATE text matches after an ALTER. A one-space change fails it.
- **A function called by a DEFAULT constraint cannot be altered** (error 3729, "Cannot ALTER ... because it
  is being referenced by object 'DF_...'"): drop the default, ALTER the function, re-create the default
  with the same name and definition, all in one transaction.
- **A type change on a column (varchar -> nvarchar, bigint -> int, nvarchar(max) -> datetime) is blocked
  by the indexes and the DEFAULT on it.** Capture their exact definitions from the catalog, drop them,
  ALTER COLUMN, re-create them; a length-only change of the same type is not blocked by a default.
  Without dependents on a big table, do it ONLINE: one file that drops the column's statistics, a
  second file with the ONLINE ALTER COLUMN alone (first operation of its transaction).
- **ALTER COLUMN never truncates on a type change:** a value that does not fit the new type (non-numeric
  text to int, bigint above the int range, an unparsable date) stops the statement with an error. Check
  the data first with TRY_CONVERT and fill NULLs from their source column before making it NOT NULL.
- **Stopping a parallel-scan deadlock from a caller you cannot change.** An ad-hoc statement sent with
  literals (`WHERE message_id = 8641686710` on an nvarchar column) is neither seekable (the column gets
  converted) nor parameterized (`query_parameterization_type_desc = None`, one Query Store query per
  value, same `query_hash`), so a Query Store hint has no stable query_id to attach to. Two plan guides on
  the statement's template do it: `sp_get_query_template` on one sample, then a `TEMPLATE` guide with
  `OPTION (PARAMETERIZATION FORCED)` and a `SQL` guide on the same parameterized text and `@params` with
  `OPTION (MAXDOP 1)`. Serial scans of one plan lock pages in the same order, so concurrent copies block
  briefly instead of deadlocking (`exchangeEvent` + `pagelock` in the graph). Forced parameterization
  types an integer literal in a comparison above the int range as `numeric(38,0)` and a string literal as
  `varchar(8000)`, so the template is stable across values. Verify on the cached `Prepared` plan:
  `PlanGuideName="<sql guide>"` and `NonParallelPlanReason="MaxDOPSetToOne"`; the ad-hoc entry shows
  `TemplatePlanGuideName`. It is a mitigation: the statement still scans until the caller sends a typed
  value, and once it does the guides simply stop matching.
- **The tracking table follows the same rule.** `dbo.__schema_migrations` is now created with
  `migration_id nvarchar(200)` under `PK___schema_migrations` and `sha256 nchar(64)`. Older copies
  have `varchar(200)` / `char(64)` and a system-named PK (`PK____schema__<hash>`, different in every
  database). Convert them with a migration: drop the PK found in `sys.key_constraints`, ALTER both
  columns, re-add the named PK. `EXEC (...)` only concatenates literals and variables, so build the
  DROP into a variable first (`EXEC (N'...' + QUOTENAME(@pk))` is a syntax error, 102).
- **Error 689 after an ONLINE ALTER COLUMN:** the online rebuild leaves cleanup work on the table, and an
  OFFLINE change to another column of the same table right after it fails with 689 until the cleanup
  finishes. Order each table's changes offline first, online last, and let the runner wait ~30 s and
  resume (the migration that failed was rolled back and is still pending) if it happens anyway.
- **A column with a DEFAULT on a busy, large table** (a queue that takes inserts all day): the offline path
  (drop default, ALTER, re-add) holds a schema lock for the whole rewrite, long enough to time out the
  application's 30 s commands. Three files instead: (1) drop the default, guarded by a THROW if the column
  holds NULLs; (2) the ONLINE ALTER COLUMN alone; (3) re-add the default under its canonical name and set
  `col = <default>` WHERE col IS NULL, which catches any row inserted between (1) and (3) without it.
  Only for a NULLable column (a NOT NULL one rejects those inserts while the default is gone); a reader
  that polls for the default value sees those rows only after step (3), a delay of the ALTER's duration.
  The steps depend on each other, so this path cannot be dry-run as a whole: prove it with a real apply on
  a test database that has the same shape before running it on production.
