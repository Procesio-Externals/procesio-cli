"""mysql tool entrypoint - read-only MySQL/MariaDB queries over pymysql.

Action-dispatched, JSON in / JSON out. READ-ONLY BY DEFAULT: MySQL has no
ApplicationIntent=ReadOnly, so the shared write-guard IS the enforcement -
any non-SELECT statement (or multi-statement batch) is rejected unless
``--write`` is passed. Connection details live in named profiles
(profiles.json); the password lives ONLY in Windows Credential Manager under
``agents-and-tools:mysql:<profile>``.

Actions:
  profiles
  add-profile     --name --host [--database --username --port --charset --tls ...]
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
from dataclasses import dataclass  # noqa: E402
from typing import Callable  # noqa: E402

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from tools._lib import dbquery  # noqa: E402
from tools._lib import dbschema  # noqa: E402
from tools._lib import userdata  # noqa: E402
from tools._lib.dbprofiles import (  # noqa: E402
    AuthRequiredError,
    ProfileError,
    ProfileStore,
)
from tools._lib.io import emit, fail  # noqa: E402
from tools.mysql import connection  # noqa: E402
from tools.mysql import schema as mysql_schema  # noqa: E402

TOOL = "mysql"
# User-specific config lives in the central user-data folder, not in the tool dir
# (framework/user-data separation). See tools/_lib/userdata.py and the breadcrumb
# tools/mysql/MOVED-TO-CENTRAL.md.
PROFILES_PATH = userdata.config_dir(TOOL) / "profiles.json"


class UsageError(Exception):
    """Bad/invalid arguments -> invalid_argument, exit 2."""


class MigrateError(Exception):
    """A migration failed mid-apply. Carries partial result details for context."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


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


# -- profile management (no DB) ---------------------------------------------

def _profiles(_args) -> dict:
    store = _store()
    return {"count": len(store.names()), "profiles": store.list_public()}


def _add_profile_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--name", required=True, help="Profile name (also the credential name)")
    p.add_argument("--host", required=True, help="MySQL host")
    p.add_argument("--database", help="Default schema/database")
    p.add_argument("--username", help="MySQL user (default: root)")
    p.add_argument("--port", type=int, help="TCP port (default 3306)")
    p.add_argument("--charset", help="Connection charset (default utf8mb4)")
    p.add_argument("--tls", choices=["yes", "no"], help="Wrap the socket in TLS (default no)")
    p.add_argument("--tls-verify-cert", dest="tls_verify_cert", choices=["yes", "no"],
                   help="Verify the server certificate chain (default no)")
    p.add_argument("--connect-timeout", dest="connect_timeout", type=int,
                   help="Connect timeout seconds (default 30)")
    p.add_argument("--statement-timeout", dest="statement_timeout", type=int,
                   help="Read/statement timeout seconds, 0=unbounded (default 300)")
    p.add_argument("--overwrite", action="store_true", help="Replace an existing profile")


def _add_profile(args) -> dict:
    config: dict = {"host": args.host}
    if args.database:
        config["database"] = args.database
    if args.username:
        config["username"] = args.username
    if args.port:
        config["port"] = args.port
    if args.charset:
        config["charset"] = args.charset
    if args.tls:
        config["tls"] = args.tls == "yes"
    if args.tls_verify_cert:
        config["tls_verify_cert"] = args.tls_verify_cert == "yes"
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
    p.add_argument("--params", help="Parameter values as a JSON array, bound via %s placeholders")
    p.add_argument("--max-rows", dest="max_rows", type=int, default=1000,
                   help="Cap rows returned (default 1000; 0=unbounded)")
    p.add_argument("--write", action="store_true",
                   help="Allow a non-SELECT/DDL/multi statement (off by default)")
    p.add_argument("--database", help="Run against this database instead of the profile's")


def _query(args, conn) -> dict:
    params = _parse_params(args.params)
    dbquery.assert_read_only(args.sql, write=args.write)
    result = connection.run_query(conn, args.sql, params, args.max_rows)
    result["write"] = bool(args.write)
    return result


def _tables_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="List tables from this database instead of the profile's")
    p.add_argument("--schema", help="Restrict to one schema (default: the profile's database)")


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


