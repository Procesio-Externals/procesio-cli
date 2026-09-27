"""The SQL formatter may move whitespace and nothing else.

The formatter exists so a Query Store node is readable in the designer, and a Query Store node
IS its statement - so a formatter that could alter one would be trading correctness for looks.
These tests pin the guarantee rather than the cosmetics: same tokens, same order, idempotent,
and hands the input back whenever it cannot prove that.
"""
from tools.procesio.sqlformat import SINGLE_LINE_LIMIT, format_sql, is_unreadable, _tokens


def test_one_line_statement_is_laid_out():
    out = format_sql("SELECT a, b FROM t WHERE x = 1 AND y = 2")
    assert out.splitlines() == ["SELECT a, b", "FROM t", "WHERE x = 1", "AND y = 2"]


def test_only_whitespace_changes():
    sql = ("WITH c AS (SELECT MAX(n) AS n FROM t WHERE k = 'a') "
           "SELECT p.id, q.v FROM p JOIN q ON q.id = p.id WHERE p.n > 0 ORDER BY p.id")
    assert _tokens(format_sql(sql)) == _tokens(sql)


def test_formatting_is_idempotent():
    sql = "SELECT a FROM t WHERE b = 1 AND c = 2 ORDER BY a"
    once = format_sql(sql)
    assert format_sql(once) == once


def test_a_keyword_inside_a_string_literal_is_left_alone():
    sql = "UPDATE t SET msg = 'select from where and or' WHERE id = 1"
    out = format_sql(sql)
    assert "'select from where and or'" in out
    assert _tokens(out) == _tokens(sql)


def test_a_doubled_quote_inside_a_literal_survives():
    sql = "SELECT 'it''s fine, and from where' AS s FROM t WHERE a = 1"
    out = format_sql(sql)
    assert "'it''s fine, and from where'" in out
    assert _tokens(out) == _tokens(sql)


def test_placeholders_and_chips_are_opaque():
    sql = "SELECT <%0%> FROM {{ds:Settings}} WHERE {{col:Settings.Key}} = @k AND <%1%> IS NULL"
    out = format_sql(sql)
    for token in ("<%0%>", "{{ds:Settings}}", "{{col:Settings.Key}}", "<%1%>", "@k"):
        assert token in out


def test_already_multiline_sql_is_left_exactly_as_the_author_wrote_it():
    sql = "SELECT a\n  FROM t\n WHERE b = 1"
    assert format_sql(sql) == sql


def test_blank_and_non_string_inputs_pass_through():
    assert format_sql("") == ""
    assert format_sql(None) is None


def test_nested_parentheses_indent():
    out = format_sql("SELECT (SELECT x FROM u WHERE u.id = t.id) AS v FROM t")
    assert any(line.startswith("  ") for line in out.splitlines())


def test_is_unreadable_only_fires_on_a_long_single_line():
    assert is_unreadable("SELECT " + "a" * SINGLE_LINE_LIMIT)
    assert not is_unreadable("SELECT a FROM t")
    assert not is_unreadable("SELECT " + "a" * SINGLE_LINE_LIMIT + "\nFROM t")


def test_the_builder_refuses_a_long_one_line_script():
    """SQL gets laid out; a script gets refused, because rewriting code could change it."""
    import pytest

    import tools.procesio.dto.process.builder as pb

    long_line = "var x = 1; " * 40                       # ~440 characters, one line
    cfg = {"title": "t",
           "variables": [{"name": "out", "type": "string", "direction": "output"}],
           "actions": [{"id": "n", "action": "Node",
                        "params": {"Code": long_line, "Single Result": {"var": "out"}}}]}
    with pytest.raises(Exception) as e:
        pb.build(cfg, {"var_ids": {"out": "22222222-2222-2222-2222-222222222222"}})
    assert "ONE line" in str(e.value)
