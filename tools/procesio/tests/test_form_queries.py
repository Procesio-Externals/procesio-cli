"""A form's saved Data Store queries: the builder config, the QUERY event, the surgical
handlers and the run.

The invariants worth guarding: a save that does not mean to touch the queries never
deletes them (the PUT replaces the whole template), a malformed query is refused before
anything is written, and running a saved statement is never classed as a read.
"""
from __future__ import annotations

import itertools
import json

import pytest

from agents._lib import reversibility
from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import builder as fb
from tools.procesio.dto.form import queries as fq
from tools.procesio.errors import NotPersisted, ProcesioAPIError, UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V", "workspace_id": "WS1"}
STORE, COLUMN, QID = "store-1", "column-1", "11111111-1111-1111-1111-111111111111"
SQL = "SELECT Product, Qty FROM  <%1%>\nWHERE <%2%> = @product"
BINDINGS = [{"id": 1, "type": "dataStoreTable", "dataStoreId": STORE},
            {"id": 2, "type": "dataStoreColumn", "dataStoreId": STORE, "columnId": COLUMN}]


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _ctx():
    cnt = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"}


def _config(**extra) -> dict:
    return {"name": "Stock", "elements": [
        {"type": "input", "name": "product"},
        {"type": "input", "name": "count"},
        {"type": "button", "name": "find", "label": "Find", "events": [
            {"on": "click", "do": "datastore", "operation": "query", "query": "Find product",
             "inputs": [{"left": "@product", "right": "product"}],
             "outputs": [{"left": "count", "right": "count"}]}]},
    ], "queries": [{"name": "Find product", "sql": SQL, "bindings": BINDINGS}], **extra}


def _wire(qid=QID, name="Find product", **over) -> dict:
    return {"id": qid, "name": name, "value": SQL,
            "variable": [{**b, "variableId": None, "attribute": None} for b in BINDINGS],
            "parameters": ["@product"], "timeoutSeconds": None, **over}


def _event(query_id=QID) -> dict:
    return {"id": "ev1", "type": "CLICK", "action": "RUN_DATA_STORE_OPERATION",
            "config": {"dataStoreId": None, "operation": "QUERY", "inputMap": [],
                       "outputMap": [], "filters": [], "queryId": query_id}}


def _form(queries=None, events=None) -> dict:
    """A designer GET echo. No updatedOn/version, so the concurrency guard is inert."""
    return {
        "id": "F1", "name": "Stock", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "queries": [_wire()] if queries is None else queries,
        "data": {"code": "", "elements": [{"id": "b1", "type": "button", "configs": [
            {"id": "c1", "key": "name", "value": "find"},
            {"id": "c2", "key": "onClickEvents",
             "value": {"debounce": 0, "events": events or []}}]}]},
    }


def _click_config(dto: dict) -> dict:
    button = next(e for e in dto["Data"]["elements"] if e["type"] == "button")
    slot = next(c for c in button["configs"] if c["key"] == "onClickEvents")
    return slot["value"]["events"][0]


# -- the statement scan ------------------------------------------------------

def test_parameters_are_read_outside_quotes_and_comments():
    sql = ("SELECT '@inquote', \"@dq\", `@ident`, @@version -- @line\n"
           "/* @block */ # @hash\nFROM t WHERE a = @first AND b = @second OR c = @first")
    assert fq.sql_parameters(sql) == ["@first", "@second"]


# -- form-create / form-edit config ------------------------------------------

def test_queries_config_becomes_the_wire_shape():
    dto = fb.build(_config(), _ctx())
    (query,) = dto["Queries"]
    assert query["name"] == "Find product" and query["value"] == SQL
    assert query["parameters"] == ["@product"] and query["timeoutSeconds"] is None
    assert query["variable"] == _wire()["variable"]
    assert query["id"].startswith("00000000-0000-0000-0000-")


