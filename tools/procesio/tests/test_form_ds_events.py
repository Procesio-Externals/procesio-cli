"""A form reads a Data Store itself: form-level events (onLoad / before / after submit), READ
filters, a query or a READ filling a dropdown, and form-edit keeping the events the designer
made. Every wire shape asserted here was captured from a designer save on production
(2026-11-19) and then run in the form runtime."""
from __future__ import annotations

import itertools
import json

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import builder as fb
from tools.procesio.dto.form import queries as form_queries
from tools.procesio.errors import UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V", "workspace_id": "WS1"}
STORE, QID = "store-1", "11111111-1111-1111-1111-111111111111"
QUERY = {"id": QID, "name": "Product list",
         "sql": "SELECT Sku AS value, Product AS label FROM <%1%> WHERE Qty > @minqty",
         "bindings": [{"id": 1, "type": "dataStoreTable", "dataStoreId": STORE}]}


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _ctx(**extra):
    cnt = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}", **extra}


def _table():
    return {"type": "table", "dynamic": True, "name": "products", "label": "Products",
            "columns": [{"key": "Sku", "label": "SKU", "cell": {"type": "input", "name": "rowsku"}}]}


def _config(events, **extra):
    return {"name": "Stock", "elements": [
        {"type": "input", "name": "category"},
        {"type": "input", "name": "count"},
        {"type": "select", "name": "productpick", "label": "Product"},
        _table()], "events": events, **extra}


def _read(**extra):
    return {"on": "load", "do": "datastore", "operation": "read", "dataStoreId": STORE,
            "outputs": [{"left": "rows", "right": "products"}, {"left": "count", "right": "count"}],
            **extra}


def _el(dto, name):
    return next(e for e in dto["Data"]["elements"]
                if any(c.get("key") == "name" and c.get("value") == name for c in e["configs"]))


def _cfg(el, key):
    return next(c for c in el["configs"] if c["key"] == key)


def _path(dto, el, key):
    return f"{dto['Data']['dataModel']['id']}.{fb._FIELDS_NS}.{el['id']}.{_cfg(el, key)['id']}"


# -- form-level events ---------------------------------------------------------

def test_a_load_event_is_saved_in_data_events_as_the_designer_saves_it():
    dto = fb.build(_config([_read()]), _ctx(form_id="F1"))
    [ev] = dto["Data"]["events"]
    assert ev["type"] == "FORM_LOAD" and ev["action"] == "RUN_DATA_STORE_OPERATION"
    cfg = ev["config"]
    assert cfg["dataStoreId"] == STORE and cfg["operation"] == "READ"
    assert cfg["inputMap"] == [{"id": 0, "left": "page", "right": "1"},
                               {"id": 1, "left": "countPerPage", "right": "1000"}]
    assert [o["left"] for o in cfg["outputMap"]] == ["rows", "columns", "count", "success"]


@pytest.mark.parametrize("on,kind", [("load", "FORM_LOAD"),
                                     ("beforesubmit", "FORM_BEFORE_SUBMIT"),
                                     ("aftersubmit", "FORM_AFTER_SUBMIT")])
def test_each_form_trigger_has_its_designer_type(on, kind):
    dto = fb.build(_config([{**_read(), "on": on}]), _ctx(form_id="F1"))
    assert dto["Data"]["events"][0]["type"] == kind


def test_an_element_trigger_is_refused_at_form_level():
    with pytest.raises(UsageError, match="form-level event"):
        fb.build(_config([{**_read(), "on": "click"}]), _ctx(form_id="F1"))


def test_read_rows_reach_a_dynamic_table_and_count_a_field_named_like_the_output():
    """`count` is both an output name and a field here: only the right side is a field."""
    dto = fb.build(_config([_read()]), _ctx(form_id="F1"))
    out = dto["Data"]["events"][0]["config"]["outputMap"]
    row = next(e for e in dto["Data"]["elements"] if e["type"] == "dynamic-table-row")
    assert out[0] == {"id": 0, "left": "rows", "right": _path(dto, row, "sourceValue")}
    assert out[2] == {"id": 2, "left": "count", "right": fb_field(dto, "count")}


def fb_field(dto, name):
    el = _el(dto, name)
    return _path(dto, el, "value")


# -- READ filters --------------------------------------------------------------

