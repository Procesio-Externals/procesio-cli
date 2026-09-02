"""Unit tests for the shared, pure tools/_lib/dbquery.py. No DB required."""
from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid

import pytest

from tools._lib import dbquery


# --- write guard: blocks ----------------------------------------------------

@pytest.mark.parametrize("kw", dbquery.WRITE_KEYWORDS)
def test_guard_blocks_every_write_keyword(kw):
    sql = f"{kw} something here"
    assert dbquery.is_write_sql(sql)
    with pytest.raises(dbquery.WriteGuardError):
        dbquery.assert_read_only(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO t (a) VALUES (1)",
    "UPDATE t SET a=1 WHERE id=2",
    "DELETE FROM t WHERE id=2",
    "MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPDATE SET a=1",
    "TRUNCATE TABLE t",
    "DROP TABLE t",
    "ALTER TABLE t ADD c INT",
    "CREATE TABLE t (a INT)",
    "GRANT SELECT ON t TO u",
    "EXEC dbo.sp_do_thing",
    "EXECUTE dbo.sp_do_thing",
    "CALL do_thing()",
    "REPLACE INTO t (a) VALUES (1)",
])
def test_guard_blocks_representative_writes(sql):
    with pytest.raises(dbquery.WriteGuardError):
        dbquery.assert_read_only(sql)


def test_guard_blocks_multi_statement_batch():
    with pytest.raises(dbquery.WriteGuardError):
        dbquery.assert_read_only("SELECT 1; SELECT 2")


def test_guard_blocks_select_then_delete():
    with pytest.raises(dbquery.WriteGuardError):
        dbquery.assert_read_only("SELECT 1; DELETE FROM t WHERE id=1")


def test_guard_blocks_lowercase():
    with pytest.raises(dbquery.WriteGuardError):
        dbquery.assert_read_only("insert into t values (1)")


# --- write guard: allows ----------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "SELECT TOP 10 * FROM dbo.Customer",
    "SELECT * FROM t WHERE name = 'DELETE me'",          # keyword in a literal
    'SELECT "UPDATE" AS col',                             # keyword in dq-string
    "SELECT * FROM [DROP_log]",                           # T-SQL bracketed ident
    "SELECT * FROM `delete_log`",                         # MySQL backtick ident
    "SELECT 1 -- INSERT here is a comment",
    "SELECT 1 # DELETE here is a comment",
    "SELECT 1 /* CREATE block comment */",
    "WITH r AS (SELECT id FROM t) SELECT COUNT(*) FROM r",  # CTE
    "SHOW CREATE TABLE issues",                           # read-only DDL inspection
    "SELECT 1;",                                          # single statement, trailing ;
])
def test_guard_allows_read_only(sql):
    dbquery.assert_read_only(sql)        # must not raise
    assert not dbquery.is_write_sql(sql)


def test_guard_bypassed_with_write_flag():
    # write=True bypasses the guard entirely (the tool confirmed --write).
    dbquery.assert_read_only("DELETE FROM t WHERE id=1", write=True)
    dbquery.assert_read_only("SELECT 1; UPDATE t SET a=1", write=True)


def test_message_names_the_keyword():
    with pytest.raises(dbquery.WriteGuardError) as ei:
        dbquery.assert_read_only("UPDATE t SET a=1")
    assert "UPDATE" in str(ei.value)


# --- params are never interpolated ------------------------------------------

def test_guard_runs_on_sql_text_not_param_values():
    # The guard only sees the SQL string; a write keyword living in a *param
    # value* (a separate sequence the DBAPI binds) never reaches the guard,
    # proving values are not concatenated into the SQL we check.
    sql = "SELECT * FROM t WHERE note = ?"
    params = ["DELETE FROM t"]          # malicious-looking value, but it's a param
    dbquery.assert_read_only(sql)        # SQL itself is a plain SELECT -> allowed
    assert "DELETE" not in sql           # value is not in the statement text
    assert params == ["DELETE FROM t"]   # untouched


# --- json_safe coercion -----------------------------------------------------

def test_json_safe_datetime_date_time():
    assert dbquery.json_safe(dt.datetime(2026, 6, 29, 13, 30, 5)) == "2026-06-29T13:30:05"
    assert dbquery.json_safe(dt.date(2026, 6, 29)) == "2026-06-29"
    assert dbquery.json_safe(dt.time(13, 30, 5)) == "13:30:05"


