---
name: mysql
description: Read-only MySQL/MariaDB queries over pymysql with named connection profiles. SELECT-only by default (--write to override); returns rows as JSON; schema/table introspection. MySQL has no read-only intent, so the write-guard is the enforcement.
---

# mysql

Read-only MySQL/MariaDB queries over pymysql with named connection profiles. SELECT-only by default (--write to override); returns rows as JSON; schema/table introspection. MySQL has no read-only intent, so the write-guard is the enforcement.

## How to call it

```bash
python scripts/run-tool.py mysql <action> [--args]
# e.g. mysql query --profile default --sql "SELECT * FROM issues LIMIT 10"
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

**Start with `query`.**

## Actions

| action | required args | what it does |
|---|---|---|
| `add-profile` | `--name`, `--host` | Store a connection profile (config only; set the password separately via set-credential). |
| `columns` | `--profile`, `--table` | List a table's columns (name, type, nullable, key, length, default). |
| `migrate` | `--profile` | Forward-only versioned migration runner. mode=list (default, read-only) shows applied/pending + drift + danger warnings; mode=apply (gated by --apply) runs… |
| `profiles` | — | List configured connection profiles (no passwords). |
| `query` | `--profile`, `--sql` | Run read-only SQL (SELECT by default; --write allows non-SELECT). Params bound via %s placeholders, never interpolated. |
| `schema-diff` | `--left`, `--right` | Compare two schema sides and report objects added/removed/changed with a unified diff per change. Each side is a mirror directory OR profile:NAME (extracted… |
| `schema-extract` | `--profile` | Mirror every object in the database to local .sql files (one per object) under <out>/schema/<Type>/. Read-only and incremental: a re-run with no changes writes… |
| `tables` | `--profile` | List tables and views, optionally restricted to one schema. |
| `test-connection` | `--profile` | Connect and return the masked connection string + server version (never the password). |

---

Generated from `tools/mysql/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