def test_compact_filters_become_the_designer_conditions():
    ev = _read(filters=[{"column": "Category", "op": "equals", "field": "category"},
                        {"column": "Qty", "op": ">", "value": 10}])
    dto = fb.build(_config([ev]), _ctx(form_id="F1"))
    cfg = dto["Data"]["events"][0]["config"]
    first, second = cfg["filters"]
    assert cfg["areFiltersConfigured"] is True
    assert first["operator"] == "EQUALS" and first["logicOperator"] == 1
    assert first["leftOperator"] == {"variable": "", "attribute": {"id": "", "nextAttribute": None},
                                     "value": "Category"}
    assert first["rightOperator"]["value"] == fb_field(dto, "category")
    assert second["operator"] == "GREATER_THAN" and second["logicOperator"] == 0
    assert second["rightOperator"]["value"] == "10"
    assert first["value"] is None and first["operandsAsListOptional"] is True


def test_or_joins_conditions_and_between_takes_an_aux_value():
    ev = _read(logic="or", filters=[{"column": "Qty", "op": "between", "value": 1, "aux": 5},
                                    {"column": "Category", "op": "isEmpty"}])
    cfg = fb.build(_config([ev]), _ctx(form_id="F1"))["Data"]["events"][0]["config"]
    assert [c["logicOperator"] for c in cfg["filters"]] == [2, 0]
    assert cfg["filters"][0]["operator"] == "BETWEEN"
    assert cfg["filters"][0]["auxOperator"]["value"] == "5"
    assert cfg["filters"][1]["operator"] == "IS_EMPTY"


def test_an_unknown_operator_or_field_is_refused():
    with pytest.raises(UsageError, match="operator"):
        fb.build(_config([_read(filters=[{"column": "Qty", "op": "about", "value": 1}])]),
                 _ctx(form_id="F1"))
    with pytest.raises(UsageError, match="nosuch"):
        fb.build(_config([_read(filters=[{"column": "Qty", "op": "equals", "field": "nosuch"}])]),
                 _ctx(form_id="F1"))


def test_designer_conditions_pass_through_unchanged():
    raw = [{"id": 0, "operator": "EQUALS", "leftOperator": {"value": "Category"},
            "rightOperator": {"value": "x"}, "logicOperator": 0}]
    cfg = fb.build(_config([_read(filters=raw)]), _ctx(form_id="F1"))["Data"]["events"][0]["config"]
    assert cfg["filters"] == raw


# -- a query or a READ filling a dropdown ----------------------------------------

def test_query_rows_fill_a_dropdown_with_a_typed_parameter_value():
    ev = {"on": "load", "do": "datastore", "operation": "query", "query": "Product list",
          "inputs": [{"left": "@minqty", "value": "50"}],
          "outputs": [{"left": "rows", "right": "productpick"}]}
    dto = fb.build(_config([ev], queries=[QUERY]), _ctx(form_id="F1"))
    cfg = dto["Data"]["events"][0]["config"]
    pick = _el(dto, "productpick")
    assert cfg["inputMap"] == [{"id": 0, "left": "@minqty", "right": "50"}]
    assert cfg["outputMap"][0]["right"] == _path(dto, pick, "sourceValue")
    # without a source type the dropdown builds no options from the rows
    assert _cfg(pick, "sourceType")["value"] == "JSON"
    assert _cfg(pick, "sourceValue")["id"] in json.dumps(dto["Data"]["dataModel"])


def test_an_element_event_can_fill_a_dropdown_too():
    cfg = _config([], queries=[QUERY])
    cfg["elements"][0]["events"] = [{"on": "input", "do": "datastore", "operation": "query",
                                     "query": "Product list",
                                     "inputs": [{"left": "@minqty", "right": "category"}],
                                     "outputs": [{"left": "rows", "right": "productpick"}]}]
    dto = fb.build(cfg, _ctx(form_id="F1"))
    ev = _cfg(_el(dto, "category"), "onInputEvents")["value"]["events"][0]
    assert ev["config"]["outputMap"][0]["right"] == _path(dto, _el(dto, "productpick"), "sourceValue")


# -- form-edit keeps the form's own events; queries run by them count ----------------

def _live(events):
    return {"id": "F1", "name": "Stock", "isPrivate": False, "type": 1, "status": 1,
            "state": True, "assignees": [], "customUrl": None, "queries": [],
            "data": {"code": "", "events": events, "elements": []}}


LIVE_EVENT = {"id": "e1", "type": "FORM_LOAD", "action": "RUN_DATA_STORE_OPERATION",
              "config": {"dataStoreId": STORE, "operation": "READ"}}


def test_form_edit_without_events_keeps_the_live_form_events():
    cfg = {"name": "Stock", "elements": [{"type": "input", "name": "a"}]}
    s = FakeSession(queue=[FakeResp(200, _live([LIVE_EVENT])), FakeResp(200, {}),
                           FakeResp(200, _live([LIVE_EVENT]))])
    _call("form-edit", ["--id", "F1", "--config", json.dumps(cfg)], s)
    put = next(c for c in s.calls if c["method"] == "PUT")
    assert put["json"]["Data"]["events"] == [LIVE_EVENT]


