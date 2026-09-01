# mysql

Read-only **MySQL / MariaDB** queries over `pymysql`, with named connection
profiles. SELECT-only by default; `--write` is required (and gated by the shared
guard) for any non-SELECT. JSON in / JSON out.

> MySQL has no `ApplicationIntent=ReadOnly` equivalent, so for this engine the
> **write-guard is the read-only enforcement**. Its keyword list is the superset
> of both engines (adds `REPLACE`, `CALL`, `LOAD`, `LOCK`, `RENAME`, …).

## Credentials (the model)

A profile splits into two halves:

- **Non-secret config** (host, database, username, port, charset, TLS flags,
  timeouts) lives in `tools/mysql/profiles.json`. Never a password.
- **The password** lives ONLY in Windows Credential Manager, under the target
  `agents-and-tools:mysql:<profile-name>` — the secret name **is** the profile
  name. Read at runtime via `creds.get("mysql", <profile>)`.

For a profile named `default`, set its password with:

```powershell
python scripts/set-credential.py mysql default
```

If it's missing, DB actions fail with code `auth_required` and that exact hint.

## Actions

```powershell
# List profiles (no passwords). Works with no DB and no driver installed.
python scripts/run-tool.py mysql profiles

# Add a profile (config only — password set separately, see above).
python scripts/run-tool.py mysql add-profile `
  --name default --host 10.0.0.5 --database redmine --username readonly --tls yes

# Connectivity check: masked DSN + server version (never the password).
python scripts/run-tool.py mysql test-connection --profile default

# Read-only query. Params are bound via %s placeholders, never interpolated.
python scripts/run-tool.py mysql query --profile default `
  --sql "SELECT * FROM issues WHERE project_id = %s LIMIT 10" --params '[3]'

# A write needs the explicit flag (still gated, still parameterised):
python scripts/run-tool.py mysql query --profile default `
  --sql "DELETE FROM cache WHERE id = %s" --params '[7]' --write

# Schema introspection (defaults to the profile's database).
python scripts/run-tool.py mysql tables  --profile default
python scripts/run-tool.py mysql columns --profile default --table issues
```

## Multiple databases (one profile, many DBs)

`--database` is just the **default schema** and is optional — one profile (one host +
login + credential) already reaches every database on the host. Pick one per call:

```powershell
python scripts/run-tool.py mysql query   --profile prod --database redmine   --sql "SELECT * FROM issues LIMIT 5"
python scripts/run-tool.py mysql tables  --profile prod --database wordpress
python scripts/run-tool.py mysql columns --profile prod --database wordpress --table wp_posts
```

`--database` sets the connection's default schema for that call, so `tables`/`columns`
introspect it and unqualified names resolve to it. You can also reach another schema
inline with a qualified name (`SELECT * FROM otherdb.t`) if the login has grants.
Prefer one named profile per database? That works too — both styles are fine.

## Schema mirror, diff & migrations

Three actions extend the tool from "query a DB" to "version a DB's schema". They
share the engine-agnostic machinery in `tools/_lib/dbschema.py`; the MySQL-specific
half (catalog enumeration, `SHOW CREATE`, the `__schema_migrations` table) lives in
`tools/mysql/schema.py`.

### `schema-extract` — mirror every object to local `.sql` files (read-only)

Writes one file per object under `<out>/schema/<Type>/<schema>.<name>.sql` plus a
`_manifest.json` of `relpath -> sha256`. **Incremental** by default — a re-run with no
schema changes writes nothing. Read-only (only `SELECT` / `SHOW CREATE`).

```powershell
# Mirror the profile's database to ./db-mirror/<profile>/
python scripts/run-tool.py mysql schema-extract --profile default

# Pick a database, a subset of object types, and a custom output dir.
python scripts/run-tool.py mysql schema-extract --profile prod `
  --database redmine --types TABLE,VIEW,PROCEDURE --out .\mirrors\redmine

# See what would change without touching disk.
python scripts/run-tool.py mysql schema-extract --profile default --dry-run

# Force a clean re-extract.
python scripts/run-tool.py mysql schema-extract --profile default --full
```

`--types` accepts any of `TABLE,VIEW,PROCEDURE,FUNCTION,TRIGGER,EVENT`. Returns
`{profile, database, out, written, unchanged, removed, total, by_type, dry_run}`.

### `schema-diff` — compare two schema sides (read-only)

