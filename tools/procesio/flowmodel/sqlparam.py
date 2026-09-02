"""Parameterize PROCESIO SQL Server actions.

The SAFE way to pass flow-variable values into an `Execute Query` / `Execute Command` action is
NAMED SQL parameters (`@name`) bound via the action's `Parameters config tab` (a `map-parameters`
setting) — values then travel as typed, driver-escaped SQL parameters. The UNSAFE way (and the wrong
action config) is to string-interpolate the value into the SQL text as `N'<%N%>'`; that is
SQL-injection-prone, especially where the value is user text (a contact name, a message, OCR).

This module detects inline-`<%N%>` SQL nodes and converts them to the parameterized form. It also
migrates the deprecated `Execute Query V2` template (inline-only) to `Execute Query` (which carries the
`Parameters config tab`). Pure: it mutates a raw flow DTO dict in place; callers fetch/validate/put.

See tools/procesio/PROCESIO-SQL-ACTIONS-NOTES.md for the full DTO shape and property ids.
"""
from __future__ import annotations

import copy
import re

# 'Execute Query' template property ids (verified live 2026-07-03 on Chat Flow/Resolve Contact).
EQ_TEMPLATE = "Execute Query"
EQ_TEMPLATE_ID = "76470756-6dbd-4ab2-a4bf-88b47ed381ba"
# The deprecated 'Execute Query V2' template. CRUCIAL: the designer renders the action TYPE from the
# templateId, and the build put many SQL nodes on this template while LABELLING them "Execute Query".
# The map-parameters binding does NOT exist on V2, so a node must be migrated to EQ_TEMPLATE_ID (which
# the migration does) or the @params are unbound at runtime. Key it on templateId, never the label.
PID_CRED = "f96ff811-572f-084a-8cac-a74a2c2e365f"      # 'Select Database Server' (credentials)
PID_SIDEPANEL = "8add0f17-b2b1-4d5f-962b-c5d400a4e2d4"  # 'Execute Query' (side-pannel container)
PID_QUERY = "11350a1d-4139-d942-adcb-a2c2c52e5e22"      # 'Query' (code-editor, sql)
PID_BIND = "73416282-bcfe-4934-9e40-a39f2bb33d2d"       # 'Parameters config tab' (map-parameters)
PID_TIMEOUT = "9ce93b2d-5226-4228-a64d-3693c8d3e0e3"    # 'Time Out' (number)
PID_OUTPUT = "8aa02e91-1a1e-a44a-b09b-6965d67da04d"     # 'Output' (any)

# 'Execute Command' is a SECOND family with its OWN property ids - notably its own
# 'Parameters config tab' (0acb249e...), NOT the Execute Query one. Writing the Query binding id onto a
# Command node leaves every @param unbound at runtime with nothing to show for it, so the bind id must
# always be looked up per family (verified live 2026-08-22 against GET /api/Actions?getFullAction=true).
EC_TEMPLATE = "Execute Command"
EC_TEMPLATE_ID = "a1625da6-c093-4695-a97c-3c3d9a9b0cae"
EC_PID_CRED = "5f75a4fd-d0f5-4ac1-8257-467e50e7292e"     # 'Select Database Server' (credentials)
EC_PID_SIDEPANEL = "975f25dc-1044-4488-b635-10a2039f8d89"
EC_PID_COMMAND = "824575f6-7652-4bc2-8186-63b32c92cc22"  # 'Command' (code-editor, sql)
EC_PID_BIND = "0acb249e-8b21-4bfd-946c-1e65e26baa68"     # 'Parameters config tab' (map-parameters)
EC_PID_TIMEOUT = "2be309c6-9144-4b27-a722-fbc9c89735c2"  # 'Time Out' (number, required, 60..1800)
EC_PID_OUTPUT = "e6ffaa2d-2c32-412d-a9d4-b1038ece9d38"   # 'Output' (number, required)

