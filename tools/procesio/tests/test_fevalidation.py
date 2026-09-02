"""Front-end (designer-layer) process-validation pure-logic tests.

Every case maps to a rule in docs_info/process-validation-reference-1.md.
"""
from tools.procesio.flowmodel import fevalidation as fv
from tools.procesio.flowmodel.fevalidation import validate_flow, split_severity


# -- tiny DTO builders (camelCase, like the live Web-API) ----------------------

def _act(aid, name, tmpl="Concatenate", settings=None, ports=None, shape="square",
         parent=None):
    a = {"id": aid, "actionName": name, "actionTemplateName": tmpl,
         "customData": {"type": shape,
                        "configuration": [{"settings": settings or []}]},
         "ports": ports or []}
    if parent:
        a["parentId"] = parent
    return a


def _start(ports=None):
    return _act("start", "Start", "Start", ports=ports or [])


def _stop():
    return _act("stop", "Stop", "Stop", ports=[])


def _flow(actions, variables=None):
    return {"actions": actions, "variables": variables or []}


def _line(src, dst, **d):
    return {"sourceId": src, "destinationId": dst, "type": d.get("type", 0),
            "data": d.get("data", {})}


def _errs(flow, **kw):
    e, _ = split_severity(validate_flow(flow, **kw))
    return e


def _codes(flow, **kw):
    return {w["code"] for w in validate_flow(flow, **kw)}


# -- valid baseline ------------------------------------------------------------

def _valid_flow():
    return _flow([
        _start(ports=[_line("start", "mid")]),
        _act("mid", "Mid", settings=[], ports=[_line("mid", "stop")]),
        _stop(),
    ])


def test_valid_flow_clean():
    assert _errs(_valid_flow(), target_vars_of=lambda f: {}) == []


# -- points (ref checkPointsValidation) ---------------------------------------

def test_missing_start():
    flow = _flow([_act("mid", "Mid", ports=[_line("mid", "stop")]), _stop()])
    assert "START_COUNT" in _codes(flow)


def test_two_starts():
    flow = _flow([_start(ports=[_line("start", "stop")]),
                  _act("s2", "Start2", "Start", ports=[_line("s2", "stop")]), _stop()])
    assert "START_COUNT" in _codes(flow)


def test_missing_stop():
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", ports=[])])
    assert "STOP_COUNT" in _codes(flow)


# -- node names (ref checkNodeNameValidation) ---------------------------------

def test_empty_node_name():
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "", ports=[_line("mid", "stop")]), _stop()])
    assert "NODE_NAME" in _codes(flow)


# -- connectivity (ref noUnconnectedNodes) ------------------------------------

def test_unconnected_start():
    flow = _flow([_start(ports=[]), _stop()])
    codes = _codes(flow)
    assert "UNCONNECTED" in codes


def test_node_only_connected_to_stop_flagged():
    # mid's single line goes to Stop -> UNCONNECTED (ref: len==1 && endpoint is Stop)
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", ports=[_line("mid", "stop")]),
                  _act("orphan", "Orphan", ports=[_line("orphan", "stop")]), _stop()])
    # orphan: lines = [orphan->stop] only, len 1, endpoint stop -> UNCONNECTED
    assert "UNCONNECTED" in _codes(flow)


def test_error_path_only_missing_stop():
    # a node whose only NON-error line is incoming -> MISSING_STOP variant
    flow = _flow([
        _start(ports=[_line("start", "mid")]),
        _act("mid", "Mid", ports=[_line("mid", "err", type=1, data={"isDefault": "error"})]),
        _act("err", "ErrHandler", ports=[_line("err", "stop")]),
        _stop(),
    ])
    codes = _codes(flow)
    assert "MISSING_STOP" in codes


# -- required fields (ref DefaultControlValidator.doRequiredCheck) -------------

def test_required_empty_default():
    s = {"id": "s1", "type": "text", "label": "URL", "isRequired": True,
         "dataTypeId": fv.STRING, "isList": False, "value": ""}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "REQUIRED" in _codes(flow)


def test_required_filled_ok():
    s = {"id": "s1", "type": "text", "label": "URL", "isRequired": True,
         "dataTypeId": fv.STRING, "isList": False, "value": "https://x"}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "REQUIRED" not in _codes(flow)


