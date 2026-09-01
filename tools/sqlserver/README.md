# sqlserver

Read-only **SQL Server** queries over `pyodbc`, with named connection profiles.
SELECT-only by default; `--write` is required (and gated by the shared guard)
for any non-SELECT. JSON in / JSON out, like every tool here.

## Credentials (the model)

A profile splits into two halves:

- **Non-secret config** (server, database, username, driver, port, TLS flags,
  timeouts) lives in `tools/sqlserver/profiles.json`. Never a password.
- **The password** lives ONLY in Windows Credential Manager, under the target
  `agents-and-tools:sqlserver:<profile-name>` — the secret name **is** the
  profile name. Read at runtime via `creds.get("sqlserver", <profile>)`.

For a profile named `default`, set its password with:

```powershell
python scripts/set-credential.py sqlserver default
```

If it's missing, DB actions fail with code `auth_required` and that exact hint.

## Actions

```powershell
# List profiles (no passwords). Works with no DB and no driver installed.
python scripts/run-tool.py sqlserver profiles

# Add a profile (config only — password set separately, see above).
python scripts/run-tool.py sqlserver add-profile `
  --name default --server myhost.database.windows.net `
  --database DeployCenter --username ringhelteam

# Connectivity check: masked connection string + server version (never the password).
python scripts/run-tool.py sqlserver test-connection --profile default

# Read-only query. Params are bound via ? placeholders, never interpolated.
python scripts/run-tool.py sqlserver query --profile default `
  --sql "SELECT TOP 10 * FROM dbo.Customer WHERE City = ?" --params '["Cluj"]'

# A write needs the explicit flag (still gated, still parameterised):
python scripts/run-tool.py sqlserver query --profile default `
  --sql "UPDATE dbo.Flag SET on=1 WHERE id=?" --params '[7]' --write

# Line endings in --sql are normalized to CRLF before execution (reported as
# "eol_normalized": true). This keeps CREATE/ALTER PROCEDURE|VIEW|FUNCTION|
# TRIGGER definitions internally consistent so SSMS never shows its
# "Inconsistent Line Endings" prompt when the object is scripted out. Pass
# --no-normalize-eol only if you must preserve a bare LF inside a string
# literal (param values are bound separately and are never touched).

# Schema introspection.
python scripts/run-tool.py sqlserver tables  --profile default --schema dbo
python scripts/run-tool.py sqlserver columns --profile default --table dbo.Customer
```

## Schema mirror, diff & migrations

Three actions built on the shared, engine-agnostic core in `tools/_lib/dbschema.py`.
`schema-extract`, `schema-diff`, and `migrate --mode list` are **read-only**;
`migrate --mode apply` is the only writer and is gated behind `--apply`.

### `schema-extract` — mirror every object to local `.sql` files

Writes one `.sql` file per object under `<out>/schema/<Type>/<schema>.<name>.sql`,
plus a `_manifest.json` of relpath→sha256. Incremental by default (a second run
with no schema change writes 0 files); `--full` wipes and re-extracts.

```powershell
# Mirror a whole DB (default out: ./db-mirror/<profile>)
python scripts/run-tool.py sqlserver schema-extract --profile deploycenter

# Pick a specific DB on a server profile, only some object families, dry-run
python scripts/run-tool.py sqlserver schema-extract --profile prod --database fee_dev `
  --types P,V,FN,U --out ./db-mirror/fee_dev --dry-run
```

Module objects (procedures `P`, functions `FN`/`IF`/`TF`, views `V`, DML triggers
`TR`) are captured **verbatim** from `sys.sql_modules.definition`. Tables (`U`) get
`CREATE TABLE` DDL generated from the catalog (columns/types/nullability/identity/
defaults/collation/computed, primary key, foreign keys, non-PK indexes, check
constraints). `--types` filters by object **family** — e.g. `--types FN` keeps the
whole Functions family (scalar + inline + table-valued), since the on-disk label
does not distinguish them. Output: `{profile, database, out, written, unchanged,
removed, total, by_type, dry_run}`.

### `schema-diff` — compare two mirrors or two live DBs

Each side is either an existing mirror **directory** or `profile:NAME` (extracted to
a temp mirror on the fly, with an optional `--database-*` override). Returns objects
added (only on the right) / removed (only on the left) / changed (with a unified
diff per object). `--no-diff-text` keeps just the name lists.

```powershell
# Two already-extracted mirrors
python scripts/run-tool.py sqlserver schema-diff --left ./db-mirror/fee_dev --right ./db-mirror/fee_release