# role -> property id, per CURRENT template. `timeout_default` fills a required Time Out that a
# migrated legacy node never had, so the migration cannot leave the designer with an empty required field.
_CURRENT = {
    EQ_TEMPLATE: {"templateId": EQ_TEMPLATE_ID, "cred": PID_CRED, "sidepanel": PID_SIDEPANEL,
                  "sql": PID_QUERY, "bind": PID_BIND, "timeout": PID_TIMEOUT, "output": PID_OUTPUT,
                  "timeout_default": None, "output_type": "any",
                  "description": "Execute a custom SQL Query on the target database.",
                  "labels": {PID_CRED: "Select Database Server", PID_SIDEPANEL: "Execute Query",
                             PID_QUERY: "Query", PID_TIMEOUT: "Time Out", PID_OUTPUT: "Output"}},
    EC_TEMPLATE: {"templateId": EC_TEMPLATE_ID, "cred": EC_PID_CRED, "sidepanel": EC_PID_SIDEPANEL,
                  "sql": EC_PID_COMMAND, "bind": EC_PID_BIND, "timeout": EC_PID_TIMEOUT,
                  "output": EC_PID_OUTPUT, "timeout_default": "300", "output_type": "number",
                  "description": "Execute a custom SQL Command on the target database.",
                  "labels": {EC_PID_CRED: "Select Database Server", EC_PID_SIDEPANEL: "Execute Command",
                             EC_PID_COMMAND: "Command", EC_PID_TIMEOUT: "Time Out",
                             EC_PID_OUTPUT: "Output"}},
}

# The property roles a family remap has to move. Order is irrelevant; completeness is not — a role
# left behind keeps the OLD template's property id on the node, which the designer then ignores.
_ROLE_KEYS = ("cred", "sidepanel", "sql", "bind", "timeout", "output")

# DEPRECATED templateId -> (family, {role: that template's property id}). Every one of these is
# inline-only (no map-parameters), so a node on one MUST be migrated before it can bind @params.
# Key on templateId, never the label: nodes on a legacy template are routinely LABELLED with the
# current template's name (all four collectors in one live workspace were, 2026-08-22).
_LEGACY = {
    "a9f851c2-e0ba-4fee-9a06-5445ba000001": (EQ_TEMPLATE, {          # Execute Query V2
        "cred": "a9f851c2-e0ba-4fee-9a06-5445bc000011",
        "sidepanel": "a9f851c2-e0ba-4fee-9a06-5445bc000012",
        "output": "a9f851c2-e0ba-4fee-9a06-5445bc000013",
        "sql": "a9f851c2-e0ba-4fee-9a06-5445bc000014",
        "timeout": "a9f851c2-e0ba-4fee-9a06-5445bc000015"}),
    "574a2ab1-4d24-4d6c-9483-f61597a6d5ff": (EQ_TEMPLATE, {          # Execute Query V1
        "cred": "a9d217b3-6a3c-44c5-81ff-581c860fb560",
        "sidepanel": "0b5bedd7-cd08-49f3-ba70-9d24aa7239ef",
        "output": "459b4db8-25f1-4903-9be8-3239312e93e6",
        "sql": "487bcfdb-67fd-49c0-bf02-0fb614dbb800"}),
    "c2760ff2-cd9e-49b4-b751-c05c88e06dac": (EC_TEMPLATE, {          # Execute Command V1
        "cred": "6701cb8b-3bde-4c7e-a45d-c37eaeff5e3d",
        "sidepanel": "fea72099-4718-473d-a091-7749aa38305b",
        "sql": "53896b0d-73a6-412f-9e67-224ca1daae7c",
        "timeout": "f3452b3a-2c10-40df-9d34-2d2779dc6ed6",
        "output": "f3452b3a-2c10-40df-9d34-2d2779dc6ed7"}),
}


def family_of(node: dict) -> tuple[str, dict | None]:
    """(current-family name, legacy role map or None) for a SQL node, keyed on templateId.

    Falls back to the label only when the templateId is unknown - a node built against a template
    this table has not seen yet still parameterizes, it just does not migrate.
    """
    tid = str(node.get("templateId") or "")
    if tid in _LEGACY:
        return _LEGACY[tid]
    for fam, spec in _CURRENT.items():
        if tid == spec["templateId"]:
            return fam, None
    label = node.get("actionTemplateName") or ""
    return (EC_TEMPLATE if EC_TEMPLATE in label else EQ_TEMPLATE), None


def bind_pid(node: dict) -> str:
    """The 'Parameters config tab' property id for THIS node's family."""
    return _CURRENT[family_of(node)[0]]["bind"]