def test_explicit_id_parameters_and_wire_names_pass_through():
    cfg = _config(queries=[{"id": QID, "name": "Find product", "value": SQL,
                            "variable": BINDINGS, "parameters": ["product"],
                            "timeoutSeconds": 30}])
    cfg["elements"][2]["events"][0]["inputs"] = [{"left": "product", "right": "product"}]
    (query,) = fb.build(cfg, _ctx())["Queries"]
    assert (query["id"], query["parameters"], query["timeoutSeconds"]) == (QID, ["product"], 30)


def test_a_config_without_queries_sends_no_queries_key():
    cfg = _config()
    del cfg["queries"]
    cfg["elements"][2]["events"] = []
    assert "Queries" not in fb.build(cfg, _ctx())


def test_query_event_is_saved_as_the_designer_saves_it():
    dto = fb.build(_config(), _ctx())
    event = _click_config(dto)
    root = dto["Data"]["dataModel"]["id"]
    by_name = {next(c["value"] for c in e["configs"] if c["key"] == "name"): e
               for e in dto["Data"]["elements"]}

    def path(name):
        el = by_name[name]
        return f"{root}.{fb._FIELDS_NS}.{el['id']}." + next(
            c["id"] for c in el["configs"] if c["key"] == "value")

    assert event["action"] == "RUN_DATA_STORE_OPERATION" and event["type"] == "CLICK"
    assert event["config"] == {
        "dataStoreId": None, "operation": "QUERY",
        "inputMap": [{"id": 0, "left": "@product", "right": path("product")}],
        # `count` on the left stays the output name although a field is called count
        "outputMap": [{"id": 0, "left": "rows", "right": ""},
                      {"id": 1, "left": "columns", "right": ""},
                      {"id": 2, "left": "count", "right": path("count")},
                      {"id": 3, "left": "success", "right": ""}],
        "filters": [], "queryId": dto["Queries"][0]["id"]}
    assert list(event["config"]) == ["dataStoreId", "operation", "inputMap", "outputMap",
                                     "filters", "queryId"]


def test_rows_mapped_to_a_dynamic_table_go_to_its_row_source():
    cfg = _config()
    cfg["elements"][2]["events"][0]["outputs"] = [{"left": "rows", "right": "products"}]
    cfg["elements"].append({"type": "table", "dynamic": True, "name": "products",
                            "label": "Products", "columns": [
                                {"key": "Product", "label": "Product",
                                 "cell": {"type": "input", "name": "rowproduct"}}]})
    dto = fb.build(cfg, _ctx())
    row = next(e for e in dto["Data"]["elements"] if e["type"] == "dynamic-table-row")
    source = next(c["id"] for c in row["configs"] if c["key"] == "sourceValue")
    rows = _click_config(dto)["config"]["outputMap"][0]

    assert rows == {"id": 0, "left": "rows", "right":
                    f"{dto['Data']['dataModel']['id']}.{fb._FIELDS_NS}.{row['id']}.{source}"}
    # the path must resolve: the row's data model carries the attribute it points at
    assert f'"id": "{source}", "name": "sourceValue"' in json.dumps(dto["Data"]["dataModel"])


def _products_table(dynamic=True) -> dict:
    return {"type": "table", "dynamic": dynamic, "name": "products", "label": "Products",
            "columns": [{"key": "Product", "label": "Product",
                         "cell": {"type": "input", "name": "rowproduct"}}]}


def test_rows_reach_a_dynamic_table_nested_in_a_section():
    """A table inside a container is built with a copy of the build context; its row
    source must still be seen by the query wiring."""
    cfg = _config()
    cfg["elements"][2]["events"][0]["outputs"] = [{"left": "rows", "right": "products"}]
    cfg["elements"].append({"type": "section", "name": "results",
                            "children": [_products_table()]})
    dto = fb.build(cfg, _ctx())
    row = next(e for e in dto["Data"]["elements"] if e["type"] == "dynamic-table-row")
    source = next(c["id"] for c in row["configs"] if c["key"] == "sourceValue")
    rows = _click_config(dto)["config"]["outputMap"][0]
    assert rows["right"] == f"{dto['Data']['dataModel']['id']}.{fb._FIELDS_NS}.{row['id']}.{source}"