# -- placeholders (ref doPlaceholdersCheck) -----------------------------------

def test_leftover_placeholder():
    s = {"id": "s1", "type": "text", "label": "Body", "isRequired": False,
         "dataTypeId": fv.STRING, "value": "xxxxxxxx-xxxx-xxxx-xxxx-abcdefghijk"}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "PLACEHOLDER" in _codes(flow)


def test_empty_template_marker_placeholder():
    s = {"id": "s1", "type": "text", "label": "Body", "value": "a <%%> b"}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "PLACEHOLDER" in _codes(flow)


# -- value format (ref doValueCheck) ------------------------------------------

def test_empty_optional_numeric_not_flagged():
    # an optional number field left blank (e.g. a Delay's unused "Runtime Amount") is a
    # valid FORMAT — emptiness is the required check's job, not the value check's.
    s = {"id": "s1", "type": "number", "label": "Runtime Amount", "isRequired": False,
         "dataTypeId": fv.INTEGER, "isList": False, "value": ""}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    codes = _codes(flow)
    assert "VALUE_INTEGER" not in codes and "VALUE_NUMBER" not in codes


def test_value_not_a_number():
    s = {"id": "s1", "type": "text", "label": "Count", "dataTypeId": fv.NUMBER,
         "isList": False, "value": "abc"}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "VALUE_NUMBER" in _codes(flow)


def test_value_integer_bad():
    s = {"id": "s1", "type": "text", "label": "N", "dataTypeId": fv.INTEGER,
         "isList": False, "value": "3.5"}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "VALUE_INTEGER" in _codes(flow)


def test_value_number_with_variable_skipped():
    # a variable reference -> value check is skipped (concrete value unknown at design time)
    s = {"id": "s1", "type": "text", "label": "N", "dataTypeId": fv.NUMBER,
         "value": "11111111-2222-4333-8444-555555555555"}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "VALUE_NUMBER" not in _codes(flow)


# -- limits (ref checkLimits) --------------------------------------------------

def test_limits_out_of_range():
    s = {"id": "s1", "type": "number", "label": "Retries", "dataTypeId": fv.INTEGER,
         "value": 99, "limits": {"min": 0, "max": 10}}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "LIMIT_RANGE" in _codes(flow)


def test_limits_within_range_ok():
    s = {"id": "s1", "type": "number", "label": "Retries", "dataTypeId": fv.INTEGER,
         "value": 5, "limits": {"min": 0, "max": 10}}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()])
    assert "LIMIT_RANGE" not in _codes(flow)


# -- variables (ref checkVariables) -------------------------------------------

def test_duplicate_variable_names():
    flow = _valid_flow()
    flow["variables"] = [{"id": "v1", "name": "x", "dataType": fv.STRING},
                         {"id": "v2", "name": "x", "dataType": fv.STRING}]
    assert "VAR_UNIQUE" in _codes(flow, target_vars_of=lambda f: {})


def test_primitive_name_collision():
    flow = _valid_flow()
    # named "string" but typed integer -> collision
    flow["variables"] = [{"id": "v1", "name": "string", "dataType": fv.INTEGER}]
    assert "VAR_PRIMITIVE_NAME" in _codes(flow, target_vars_of=lambda f: {})


def test_primitive_name_matching_type_ok():
    flow = _valid_flow()
    flow["variables"] = [{"id": "v1", "name": "string", "dataType": fv.STRING}]
    assert "VAR_PRIMITIVE_NAME" not in _codes(flow, target_vars_of=lambda f: {})


# -- subprocess mapping (ref checkSubprocess) ---------------------------------

def _subcall(target, inputs=None, outputs=None):
    subsecs = [{"type": "process-inputs", "value": inputs or []},
               {"type": "process-outputs", "value": outputs or []}]
    return {"id": "call", "actionName": "Call X", "actionTemplateName": "Call Subprocess",
            "customData": {"type": "square", "configuration": [{"settings": [
                {"type": "side-pannel", "id": "5456caf0", "value": subsecs},
                {"type": "flow-list", "value": target}]}]},
            "ports": [_line("call", "stop")], "parameters": []}


