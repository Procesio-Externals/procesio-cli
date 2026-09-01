"""Engine-agnostic SQL helpers shared by the `sqlserver` and `mysql` tools.

PURE module: it imports no database driver and opens no connection, so every
function here is unit-testable with zero infrastructure. The two tools wire it
to pyodbc / pymysql at the edges.

What lives here:
  - ``assert_read_only`` / ``is_write_sql`` — a regex write-statement guard that
    blocks INSERT/UPDATE/DELETE/MERGE/UPSERT/TRUNCATE/ALTER/CREATE/DROP/GRANT/
    EXEC/CALL/... and multi-statement batches, unless ``write=True``.
  - ``rows_to_dicts`` — DBAPI cursor rows -> ``list[dict]`` with JSON-safe
    coercion (datetime/date/time/timedelta/Decimal/bytes/UUID/memoryview/...).
  - ``cap_rows`` — apply a max-rows cap and report a ``truncated`` flag.
  - ``mask_dsn`` — redact a password inside any connection string for logging.

The guard is intentionally conservative: it strips string literals, quoted
identifiers and comments first, then looks for write keywords as whole words at
statement level. It is a guard, not a SQL parser — the real read-only guarantee
for SQL Server also leans on ApplicationIntent=ReadOnly + a read-only login when
configured; for MySQL (no ApplicationIntent equivalent) THIS guard is the
enforcement, so its keyword list is the superset of both engines.
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import re
import uuid as _uuid
from typing import Any, Sequence


class WriteGuardError(Exception):
    """Raised when a read-only query receives a write/DDL/multi-statement SQL.

    Tools map this to the framework error code ``write_blocked`` (exit 2).
    """


# Write / schema-change / side-effecting keywords. Superset across SQL Server
# and MySQL so the single guard protects both engines:
#   - DML:           INSERT, UPDATE, DELETE, MERGE, REPLACE (MySQL upsert), UPSERT
#   - DDL:           CREATE, ALTER, DROP, TRUNCATE, RENAME
#   - permissions:   GRANT, REVOKE, DENY
#   - procedural:    EXEC, EXECUTE, CALL
#   - bulk / locks:  BULK, LOAD, LOCK, UNLOCK, HANDLER, DO
#   - tx / backup:   BACKUP, RESTORE, COMMIT, ROLLBACK, SET, USE
# SET/USE/COMMIT/ROLLBACK are blocked because they change session/tx state and
# have no place in a read-only ad-hoc query path.
WRITE_KEYWORDS: tuple[str, ...] = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "REPLACE",
    "CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "DENY",
    "EXEC", "EXECUTE", "CALL",
    "BULK", "LOAD", "LOCK", "UNLOCK", "HANDLER", "DO",
    "BACKUP", "RESTORE", "COMMIT", "ROLLBACK", "SET", "USE",
)

_WRITE_KW_RE = re.compile(r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b", re.IGNORECASE)

# Read-only DDL-inspection idioms whose CREATE keyword does not create anything.
_SHOW_CREATE_RE = re.compile(
    r"\bSHOW\s+CREATE\s+"
    r"(?:TABLE|VIEW|PROCEDURE|FUNCTION|TRIGGER|EVENT|DATABASE|SCHEMA)\b",
    re.IGNORECASE,
)

# Regexes that strip out non-statement text before keyword scanning so that a
# keyword inside a literal / identifier / comment never trips the guard.
_STRIP_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"'(?:[^'\\]|\\.|'')*'", re.DOTALL),   # 'single-quoted' ('' or \' escaped)
    re.compile(r'"(?:[^"\\]|\\.|"")*"', re.DOTALL),   # "double-quoted"
    re.compile(r"`(?:[^`\\]|\\.)*`", re.DOTALL),       # `backtick identifier` (MySQL)
    re.compile(r"\[[^\]]*\]"),                          # [bracketed identifier] (T-SQL)
    re.compile(r"/\*.*?\*/", re.DOTALL),               # /* block comment */
    re.compile(r"--[^\n]*"),                            # -- line comment
    re.compile(r"#[^\n]*"),                             # # line comment (MySQL)
    _SHOW_CREATE_RE,                                    # SHOW CREATE ... (read-only)
)


def _strip_noise(sql: str) -> str:
    """Remove literals, quoted identifiers, comments, SHOW CREATE prefixes."""
    out = sql
    for rx in _STRIP_RES:
        out = rx.sub(" ", out)
    return out


def _split_statements(stripped: str) -> list[str]:
    """Split a noise-stripped SQL on semicolons into non-empty statements.

    Operates on already-stripped text, so semicolons inside literals/comments
    are gone and can't create phantom statements.
    """
    return [s.strip() for s in stripped.split(";") if s.strip()]


def find_write_keywords(sql: str) -> list[str]:
    """Return write keywords found at statement level (after noise-stripping)."""
    stripped = _strip_noise(sql)
    return [m.group(1).upper() for m in _WRITE_KW_RE.finditer(stripped)]


def is_multi_statement(sql: str) -> bool:
    """True if the SQL is a batch of more than one statement (post-strip)."""
    return len(_split_statements(_strip_noise(sql))) > 1


def is_write_sql(sql: str) -> bool:
    """True if `sql` would be rejected under read-only rules (write or batch)."""
    return bool(find_write_keywords(sql)) or is_multi_statement(sql)


def assert_read_only(sql: str, *, write: bool = False) -> None:
    """Raise ``WriteGuardError`` unless `sql` is a single read-only statement.

    When ``write=True`` the guard is bypassed entirely (the tool has already
    confirmed the caller passed ``--write``). When ``write=False`` (default),
    any write/DDL/EXEC keyword OR a multi-statement batch is rejected.
    """
    if write:
        return
    hits = find_write_keywords(sql)
    if hits:
        # de-duplicate but keep order for a stable message
        seen: list[str] = []
        for h in hits:
            if h not in seen:
                seen.append(h)
        raise WriteGuardError(
            f"read-only guard blocked write keyword(s) {seen}. "
            f"Pass --write to allow a non-SELECT statement."
        )
    if is_multi_statement(sql):
        raise WriteGuardError(
            "read-only guard blocked a multi-statement batch (';' separates "
            "statements). Run one statement per query, or pass --write."
        )


# ---------------------------------------------------------------------------
# Line-ending normalization for DDL / script text
# ---------------------------------------------------------------------------

def normalize_eol(sql: str, style: str = "crlf") -> str:
    """Normalize every line ending in `sql` to one consistent style.

    Collapses CRLF and lone CR to LF first, then expands to the target style,
    so the result never contains a mixed CR/LF run. Default ``"crlf"`` matches
    SQL Server / SSMS: when a ``CREATE``/``ALTER`` of a PROCEDURE, VIEW,
    FUNCTION or TRIGGER is sent with LF-only newlines, SQL Server stores the
    object source verbatim, and SSMS then reports *"Inconsistent Line Endings"*
    on script-out because it prepends a CRLF ``SET ANSI_NULLS…GO`` header.
    Emitting CRLF keeps stored definitions internally consistent.

    T-SQL is whitespace-insensitive between tokens, so this never changes query
    semantics *outside* of string literals. The one case to preserve a bare LF
    is inside a string literal that must stay LF — callers expose an opt-out
    (the sqlserver tool's ``--no-normalize-eol``) for that. Parameter values are
    bound separately (``?`` placeholders) and are never passed through here.
    """
    lf = sql.replace("\r\n", "\n").replace("\r", "\n")
    if style == "lf":
        return lf
    if style != "crlf":
        raise ValueError(f"unknown eol style: {style!r} (use 'crlf' or 'lf')")
    return lf.replace("\n", "\r\n")


# ---------------------------------------------------------------------------
# Row formatting: DBAPI rows -> JSON-safe list[dict]
# ---------------------------------------------------------------------------

def json_safe(value: Any) -> Any:
    """Coerce one DBAPI value into something ``json.dumps`` can serialise.

    datetime/date/time -> ISO 8601 string; timedelta -> total seconds (float);
    Decimal -> str (preserves precision); bytes/bytearray/memoryview -> hex str;
    UUID -> str. Primitives (str/int/float/bool/None) pass through unchanged.
    Anything else falls back to ``str(value)``.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    if isinstance(value, _decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, memoryview):
        return value.tobytes().hex()
    if isinstance(value, _uuid.UUID):
        return str(value)
    return str(value)


def column_names(cursor) -> list[str]:
    """Column names from a DBAPI ``cursor.description`` (empty if no result set)."""
    if not getattr(cursor, "description", None):
        return []
    return [d[0] for d in cursor.description]


def rows_to_dicts(
    columns: Sequence[str],
    raw_rows: Sequence[Any],
) -> list[dict]:
    """Map DBAPI rows to JSON-safe dicts keyed by `columns`.

    Accepts both sequence rows (pyodbc tuples) and mapping rows (pymysql
    DictCursor dicts) — for a dict row we read each column by name, for a
    sequence row by position. Every value is passed through ``json_safe``.
    """
    out: list[dict] = []
    for row in raw_rows:
        if isinstance(row, dict):
            out.append({c: json_safe(row.get(c)) for c in columns})
        else:
            out.append({columns[i]: json_safe(row[i]) for i in range(len(columns))})
    return out


def cap_rows(rows: list[Any], max_rows: int | None) -> tuple[list[Any], bool]:
    """Trim `rows` to at most `max_rows`; return ``(rows, truncated)``.

    ``max_rows is None`` or ``<= 0`` means no cap. ``truncated`` is True only
    when rows were actually dropped.
    """
    if max_rows is None or max_rows <= 0:
        return rows, False
    if len(rows) > max_rows:
        return rows[:max_rows], True
    return rows, False


# ---------------------------------------------------------------------------
# Connection-string masking (for safe logging / test-connection output)
# ---------------------------------------------------------------------------

# pyodbc uses PWD=...; pymysql-style DSNs may use password=...; URL DSNs use
# scheme://user:password@host. Cover all three.
_MASK_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(PWD\s*=)[^;]*"), r"\1***"),
    (re.compile(r"(?i)(PASSWORD\s*=)[^;]*"), r"\1***"),
    (re.compile(r"(?i)(PASSWORD\s*:\s*)[^,}\s]+"), r"\1***"),
    # scheme://user:password@host  ->  scheme://user:***@host
    (re.compile(r"(://[^:/@\s]+:)[^@/\s]+(@)"), r"\1***\2"),
)


def mask_dsn(dsn: str) -> str:
    """Replace any password value in a connection string with ``***``."""
    out = dsn
    for rx, repl in _MASK_RES:
        out = rx.sub(repl, out)
    return out
