"""sqlserver dispatch + introspection tests against an injected fake cursor.

No live DB and no pyodbc are needed: we inject a ``conn_factory`` into
``dispatch`` so query/tables/columns run against a recording fake. The
connection-string builder + masking are tested directly.
"""
from __future__ import annotations

import datetime as dt
import decimal

import pytest

from tools._lib import dbquery
from tools.sqlserver import connection, main


# --- fake DBAPI -------------------------------------------------------------

class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.executed = []           # list of (sql, params)
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        self.closed = True


class FakeConn:
    """Returns a queued cursor on each .cursor() call."""

    def __init__(self, queue):
        self._queue = list(queue)
        self.cursors = []
        self.closed = False

    def cursor(self):
        cur = self._queue.pop(0)
        self.cursors.append(cur)
        return cur

    def close(self):
        self.closed = True


def _factory(*cursors):
    conn = FakeConn(cursors)
    return lambda _profile: conn, conn


# --- a profile must exist for needs_conn actions ----------------------------

@pytest.fixture
def one_profile(tmp_path, monkeypatch):
    """Point the tool's profile store at a tmp profiles.json with one profile,
    and stub creds so no real Credential Manager is touched."""
    from tools._lib import dbprofiles

    pfile = tmp_path / "profiles.json"
    monkeypatch.setattr(main, "PROFILES_PATH", pfile)
    monkeypatch.setattr(dbprofiles.creds, "has", lambda *a: False)
    monkeypatch.setattr(dbprofiles.creds, "get_optional", lambda *a: None)
    main._store().add("default", {"server": "h", "database": "d", "username": "u"})
    return pfile


# --- connection-string builder ---------------------------------------------

def test_build_dsn_includes_password_and_intent():
    profile = {"server": "h", "database": "d", "username": "u", "port": 1433}
    dsn = connection.build_dsn(profile, "secret")
    assert "Server=h,1433" in dsn
    assert "UID=u" in dsn
    assert "PWD=secret" in dsn
    assert "ApplicationIntent=ReadOnly" in dsn


def test_masked_dsn_hides_password():
    profile = {"server": "h", "database": "d", "username": "u"}
    masked = connection.masked_dsn(profile)
    assert "PWD=***" in masked
    assert "set" not in masked.split("PWD=")[1].split(";")[0].lower() or "***" in masked


def test_build_dsn_trusted_connection_when_no_username():
    dsn = connection.build_dsn({"server": "h", "database": "d"}, None)
    assert "Trusted_Connection=yes" in dsn
    assert "UID=" not in dsn


# --- run_query passes params through, never interpolates --------------------

def test_run_query_binds_params_and_coerces():
    cur = FakeCursor(
        description=[("id", None), ("ts", None), ("amt", None)],
        rows=[(1, dt.datetime(2026, 1, 1, 0, 0, 0), decimal.Decimal("9.99"))],
    )
    conn = FakeConn([cur])
    out = connection.run_query(conn, "SELECT * FROM t WHERE id = ?", [1], None)
    # params handed to the driver as a list, NOT spliced into the SQL string.
    assert cur.executed == [("SELECT * FROM t WHERE id = ?", [1])]
    assert out["columns"] == ["id", "ts", "amt"]
    assert out["rows"][0]["ts"] == "2026-01-01T00:00:00"
    assert out["rows"][0]["amt"] == "9.99"
    assert out["row_count"] == 1
    assert out["truncated"] is False


def test_run_query_truncates_to_max_rows():
    cur = FakeCursor(description=[("n", None)], rows=[(i,) for i in range(5)])
    out = connection.run_query(FakeConn([cur]), "SELECT n FROM t", None, 2)
    assert out["row_count"] == 2
    assert out["truncated"] is True


# --- dispatch: query --------------------------------------------------------

def test_dispatch_query_read_only_ok(one_profile):
    cur = FakeCursor(description=[("c", None)], rows=[(7,)])
    factory, conn = _factory(cur)
    result = main.dispatch(
        "query", ["--profile", "default", "--sql", "SELECT c FROM t"],
        conn_factory=factory,
    )
    assert result["rows"] == [{"c": 7}]
    assert result["write"] is False
    assert conn.closed is True


def test_dispatch_query_blocks_write_without_flag(one_profile):
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    with pytest.raises(dbquery.WriteGuardError):
        main.dispatch(
            "query", ["--profile", "default", "--sql", "DELETE FROM t"],
            conn_factory=factory,
        )


