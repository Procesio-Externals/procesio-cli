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