_SQL_KW = re.compile(r"\b(EXEC|SELECT|UPDATE|INSERT|DELETE|MERGE|DECLARE)\b", re.I)
_PLACEHOLDER = re.compile(r"<%(\d+)%>")
_SQL_TEMPLATES = ("Execute Query", "Execute Command")   # includes 'Execute Query V2'


def is_sql_node(node: dict) -> bool:
    t = node.get("actionTemplateName", "") or ""
    return any(k in t for k in _SQL_TEMPLATES)


def _query_param(node: dict):
    """the parameters[] entry whose value is the SQL text still holding inline <%N%>."""
    for p in node.get("parameters") or []:
        v = p.get("value")
        if isinstance(v, str) and _PLACEHOLDER.search(v) and _SQL_KW.search(v):
            return p
    return None


def _query_setting(node: dict):
    """(container-setting, query-sub-setting) inside the side-pannel; the designer copy of the SQL."""
    for c in (node.get("customData") or {}).get("configuration") or []:
        for s in c.get("settings") or []:
            if isinstance(s.get("value"), list):
                for sub in s["value"]:
                    if isinstance(sub, dict) and str(sub.get("label", "")).lower() in ("query", "command"):
                        return s, sub
    return None, None


def is_inline(node: dict) -> bool:
    """True if this SQL node string-interpolates a value as N'<%N%>' (the injectable anti-pattern)."""
    qp = _query_param(node)
    if not qp:
        return False
    return bool(re.search(r"N?'<%\d+%>'", qp["value"]))


def scan(flow: dict) -> list[dict]:
    """List every SQL action in a flow with its inline/parameterized status."""
    out = []
    for a in flow.get("actions") or []:
        if is_sql_node(a):
            out.append({"actionName": a.get("actionName"), "id": a.get("id"),
                        "template": a.get("actionTemplateName"), "inline": is_inline(a)})
    return out


def find_node(flow: dict, key: str):
    for a in flow.get("actions") or []:
        if a.get("id") == key or a.get("actionName") == key:
            return a
    return None


def _designate_source(ve: dict) -> str:
    return ve["variableId"] + ("." + ve["attribute"]["attributeId"] if ve.get("attribute") else "")


def parameterize_node(node: dict) -> tuple[bool, str]:
    """Convert one inline-<%N%> SQL node to the parameterized form, in place.

    Rewrites each `N'<%K%>'` (and the un-quoted forms) to `@pK`, moves the placeholder->variable map
    into a `Parameters config tab` (map-parameters) binding, and — for a deprecated `Execute Query V2`
    node — swaps the template to `Execute Query`. Literals stay inline. Returns (changed, message).
    """
    if not is_sql_node(node):
        return False, "not a SQL Server action (Execute Query / Execute Command)"
    qp = _query_param(node)
    if not qp:
        return False, "already parameterized or no inline <%N%> in the SQL"
    sql = qp["value"]
    varmap = {v["id"]: v for v in (qp.get("variable") or [])}
    idxs = sorted(set(int(m) for m in _PLACEHOLDER.findall(sql)) & set(varmap))
    if not idxs:
        return False, "no bound <%N%> placeholders to parameterize"

    new_sql = sql
    runtime, designer = [], []
    for k in idxs:
        for form in ("N'<%%%d%%>'" % k, "'<%%%d%%>'" % k, "<%%%d%%>" % k):
            new_sql = new_sql.replace(form, "@p%d" % k)
        ve = varmap[k]
        runtime.append({"id": k,
                        "source": {"value": "<%%%d%%>" % k, "variable": [copy.deepcopy(ve)]},
                        "destination": {"value": "p%d" % k, "variable": []}})
        designer.append({"id": k, "destination": "p%d" % k, "source": _designate_source(ve)})

    # Migrate a node on a DEPRECATED template to its family's current one first (role-based id remap):
    # every legacy template is inline-only, so without this the @params have no property to bind to.
    fam, legacy = family_of(node)
    if legacy:
        _migrate_to_current(node, qp, fam, legacy)
    pid_bind = _CURRENT[fam]["bind"]

    # -- runtime form (what the engine executes) --
    qp["value"] = new_sql
    qp.pop("variable", None)
    params = node.setdefault("parameters", [])
    bp = next((p for p in params if p.get("tabPropertyId") == pid_bind), None)
    if bp:
        bp["value"] = runtime
    else:
        params.append({"tabPropertyId": pid_bind, "value": runtime})

    # -- designer copy (customData side-pannel) --
    setting, qsub = _query_setting(node)
    if qsub is not None:
        qsub["value"] = new_sql
        lst = setting["value"]
        existing = next((s for s in lst if isinstance(s, dict) and s.get("id") == pid_bind), None)
        if existing:
            existing["value"] = designer
        else:
            lst.insert(1, {"id": pid_bind, "dataTypeId": None, "label": "Parameters config tab",
                           "type": "map-parameters", "value": designer})
    return True, "parameterized %d value(s): %s" % (len(idxs), ", ".join("@p%d" % k for k in idxs))


