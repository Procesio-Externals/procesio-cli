"""SQL Server engine-specific schema extraction + migration helpers.

Provides the driver-touching half of the `schema-extract`, `schema-diff`, and
`migrate` actions; the pure, engine-agnostic machinery (mirror layout, diff,
migration discovery / danger / GO split) lives in ``tools/_lib/dbschema.py``.

Every function here takes a connection-like object (a real pyodbc connection or
a test fake) and uses ``conn.cursor()`` directly. The extract path is read-only
(SELECT against the system catalog). The migrate path is the only writer and is
gated upstream behind ``--apply``.

A "record" is the shared dbschema shape:
    {"type": <dir label>, "schema": <str|"">, "name": <str>, "definition": <sql>}

Object types extracted (by the ``sys.objects.type`` letter):
    P   procedures              -> dir "Procedures"   (verbatim sys.sql_modules)
    FN  scalar functions        -> dir "Functions"    (verbatim)
    IF  inline TVFs             -> dir "Functions"    (verbatim)
    TF  table-valued functions  -> dir "Functions"    (verbatim)
    V   views                   -> dir "Views"        (verbatim)
    TR  DML triggers            -> dir "Triggers"     (verbatim)
    U   user tables             -> dir "Tables"       (DDL generated from catalog)

Module objects (P/FN/IF/TF/V/TR) come VERBATIM from ``sys.sql_modules.definition``
so the mirror is byte-faithful to what the server stores. Tables (U) have no stored
"CREATE TABLE" text, so their DDL is generated from the catalog: columns (type,
nullability, identity, default, collation, computed), primary key, foreign keys,
non-PK indexes, and check constraints.

DEFERRED (v1 — not blocking; port from a sibling schema extractor when needed):
    - CLR assemblies (sys.assemblies) and CLR procs/types
    - user-defined types: scalar alias / table types / CLR types
    - authored schemas (CREATE SCHEMA) and database-scope DDL triggers
    - partitioning / filegroups / XML schema collections / full-text / sequences
    - synonyms, Service Broker objects, extended properties
"""
from __future__ import annotations

from typing import Any

from tools._lib import dbschema

# ---------------------------------------------------------------------------
# Type-letter -> readable directory label. The mirror groups objects by this
# label (dbschema.mirror_relpath uses it as the <Type> folder).
# ---------------------------------------------------------------------------

MODULE_TYPES = {
    "P": "Procedures",
    "FN": "Functions",
    "IF": "Functions",
    "TF": "Functions",
    "V": "Views",
    "TR": "Triggers",
}
TABLE_TYPE = "U"
TABLE_LABEL = "Tables"

# All type letters this engine knows how to extract.
ALL_TYPES = set(MODULE_TYPES) | {TABLE_TYPE}


# ---------------------------------------------------------------------------
# small cursor helpers
# ---------------------------------------------------------------------------

def _rows(cur) -> list[dict[str, Any]]:
    """Materialise the current cursor result as a list of column->value dicts."""
    cols = [c[0] for c in cur.description]
    return [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]


def _normalize(text: str) -> str:
    """Collapse CRLF/CR to LF so hashes are deterministic across hosts.

    SQL Server returns ``sys.sql_modules.definition`` with CRLF line endings; on
    Windows ``Path.write_text`` would translate ``\\n`` -> ``\\r\\n`` again,
    producing ``\\r\\r\\n``. Normalising to LF here keeps the mirror clean and the
    manifest sha stable (incremental runs short-circuit correctly).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------------------
# Module objects (procedures / functions / views / triggers) — verbatim
# ---------------------------------------------------------------------------

# One catalog query pulls every module definition. A LEFT JOIN to sys.sql_modules
# means encrypted (WITH ENCRYPTION) or permission-denied objects come back with a
# NULL body — surfaced as a comment placeholder rather than dropped silently.
_MODULES_SQL = """
SELECT
    SCHEMA_NAME(o.schema_id)      AS schema_name,
    o.name                        AS object_name,
    o.type                        AS type_code,
    o.type_desc                   AS type_desc,
    m.definition                  AS body
FROM sys.objects o
LEFT JOIN sys.sql_modules m ON m.object_id = o.object_id
WHERE o.type IN ('P','FN','TF','IF','V','TR')
  AND o.is_ms_shipped = 0