# Two live DBs on the same server profile, names only (no diff bodies)
python scripts/run-tool.py sqlserver schema-diff `
  --left profile:fee_dev --right profile:fee_release --no-diff-text
```

### `migrate` — forward-only versioned migration runner

Applies pending `NNNN_<slug>.sql` files in numeric order, tracking applied state in
`dbo.__schema_migrations` (created on first run). `--mode list` (default, read-only)
shows applied vs pending, flags **drift** (an applied file whose sha256 changed on
disk), and surfaces danger warnings (DROP/TRUNCATE, unqualified UPDATE/DELETE) per
pending file. `--mode apply` **writes** and therefore requires an explicit `--apply`;
it refuses to run on drift unless `--accept-drift`, applies pending in order (each
file in one transaction, GO batches split), records a tracking row on success, and
stops on the first error.

```powershell
# Safe default: see what's applied vs pending (read-only)
python scripts/run-tool.py sqlserver migrate --profile sandbox --dir ./db-migrations/sandbox

# Validate without persisting — each file runs in a rolled-back transaction
python scripts/run-tool.py sqlserver migrate --profile sandbox --mode apply --apply --dry-run

# Actually apply (writes). --apply is mandatory; never run against production casually.
python scripts/run-tool.py sqlserver migrate --profile sandbox --mode apply --apply
```

**Deferred / limitations (v1):** exotic objects are NOT yet extracted — CLR
assemblies, user-defined scalar/table/CLR types, authored schemas, database-scope
DDL triggers, partitioning/filegroups/XML schema collections/full-text, sequences,
synonyms, Service Broker, extended properties (port from a sibling schema extractor when
needed). GO-batch splitting is line-based: a `GO` alone on a line **inside** a string
literal or block comment is still treated as a batch separator. No down/rollback
migrations (write a new forward migration to reverse).

## Multiple databases (one profile, many DBs)

`--database` is **optional** on a profile, so a profile can be just a server + login
(one credential) and you pick the database per call:

```powershell
# One profile for the whole instance (no --database)...
python scripts/run-tool.py sqlserver add-profile --name prod --server myhost --username ringhelteam
python scripts/set-credential.py sqlserver prod

# ...then target any database on it per call:
python scripts/run-tool.py sqlserver query   --profile prod --database DeployCenter --sql "SELECT TOP 5 * FROM dbo.Customer"
python scripts/run-tool.py sqlserver tables  --profile prod --database FEE
python scripts/run-tool.py sqlserver columns --profile prod --database FEE --table dbo.Invoice
```

`--database` overrides the profile's default for that one call (SQL Server connects
straight to that DB — no `USE`, which the read-only guard blocks anyway). Omit it to
use the profile's `--database`, or the login's default DB if the profile has none.
Prefer one named profile per database instead? That still works — both styles are fine.

## add-profile options

| flag | default | notes |
|------|---------|-------|
| `--name` | — (required) | profile + credential name |
| `--server` | — (required) | `host`, `host\instance`, or fqdn |
| `--database` | login default | optional — one profile can serve many DBs; override per call with `query/tables/columns --database` |
| `--username` | trusted conn | omit for a Windows/trusted connection |
| `--port` | — | appended as `server,port` |
| `--driver` | newest installed `ODBC Driver … for SQL Server` | auto-detected via `pyodbc.drivers()`; pass one to pin it |
| `--encrypt` | `yes` | `yes`/`no` |
| `--trust-server-certificate` | `no` | `yes`/`no` (self-signed/on-prem) |
| `--connect-timeout` | `30` | seconds |
| `--statement-timeout` | `300` | seconds, `0` = unbounded |
| `--overwrite` | off | replace an existing profile |

## Safety

- **Read-only by default** — `INSERT/UPDATE/DELETE/MERGE/TRUNCATE/ALTER/CREATE/
  DROP/GRANT/EXEC/CALL/…` and multi-statement batches are rejected unless
  `--write` is passed. The guard lives in `tools/_lib/dbquery.py`.
- Read-only profiles also add `ApplicationIntent=ReadOnly`; pair with a
  dedicated read-only SQL login for defence in depth.
- Values are always **parameterised** (`?`), never spliced into the SQL.
- A **max-rows cap** (`--max-rows`, default 1000) returns a `truncated` flag.
- The connection string is **masked** (`PWD=***`) everywhere it surfaces.

## Dependencies

`pyodbc` + a Microsoft ODBC Driver for SQL Server (17 or 18). Imported lazily —
if absent, DB actions fail with `missing_dependency` and an install hint;
`profiles` / `add-profile` keep working.

## Errors

`invalid_argument` (2), `auth_required`, `write_blocked` (2),
`missing_dependency`, `db_error`, `error`.
