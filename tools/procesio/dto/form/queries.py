"""A form template's saved Data Store queries - PURE helpers shared by the builder
(`form-create` / `form-edit`) and the surgical handlers (handlers/form_queries.py).

A saved query is `{id, name, value, variable, parameters, timeoutSeconds}`: `value` is the
SQL with `<%N%>` tags, `variable` holds one binding per tag (a Data Store table or column),
`parameters` are the `@name`s the statement takes at run time. The save refuses a
malformed query with one error item per problem; `problems` reports the same ones
before a byte is sent. The SQL itself is checked by nobody until the query runs.
"""
from __future__ import annotations

import re
import uuid

from tools.procesio.errors import UsageError

OUTPUTS = ("rows", "columns", "count", "success")

_TAG = re.compile(r"<%(\d+)%>")
_PARAMETER = re.compile(r"@?[A-Za-z_][A-Za-z0-9_]*")
_PARAMETER_MAX = 64
_NAME_MAX = 128
_TIMEOUT_RANGE = (1, 600)
_BINDING_KINDS = {"datastoretable", "datastorecolumn", 1, 2}

# What a statement scan skips: string literals, quoted identifiers and comments. A `@name`
# inside any of them is text, not a parameter. `@@name` is a server variable.
_SKIP = re.compile(
    r"'(?:[^'\\]|\\.|'')*'"
    r'|"(?:[^"\\]|\\.|"")*"'
    r"|`[^`]*`"
    r"|/\*.*?\*/"
    r"|--(?=\s)[^\n]*|#[^\n]*",
    re.S)
_AT_NAME = re.compile(r"(?<![@\w])@[A-Za-z_][A-Za-z0-9_]*")


def code_only(sql: str) -> str:
    """The statement with its string literals, quoted identifiers and comments blanked,
    so a scan for keywords or parameters reads only the code."""
    return _SKIP.sub(" ", sql or "")


def sql_parameters(sql: str) -> list[str]:
    """The `@name`s a statement uses, in order of first appearance, each once."""
    out: list[str] = []
    for name in _AT_NAME.findall(code_only(sql)):
        if name not in out:
            out.append(name)
    return out


def bindings(raw) -> list[dict]:
    """Tag bindings in the shape the designer saves, with the two keys it leaves null."""
    out = []
    for b in raw or []:
        if not isinstance(b, dict):
            raise UsageError(f"a query binding must be an object, got {b!r}")
        out.append({**b, "variableId": b.get("variableId"), "attribute": b.get("attribute")})
    return out


def from_config(spec: dict, new_id=None) -> dict:
    """One `queries` config entry -> the wire query. `sql` / `bindings` are the authoring
    names for `value` / `variable`; `parameters` left out is derived from the statement."""
    if not isinstance(spec, dict):
        raise UsageError(f"each query must be an object, got {spec!r}")
    sql = spec.get("sql", spec.get("value"))
    parameters = spec.get("parameters")
    return {
        "id": spec.get("id") or (new_id or (lambda: str(uuid.uuid4())))(),
        "name": spec.get("name"),
        "value": sql,
        "variable": bindings(spec.get("bindings", spec.get("variable"))),
        "parameters": sql_parameters(sql) if parameters is None else list(parameters),
        "timeoutSeconds": spec.get("timeoutSeconds"),
    }


def _kind(value):
    return value.strip().lower() if isinstance(value, str) else value


def _tag_number(value):
    return int(value) if isinstance(value, str) and value.isdigit() else value