ORDER BY SCHEMA_NAME(o.schema_id), o.name;
"""


def _emit_module(obj: dict[str, Any]) -> str:
    body = obj.get("body")
    schema = obj.get("schema_name") or ""
    name = obj.get("object_name")
    if body is None:
        return (
            f"-- Object: {schema}.{name}\n"
            f"-- Type:   {obj.get('type_desc')}\n"
            f"-- NOTE:   definition unavailable (encrypted or permission denied)\n"
        )
    body = _normalize(body)
    if not body.endswith("\n"):
        body += "\n"
    return body


def extract_modules(conn) -> list[dict[str, Any]]:
    """Records for every P/FN/IF/TF/V/TR object, definition VERBATIM."""
    cur = conn.cursor()
    cur.execute(_MODULES_SQL)
    out: list[dict[str, Any]] = []
    for obj in _rows(cur):
        code = (obj.get("type_code") or "").strip()
        label = MODULE_TYPES.get(code)
        if not label:
            continue
        out.append({
            "type": label,
            "schema": obj.get("schema_name") or "",
            "name": obj.get("object_name"),
            "definition": _emit_module(obj),
        })
    return out


# ---------------------------------------------------------------------------
# Tables — CREATE TABLE DDL generated from the catalog
# ---------------------------------------------------------------------------

_TABLES_SQL = """
SELECT
    t.object_id,
    SCHEMA_NAME(t.schema_id)      AS schema_name,
    t.name                        AS table_name
FROM sys.tables t
WHERE t.is_ms_shipped = 0
ORDER BY SCHEMA_NAME(t.schema_id), t.name;
"""

_COLUMNS_SQL = """
SELECT
    c.column_id,
    c.name                    AS column_name,
    TYPE_NAME(c.user_type_id) AS type_name,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    c.is_identity,
    CAST(ic.seed_value      AS NVARCHAR(64)) AS seed_value,
    CAST(ic.increment_value AS NVARCHAR(64)) AS increment_value,
    c.collation_name,
    cc.definition             AS computed_definition,
    cc.is_persisted,
    dc.definition             AS default_definition,
    dc.name                   AS default_name,
    c.is_computed
FROM sys.columns c
LEFT JOIN sys.identity_columns ic ON ic.object_id = c.object_id AND ic.column_id = c.column_id
LEFT JOIN sys.computed_columns cc ON cc.object_id = c.object_id AND cc.column_id = c.column_id
LEFT JOIN sys.default_constraints dc
       ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
WHERE c.object_id = ?
ORDER BY c.column_id;
"""

_PK_SQL = """
SELECT
    kc.name                AS constraint_name,
    i.type_desc,
    c.name                 AS column_name,
    ic.is_descending_key,
    ic.key_ordinal
FROM sys.key_constraints kc
JOIN sys.indexes i        ON i.object_id = kc.parent_object_id AND i.index_id = kc.unique_index_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c        ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE kc.parent_object_id = ? AND kc.type = 'PK'
ORDER BY kc.name, ic.key_ordinal;
"""

_INDEX_SQL = """
SELECT
    i.index_id,
    i.name                 AS index_name,
    i.type_desc,
    i.is_unique,
    i.filter_definition,
    c.name                 AS column_name,
    ic.is_descending_key,
    ic.is_included_column,
    ic.key_ordinal
FROM sys.indexes i
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c        ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = ?
  AND i.is_primary_key = 0
  AND i.is_unique_constraint = 0
  AND i.type > 0
ORDER BY i.index_id, ic.is_included_column, ic.key_ordinal;
"""

_FK_SQL = """
SELECT
    fk.name                AS fk_name,
    SCHEMA_NAME(ref.schema_id) AS ref_schema,
    ref.name               AS ref_table,
    pc.name                AS parent_column,
    rc.name                AS ref_column,
    fk.delete_referential_action_desc,
    fk.update_referential_action_desc,
    fkc.constraint_column_id
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id     AND pc.column_id = fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
JOIN sys.tables ref ON ref.object_id = fk.referenced_object_id
WHERE fk.parent_object_id = ?
ORDER BY fk.name, fkc.constraint_column_id;
"""

_CHECK_SQL = """
SELECT
    cc.name       AS constraint_name,
    cc.definition AS definition,
    cc.is_disabled
