"""Deterministic, PURE naming for process actions and Decisional branches.

Why this exists: an un-named action falls back to its generic template label
("Node", "Call API"), so a canvas of a dozen script nodes is unreadable — the
exact problem `rename-actions` fixes post-hoc. This derives a meaningful label
from what the action is CONFIGURED to do, at BUILD time, so a freshly built or
edited process arrives already legible. Likewise a Decisional/AI Decisional
branch defaults to "Case 1/2/3…"; this labels each non-default case by its
condition instead.

Load-bearing rules:
  * An explicit ``name`` on the action/branch ALWAYS wins; this only fills the
    blank. On an edit the derived name is recomputed, so it always reflects the
    CURRENT config (the "re-evaluate on edit" contract) — an explicit label the
    user set stays put.
  * A name is derived ONLY from LITERAL config (a plain string/number). A param
    bound to a variable/template is unknowable at build time, so the deriver
    returns ``None`` and the caller keeps the template label — never a guess.
  * A name is COSMETIC — every reference in a flow is by id (ports, Decisional
    cases, parameter bindings) — so naming can only ever change a label, never
    wiring.
  * Decisional / AI Decisional ACTIONS keep their template label; their meaning
    lives in the per-branch names (``derive_branch_name``).
  * Everything here is pure and deterministic (no clock, no randomness): the
    same config always yields the same names — required for golden tests and
    for stable canvases across edits.
"""
from __future__ import annotations

import re

MAX_ACTION_NAME = 60
MAX_BRANCH_NAME = 48


# -- shared helpers -----------------------------------------------------------

def _cap(text, limit=MAX_ACTION_NAME):
    """Collapse whitespace, trim, and cap length with an ellipsis. Empty -> None."""
    if not text:
        return None
    s = re.sub(r"\s+", " ", str(text)).strip()
    if not s:
        return None
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _literal(params, *labels):
    """A param's LITERAL value by any label (case-insensitive), or None.

    A binding to a variable/template/credential ({"var"|"template"|"credential"})
    is not a literal — it cannot be summarized at build time — so it yields None.
    A bare scalar or {"value": x} yields the scalar.
    """
    low = {str(k).strip().lower(): v for k, v in (params or {}).items()}
    for lb in labels:
        if lb.strip().lower() in low:
            v = low[lb.strip().lower()]
            if isinstance(v, dict):
                if "value" in v and len(v) == 1:
                    return v["value"]
                return None
            if isinstance(v, (list, tuple)):
                return None
            return v
    return None


def _var_name(params, *labels):
    """The variable NAME a param is bound to ({"var": name}), or None."""
    low = {str(k).strip().lower(): v for k, v in (params or {}).items()}
    for lb in labels:
        v = low.get(lb.strip().lower())
        if isinstance(v, dict) and isinstance(v.get("var"), str):
            return v["var"]
    return None


# -- action names -------------------------------------------------------------

