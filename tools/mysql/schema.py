"""Engine-specific schema extraction + migration bits for the `mysql` tool.

Pairs with the engine-agnostic machinery in ``tools/_lib/dbschema.py``
(``write_mirror`` / ``diff_mirrors`` / ``discover_migrations`` / ``pending`` /
``danger_warnings`` / hashing). This module is the MySQL half: it knows how to
enumerate a database's objects via INFORMATION_SCHEMA, pull each object's full
DDL with ``SHOW CREATE ...``, maintain the ``__schema_migrations`` tracking
table, and apply a migration file's statements.

It takes a connection-like object (any DB-API conn whose ``cursor()`` yields a
DictCursor — i.e. ``fetchall()``/``fetchone()`` return ``dict`` rows). Tests
inject a fake; production uses ``tools.mysql.connection``.

MySQL is simpler than SQL Server here: ``SHOW CREATE TABLE/VIEW/PROCEDURE/
FUNCTION/TRIGGER`` and ``SHOW CREATE EVENT`` hand back the complete ``CREATE``
statement, so the mirror DDL is verbatim and no catalog reconstruction is needed.

DELIMITER caveat (documented limitation): MySQL stored-routine bodies that a
human authored with ``DELIMITER`` blocks cannot be naively split on ``;`` — the
body itself contains semicolons. ``apply_migration_sql`` therefore runs each
migration file as a SINGLE statement (no client-side ``;`` splitting and no
``DELIMITER`` handling). Author routine migrations as one ``CREATE PROCEDURE``/
``CREATE FUNCTION`` statement per file (no ``DELIMITER``); the driver accepts the
full body in one ``execute``. Multi-statement DDL files (several plain
statements separated by ``;``) are NOT supported in one file for the same reason
— keep one statement per migration file, or rely on the routine body being a
single statement. ``split_go_batches`` is SQL-Server-only and is NOT used here.
"""
from __future__ import annotations

import time
from typing import Any

# Object-type "dir labels" used as the mirror's <Type> directory and as the
# user-facing --types vocabulary. Maps label -> the INFORMATION_SCHEMA source.
TYPE_LABELS = ("Tables", "Views", "Procedures", "Functions", "Triggers", "Events")

# --types accepts the singular engine letters (TABLE,VIEW,...) per the spec;
# map each to its dir label.
_FILTER_TO_LABEL = {
    "TABLE": "Tables",
    "VIEW": "Views",
    "PROCEDURE": "Procedures",
    "FUNCTION": "Functions",
    "TRIGGER": "Triggers",
    "EVENT": "Events",
}

MIGRATIONS_TABLE = "__schema_migrations"


# ---------------------------------------------------------------------------
# small cursor helpers (DictCursor-aware, tolerant of fake cursors)
# ---------------------------------------------------------------------------

def _rows(conn, sql: str, params=None) -> list[dict]:
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        out = cur.fetchall()
        return list(out) if out else []
    finally:
        _close(cur)


def _one(conn, sql: str, params=None) -> dict | None:
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        if hasattr(cur, "fetchone"):
            row = cur.fetchone()
            if row is not None:
                return row
            return None
        rows = cur.fetchall()
        return rows[0] if rows else None
    finally:
        _close(cur)


def _close(cur) -> None:
    try:
        cur.close()
    except Exception:  # noqa: BLE001
        pass


def _create_value(row: dict | None, *keys: str) -> str:
    """SHOW CREATE returns a dict whose DDL column key varies by object type
    (``Create Table`` / ``Create View`` / ``Create Procedure`` / ...). Triggers
    in particular use ``SQL Original Statement``. Pull the first matching key;
    fall back to the last non-name string column so we degrade gracefully on an
    unexpected MySQL/MariaDB variant."""
    if not row:
        return ""
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k])
    # case-insensitive retry (MariaDB sometimes differs in casing)
    lower = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v is not None:
            return str(v)
    # last resort: the longest string value that is not the object name
    candidates = [v for v in row.values() if isinstance(v, str)]
    return max(candidates, key=len) if candidates else ""