def test_form_edit_with_events_replaces_them():
    cfg = {"name": "Stock", "events": [], "queries": [],
           "elements": [{"type": "input", "name": "a"}]}
    s = FakeSession(queue=[FakeResp(200, {}), FakeResp(200, _live([]))])
    _call("form-edit", ["--id", "F1", "--config", json.dumps(cfg)], s)
    put = next(c for c in s.calls if c["method"] == "PUT")
    assert put["json"]["Data"]["events"] == []


def test_a_query_run_only_by_a_form_event_is_not_reported_as_unreferenced():
    events = [{"id": "e1", "type": "FORM_LOAD", "action": "RUN_DATA_STORE_OPERATION",
               "config": {"operation": "QUERY", "queryId": QID}}]
    wire = [{"id": QID, "name": "Product list", "value": "SELECT 1", "parameters": []}]
    assert form_queries.references([], events) == {QID: ["form onLoad"]}
    assert form_queries.unreferenced_warnings(wire, [], events) == []


# -- drafts ----------------------------------------------------------------------

def test_a_draft_form_is_reported_offline():
    warnings = fb._lint({"status": 0, "data": {"elements": [], "events": []}})
    assert any("draft" in w and "not reachable" in w for w in warnings)
    assert not any("draft" in w for w in fb._lint({"status": 1, "data": {"elements": []}}))


def test_process_ids_on_form_events_are_resolved_too():
    out: set = set()
    fb._collect_process_ids_config({"events": [{"on": "load", "do": "process", "processId": "P9"}],
                                    "elements": []}, out)
    assert out == {"P9"}


# -- writes: ADD / UPDATE / DELETE ----------------------------------------------------
# Verified on production 2026-11-19: Add fills CreatedById/UpdatedById itself; an Update
# without a filter never works (the runtime matches by every mapped column, and the
# server refuses a mapped key column: "Primary key columns cannot be updated from this
# endpoint"); a Delete without a filter deletes by every mapped column.

COLUMNS = {STORE: {"names": ["Sku", "Product", "Qty", "Category"], "pk": ["Sku"]}}


def _write(op, **extra):
    ev = {"on": "click", "do": "datastore", "operation": op, "dataStoreId": STORE,
          "outputs": [{"left": "success", "right": "count"}], **extra}
    cfg = _config([])
    cfg["elements"].append({"type": "button", "name": "go", "events": [ev]})
    return cfg


def _go(dto):
    return _cfg(_el(dto, "go"), "onClickEvents")["value"]["events"][0]["config"]


def test_add_is_saved_as_the_designer_saves_it():
    cfg = _write("add", inputs=[{"left": "Sku", "right": "category"},
                                {"left": "Category", "value": "test"}])
    dto = fb.build(cfg, _ctx(form_id="F1", ds_columns=COLUMNS))
    c = _go(dto)
    assert c["operation"] == "ADD" and c["filters"] == [] and c["queryId"] is None
    assert c["areFiltersConfigured"] is True
    assert c["inputMap"] == [{"id": 0, "left": "Sku", "right": fb_field(dto, "category")},
                             {"id": 1, "left": "Category", "right": "test"}]
    assert c["outputMap"] == [{"id": 0, "left": "success", "right": fb_field(dto, "count")}]


def test_a_write_has_only_the_success_output():
    with pytest.raises(UsageError, match="success"):
        fb.build(_write("add", inputs=[{"left": "Sku", "right": "category"}],
                        outputs=[{"left": "rows", "right": "products"}]), _ctx(form_id="F1"))


def test_add_takes_no_filters():
    with pytest.raises(UsageError, match="ADD takes no filters"):
        fb.build(_write("add", inputs=[{"left": "Sku", "right": "category"}],
                        filters=[{"column": "Sku", "op": "equals", "value": "x"}]), _ctx(form_id="F1"))


def test_update_without_a_filter_is_refused():
    with pytest.raises(UsageError, match="UPDATE needs `filters`"):
        fb.build(_write("update", inputs=[{"left": "Product", "right": "category"}]),
                 _ctx(form_id="F1"))


def test_update_of_a_key_column_is_refused_when_the_store_is_known():
    cfg = _write("update", inputs=[{"left": "Sku", "right": "category"}],
                 filters=[{"column": "Sku", "op": "equals", "field": "category"}])
    with pytest.raises(UsageError, match="primary key"):
        fb.build(cfg, _ctx(form_id="F1", ds_columns=COLUMNS))


def test_an_unknown_column_is_refused_when_the_store_is_known():
    with pytest.raises(UsageError, match="Prodcut"):
        fb.build(_write("add", inputs=[{"left": "Prodcut", "right": "category"}]),
                 _ctx(form_id="F1", ds_columns=COLUMNS))