def _query_problems(query: dict) -> list[str]:
    out: list[str] = []
    sql = query.get("value")
    if not isinstance(sql, str) or not sql.strip():
        out.append("the query text is empty")
        sql = ""
    tags = sorted({int(n) for n in _TAG.findall(sql)})
    bound: dict = {}
    for b in query.get("variable") or []:
        if not isinstance(b, dict):
            out.append(f"binding {b!r} is not an object")
            continue
        tag = _tag_number(b.get("id"))
        if tag not in tags:
            continue   # a binding no tag uses is stored as sent and never resolved
        bound[tag] = bound.get(tag, 0) + 1
        kind = _kind(b.get("type"))
        if b.get("variableId"):
            out.append(f"binding {b.get('id')} is a process variable; a form query binds only "
                       f"Data Store tables and columns")
        elif kind not in _BINDING_KINDS:
            out.append(f"binding {b.get('id')} has unknown kind {b.get('type')!r} "
                       f"(use dataStoreTable or dataStoreColumn)")
        elif not b.get("dataStoreId"):
            out.append(f"binding {b.get('id')} has no dataStoreId")
        elif kind in ("datastorecolumn", 2) and not b.get("columnId"):
            out.append(f"binding {b.get('id')} is a column binding without a columnId")
    for n in tags:
        if n not in bound:
            out.append(f"tag <%{n}%> has no binding")
    out.extend(f"tag <%{n}%> is bound {count} times"
               for n, count in bound.items() if count > 1)
    seen: set = set()
    for p in query.get("parameters") or []:
        bare = p[1:] if isinstance(p, str) and p.startswith("@") else p
        if not isinstance(p, str) or not _PARAMETER.fullmatch(p):
            out.append(f"parameter {p!r} is not a valid name (letters, digits and "
                       f"underscore, not starting with a digit, optional leading @)")
        elif len(bare) > _PARAMETER_MAX:
            out.append(f"parameter {p!r} is longer than {_PARAMETER_MAX} characters")
        elif p in seen:
            out.append(f"parameter {p!r} is declared twice")
        seen.add(p)
    timeout = query.get("timeoutSeconds")
    low, high = _TIMEOUT_RANGE
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int)
                                or not low <= timeout <= high):
        out.append(f"timeoutSeconds {timeout!r} is outside {low}..{high} "
                   f"(leave it null for the default of 60)")
    return out


def problems(queries: list) -> list[str]:
    """Every problem the save would refuse, worded like the server's `target`:
    `queries[i] '<name>': <problem>`."""
    out: list[str] = []
    ids: set = set()
    names: set = set()
    for i, q in enumerate(queries or []):
        if not isinstance(q, dict):
            out.append(f"queries[{i}]: not an object")
            continue
        where = f"queries[{i}] {str(q.get('name') or '')!r}"
        qid, name = q.get("id"), q.get("name")
        if not qid:
            out.append(f"{where}: the id is missing")
        elif str(qid).lower() in ids:
            out.append(f"{where}: the id {qid} is used by another query")
        if not isinstance(name, str) or not name.strip():
            out.append(f"{where}: the name is missing")
        elif len(name) > _NAME_MAX:
            out.append(f"{where}: the name is longer than {_NAME_MAX} characters")
        elif name.strip().lower() in names:
            out.append(f"{where}: the name is used by another query")
        ids.add(str(qid).lower())
        names.add(str(name or "").strip().lower())
        out.extend(f"{where}: {p}" for p in _query_problems(q))
    return out


def check(queries: list) -> None:
    found = problems(queries)
    if found:
        raise UsageError("the form's queries would be refused by the save:\n  - "
                         + "\n  - ".join(found))


def find(queries: list, ref) -> dict | None:
    """The query with this id, else the one with this name."""
    ref = str(ref or "").strip()
    if not ref:
        return None
    for q in queries or []:
        if str(q.get("id") or "").lower() == ref.lower():
            return q
    hits = [q for q in queries or [] if str(q.get("name") or "").strip() == ref]
    return hits[0] if len(hits) == 1 else None


def resolve(queries: list, ref) -> dict:
    hit = find(queries, ref)
    if hit is None:
        known = ", ".join(repr(q.get("name")) for q in queries or []) or "(none)"
        raise UsageError(f"no saved query with id or name {ref!r} on this form; known: {known}")
    return hit


def check_parameter_names(query: dict, supplied) -> None:
    """A run and an event's inputMap both name parameters EXACTLY as declared: the server
    refuses any other spelling, `product` for a declared `@product` included."""
    declared = list(query.get("parameters") or [])
    unknown = [n for n in supplied if n not in declared]
    if unknown:
        raise UsageError(
            f"query {query.get('name')!r} does not declare {', '.join(map(repr, unknown))}; "
            f"name parameters exactly as declared: "
            f"{', '.join(map(repr, declared)) or '(the query takes none)'}")


_FORM_EVENT_LABEL = {"FORM_LOAD": "form onLoad", "FORM_BEFORE_SUBMIT": "form onBeforeSubmit",
                     "FORM_AFTER_SUBMIT": "form onAfterSubmit"}


