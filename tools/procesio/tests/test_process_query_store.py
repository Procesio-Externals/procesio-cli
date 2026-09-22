"""Locks the Query Store NODE authoring shapes the builder emits from a `queryStore` spec.

Reverse-engineered from a live PROCESIO export and verified end-to-end in a real workspace
(SELECT/JOIN/GROUP BY, INSERT/UPDATE/DELETE/REPLACE, list params, error branch). The shape
facts that make the node RUN rather than merely validate:
  - b102 Query: `Value` is SQL with `<%N%>`; each `<%N%>` is a CHIP in `Variable[]` typed
    dataStoreTable ({dataStoreId}) or dataStoreColumn ({dataStoreId, columnId}) - NOT a
    process variable; `@param` stays literal in the SQL.
  - b103 Parameters: rows {id, source:{value,variable}, destination:{value:<paramName>}}.
  - b105/b106 outputs bind like any {var}. One <%N%> id sequence across the whole node.
  - Designer mirror: b102 -> `ds.<dataStoreId>[.<columnId>]`, b103 -> {id,destination,source}.
"""
from __future__ import annotations

import itertools
import re

import pytest

from tools.procesio.dto.process import builder as pb
from tools.procesio.flowmodel import fevalidation as fv

_STORE = "11111111-1111-1111-1111-111111111111"
_C_NAME = "22222222-2222-2222-2222-222222222222"
_C_TIER = "33333333-3333-3333-3333-333333333333"
_C_CODE = "44444444-4444-4444-4444-444444444444"
_ORD = "55555555-5555-5555-5555-555555555555"
_O_CUST = "66666666-6666-6666-6666-666666666666"
_O_AMT = "77777777-7777-7777-7777-777777777777"

_DSM = {
    "qs_customers": {"id": _STORE, "columns": {"name": _C_NAME, "tier": _C_TIER, "customercode": _C_CODE}},
    "qs_orders": {"id": _ORD, "columns": {"customercode": _O_CUST, "amount": _O_AMT}},
}


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}",
            "datastore_meta": _DSM}


def _qs_node(dto):
    return next(a for a in dto["Actions"] if a.get("ActionTemplateName") == "Query Store")


def _param(node, tail):
    return next(p for p in node["Parameters"] if p["TabPropertyId"].endswith(tail))


def _cd(node, tail):
    def walk(settings):
        for s in settings or []:
            if str(s.get("id", "")).endswith(tail):
                return s
            if isinstance(s.get("value"), list):
                r = walk(s["value"])
                if r:
                    return r
    for tab in node["CustomData"]["configuration"]:
        r = walk(tab.get("settings", []))
        if r:
            return r


_ROWS = {"name": "rows", "type": "json", "isList": True, "direction": "output"}
_CNT = {"name": "count", "type": "integer", "direction": "output"}


def _select_cfg():
    return {"title": "t",
            "variables": [{"name": "maxTier", "type": "integer", "direction": "input"}, _ROWS, _CNT],
            "actions": [{"id": "q", "action": "Query Store", "queryStore": {
                "sql": "select {{col:QS_Customers.Name}} from {{ds:QS_Customers}} "
                       "where {{col:QS_Customers.Tier}} <= @maxTier",
                "params": {"maxTier": {"var": "maxTier"}},
                "resultRows": "rows", "totalCount": "count"}}]}


def test_query_chips_and_placeholders():
    node = _qs_node(pb.build(_select_cfg(), _ctx()))
    q = _param(node, "b102")
    assert q["Value"] == "select <%0%> from <%1%> where <%2%> <= @maxTier"  # @param stays literal
    chips = q["Variable"]
    assert chips[0] == {"id": 0, "type": "dataStoreColumn", "variableId": None,
                        "dataStoreId": _STORE, "columnId": _C_NAME, "attribute": None}
    assert chips[1] == {"id": 1, "type": "dataStoreTable", "variableId": None,
                        "dataStoreId": _STORE, "attribute": None}
    assert chips[2]["columnId"] == _C_TIER and chips[2]["type"] == "dataStoreColumn"