def test_delete_without_a_filter_by_a_non_key_column_warns():
    warnings: list = []
    fb.build(_write("delete", inputs=[{"left": "Category", "right": "category"}]),
             _ctx(form_id="F1", ds_columns=COLUMNS, _build_warnings=warnings))
    assert any("every row whose" in w for w in warnings)
    warnings.clear()
    fb.build(_write("delete", inputs=[{"left": "Sku", "right": "category"}]),
             _ctx(form_id="F1", ds_columns=COLUMNS, _build_warnings=warnings))
    assert warnings == []


def test_the_stores_a_form_writes_are_read_before_the_build():
    class Client:
        env = None
        calls: list = []

        def get(self, path, *a, **k):
            self.calls.append(path)
            return {"id": STORE, "columns": [
                {"name": "Sku", "isPrimaryKey": True, "isSystemColumn": False},
                {"name": "Qty", "isPrimaryKey": False, "isSystemColumn": False},
                {"name": "CreatedOn", "isPrimaryKey": False, "isSystemColumn": True}]}
    client = Client()
    ctx = fb._prepare_ctx(client, _write("update", inputs=[], filters=[]))
    assert client.calls == [f"/api/DataStore/{STORE}"]
    assert ctx["ds_columns"][STORE] == {"names": ["Sku", "Qty"], "pk": ["Sku"]}


# -- row limits (form-runtime team, 2026-11-19: the backend does not limit a form's rows;
#    keep 200 for a table / dynamic row and 100 for a dropdown or radio group) ----------------

def _warnings_for(cfg):
    found: list = []
    fb.build(cfg, _ctx(form_id="F1", _build_warnings=found))
    return found


def test_a_query_without_limit_filling_a_dropdown_warns_with_100():
    ev = {"on": "load", "do": "datastore", "operation": "query", "query": "Product list",
          "outputs": [{"left": "rows", "right": "productpick"}]}
    found = _warnings_for(_config([ev], queries=[QUERY]))
    assert any("LIMIT 100" in w and "Product list" in w for w in found)


def test_a_query_with_limit_does_not_warn():
    limited = {**QUERY, "sql": QUERY["sql"] + " LIMIT 100"}
    ev = {"on": "load", "do": "datastore", "operation": "query", "query": "Product list",
          "outputs": [{"left": "rows", "right": "productpick"}]}
    assert not any("LIMIT" in w for w in _warnings_for(_config([ev], queries=[limited])))


def test_a_read_of_1000_rows_into_a_table_warns_with_200():
    found = _warnings_for(_config([_read()]))
    assert any("countPerPage" in w and "200" in w for w in found)
    small = _read(inputs=[{"left": "countPerPage", "value": "200"}])
    assert not any("countPerPage" in w for w in _warnings_for(_config([small])))


# -- form-edit gives elements new ids: the kept form events must follow them --------------

def test_kept_form_events_are_remapped_to_the_rebuilt_elements():
    """Seen on production: an onLoad READ kept by form-edit still pointed at the old table
    row and field ids, so after the edit it filled nothing, with no error."""
    cfg = _config([_read()])
    old = fb.build(cfg, _ctx(form_id="F1"))
    live_events = old["Data"]["events"]
    edit_cfg = {k: v for k, v in cfg.items() if k != "events"}
    cnt = itertools.count(500)
    new = fb.build(edit_cfg, {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}",
                              "form_id": "F1", "live_events": live_events,
                              "live_elements": old["Data"]["elements"]})
    out = new["Data"]["events"][0]["config"]["outputMap"]
    row = next(e for e in new["Data"]["elements"] if e["type"] == "dynamic-table-row")
    assert out[0]["right"] == _path(new, row, "sourceValue")
    assert out[2]["right"] == fb_field(new, "count")


def test_a_kept_event_filling_a_dropdown_keeps_its_source_type():
    ev = {"on": "load", "do": "datastore", "operation": "query", "query": "Product list",
          "outputs": [{"left": "rows", "right": "productpick"}]}
    cfg = _config([ev], queries=[QUERY])
    old = fb.build(cfg, _ctx(form_id="F1"))
    edit_cfg = {k: v for k, v in cfg.items() if k != "events"}
    cnt = itertools.count(700)
    new = fb.build(edit_cfg, {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}",
                              "form_id": "F1", "live_events": old["Data"]["events"],
                              "live_elements": old["Data"]["elements"]})
    pick = _el(new, "productpick")
    assert new["Data"]["events"][0]["config"]["outputMap"][0]["right"] == _path(new, pick, "sourceValue")
    assert _cfg(pick, "sourceType")["value"] == "JSON"
