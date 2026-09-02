"""SQL-action parameterization (tools.procesio.flowmodel.sqlparam) — pure-logic unit tests."""
from __future__ import annotations

from tools.procesio.flowmodel import sqlparam

CRED = "45a1dd18-9d06-47cf-8a7b-7732447264af"
SQL = "EXEC dbo.sp_Foo\n    @A = N'<%0%>',\n    @B = N'<%1%>',\n    @TopN = 5"


def _inline_eq_node():
    """An 'Execute Query' node that inlines two values as N'<%0%>' / N'<%1%>' (the anti-pattern)."""
    return {
        "id": "n1", "actionName": "Get X", "actionTemplateName": "Execute Query",
        "templateId": sqlparam.EQ_TEMPLATE_ID,
        "customData": {"configuration": [{"settings": [
            {"id": sqlparam.PID_CRED, "type": "credentials", "value": CRED},
            {"id": sqlparam.PID_SIDEPANEL, "type": "side-pannel", "value": [
                {"id": sqlparam.PID_QUERY, "label": "Query", "type": "code-editor",
                 "language": "sql", "value": SQL},
            ]},
        ]}]},
        "parameters": [
            {"tabPropertyId": sqlparam.PID_CRED, "value": CRED},
            {"tabPropertyId": sqlparam.PID_QUERY, "value": SQL,
             "variable": [{"id": 0, "variableId": "aaaaaaaa-0000-0000-0000-000000000000", "attribute": None},
                          {"id": 1, "variableId": "bbbbbbbb-0000-0000-0000-000000000000", "attribute": None}]},
        ],
    }


def test_scan_flags_inline():
    rows = sqlparam.scan({"actions": [_inline_eq_node()]})
    assert rows == [{"actionName": "Get X", "id": "n1", "template": "Execute Query", "inline": True}]


def test_parameterize_rewrites_sql_and_builds_binding():
    node = _inline_eq_node()
    ok, msg = sqlparam.parameterize_node(node)
    assert ok and "@p0" in msg and "@p1" in msg

    qp = next(p for p in node["parameters"] if isinstance(p["value"], str) and "EXEC" in p["value"])
    assert "<%" not in qp["value"]                       # no inline placeholders left
    assert "@p0" in qp["value"] and "@p1" in qp["value"]  # named params
    assert "@TopN = 5" in qp["value"]                    # literal stays inline
    assert "variable" not in qp                          # inline var-map removed

    bp = next(p for p in node["parameters"] if p["tabPropertyId"] == sqlparam.PID_BIND)
    assert [e["destination"]["value"] for e in bp["value"]] == ["p0", "p1"]
    assert bp["value"][0]["source"]["variable"][0]["variableId"] == "aaaaaaaa-0000-0000-0000-000000000000"

    sub = node["customData"]["configuration"][0]["settings"][1]["value"]
    assert any(s.get("id") == sqlparam.PID_BIND and s.get("type") == "map-parameters" for s in sub)


def test_parameterize_is_idempotent():
    node = _inline_eq_node()
    assert sqlparam.parameterize_node(node)[0] is True
    assert sqlparam.parameterize_node(node)[0] is False   # already parameterized
    assert sqlparam.scan({"actions": [node]})[0]["inline"] is False


def test_attribute_path_source():
    node = _inline_eq_node()
    node["parameters"][1]["variable"][0]["attribute"] = {"attributeId": "cccccccc-0000-0000-0000-000000000000",
                                                         "nextAttribute": None}
    sqlparam.parameterize_node(node)
    bp = next(p for p in node["parameters"] if p["tabPropertyId"] == sqlparam.PID_BIND)
    sub = node["customData"]["configuration"][0]["settings"][1]["value"]
    designer = next(s for s in sub if s.get("id") == sqlparam.PID_BIND)
    assert designer["value"][0]["source"] == "aaaaaaaa-0000-0000-0000-000000000000.cccccccc-0000-0000-0000-000000000000"


def test_v2_template_migrates_to_execute_query():
    # The real bug: a node LABELLED "Execute Query" but on the deprecated V2 template (a9f851c2). Must be
    # keyed on templateId, not the label — else it keeps V2 (no binding property) -> unbound @params.
    node = _inline_eq_node()
    node["actionTemplateName"] = "Execute Query"                       # mislabelled
    node["templateId"] = "a9f851c2-e0ba-4fee-9a06-5445ba000001"        # ...but really on V2
    node["parameters"][0]["tabPropertyId"] = "a9f851c2-e0ba-4fee-9a06-5445bc000011"  # cred (GUID value)
    node["parameters"][1]["tabPropertyId"] = "a9f851c2-e0ba-4fee-9a06-5445bc000014"  # query
    ok, _ = sqlparam.parameterize_node(node)
    assert ok
    assert node["templateId"] == sqlparam.EQ_TEMPLATE_ID              # migrated to the latest template
    qp = next(p for p in node["parameters"] if isinstance(p["value"], str) and "EXEC" in p["value"])
    assert qp["tabPropertyId"] == sqlparam.PID_QUERY
    cred = next(p for p in node["parameters"] if p["value"] == CRED)
    assert cred["tabPropertyId"] == sqlparam.PID_CRED


CMD_SQL = "EXEC xch.Save @Body = N'<%0%>'"
EC_V1 = "c2760ff2-cd9e-49b4-b751-c05c88e06dac"
EC_V1_CRED = "6701cb8b-3bde-4c7e-a45d-c37eaeff5e3d"
EC_V1_SIDE = "fea72099-4718-473d-a091-7749aa38305b"
EC_V1_CMD = "53896b0d-73a6-412f-9e67-224ca1daae7c"
EC_V1_OUT = "f3452b3a-2c10-40df-9d34-2d2779dc6ed7"