def test_dispatch_query_allows_write_with_flag(one_profile):
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    result = main.dispatch(
        "query",
        ["--profile", "default", "--sql", "DELETE FROM t WHERE id=?",
         "--params", "[1]", "--write"],
        conn_factory=factory,
    )
    assert result["write"] is True
    assert result["row_count"] == 0


def test_dispatch_query_normalizes_lf_to_crlf(one_profile):
    """DDL sent with LF-only newlines is CRLF-normalized before execution, so
    SQL Server stores a consistent object definition (no SSMS EOL warning)."""
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    result = main.dispatch(
        "query",
        ["--profile", "default", "--write", "--sql",
         "ALTER PROCEDURE p AS\nBEGIN\nSELECT 1\nEND"],
        conn_factory=factory,
    )
    executed_sql = cur.executed[0][0]
    assert "\r\n" in executed_sql
    assert "\n" not in executed_sql.replace("\r\n", "")   # no lone LF remains
    assert result["eol_normalized"] is True


def test_dispatch_query_no_normalize_eol_preserves_lf(one_profile):
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    result = main.dispatch(
        "query",
        ["--profile", "default", "--write", "--no-normalize-eol", "--sql",
         "ALTER PROCEDURE p AS\nBEGIN\nSELECT 1\nEND"],
        conn_factory=factory,
    )
    executed_sql = cur.executed[0][0]
    assert "\r\n" not in executed_sql            # left exactly as passed
    assert executed_sql.count("\n") == 3
    assert result["eol_normalized"] is False


def test_dispatch_query_bad_params_json(one_profile):
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    with pytest.raises(main.UsageError):
        main.dispatch(
            "query",
            ["--profile", "default", "--sql", "SELECT 1", "--params", "{not json}"],
            conn_factory=factory,
        )


# --- dispatch: tables / columns --------------------------------------------

def test_dispatch_tables(one_profile):
    cur = FakeCursor(
        description=[("TABLE_SCHEMA", None), ("TABLE_NAME", None), ("TABLE_TYPE", None)],
        rows=[("dbo", "Customer", "BASE TABLE")],
    )
    factory, _ = _factory(cur)
    result = main.dispatch("tables", ["--profile", "default"], conn_factory=factory)
    assert result["count"] == 1
    assert result["tables"][0]["TABLE_NAME"] == "Customer"


def test_dispatch_tables_schema_is_parameterised(one_profile):
    cur = FakeCursor(description=[("TABLE_SCHEMA", None)], rows=[])
    factory, _ = _factory(cur)
    main.dispatch("tables", ["--profile", "default", "--schema", "dbo"],
                  conn_factory=factory)
    sql, params = cur.executed[0]
    assert "?" in sql and params == ["dbo"]      # bound, not interpolated


def test_dispatch_columns_splits_schema_qualified(one_profile):
    cur = FakeCursor(description=[("COLUMN_NAME", None)], rows=[("id",)])
    factory, _ = _factory(cur)
    main.dispatch("columns", ["--profile", "default", "--table", "dbo.Customer"],
                  conn_factory=factory)
    sql, params = cur.executed[0]
    assert params == ["Customer", "dbo"]


# --- dispatch: errors -------------------------------------------------------

def test_dispatch_unknown_action():
    with pytest.raises(main.UsageError):
        main.dispatch("nope", [])


def test_dispatch_missing_required_arg():
    with pytest.raises(main.UsageError):
        main.dispatch("query", ["--profile", "default"])     # no --sql


def test_dispatch_unknown_profile_raises_profile_error(tmp_path, monkeypatch):
    from tools._lib import dbprofiles
    monkeypatch.setattr(main, "PROFILES_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(dbprofiles.creds, "has", lambda *a: False)
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    with pytest.raises(dbprofiles.ProfileError):
        main.dispatch("query", ["--profile", "ghost", "--sql", "SELECT 1"],
                      conn_factory=factory)


# --- multiple databases per profile: --database override --------------------

def test_build_dsn_omits_database_when_absent():
    # a server+login-only profile connects to the login's default database
    dsn = connection.build_dsn({"server": "h", "username": "u"}, "s")
    assert "Database=" not in dsn


def test_dispatch_query_database_override(one_profile):
    """--database overrides the profile's database, so ONE profile (one server +
    login + credential) can query any database on that server."""
    captured = {}
    conn = FakeConn([FakeCursor(description=[("c", None)], rows=[(1,)])])

    def factory(profile):
        captured["db"] = profile.get("database")
        return conn

    main.dispatch(
        "query",
        ["--profile", "default", "--sql", "SELECT c FROM t", "--database", "OtherDB"],
        conn_factory=factory,
    )
    assert captured["db"] == "OtherDB"      # overrode the profile's "d"