def _current_database(conn) -> str:
    row = _one(conn, "SELECT DATABASE() AS db")
    if not row:
        return ""
    db = row.get("db") if isinstance(row, dict) else None
    return str(db) if db else ""


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def extract_objects(conn, types=None) -> list[dict]:
    """Enumerate all objects in the connected database and return mirror records.

    Each record is ``{"type", "schema", "name", "definition"}`` where ``type``
    is a dir label (Tables/Views/Procedures/Functions/Triggers/Events),
    ``schema`` is the database name (or ""), ``name`` is the object name, and
    ``definition`` is the full ``SHOW CREATE`` text.

    ``types`` (optional) filters by the engine vocabulary
    ``TABLE,VIEW,PROCEDURE,FUNCTION,TRIGGER,EVENT`` (case-insensitive); each maps
    to its dir label. ``None`` extracts everything.
    """
    wanted = _wanted_labels(types)
    db = _current_database(conn)
    schema = db or ""
    records: list[dict] = []

    if "Tables" in wanted:
        for name in _table_names(conn, db, "BASE TABLE"):
            row = _one(conn, f"SHOW CREATE TABLE `{name}`")
            ddl = _create_value(row, "Create Table")
            records.append(_rec("Tables", schema, name, ddl))

    if "Views" in wanted:
        for name in _table_names(conn, db, "VIEW"):
            row = _one(conn, f"SHOW CREATE VIEW `{name}`")
            ddl = _create_value(row, "Create View")
            records.append(_rec("Views", schema, name, ddl))

    if "Procedures" in wanted:
        for name in _routine_names(conn, db, "PROCEDURE"):
            row = _one(conn, f"SHOW CREATE PROCEDURE `{name}`")
            ddl = _create_value(row, "Create Procedure")
            records.append(_rec("Procedures", schema, name, ddl))

    if "Functions" in wanted:
        for name in _routine_names(conn, db, "FUNCTION"):
            row = _one(conn, f"SHOW CREATE FUNCTION `{name}`")
            ddl = _create_value(row, "Create Function")
            records.append(_rec("Functions", schema, name, ddl))

    if "Triggers" in wanted:
        for name in _trigger_names(conn, db):
            row = _one(conn, f"SHOW CREATE TRIGGER `{name}`")
            ddl = _create_value(row, "SQL Original Statement", "Statement")
            records.append(_rec("Triggers", schema, name, ddl))

    if "Events" in wanted:
        for name in _event_names(conn, db):
            row = _one(conn, f"SHOW CREATE EVENT `{name}`")
            ddl = _create_value(row, "Create Event")
            records.append(_rec("Events", schema, name, ddl))

    return records


def _wanted_labels(types) -> set[str]:
    if not types:
        return set(TYPE_LABELS)
    if isinstance(types, str):
        tokens = [t for t in types.replace(",", " ").split() if t]
    else:
        tokens = list(types)
    wanted: set[str] = set()
    for tok in tokens:
        key = str(tok).strip().upper().rstrip("S")  # tolerate plural/singular
        # restore exact known forms
        for engine_key, label in _FILTER_TO_LABEL.items():
            if engine_key == key or engine_key.rstrip("S") == key or label.upper().rstrip("S") == key:
                wanted.add(label)
    return wanted or set(TYPE_LABELS)


def _rec(type_label: str, schema: str, name: str, definition: str) -> dict:
    # Normalize line endings to LF so the mirror is stable across hosts.
    text = (definition or "").replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return {"type": type_label, "schema": schema, "name": str(name),
            "definition": text}


def _table_names(conn, db: str, table_type: str) -> list[str]:
    if db:
        rows = _rows(
            conn,
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = %s ORDER BY TABLE_NAME",
            [db, table_type],
        )
    else:
        rows = _rows(
            conn,
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = %s ORDER BY TABLE_NAME",
            [table_type],
        )
    return [str(r["TABLE_NAME"]) for r in rows if r.get("TABLE_NAME")]


def _routine_names(conn, db: str, routine_type: str) -> list[str]:
    if db:
        rows = _rows(
            conn,
            "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
            "WHERE ROUTINE_SCHEMA = %s AND ROUTINE_TYPE = %s ORDER BY ROUTINE_NAME",
            [db, routine_type],
        )
    else:
        rows = _rows(
            conn,
            "SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES "
            "WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = %s ORDER BY ROUTINE_NAME",
            [routine_type],
        )
    return [str(r["ROUTINE_NAME"]) for r in rows if r.get("ROUTINE_NAME")]


def _trigger_names(conn, db: str) -> list[str]:
    if db:
        rows = _rows(
            conn,
            "SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = %s ORDER BY TRIGGER_NAME",
            [db],
        )
    else:
        rows = _rows(
            conn,
            "SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = DATABASE() ORDER BY TRIGGER_NAME",
        )
    return [str(r["TRIGGER_NAME"]) for r in rows if r.get("TRIGGER_NAME")]


def _event_names(conn, db: str) -> list[str]:
    if db:
        rows = _rows(
            conn,
            "SELECT EVENT_NAME FROM INFORMATION_SCHEMA.EVENTS "
            "WHERE EVENT_SCHEMA = %s ORDER BY EVENT_NAME",
            [db],
        )
    else:
        rows = _rows(
            conn,
            "SELECT EVENT_NAME FROM INFORMATION_SCHEMA.EVENTS "
            "WHERE EVENT_SCHEMA = DATABASE() ORDER BY EVENT_NAME",
        )
    return [str(r["EVENT_NAME"]) for r in rows if r.get("EVENT_NAME")]


