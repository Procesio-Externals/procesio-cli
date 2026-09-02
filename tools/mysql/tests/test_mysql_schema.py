"""schema-extract / schema-diff / migrate tests for the mysql tool.

No live DB, no pymysql socket: a scripted fake connection answers the
INFORMATION_SCHEMA enumeration + SHOW CREATE / tracking-table queries by
matching on a substring of the SQL. Mirror writes go to tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools._lib import dbschema
from tools.mysql import main, schema


# --- scripted fake DB-API (DictCursor: rows are dicts) ----------------------

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._result: list[dict] = []
        self.closed = False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, list(params) if params else None))
        self._result = self.conn._answer(sql, params)

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        self.closed = True


class FakeConn:
    """Answers queries by scanning ``rules`` (substring -> rows or callable)."""

    def __init__(self, rules):
        self.rules = rules
        self.executed: list[tuple] = []
        self.began = 0
        self.committed = 0
        self.rolled_back = 0
        self.closed = False

    def _answer(self, sql, params):
        for needle, value in self.rules:
            if needle in sql:
                return value(params) if callable(value) else list(value)
        return []

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        self.began += 1

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


# --- extract_objects --------------------------------------------------------

def _extract_rules():
    return [
        ("SELECT DATABASE()", [{"db": "redmine"}]),
        ("TABLE_TYPE = %s",
         lambda p: ([{"TABLE_NAME": "issues"}] if p and p[-1] == "BASE TABLE"
                    else [{"TABLE_NAME": "v_open"}] if p and p[-1] == "VIEW" else [])),
        ("ROUTINE_TYPE = %s",
         lambda p: ([{"ROUTINE_NAME": "do_thing"}] if p and p[-1] == "PROCEDURE"
                    else [{"ROUTINE_NAME": "calc"}] if p and p[-1] == "FUNCTION" else [])),
        ("INFORMATION_SCHEMA.TRIGGERS", [{"TRIGGER_NAME": "trg_ins"}]),
        ("INFORMATION_SCHEMA.EVENTS", [{"EVENT_NAME": "nightly"}]),
        ("SHOW CREATE TABLE", [{"Table": "issues", "Create Table": "CREATE TABLE `issues` (\n  id int\n)"}]),
        ("SHOW CREATE VIEW", [{"View": "v_open", "Create View": "CREATE VIEW `v_open` AS SELECT 1"}]),
        ("SHOW CREATE PROCEDURE", [{"Procedure": "do_thing", "Create Procedure": "CREATE PROCEDURE do_thing() BEGIN END"}]),
        ("SHOW CREATE FUNCTION", [{"Function": "calc", "Create Function": "CREATE FUNCTION calc() RETURNS INT RETURN 1"}]),
        ("SHOW CREATE TRIGGER", [{"Trigger": "trg_ins", "SQL Original Statement": "CREATE TRIGGER trg_ins BEFORE INSERT ON issues FOR EACH ROW SET @x=1"}]),
        ("SHOW CREATE EVENT", [{"Event": "nightly", "Create Event": "CREATE EVENT nightly ON SCHEDULE EVERY 1 DAY DO SELECT 1"}]),
    ]


def test_extract_objects_all_types():
    conn = FakeConn(_extract_rules())
    records = schema.extract_objects(conn)
    by_type = {r["type"]: r for r in records}
    assert set(by_type) == {"Tables", "Views", "Procedures", "Functions",
                            "Triggers", "Events"}
    assert by_type["Tables"]["name"] == "issues"
    assert by_type["Tables"]["schema"] == "redmine"
    assert by_type["Tables"]["definition"].startswith("CREATE TABLE `issues`")
    # trigger uses the 'SQL Original Statement' key
    assert by_type["Triggers"]["definition"].startswith("CREATE TRIGGER trg_ins")
    # definitions are LF-normalized and newline-terminated
    for r in records:
        assert "\r" not in r["definition"]
        assert r["definition"].endswith("\n")


def test_extract_objects_types_filter():
    conn = FakeConn(_extract_rules())
    records = schema.extract_objects(conn, types="TABLE,VIEW")
    assert {r["type"] for r in records} == {"Tables", "Views"}


def test_create_value_falls_back_case_insensitive():
    # MariaDB casing variant: 'create table' lowercase key
    assert schema._create_value({"Table": "t", "create table": "CREATE TABLE t"},
                                "Create Table") == "CREATE TABLE t"


# --- schema-extract dispatch (conn_factory injection -> tmp_path) -----------

@pytest.fixture
def one_profile(tmp_path, monkeypatch):
    from tools._lib import dbprofiles
    pfile = tmp_path / "profiles.json"
    monkeypatch.setattr(main, "PROFILES_PATH", pfile)
    monkeypatch.setattr(dbprofiles.creds, "has", lambda *a: False)
    monkeypatch.setattr(dbprofiles.creds, "get_optional", lambda *a: None)
    main._store().add("default", {"host": "h", "database": "d", "username": "u"})
    return pfile


def test_schema_extract_dispatch_writes_mirror(one_profile, tmp_path):
    out = tmp_path / "mirror"
    conn = FakeConn(_extract_rules())
    result = main.dispatch(
        "schema-extract",
        ["--profile", "default", "--out", str(out)],
        conn_factory=lambda _p: conn,
    )
    assert result["written"] == 6
    assert result["total"] == 6
    assert result["by_type"]["Tables"] == 1
    # files on disk + manifest
    assert (out / "schema" / "Tables" / "redmine.issues.sql").is_file()
    manifest = json.loads((out / "_manifest.json").read_text(encoding="utf-8"))
    assert any("issues" in rel for rel in manifest)
    assert conn.closed is True


def test_schema_extract_dry_run_writes_nothing(one_profile, tmp_path):
    out = tmp_path / "mirror"
    conn = FakeConn(_extract_rules())
    result = main.dispatch(
        "schema-extract",
        ["--profile", "default", "--out", str(out), "--dry-run"],
        conn_factory=lambda _p: conn,
    )
    assert result["dry_run"] is True
    assert result["written"] == 6
    assert not out.exists()          # nothing written to disk


def test_schema_extract_incremental_second_run(one_profile, tmp_path):
    out = tmp_path / "mirror"
    main.dispatch("schema-extract", ["--profile", "default", "--out", str(out)],
                  conn_factory=lambda _p: FakeConn(_extract_rules()))
    # second run, identical objects -> nothing written
    result = main.dispatch("schema-extract", ["--profile", "default", "--out", str(out)],
                           conn_factory=lambda _p: FakeConn(_extract_rules()))
    assert result["written"] == 0
    assert result["unchanged"] == 6


# --- schema-diff dir-vs-dir (no DB) ----------------------------------------

def _make_mirror(root: Path, files: dict[str, str]):
    for rel, text in files.items():
        p = root / "schema" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def test_schema_diff_dir_vs_dir(tmp_path):
    left = tmp_path / "L"
    right = tmp_path / "R"
    _make_mirror(left, {"Tables/a.sql": "CREATE TABLE a (id int);\n",
                        "Tables/gone.sql": "CREATE TABLE gone (id int);\n"})
    _make_mirror(right, {"Tables/a.sql": "CREATE TABLE a (id bigint);\n",
                         "Tables/new.sql": "CREATE TABLE new (id int);\n"})
    result = main.dispatch("schema-diff", ["--left", str(left), "--right", str(right)])
    assert result["summary"] == {"added": 1, "removed": 1, "changed": 1}
    assert result["added"] == ["schema/Tables/new.sql"]
    assert result["removed"] == ["schema/Tables/gone.sql"]
    assert "bigint" in result["changed"][0]["diff"]


def test_schema_diff_no_diff_text(tmp_path):
    left = tmp_path / "L"
    right = tmp_path / "R"
    _make_mirror(left, {"Tables/a.sql": "x\n"})
    _make_mirror(right, {"Tables/a.sql": "y\n"})
    result = main.dispatch(
        "schema-diff",
        ["--left", str(left), "--right", str(right), "--no-diff-text"])
    assert result["summary"]["changed"] == 1
    assert "diff" not in result["changed"][0]


def test_schema_diff_rejects_bad_dir(tmp_path):
    left = tmp_path / "L"
    _make_mirror(left, {"Tables/a.sql": "x\n"})
    with pytest.raises(main.UsageError):
        main.dispatch("schema-diff",
                      ["--left", str(left), "--right", str(tmp_path / "nope")])


# --- migrate: list + apply gating -------------------------------------------

def _migrations_dir(tmp_path: Path) -> Path:
    d = tmp_path / "migs"
    d.mkdir()
    (d / "0001_create_t.sql").write_text("CREATE TABLE t (id int);\n", encoding="utf-8")
    (d / "0002_drop_t.sql").write_text("DROP TABLE t;\n", encoding="utf-8")
    return d


def _migrate_rules(applied_rows):
    return [
        ("information_schema.tables", [{"x": 1}]),   # tracking_table_exists -> exists
        ("CREATE TABLE IF NOT EXISTS", []),          # ensure_migrations_table (apply only)
        (f"FROM `{schema.MIGRATIONS_TABLE}`", applied_rows),  # fetch_applied
    ]


def test_migrate_list_pending_and_drift(one_profile, tmp_path):
    d = _migrations_dir(tmp_path)
    # 0001 already applied, but with a STALE sha -> drift
    applied = [{"migration_id": "0001_create_t", "filename": "0001_create_t.sql",
                "sha256": "deadbeef", "applied_at": None}]
    conn = FakeConn(_migrate_rules(applied))
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(d), "--mode", "list"],
        conn_factory=lambda _p: conn,
    )
    assert result["applied_count"] == 1
    assert result["pending_count"] == 1
    assert result["pending"][0]["migration_id"] == "0002_drop_t"
    # 0002 drops a table -> danger warning surfaced
    assert any("DROP" in w for w in result["pending"][0]["danger_warnings"])
    assert result["drift"] == ["0001_create_t"]


def test_migrate_list_is_read_only_when_table_absent(one_profile, tmp_path):
    """`list` must NEVER create the tracking table (read-only on production DBs)."""
    d = _migrations_dir(tmp_path)
    conn = FakeConn([("information_schema.tables", [])])   # tracking table absent
    result = main.dispatch(
        "migrate", ["--profile", "default", "--dir", str(d), "--mode", "list"],
        conn_factory=lambda _p: conn)
    assert result["applied_count"] == 0 and result["pending_count"] == 2
    assert not any("CREATE TABLE" in sql.upper() for sql, _ in conn.executed)


def test_migrate_apply_requires_apply_flag(one_profile, tmp_path):
    d = _migrations_dir(tmp_path)
    conn = FakeConn(_migrate_rules([]))
    with pytest.raises(main.UsageError) as ei:
        main.dispatch(
            "migrate",
            ["--profile", "default", "--dir", str(d), "--mode", "apply"],
            conn_factory=lambda _p: conn,
        )
    assert "--apply" in str(ei.value)


def test_migrate_apply_runs_pending_and_records(one_profile, tmp_path):
    d = _migrations_dir(tmp_path)
    conn = FakeConn(_migrate_rules([]))
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(d), "--mode", "apply", "--apply"],
        conn_factory=lambda _p: conn,
    )
    statuses = [r["status"] for r in result["applied_results"]]
    assert statuses == ["applied", "applied"]
    # two files applied -> two transactions committed + two tracking inserts
    assert conn.committed == 2
    inserts = [s for s, _ in conn.executed if "INSERT INTO" in s and schema.MIGRATIONS_TABLE in s]
    assert len(inserts) == 2


def test_migrate_apply_dry_run_rolls_back(one_profile, tmp_path):
    d = _migrations_dir(tmp_path)
    conn = FakeConn(_migrate_rules([]))
    result = main.dispatch(
        "migrate",
        ["--profile", "default", "--dir", str(d), "--mode", "apply",
         "--apply", "--dry-run"],
        conn_factory=lambda _p: conn,
    )
    assert all(r["status"] == "dry-run" for r in result["applied_results"])
    assert conn.rolled_back == 2
    assert conn.committed == 0
    # no tracking inserts on dry-run
    assert not any("INSERT INTO" in s and schema.MIGRATIONS_TABLE in s
                   for s, _ in conn.executed)


def test_migrate_apply_refuses_on_drift(one_profile, tmp_path):
    d = _migrations_dir(tmp_path)
    applied = [{"migration_id": "0001_create_t", "filename": "0001_create_t.sql",
                "sha256": "stale", "applied_at": None}]
    conn = FakeConn(_migrate_rules(applied))
    with pytest.raises(main.UsageError) as ei:
        main.dispatch(
            "migrate",
            ["--profile", "default", "--dir", str(d), "--mode", "apply", "--apply"],
            conn_factory=lambda _p: conn,
        )
    assert "drift" in str(ei.value).lower()


# --- shared dbschema migration helpers (sanity, no DB) ----------------------

def test_discover_and_pending(tmp_path):
    d = _migrations_dir(tmp_path)
    found, skipped = dbschema.discover_migrations(d)
    assert [mid for mid, _ in found] == ["0001_create_t", "0002_drop_t"]
    assert skipped == []
    pend = dbschema.pending({"0001_create_t"}, found)
    assert [mid for mid, _ in pend] == ["0002_drop_t"]