FROM sys.check_constraints cc
WHERE cc.parent_object_id = ?
ORDER BY cc.name;
"""

_LENGTH_TYPES = {"varchar", "nvarchar", "char", "nchar", "varbinary", "binary"}
_PRECISION_TYPES = {"decimal", "numeric"}
_SCALE_TYPES = {"datetime2", "time", "datetimeoffset"}
_COLLATABLE = {"varchar", "nvarchar", "char", "nchar", "text", "ntext"}


def _format_type(type_name: str, max_length, precision, scale) -> str:
    t = (type_name or "").lower()
    if t in _LENGTH_TYPES:
        if max_length == -1:
            return f"{t}(MAX)"
        chars = max_length // 2 if t.startswith("n") else max_length
        return f"{t}({chars})"
    if t in _PRECISION_TYPES:
        return f"{t}({precision}, {scale})"
    if t in _SCALE_TYPES:
        return f"{t}({scale})"
    return t


def _qname(schema: str, name: str) -> str:
    return f"[{schema}].[{name}]"


def _emit_table(conn, obj: dict[str, Any]) -> str:
    oid = obj["object_id"]
    schema = obj["schema_name"]
    name = obj["table_name"]
    cur = conn.cursor()

    cur.execute(_COLUMNS_SQL, oid)
    columns = _rows(cur)
    cur.execute(_PK_SQL, oid)
    pk_rows = _rows(cur)
    cur.execute(_INDEX_SQL, oid)
    idx_rows = _rows(cur)
    cur.execute(_FK_SQL, oid)
    fk_rows = _rows(cur)
    cur.execute(_CHECK_SQL, oid)
    ck_rows = _rows(cur)

    lines: list[str] = [f"CREATE TABLE {_qname(schema, name)} ("]
    col_defs: list[str] = []
    for c in columns:
        if c.get("is_computed") and c.get("computed_definition"):
            persist = " PERSISTED" if c.get("is_persisted") else ""
            col_defs.append(f"    [{c['column_name']}] AS {c['computed_definition']}{persist}")
            continue
        type_str = _format_type(c["type_name"], c["max_length"], c["precision"], c["scale"])
        ident = ""
        if c.get("is_identity"):
            ident = f" IDENTITY({c.get('seed_value')},{c.get('increment_value')})"
        nullable = "NULL" if c.get("is_nullable") else "NOT NULL"
        default = ""
        if c.get("default_definition"):
            default = f" CONSTRAINT [{c['default_name']}] DEFAULT {c['default_definition']}"
        coll = ""
        if c.get("collation_name") and (c["type_name"] or "").lower() in _COLLATABLE:
            coll = f" COLLATE {c['collation_name']}"
        col_defs.append(
            f"    [{c['column_name']}] {type_str}{coll}{ident} {nullable}{default}"
        )

    if pk_rows:
        pk_name = pk_rows[0]["constraint_name"]
        pk_type = "CLUSTERED" if pk_rows[0]["type_desc"] == "CLUSTERED" else "NONCLUSTERED"
        pk_cols = ", ".join(
            f"[{r['column_name']}]{' DESC' if r.get('is_descending_key') else ''}"
            for r in pk_rows
        )
        col_defs.append(f"    CONSTRAINT [{pk_name}] PRIMARY KEY {pk_type} ({pk_cols})")

    lines.append(",\n".join(col_defs))
    lines.append(");")
    lines.append("GO")

    # CHECK constraints
    for ck in ck_rows:
        dis = " WITH NOCHECK" if ck.get("is_disabled") else ""
        lines.append(
            f"ALTER TABLE {_qname(schema, name)}{dis} "
            f"ADD CONSTRAINT [{ck['constraint_name']}] CHECK {ck['definition']};"
        )
        lines.append("GO")

    # Non-PK indexes
    if idx_rows:
        by_idx: dict[Any, list[dict]] = {}
        for r in idx_rows:
            by_idx.setdefault(r["index_id"], []).append(r)
        for entries in by_idx.values():
            ix = entries[0]
            keys = sorted(
                (e for e in entries if not e.get("is_included_column")),
                key=lambda e: e["key_ordinal"],
            )
            incs = [e for e in entries if e.get("is_included_column")]
            unique = "UNIQUE " if ix.get("is_unique") else ""
            key_cols = ", ".join(
                f"[{e['column_name']}]{' DESC' if e.get('is_descending_key') else ''}"
                for e in keys
            )
            include = ""
            if incs:
                include = " INCLUDE (" + ", ".join(f"[{e['column_name']}]" for e in incs) + ")"
            where = f" WHERE {ix['filter_definition']}" if ix.get("filter_definition") else ""
            lines.append(
                f"CREATE {unique}{ix['type_desc']} INDEX [{ix['index_name']}] "
                f"ON {_qname(schema, name)} ({key_cols}){include}{where};"
            )
            lines.append("GO")

    # Foreign keys
    if fk_rows:
        by_fk: dict[str, list[dict]] = {}
        for r in fk_rows:
            by_fk.setdefault(r["fk_name"], []).append(r)
        for fk_name, entries in by_fk.items():
            entries.sort(key=lambda e: e["constraint_column_id"])
            head = entries[0]
            parent_cols = ", ".join(f"[{e['parent_column']}]" for e in entries)
            ref_cols = ", ".join(f"[{e['ref_column']}]" for e in entries)
            on_del = (
                f" ON DELETE {head['delete_referential_action_desc'].replace('_', ' ')}"
                if head.get("delete_referential_action_desc") not in (None, "NO_ACTION") else ""
            )
            on_upd = (
                f" ON UPDATE {head['update_referential_action_desc'].replace('_', ' ')}"
                if head.get("update_referential_action_desc") not in (None, "NO_ACTION") else ""
            )
            lines.append(
                f"ALTER TABLE {_qname(schema, name)} "
                f"ADD CONSTRAINT [{fk_name}] FOREIGN KEY ({parent_cols}) "
                f"REFERENCES {_qname(head['ref_schema'], head['ref_table'])} "
                f"({ref_cols}){on_del}{on_upd};"
            )
            lines.append("GO")

    return "\n".join(lines) + "\n"


def extract_tables(conn) -> list[dict[str, Any]]:
    """Records for every user table, DDL generated from the catalog."""
    cur = conn.cursor()
    cur.execute(_TABLES_SQL)
    tables = _rows(cur)
    out: list[dict[str, Any]] = []
    for obj in tables:
        out.append({
            "type": TABLE_LABEL,
            "schema": obj.get("schema_name") or "",
            "name": obj.get("table_name"),
            "definition": _emit_table(conn, obj),
        })
    return out


# ---------------------------------------------------------------------------
# Public extract entrypoint
# ---------------------------------------------------------------------------

def extract_objects(conn, types=None) -> list[dict[str, Any]]:
    """Extract all (or a filtered subset of) DB objects as dbschema records.

    `types` is an optional iterable of SQL Server type letters to keep
    (``P``, ``FN``, ``TF``, ``IF``, ``V``, ``TR``, ``U``). ``None`` extracts all.
    The connection is autocommit + read-only; only SELECTs against the catalog
    are issued. Returns records sorted for a stable mirror.
    """
    wanted = None
    if types is not None:
        wanted = {t.strip().upper() for t in types if t and t.strip()}

    records: list[dict[str, Any]] = []
    want_modules = wanted is None or (wanted & set(MODULE_TYPES))
    if want_modules:
        for rec in extract_modules(conn):
            # filter at the type-letter level when a subset was requested
            if wanted is not None:
                # map back: the dir label alone is ambiguous (Functions <- FN/IF/TF),
                # so re-derive whether this record's letter is wanted by re-running
                # is unnecessary — extract_modules already only yields known labels;
                # filtering by letter happens below via _module_letter_wanted.
                pass
            records.append(rec)
        if wanted is not None:
            records = [r for r in records if _record_letters_wanted(r, wanted)]

    if wanted is None or TABLE_TYPE in wanted:
        records.extend(extract_tables(conn))

    records.sort(key=lambda r: (r["type"], r.get("schema") or "", r["name"]))
    return records


# Reverse map label -> set of letters that can produce it, for --types filtering.
_LABEL_LETTERS: dict[str, set[str]] = {}
for _letter, _label in MODULE_TYPES.items():
    _LABEL_LETTERS.setdefault(_label, set()).add(_letter)
_LABEL_LETTERS[TABLE_LABEL] = {TABLE_TYPE}


def _record_letters_wanted(record: dict, wanted: set[str]) -> bool:
    """True if the record's dir label maps to at least one wanted type letter.

    "Functions" maps to {FN, IF, TF}; if the user asked for only ``TF`` we cannot
    distinguish from the label alone, so we keep the whole Functions group when
    ANY of its letters is wanted. This is the documented coarse behaviour: --types
    selects object FAMILIES (proc / function / view / trigger / table), not the
    sub-kinds of a family.
    """
    letters = _LABEL_LETTERS.get(record["type"], set())
    return bool(letters & wanted)


# ===========================================================================
# Migration engine
# ===========================================================================

MIGRATIONS_SCHEMA = "dbo"
MIGRATIONS_TABLE = "__schema_migrations"
MIG_FQN = f"[{MIGRATIONS_SCHEMA}].[{MIGRATIONS_TABLE}]"

_ENSURE_TABLE_SQL = f"""
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE t.name = '{MIGRATIONS_TABLE}' AND s.name = '{MIGRATIONS_SCHEMA}'
)
BEGIN
    CREATE TABLE {MIG_FQN} (
        migration_id   VARCHAR(200)  NOT NULL PRIMARY KEY,
        filename       NVARCHAR(260) NOT NULL,
        sha256         CHAR(64)      NOT NULL,
        applied_at     DATETIME2(0)  NOT NULL
            CONSTRAINT DF___schema_migrations_applied_at DEFAULT SYSUTCDATETIME(),
        applied_by     NVARCHAR(128) NOT NULL
            CONSTRAINT DF___schema_migrations_applied_by DEFAULT SUSER_SNAME(),
        duration_ms    INT NULL,
        notes          NVARCHAR(MAX) NULL
    );