def test_json_safe_timedelta_decimal():
    assert dbquery.json_safe(dt.timedelta(hours=1, minutes=30)) == 5400.0
    assert dbquery.json_safe(decimal.Decimal("19.99")) == "19.99"


def test_json_safe_bytes_uuid_memoryview():
    assert dbquery.json_safe(b"\x00\xff") == "00ff"
    assert dbquery.json_safe(bytearray(b"\x01\x02")) == "0102"
    assert dbquery.json_safe(memoryview(b"\xab")) == "ab"
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert dbquery.json_safe(u) == "12345678-1234-5678-1234-567812345678"


def test_json_safe_primitives_passthrough():
    for v in (None, "x", 3, 3.5, True):
        assert dbquery.json_safe(v) == v


def test_rows_to_dicts_is_json_serialisable():
    columns = ["id", "ts", "amount", "blob", "uid"]
    raw = [
        (1, dt.datetime(2026, 1, 2, 3, 4, 5), decimal.Decimal("10.5"),
         b"\xde\xad", uuid.UUID("00000000-0000-0000-0000-000000000001")),
    ]
    rows = dbquery.rows_to_dicts(columns, raw)
    # The whole structure must round-trip through json.dumps without a default=.
    text = json.dumps(rows)
    back = json.loads(text)
    assert back[0]["ts"] == "2026-01-02T03:04:05"
    assert back[0]["amount"] == "10.5"
    assert back[0]["blob"] == "dead"
    assert back[0]["uid"] == "00000000-0000-0000-0000-000000000001"


def test_rows_to_dicts_accepts_dict_rows():
    columns = ["id", "name"]
    raw = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert dbquery.rows_to_dicts(columns, raw) == raw


# --- cap_rows ---------------------------------------------------------------

def test_cap_rows_truncates_and_flags():
    rows, truncated = dbquery.cap_rows([1, 2, 3, 4, 5], 3)
    assert rows == [1, 2, 3]
    assert truncated is True


def test_cap_rows_no_truncation_when_under_cap():
    rows, truncated = dbquery.cap_rows([1, 2], 3)
    assert rows == [1, 2]
    assert truncated is False


def test_cap_rows_none_or_zero_means_unbounded():
    for cap in (None, 0, -1):
        rows, truncated = dbquery.cap_rows([1, 2, 3], cap)
        assert rows == [1, 2, 3]
        assert truncated is False


# --- normalize_eol ----------------------------------------------------------

def test_normalize_eol_lf_to_crlf():
    assert dbquery.normalize_eol("a\nb\nc") == "a\r\nb\r\nc"


def test_normalize_eol_collapses_existing_crlf_no_doubling():
    # already-CRLF text must stay single CRLF, never CR CR LF.
    assert dbquery.normalize_eol("a\r\nb") == "a\r\nb"
    assert "\r\r" not in dbquery.normalize_eol("a\r\nb\nc\r\nd")


def test_normalize_eol_handles_lone_cr():
    assert dbquery.normalize_eol("a\rb") == "a\r\nb"


def test_normalize_eol_mixed_endings_become_uniform_crlf():
    out = dbquery.normalize_eol("a\nb\r\nc\rd")
    assert out == "a\r\nb\r\nc\r\nd"
    assert out.count("\n") == out.count("\r\n") == 3


def test_normalize_eol_lf_style_strips_cr():
    assert dbquery.normalize_eol("a\r\nb\rc", style="lf") == "a\nb\nc"


def test_normalize_eol_no_newlines_unchanged():
    assert dbquery.normalize_eol("SELECT 1") == "SELECT 1"


def test_normalize_eol_rejects_unknown_style():
    with pytest.raises(ValueError):
        dbquery.normalize_eol("a\nb", style="mac")


# --- mask_dsn ---------------------------------------------------------------

def test_mask_dsn_hides_pyodbc_password():
    dsn = "Driver={X};Server=h;Database=d;UID=u;PWD=s3cr3t;APP=t;"
    masked = dbquery.mask_dsn(dsn)
    assert "s3cr3t" not in masked
    assert "PWD=***" in masked


def test_mask_dsn_hides_password_keyword_forms():
    assert "p@ss" not in dbquery.mask_dsn("host=h;password=p@ss;db=d")
    assert "p@ss" not in dbquery.mask_dsn("mysql://u:p@ss@h:3306/d")
