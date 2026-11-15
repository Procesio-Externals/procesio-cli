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


def sql_parameters(sql: str) -> list[str]:
    """The `@name`s a statement uses, in order of first appearance, each once."""
    out: list[str] = []
    for name in _AT_NAME.findall(_SKIP.sub(" ", sql or "")):
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


def references(elements: list) -> dict:
    """{queryId: [name of each element with an event that runs it]}."""
    out: dict = {}
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


def unreferenced(queries: list, elements: list) -> list[dict]:
    used = {str(k).lower() for k in references(elements)}
    return [q for q in queries or [] if str(q.get("id") or "").lower() not in used]


def unreferenced_warnings(queries: list, elements: list) -> list[str]:
    """A designer save sends only the queries some event runs, so one that no event runs
    does not survive the form being opened and saved in the designer."""
    return [f"query {q.get('name')!r} is run by no event: the next save from the designer "
            f"drops it. Wire it to an element event (operation QUERY) to keep it."
            for q in unreferenced(queries, elements)]


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


def warnings(queries: list, elements: list) -> list[str]:
    return (unreferenced_warnings(queries, elements) + audit_warnings(queries)
            + spelling_warnings(queries))
