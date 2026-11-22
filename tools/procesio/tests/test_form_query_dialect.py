"""A form query written for SQL Server is warned about when it is saved or read.

A Data Store is MySQL-backed. The save does not read the statement, and a run of a statement
MySQL refuses answers only "invalid SQL syntax" or "could not be executed", without the place.
A writer that cannot run the query then rewrites it without learning what was wrong. The
warning names each SQL Server spelling and what MySQL takes instead.
"""
from __future__ import annotations

import json

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import queries as fq
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V", "workspace_id": "WS1"}
STORE, QID = "store-1", "11111111-1111-1111-1111-111111111111"
BINDINGS = [{"id": 1, "type": "dataStoreTable", "dataStoreId": STORE}]


def _found(sql: str) -> str:
    warnings = fq.dialect_warnings([{"name": "Q", "value": sql}])
    assert len(warnings) <= 1
    return warnings[0] if warnings else ""


@pytest.mark.parametrize("sql, spelling, mysql", [
    ("SELECT TOP 10 a FROM <%1%> ORDER BY a DESC", "SELECT TOP n", "LIMIT n"),
    ("select distinct top (5) a from <%1%>", "SELECT TOP n", "LIMIT n"),
    ("SELECT [Player Name] FROM <%1%>", "[bracketed] names", "backticks"),
    ("SELECT a FROM <%1%> ORDER BY a OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY",
     "OFFSET n ROWS FETCH NEXT m ROWS ONLY", "LIMIT m OFFSET n"),
    ("SELECT a FROM <%1%> WITH (NOLOCK)", "WITH (NOLOCK)", "leave it out"),
    ("INSERT INTO <%1%> (a) OUTPUT INSERTED.a VALUES (@a)", "OUTPUT INSERTED / DELETED", "SELECT"),
    ("SELECT a FROM dbo.<%1%>", "the dbo. schema prefix", "leave it out"),
    ("INSERT INTO <%1%> (id) VALUES (NEWID())", "NEWID()", "parameter"),
    ("UPDATE <%1%> SET t = getdate()", "GETDATE()", "NOW()"),
    ("UPDATE <%1%> SET t = SYSUTCDATETIME()", "SYSUTCDATETIME()", "UTC_TIMESTAMP()"),
    ("SELECT SCOPE_IDENTITY()", "SCOPE_IDENTITY()", "LAST_INSERT_ID()"),
    ("SELECT LEN(a) FROM <%1%>", "LEN()", "CHAR_LENGTH()"),
    ("SELECT IIF(a > 1, 'x', 'y') FROM <%1%>", "IIF()", "IF(condition, a, b)"),
    ("SELECT DATEADD(day, 1, t) FROM <%1%>", "DATEADD()", "DATE_ADD"),
    ("SELECT TRY_CONVERT(int, @a)", "TRY_CONVERT()", "CAST(value AS"),
    ("SELECT CONVERT(VARCHAR(10), @a)", "CONVERT(VARCHAR, value)", "CAST(value AS"),
    ("SELECT ISNULL(@a, 0)", "ISNULL(value, fallback)", "IFNULL"),
    ("SELECT DATEDIFF(day, a, b) FROM <%1%>", "DATEDIFF(unit, a, b)", "TIMESTAMPDIFF"),
    ("SELECT CAST(@a AS INT)", "CAST(... AS INT)", "SIGNED"),
    ("SELECT CAST(COALESCE(@a, (SELECT 1)) AS nvarchar(50))", "CAST(... AS NVARCHAR)", "CHAR"),
])
def test_a_sql_server_spelling_is_named_with_its_mysql_form(sql, spelling, mysql):
    warning = _found(sql)
    assert f"{spelling} (MySQL: " in warning
    assert mysql in warning.split(f"{spelling} (MySQL: ", 1)[1]
    assert warning.startswith("query 'Q' uses SQL Server spellings, and a Data Store runs MySQL")


@pytest.mark.parametrize("sql", [
    "SELECT a AS Player, b AS Score FROM <%1%> ORDER BY b DESC LIMIT 5 OFFSET 10",
    "SELECT IFNULL(a, 'x'), ISNULL(b), DATEDIFF(NOW(), t), CHAR_LENGTH(a) FROM <%1%>",
    "SELECT CAST(@s AS SIGNED), CAST(@d AS DECIMAL(10,2)), CONVERT(@s, SIGNED), UTC_TIMESTAMP()",
    "SELECT a FROM <%1%> WHERE b MEMBER OF (CAST(@numbers AS JSON))",
    # a spelling inside a string literal, a quoted name or a comment is text, not code
    "SELECT a FROM <%1%> WHERE b = '[x] GETDATE() TOP' AND c->'$[0]' = 1",
    "SELECT `top`, a FROM <%1%> /* SELECT TOP 1 NEWID() */ -- LEN(a)\nLIMIT 1",
    # a call that never closes is the run's to refuse; the scan does not guess
    "SELECT ISNULL(@a, 0",
    "",
])
def test_a_mysql_statement_draws_no_warning(sql):
    assert _found(sql) == ""


