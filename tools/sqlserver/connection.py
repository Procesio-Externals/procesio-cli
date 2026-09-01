"""pyodbc connection factory + query layer for the `sqlserver` tool.

Lazy driver import: pyodbc is only imported when a connection is actually
opened, so `add-profile` / `profiles` work on a box without the ODBC driver.
If pyodbc is missing we raise ``MissingDependencyError`` (mapped to
``missing_dependency``) with an install hint.

A profile's NON-SECRET config (from profiles.json) carries:
  server   (required)  host\\instance or host,port or fqdn
  database (optional)  default DB; omit for a server+login-only profile and
                       pick the DB per call via --database (login default if neither)
  username (optional)  SQL login; omit for a trusted/Windows connection
  driver   (optional)  ODBC driver name; default = the newest driver actually
                       installed here (see best_available_driver)
  port     (optional)  appended to server as server,port when set
  encrypt              bool, default True
  trust_server_certificate  bool, default False
  connect_timeout      seconds, default 30
  statement_timeout    seconds, default 300 (0 = unbounded)
  read_only            bool, default True (adds ApplicationIntent=ReadOnly)
The password comes from Credential Manager (never from the file).
"""
from __future__ import annotations

from typing import Any

from tools._lib import dbquery

DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
# Newest first: a profile created without --driver should use the best driver
# the box actually has, not a fixed name. Hardcoding 18 meant every profile
# made on a machine with only 17 failed at CONNECT time with a driver error -
# which reads like a credential problem and sends you hunting in the wrong
# place. GeFEE2's own _connection.py already picks by availability.
DRIVER_PREFERENCE = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13.1 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
)
DEFAULT_CONNECT_TIMEOUT = 30
DEFAULT_STATEMENT_TIMEOUT = 300
APP_TAG = "agents-and-tools-sqlserver"


class MissingDependencyError(Exception):
    """pyodbc / ODBC driver not installed. -> missing_dependency."""


class DBError(Exception):
    """A driver-level error opening/executing. -> db_error."""


def _import_pyodbc():
    try:
        import pyodbc  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on host
        raise MissingDependencyError(
            "pyodbc is not installed (or no ODBC driver is available). Install with:\n"
            "    uv pip install pyodbc\n"
            "and install an ODBC Driver for SQL Server (17 or 18): "
            "https://aka.ms/odbc18-msi"
        ) from e
    return pyodbc


def _server_field(profile: dict) -> str:
    server = profile.get("server")
    if not server:
        raise DBError("profile is missing 'server'")
    port = profile.get("port")
    if port and "," not in str(server) and "\\" not in str(server):
        return f"{server},{port}"
    return str(server)


def installed_drivers() -> list[str]:
    """ODBC drivers present on this box, or [] if pyodbc is unavailable.

    Never raises: driver selection must not turn a missing optional dependency
    into a failure at a point where the caller has not asked to connect yet.
    """
    try:
        import pyodbc  # noqa: PLC0415

        return list(pyodbc.drivers())
    except Exception:  # noqa: BLE001 - see docstring
        return []


def best_available_driver() -> str:
    """The newest preferred driver actually installed here.

    Falls back to DEFAULT_DRIVER when nothing is enumerable, so the error the
    user eventually sees still names a real driver they can install rather than
    an empty string.
    """
    available = set(installed_drivers())
    for name in DRIVER_PREFERENCE:
        if name in available:
            return name
    # Nothing recognised: prefer any "ODBC Driver NN for SQL Server" present,
    # highest version first, so a newer driver than this list knows about wins.
    numbered = sorted(
        (d for d in available if d.startswith("ODBC Driver ")),
        key=lambda d: [int(p) for p in d.split()[2].split(".") if p.isdigit()] or [0],
        reverse=True,
    )
    return numbered[0] if numbered else DEFAULT_DRIVER