def test_parameters_map_and_outputs():
    node = _qs_node(pb.build(_select_cfg(), _ctx()))
    p = _param(node, "b103")
    assert p["Variable"] == []                                   # sources live INLINE
    row = p["Value"][0]
    assert row["destination"] == {"value": "maxTier", "variable": []}   # @param name, no '@'
    assert re.match(r"^<%\d+%>$", row["source"]["value"])
    assert row["source"]["variable"][0]["variableId"]            # bound to the process variable
    # outputs bind like any {var}: Value=<%N%>, Variable=[{variableId}]
    for tail in ("b105", "b106"):
        op = _param(node, tail)
        assert re.match(r"^<%\d+%>$", op["Value"]) and op["Variable"][0]["variableId"]
    assert _param(node, "b104")["Value"] == "1800"              # Time Out default


def test_one_id_sequence_across_node():
    node = _qs_node(pb.build(_select_cfg(), _ctx()))
    ids = []
    for p in node["Parameters"]:
        for v in p.get("Variable") or []:
            ids.append(v["id"])
        val = p.get("Value")
        if isinstance(val, list):
            for row in val:
                ids += [v["id"] for v in (row.get("source", {}).get("variable") or [])]
    assert ids == sorted(set(ids)) and ids == list(range(len(ids)))  # contiguous, unique


def test_designer_mirror():
    node = _qs_node(pb.build(_select_cfg(), _ctx()))
    q = _cd(node, "b102")["value"]                              # code-editor -> ds.<id>[.<col>]
    assert q == f"select ds.{_STORE}.{_C_NAME} from ds.{_STORE} where ds.{_STORE}.{_C_TIER} <= @maxTier"
    prow = _cd(node, "b103")["value"][0]                        # map-parameters designer row
    assert prow["destination"] == "maxTier" and prow["source"]                       # var id
    assert _cd(node, "b105")["value"] and _cd(node, "b106")["value"]                  # output var ids


def test_join_two_data_stores():
    cfg = {"title": "t", "variables": [_ROWS, _CNT],
           "actions": [{"id": "q", "action": "Query Store", "queryStore": {
               "sql": "SELECT c.{{col:QS_Customers.Name}} AS Customer, SUM(o.{{col:QS_Orders.Amount}}) AS Rev "
                      "FROM {{ds:QS_Customers}} AS c JOIN {{ds:QS_Orders}} AS o "
                      "ON o.{{col:QS_Orders.CustomerCode}} = c.{{col:QS_Customers.CustomerCode}} "
                      "GROUP BY c.{{col:QS_Customers.Name}}",
               "resultRows": "rows", "totalCount": "count"}}]}
    node = _qs_node(pb.build(cfg, _ctx()))
    chips = _param(node, "b102")["Variable"]
    stores = {c["dataStoreId"] for c in chips}
    assert stores == {_STORE, _ORD}                            # both data stores chipped
    assert {c["columnId"] for c in chips if c["type"] == "dataStoreColumn"} == {
        _C_NAME, _O_AMT, _O_CUST, _C_CODE}


def test_guid_passthrough_without_meta():
    cfg = {"title": "t", "variables": [_ROWS],
           "actions": [{"id": "q", "action": "Query Store", "queryStore": {
               "sql": f"select {{{{col:{_STORE}.{_C_NAME}}}}} from {{{{ds:{_STORE}}}}}",
               "resultRows": "rows"}}]}
    ctx = {"new_id": lambda: "00000000-0000-0000-0000-000000000001"}   # no datastore_meta
    node = _qs_node(pb.build(cfg, ctx))
    chips = _param(node, "b102")["Variable"]
    assert chips[0]["columnId"] == _C_NAME and chips[1]["dataStoreId"] == _STORE


def test_unknown_store_name_raises():
    cfg = {"title": "t", "variables": [_ROWS],
           "actions": [{"id": "q", "action": "Query Store", "queryStore": {
               "sql": "select {{col:Nope.Name}} from {{ds:Nope}}", "resultRows": "rows"}}]}
    with pytest.raises(Exception) as e:
        pb.build(cfg, _ctx())
    assert "unknown Data Store" in str(e.value)


def test_fe_validation_clean():
    assert fv.validate_flow(pb.build(_select_cfg(), _ctx())) == []
