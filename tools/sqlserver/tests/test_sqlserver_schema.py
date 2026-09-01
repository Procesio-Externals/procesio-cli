"""Tests for the sqlserver schema-extract / schema-diff / migrate actions.

No live DB and no pyodbc: extraction runs against a FAKE cursor returning canned
catalog rows, dispatch injects a ``conn_factory``, and the diff dir-vs-dir path
needs no connection at all. The migrate ``list`` path uses a fake connection that
returns canned applied rows; the apply-without-``--apply`` guard is asserted.
"""
from __future__ import annotations

import pytest

from tools._lib import dbschema
from tools.sqlserver import main, schema


# --- programmable fake cursor/connection ------------------------------------

class FakeCursor:
    """Replays a queue of (description, rows) results across execute() calls.

    Each execute() advances to the next queued result; description/fetchall
    reflect the most recent execute. This models pyodbc's behaviour where the
    same cursor is reused for several queries (as schema._emit_table does).
    """

    def __init__(self, results):
        self._results = list(results)        # list[(description, rows)]
        self._i = -1
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        if self._i + 1 < len(self._results):
            self._i += 1

    @property
    def description(self):
        if self._i < 0:
            return None
        return self._results[self._i][0]

    def fetchall(self):
        if self._i < 0:
            return []
        return list(self._results[self._i][1])

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def close(self):
        pass


class FakeConn:
    """Hands out a queued cursor on each .cursor() call."""

    def __init__(self, cursor_queue):
        self._queue = list(cursor_queue)
        self.cursors = []
        self.closed = False

    def cursor(self):
        cur = self._queue.pop(0)
        self.cursors.append(cur)
        return cur

    def close(self):
        self.closed = True


def _desc(*names):
    return [(n, None) for n in names]


# --- a profile must exist for needs_conn actions ----------------------------

@pytest.fixture
def one_profile(tmp_path, monkeypatch):
    from tools._lib import dbprofiles

    pfile = tmp_path / "profiles.json"
    monkeypatch.setattr(main, "PROFILES_PATH", pfile)
    monkeypatch.setattr(dbprofiles.creds, "has", lambda *a: False)
    monkeypatch.setattr(dbprofiles.creds, "get_optional", lambda *a: None)
    main._store().add("default", {"server": "h", "database": "d", "username": "u"})
    return pfile


# ===========================================================================
# extract_objects against a fake cursor
# ===========================================================================

# canned module rows: a proc, a scalar function, a view, a trigger, plus an
# is_ms_shipped-style row already excluded by SQL, and an encrypted (NULL body).
_MODULE_DESC = _desc("schema_name", "object_name", "type_code", "type_desc", "body")
_MODULE_ROWS = [
    ("dbo", "GetCustomer", "P ", "SQL_STORED_PROCEDURE",
     "CREATE PROCEDURE dbo.GetCustomer AS SELECT 1\r\n"),
    ("dbo", "fnTax", "FN", "SQL_SCALAR_FUNCTION",
     "CREATE FUNCTION dbo.fnTax() RETURNS int AS BEGIN RETURN 1 END"),
    ("dbo", "vCustomer", "V", "VIEW", "CREATE VIEW dbo.vCustomer AS SELECT 1 AS x"),
    ("dbo", "trAudit", "TR", "SQL_TRIGGER", "CREATE TRIGGER dbo.trAudit ON dbo.t AFTER INSERT AS SELECT 1"),
    ("dbo", "secret", "P", "SQL_STORED_PROCEDURE", None),   # encrypted -> NULL body
]


def _modules_only_conn():
    return FakeConn([FakeCursor([(_MODULE_DESC, _MODULE_ROWS)])])


def test_extract_modules_verbatim_and_labels():
    recs = schema.extract_modules(_modules_only_conn())
    by_name = {r["name"]: r for r in recs}
    assert by_name["GetCustomer"]["type"] == "Procedures"
    assert by_name["fnTax"]["type"] == "Functions"
    assert by_name["vCustomer"]["type"] == "Views"
    assert by_name["trAudit"]["type"] == "Triggers"
    # CRLF normalised to LF, verbatim body preserved
    assert by_name["GetCustomer"]["definition"] == "CREATE PROCEDURE dbo.GetCustomer AS SELECT 1\n"
    # encrypted object surfaces a NOTE placeholder rather than being dropped
    assert "definition unavailable" in by_name["secret"]["definition"]


