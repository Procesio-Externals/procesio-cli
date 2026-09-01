"""pymysql connection factory + query layer for the `mysql` tool.

Lazy driver import: pymysql is only imported when a connection is opened, so
`add-profile` / `profiles` work without it. If pymysql is missing we raise
``MissingDependencyError`` (mapped to ``missing_dependency``) with an install
hint.

MySQL has no ApplicationIntent=ReadOnly equivalent, so read-only is enforced
by the shared write-guard in dbquery (the dispatch layer calls it before any
statement runs). A profile's NON-SECRET config (from profiles.json):
  host     (required)
  database (optional)  default schema
  username (optional)  default 'root'
  port     (optional)  default 3306
  charset  (optional)  default 'utf8mb4'
  tls                  bool, default False (wrap socket in TLS)
  tls_verify_cert      bool, default False (verify the server cert chain)
  connect_timeout      seconds, default 30
  statement_timeout    seconds, default 300 (read timeout; 0 = unbounded)
The password comes from Credential Manager (never the file).
"""
from __future__ import annotations

import ssl as _ssl
from typing import Any

from tools._lib import dbquery

DEFAULT_PORT = 3306
DEFAULT_USERNAME = "root"
DEFAULT_CHARSET = "utf8mb4"
DEFAULT_CONNECT_TIMEOUT = 30
DEFAULT_STATEMENT_TIMEOUT = 300


class MissingDependencyError(Exception):
    """pymysql not installed. -> missing_dependency."""


class DBError(Exception):
    """A driver-level error opening/executing. -> db_error."""


def _import_pymysql():
    try:
        import pymysql  # noqa: PLC0415
        import pymysql.cursors  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on host
        raise MissingDependencyError(
            "pymysql is not installed. Install with:\n"
            "    uv pip install pymysql cryptography\n"
            "(cryptography is needed for MySQL 8 caching_sha2_password auth)."
        ) from e
    return pymysql


def _ssl_context(profile: dict):
    if not profile.get("tls"):
        return None
    ctx = _ssl.create_default_context()
    if not profile.get("tls_verify_cert", False):
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
    return ctx


def connection_kwargs(profile: dict, password: str | None) -> dict:
    """Build pymysql.connect kwargs (password included when given)."""
    host = profile.get("host")
    if not host:
        raise DBError("profile is missing 'host'")
    pymysql = _import_pymysql()
    kwargs: dict[str, Any] = {
        "host": host,
        "port": int(profile.get("port", DEFAULT_PORT)),
        "user": profile.get("username", DEFAULT_USERNAME),
        "charset": profile.get("charset", DEFAULT_CHARSET),
        "autocommit": True,
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": int(profile.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT)),
        "read_timeout": int(profile.get("statement_timeout", DEFAULT_STATEMENT_TIMEOUT)),
    }
    if profile.get("database"):
        kwargs["database"] = profile["database"]
    if password is not None:
        kwargs["password"] = password
    ctx = _ssl_context(profile)
    if ctx is not None:
        kwargs["ssl"] = ctx
    return kwargs


def masked_dsn(profile: dict) -> str:
    """A human-readable, password-free connection summary - safe to return/log."""
    host = profile.get("host", "?")
    port = int(profile.get("port", DEFAULT_PORT))
    user = profile.get("username", DEFAULT_USERNAME)
    database = profile.get("database", "")
    tls = "on" if profile.get("tls") else "off"
    dsn = f"mysql://{user}:***@{host}:{port}/{database}?charset={profile.get('charset', DEFAULT_CHARSET)}&tls={tls}"
    return dbquery.mask_dsn(dsn)


def connect(profile: dict, password: str | None):
    """Open a pymysql connection for `profile`."""
    pymysql = _import_pymysql()
    kwargs = connection_kwargs(profile, password)
    try:
        return pymysql.connect(**kwargs)
    except pymysql.Error as e:  # pragma: no cover - needs a live server
        raise DBError(str(e)) from e


# ---------------------------------------------------------------------------
# Query + introspection. Each takes a connection-like object so tests can
# inject a fake. The write-guard is enforced by the dispatch layer.
# ---------------------------------------------------------------------------

def run_query(
    conn,
    sql: str,
    params: list | tuple | None,
    max_rows: int | None,
) -> dict:
    """Execute one SQL statement; return {columns, rows, row_count, truncated}.

    `params` are passed to ``cursor.execute`` (pymysql uses ``%s`` placeholders);
    they are never string-interpolated into `sql`.
    """
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, list(params))
        else:
            cur.execute(sql)
        columns = dbquery.column_names(cur)
        raw = cur.fetchall() if columns else []
        capped, truncated = dbquery.cap_rows(list(raw), max_rows)
        rows = dbquery.rows_to_dicts(columns, capped)
    finally:
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


def server_version(conn) -> str:
    out = run_query(conn, "SELECT VERSION() AS version", None, None)
    rows = out["rows"]
    return str(rows[0].get("version", "")) if rows else ""


def list_tables(conn, schema: str | None) -> list[dict]:
    sql = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
        "FROM INFORMATION_SCHEMA.TABLES"
    )
    params: list[Any] = []
    if schema:
        sql += " WHERE TABLE_SCHEMA = %s"
        params.append(schema)
    else:
        sql += " WHERE TABLE_SCHEMA = DATABASE()"
    sql += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
    out = run_query(conn, sql, params or None, None)
    return out["rows"]


def list_columns(conn, table: str) -> list[dict]:
    """Columns for `table`, which may be ``schema.table`` or just ``table``."""
    schema, _, name = table.rpartition(".")
    sql = (
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY, "
        "CHARACTER_MAXIMUM_LENGTH, COLUMN_DEFAULT "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = %s"
    )
    params: list[Any] = [name]
    if schema:
        sql += " AND TABLE_SCHEMA = %s"
        params.append(schema)
    else:
        sql += " AND TABLE_SCHEMA = DATABASE()"
    sql += " ORDER BY ORDINAL_POSITION"
    out = run_query(conn, sql, params, None)
    return out["rows"]