@pytest.mark.parametrize("target", ["products", "productsrow"])
def test_rows_aimed_at_a_static_table_are_refused(target):
    cfg = _config()
    cfg["elements"][2]["events"][0]["outputs"] = [{"left": "rows", "right": target}]
    cfg["elements"].append(_products_table(dynamic=False))
    with pytest.raises(UsageError, match="only a dynamic table"):
        fb.build(cfg, _ctx())


def test_query_event_fails_loudly_on_an_unknown_query():
    cfg = _config()
    cfg["elements"][2]["events"][0]["query"] = "No such query"
    with pytest.raises(UsageError, match="no saved query.*'Find product'"):
        fb.build(cfg, _ctx())


def test_query_event_refuses_a_parameter_spelled_differently():
    cfg = _config()
    cfg["elements"][2]["events"][0]["inputs"] = [{"left": "product", "right": "product"}]
    with pytest.raises(UsageError, match="exactly as declared: '@product'"):
        fb.build(cfg, _ctx())


def test_query_event_refuses_an_unknown_output():
    cfg = _config()
    cfg["elements"][2]["events"][0]["outputs"] = [{"left": "total", "right": "count"}]
    with pytest.raises(UsageError, match="rows \\| columns \\| count \\| success"):
        fb.build(cfg, _ctx())


@pytest.mark.parametrize("change, problem", [
    ({"bindings": BINDINGS[:1]}, "tag <%2%> has no binding"),
    ({"bindings": BINDINGS + [BINDINGS[0]]}, "tag <%1%> is bound 2 times"),
    ({"bindings": [{**BINDINGS[0], "type": "table"}, BINDINGS[1]]}, "unknown kind 'table'"),
    ({"bindings": [{**BINDINGS[0], "variableId": "v1"}, BINDINGS[1]]}, "process variable"),
    ({"bindings": [BINDINGS[0], {**BINDINGS[1], "columnId": None}]}, "without a columnId"),
    ({"parameters": ["@1bad"]}, "not a valid name"),
    ({"parameters": ["@" + "p" * 65]}, "longer than 64"),
    ({"parameters": ["@product", "@product"]}, "declared twice"),
    ({"timeoutSeconds": 0}, "outside 1..600"),
    ({"timeoutSeconds": 601}, "outside 1..600"),
    ({"sql": "  ", "bindings": []}, "query text is empty"),
])
def test_a_malformed_query_is_refused_before_the_save(change, problem):
    query = {"name": "Find product", "sql": SQL, "bindings": BINDINGS, **change}
    with pytest.raises(UsageError) as e:
        fb.build(_config(queries=[query]), _ctx())
    assert f"queries[0] 'Find product': " in str(e.value) and problem in str(e.value)


def test_duplicate_ids_and_names_are_refused():
    found = fq.problems([_wire(), _wire()])
    assert any("the id" in p and "another query" in p for p in found)
    assert any("the name is used by another query" in p for p in found)


def test_numeric_binding_kinds_are_accepted():
    assert fq.problems([_wire(variable=[{**BINDINGS[0], "type": 1}, {**BINDINGS[1], "type": 2}])]) == []


def test_an_unreferenced_query_is_reported_as_a_lint_warning():
    cfg = _config()
    cfg["elements"][2]["events"] = []
    warnings = fb._lint(fb.build(cfg, _ctx()))
    assert any("'Find product' is run by no event" in w for w in warnings)
    assert not any("run by no event" in w for w in fb._lint(fb.build(_config(), _ctx())))


# -- form-edit keeps what it was not told about -------------------------------

def _plain_config() -> dict:
    return {"name": "Stock", "elements": [{"type": "input", "name": "product"}]}