Each side is **either** a mirror directory **or** `profile:NAME` (extracted live to a
temp mirror first). Reports objects added / removed / changed, with a unified diff per
change (suppress bodies with `--no-diff-text`).

```powershell
# Two already-extracted mirrors.
python scripts/run-tool.py mysql schema-diff --left .\mirrors\dev --right .\mirrors\rel

# Live: same profile, two databases on the host.
python scripts/run-tool.py mysql schema-diff `
  --left profile:prod --database-left app_dev `
  --right profile:prod --database-right app_release

# Just the changed/added/removed name lists (no diff bodies).
python scripts/run-tool.py mysql schema-diff --left .\a --right .\b --no-diff-text
```

Returns `{left, right, added[], removed[], changed[{relpath, diff}], unchanged,
identical, summary}`. Read-only end to end.

### `migrate` — forward-only versioned migration runner

Applies pending `NNNN_<slug>.sql` files in numeric order, tracking applied state in a
`__schema_migrations` table inside the target DB. `list` (the default) is read-only;
`apply` is the **only writer** and is gated behind `--apply`.

```powershell
# List applied vs pending + drift + danger warnings (read-only).
python scripts/run-tool.py mysql migrate --profile default --dir .\db-migrations\app

# Validate without persisting: each migration runs in a rolled-back transaction.
python scripts/run-tool.py mysql migrate --profile default --dir .\db-migrations\app `
  --mode apply --apply --dry-run

# Actually apply pending migrations (requires --apply).
python scripts/run-tool.py mysql migrate --profile default --dir .\db-migrations\app `
  --mode apply --apply
```

- Default `--dir` is `./db-migrations/<profile>`.
- `apply` **refuses to run on drift** (an applied migration whose file `sha256` changed
  on disk) unless `--accept-drift` is passed.
- Each file runs in its own transaction; the runner **stops on the first error**.
- `danger_warnings` (DROP/TRUNCATE TABLE, unqualified UPDATE/DELETE) are surfaced per
  pending file but do **not** block.

**DELIMITER / multi-statement caveat (important):** MySQL stored-routine bodies contain
semicolons, so a migration file is executed as a **single statement** — there is no
client-side `;`-splitting and no `DELIMITER` handling. Author each migration as **one
statement per file** (e.g. a single `CREATE PROCEDURE ... BEGIN ... END` with **no**
`DELIMITER` lines, or one plain DDL statement). Files with several `;`-separated plain
statements, or `DELIMITER`-wrapped bodies, are **not** supported in one file. (`GO`
batch-splitting is SQL-Server-only and is not used here.)

> **Safety:** `schema-extract`, `schema-diff`, and `migrate --mode list` are read-only.
> `migrate --mode apply` is the only write path and requires the explicit `--apply` flag.

## add-profile options

| flag | default | notes |
|------|---------|-------|
| `--name` | — (required) | profile + credential name |
| `--host` | — (required) | |
| `--database` | login default | default schema (optional); override per call with `query/tables/columns --database` |
| `--username` | `root` | |
| `--port` | `3306` | |
| `--charset` | `utf8mb4` | |
| `--tls` | `no` | `yes`/`no` — wrap the socket in TLS |
| `--tls-verify-cert` | `no` | `yes`/`no` — verify the server cert chain |
| `--connect-timeout` | `30` | seconds |
| `--statement-timeout` | `300` | read timeout, seconds, `0` = unbounded |
| `--overwrite` | off | replace an existing profile |

## Safety

- **Read-only by default** — `INSERT/UPDATE/DELETE/REPLACE/MERGE/TRUNCATE/ALTER/
  CREATE/DROP/GRANT/CALL/LOAD/LOCK/…` and multi-statement batches are rejected
  unless `--write` is passed. The guard lives in `tools/_lib/dbquery.py`.
- Values are always **parameterised** (`%s`), never spliced into the SQL.
- A **max-rows cap** (`--max-rows`, default 1000) returns a `truncated` flag.
- TLS without cert-verification encrypts the channel for IP-only hosts (the
  SQL-Server `TrustServerCertificate=yes` analogue).

## Dependencies

`pymysql` + `cryptography` (the latter for MySQL 8 `caching_sha2_password`).
Imported lazily — if absent, DB actions fail with `missing_dependency`;
`profiles` / `add-profile` keep working.

## Errors

`invalid_argument` (2), `auth_required`, `write_blocked` (2),
`missing_dependency`, `db_error`, `error`.
