"""Locks the Data Store NODE authoring shapes (dsMap / dsWhere) the builder emits.

These runtime shapes were reverse-engineered from a live PROCESIO export and verified
end-to-end (SELECT+Where filters, INSERT+Set Values writes) against a real Data Store.
The three shape facts below are what make the node RUN rather than just validate:
  - Set Values  (a103) row = {id, column:<name>, source:{value,variable}}         (column by NAME)
  - Where       (a106) value = [{id:<GUID>, condition:[{...operator/left/right...}]}]  (element id is a GUID,
                param-level Variable is EMPTY, operator is a decisional token like EQUALS)
A regression on any of these reproduces a silent runtime failure (e.g. an int element id ->
.NET 'Nullable object must have a value.'), so they are pinned here.
"""
from __future__ import annotations

import itertools
import re

from tools.procesio.dto.process import builder as pb

_GUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_DS = "667379d7-f146-4a04-9b9f-66682858e162"


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}


def _ds_node(dto):
    return [a for a in dto["Actions"] if a.get("ActionTemplateName") == "Data Store"]


def _param(node, tail):
    return next(p for p in node["Parameters"] if p["TabPropertyId"].endswith(tail))


def _cd_setting(node, stype):
    def walk(settings):
        for s in settings or []:
            if s.get("type") == stype:
                return s
            if isinstance(s.get("value"), list):
                r = walk(s["value"])
                if r:
                    return r
    for tab in node["CustomData"]["configuration"]:
        r = walk(tab.get("settings", []))
        if r:
            return r


def test_ds_where_runtime_shape():
    cfg = {"title": "t",
           "variables": [{"name": "keyIn", "type": "string", "direction": "input"},
                         {"name": "rows", "type": "json", "direction": "output"}],
           "actions": [{"id": "sel", "action": "Data Store",
                        "params": {"Select Data Store": _DS, "Operation": "SelectRows",
                                   "Result Rows": {"var": "rows"}},
                        "dsWhere": [{"column": "rowKey", "op": "equals", "value": {"var": "keyIn"}}]}]}
    node = _ds_node(pb.build(cfg, _ctx()))[0]
    p = _param(node, "a106")
    assert p["Variable"] == []                          # variables live INLINE, not at param level
    val = p["Value"]
    assert isinstance(val, list) and len(val) == 1      # IList<InputDataStoreDecisional>
    el = val[0]
    assert _GUID.match(str(el["id"]))                   # element id is a GUID (int -> Nullable error)
    c = el["condition"][0]
    assert c["operator"] == "EQUALS"                    # decisional token, not a QueryOperators int
    assert c["leftOperator"] == {"value": "rowKey", "variable": []}   # column on the left, by name
    rop = c["rightOperator"]
    assert re.match(r"^<%\d+%>$", rop["value"])                      # placeholder value
    assert rop["variable"][0]["variableId"]                          # bound var inline on the right
    assert rop["value"] == f"<%{rop['variable'][0]['id']}%>"         # placeholder index matches inline id
    assert c["auxOperator"] is None
    # designer card mirrors it and satisfies the FE Where validator
    cd = _cd_setting(node, "data-store-decisional")["value"]
    assert cd[0]["name"] == "Where" and cd[0]["condition"][0]["leftOperator"]["value"] == "rowKey"


def test_ds_setvalues_runtime_shape():
    cfg = {"title": "t",
           "variables": [{"name": "k", "type": "string", "direction": "input"},
                         {"name": "rate", "type": "double", "direction": "input"}],
           "actions": [{"id": "ins", "action": "Data Store",
                        "params": {"Select Data Store": _DS, "Operation": "InsertRows"},
                        "dsMap": {"rowKey": {"var": "k"}, "rateRON": {"var": "rate"},
                                  "sourceUrl": "https://curs.bnr.ro"}}]}
    node = _ds_node(pb.build(cfg, _ctx()))[0]
    rows = _param(node, "a103")["Value"]
    assert [r["column"] for r in rows] == ["rowKey", "rateRON", "sourceUrl"]   # target by NAME
    assert rows[0]["source"]["variable"][0]["variableId"]                      # var binding inline
    assert rows[2]["source"] == {"value": "https://curs.bnr.ro", "variable": []}  # bare = literal
    # designer rows are {id, left, right} (NOT the document-mapper {process, document})
    cd = _cd_setting(node, "data-store-mapper")["value"]
    assert cd[0]["left"] == "rowKey" and "document" not in cd[0]
