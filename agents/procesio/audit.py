"""Static analysis of a PROCESIO process (flow) DTO.

Two kinds of findings:
  - correctness: the designer-vs-runtime parity bugs that make Validate fail even
    when the process runs (the hard-won PHASE4-E2E lessons). `verify` gates on these.
  - practice: best-practice smells (too many actions, slow actions, no error
    handling, no description, possible inline secret). The `audit` action reports them.

DTO case matters: the LIVE Web-API returns camelCase (`actions`, `parameters`,
`value`), while the offline .procesio EXPORT bundles use PascalCase (`Actions`,
`Parameters`, `Value`). Every lookup goes through `ci()` (case-insensitive) so the
agent works on a live process AND on an export golden. Beyond that the auditor is
defensive: an unknown shape downgrades a check to "skipped" rather than crashing
or emitting a false finding. It never invents certainty it does not have.
"""
from __future__ import annotations

import json
import re

_STRUCTURAL = {"start", "stop"}  # no configuration expected (compared lowercased)
# A node whose human NAME signals a Data Store / cache operation while its action
# TYPE is 'Call API' is a masquerade: a Call API does NOT touch the Data Store, it
# just calls an HTTP endpoint (the FX-usecase bug - a Call API node wearing a cache
# icon). Intent keywords are matched on the action NAME, the type on the template.
_DATASTORE_INTENT = ("cache", "data store", "datastore")
_CALLAPI_TEMPLATE = "call api"
_SLOW_KEYWORDS = ("call api", "sql", "ftp", "decisional",
                  "data store", "mysql", "redis")  # network/DB-bound: count toward speed
_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_SECRET_KEYWORDS = ("password", "passwd", "apikey", "api_key", "api-key",
                    "secret", "client_secret", "bearer ", "authorization")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/_=-]{24,}$")


def ci(d, *names):
    """Case-insensitive dict get: first `names` value whose key matches ignoring
    case. Handles live camelCase and export PascalCase from one call site."""
    if not isinstance(d, dict):
        return None
    lowered = {k.lower(): k for k in d.keys()}
    for n in names:
        k = lowered.get(n.lower())
        if k is not None:
            return d[k]
    return None


def _actions(flow: dict) -> list[dict]:
    a = ci(flow, "actions")
    return [x for x in a if isinstance(x, dict)] if isinstance(a, list) else []


def _template(a: dict) -> str:
    return str(ci(a, "actionTemplateName") or ci(a, "actionName") or "")


def _name(a: dict) -> str:
    return str(ci(a, "actionName") or _template(a) or "?")


def _is_structural(a: dict) -> bool:
    return _template(a).strip().lower() in _STRUCTURAL


def _param_set(p: dict) -> bool:
    val = ci(p, "value")
    return (val not in (None, "")) or bool(ci(p, "variable"))


def _config_settings(a: dict) -> list[dict]:
    conf = ci(ci(a, "customData") or {}, "configuration")
    if not isinstance(conf, list):
        return []
    settings: list[dict] = []
    for tab in conf:
        if isinstance(tab, dict):
            for s in ci(tab, "settings") or []:
                if isinstance(s, dict):
                    settings.append(s)
    return settings


def _config_set(s: dict) -> bool:
    return ci(s, "value") not in (None, "", [], {})


def _f(kind, severity, code, message, citation, action=None) -> dict:
    out = {"kind": kind, "severity": severity, "code": code,
           "message": message, "citation": citation}
    if action:
        out["action"] = action
    return out


def _datastore_masquerade(flow: dict) -> list[dict]:
    """A node named like a Data Store/cache op whose TYPE is 'Call API' does not read
    or write the Data Store - it just calls an endpoint. Hard-fail: the cache never
    works, which is invisible because the process still 'runs' green (FX-usecase bug)."""
    out: list[dict] = []
    for a in _actions(flow):
        if _is_structural(a):
            continue
        if any(k in _name(a).lower() for k in _DATASTORE_INTENT) \
                and _CALLAPI_TEMPLATE in _template(a).lower():
            out.append(_f(
                "correctness", "fail", "datastore-as-callapi",
                "action is named like a Data Store / cache operation but its type is "
                "'Call API' - a Call API node does NOT read or write the Data Store. "
                "Use a native Data Store action (Select/Insert/Update/Delete), not a "
                "Call API dressed with a cache icon.",
                "FX-usecase diagnosis; PROCESIO-DATASTORE", _name(a)))
    return out