def test_one_warning_per_query_lists_each_spelling_once():
    sql = ("INSERT INTO <%1%> (a, b, t) VALUES (ISNULL(@a, 0), ISNULL(@b, 0), GETDATE()); "
           "SELECT TOP 1 [a], GETDATE() FROM <%1%>")
    warning = _found(sql)
    for spelling in ("SELECT TOP n", "[bracketed] names", "GETDATE()", "ISNULL(value, fallback)"):
        assert warning.count(spelling + " (MySQL: ") == 1
    assert "run the query once after saving it" in warning


def test_only_the_queries_that_need_it_are_named():
    warnings = fq.dialect_warnings([
        {"name": "Top scores", "value": "SELECT TOP 5 a FROM <%1%>"},
        {"name": "Fine", "value": "SELECT a FROM <%1%> LIMIT 5"},
        {"name": "No text"}])
    assert len(warnings) == 1 and warnings[0].startswith("query 'Top scores'")


# ------------------------------------------------------------------ where it is reported

def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _wire(sql: str) -> dict:
    return {"id": QID, "name": "Top scores", "value": sql,
            "variable": [{**b, "variableId": None, "attribute": None} for b in BINDINGS],
            "parameters": [], "timeoutSeconds": None}


def _form(sql: str) -> dict:
    event = {"id": "ev1", "type": "CLICK", "action": "RUN_DATA_STORE_OPERATION",
             "config": {"dataStoreId": None, "operation": "QUERY", "inputMap": [],
                        "outputMap": [], "filters": [], "queryId": QID}}
    return {"id": "F1", "name": "Scores", "isPrivate": False, "type": 1, "status": 1,
            "state": True, "assignees": [], "customUrl": None, "queries": [_wire(sql)],
            "data": {"code": "", "elements": [{"id": "b1", "type": "button", "configs": [
                {"id": "c1", "key": "name", "value": "load"},
                {"id": "c2", "key": "onClickEvents",
                 "value": {"debounce": 0, "events": [event]}}]}]}}


def test_the_form_warnings_include_it():
    form = _form("SELECT TOP 5 a FROM <%1%>")
    warnings = fq.warnings(form["queries"], form["data"]["elements"])
    assert len(warnings) == 1 and "SELECT TOP n" in warnings[0]


def test_form_get_queries_reports_a_stored_sql_server_statement():
    s = FakeSession(queue=[FakeResp(200, _form("SELECT TOP 5 a FROM <%1%> ORDER BY a DESC"))])
    out = _call("form-get-queries", ["--form-id", "F1"], s)
    assert len(out["warnings"]) == 1
    assert "SELECT TOP n (MySQL: LIMIT n at the end of the statement)" in out["warnings"][0]


def test_form_set_saved_statement_reports_it_and_still_saves():
    tsql = "SELECT TOP 5 a FROM <%1%> ORDER BY a DESC"
    s = FakeSession(queue=[FakeResp(200, _form("SELECT a FROM <%1%> LIMIT 5")),
                           FakeResp(200, {}), FakeResp(200, _form(tsql))])
    out = _call("form-set-saved-statement",
                ["--form-id", "F1", "--name", "Top scores", "--sql", tsql,
                 "--bindings", json.dumps(BINDINGS)], s)
    assert s.calls[1]["method"] == "PUT"            # a warning never refuses the save
    assert s.calls[1]["json"]["Queries"][0]["value"] == tsql
    assert any("SELECT TOP n" in w for w in out["warnings"])

    s = FakeSession(queue=[FakeResp(200, _form(tsql)), FakeResp(200, {}),
                           FakeResp(200, _form("SELECT a FROM <%1%> ORDER BY a DESC LIMIT 5"))])
    out = _call("form-set-saved-statement",
                ["--form-id", "F1", "--name", "Top scores",
                 "--sql", "SELECT a FROM <%1%> ORDER BY a DESC LIMIT 5"], s)
    assert "warnings" not in out