def test_form_edit_without_queries_keeps_the_live_ones():
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {}), FakeResp(200, _form())])
    _call("form-edit", ["--id", "F1", "--config", json.dumps(_plain_config())], s)
    live_read, put, _ = s.calls
    assert live_read["method"] == "GET" and live_read["url"].endswith("/api/FormTemplate/F1")
    assert put["method"] == "PUT" and put["json"]["Id"] == "F1"
    assert put["json"]["Queries"] == [_wire()]


def test_form_edit_can_wire_an_event_to_a_live_query_by_name():
    cfg = _config()
    del cfg["queries"]
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {}), FakeResp(200, _form())])
    _call("form-edit", ["--id", "F1", "--config", json.dumps(cfg)], s)
    assert _click_config(s.calls[1]["json"])["config"]["queryId"] == QID


def test_form_edit_stops_before_writing_when_the_live_form_cannot_be_read():
    s = FakeSession(queue=[FakeResp(200, {"unexpected": True})])
    with pytest.raises(UsageError, match="nothing was written"):
        _call("form-edit", ["--id", "F1", "--config", json.dumps(_plain_config())], s)
    assert [c["method"] for c in s.calls] == ["GET"]


def test_form_edit_with_queries_replaces_them_without_reading_the_live_form():
    """Listing both `queries` and `events` leaves nothing to carry over from the live form."""
    cfg = {**_plain_config(), "queries": [], "events": []}
    s = FakeSession(queue=[FakeResp(200, {}), FakeResp(200, _form(queries=[]))])
    _call("form-edit", ["--id", "F1", "--config", json.dumps(cfg)], s)
    assert [c["method"] for c in s.calls] == ["PUT", "GET"]
    assert s.calls[0]["json"]["Queries"] == []


def test_form_edit_with_queries_still_reads_the_live_form_for_its_events():
    cfg = {**_plain_config(), "queries": []}
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {}), FakeResp(200, _form(queries=[]))])
    _call("form-edit", ["--id", "F1", "--config", json.dumps(cfg)], s)
    assert [c["method"] for c in s.calls] == ["GET", "PUT", "GET"]
    assert s.calls[1]["json"]["Queries"] == []


def test_form_edit_dry_run_previews_the_carried_queries():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-edit", ["--id", "F1", "--dry-run", "--config", json.dumps(_plain_config())], s)
    assert out["dto"]["Queries"] == [_wire()] and out["dto"]["Id"] == "F1"
    assert [c["method"] for c in s.calls] == ["GET"]


# -- form-get-queries ---------------------------------------------------------

def test_get_queries_lists_them_with_the_elements_that_run_them():
    other = _wire("22222222-2222-2222-2222-222222222222", "Orphan")
    s = FakeSession(queue=[FakeResp(200, _form(queries=[_wire(), other], events=[_event()]))])
    out = _call("form-get-queries", ["--form-id", "F1"], s)
    assert out["count"] == 2 and out["queries"][0] == _wire()
    assert out["run_by"] == {QID: ["find"], other["id"]: []}
    assert len(out["warnings"]) == 1 and "'Orphan'" in out["warnings"][0]


# -- form-set-saved-statement -------------------------------------------------

def test_set_adds_a_query_and_keeps_the_others():
    after = _form(queries=[_wire(), _wire("new-id", "Count stock")])
    s = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {}), FakeResp(200, after)])
    out = _call("form-set-saved-statement",
                ["--form-id", "F1", "--query-id", "new-id", "--name", "Count stock",
                 "--sql", "SELECT COUNT(*) AS n FROM <%1%> WHERE Qty > @min",
                 "--bindings", json.dumps(BINDINGS[:1]), "--timeout-seconds", "120"], s)
    body = s.calls[1]["json"]
    assert s.calls[1]["method"] == "PUT" and body["Id"] == "F1"
    assert body["Queries"][0] == _wire()
    assert body["Queries"][1] == {
        "id": "new-id", "name": "Count stock",
        "value": "SELECT COUNT(*) AS n FROM <%1%> WHERE Qty > @min",
        "variable": [{**BINDINGS[0], "variableId": None, "attribute": None}],
        "parameters": ["@min"], "timeoutSeconds": 120}
    assert body["Data"] == _form()["data"]
    assert out["created"] is True and out["verified"] is True and out["previous"] is None
    assert "run by no event" in out["warnings"][0]