def test_subprocess_required_input_unmapped():
    tgt = "11111111-2222-4333-8444-555555555555"
    call = _subcall(tgt, inputs=[])
    flow = _flow([_start(ports=[_line("start", "call")]), call, _stop()])
    tv = {"B": {"name": "SessionId", "type": 10, "isRequired": True}}
    assert "SUB_REQ_UNMAPPED" in _codes(flow, target_vars_of=lambda f: tv if f == tgt else {})


def test_subprocess_mapped_ok():
    tgt = "11111111-2222-4333-8444-555555555555"
    call = _subcall(tgt, inputs=[{"subprocess": "B", "process": "v1"}])
    flow = _flow([_start(ports=[_line("start", "call")]), call, _stop()],
                 variables=[{"id": "v1", "name": "sess", "type": 20}])
    tv = {"B": {"name": "SessionId", "type": 10, "isRequired": True}}
    codes = _codes(flow, target_vars_of=lambda f: tv if f == tgt else {})
    assert "SUB_REQ_UNMAPPED" not in codes


# -- decisional cases (ref ConditionalValidator + DecisionalCardValidation) ----

def test_decisional_case_incomplete():
    s = {"id": "11d4044a-8586-47f6-b3ce-1cae5da40f30", "type": "decisional-case",
         "label": "Cases", "value": [{"name": "", "target": "t", "condition": []}]}
    node = _act("dec", "Decision", "Decisional", settings=[s],
                ports=[_line("start", "dec"), _line("dec", "stop")], shape="diamond")
    flow = _flow([_start(ports=[_line("start", "dec")]), node, _stop()])
    assert "CASE_INCOMPLETE" in _codes(flow)


def test_decisional_case_complete_ok():
    s = {"id": "11d4044a-8586-47f6-b3ce-1cae5da40f30", "type": "decisional-case",
         "label": "Cases", "value": [{"name": "c1", "target": "stop", "condition": [
             {"operator": "eq", "leftOperator": {"value": "a"},
              "rightOperator": {"value": "b"}, "value": None}]}]}
    node = _act("dec", "Decision", "Decisional", settings=[s],
                ports=[_line("start", "dec"), _line("dec", "stop")], shape="diamond")
    flow = _flow([_start(ports=[_line("start", "dec")]), node, _stop()])
    assert "CASE_INCOMPLETE" not in _codes(flow)


# -- type mismatch WARNING layer (ref DefaultControlValidator.doDataTypeCheck) --

def test_type_mismatch_is_warning_not_error():
    # setting expects INTEGER; value references a STRING variable -> mismatch (warning)
    var = "11111111-2222-4333-8444-555555555555"
    s = {"id": "s1", "type": "text", "label": "N", "isRequired": False,
         "dataTypeId": fv.INTEGER, "isList": False, "value": var}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()],
                 variables=[{"id": var, "name": "s", "dataType": fv.STRING, "isList": False}])
    dts = [{"id": fv.STRING}, {"id": fv.INTEGER}]
    all_w = validate_flow(flow, datatypes=dts, target_vars_of=lambda f: {})
    errs, warns = split_severity(all_w)
    assert any(w["code"] == "TYPE_MISMATCH" for w in warns)
    assert all(e["code"] != "TYPE_MISMATCH" for e in errs)


def test_type_checks_skipped_without_datatypes():
    var = "11111111-2222-4333-8444-555555555555"
    s = {"id": "s1", "type": "text", "label": "N", "dataTypeId": fv.INTEGER, "value": var}
    flow = _flow([_start(ports=[_line("start", "mid")]),
                  _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")]), _stop()],
                 variables=[{"id": var, "name": "s", "dataType": fv.STRING}])
    assert "TYPE_MISMATCH" not in _codes(flow, target_vars_of=lambda f: {})


# -- disabled actions ignored --------------------------------------------------

def test_disabled_action_skipped():
    s = {"id": "s1", "type": "text", "label": "URL", "isRequired": True, "value": ""}
    dead = _act("mid", "Mid", settings=[s], ports=[_line("mid", "stop")])
    dead["isDisabled"] = True
    # a disabled node must not raise REQUIRED; keep a live path so points/connectivity pass
    flow = _flow([_start(ports=[_line("start", "stop")]), dead, _stop()])
    assert "REQUIRED" not in _codes(flow)