# --- table DDL generation ---------------------------------------------------

_TABLES_DESC = _desc("object_id", "schema_name", "table_name")
_TABLES_ROWS = [(10, "dbo", "Customer")]

_COLUMNS_DESC = _desc(
    "column_id", "column_name", "type_name", "max_length", "precision", "scale",
    "is_nullable", "is_identity", "seed_value", "increment_value", "collation_name",
    "computed_definition", "is_persisted", "default_definition", "default_name",
    "is_computed",
)
_COLUMNS_ROWS = [
    # Id INT IDENTITY(1,1) NOT NULL
    (1, "Id", "int", 4, 10, 0, 0, 1, "1", "1", None, None, 0, None, None, 0),
    # Name nvarchar(100) NOT NULL with a default
    (2, "Name", "nvarchar", 200, 0, 0, 0, 0, None, None, "Latin1_General_CI_AS",
     None, 0, "('x')", "DF_Customer_Name", 0),
    # Notes nvarchar(MAX) NULL
    (3, "Notes", "nvarchar", -1, 0, 0, 1, 0, None, None, "Latin1_General_CI_AS",
     None, 0, None, None, 0),
]

_PK_DESC = _desc("constraint_name", "type_desc", "column_name", "is_descending_key", "key_ordinal")
_PK_ROWS = [("PK_Customer", "CLUSTERED", "Id", 0, 1)]

_INDEX_DESC = _desc("index_id", "index_name", "type_desc", "is_unique",
                    "filter_definition", "column_name", "is_descending_key",
                    "is_included_column", "key_ordinal")
_INDEX_ROWS = [(2, "IX_Customer_Name", "NONCLUSTERED", 0, None, "Name", 0, 0, 1)]

_FK_DESC = _desc("fk_name", "ref_schema", "ref_table", "parent_column", "ref_column",
                 "delete_referential_action_desc", "update_referential_action_desc",
                 "constraint_column_id")
_FK_ROWS = [("FK_Customer_Region", "dbo", "Region", "RegionId", "Id",
             "NO_ACTION", "NO_ACTION", 1)]

_CHECK_DESC = _desc("constraint_name", "definition", "is_disabled")
_CHECK_ROWS = []


def _tables_conn():
    # extract_tables: 1 cursor for the TABLES list, then one cursor reused for the
    # five per-table queries (columns, pk, index, fk, check).
    tables_cur = FakeCursor([(_TABLES_DESC, _TABLES_ROWS)])
    table_detail_cur = FakeCursor([
        (_COLUMNS_DESC, _COLUMNS_ROWS),
        (_PK_DESC, _PK_ROWS),
        (_INDEX_DESC, _INDEX_ROWS),
        (_FK_DESC, _FK_ROWS),
        (_CHECK_DESC, _CHECK_ROWS),
    ])
    return FakeConn([tables_cur, table_detail_cur])


def test_extract_tables_generates_create_ddl():
    recs = schema.extract_tables(_tables_conn())
    assert len(recs) == 1
    rec = recs[0]
    assert rec["type"] == "Tables"
    assert rec["schema"] == "dbo" and rec["name"] == "Customer"
    ddl = rec["definition"]
    assert "CREATE TABLE [dbo].[Customer]" in ddl
    assert "[Id] int IDENTITY(1,1) NOT NULL" in ddl
    assert "[Name] nvarchar(100)" in ddl                  # 200 bytes / 2 = 100 chars
    # nvarchar(MAX), nullable, with collation between type and nullability
    assert "[Notes] nvarchar(MAX)" in ddl
    assert "[Notes] nvarchar(MAX) COLLATE Latin1_General_CI_AS NULL" in ddl
    assert "CONSTRAINT [PK_Customer] PRIMARY KEY CLUSTERED ([Id])" in ddl
    assert "CREATE NONCLUSTERED INDEX [IX_Customer_Name]" in ddl
    assert "ADD CONSTRAINT [FK_Customer_Region] FOREIGN KEY ([RegionId])" in ddl
    assert "REFERENCES [dbo].[Region] ([Id])" in ddl


def test_extract_objects_types_filter_modules_only():
    # only modules cursor needed when U is excluded
    recs = schema.extract_objects(_modules_only_conn(), types=["P", "V"])
    labels = {r["type"] for r in recs}
    # Procedures + Views kept; Functions/Triggers dropped by the family filter
    assert "Procedures" in labels and "Views" in labels
    assert "Functions" not in labels and "Triggers" not in labels
    assert "Tables" not in labels