def test_set_changes_one_query_by_name_and_rederives_parameters():
    s = FakeSession(queue=[FakeResp(200, _form(events=[_event()])), FakeResp(200, {}),
                           FakeResp(200, _form())])
    out = _call("form-set-saved-statement",
                ["--form-id", "F1", "--name", "Find product",
                 "--sql", "SELECT Product FROM <%1%> WHERE <%2%> = @name AND Qty > @min"], s)
    (query,) = s.calls[1]["json"]["Queries"]
    assert query["id"] == QID and query["parameters"] == ["@name", "@min"]
    assert query["variable"] == _wire()["variable"]
    assert out["created"] is False and out["previous"] == _wire()
    assert out["run_by"] == ["find"] and "warnings" not in out


def test_set_warns_about_an_insert_without_the_audit_columns_even_when_an_event_runs_it():
    s = FakeSession(queue=[FakeResp(200, _form(events=[_event()]))])
    out = _call("form-set-saved-statement",
                ["--form-id", "F1", "--name", "Find product", "--dry-run",
                 "--sql", "INSERT INTO <%1%> (<%2%>) VALUES (@name)"], s)
    (warning,) = out["warnings"]
    assert out["run_by"] == ["find"] and "CreatedById and UpdatedById" in warning


def test_set_dry_run_writes_nothing():
    s = FakeSession(queue=[FakeResp(200, _form())])
    out = _call("form-set-saved-statement",
                ["--form-id", "F1", "--name", "Find product", "--timeout-seconds", "30", "--dry-run"], s)
    assert out["dry_run"] is True and out["query"]["timeoutSeconds"] == 30
    assert [c["method"] for c in s.calls] == ["GET"]


def test_set_refuses_a_malformed_query_before_any_write():
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError, match="tag <%3%> has no binding"):
        _call("form-set-saved-statement",
              ["--form-id", "F1", "--name", "Find product", "--sql", "SELECT * FROM <%3%>"], s)
    assert [c["method"] for c in s.calls] == ["GET"]


def test_set_reports_a_save_the_server_did_not_keep():
    s = FakeSession(queue=[FakeResp(200, _form(queries=[])), FakeResp(200, {}),
                           FakeResp(200, _form(queries=[]))])
    with pytest.raises(NotPersisted):
        _call("form-set-saved-statement",
              ["--form-id", "F1", "--name", "Q", "--sql", "SELECT 1"], s)


# -- form-delete-saved-statement ----------------------------------------------

def test_delete_is_refused_while_an_event_runs_the_query():
    s = FakeSession(queue=[FakeResp(200, _form(events=[_event()]))])
    with pytest.raises(UsageError, match="still run by an event on find"):
        _call("form-delete-saved-statement", ["--form-id", "F1", "--query-id", "Find product"], s)
    assert [c["method"] for c in s.calls] == ["GET"]


def test_delete_of_a_referenced_query_can_be_forced():
    s = FakeSession(queue=[FakeResp(200, _form(events=[_event()])), FakeResp(200, {}),
                           FakeResp(200, _form(queries=[]))])
    out = _call("form-delete-saved-statement",
                ["--form-id", "F1", "--query-id", QID, "--allow-referenced"], s)
    assert s.calls[1]["json"]["Queries"] == []
    assert out["deleted"] is True and out["removed"] == _wire() and out["run_by"] == ["find"]


def test_delete_removes_only_the_named_query():
    other = _wire("22222222-2222-2222-2222-222222222222", "Other")
    s = FakeSession(queue=[FakeResp(200, _form(queries=[_wire(), other])), FakeResp(200, {}),
                           FakeResp(200, _form(queries=[other]))])
    _call("form-delete-saved-statement", ["--form-id", "F1", "--query-id", "Find product"], s)
    assert s.calls[1]["json"]["Queries"] == [other]