# -- schema-extract (read-only mirror of all DB objects) --------------------

def _schema_extract_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="Extract this database instead of the profile's")
    p.add_argument("--out", help="Mirror output dir (default ./db-mirror/<profile>)")
    p.add_argument("--types",
                   help="Comma list of object types to include "
                        "(TABLE,VIEW,PROCEDURE,FUNCTION,TRIGGER,EVENT); default all")
    p.add_argument("--full", action="store_true",
                   help="Wipe and re-extract everything (default: incremental)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Report what would change without writing")


def _schema_extract(args, conn) -> dict:
    records = mysql_schema.extract_objects(conn, args.types)
    out_dir = args.out or str(Path("./db-mirror") / args.profile)
    summary = dbschema.write_mirror(out_dir, records, full=args.full,
                                    dry_run=args.dry_run)
    database = getattr(args, "database", None) or ""
    return {"profile": args.profile, "database": database, **summary}


# -- schema-diff (manages its own connections; dir OR profile:NAME) ---------

def _schema_diff_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--left", required=True,
                   help="A mirror directory OR 'profile:NAME' to extract live")
    p.add_argument("--right", required=True,
                   help="A mirror directory OR 'profile:NAME' to extract live")
    p.add_argument("--database-left", dest="database_left",
                   help="DB override when --left is a profile")
    p.add_argument("--database-right", dest="database_right",
                   help="DB override when --right is a profile")
    p.add_argument("--types",
                   help="Comma list of object types to include when a side is a profile")
    p.add_argument("--no-diff-text", dest="no_diff_text", action="store_true",
                   help="Suppress per-object unified diff bodies (name lists only)")


def _resolve_side(spec: str, db_override: str | None, types, tmp_root: Path,
                  label: str) -> str:
    """Return a mirror directory for one diff side. A directory is used as-is;
    'profile:NAME' is extracted live to a temp mirror under tmp_root."""
    if spec.startswith("profile:"):
        profile_name = spec[len("profile:"):]
        if not profile_name:
            raise UsageError(f"--{label} 'profile:' needs a profile name")
        store = _store()
        profile = store.get(profile_name)
        if db_override:
            profile = {**profile, "database": db_override}
        password = store.password(profile_name)
        conn = connection.connect(profile, password)
        try:
            records = mysql_schema.extract_objects(conn, types)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        target = tmp_root / label
        dbschema.write_mirror(target, records, full=True, dry_run=False)
        return str(target)
    # plain directory
    if not Path(spec).is_dir():
        raise UsageError(
            f"--{label} '{spec}' is neither a directory nor 'profile:NAME'")
    return spec


def _schema_diff(args) -> dict:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="mysql-diff-") as td:
        tmp_root = Path(td)
        left = _resolve_side(args.left, getattr(args, "database_left", None),
                             args.types, tmp_root, "left")
        right = _resolve_side(args.right, getattr(args, "database_right", None),
                              args.types, tmp_root, "right")
        result = dbschema.diff_mirrors(left, right,
                                       include_diff=not args.no_diff_text)
    return {"left": args.left, "right": args.right, **result}


# -- migrate (list is read-only; apply is the only writer, gated by --apply) -

def _migrate_args(p: argparse.ArgumentParser) -> None:
    _profile_arg(p)
    p.add_argument("--database", help="Migrate this database instead of the profile's")
    p.add_argument("--dir", help="Migrations dir (default ./db-migrations/<profile>)")
    p.add_argument("--mode", choices=["list", "apply"], default="list",
                   help="list (read-only, default) or apply (writes)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Apply each pending migration in a rolled-back transaction")
    p.add_argument("--apply", action="store_true",
                   help="Required confirmation to actually write (with --mode apply)")
    p.add_argument("--accept-drift", dest="accept_drift", action="store_true",
                   help="Proceed with apply even if applied files changed on disk")


