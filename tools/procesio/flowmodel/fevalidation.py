"""Front-end (designer-layer) process validation — a faithful offline port of the
Process Designer's client-side "Process Errors" checks.

Why this exists: POST /api/Projects/validate validates only the RUNTIME layer
(parameters) and returns EMPTY even when the designer REFUSES to save. The designer's
"Process Errors" panel is a separate CLIENT-SIDE check of the DESIGNER layer
(customData) with NO server endpoint. This module replicates that check so a flow can
be validated offline / before every save, exactly like the FE does before it lets the
user save.

Source of truth: tools/procesio/docs_info/process-validation-reference-1.md — the FE
team's verbatim dump of Validation.ts + ControlValidators/*. Every check here maps to a
method/validator there; section refs are noted inline (e.g. "ref §2 noUnconnectedNodes").

Two severities:
  * error   — deterministic, high-signal, structural/required/placeholder/value-format
              checks + subprocess mapping. These BLOCK a save (the designer would too).
  * warning — the data-type MISMATCH layer, which depends on the FE helper
              getValueDataTypes whose exact source is NOT in the reference. Ported
              best-effort and kept NON-blocking so an imperfect reconstruction can never
              wrongly block a legitimate save. Tunable against real flows.

PURE + offline + case-insensitive: exports are PascalCase (Actions, CustomData), the
live Web-API is camelCase (actions, customData). Every field access goes through `_g`.
Never mutates the input. No network — subprocess data and the datatype catalog are
INJECTED (target_vars_of / datatypes) so the whole thing is unit-testable.

Born 2026-07-06 from process-validation-reference-1.md.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

# -- constant reference (ref §6) ----------------------------------------------

START_TID = "c0e32108-6e3e-4ab8-96bd-cd61be6edb33"
STOP_TID = "c0e32108-6e3e-4ab8-96bd-cd61be6edb34"
FOREACH_TID = "dbef0804-66a9-4f8f-872c-ece1b89b8fdb"
CALL_SUB_TID = "c37e56fe-d924-4604-a86f-7c93f863fcdf"
TRIGGER_SUB_TID = "615365f9-9ccb-dd46-85a6-af824b7be897"
DECISIONAL_TID = "f5dcbb04-253d-4061-99a1-9b2822c2e6d2"
AI_DECISIONAL_TID = "772aac51-73f5-471d-bf9f-f5099cb30001"

DECISIONAL_CASE_SETTING = "11d4044a-8586-47f6-b3ce-1cae5da40f30"
DELAY_TYPE_SETTING = "f1293589-6ede-4cc6-a04b-cc70e7084cb0"

# Data-type GUIDs (ref §6.3)
BOOLEAN = "0317bfee-b2f5-4bde-bfe8-121212121210"
INTEGER = "0317bfee-b2f5-4bde-bfe8-121212121211"
FLOAT = "0317bfee-b2f5-4bde-bfe8-121212121212"
DOUBLE = "0317bfee-b2f5-4bde-bfe8-121212121213"
STRING = "0317bfee-b2f5-4bde-bfe8-121212121214"
DATE = "0317bfee-b2f5-4bde-bfe8-121212121215"
RELATIONSHIP = "0317bfee-b2f5-4bde-bfe8-121212121216"
TIME = "0317bfee-b2f5-4bde-bfe8-121212121217"
DATETIME = "0317bfee-b2f5-4bde-bfe8-121212121218"
GUID = "0317bfee-b2f5-4bde-bfe8-121212121222"
NUMBER = "NUMBER"
FILE = "10c6ac59-3929-49e6-99dc-121212121219"
JSON_T = "0317bfee-b2f5-4bde-bfe8-121212121220"
OBJECT = "0317bfee-b2f5-4bde-bfe8-121212121221"

_PRIMITIVE_IDS = {BOOLEAN, INTEGER, FLOAT, DOUBLE, STRING, DATE, RELATIONSHIP,
                  TIME, DATETIME, GUID, NUMBER}
# variable-name collision map (ref checkVariables + mapGUIDtoType/typeArray)
_PRIMITIVE_NAME = {
    BOOLEAN: "boolean", INTEGER: "integer", FLOAT: "float", DOUBLE: "double",
    STRING: "string", DATE: "date", RELATIONSHIP: "relationship", TIME: "time",
    DATETIME: "datetime", GUID: "guid", NUMBER: "number",
}
_TYPE_NAMES = set(_PRIMITIVE_NAME.values())

# SettingType values (ref §6.4) -> validator key
AI_DECISIONAL_CASE = "ai-decisional-case"
_SETTING_TYPE_TO_VALIDATOR = {
    "tabs-payload": "tabs_payload_old",
    "tabs-payload-v2": "tabs_payload",
    "decisional-case": "conditional",
    "ai-decisional-case": "ai_decisional",
    "process-inputs": "process_io",
    "process-outputs": "process_io",
    "column-definition": "column_definition",
    "delay-definition": "delay",
    "map-process-data": "map_process_data",
    "document-mapper": "document_mapper",
    "data-store-mapper": "document_mapper",
    "data-store-decisional": "data_store_decisional",
    "map-parameters": "map_parameters",
    # "number" and everything else -> default
}

# GUID / dotted-GUID reference regex (ref §2 variableRegex)
_VAR_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"(\.[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})*)\b(?!\.)")
# leftover-placeholder regex (ref AbstractControlValidator.hasPlaceholder)
_PLACEHOLDER_RE = re.compile(
    r"([x]{8}-[x]{4}-[x]{4}-[x]{4}-[a-zA-Z]{11}(\.[x]{8}-[x]{4}-[x]{4}-[x]{4}-[a-zA-Z]{11})*)\b(?!\.)")


# -- case-insensitive access ---------------------------------------------------

def _g(obj: Any, *names: str, default=None):
    if not isinstance(obj, dict):
        return default
    low = {str(k).lower(): v for k, v in obj.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return default


# -- primitive helpers (ref utils/type/*) -------------------------------------

def _is_empty(value) -> bool:
    return value is None or value == "" or (isinstance(value, list) and len(value) == 0)


def _is_valid_number(x) -> bool:
    if isinstance(x, bool):
        return False
    if isinstance(x, (int, float)):
        return True
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return False
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False


def _is_valid_integer(x) -> bool:
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float):
        return x.is_integer()
    if isinstance(x, str):
        s = x.strip()
        if not re.fullmatch(r"[+-]?\d+", s or ""):
            return False
        return True
    return False


def _is_boolean(x) -> bool:
    if isinstance(x, bool):
        return True
    if isinstance(x, str):
        return x.strip().lower() in ("true", "false")
    return False


def _has_variable(value) -> bool:
    """ref Variables/Utils.hasVariable — the value string contains a variable ref."""
    if not isinstance(value, str):
        return False
    return bool(_VAR_RE.search(value))


def _has_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(value))


# -- node model helpers --------------------------------------------------------

def _template_id(action: dict) -> str | None:
    return _g(action, "ActionTemplateId", "templateId")


def _template_name(action: dict) -> str | None:
    return _g(action, "ActionTemplateName", "actionTemplateName", "ActionName", "actionName")


def _cd(action: dict) -> dict:
    return _g(action, "CustomData", "customData", default={}) or {}


def _shape(action: dict) -> str | None:
    return _g(_cd(action), "type")


def _cd_name(action: dict):
    """The canvas node label = customData.name (the FE model's node.name). Returns a
    sentinel `_ABSENT` when customData has no `name` key at all (older/fixture DTOs that
    keep the name on actionName instead), so callers can fall back correctly."""
    cd = _cd(action)
    if isinstance(cd, dict) and any(str(k).lower() == "name" for k in cd):
        return _g(cd, "name") or ""
    return _ABSENT


_ABSENT = object()


def _kind(action: dict) -> str:
    """Classify an action into a template family, by GUID first then name/shape."""
    tid = _template_id(action)
    if tid == START_TID:
        return "start"
    if tid == STOP_TID:
        return "stop"
    if tid == FOREACH_TID:
        return "foreach"
    if tid == CALL_SUB_TID:
        return "call_sub"
    if tid == TRIGGER_SUB_TID:
        return "trigger_sub"
    if tid == DECISIONAL_TID:
        return "decisional"
    if tid == AI_DECISIONAL_TID:
        return "ai_decisional"
    name = (_template_name(action) or "").strip().lower()
    by_name = {
        "start": "start", "stop": "stop", "for each": "foreach",
        "call subprocess": "call_sub", "trigger subprocess": "trigger_sub",
        "decisional": "decisional", "decision": "decisional",
        "ai decisional": "ai_decisional",
    }
    if name in by_name:
        return by_name[name]
    # legacy DTOs may carry no template id/name — fall back to the canvas label. Only
    # structural templates default their label from the template, so this stays reliable
    # for Start/Stop/For Each/(Trigger) Subprocess; a renamed node just reads as "other".
    cdn = _cd_name(action)
    if cdn is not _ABSENT and (cdn or "").strip().lower() in by_name:
        return by_name[(cdn or "").strip().lower()]
    if _shape(action) == "diamond":
        return "decisional"
    return "other"


def _action_id(action: dict) -> str | None:
    return _g(action, "Id", "id")


def _action_name(action: dict) -> str:
    # The FE's node.name IS customData.name; use it when present (even when ""), else fall
    # back to actionName for DTOs that keep the label there (fixtures / some exports).
    cdn = _cd_name(action)
    if cdn is not _ABSENT:
        return cdn
    return _g(action, "ActionName", "actionName", "name", default="") or ""


def _badges(action: dict, suffix: str = "") -> list[str]:
    """ref AbstractControlValidator.getBadges (offline approximation: no store lookup)."""
    name = _action_name(action)
    tmpl = (_template_name(action) or "").strip()
    badges: list[str] = []
    if name and tmpl and tmpl != name.strip():
        badges.append(name)
    label = (tmpl or name or "action") + suffix
    badges.append(label)
    return badges


def _settings_of(action: dict):
    """Yield (config_setting) for each top-level setting in the action's configuration."""
    cd = _g(action, "CustomData", default={}) or {}
    for tab in _g(cd, "configuration", default=[]) or []:
        for s in _g(tab, "settings", default=[]) or []:
            if isinstance(s, dict):
                yield s


def _walk_settings_loose(action: dict):
    """Yield every setting in the configuration, recursing one level into side-panel
    list values (which hold sub-settings that may carry no `id`). Mirrors the reader's
    _walk_settings; used to locate id-less settings like `flow-list`."""
    for s in _settings_of(action):
        yield s
        val = _g(s, "value")
        if isinstance(val, list):
            for sub in val:
                if isinstance(sub, dict) and (_g(sub, "label") or _g(sub, "type")):
                    yield sub


def _all_settings_recursive(action: dict) -> list[dict]:
    """ref AbstractControlValidator.getAllSettings — flatten nested side-panel settings."""
    out: list[dict] = []

    def walk(s: dict):
        if _g(s, "id") is not None:
            out.append(s)
            val = _g(s, "value")
            if isinstance(val, list):
                for sub in val:
                    if isinstance(sub, dict):
                        walk(sub)
    for s in _settings_of(action):
        walk(s)
    return out


# -- ports -> line model (ref §2 lineArray) -----------------------------------

def _build_lines(actions: list[dict]) -> dict[str, list[dict]]:
    """Reconstruct each node's `lineArray` from all actions' Ports (edges live on the
    source action). A line touches a node if it is that node's source OR destination.
    error_path is true for the Error output path (Type==1 or Data.isDefault=='error')."""
    lines: list[dict] = []
    for a in actions:
        src = _action_id(a)
        for p in _g(a, "Ports", "ports", default=[]) or []:
            s = _g(p, "SourceId", "sourceId", default=src)
            d = _g(p, "DestinationId", "destinationId")
            if not s or not d:
                continue
            pdata = _g(p, "Data", "data", default={}) or {}
            is_err = (int(_g(p, "Type", "type", default=0) or 0) == 1) or \
                     (_g(pdata, "isDefault") == "error")
            lines.append({"source": s, "dest": d, "error_path": is_err})
    by_node: dict[str, list[dict]] = {}
    for ln in lines:
        by_node.setdefault(ln["source"], []).append(ln)
        if ln["dest"] != ln["source"]:
            by_node.setdefault(ln["dest"], []).append(ln)
    return by_node


# =============================================================================
# Warning helper
# =============================================================================

def _w(severity: str, code: str, text: str, action: dict | None = None,
       suffix: str = "", badges: list[str] | None = None) -> dict:
    return {
        "severity": severity,
        "code": code,
        "text": text,
        "badges": badges if badges is not None else (_badges(action, suffix) if action else []),
        "actionId": _action_id(action) if action else None,
        "action": _action_name(action) if action else None,
    }


# =============================================================================
# getValueDataTypes + validateDataType  (the WARNING type layer, ref §3 / glossary)
# =============================================================================

def _resolve_ref_type(ref: str, var_by_id: dict, dt_by_id: dict) -> tuple[str | None, bool] | None:
    """Resolve a dotted variable reference (v.attr.attr) to (dataTypeId, isList).
    Returns None if the root variable is unknown."""
    parts = ref.split(".")
    root = var_by_id.get(parts[0])
    if not root:
        return None
    dt = _g(root, "DataType", "dataType")
    is_list = bool(_g(root, "IsList", "isList", default=False))
    for attr_id in parts[1:]:
        model = dt_by_id.get(dt)
        if not model:
            return (None, is_list)
        attr = next((at for at in (_g(model, "attributes", "Attributes", default=[]) or [])
                     if _g(at, "id", "Id") == attr_id), None)
        if not attr:
            return (None, is_list)
        dt = _g(attr, "dataTypeId", "DataTypeId", "dataType", "DataType")
        is_list = bool(_g(attr, "isList", "IsList", default=False))
    return (dt, is_list)


def get_value_data_types(value, var_by_id: dict, dt_by_id: dict) -> dict:
    """ref Values/ValueDataTypesHelper.getValueDataTypes — parse variable refs in a raw
    value and return the datatypes they resolve to, split scalar vs list.
    A plain constant (no variable refs) yields empty lists ({} => "valid, skip")."""
    scalar: list[dict] = []
    listed: list[dict] = []
    if not isinstance(value, str):
        return {"scalar": scalar, "list": listed}
    for m in _VAR_RE.finditer(value):
        resolved = _resolve_ref_type(m.group(1), var_by_id, dt_by_id)
        if resolved is None:
            continue
        dt_id, is_list = resolved
        if dt_id is None:
            continue
        model = dt_by_id.get(dt_id) or {"id": dt_id}
        (listed if is_list else scalar).append(model)
    return {"scalar": scalar, "list": listed}


def _is_primitive(dt_id: str) -> bool:
    return dt_id in _PRIMITIVE_IDS


def _is_custom_type_allowed(dt_id: str) -> bool:
    return dt_id in (JSON_T, OBJECT)


def validate_data_type(types: dict, setting: dict, excluded: list[str] | None = None) -> bool:
    """ref §3 SettingValidation.validateDataType — true if the value's actual types are
    assignable to what the setting expects (dataTypeId / isList)."""
    excluded = excluded or []
    scalar = types.get("scalar", [])
    listed = types.get("list", [])
    if len(scalar) == 0 and len(listed) == 0:
        return True
    is_list = bool(_g(setting, "isList", "IsList", default=False))
    if (is_list and (len(scalar) != 0 or len(listed) != 1)) or \
       (not is_list and (len(scalar) == 0 or len(listed) != 0)):
        return False
    setting_dt = _g(setting, "dataTypeId", "DataTypeId")
    for dt in [*scalar, *listed]:
        if not dt:
            continue
        dt_id = _g(dt, "id", "Id")
        if dt_id in excluded:
            flag = False
        elif setting_dt == OBJECT:
            flag = True
        elif _is_primitive(dt_id):
            flag = True if setting_dt == STRING else (dt_id == setting_dt)
        else:
            flag = _is_custom_type_allowed(setting_dt) or (dt_id == setting_dt)
        if not flag:
            return False
    return True


# =============================================================================
# Field-level validators (ref §4) — dispatched per setting.type
# =============================================================================

def _placeholders_check(action: dict, setting: dict) -> list[dict]:
    """ref AbstractControlValidator.doPlaceholdersCheck — runs for EVERY setting."""
    value = _g(setting, "value")
    if not value:
        return []
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    if isinstance(value, str) and (_has_placeholder(value) or "<%%>" in value):
        return [_w("error", "PLACEHOLDER",
                   "Please replace all placeholders in the template.",
                   action, f" - {_g(setting, 'label', default='')}")]
    return []


def _label(setting: dict) -> str:
    return _g(setting, "label", "Label", default="") or ""


def _default_required(action, setting) -> list[dict]:
    if _g(setting, "isRequired", "IsRequired") and _is_empty(_g(setting, "value")):
        return [_w("error", "REQUIRED",
                   "Please make sure that the action is defined/configured properly.",
                   action, f" - {_label(setting)}")]
    return []


def _default_value_check(action, setting) -> list[dict]:
    """ref DefaultControlValidator.doValueCheck — number/integer literal well-formedness."""
    value = _g(setting, "value")
    if value is None or _has_variable(value):
        return []
    is_list = bool(_g(setting, "isList", "IsList", default=False))
    values = value if (is_list and isinstance(value, list)) else [value]
    if not isinstance(values, list):
        # try to parse a JSON list literal
        try:
            parsed = json.loads(values.replace("'", '"')) if isinstance(values, str) else values
            if isinstance(parsed, list):
                values = parsed
            else:
                values = [value]
        except Exception:  # noqa: BLE001
            values = [value]
    # An empty / unset value is NOT a format error — the required check owns emptiness.
    # (ref: the FE's isValidNumber/isValidInteger treat "" as valid, so an optional numeric
    # field left blank — e.g. a Delay's unused "Runtime Amount" — must not be flagged.)
    values = [v for v in values if not (v is None or (isinstance(v, str) and v.strip() == ""))]
    if not values:
        return []
    dt = _g(setting, "dataTypeId", "DataTypeId")
    stype = _g(setting, "type")
    if dt in (FLOAT, DOUBLE, NUMBER):
        if not all(_is_valid_number(v) for v in values):
            return [_w("error", "VALUE_NUMBER", "Please make sure that the value is a number.",
                       action, f" - {_label(setting)}")]
    elif dt == INTEGER:
        if not all(_is_valid_integer(v) for v in values):
            return [_w("error", "VALUE_INTEGER", "Please make sure that the value is an integer.",
                       action, f" - {_label(setting)}")]
    elif dt == OBJECT and stype == "number":
        if not all(_is_valid_number(v) for v in values):
            return [_w("error", "VALUE_NUMBER", "Please make sure that the value is a number.",
                       action, f" - {_label(setting)}")]
    return []


def _dt_label(dt_by_id: dict, dt_id, is_list: bool = False) -> str:
    name = _g(dt_by_id.get(dt_id) or {}, "name", "Name") or (dt_id or "?")
    return f"list<{name}>" if is_list else str(name)


def _type_hint(setting, types: dict, dt_by_id: dict) -> str:
    """Name the expected vs actual type. "Error: data type mismatch." alone does not
    say WHAT to change; a real case (2026-07-30) was Call API's `Response Status`,
    which needs an **integer** variable — binding a `number` failed with only that
    opaque text, once as an FE warning and again as a BE error."""
    expected = _dt_label(dt_by_id, _g(setting, "dataTypeId", "DataTypeId"),
                         bool(_g(setting, "isList", "IsList", default=False)))
    actual = [_dt_label(dt_by_id, _g(dt, "id", "Id")) for dt in (types.get("scalar") or [])]
    actual += [_dt_label(dt_by_id, _g(dt, "id", "Id"), True) for dt in (types.get("list") or [])]
    got = ", ".join(a for a in actual if a) or "nothing"
    return (f"binds {got}; this property expects {expected}. Retype the variable (or "
            f"rebind) to match — the BE validator rejects the same mismatch on save.")


def _default_datatype_check(action, setting, var_by_id, dt_by_id) -> list[dict]:
    """ref DefaultControlValidator.doDataTypeCheck — WARNING layer."""
    value = _g(setting, "value") or ""
    if not isinstance(value, str):
        return []
    types = get_value_data_types(value, var_by_id, dt_by_id)
    if not validate_data_type(types, setting):
        w = _w("warning", "TYPE_MISMATCH", "Error: data type mismatch.",
               action, f" - {_label(setting)}")
        w["hint"] = _type_hint(setting, types, dt_by_id)   # additive; text kept for FE parity
        return [w]
    return []


def _ai_decisional_required(action, setting) -> list[dict]:
    """ref §4.4 AiDecisionalCaseValidator."""
    value = _g(setting, "value")
    if not isinstance(value, list) or len(value) == 0:
        return []
    incomplete = any(
        not (_g(c, "name") or "").strip() or not (_g(c, "condition") or "").strip()
        or not _g(c, "target")
        for c in value if isinstance(c, dict))
    if incomplete:
        return [_w("error", "AI_CASE_INCOMPLETE",
                   "Action definition incomplete. Please make sure all AI cases have a "
                   "name, condition, and target configured.", action, f" - {_label(setting)}")]
    return []


def _tabs_payload_required(action, setting) -> list[dict]:
    """ref §4.5 TabsPayloadControlValidator (v2): row has value but no key."""
    value = _g(setting, "value") or {}
    errors: list[dict] = []
    body = _g(value, "body", default={}) or {}
    btype = _g(body, "type")
    bval = _g(body, "value", default={}) or {}
    active = _g(bval, btype) if btype else None
    label = _label(setting)

    def row_missing_key(item):
        return _g(item, "value") and len(str(_g(item, "value"))) > 0 and \
            (not _g(item, "key") or len(str(_g(item, "key")).strip()) == 0)

    if isinstance(active, list):
        for i, item in enumerate(active):
            if isinstance(item, dict) and row_missing_key(item):
                errors.append(_w("error", "PAYLOAD_ROW_NO_KEY",
                                 "Please make sure that the action is defined/configured properly.",
                                 action, f" - {label} (Body, row {i + 1})"))
    for key, subname in (("queryParams", "Query Params"), ("headers", "Headers")):
        for i, item in enumerate(_g(value, key, default=[]) or []):
            if isinstance(item, dict) and row_missing_key(item):
                errors.append(_w("error", "PAYLOAD_ROW_NO_KEY",
                                 "Please make sure that the action is defined/configured properly.",
                                 action, f" - {label} ({subname}, row {i + 1})"))
    return errors


def _tabs_payload_old_required(action, setting) -> list[dict]:
    """ref §4.6 TabsPayloadOldControlValidator: query/header row value w/o key."""
    value = _g(setting, "value") or {}
    errors: list[dict] = []
    label = _label(setting)
    for key, subname in (("queryParams", "Query Params"), ("headers", "Headers")):
        for item in _g(value, key, default=[]) or []:
            if isinstance(item, dict) and _g(item, "value") and \
                    len(str(_g(item, "value"))) > 0 and \
                    (not _g(item, "key") or len(str(_g(item, "key")).strip()) == 0):
                errors.append(_w("error", "PAYLOAD_ROW_NO_KEY",
                                 "Please make sure that the action is defined/configured properly.",
                                 action, f" - {label} ({subname})"))
    return errors


def _process_io_required(action, setting) -> list[dict]:
    """ref §4.7 ProcessInputOutputValidator."""
    value = _g(setting, "value")
    label = _label(setting)
    if value is None:
        return [_w("error", "REQUIRED",
                   "Please make sure that the action is defined/configured properly.",
                   action, f" - {label}")]
    errors: list[dict] = []
    if isinstance(value, list):
        if len(value) == 0:
            return []
        for i, row in enumerate(value):
            sub = _g(row, "subprocess")
            if not sub or len(str(sub).strip()) == 0:
                errors.append(_w("error", "REQUIRED",
                                 "Please make sure that the action is defined/configured properly.",
                                 action, f" - {label} (row {i + 1})"))
    return errors


def _conditional_required(action, setting) -> list[dict]:
    """ref §4.8 ConditionalValidator + §5 DecisionalCardValidation."""
    value = _g(setting, "value")
    if not value or (isinstance(value, list) and len(value) == 0):
        return []
    has_errors = False
    if isinstance(value, list):
        for case in value:
            if _decisional_card_invalid(case):
                has_errors = True
    if has_errors:
        return [_w("error", "CASE_INCOMPLETE",
                   "Action definition incomplete. Please make sure all cases are configured.",
                   action, f" - {_label(setting)}")]
    return []


def _decisional_card_invalid(case: dict) -> bool:
    """ref §5 DecisionalCardValidation — name required, target required, >=1 condition,
    and each condition's operator+operands filled."""
    if not isinstance(case, dict):
        return True
    if not (_g(case, "name") or "").strip():
        return True
    if not _g(case, "target"):
        return True
    conditions = _g(case, "condition", default=[]) or []
    if len(conditions) < 1:
        return True
    return _conditions_incomplete(conditions)


def _conditions_incomplete(conditions: list) -> bool:
    for cond in conditions:
        if not isinstance(cond, dict):
            return True
        val = _g(cond, "value")
        if val is None:
            # row condition: operator + left operand required (right unless unary — unknown
            # offline, so require left+operator which the FE always requires)
            if not _g(cond, "operator"):
                return True
            left = _g(cond, "leftOperator", default={}) or {}
            if _is_empty(_g(left, "value")):
                return True
        elif isinstance(val, list):
            if len(val) == 0:
                return True
            if _conditions_incomplete(val):
                return True
    return False


def _data_store_decisional_required(action, setting) -> list[dict]:
    """ref §4.9 DataStoreDecisionalValidator — Where conditions configured."""
    value = _g(setting, "value")
    if not isinstance(value, list) or len(value) == 0:
        return []
    conditions = _g(value[0], "condition", default=[]) or []
    if len(conditions) == 0:
        return []
    if _conditions_incomplete(conditions):
        return [_w("error", "WHERE_INCOMPLETE",
                   "Action definition incomplete. Please make sure the Where conditions "
                   "are configured.", action, f" - {_label(setting)}")]
    return []


def _delay_required(action, setting) -> list[dict]:
    """ref §4.10 DelayDefinitionValidator."""
    value = _g(setting, "value")
    errors: list[dict] = []
    label = _label(setting)
    delay_type = None
    for s in _all_settings_recursive(action):
        if _g(s, "id") == DELAY_TYPE_SETTING and _g(s, "value"):
            delay_type = _g(s, "value")
            break
    if not delay_type:
        return []
    dval = _g(value, "value") if isinstance(value, dict) else None
    interval = _g(value, "interval") if isinstance(value, dict) else None
    is_wait_for = str(delay_type).lower().replace("_", " ") in ("wait for", "waitfor")
    if not value or dval is None or dval == "" or (is_wait_for and not interval):
        errors.append(_w("error", "REQUIRED",
                         "Please make sure that the action is defined/configured properly.",
                         action, f" - {label}"))
    if isinstance(value, dict) and dval not in (None, ""):
        if is_wait_for and _is_valid_number(dval) and float(dval) < 0:
            errors.append(_w("error", "DELAY_INVALID", "Invalid delay value.",
                             action, f" - {label}"))
    return errors


def _document_mapper_required(action, setting) -> list[dict]:
    """ref §4.11 DocumentMapperValidator."""
    value = _g(setting, "value")
    if not value or (isinstance(value, list) and len(value) == 0):
        return []
    errors: list[dict] = []
    label = _label(setting)
    rows = [r for r in value if isinstance(r, dict)]
    idx = 0
    for row in rows:
        doc = _g(row, "document")
        if (not doc) or (doc and _has_variable(doc)):
            if not doc or len(str(doc).strip()) == 0:
                errors.append(_w("error", "REQUIRED",
                                 "Please make sure that the action is defined/configured properly.",
                                 action, f" - {label} (row {idx + 1})"))
        idx += 1
    return errors


def _column_definition_required(action, setting) -> list[dict]:
    """ref §4.12 ColumnDefinitionControlValidator."""
    value = _g(setting, "value")
    rows = _g(value, "rows") if isinstance(value, dict) else None
    label = _label(setting)
    if not rows or (isinstance(rows, list) and len(rows) == 0):
        return [_w("error", "REQUIRED",
                   "Please make sure that the action is defined/configured properly.",
                   action, " - column definition")]
    errors: list[dict] = []
    for i, row in enumerate(rows):
        cn = _g(row, "columnName")
        at = _g(row, "attribute")
        if not cn or len(str(cn).strip()) == 0 or not at or len(str(at).strip()) == 0:
            errors.append(_w("error", "REQUIRED",
                             "Please make sure that the action is defined/configured properly.",
                             action, f" - {label} (row {i + 1})"))
    return errors


def _column_definition_datatype(action, setting, var_by_id, dt_by_id) -> list[dict]:
    """ref §4.12 ColumnDefinitionControlValidator.doDataTypeCheck — WARNING layer."""
    value = _g(setting, "value")
    rows = _g(value, "rows") if isinstance(value, dict) else None
    if not rows:
        return []
    probe = dict(setting)
    probe["dataTypeId"] = STRING
    errors: list[dict] = []
    for i, row in enumerate(rows):
        attr = (_g(row, "attribute") or "").strip()
        if not validate_data_type(get_value_data_types(attr, var_by_id, dt_by_id), probe):
            errors.append(_w("warning", "TYPE_MISMATCH", "Error: data type mismatch.",
                             action, f" - {_label(setting)} attribute (row {i + 1})"))
    return errors


def _map_row_required(action, setting) -> list[dict]:
    """ref §4.13 MapParametersValidator / §4.14 MapProcessDataValidator (identical required)."""
    value = _g(setting, "value")
    label = _label(setting)
    if isinstance(value, list) and len(value) == 0:
        return []
    if not value:
        return [_w("error", "REQUIRED",
                   "Please make sure that the action is defined/configured properly.",
                   action, f" - {label} (row 1)")]
    errors: list[dict] = []
    for i, row in enumerate(value):
        dest = _g(row, "destination")
        src = _g(row, "source")
        if not dest or (src is not None and len(str(src).strip()) == 0):
            errors.append(_w("error", "REQUIRED",
                             "Please make sure that the action is defined/configured properly.",
                             action, f" - {label} (row {i + 1})"))
    return errors


_REQUIRED_VALIDATORS: dict[str, Callable] = {
    "ai_decisional": _ai_decisional_required,
    "tabs_payload": _tabs_payload_required,
    "tabs_payload_old": _tabs_payload_old_required,
    "process_io": _process_io_required,
    "conditional": _conditional_required,
    "data_store_decisional": _data_store_decisional_required,
    "delay": _delay_required,
    "document_mapper": _document_mapper_required,
    "column_definition": _column_definition_required,
    "map_parameters": _map_row_required,
    "map_process_data": _map_row_required,
}


def _validator_key(setting_type: str | None) -> str:
    return _SETTING_TYPE_TO_VALIDATOR.get(setting_type or "", "default")


# =============================================================================
# Graph-level checks (ref §2)
# =============================================================================

def _check_field_validation(actions, var_by_id, dt_by_id, include_types) -> list[dict]:
    """ref §2 checkFieldValidation — dispatch every setting to its validator."""
    errors: list[dict] = []
    for a in actions:
        for setting in _settings_of(a):
            value = _g(setting, "value")
            stype = _g(setting, "type")
            sid = _g(setting, "id")
            # ref: array-valued settings are expanded to their elements, EXCEPT decisional /
            # AI-decisional cases (validated as a whole setting).
            if isinstance(value, list) and sid != DECISIONAL_CASE_SETTING and \
                    stype != AI_DECISIONAL_CASE:
                items = [v for v in value if isinstance(v, dict)]
            else:
                items = [setting]
            for val in items:
                key = _validator_key(_g(val, "type"))
                if key in _REQUIRED_VALIDATORS:
                    errors.extend(_REQUIRED_VALIDATORS[key](a, val))
                else:  # default
                    errors.extend(_default_required(a, val))
                    errors.extend(_default_value_check(a, val))
                    if include_types:
                        errors.extend(_default_datatype_check(a, val, var_by_id, dt_by_id))
                # placeholders check runs for every setting (base class)
                errors.extend(_placeholders_check(a, val))
                # type layer for the two ported composite type-checks
                if include_types and key == "column_definition":
                    errors.extend(_column_definition_datatype(a, val, var_by_id, dt_by_id))
    return errors


def _check_unconnected(actions, lines_by_node, children_by_parent) -> list[dict]:
    """ref §2 noUnconnectedNodes."""
    UNCONNECTED = "Please make sure that all actions are connected."
    MISSING_END = ("Process definition incomplete. Please make sure the action is "
                   "connected to Stop action.")
    MISSING_END_ERR = ("Process definition incomplete. Please make sure the action has any "
                       "connection besides Error path connection.")
    kind_by_id = {_action_id(a): _kind(a) for a in actions}
    errors: list[dict] = []
    for a in actions:
        nid = _action_id(a)
        kind = kind_by_id.get(nid)
        original = lines_by_node.get(nid, [])
        # filterErrorPortLines: keep incoming lines always; drop outgoing error-path lines
        filtered = [ln for ln in original if ln["dest"] == nid or not ln["error_path"]]
        if kind in ("start", "stop"):
            if not filtered:
                errors.append(_w("error", "UNCONNECTED", UNCONNECTED, a))
            continue
        if not filtered:
            errors.append(_w("error", "UNCONNECTED", UNCONNECTED, a))
        elif len(filtered) == 1:
            ln = filtered[0]
            other_is_stop = kind_by_id.get(ln["source"]) == "stop" or \
                kind_by_id.get(ln["dest"]) == "stop"
            if other_is_stop:
                errors.append(_w("error", "UNCONNECTED", UNCONNECTED, a))
            elif not _g(a, "ParentId", "parentId"):
                text = MISSING_END_ERR if len(filtered) != len(original) else MISSING_END
                errors.append(_w("error", "MISSING_STOP", text, a))
        elif kind in ("decisional", "ai_decisional") and len(filtered) >= 2:
            has_entry = any(ln["dest"] == nid for ln in filtered)
            if not has_entry:
                errors.append(_w("error", "UNCONNECTED", UNCONNECTED, a))
        elif kind == "foreach":
            child_ids = children_by_parent.get(nid, [])
            inner_start = next((c for c in child_ids
                                if kind_by_id.get(c) == "start"), None)
            if inner_start and not lines_by_node.get(inner_start):
                errors.append(_w("error", "UNCONNECTED", UNCONNECTED, a))
    return errors


def _check_node_names(actions) -> list[dict]:
    """ref §2 checkNodeNameValidation."""
    errors: list[dict] = []
    for a in actions:
        if _action_name(a) == "":
            errors.append(_w("error", "NODE_NAME",
                             "Please make sure that all actions have a name.", a, " - node name"))
    return errors


def _check_points(actions) -> list[dict]:
    """ref §2 checkPointsValidation — exactly 1 Start, >=1 Stop."""
    errors: list[dict] = []
    starts = [a for a in actions if _kind(a) == "start"]
    stops = [a for a in actions if _kind(a) == "stop"]
    if len(starts) != 1:
        errors.append(_w("error", "START_COUNT",
                         "Please make sure that the process have 1 start action",
                         badges=["Start"]))
    if len(stops) < 1:
        errors.append(_w("error", "STOP_COUNT",
                         "Please make sure that the process have at least 1 stop action",
                         badges=["Stop"]))
    return errors


def _check_limits(actions) -> list[dict]:
    """ref §2 checkLimits — numeric settings with limits within [min, max]."""
    errors: list[dict] = []
    for a in actions:
        for setting in _settings_of(a):
            value = _g(setting, "value")
            candidates = value if isinstance(value, list) else [setting]
            for s in (candidates if isinstance(value, list) else [setting]):
                lim = _g(s, "limits") if isinstance(s, dict) else None
                sval = _g(s, "value") if isinstance(s, dict) else None
                if not lim:
                    continue
                lo, hi = _g(lim, "min"), _g(lim, "max")
                if sval is None or (isinstance(sval, str) and sval.strip() == ""):
                    continue  # unset value: nothing to range-check (ref: FE Number("")===0 path)
                if not _is_valid_number(sval):
                    errors.append(_w("error", "LIMIT_NAN",
                                     "Please make sure that the value is a number.",
                                     a, f" - {_label(s)}"))
                    errors.append(_w("error", "LIMIT_RANGE",
                                     f"Please make sure that the value is between {lo} and {hi}.",
                                     a, f" - {_label(s)}"))
                    continue
                n = float(sval)
                if (lo is not None and n < lo) or (hi is not None and n > hi):
                    errors.append(_w("error", "LIMIT_RANGE",
                                     f"Please make sure that the value is between {lo} and {hi}.",
                                     a, f" - {_label(s)}"))
    return errors


def _check_variables(variables) -> list[dict]:
    """ref §2 checkVariables — unique names + primitive-name collision."""
    errors: list[dict] = []
    dups: set[str] = set()
    for v in variables:
        name = _g(v, "Name", "name")
        vid = _g(v, "Id", "id")
        if name is None:
            continue
        clash = any(_g(o, "Name", "name") == name and _g(o, "Id", "id") != vid
                    for o in variables)
        if clash and name not in dups:
            errors.append(_w("error", "VAR_UNIQUE", "Variable name should be unique.",
                             badges=[f"Variable: {name}"]))
            dups.add(name)
        dt = _g(v, "DataType", "dataType")
        type_name = _PRIMITIVE_NAME.get(dt, "custom")
        low = str(name).lower()
        if low in _TYPE_NAMES and type_name != "custom" and type_name != low:
            errors.append(_w("error", "VAR_PRIMITIVE_NAME",
                             "Cannot name variables as Primitives with a different type.",
                             badges=[f"Variable: {name}"]))
    return errors


def _check_subprocess(actions, target_vars_of) -> list[dict]:
    """ref §2 checkSubprocess — subprocess validity + required-input mapping + dead refs.
    target_vars_of(flow_id) -> {var_id: var_dict}; returns {} when unavailable (skips)."""
    if target_vars_of is None:
        return []
    errors: list[dict] = []
    for a in actions:
        if _kind(a) not in ("call_sub", "trigger_sub"):
            continue
        # locate the side-panel + selected subprocess id
        sidepanel = None
        for s in _settings_of(a):
            if _g(s, "type") == "side-pannel":
                sidepanel = s
                break
        target = None
        for s in _walk_settings_loose(a):
            if _g(s, "type") == "flow-list":
                target = _g(s, "value")
                break
        if not target:
            # fall back to a GUID parameter value
            for p in _g(a, "parameters", "Parameters", default=[]) or []:
                pv = _g(p, "value", "Value")
                if isinstance(pv, str) and _VAR_RE.fullmatch(pv or "") and \
                        pv != "00000000-0000-0000-0000-000000000000":
                    target = pv
                    break
        if not target:
            continue
        tvars = target_vars_of(target) or {}
        # process-inputs / outputs subsections
        inputs, outputs = [], []
        for sub in (_g(sidepanel, "value", default=[]) or []) if sidepanel else []:
            if _g(sub, "type") == "process-inputs":
                inputs = _g(sub, "value", default=[]) or []
            elif _g(sub, "type") == "process-outputs":
                outputs = _g(sub, "value", default=[]) or []
        mapped_in = {_g(r, "subprocess"): _g(r, "process") for r in inputs}
        for vid, v in tvars.items():
            if _g(v, "type", "Type") == 10 and _g(v, "isRequired", "IsRequired"):
                src = mapped_in.get(vid)
                if src is None or src == "":
                    errors.append(_w("error", "SUB_REQ_UNMAPPED",
                                     f"Mapping of required subprocess variable "
                                     f"(<b>{_g(v, 'name', 'Name')}</b>) is missing.", a))
        input_ids = set(tvars.keys())
        for r in inputs:
            sub = _g(r, "subprocess") or ""
            for m in _VAR_RE.finditer(str(sub)):
                root = m.group(1).split(".")[0]
                if root not in input_ids:
                    errors.append(_w("error", "SUB_CHECK_MAPPING", "Check data mapping.", a))
        output_ids = {vid for vid, v in tvars.items()
                      if _g(v, "type", "Type") == 30}
        for r in outputs:
            sub = _g(r, "subprocess") or ""
            for m in _VAR_RE.finditer(str(sub)):
                root = m.group(1).split(".")[0]
                if root in tvars and root not in output_ids:
                    errors.append(_w("error", "SUB_CHECK_MAPPING", "Check data mapping.", a))
    return errors


# =============================================================================
# Public entrypoint
# =============================================================================

def validate_flow(flow: dict, *, datatypes: list[dict] | None = None,
                  target_vars_of: Callable[[str], dict] | None = None,
                  include_types: bool = True) -> list[dict]:
    """Pure FE (designer-layer) validation over a flow DTO. Returns a list of warning
    dicts {severity, code, text, badges, action, actionId}. severity 'error' entries
    block a save; 'warning' entries are the advisory type-mismatch layer.

    - datatypes: DataModel[] catalog (for the type layer; type checks skipped if None).
    - target_vars_of(flow_id) -> {var_id: var}: resolver for subprocess checks (offline
      injectable); when None, subprocess mapping checks are skipped.
    - include_types: master switch for the WARNING type-mismatch layer.
    """
    flow = _g(flow, "flow") or flow
    actions = [a for a in (_g(flow, "Actions", "actions", default=[]) or [])
               if not _g(a, "IsDisabled", "isDisabled", default=False)]
    variables = _g(flow, "Variables", "variables", default=[]) or []

    var_by_id = {_g(v, "Id", "id"): v for v in variables}
    dt_by_id = {_g(d, "id", "Id"): d for d in (datatypes or [])}
    have_types = include_types and bool(datatypes)

    lines_by_node = _build_lines(actions)
    children_by_parent: dict[str, list[str]] = {}
    for a in actions:
        pid = _g(a, "ParentId", "parentId")
        if pid:
            children_by_parent.setdefault(pid, []).append(_action_id(a))

    warnings: list[dict] = []
    warnings.extend(_check_unconnected(actions, lines_by_node, children_by_parent))
    warnings.extend(_check_field_validation(actions, var_by_id, dt_by_id, have_types))
    warnings.extend(_check_node_names(actions))
    warnings.extend(_check_points(actions))
    warnings.extend(_check_limits(actions))
    warnings.extend(_check_subprocess(actions, target_vars_of))
    warnings.extend(_check_variables(variables))
    return warnings


def split_severity(warnings: list[dict]) -> tuple[list[dict], list[dict]]:
    """(errors, warnings) — errors block a save."""
    errs = [w for w in warnings if w.get("severity") == "error"]
    warns = [w for w in warnings if w.get("severity") != "error"]
    return errs, warns
