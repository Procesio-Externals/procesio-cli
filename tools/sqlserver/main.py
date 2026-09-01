"""sqlserver tool entrypoint - read-only SQL Server queries over pyodbc.

Action-dispatched, JSON in / JSON out. READ-ONLY BY DEFAULT: any non-SELECT
statement (or a multi-statement batch) is rejected by the shared write-guard
unless ``--write`` is passed. Connection details live in named profiles
(profiles.json); the password lives ONLY in Windows Credential Manager under
``agents-and-tools:sqlserver:<profile>``.

Actions:
  profiles
  add-profile     --name --server --database [--username --port --driver ...]
  test-connection --profile
  query           --profile --sql [--params JSON] [--max-rows N] [--write]
  tables          --profile [--schema]
  columns         --profile --table
  schema-extract  --profile [--database --out --types --full --dry-run]
  schema-diff     --left --right [--database-left --database-right --types --no-diff-text]
  migrate         --profile [--database --dir --mode --dry-run --apply --accept-drift]
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = TOOL_ROOT.parents[1]
_VENV_PY = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import argparse  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from typing import Callable  # noqa: E402

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from tools._lib import dbquery, dbschema, userdata  # noqa: E402
from tools._lib.dbprofiles import (  # noqa: E402
    AuthRequiredError,
    ProfileError,
    ProfileStore,
)
from tools._lib.io import emit, fail  # noqa: E402
from tools.sqlserver import connection, schema  # noqa: E402

TOOL = "sqlserver"
# User-specific config lives in the central user-data folder, not in the tool dir
# (framework/user-data separation). See tools/_lib/userdata.py and the breadcrumb
# tools/sqlserver/MOVED-TO-CENTRAL.md.
PROFILES_PATH = userdata.config_dir(TOOL) / "profiles.json"


class UsageError(Exception):
    """Bad/invalid arguments -> invalid_argument, exit 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise UsageError(message)


@dataclass
class ActionDef:
    func: Callable
    add_args: Callable[[argparse.ArgumentParser], None] = lambda p: None
    description: str = ""
    needs_conn: bool = False


def _store() -> ProfileStore:
    return ProfileStore(TOOL, PROFILES_PATH)


def _parse_params(raw: str | None) -> list | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"--params must be a JSON array, got invalid JSON: {e}") from e
    if not isinstance(data, list):
        raise UsageError("--params must be a JSON array, e.g. '[42, \"abc\"]'")
    return data


def _split_types(raw: str | None) -> list[str] | None:
    """'P,FN,U' -> ['P','FN','U']; None/'' -> None (all types)."""
    if not raw:
        return None
    parts = [t.strip() for t in raw.split(",") if t.strip()]
    return parts or None


# -- profile management (no DB) ---------------------------------------------

def _profiles(_args) -> dict:
    store = _store()
    return {"count": len(store.names()), "profiles": store.list_public()}


def _add_profile_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="Profile name (also the credential name)")
    p.add_argument("--server", required=True, help="Host, host\\instance, or fqdn")
    p.add_argument("--database", help="Default database (optional; one profile can serve "
                   "many DBs - pick per call with --database on query/tables/columns)")
    p.add_argument("--username", help="SQL login (omit for a trusted/Windows connection)")
    p.add_argument("--port", type=int, help="TCP port (appended as server,port)")
    p.add_argument("--driver", help="ODBC driver name (default: the newest ODBC Driver "
                   "for SQL Server installed on this machine)")
    p.add_argument("--encrypt", choices=["yes", "no"], help="Encrypt the connection (default yes)")
    p.add_argument("--trust-server-certificate", dest="trust_server_certificate",
                   choices=["yes", "no"], help="Trust a self-signed server cert (default no)")
    p.add_argument("--connect-timeout", dest="connect_timeout", type=int,
                   help="Connect timeout seconds (default 30)")
    p.add_argument("--statement-timeout", dest="statement_timeout", type=int,
                   help="Statement timeout seconds, 0=unbounded (default 300)")
    p.add_argument("--overwrite", action="store_true", help="Replace an existing profile")


def _add_profile(args) -> dict:
    config: dict = {"server": args.server}
    if args.database:
        config["database"] = args.database
    if args.username:
        config["username"] = args.username
    if args.port:
        config["port"] = args.port
    if args.driver:
        config["driver"] = args.driver
    if args.encrypt:
        config["encrypt"] = args.encrypt == "yes"
    if args.trust_server_certificate:
        config["trust_server_certificate"] = args.trust_server_certificate == "yes"
    if args.connect_timeout is not None:
        config["connect_timeout"] = args.connect_timeout
    if args.statement_timeout is not None:
        config["statement_timeout"] = args.statement_timeout
    view = _store().add(args.name, config, overwrite=args.overwrite)
    view["note"] = (
        f"profile stored (no password). Set the password with: "
        f"python scripts/set-credential.py {TOOL} {args.name}"
    )
    return view