# ===========================================================================
# schema-extract dispatch -> writes a mirror under tmp_path
# ===========================================================================

def test_dispatch_schema_extract_writes_mirror(one_profile, tmp_path):
    out = tmp_path / "mirror"
    conn = _modules_only_conn()
    result = main.dispatch(
        "schema-extract",
        ["--profile", "default", "--types", "P,V,FN,TR", "--out", str(out)],
        conn_factory=lambda _p: conn,
    )
    assert result["profile"] == "default"
    # proc, fn, view, trigger + the encrypted "secret" proc (NULL body -> NOTE placeholder,
    # still a record). --types P,V,FN,TR keeps all 5 module objects.
    assert result["written"] == 5
    assert (out / "_manifest.json").is_file()
    proc = out / "schema" / "Procedures" / "dbo.GetCustomer.sql"
    assert proc.is_file()
    assert proc.read_text(encoding="utf-8").startswith("CREATE PROCEDURE")
    assert conn.closed is True


def test_dispatch_schema_extract_dry_run_writes_nothing(one_profile, tmp_path):
    out = tmp_path / "mirror"
    result = main.dispatch(
        "schema-extract",
        ["--profile", "default", "--types", "P", "--out", str(out), "--dry-run"],
        conn_factory=lambda _p: _modules_only_conn(),
    )
    assert result["dry_run"] is True
    assert not out.exists()


# ===========================================================================
# schema-diff dir-vs-dir (no DB)
# ===========================================================================

def _make_mirror(root, files):
    schema_root = root / "schema"
    for rel, text in files.items():
        p = schema_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def test_dispatch_schema_diff_dirs(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    _make_mirror(left, {
        "Procedures/dbo.A.sql": "CREATE PROC A AS SELECT 1\n",
        "Views/dbo.Gone.sql": "CREATE VIEW Gone AS SELECT 1\n",
    })
    _make_mirror(right, {
        "Procedures/dbo.A.sql": "CREATE PROC A AS SELECT 2\n",   # changed
        "Views/dbo.New.sql": "CREATE VIEW New AS SELECT 1\n",     # added
    })
    result = main.dispatch("schema-diff", ["--left", str(left), "--right", str(right)])
    assert result["summary"] == {"added": 1, "removed": 1, "changed": 1}
    assert "schema/Views/dbo.New.sql" in result["added"]
    assert "schema/Views/dbo.Gone.sql" in result["removed"]
    assert result["changed"][0]["relpath"] == "schema/Procedures/dbo.A.sql"
    assert "diff" in result["changed"][0]            # unified diff present by default


def test_dispatch_schema_diff_no_diff_text(tmp_path):
    left = tmp_path / "l"
    right = tmp_path / "r"
    _make_mirror(left, {"Procedures/dbo.A.sql": "x\n"})
    _make_mirror(right, {"Procedures/dbo.A.sql": "y\n"})
    result = main.dispatch(
        "schema-diff",
        ["--left", str(left), "--right", str(right), "--no-diff-text"],
    )
    assert result["changed"][0]["relpath"] == "schema/Procedures/dbo.A.sql"
    assert "diff" not in result["changed"][0]


def test_dispatch_schema_diff_profile_side_extracts(one_profile, tmp_path):
    # left is a live profile (extracted via the fake cursor), right is an empty dir
    right = tmp_path / "right"
    (right / "schema").mkdir(parents=True)
    result = main.dispatch(
        "schema-diff",
        ["--left", "profile:default", "--right", str(right), "--types", "P,V,FN,TR"],
        conn_factory=lambda _p: _modules_only_conn(),
    )
    # everything in the extracted left is "removed" relative to the empty right
    assert result["summary"]["added"] == 0
    assert result["summary"]["removed"] >= 4


# ===========================================================================
# migrate
# ===========================================================================

class MigrateConn:
    """Fake connection for migrate: ensure-table is a no-op execute, then a SELECT
    on the tracking table returns canned applied rows."""

    def __init__(self, applied_rows, exists=True):
        self._applied_rows = applied_rows
        self._exists = exists
        self.executed = []

    def cursor(self):
        return self  # the conn is its own cursor for simplicity

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        self._last = sql

    def fetchall(self):
        if "SELECT migration_id" in self._last:
            return list(self._applied_rows)
        return []

    def fetchone(self):
        # tracking_table_exists probes sys.tables; report existence per self._exists.
        if "sys.tables" in self._last:
            return (1,) if self._exists else None
        return None

    def close(self):
        pass


def _write_migrations(d, files):
    d.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")


def test_migrate_list_applied_and_pending(one_profile, tmp_path):
    mig_dir = tmp_path / "migrations"
    _write_migrations(mig_dir, {
        "001_init.sql": "CREATE TABLE dbo.A (id int);\n",
        "002_drop.sql": "DROP TABLE dbo.A;\n",
    })
    # 001 already applied (matching sha so no drift); 002 pending
    sha001 = dbschema.sha256_file(mig_dir / "001_init.sql")
    applied = [("001_init", sha001, "001_init.sql", "2026-01-01T00:00:00")]
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(mig_dir), "--mode", "list"],
        conn_factory=lambda _p: MigrateConn(applied),
    )
    assert result["mode"] == "list"
    assert [a["migration_id"] for a in result["applied"]] == ["001_init"]
    assert [p["migration_id"] for p in result["pending"]] == ["002_drop"]
    assert result["drift"] == []
    # the pending DROP migration carries a danger warning
    assert any("destructive" in w for w in result["pending"][0]["danger_warnings"])


