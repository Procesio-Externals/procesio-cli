"""mysql dispatch + introspection tests against an injected fake cursor.

No live DB and no pymysql are needed: we inject a ``conn_factory`` into
``dispatch``. The connection-kwargs builder + masked DSN are tested directly
(connection_kwargs imports pymysql only for the DictCursor class, which is
present in the venv, but never opens a socket).
"""
from __future__ import annotations

import datetime as dt
import decimal

import pytest

from tools._lib import dbquery
from tools.mysql import connection, main


# --- fake DBAPI (DictCursor-style: rows are dicts) --------------------------

class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class FakeConn:
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


@pytest.fixture
def one_profile(tmp_path, monkeypatch):
    from tools._lib import dbprofiles
    pfile = tmp_path / "profiles.json"
    monkeypatch.setattr(main, "PROFILES_PATH", pfile)
    monkeypatch.setattr(dbprofiles.creds, "has", lambda *a: False)
    monkeypatch.setattr(dbprofiles.creds, "get_optional", lambda *a: None)
    main._store().add("default", {"host": "h", "database": "d", "username": "u"})
    return pfile


def test_dispatch_query_database_override(one_profile):
    """--database overrides the profile's database, so ONE profile (one host +
    login + credential) can query any database on that host."""
    captured = {}
    conn = FakeConn([FakeCursor(description=[], rows=[])])

    def factory(profile):
        captured["db"] = profile.get("database")
        return conn

    main.dispatch(
        "query",
        ["--profile", "default", "--sql", "SELECT 1", "--database", "OtherDB"],
        conn_factory=factory,
    )
    assert captured["db"] == "OtherDB"      # overrode the profile's "d"


# --- connection kwargs ------------------------------------------------------

def test_connection_kwargs_basic():
    profile = {"host": "h", "database": "d", "username": "u", "port": 3307}
    k = connection.connection_kwargs(profile, "secret")
    assert k["host"] == "h"
    assert k["port"] == 3307
    assert k["user"] == "u"
    assert k["password"] == "secret"
    assert k["database"] == "d"
    assert k["autocommit"] is True
    assert "ssl" not in k                       # tls off by default


def test_connection_kwargs_tls_no_verify():
    profile = {"host": "h", "tls": True, "tls_verify_cert": False}
    k = connection.connection_kwargs(profile, "x")
    ctx = k["ssl"]
    assert ctx.check_hostname is False


def test_masked_dsn_hides_password():
    profile = {"host": "h", "database": "d", "username": "u"}
    masked = connection.masked_dsn(profile)
    assert ":***@" in masked
    assert "mysql://u:***@h:3306/d" in masked


# --- run_query: %s placeholders, dict rows, coercion ------------------------

def test_run_query_binds_params_and_coerces():
    cur = FakeCursor(
        description=[("id", None), ("ts", None), ("amt", None)],
        rows=[{"id": 1, "ts": dt.datetime(2026, 1, 1), "amt": decimal.Decimal("9.99")}],
    )
    out = connection.run_query(FakeConn([cur]),
                               "SELECT * FROM t WHERE id = %s", [1], None)
    assert cur.executed == [("SELECT * FROM t WHERE id = %s", [1])]
    assert out["rows"][0]["ts"] == "2026-01-01T00:00:00"
    assert out["rows"][0]["amt"] == "9.99"
    assert out["truncated"] is False


def test_run_query_truncates():
    cur = FakeCursor(description=[("n", None)],
                     rows=[{"n": i} for i in range(5)])
    out = connection.run_query(FakeConn([cur]), "SELECT n FROM t", None, 2)
    assert out["row_count"] == 2
    assert out["truncated"] is True


# --- dispatch ---------------------------------------------------------------

def test_dispatch_query_read_only_ok(one_profile):
    cur = FakeCursor(description=[("c", None)], rows=[{"c": 7}])
    factory, conn = _factory(cur)
    result = main.dispatch(
        "query", ["--profile", "default", "--sql", "SELECT c FROM t"],
        conn_factory=factory,
    )
    assert result["rows"] == [{"c": 7}]
    assert result["write"] is False
    assert conn.closed is True


def test_dispatch_query_blocks_replace_upsert(one_profile):
    # REPLACE is MySQL's upsert; the guard must block it read-only.
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    with pytest.raises(dbquery.WriteGuardError):
        main.dispatch(
            "query", ["--profile", "default", "--sql", "REPLACE INTO t VALUES (1)"],
            conn_factory=factory,
        )


def test_dispatch_query_allows_write_flag(one_profile):
    cur = FakeCursor(description=[], rows=[])
    factory, _ = _factory(cur)
    result = main.dispatch(
        "query",
        ["--profile", "default", "--sql", "DELETE FROM t WHERE id=%s",
         "--params", "[1]", "--write"],
        conn_factory=factory,
    )
    assert result["write"] is True


def test_dispatch_tables_default_database(one_profile):
    cur = FakeCursor(description=[("TABLE_NAME", None)], rows=[{"TABLE_NAME": "issues"}])
    factory, _ = _factory(cur)
    result = main.dispatch("tables", ["--profile", "default"], conn_factory=factory)
    sql, params = cur.executed[0]
    assert "DATABASE()" in sql                   # falls back to profile db
    assert result["tables"][0]["TABLE_NAME"] == "issues"


def test_dispatch_columns_parameterised(one_profile):
    cur = FakeCursor(description=[("COLUMN_NAME", None)], rows=[{"COLUMN_NAME": "id"}])
    factory, _ = _factory(cur)
    main.dispatch("columns", ["--profile", "default", "--table", "redmine.issues"],
                  conn_factory=factory)
    sql, params = cur.executed[0]
    assert "%s" in sql
    assert params == ["issues", "redmine"]


def test_dispatch_unknown_action():
    with pytest.raises(main.UsageError):
        main.dispatch("nope", [])


def test_dispatch_missing_required_arg():
    with pytest.raises(main.UsageError):
        main.dispatch("query", ["--profile", "default"])     # no --sql