def _short_endpoint(url):
    """The path of a URL (query stripped), or its host if there is no path."""
    s = str(url).strip()
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)(/[^?#]*)?", s)
    if m:
        host, path = m.group(1), m.group(2)
        if path and path != "/":
            return path.rstrip("/") or path
        return host
    # not an absolute URL: take the part before any query, first line only
    return s.split("?", 1)[0].splitlines()[0].strip() or None


_SQL_VERB = re.compile(r"^\s*(?:--[^\n]*\n|/\*.*?\*/|\s)*"
                       r"(SELECT|INSERT|UPDATE|DELETE|MERGE|EXEC(?:UTE)?|WITH|CREATE|DROP|ALTER|TRUNCATE)",
                       re.IGNORECASE | re.DOTALL)
_SQL_TABLE = re.compile(r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+"
                        r"[\[\"`]?([A-Za-z_][\w.$]*)", re.IGNORECASE)


def _sql_summary(query):
    """"SELECT clients" from a literal SQL string; verb alone if no table found."""
    q = str(query)
    mv = _SQL_VERB.search(q)
    if not mv:
        return None
    verb = mv.group(1).upper().replace("EXECUTE", "EXEC")
    mt = _SQL_TABLE.search(q)
    return f"{verb} {mt.group(1)}" if mt else verb


def _leading_comment(code):
    """The first line of code if it is a comment (// # /* … */), else None.

    A leading comment is a cheap, deterministic way for the author to name a
    Node ("// resolve the invoice period"); absent one there is nothing to
    summarize, so the Node keeps its template label.
    """
    for raw in str(code).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            return line[2:].strip() or None
        if line.startswith("#"):
            return line.lstrip("#").strip() or None
        if line.startswith("/*"):
            return line[2:].split("*/", 1)[0].strip() or None
        return None  # first real line is code, not a comment
    return None


def derive_action_name(spec, template_name):
    """A meaningful name for an action from its LITERAL config, or None.

    None means "nothing better than the template label" — the caller keeps
    ``template_name``. Only high-value templates are enriched; everything else
    (whose template label is already descriptive: "Send Mail", "Download File")
    returns None by design.
    """
    tn = (template_name or "").strip().lower()
    params = spec.get("params") or {}

    if tn in ("call api", "curl"):
        verb = _literal(params, "Verb", "Method")
        endpoint = _literal(params, "Endpoint", "URL", "Url")
        if endpoint:
            path = _short_endpoint(endpoint)
            if path:
                return _cap(f"{str(verb).upper()} {path}" if verb else path)
        return None

    if tn in ("for each", "foreach"):
        lst = _var_name(params, "For Each Item", "In List")
        return _cap(f"For each {lst}") if lst else None

    if tn == "node":
        code = _literal(params, "Code")
        return _cap(_leading_comment(code)) if code else None

    if tn in ("execute query", "execute command"):
        summ = _sql_summary(_literal(params, "Query", "Command") or "")
        return _cap(summ) if summ else None

    if tn == "generate document":
        fn = _literal(params, "File Name", "FileName")
        return _cap(f"Generate {fn}") if fn else None

    return None


def disambiguate(entries):
    """Make AUTO-derived names unique within a flow. Returns {key: final_name}.

    ``entries`` is an ordered list of (key, name, is_auto). Explicit names
    (is_auto False) are kept verbatim — a user may deliberately reuse a label.
    Auto names that collide with any name already taken get a " 2", " 3"… suffix
    in flow order, so three un-named Call APIs read "GET /a", "POST /b", etc. and
    two identical ones read "GET /x", "GET /x 2".
    """
    used = {name for _, name, is_auto in entries if not is_auto and name}
    final = {}
    for key, name, is_auto in entries:
        if not is_auto:
            final[key] = name
            continue
        cand, n = name, 1
        while cand in used:
            n += 1
            cand = f"{name} {n}"
        used.add(cand)
        final[key] = cand
    return final


# -- branch (Decisional case) names -------------------------------------------

_OP_SYMBOL = {
    "EQUALS": "=", "DOES_NOT_EQUAL": "≠",
    "GREATER_THAN": ">", "GREATER_THAN_OR_EQUAL_TO": "≥",
    "LESS_THAN": "<", "LESS_THAN_OR_EQUAL_TO": "≤",
    "CONTAINS": "contains", "DOES_NOT_CONTAIN": "doesn't contain",
    "BELONGS": "in", "DOES_NOT_BELONG": "not in",
}
# unary operators: the right operand is ignored, so render the left alone
_OP_UNARY = {
    "IS_EMPTY": "{x} empty", "IS_NOT_EMPTY": "{x} present",
    "IS_TRUE": "{x}", "IS_FALSE": "not {x}",
}


def _operand_label(op):
    """A readable token for a decisional operand (variable name, path, or literal)."""
    if isinstance(op, dict):
        if isinstance(op.get("var"), str):
            path = op.get("path")
            return op["var"] + ("." + ".".join(str(p) for p in path) if path else "")
        if "value" in op:
            op = op["value"]
        else:
            return ""
    return "" if op is None else str(op)


def _condition_label(cond):
    left = _operand_label(cond.get("left"))
    op = (cond.get("op") or "").strip().upper()
    if op in _OP_UNARY:
        return _OP_UNARY[op].format(x=left).strip()
    sym = _OP_SYMBOL.get(op) or op.replace("_", " ").lower()
    right = _operand_label(cond.get("right", ""))
    return f"{left} {sym} {right}".strip()


def derive_branch_name(branch, is_ai):
    """A label for a non-default Decisional case from its condition, or None.

    AI Decisional: the case ``condition`` is already a plain-English sentence, so
    a capped form of it IS the name. Rule-based Decisional: join each ``when``
    clause ("amount > 1000 and status = paid"). None -> caller falls back to
    "Case N".
    """
    if is_ai:
        return _cap(branch.get("condition") or "", MAX_BRANCH_NAME)
    whens = branch.get("when") or []
    parts = [p for p in (_condition_label(c) for c in whens) if p]
    if not parts:
        return None
    tail = whens[1:]
    joiner = " or " if tail and all(
        (c.get("logic", "and") or "and").strip().lower() == "or" for c in tail) else " and "
    return _cap(joiner.join(parts), MAX_BRANCH_NAME)