END;
"""


def ensure_migrations_table(conn) -> None:
    """Create ``dbo.__schema_migrations`` if it does not already exist. This is a
    WRITE — only the ``apply`` path calls it; ``list`` stays read-only."""
    cur = conn.cursor()
    cur.execute(_ENSURE_TABLE_SQL)


def tracking_table_exists(conn) -> bool:
    """Read-only: does the tracking table exist? (never creates it)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "WHERE t.name = ? AND s.name = ?", (MIGRATIONS_TABLE, MIGRATIONS_SCHEMA))
    return cur.fetchone() is not None


def fetch_applied(conn) -> dict[str, dict[str, Any]]:
    """Return {migration_id: {sha256, filename, applied_at}} from the tracking table.

    READ-ONLY: if the tracking table does not exist yet, returns {} WITHOUT
    creating it (only ``apply`` creates the table).
    """
    if not tracking_table_exists(conn):
        return {}
    cur = conn.cursor()
    cur.execute(
        f"SELECT migration_id, sha256, filename, applied_at FROM {MIG_FQN}"
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        # Support both pyodbc Row (attribute access) and plain tuples (test fakes).
        if hasattr(row, "migration_id"):
            mid = row.migration_id
            out[mid] = {
                "sha256": row.sha256,
                "filename": row.filename,
                "applied_at": _to_str(row.applied_at),
            }
        else:
            mid = row[0]
            out[mid] = {
                "sha256": row[1],
                "filename": row[2],
                "applied_at": _to_str(row[3]),
            }
    return out


def _to_str(value) -> Any:
    """JSON-safe scalar (datetimes -> isoformat, else passthrough)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def record_applied(conn, mig_id: str, filename: str, sha: str,
                   duration_ms: int | None = None) -> None:
    """Insert a tracking row for a successfully applied migration."""
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO {MIG_FQN} (migration_id, filename, sha256, duration_ms) "
        f"VALUES (?, ?, ?, ?)",
        (mig_id, filename, sha, duration_ms),
    )


def apply_migration_sql(conn, sql: str, *, dry_run: bool = False) -> int:
    """Execute one migration's SQL inside a SINGLE transaction for the file.

    The SQL is split into GO batches (``dbschema.split_go_batches``); each batch
    runs via ``cursor.execute``. Our connection is autocommit=True, so we open an
    explicit transaction with ``BEGIN TRAN`` and either ``COMMIT`` (apply) or
    ``ROLLBACK`` (dry-run / on error) — giving file-level atomicity and a no-op
    validation mode.

    Returns the number of batches executed. Re-raises on the first batch error
    after rolling the file's transaction back.

    Known limitation: ``split_go_batches`` splits on any line that is exactly
    ``GO`` — a ``GO`` alone on a line inside a string literal or block comment is
    still treated as a batch separator (documented in dbschema.split_go_batches).
    """
    batches = dbschema.split_go_batches(sql)
    cur = conn.cursor()
    cur.execute("SET XACT_ABORT ON; BEGIN TRANSACTION;")
    executed = 0
    try:
        for batch in batches:
            if not batch.strip():
                continue
            cur.execute(batch)
            executed += 1
    except Exception:
        try:
            cur.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;")
        except Exception:  # noqa: BLE001
            pass
        raise
    if dry_run:
        cur.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;")
    else:
        cur.execute("IF @@TRANCOUNT > 0 COMMIT TRANSACTION;")
    return executed