# -- DB actions --------------------------------------------------------------

def _profile_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--profile", required=True, help="Profile name")


def _test_connection(args, conn) -> dict:
    profile = _store().get(args.profile)
    return {
        "profile": args.profile,
        "connection_string": connection.masked_dsn(profile),
        "server_version": connection.server_version(conn),
        "connected": True,
    }


def _query_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--sql", required=True, help="SQL statement (SELECT by default)")
    p.add_argument("--params", help="Parameter values as a JSON array, bound via ? placeholders")
    p.add_argument("--max-rows", dest="max_rows", type=int, default=1000,
                   help="Cap rows returned (default 1000; 0=unbounded)")
    p.add_argument("--write", action="store_true",
                   help="Allow a non-SELECT/DDL/multi statement (off by default)")
    p.add_argument("--database", help="Run against this database instead of the profile's")
    p.add_argument("--no-normalize-eol", dest="no_normalize_eol", action="store_true",
                   help="Keep SQL line endings as-is (default: normalize to CRLF so a "
                        "CREATE/ALTER proc/view/function/trigger stores consistent EOLs "
                        "and SSMS does not flag inconsistent line endings on script-out)")


def _query(args, conn) -> dict:
    params = _parse_params(args.params)
    # Normalize script line endings to CRLF (SQL Server / SSMS native) so DDL
    # object definitions store consistent EOLs; --no-normalize-eol opts out.
    sql = args.sql if getattr(args, "no_normalize_eol", False) else dbquery.normalize_eol(args.sql)
    dbquery.assert_read_only(sql, write=args.write)
    result = connection.run_query(conn, sql, params, args.max_rows)
    result["write"] = bool(args.write)
    result["eol_normalized"] = not getattr(args, "no_normalize_eol", False)
    return result


def _tables_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="List tables from this database instead of the profile's")
    p.add_argument("--schema", help="Restrict to one schema")


def _tables(args, conn) -> dict:
    tables = connection.list_tables(conn, args.schema)
    return {"profile": args.profile, "count": len(tables), "tables": tables}


def _columns_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="Read columns from this database instead of the profile's")
    p.add_argument("--table", required=True, help="Table name (schema.table or table)")


def _columns(args, conn) -> dict:
    cols = connection.list_columns(conn, args.table)
    return {"profile": args.profile, "table": args.table,
            "count": len(cols), "columns": cols}


# -- schema-extract ----------------------------------------------------------

def _schema_extract_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="Extract this database instead of the profile's")
    p.add_argument("--out", help="Mirror output directory (default ./db-mirror/<profile>)")
    p.add_argument("--types", help="Comma-separated type letters to extract "
                   "(P,FN,TF,IF,V,TR,U); default all")
    p.add_argument("--full", action="store_true",
                   help="Wipe the mirror and re-extract everything")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Report what would change without writing")


def _schema_extract(args, conn) -> dict:
    out = args.out or f"./db-mirror/{args.profile}"
    types = _split_types(args.types)
    records = schema.extract_objects(conn, types)
    summary = dbschema.write_mirror(out, records, full=args.full, dry_run=args.dry_run)
    db = getattr(args, "database", None)
    return {"profile": args.profile, "database": db, **summary}


# -- schema-diff (manages its own connections) ------------------------------

def _schema_diff_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--left", required=True,
                   help="Mirror directory OR profile:NAME for the left side")
    p.add_argument("--right", required=True,
                   help="Mirror directory OR profile:NAME for the right side")
    p.add_argument("--database-left", dest="database_left",
                   help="Database override when --left is a profile")
    p.add_argument("--database-right", dest="database_right",
                   help="Database override when --right is a profile")
    p.add_argument("--types", help="Comma-separated type letters to extract for "
                   "profile sides (P,FN,TF,IF,V,TR,U); default all")
    p.add_argument("--no-diff-text", dest="no_diff_text", action="store_true",
                   help="Only list added/removed/changed names (omit unified diffs)")


