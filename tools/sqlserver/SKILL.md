---
name: sqlserver
description: Read-only SQL Server queries over pyodbc with named connection profiles. SELECT-only by default (--write to override); returns rows as JSON; schema/table introspection.
---

# sqlserver

Read-only SQL Server queries over pyodbc with named connection profiles. SELECT-only by default (--write to override); returns rows as JSON; schema/table introspection.

## How to call it

```bash
python scripts/run-tool.py sqlserver <action> [--args]
# e.g. sqlserver query --profile default --sql "SELECT TOP 10 * FROM dbo.Customer"
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

**Start with `query`.**

## Actions

| action | required args | what it does |
|---|---|---|
| `add-profile` | `--name`, `--server` | Store a connection profile (config only; set the password separately via set-credential). |
| `columns` | `--profile`, `--table` | List a table's columns (name, type, nullable, length, default). |
| `migrate` | `--profile` | List or apply versioned .sql migrations (forward-only; tracking table; apply gated behind --apply). list is read-only and the default. |
| `profiles` | — | List configured connection profiles (no passwords). |
| `query` | `--profile`, `--sql` | Run read-only SQL (SELECT by default; --write allows non-SELECT). Params bound via ? placeholders, never interpolated. |
| `schema-diff` | `--left`, `--right` | Diff two schema mirrors or live profiles (objects added/removed/changed + unified diffs). Read-only. |
| `schema-extract` | `--profile` | Mirror all DB objects to local .sql files (one per object; incremental; read-only). |
| `tables` | `--profile` | List tables and views, optionally restricted to one schema. |
| `test-connection` | `--profile` | Connect and return the masked connection string + server version (never the password). |

---

Generated from `tools/sqlserver/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