def references(elements: list, form_events: list | None = None) -> dict:
    """{queryId: [name of each element, or form trigger, with an event that runs it]}."""
    out: dict = {}
    for ev in form_events or []:
        qid = ((ev or {}).get("config") or {}).get("queryId") if isinstance(ev, dict) else None
        label = _FORM_EVENT_LABEL.get((ev or {}).get("type"), "form event") if qid else None
        if qid and label not in out.setdefault(qid, []):
            out[qid].append(label)
    for el in elements or []:
        configs = el.get("configs") or []
        label = next((c.get("value") for c in configs if c.get("key") == "name"), None) or el.get("id")
        for c in configs:
            value = c.get("value")
            events = value.get("events") if isinstance(value, dict) else value
            for ev in events if isinstance(events, list) else []:
                qid = ((ev or {}).get("config") or {}).get("queryId") if isinstance(ev, dict) else None
                if qid and label not in out.setdefault(qid, []):
                    out[qid].append(label)
    return out


def unreferenced(queries: list, elements: list, form_events: list | None = None) -> list[dict]:
    used = {str(k).lower() for k in references(elements, form_events)}
    return [q for q in queries or [] if str(q.get("id") or "").lower() not in used]


def unreferenced_warnings(queries: list, elements: list,
                          form_events: list | None = None) -> list[str]:
    """A designer save sends only the queries some event runs, so one that no event runs
    does not survive the form being opened and saved in the designer."""
    return [f"query {q.get('name')!r} is run by no event: the next save from the designer "
            f"drops it. Wire it to an element or form event (operation QUERY) to keep it."
            for q in unreferenced(queries, elements, form_events)]


_INSERTS = re.compile(r"\b(INSERT|REPLACE)\s+INTO\b", re.IGNORECASE)
_AUDIT_COLUMNS = ("CreatedById", "UpdatedById")


def audit_warnings(queries: list) -> list[str]:
    """A Data Store row needs CreatedById and UpdatedById, and nothing supplies them to a
    form query: an INSERT that leaves them out is refused when it runs, not when it is
    saved."""
    out = []
    for q in queries or []:
        text = str(q.get("value") or "")
        missing = [c for c in _AUDIT_COLUMNS if c.lower() not in text.lower()]
        if _INSERTS.search(text) and missing:
            out.append(f"query {q.get('name')!r} inserts without {' and '.join(missing)}: the run "
                       f"is refused for a required column with no default. Add both columns and "
                       f"bind them to a parameter that carries a user id, mapped from a form "
                       f"field (plain @name, no UUID_TO_BIN).")
    return out


def spelling_warnings(queries: list) -> list[str]:
    """Two spellings of one parameter (`x` beside `@x`, or `X` beside `x`) pass the save and
    are refused by the Data Store service every time the query runs."""
    out = []
    for q in queries or []:
        by_name: dict = {}
        for p in q.get("parameters") or []:
            if isinstance(p, str):
                by_name.setdefault(p.lstrip("@").lower(), set()).add(p)
        for spellings in by_name.values():
            if len(spellings) > 1:
                out.append(f"query {q.get('name')!r} declares one parameter in several spellings "
                           f"({', '.join(sorted(spellings))}): the save accepts it and every run "
                           f"is refused. Keep one spelling.")
    return out