def _inline_command_v1_node(label="Execute Command"):
    """An inline-SQL node on the DEPRECATED 'Execute Command V1' template. Note the label says
    'Execute Command' while templateId is V1 - the real-world shape, and why the family is keyed on
    templateId. V1 has no Parameters config tab and no Time Out."""
    return {
        "id": "n2", "actionName": "save rates to DB", "actionTemplateName": label,
        "templateId": EC_V1,
        "customData": {"configuration": [{"settings": [
            {"id": EC_V1_CRED, "type": "credentials", "value": CRED},
            {"id": EC_V1_SIDE, "type": "side-pannel", "value": [
                {"id": EC_V1_CMD, "label": "Command", "type": "code-editor",
                 "language": "sql", "value": CMD_SQL},
                {"id": EC_V1_OUT, "label": "Output", "type": "number", "value": None},
            ]},
        ]}]},
        "parameters": [
            {"tabPropertyId": EC_V1_CRED, "value": CRED},
            {"tabPropertyId": EC_V1_CMD, "value": CMD_SQL,
             "variable": [{"id": 0, "variableId": "dddddddd-0000-0000-0000-000000000000", "attribute": None}]},
            {"tabPropertyId": EC_V1_OUT, "value": "<%1%>",
             "variable": [{"id": 1, "variableId": "eeeeeeee-0000-0000-0000-000000000000", "attribute": None}]},
        ],
    }


def test_family_is_keyed_on_templateid_not_the_label():
    assert sqlparam.family_of(_inline_command_v1_node())[0] == sqlparam.EC_TEMPLATE
    assert sqlparam.family_of(_inline_eq_node())[0] == sqlparam.EQ_TEMPLATE


def test_command_binds_its_own_parameters_tab_not_the_query_one():
    """The bug this guards: writing the Execute QUERY bind id onto a Command node leaves every
    @param unbound at runtime, silently."""
    node = _inline_command_v1_node()
    assert sqlparam.bind_pid(node) == sqlparam.EC_PID_BIND
    assert sqlparam.EC_PID_BIND != sqlparam.PID_BIND
    ok, _ = sqlparam.parameterize_node(node)
    assert ok
    assert any(p["tabPropertyId"] == sqlparam.EC_PID_BIND for p in node["parameters"])
    assert not any(p["tabPropertyId"] == sqlparam.PID_BIND for p in node["parameters"])


def test_command_v1_migrates_to_current_command_template():
    node = _inline_command_v1_node()
    sqlparam.parameterize_node(node)
    assert node["templateId"] == sqlparam.EC_TEMPLATE_ID
    assert node["actionTemplateName"] == sqlparam.EC_TEMPLATE
    ids = {p["tabPropertyId"] for p in node["parameters"]}
    assert sqlparam.EC_PID_CRED in ids and sqlparam.EC_PID_COMMAND in ids and sqlparam.EC_PID_OUTPUT in ids
    assert not (ids & {EC_V1_CRED, EC_V1_CMD, EC_V1_OUT})     # no legacy id left behind
    side = node["customData"]["configuration"][0]["settings"][1]
    assert side["id"] == sqlparam.EC_PID_SIDEPANEL
    assert {s["id"] for s in side["value"]} >= {sqlparam.EC_PID_COMMAND, sqlparam.EC_PID_OUTPUT}


def test_migration_seeds_the_required_timeout_the_legacy_template_lacked():
    node = _inline_command_v1_node()
    sqlparam.parameterize_node(node)
    tp = next(p for p in node["parameters"] if p["tabPropertyId"] == sqlparam.EC_PID_TIMEOUT)
    assert 60 <= int(tp["value"]) <= 1800
    side = node["customData"]["configuration"][0]["settings"][1]["value"]
    assert any(s["id"] == sqlparam.EC_PID_TIMEOUT for s in side)


def test_command_sql_is_rewritten_and_the_variable_moves_to_the_binding():
    node = _inline_command_v1_node()
    sqlparam.parameterize_node(node)
    qp = next(p for p in node["parameters"] if p["tabPropertyId"] == sqlparam.EC_PID_COMMAND)
    assert qp["value"] == "EXEC xch.Save @Body = @p0"
    assert "variable" not in qp
    bp = next(p for p in node["parameters"] if p["tabPropertyId"] == sqlparam.EC_PID_BIND)
    assert bp["value"][0]["destination"]["value"] == "p0"
    assert bp["value"][0]["source"]["variable"][0]["variableId"] == "dddddddd-0000-0000-0000-000000000000"


def test_command_parameterize_is_idempotent():
    node = _inline_command_v1_node()
    assert sqlparam.parameterize_node(node)[0] is True
    assert sqlparam.parameterize_node(node)[0] is False


def test_migration_refreshes_labels_to_the_current_template_wording():
    node = _inline_command_v1_node()
    sqlparam.parameterize_node(node)
    settings = node["customData"]["configuration"][0]["settings"]
    cred = next(s for s in settings if s["id"] == sqlparam.EC_PID_CRED)
    assert cred["label"] == "Select Database Server"      # was the V1 'Select SQL credentials'
    side = next(s for s in settings if s["id"] == sqlparam.EC_PID_SIDEPANEL)
    assert side["label"] == "Execute Command"
    assert {s["label"] for s in side["value"] if s["id"] == sqlparam.EC_PID_COMMAND} == {"Command"}