# -- form-run-saved-statement -------------------------------------------------

RESULT = {"columns": [{"columnId": COLUMN, "name": "Product"}],
          "rows": {"totalItemCount": 1, "pageNumber": 1, "pageItemCount": 1,
                   "pageItems": [{"Product": "apple", "Qty": 3}]}}


def _raw(status, body):
    return FakeResp(status, content=json.dumps(body).encode("utf-8"))


def test_run_posts_to_the_form_runtime_route_scoped_by_header():
    s = FakeSession(queue=[FakeResp(200, _form()), _raw(200, RESULT)])
    out = _call("form-run-saved-statement",
                ["--form-id", "F1", "--query-id", "Find product", "--params",
                 '{"@product": "apple"}', "--form-instance-id", "I1", "--workspace-id", "WS1"], s)
    post = s.calls[1]
    assert post["method"] == "POST" and post["url"].endswith(f"/api/Form/dataStore/query/{QID}")
    assert post["json"] == {"parameters": {"@product": "apple"}}
    assert post["headers"]["formTemplateWorkspaceId"] == "WS1"
    assert post["headers"]["formTemplateId"] == "F1" and post["headers"]["formInstanceId"] == "I1"
    assert post["headers"]["workspaceid"] == "WS1"
    assert out["rows"] == [{"Product": "apple", "Qty": 3}] and out["count"] == 1
    assert out["parameters_bound_null"] == []


def test_run_names_the_form_workspace_separately_when_asked():
    s = FakeSession(queue=[FakeResp(200, _form()), _raw(200, RESULT)])
    out = _call("form-run-saved-statement",
                ["--form-id", "F1", "--query-id", QID, "--form-workspace-id", "WS2"], s)
    post = s.calls[1]
    assert post["headers"]["formTemplateWorkspaceId"] == "WS2"
    assert "formInstanceId" not in post["headers"] and post["json"] is None
    assert out["parameters_bound_null"] == ["@product"]


@pytest.mark.parametrize("params", ['{"product": "apple"}', '{"@Product": "apple"}',
                                    '{"@product": "apple", "@extra": 1}'])
def test_run_refuses_undeclared_parameter_names_before_calling(params):
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError, match="exactly as declared: '@product'"):
        _call("form-run-saved-statement",
              ["--form-id", "F1", "--query-id", QID, "--params", params], s)
    assert [c["method"] for c in s.calls] == ["GET"]


def test_run_refuses_an_unknown_query_before_calling():
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError, match="no saved query"):
        _call("form-run-saved-statement", ["--form-id", "F1", "--query-id", "nope"], s)
    assert len(s.calls) == 1


@pytest.mark.parametrize("limit, waited", [(None, 120), (30, 120), (90, 120), (300, 330),
                                           (600, 630)])
def test_run_waits_longer_than_the_query_may_run(limit, waited):
    """A client that gives up before the server's own limit reports a failure for a write
    that still commits; a retry then writes twice."""
    s = FakeSession(queue=[FakeResp(200, _form(queries=[_wire(timeoutSeconds=limit)])),
                           _raw(200, RESULT)])
    _call("form-run-saved-statement", ["--form-id", "F1", "--query-id", QID], s)
    assert s.calls[1]["timeout"] == waited


def test_run_surfaces_the_platform_error_body():
    refusal = {"statusCode": 502, "target": "query",
               "value": "The query did not finish within the configured time limit."}
    s = FakeSession(queue=[FakeResp(200, _form()), _raw(400, refusal)])
    with pytest.raises(ProcesioAPIError) as e:
        _call("form-run-saved-statement", ["--form-id", "F1", "--query-id", QID], s)
    assert e.value.status == 400 and e.value.details == refusal


# -- a build without the feature: the save answers 200 and keeps no queries ---