def test_migrate_list_is_read_only_even_without_tracking_table(one_profile, tmp_path):
    """`list` must NEVER create the tracking table (read-only on production DBs)."""
    mig_dir = tmp_path / "migrations"
    _write_migrations(mig_dir, {"001_init.sql": "SELECT 1;\n"})
    conn = MigrateConn([], exists=False)        # tracking table does not exist
    result = main.dispatch(
        "migrate", ["--profile", "default", "--dir", str(mig_dir), "--mode", "list"],
        conn_factory=lambda _p: conn)
    assert result["applied"] == [] and len(result["pending"]) == 1
    assert not any("CREATE TABLE" in sql.upper() for sql, _ in conn.executed)


def test_migrate_list_detects_drift(one_profile, tmp_path):
    mig_dir = tmp_path / "migrations"
    _write_migrations(mig_dir, {"001_init.sql": "SELECT 1;\n"})
    applied = [("001_init", "deadbeef" * 8, "001_init.sql", "2026-01-01T00:00:00")]
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(mig_dir), "--mode", "list"],
        conn_factory=lambda _p: MigrateConn(applied),
    )
    assert len(result["drift"]) == 1
    assert result["drift"][0]["migration_id"] == "001_init"


def test_migrate_apply_requires_apply_flag(one_profile, tmp_path):
    mig_dir = tmp_path / "migrations"
    _write_migrations(mig_dir, {"001_init.sql": "SELECT 1;\n"})
    with pytest.raises(main.UsageError, match="--apply"):
        main.dispatch(
            "migrate",
            ["--profile", "default", "--dir", str(mig_dir), "--mode", "apply"],
            conn_factory=lambda _p: MigrateConn([]),
        )


def test_migrate_apply_runs_pending(one_profile, tmp_path):
    mig_dir = tmp_path / "migrations"
    _write_migrations(mig_dir, {
        "001_init.sql": "CREATE TABLE dbo.A (id int);\nGO\nINSERT INTO dbo.A VALUES (1);\n",
    })
    conn = MigrateConn([])
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(mig_dir), "--mode", "apply", "--apply"],
        conn_factory=lambda _p: conn,
    )
    assert result["applied_now"] == 1
    assert result["results"][0]["status"] == "applied"
    assert result["results"][0]["batches"] == 2          # GO split into 2 batches
    # a tracking INSERT was issued
    assert any("INSERT INTO" in sql and "__schema_migrations" in sql
               for sql, _ in conn.executed)


def test_migrate_apply_dry_run_does_not_record(one_profile, tmp_path):
    mig_dir = tmp_path / "migrations"
    _write_migrations(mig_dir, {"001_init.sql": "SELECT 1;\n"})
    conn = MigrateConn([])
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(mig_dir),
         "--mode", "apply", "--apply", "--dry-run"],
        conn_factory=lambda _p: conn,
    )
    assert result["dry_run"] is True
    assert result["results"][0]["status"] == "dry-run-ok"
    # no tracking INSERT in dry-run
    assert not any("INSERT INTO" in sql and "__schema_migrations" in sql
                   for sql, _ in conn.executed)
    # but a ROLLBACK was issued for the file's transaction
    assert any("ROLLBACK" in sql for sql, _ in conn.executed)