def correctness_findings(flow: dict) -> list[dict]:
    """Designer-vs-runtime parity checks only (what `verify` gates on)."""
    findings: list[dict] = list(_datastore_masquerade(flow))
    for a in _actions(flow):
        if _is_structural(a):
            continue
        params = ci(a, "parameters")
        if not isinstance(params, list):
            continue
        set_params = [p for p in params if isinstance(p, dict) and _param_set(p)]
        settings = _config_settings(a)
        set_settings = [s for s in settings if _config_set(s)]
        if set_params and settings and not set_settings:
            findings.append(_f(
                "correctness", "warn", "designer-blank",
                "runtime parameters are set but the designer configuration is empty; "
                "the designer will show 'not configured' and Validate will fail "
                "(mirror parameters into customData.configuration)",
                "PHASE4-E2E process-builder fix", _name(a)))
        elif params and not set_params and not set_settings:
            findings.append(_f(
                "correctness", "info", "unconfigured-action",
                "action has parameters but none are set; confirm it is meant to be empty",
                "playbook A", _name(a)))
    return findings


def _practice_findings(flow: dict) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    nonstructural = [a for a in _actions(flow) if not _is_structural(a)]
    n = len(nonstructural)

    if n > 5:
        findings.append(_f("practice", "warn", "high-action-count",
                           f"{n} non-structural actions; >5 is 'really bad' for a "
                           "form-called process - reduce/merge or move to one scripting action",
                           "best-practices 9-10"))
    elif n >= 4:
        findings.append(_f("practice", "info", "action-count",
                           f"{n} non-structural actions; aim for <=3 if a form calls this",
                           "best-practices 9-10"))

    slow = sorted({_template(a) for a in nonstructural
                   if any(k in _template(a).lower() for k in _SLOW_KEYWORDS)})
    if slow:
        findings.append(_f("practice", "info" if len(slow) <= 2 else "warn",
                           "slow-actions",
                           "latency-adding actions present: " + ", ".join(slow) +
                           " - use only where needed, minimize for form-called processes",
                           "best-practices 10"))

    has_desc = bool(str(ci(flow, "description") or "").strip())
    if not has_desc:
        findings.append(_f("practice", "info", "missing-description",
                           "process has no description; document it and the trigger order (SOP)",
                           "best-practices 7"))

    blob = json.dumps(flow, default=str).lower()
    error_handling = any(t in blob for t in
                         ('errorport', '"error"', 'onerror', 'error_port', 'erroraction'))
    if n >= 2 and not error_handling:
        findings.append(_f("practice", "info", "no-error-handling",
                           "no error-port / error handling detected (heuristic); add a "
                           "global try/catch via Error Port + Decisional",
                           "best-practices 5"))

    findings.extend(_secret_smells(nonstructural))

    summary = {
        "action_count": len(_actions(flow)),
        "nonstructural_action_count": n,
        "slow_actions": slow,
        "has_description": has_desc,
        "error_handling_detected": error_handling,
    }
    return findings, summary


def _secret_smells(actions: list[dict]) -> list[dict]:
    out: list[dict] = []
    for a in actions:
        params = ci(a, "parameters") or []
        for p in params:
            if not isinstance(p, dict) or ci(p, "variable"):
                continue  # bound to a variable -> not an inline literal
            val = ci(p, "value")
            if not isinstance(val, str) or not val or _GUID_RE.match(val):
                continue  # GUIDs (e.g. a credential id literal) are expected, not secrets
            low = val.lower()
            if any(k in low for k in _SECRET_KEYWORDS) or (
                    len(val) >= 24 and _TOKEN_RE.match(val) and not val.startswith("<%")):
                out.append(_f("practice", "warn", "possible-inline-secret",
                              "a parameter holds a literal that looks like a secret; "
                              "secrets must live in the Credential Manager, not in the process",
                              "best-practices 2", _name(a)))
                break
    return out


def audit_process(flow: dict) -> dict:
    """Full audit: correctness + practice findings + a summary."""
    correctness = correctness_findings(flow)
    practice, summary = _practice_findings(flow)
    findings = correctness + practice
    counts = {"fail": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    summary["findings_by_severity"] = counts
    summary["title"] = ci(flow, "title") or ci(flow, "name")
    return {"findings": findings, "summary": summary}