def _older_build(stored_form: dict):
    """A server whose PUT/POST accept anything and whose GET returns `stored_form`."""
    def respond(method, url, kw):
        if method == "GET" and "/api/FormTemplate/" in url:
            return FakeResp(200, stored_form)
        if method == "POST":
            return FakeResp(200, {"id": "F1"})
        return FakeResp(200, {})
    return FakeSession(responder=respond)


def _without_queries_key() -> dict:
    form = _form()
    del form["queries"]
    return form


@pytest.mark.parametrize("action, argv", [
    ("form-create", []),
    ("form-edit", ["--id", "F1"]),
])
def test_a_save_that_drops_the_queries_is_reported(action, argv):
    s = _older_build(_without_queries_key())
    out = _call(action, argv + ["--config", json.dumps(_config())], s)
    (warning,) = [w for w in out.get("warnings", []) if "did not keep its saved queries" in w]
    assert "'Find product'" in warning and "returns no `queries` at all" in warning


def test_a_save_that_keeps_the_queries_reports_nothing_about_them():
    cfg = _config(queries=[{"id": QID, "name": "Find product", "sql": SQL, "bindings": BINDINGS}])
    s = _older_build(_form())
    out = _call("form-edit", ["--id", "F1", "--config", json.dumps(cfg)], s)
    assert not [w for w in out.get("warnings", []) if "did not keep" in w]


def test_a_save_without_queries_is_never_checked_for_them():
    assert fb._persist_check({"Data": {}}, _without_queries_key()) == []
    assert fb._persist_check({"Queries": []}, _without_queries_key()) == []


# -- reversibility: a saved statement can write ------------------------------

def test_running_a_saved_statement_needs_approval():
    verdict = reversibility.classify("procesio", ["form-run-saved-statement"])
    assert verdict["reversible"] is False and verdict["blast_class"] == "data-loss"
    assert reversibility.is_read_only("procesio", ["form-run-saved-statement"]) is False
    decision = reversibility.decide("procesio", ["form-run-saved-statement"], level="L1")
    assert decision["allow"] and decision["needs_confirmation"]
    assert reversibility.decide("procesio", ["form-run-saved-statement"], level="L0")["allow"] is False


def test_the_other_query_actions_are_classed_by_what_they_do():
    assert reversibility.is_read_only("procesio", ["form-get-queries"]) is True
    # a write: not a read, although its subject is a query
    assert reversibility.is_read_only("procesio", ["form-set-saved-statement"]) is False
    assert reversibility.classify("procesio", ["form-set-saved-statement"])["reversible"] is True
    removal = reversibility.classify("procesio", ["form-delete-saved-statement"])
    assert removal["reversible"] is False and removal["verb"] == "delete"


def test_no_write_action_of_this_module_carries_a_read_verb():
    from tools.procesio.handlers import form_queries
    writes = set(form_queries.ACTIONS) - {"form-get-queries"}
    assert writes and not [a for a in writes if reversibility.is_read_only("procesio", [a])]


# -- form-set-element-event: operation QUERY -----------------------------------

def test_set_element_event_wires_a_saved_query_by_name():
    from tools.procesio.dto.form import fieldpath
    form = _form()
    form["data"]["dataModel"] = {"id": "dm"}
    form["data"]["elements"] += [
        {"id": "i1", "type": "input", "configs": [
            {"id": "n1", "key": "name", "value": "product"}, {"id": "v1", "key": "value"}]},
        {"id": "i2", "type": "input", "configs": [
            {"id": "n2", "key": "name", "value": "found"}, {"id": "v2", "key": "value"}]}]
    s = FakeSession(queue=[FakeResp(200, form), FakeResp(200, {})])
    config = {"query": "Find product",
              "inputMap": [{"id": 0, "left": "@product", "right": "product"}],
              "outputMap": [{"id": 0, "left": "count", "right": "found"}]}
    out = _call("form-set-element-event",
                ["--id", "F1", "--element", "find", "--on", "click",
                 "--action", "RUN_DATA_STORE_OPERATION", "--operation", "query",
                 "--config", json.dumps(config)], s)
    ns = fieldpath.FIELDS_NS
    assert out["event"]["config"] == {
        "dataStoreId": None, "operation": "QUERY",
        "inputMap": [{"id": 0, "left": "@product", "right": f"dm.{ns}.i1.v1"}],
        "outputMap": [{"id": 0, "left": "count", "right": f"dm.{ns}.i2.v2"}],
        "filters": [], "queryId": QID}
    assert s.calls[1]["json"]["Queries"] == [_wire()]