# SQL Server spellings and what MySQL takes instead. A Data Store is MySQL-backed, the save
# does not read the statement, and a run that MySQL refuses answers "invalid SQL syntax" or a
# general sentence, without naming the place. Each entry is refused by a stock MySQL 8: a
# syntax error (1064), an unknown function (1305) or a wrong argument count (1582). `{0}` is the spelling
# found, and the second text is what MySQL takes. A spelling MySQL accepts with another meaning
# is left out on purpose.
_TSQL_CAST_TYPES = r"(?:INT|BIGINT|SMALLINT|TINYINT|BIT|N?VARCHAR|UNIQUEIDENTIFIER|DATETIME2)"
_MYSQL_CAST_TYPES = "SIGNED, UNSIGNED, DECIMAL, CHAR, DATE or DATETIME"
_TSQL_SPELLINGS = tuple((re.compile(p, re.IGNORECASE), label, mysql) for p, label, mysql in (
    (r"\bSELECT\s+(?:DISTINCT\s+)?TOP\b", "SELECT TOP n", "LIMIT n at the end of the statement"),
    (r"\[[^\]\n]*\]", "[bracketed] names",
     "a <%N%> tag for a Data Store table or column, backticks for any other name"),
    (r"\bOFFSET\s+\S+\s+ROWS?\b", "OFFSET n ROWS FETCH NEXT m ROWS ONLY", "LIMIT m OFFSET n"),
    (r"\bWITH\s*\(\s*NOLOCK\s*\)", "WITH (NOLOCK)", "nothing, leave it out"),
    (r"\bOUTPUT\s+(?:INSERTED|DELETED)\b", "OUTPUT INSERTED / DELETED",
     "a SELECT as the last statement of the query"),
    (r"(?<![\w.])dbo\s*\.", "the dbo. schema prefix", "nothing, leave it out"),
    (r"\b(NEWID)\s*\(", "{0}()",
     "UUID(), but a Guid column takes a parameter and not a function result"),
    (r"\b(GETDATE|SYSDATETIME)\s*\(", "{0}()", "NOW()"),
    (r"\b(GETUTCDATE|SYSUTCDATETIME)\s*\(", "{0}()", "UTC_TIMESTAMP()"),
    (r"\b(SCOPE_IDENTITY)\s*\(", "{0}()", "LAST_INSERT_ID()"),
    (r"\b(LEN)\s*\(", "{0}()", "CHAR_LENGTH()"),
    (r"\b(IIF)\s*\(", "{0}()", "IF(condition, a, b)"),
    (r"\b(DATEADD)\s*\(", "{0}()", "DATE_ADD(date, INTERVAL n unit)"),
    (r"\b(TRY_CAST|TRY_CONVERT)\s*\(", "{0}()", f"CAST(value AS {_MYSQL_CAST_TYPES})"),
    (r"\bCONVERT\s*\(\s*(" + _TSQL_CAST_TYPES + r")\b", "CONVERT({0}, value)",
     f"CAST(value AS {_MYSQL_CAST_TYPES})"),
))
# A name both servers have, refused only for the SQL Server argument count.
_TSQL_ARGUMENT_COUNTS = (
    ("ISNULL", 2, "ISNULL(value, fallback)", "IFNULL(value, fallback) or COALESCE"),
    ("DATEDIFF", 3, "DATEDIFF(unit, a, b)", "TIMESTAMPDIFF(unit, a, b)"),
)
# CAST exists on both servers; only the target type differs. It is read from the end of the
# call, so an expression with its own parentheses in front of AS does not hide the type.
_TSQL_CAST_TARGET = re.compile(r"\bAS\s+(" + _TSQL_CAST_TYPES + r")\s*(?:\([^()]*\))?\s*$",
                               re.IGNORECASE)


def _call_arguments(code: str, open_paren: int) -> list[str] | None:
    """The top-level arguments of the call opened at `open_paren`; None when the parenthesis
    never closes."""
    depth, start, out = 0, open_paren + 1, []
    for i in range(open_paren, len(code)):
        ch = code[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append(code[start:i])
                return [] if len(out) == 1 and not out[0].strip() else out
        elif ch == "," and depth == 1:
            out.append(code[start:i])
            start = i + 1
    return None


def _calls(code: str, name: str):
    """The argument list of every closed call of `name` in `code`."""
    for match in re.finditer(rf"\b{name}\s*\(", code, re.IGNORECASE):
        arguments = _call_arguments(code, match.end() - 1)
        if arguments is not None:
            yield arguments


def _tsql_spellings(sql: str) -> list[str]:
    code = code_only(sql)
    found: list[str] = []

    def add(label: str, mysql: str) -> None:
        item = f"{label} (MySQL: {mysql})"
        if item not in found:
            found.append(item)

    for pattern, label, mysql in _TSQL_SPELLINGS:
        for match in pattern.finditer(code):
            add(label.format(match.group(1).upper() if match.groups() else ""), mysql)
    for name, count, label, mysql in _TSQL_ARGUMENT_COUNTS:
        if any(len(arguments) == count for arguments in _calls(code, name)):
            add(label, mysql)
    for arguments in _calls(code, "CAST"):
        target = _TSQL_CAST_TARGET.search(arguments[-1]) if arguments else None
        if target:
            add(f"CAST(... AS {target.group(1).upper()})", _MYSQL_CAST_TYPES)
    return found


def dialect_warnings(queries: list) -> list[str]:
    """A statement written for SQL Server is saved as it is and refused by MySQL at every run.
    The run does not say where, so name each spelling and its MySQL form at the write."""
    out = []
    for q in queries or []:
        found = _tsql_spellings(str(q.get("value") or ""))
        if found:
            out.append(f"query {q.get('name')!r} uses SQL Server spellings, and a Data Store runs "
                       f"MySQL: {'; '.join(found)}. The save accepts the text and the run is "
                       f"refused without naming the place, so run the query once after saving it.")
    return out


def warnings(queries: list, elements: list, form_events: list | None = None) -> list[str]:
    return (unreferenced_warnings(queries, elements, form_events) + audit_warnings(queries)
            + spelling_warnings(queries) + dialect_warnings(queries))