# ---------------------------------------------------------------------------
# migration engine bits
# ---------------------------------------------------------------------------

CREATE_MIGRATIONS_TABLE = (
    f"CREATE TABLE IF NOT EXISTS `{MIGRATIONS_TABLE}` (\n"
    "  migration_id VARCHAR(255) NOT NULL,\n"
    "  filename     VARCHAR(512) NOT NULL,\n"
    "  sha256       CHAR(64) NOT NULL,\n"
    "  applied_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,\n"
    "  applied_by   VARCHAR(255) NULL,\n"
    "  duration_ms  BIGINT NULL,\n"
    "  notes        TEXT NULL,\n"
    "  PRIMARY KEY (migration_id)\n"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)


def ensure_migrations_table(conn) -> None:
    """Create the ``__schema_migrations`` tracking table if it does not exist."""
    cur = conn.cursor()
    try:
        cur.execute(CREATE_MIGRATIONS_TABLE)
    finally:
        _close(cur)


def tracking_table_exists(conn) -> bool:
    """Read-only: does the tracking table exist in the current database?"""
    rows = _rows(
        conn,
        "SELECT 1 AS x FROM information_schema.tables "
        f"WHERE table_schema = DATABASE() AND table_name = '{MIGRATIONS_TABLE}' LIMIT 1",
    )
    return bool(rows)


def fetch_applied(conn) -> dict[str, dict]:
    """Return ``{migration_id: {"sha256", "filename", "applied_at"}}`` from the
    tracking table. READ-ONLY: returns {} if the table does not exist yet (only
    ``apply`` creates it)."""
    if not tracking_table_exists(conn):
        return {}
    rows = _rows(
        conn,
        f"SELECT migration_id, filename, sha256, applied_at "
        f"FROM `{MIGRATIONS_TABLE}` ORDER BY migration_id",
    )
    out: dict[str, dict] = {}
    for r in rows:
        mid = r.get("migration_id")
        if mid is None:
            continue
        applied_at = r.get("applied_at")
        out[str(mid)] = {
            "sha256": str(r.get("sha256") or ""),
            "filename": str(r.get("filename") or ""),
            "applied_at": applied_at.isoformat() if hasattr(applied_at, "isoformat")
            else (str(applied_at) if applied_at is not None else None),
        }
    return out


def record_applied(conn, mig_id: str, filename: str, sha: str,
                   duration_ms: int, applied_by: str | None = None,
                   notes: str | None = None) -> None:
    """Insert a tracking row for a successfully-applied migration."""
    cur = conn.cursor()
    try:
        cur.execute(
            f"INSERT INTO `{MIGRATIONS_TABLE}` "
            f"(migration_id, filename, sha256, applied_by, duration_ms, notes) "
            f"VALUES (%s, %s, %s, %s, %s, %s)",
            [mig_id, filename, sha, applied_by, int(duration_ms), notes],
        )
    finally:
        _close(cur)


def apply_migration_sql(conn, sql: str) -> int:
    """Execute a migration file's SQL inside an explicit transaction and return
    elapsed milliseconds.

    Our ``connect()`` uses ``autocommit=True``, so we open an explicit
    transaction (``conn.begin()`` / ``conn.commit()``, falling back to raw
    ``BEGIN``/``COMMIT`` for fakes) and run the file's SQL as a SINGLE statement
    — see the module docstring's DELIMITER caveat: routine bodies and
    multi-statement ``;``-separated files are NOT client-side-split.
    """
    start = time.perf_counter()
    _begin(conn)
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql)
        finally:
            _close(cur)
        _commit(conn)
    except Exception:
        _rollback(conn)
        raise
    return int((time.perf_counter() - start) * 1000)


def apply_migration_dry_run(conn, sql: str) -> int:
    """Run a migration's SQL inside a transaction that is ALWAYS rolled back,
    validating it executes without persisting. Returns elapsed milliseconds.
    Re-raises on a SQL error so the caller can stop on the first failure."""
    start = time.perf_counter()
    _begin(conn)
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql)
        finally:
            _close(cur)
    finally:
        _rollback(conn)
    return int((time.perf_counter() - start) * 1000)


def _begin(conn) -> None:
    if hasattr(conn, "begin"):
        conn.begin()
    else:  # pragma: no cover - fakes provide begin(); real pymysql conn has it
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
        finally:
            _close(cur)


def _commit(conn) -> None:
    if hasattr(conn, "commit"):
        conn.commit()
    else:  # pragma: no cover
        cur = conn.cursor()
        try:
            cur.execute("COMMIT")
        finally:
            _close(cur)


def _rollback(conn) -> None:
    try:
        if hasattr(conn, "rollback"):
            conn.rollback()
        else:  # pragma: no cover
            cur = conn.cursor()
            try:
                cur.execute("ROLLBACK")
            finally:
                _close(cur)
    except Exception:  # noqa: BLE001
        pass