def test_set_element_event_refuses_an_undeclared_query_parameter():
    s = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(UsageError, match="exactly as declared"):
        _call("form-set-element-event",
              ["--id", "F1", "--element", "find", "--on", "click",
               "--action", "RUN_DATA_STORE_OPERATION", "--operation", "QUERY",
               "--config", json.dumps({"queryId": QID, "inputMap": [{"left": "product", "right": "p"}]})], s)
    assert [c["method"] for c in s.calls] == ["GET"]


def test_an_insert_without_the_audit_columns_is_warned_about():
    insert = {"name": "Add", "value": "insert into <%1%> (<%2%>, CreatedById) VALUES (@a, @who)"}
    complete = {"name": "Add all", "value": "INSERT INTO <%1%> (<%2%>, CreatedById, UpdatedById) "
                                            "VALUES (@a, @who, @who)"}
    update = {"name": "Change", "value": "UPDATE <%1%> SET <%2%> = @a"}

    (warning,) = fq.audit_warnings([insert, complete, update])

    assert "'Add'" in warning and "UpdatedById" in warning and "CreatedById and" not in warning


def test_two_spellings_of_one_parameter_pass_the_save_and_are_warned_about():
    query = fq.from_config({"name": "Find product", "sql": SQL, "bindings": BINDINGS,
                            "parameters": ["@product", "product", "Product"]})
    assert fq.problems([query]) == []
    (warning,) = fq.spelling_warnings([query])
    assert "@product, Product, product" in warning


def test_a_binding_no_tag_uses_is_not_checked():
    unused = [{"id": 9, "variableId": "v1"}, {"id": 9, "type": "nonsense"}]
    query = fq.from_config({"name": "Find product", "sql": SQL, "bindings": BINDINGS + unused})
    assert fq.problems([query]) == []



def test_a_query_name_over_128_characters_is_refused():
    query = fq.from_config({"name": "n" * 129, "sql": SQL, "bindings": BINDINGS})
    (problem,) = fq.problems([query])
    assert "longer than 128" in problem


def test_process_rows_mapped_to_a_dynamic_table_go_to_its_row_source():
    """A RUN_PROCESS output reaches a table the same way a query's rows do: through the
    dynamic row's source (verified in the form runtime, 2026-11). Named by the table, the
    builder used to write the bare name, and the table stayed empty."""
    cfg = {"name": "Stock", "elements": [
        {"type": "input", "name": "category"},
        {"type": "button", "name": "find", "events": [
            {"on": "click", "do": "process", "processId": "P1", "syncRun": True,
             "inputs": [{"to": "category", "from": "category"}],
             "outputs": [{"to": "products", "from": "rows"}]}]},
        _products_table()]}
    ctx = {**_ctx(), "process_vars": {"P1": {"category": "v-cat", "rows": "v-rows"}}}
    dto = fb.build(cfg, ctx)
    row = next(e for e in dto["Data"]["elements"] if e["type"] == "dynamic-table-row")
    source = next(c["id"] for c in row["configs"] if c["key"] == "sourceValue")
    out = _click_config(dto)["config"]["outputMap"][0]

    assert out == {"id": 0, "left": "v-rows", "right":
                   f"{dto['Data']['dataModel']['id']}.{fb._FIELDS_NS}.{row['id']}.{source}"}