def _migrate(args, conn) -> dict:
    mig_dir = args.dir or str(Path("./db-migrations") / args.profile)
    found, skipped = dbschema.discover_migrations(mig_dir)

    applied = mysql_schema.fetch_applied(conn)   # read-only; {} if no tracking table yet

    # drift: an applied migration whose file sha256 changed (or vanished).
    by_id = {mid: p for mid, p in found}
    drift = []
    for mid, meta in applied.items():
        path = by_id.get(mid)
        if path is None:
            continue  # applied but file removed — not a content-drift case
        disk_sha = dbschema.sha256_file(path)
        if meta.get("sha256") and meta["sha256"] != disk_sha:
            drift.append(mid)

    pend = dbschema.pending(set(applied), found)
    pending_view = []
    for mid, path in pend:
        sql = path.read_text(encoding="utf-8")
        pending_view.append({
            "migration_id": mid,
            "filename": path.name,
            "sha256": dbschema.sha256_file(path),
            "danger_warnings": dbschema.danger_warnings(sql),
        })

    base = {
        "profile": args.profile,
        "database": getattr(args, "database", None) or "",
        "dir": mig_dir,
        "mode": args.mode,
        "dry_run": bool(args.dry_run),
        "applied_count": len(applied),
        "applied": sorted(applied),
        "pending_count": len(pending_view),
        "pending": pending_view,
        "drift": sorted(drift),
        "skipped_files": skipped,
    }

    if args.mode == "list":
        return base

    # --- apply mode (the only writer) --------------------------------------
    if not args.apply:
        raise UsageError(
            "migrate --mode apply requires the explicit --apply flag "
            "(this writes to the database). Re-run with --apply.")
    if drift and not args.accept_drift:
        raise UsageError(
            f"drift detected on applied migrations {sorted(drift)}: their files "
            f"changed on disk. Re-run with --accept-drift to proceed anyway.")

    # apply WRITES — create the tracking table now (the read-only `list` never does).
    mysql_schema.ensure_migrations_table(conn)
    results = []
    for mid, path in pend:
        sql = path.read_text(encoding="utf-8")
        sha = dbschema.sha256_file(path)
        try:
            if args.dry_run:
                duration = mysql_schema.apply_migration_dry_run(conn, sql)
            else:
                duration = mysql_schema.apply_migration_sql(conn, sql)
                mysql_schema.record_applied(conn, mid, path.name, sha, duration)
        except Exception as exc:  # noqa: BLE001
            results.append({"migration_id": mid, "filename": path.name,
                            "status": "error", "error": str(exc)})
            base["applied_results"] = results
            base["stopped_on_error"] = mid
            raise MigrateError(f"migration {mid} failed: {exc}", base) from exc
        results.append({"migration_id": mid, "filename": path.name,
                        "status": "dry-run" if args.dry_run else "applied",
                        "duration_ms": duration})

    base["applied_results"] = results
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
        description="List a table's columns (name, type, nullable, key, length, default)."),
    "schema-extract": ActionDef(
        _schema_extract, _schema_extract_args, needs_conn=True,
        description="Mirror every DB object to local .sql files (read-only; incremental)."),
    "schema-diff": ActionDef(
        _schema_diff, _schema_diff_args, needs_conn=False,
        description="Diff two schema mirrors or live profiles (read-only)."),
    "migrate": ActionDef(
        _migrate, _migrate_args, needs_conn=True,
        description="List/apply versioned migrations (list is read-only; apply needs --apply)."),
}


def dispatch(action: str, argv: list[str], *, conn_factory=None) -> dict:
    if action not in ACTIONS:
        raise UsageError(f"unknown action: {action}. Known: {', '.join(sorted(ACTIONS))}")
    defn = ACTIONS[action]
    parser = _Parser(prog=f"{TOOL} {action}", description=defn.description)
    defn.add_args(parser)
    parsed = parser.parse_args(argv)
    if not defn.needs_conn:
        return defn.func(parsed)
    store = _store()
    profile = store.get(parsed.profile)
    # A per-call --database overrides the profile's database, so one profile
    # (one host + login + credential) can query any database on that host.
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
    if isinstance(exc, MigrateError):
        return "migration_failed", str(exc), 1
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
        details = getattr(exc, "details", {}) or {}
        fail(code, message, details, exit_code)
    emit(result)


if __name__ == "__main__":
    main()