def build_dsn(profile: dict, password: str | None) -> str:
    """Build a pyodbc connection string. Includes the password when given.

    Use ``mask_dsn`` (dbquery) before logging/returning this string.
    """
    driver = profile.get("driver") or best_available_driver()
    database = profile.get("database")
    encrypt = profile.get("encrypt", True)
    trust = profile.get("trust_server_certificate", False)
    connect_timeout = int(profile.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT))
    read_only = profile.get("read_only", True)

    parts = [
        f"Driver={{{driver}}}",
        f"Server={_server_field(profile)}",
    ]
    # Database is optional: omit it to connect to the login's default database.
    # A profile can be server+login only, with the database picked per call via
    # the --database arg on query/tables/columns.
    if database:
        parts.append(f"Database={database}")
    parts += [
        f"Encrypt={'yes' if encrypt else 'no'}",
        f"TrustServerCertificate={'yes' if trust else 'no'}",
        f"Connection Timeout={connect_timeout}",
    ]
    username = profile.get("username")
    if username:
        parts.append(f"UID={username}")
        if password is not None:
            parts.append(f"PWD={password}")
    else:
        parts.append("Trusted_Connection=yes")
    if read_only:
        parts.append("ApplicationIntent=ReadOnly")
    parts.append(f"APP={APP_TAG}")
    return ";".join(parts) + ";"


def masked_dsn(profile: dict) -> str:
    """Connection string with the password redacted — safe to return/log."""
    return dbquery.mask_dsn(build_dsn(profile, password="<set>"))


def connect(profile: dict, password: str | None):
    """Open a pyodbc connection for `profile`. Applies the statement timeout."""
    pyodbc = _import_pyodbc()
    dsn = build_dsn(profile, password)
    connect_timeout = int(profile.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT))
    try:
        conn = pyodbc.connect(dsn, autocommit=True, timeout=connect_timeout)
    except pyodbc.Error as e:  # pragma: no cover - needs a live server
        raise DBError(str(e)) from e
    stmt_timeout = int(profile.get("statement_timeout", DEFAULT_STATEMENT_TIMEOUT))
    if stmt_timeout and stmt_timeout > 0:
        conn.timeout = stmt_timeout
    return conn


# ---------------------------------------------------------------------------
# Query + introspection. Each takes a connection-like object so tests can
# inject a fake. None of these enforce the write-guard — the dispatch layer
# (main.py) calls dbquery.assert_read_only first.
# ---------------------------------------------------------------------------

def run_query(
    conn,
    sql: str,
    params: list | tuple | None,
    max_rows: int | None,
) -> dict:
    """Execute one SQL statement and return {columns, rows, row_count, truncated}.

    `params` are passed straight to ``cursor.execute`` as a sequence (never
    string-interpolated into `sql`). pyodbc uses ``?`` placeholders.
    """
    cur = conn.cursor()
    if params:
        cur.execute(sql, list(params))
    else:
        cur.execute(sql)
    columns = dbquery.column_names(cur)
    raw = cur.fetchall() if columns else []
    capped, truncated = dbquery.cap_rows(list(raw), max_rows)
    rows = dbquery.rows_to_dicts(columns, capped)
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


def server_version(conn) -> str:
    cur = conn.cursor()
    cur.execute("SELECT @@VERSION")
    row = cur.fetchone()
    return str(row[0]) if row else ""


def list_tables(conn, schema: str | None) -> list[dict]:
    sql = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
        "FROM INFORMATION_SCHEMA.TABLES"
    )
    params: list[Any] = []
    if schema:
        sql += " WHERE TABLE_SCHEMA = ?"
        params.append(schema)
    sql += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
    out = run_query(conn, sql, params or None, None)
    return out["rows"]


def list_columns(conn, table: str) -> list[dict]:
    """Columns for `table`, which may be ``schema.table`` or just ``table``."""
    schema, _, name = table.rpartition(".")
    sql = (
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
        "CHARACTER_MAXIMUM_LENGTH, COLUMN_DEFAULT "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?"
    )
    params: list[Any] = [name]
    if schema:
        sql += " AND TABLE_SCHEMA = ?"
        params.append(schema)
    sql += " ORDER BY ORDINAL_POSITION"
    out = run_query(conn, sql, params, None)
    return out["rows"]