def _roles_of(family: str) -> dict:
    """{role: property id} for a CURRENT template, in the shape _migrate_to_current consumes."""
    spec = _CURRENT[family]
    return {role: spec[role] for role in _ROLE_KEYS if spec.get(role)}


def _output_settings(node: dict, pid: str):
    """Every designer setting carrying the Output property, at either nesting level."""
    for cfg in (node.get("customData") or {}).get("configuration") or []:
        for setting in cfg.get("settings") or []:
            if setting.get("id") == pid:
                yield setting
            if isinstance(setting.get("value"), list):
                for sub in setting["value"]:
                    if isinstance(sub, dict) and sub.get("id") == pid:
                        yield sub


def convert_family(node: dict, target: str) -> tuple[bool, str]:
    """Move a SQL node between the Execute Command and Execute Query families, in place.

    `Execute Query` carries a RESULT SET back into a flow variable; `Execute Command` carries
    rows-affected (its Output property is typed `number`). So a Command node pointed at a procedure
    that ends in SELECT throws away everything the procedure returns and still reports success —
    there is no error to see, the output variable is simply a count. Converting the family is the
    only fix, and it is a role-based property-id remap in both the runtime `parameters[]` and the
    designer `customData`, plus the Output setting's type and the labels a later reader will trust.

    The SQL text, credential, timeout and `@param` binding are carried across untouched. A node on a
    deprecated template is refused rather than half-converted: run `sql-parameterize` first, which
    migrates it onto its family's current template. Returns (changed, message).
    """
    if target not in _CURRENT:
        raise ValueError("unknown SQL action family: %s (expected %r or %r)"
                         % (target, EQ_TEMPLATE, EC_TEMPLATE))
    if not is_sql_node(node):
        return False, "not a SQL Server action (Execute Query / Execute Command)"

    source, legacy = family_of(node)
    if legacy:
        return False, ("node is on a deprecated template (%s) - run sql-parameterize first to "
                       "migrate it onto its family's current template" % node.get("templateId"))
    if source == target:
        return False, "already %s" % target

    src_sql_pid = _CURRENT[source]["sql"]
    sql_param = next((p for p in node.get("parameters") or []
                      if p.get("tabPropertyId") == src_sql_pid), None)
    if sql_param is None:
        return False, "no SQL parameter (%s) found on the node" % src_sql_pid

    cur = _CURRENT[target]
    _migrate_to_current(node, sql_param, target, _roles_of(source))

    # customData carries three things the role remap does not reach, and each one is what the next
    # reader (or the designer) uses to decide what this node IS.
    custom = node.get("customData") or {}
    if isinstance(custom.get("description"), str):
        custom["description"] = cur["description"]
    for cfg in custom.get("configuration") or []:
        if cfg.get("label") == source:
            cfg["label"] = target
    for setting in _output_settings(node, cur["output"]):
        setting["type"] = cur["output_type"]

    return True, "converted %s -> %s" % (source, target)