def _resolve_side(side: str, db_override: str | None, types, tmp_root: Path,
                  label: str, *, conn_factory=None) -> str:
    """Return a mirror directory for one diff side.

    If `side` is ``profile:NAME`` it opens that profile (with an optional
    --database override), extracts to a temp mirror under `tmp_root`, and returns
    that dir. Otherwise it is treated as an existing mirror directory.
    """
    prefix = "profile:"
    if not side.startswith(prefix):
        return side
    profile_name = side[len(prefix):]
    if not profile_name:
        raise UsageError(f"--{label} profile reference is empty (use profile:NAME)")
    store = _store()
    profile = store.get(profile_name)
    if db_override:
        profile = {**profile, "database": db_override}
    if conn_factory is not None:
        conn = conn_factory(profile)
    else:
        password = store.password(profile_name)
        conn = connection.connect(profile, password)
    try:
        records = schema.extract_objects(conn, types)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    mirror_dir = tmp_root / label
    dbschema.write_mirror(mirror_dir, records, full=True)
    return str(mirror_dir)


def _schema_diff(args, *, conn_factory=None) -> dict:
    types = _split_types(args.types)
    with tempfile.TemporaryDirectory(prefix="sqlserver-diff-") as tmp:
        tmp_root = Path(tmp)
        left = _resolve_side(args.left, getattr(args, "database_left", None), types,
                             tmp_root, "left", conn_factory=conn_factory)
        right = _resolve_side(args.right, getattr(args, "database_right", None), types,
                              tmp_root, "right", conn_factory=conn_factory)
        result = dbschema.diff_mirrors(left, right, include_diff=not args.no_diff_text)
    return result


# -- migrate -----------------------------------------------------------------

def _migrate_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="Migrate this database instead of the profile's")
    p.add_argument("--dir", help="Migrations directory (default ./db-migrations/<profile>)")
    p.add_argument("--mode", choices=["list", "apply"], default="list",
                   help="list (read-only; default) or apply (writes)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Apply each pending file in a rolled-back transaction (no persist)")
    p.add_argument("--apply", action="store_true",
                   help="Required confirmation for --mode apply (this writes)")
    p.add_argument("--accept-drift", dest="accept_drift", action="store_true",
                   help="Proceed with apply even if applied files drifted on disk")


def _migration_view(migrations, applied) -> dict:
    """Build the applied/pending/drift breakdown shared by list and apply."""
    applied_ids = set(applied)
    pending = dbschema.pending(applied_ids, migrations)
    drift = []
    for mig_id, path in migrations:
        if mig_id in applied:
            on_disk = dbschema.sha256_file(path)
            if on_disk != applied[mig_id]["sha256"]:
                drift.append({"migration_id": mig_id, "filename": path.name,
                              "stored_sha256": applied[mig_id]["sha256"],
                              "disk_sha256": on_disk})
    pending_view = []
    for mig_id, path in pending:
        sql = path.read_text(encoding="utf-8")
        pending_view.append({
            "migration_id": mig_id,
            "filename": path.name,
            "danger_warnings": dbschema.danger_warnings(sql),
        })
    on_disk_ids = {mid for mid, _ in migrations}
    orphan_applied = sorted(set(applied) - on_disk_ids)
    return {
        "applied": [
            {"migration_id": mid, "filename": applied[mid].get("filename"),
             "applied_at": applied[mid].get("applied_at")}
            for mid in sorted(applied)
        ],
        "pending": pending_view,
        "drift": drift,
        "orphan_applied": orphan_applied,
    }


def _migrate(args, conn) -> dict:
    mig_dir = args.dir or f"./db-migrations/{args.profile}"
    migrations, skipped = dbschema.discover_migrations(mig_dir)
    applied = schema.fetch_applied(conn)
    view = _migration_view(migrations, applied)
    base = {
        "profile": args.profile,
        "database": getattr(args, "database", None),
        "dir": mig_dir,
        "mode": args.mode,
        "skipped_files": skipped,
        **view,
    }

    if args.mode == "list":
        base["dry_run"] = False
        return base

    # --- apply -------------------------------------------------------------
    if not args.apply:
        raise UsageError(
            "--mode apply writes to the database; pass --apply to confirm "
            "(or use --apply --dry-run to validate via a rolled-back transaction)."
        )
    if view["drift"] and not args.accept_drift:
        drifted = ", ".join(d["migration_id"] for d in view["drift"])
        raise UsageError(
            f"refusing to apply: applied migrations changed on disk (drift): {drifted}. "
            f"Create a new forward migration, or pass --accept-drift to proceed."
        )

    # apply WRITES — create the tracking table now (the read-only `list` never does).
    schema.ensure_migrations_table(conn)
    results = []
    pending = dbschema.pending(set(applied), migrations)
    for mig_id, path in pending:
        # CRLF-normalize so a migration that (re)creates a proc/view stores
        # consistent line endings (matches the query path).
        sql = dbquery.normalize_eol(path.read_text(encoding="utf-8"))
        sha = dbschema.sha256_file(path)
        warnings = dbschema.danger_warnings(sql)
        started = time.monotonic()
        try:
            batches = schema.apply_migration_sql(conn, sql, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - started) * 1000)
            results.append({
                "migration_id": mig_id, "filename": path.name, "status": "error",
                "error": str(exc), "duration_ms": duration_ms,
                "danger_warnings": warnings,
            })
            base["results"] = results
            base["dry_run"] = bool(args.dry_run)
            base["stopped_on_error"] = mig_id
            return base
        duration_ms = int((time.monotonic() - started) * 1000)
        if not args.dry_run:
            schema.record_applied(conn, mig_id, path.name, sha, duration_ms)
        results.append({
            "migration_id": mig_id, "filename": path.name,
            "status": "dry-run-ok" if args.dry_run else "applied",
            "batches": batches, "duration_ms": duration_ms,
            "danger_warnings": warnings,
        })

    base["results"] = results
    base["dry_run"] = bool(args.dry_run)
    base["applied_now"] = len(results)
    return base


