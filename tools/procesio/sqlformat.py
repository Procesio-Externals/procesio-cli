"""Lay a SQL statement out over several lines so a person can read it in the designer.

WHY THIS EXISTS. A statement authored by concatenating strings arrives as ONE line. It runs
perfectly and it is unreadable: the designer shows a single row that scrolls off the screen, and
a reviewer cannot see a WHERE clause, a JOIN or a CASE without dragging sideways through three
thousand characters. Readability is not a nicety here, because the statement IS the logic: a
Query Store node is one statement, so the statement is the whole node.

WHAT IT GUARANTEES. Only whitespace OUTSIDE string literals ever changes:

* text inside `'...'` is copied verbatim, quotes, keywords, doubled quotes and all;
* `<%0%>` placeholders and `{{ds:Store}}` / `{{col:Store.Column}}` tokens are opaque words;
* the result is checked against the input before it is returned - same tokens in the same order,
  or the input is handed back unchanged. A formatter that can alter a statement is worse than no
  formatter, so this one refuses to guess.

It also leaves alone any statement that ALREADY contains a newline: an author who laid their own
SQL out has made a decision, and reflowing it would overwrite that.
"""
from __future__ import annotations

import re

__all__ = ["format_sql", "is_unreadable", "SINGLE_LINE_LIMIT"]

# Beyond this, a single-line statement is long enough that a reader has to scroll.
SINGLE_LINE_LIMIT = 160

# Clause heads, longest first so "GROUP BY" wins over "GROUP" and "LEFT JOIN" over "JOIN".
_BREAK_BEFORE = [
    "WITH", "SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "OFFSET",
    "UNION ALL", "UNION", "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM",
    "INNER JOIN", "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "LEFT JOIN", "RIGHT JOIN",
    "CROSS JOIN", "STRAIGHT_JOIN", "JOIN", "ON DUPLICATE KEY UPDATE",
]
# Broken only near the top level, or a nested function's arguments turn into a staircase.
_BREAK_SHALLOW = ["AND", "OR"]

_INDENT = "  "
_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _split(sql: str):
    """Yield (kind, text) where kind is 'str' for a literal and 'sql' for everything else."""
    i, n, start = 0, len(sql), 0
    while i < n:
        c = sql[i]
        if c in "'\"":
            if start != i:
                yield "sql", sql[start:i]
            quote, j = c, i + 1
            while j < n:
                if sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == quote:
                    if j + 1 < n and sql[j + 1] == quote:     # '' inside a literal
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            yield "str", sql[i:j]
            i = start = j
            continue
        i += 1
    if start < n:
        yield "sql", sql[start:]


def _tokens(sql: str):
    """A comparable token stream: literals whole, everything else word/symbol by word/symbol."""
    out = []
    for kind, text in _split(sql):
        if kind == "str":
            out.append(text)
        else:
            out.extend(re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+|\S", text))
    return out


def _match_keyword(upper: str, pos: int, words):
    """The longest keyword starting at pos, on word boundaries, or None."""
    for kw in words:
        end = pos + len(kw)
        if not upper.startswith(kw, pos):
            continue
        before_ok = pos == 0 or not (upper[pos - 1].isalnum() or upper[pos - 1] == "_")
        after_ok = end >= len(upper) or not (upper[end].isalnum() or upper[end] == "_")
        if before_ok and after_ok:
            return kw
    return None


def format_sql(sql: str, indent: str = _INDENT) -> str:
    """Return `sql` laid out over lines, or `sql` unchanged when that cannot be done safely."""
    if not isinstance(sql, str) or not sql.strip():
        return sql
    if "\n" in sql.strip():
        return sql                      # the author already laid it out

    pieces, depth, line_start = [], 0, True

    def push(text):
        nonlocal line_start
        if text:
            pieces.append(text)
            line_start = text.endswith("\n")

    def newline(extra=0):
        while pieces and pieces[-1].endswith(" "):
            pieces[-1] = pieces[-1][:-1]
        if not pieces:
            return
        push("\n" + indent * max(0, depth + extra))

    for kind, text in _split(sql):
        if kind == "str":
            push(text)
            continue
        upper, i, n = text.upper(), 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "(":
                depth += 1
                push(ch)
                i += 1
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                push(ch)
                i += 1
                continue
            if ch.isspace():
                if not line_start:
                    push(" ")
                while i < n and text[i].isspace():
                    i += 1
                continue
            kw = _match_keyword(upper, i, _BREAK_BEFORE)
            if kw is None and depth <= 1:
                kw = _match_keyword(upper, i, _BREAK_SHALLOW)
            if kw:
                newline()
                push(text[i:i + len(kw)])
                i += len(kw)
                continue
            m = _WORD.match(text, i)
            if m:
                push(m.group(0))
                i = m.end()
                continue
            push(ch)
            i += 1

    out = "".join(pieces).strip()
    # The safety gate: same tokens in the same order, or give the caller their input back.
    if _tokens(out) != _tokens(sql):
        return sql
    return out


def is_unreadable(sql: str, limit: int = SINGLE_LINE_LIMIT) -> bool:
    """True when a statement is one long line, which is the shape worth complaining about."""
    return (isinstance(sql, str) and "\n" not in sql.strip()
            and len(sql.strip()) > limit)