def rebind_output(node: dict, variable_id: str) -> tuple[bool, str]:
    """Point a SQL node's Output at a different flow variable, in both layers, in place.

    The runtime layer holds a positional `<%N%>` slot plus the variable id; the designer layer holds
    the bare variable id. A node whose Output was never bound gets a fresh slot placed past every
    `@param` bind index, because the engine resolves those slots positionally and a collision hands
    the query the wrong value. Returns (changed, message).
    """
    family, legacy = family_of(node)
    if legacy:
        return False, ("node is on a deprecated template (%s) - run sql-parameterize first"
                       % node.get("templateId"))
    pid = _CURRENT[family]["output"]

    param = next((p for p in node.get("parameters") or [] if p.get("tabPropertyId") == pid), None)
    if param is None:
        return False, "no Output parameter (%s) found on the node" % pid

    bound = param.get("variable") or []
    if bound and bound[0].get("variableId") == variable_id:
        return False, "Output is already bound to %s" % variable_id

    if bound:
        bound[0]["variableId"] = variable_id
        bound[0]["attribute"] = None
    else:
        slot = _next_slot(node)
        param["variable"] = [{"id": slot, "variableId": variable_id, "attribute": None}]
        param["value"] = "<%%%d%%>" % slot

    for setting in _output_settings(node, pid):
        setting["value"] = variable_id

    return True, "Output rebound to %s" % variable_id


def _next_slot(node: dict) -> int:
    """The first positional `<%N%>` index no parameter on this node already claims."""
    used = {-1}
    for prm in node.get("parameters") or []:
        for ve in prm.get("variable") or []:
            if isinstance(ve.get("id"), int):
                used.add(ve["id"])
        value = prm.get("value")
        if isinstance(value, str):
            used.update(int(m) for m in _PLACEHOLDER.findall(value))
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, dict) and isinstance(row.get("id"), int):
                    used.add(row["id"])
    return max(used) + 1


def _migrate_to_current(node: dict, query_param: dict, family: str, legacy: dict) -> None:
    """Move a node off a deprecated SQL template onto its family's current one, in place.

    Purely a ROLE-BASED id remap driven by _LEGACY / _CURRENT: each legacy property id is looked up by
    the role it plays (credentials, side-pannel, sql, timeout, output) and rewritten to the current
    template's id for that same role, in both the runtime `parameters[]` and the designer customData.
    A required Time Out the legacy template never had is seeded from `timeout_default`, so the
    migration cannot hand the designer an empty required field.
    """
    cur = _CURRENT[family]
    remap = {legacy[role]: cur[role] for role in legacy if role in cur}
    node["actionTemplateName"] = family
    node["templateId"] = cur["templateId"]

    for prm in node.get("parameters") or []:
        pid = prm.get("tabPropertyId")
        if pid in remap:
            prm["tabPropertyId"] = remap[pid]
    # the SQL param is authoritative even if the table missed it (unknown legacy layout)
    query_param["tabPropertyId"] = cur["sql"]

    for cfg in (node.get("customData") or {}).get("configuration") or []:
        for setting in cfg.get("settings") or []:
            if setting.get("id") in remap:
                setting["id"] = remap[setting["id"]]
            _relabel(setting, cur)
            if isinstance(setting.get("value"), list):
                for sub in setting["value"]:
                    if isinstance(sub, dict):
                        if sub.get("id") in remap:
                            sub["id"] = remap[sub["id"]]
                        _relabel(sub, cur)

    default = cur.get("timeout_default")
    if default and cur.get("timeout"):
        _ensure_setting(node, cur["timeout"], cur["sidepanel"], "Time Out", "number", default)


def _relabel(setting: dict, cur: dict) -> None:
    """Give a remapped setting the CURRENT template's wording; a stale label on a property that now
    belongs to a different template is how the next reader concludes the migration did not happen."""
    label = (cur.get("labels") or {}).get(setting.get("id"))
    if label:
        setting["label"] = label


def _ensure_setting(node: dict, pid: str, sidepanel_pid: str, label: str, stype: str, value) -> None:
    """Add a required property the legacy template did not carry, to BOTH layers, if it is absent."""
    params = node.setdefault("parameters", [])
    if not any(p.get("tabPropertyId") == pid for p in params):
        params.append({"tabPropertyId": pid, "variable": [], "value": value})
    for cfg in (node.get("customData") or {}).get("configuration") or []:
        for setting in cfg.get("settings") or []:
            if setting.get("id") == sidepanel_pid and isinstance(setting.get("value"), list):
                if not any(isinstance(s, dict) and s.get("id") == pid for s in setting["value"]):
                    setting["value"].append({"id": pid, "dataTypeId": None, "label": label,
                                             "type": stype, "value": value})