ACTIONS: dict[str, ActionDef] = {
    "profiles": ActionDef(
        _profiles, description="List configured connection profiles (no passwords)."),
    "add-profile": ActionDef(
        _add_profile, _add_profile_args,
        description="Store a connection profile (config only; password via set-credential)."),
    "test-connection": ActionDef(
        _test_connection, _profile_arg, needs_conn=True,
        description="Connect and return the masked connection string + server version."),
    "query": ActionDef(
        _query, _query_args, needs_conn=True,
        description="Run read-only SQL (use --write for non-SELECT); returns columns/rows."),
    "tables": ActionDef(
        _tables, _tables_args, needs_conn=True,
        description="List tables/views (optionally one --schema)."),
    "columns": ActionDef(
        _columns, _columns_args, needs_conn=True,
        description="List a table's columns (name, type, nullable, length, default)."),
    "schema-extract": ActionDef(
        _schema_extract, _schema_extract_args, needs_conn=True,
        description="Mirror all DB objects to local .sql files (incremental; read-only)."),
    "schema-diff": ActionDef(
        _schema_diff, _schema_diff_args, needs_conn=False,
        description="Diff two schema mirrors or live profiles (read-only)."),
    "migrate": ActionDef(
        _migrate, _migrate_args, needs_conn=True,
        description="List or apply versioned .sql migrations (apply gated behind --apply)."),
}


def dispatch(action: str, argv: list[str], *, conn_factory=None) -> dict:
    if action not in ACTIONS:
        raise UsageError(f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}")
    defn = ACTIONS[action]
    parser = _Parser(prog=f"{TOOL} {action}", description=defn.description)
    defn.add_args(parser)
    parsed = parser.parse_args(argv)
    # schema-diff manages its own connection(s) per side; pass the factory through.
    if action == "schema-diff":
        return defn.func(parsed, conn_factory=conn_factory)
    if not defn.needs_conn:
        return defn.func(parsed)
    store = _store()
    profile = store.get(parsed.profile)
    # A per-call --database overrides the profile's database, so one profile
    # (one server + login + credential) can query any DB on that server.
    db_override = getattr(parsed, "database", None)
    if db_override:
        profile = {**profile, "database": db_override}
    if conn_factory is not None:
        conn = conn_factory(profile)
    else:
        password = store.password(parsed.profile)
        conn = connection.connect(profile, password)
    try:
        return defn.func(parsed, conn)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _classify(exc: Exception):
    if isinstance(exc, UsageError):
        return "invalid_argument", str(exc), 2
    if isinstance(exc, ProfileError):
        return "invalid_argument", str(exc), 2
    if isinstance(exc, AuthRequiredError):
        return "auth_required", str(exc), 1
    if isinstance(exc, dbquery.WriteGuardError):
        return "write_blocked", str(exc), 2
    if isinstance(exc, connection.MissingDependencyError):
        return "missing_dependency", str(exc), 1
    if isinstance(exc, connection.DBError):
        return "db_error", str(exc), 1
    return "error", str(exc) or exc.__class__.__name__, 1


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("Actions:", file=sys.stderr)
        for name in sorted(ACTIONS):
            print(f"  {name:<16} {ACTIONS[name].description}", file=sys.stderr)
        sys.exit(0)
    action, rest = argv[0], argv[1:]
    try:
        result = dispatch(action, rest)
    except Exception as exc:  # noqa: BLE001
        code, message, exit_code = _classify(exc)
        fail(code, message, {}, exit_code)
    emit(result)


if __name__ == "__main__":
    main()
