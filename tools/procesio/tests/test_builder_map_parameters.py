"""A map-parameters property (Word Mail Merge's `Word Mail Parameters`) takes `{"map": {...}}`.

Each entry becomes a runtime row `{id, source:{value, variable}, destination:{value: name}}`:
a bare value is a literal, `{var, path}` binds a variable or one of its attributes, with the
same `<%N%>` index sequence as the action's other parameters. Without this the only way to fill
merge fields was a raw `{"value": [rows]}` of literals.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from tools.procesio.dto.process import builder

TEMPLATE = {"name": "Word Mail Merge", "configuration": [{"settings": [
    {"id": "p-file", "label": "Word File", "type": "file"},
    {"id": "p-map", "label": "Word Mail Parameters", "type": "map-parameters"},
]}]}
QUOTE_VAR = "33333333-3333-3333-3333-333333333333"


def _ctx():
    return {"var_ids": {"quote": QUOTE_VAR, "letter": "44444444-4444-4444-4444-444444444444"}}


def test_map_rows_bind_literals_and_variables(monkeypatch):
    monkeypatch.setattr(builder, "_attr_chain", lambda path, model, ctx: (
        {"attributeId": f"attr-{path[0]}", "nextAttribute": None} if path else None))
    monkeypatch.setattr(builder, "_model_of", lambda ctx, name: None)
    counter = [0]
    params = builder._action_parameters(TEMPLATE, {
        "Word File": {"var": "letter"},
        "Word Mail Parameters": {"map": {"customer": {"var": "quote", "path": ["customer"]},
                                         "city": "Cluj"}},
    }, _ctx(), counter)
    file_param, map_param = params
    assert file_param["Value"] == "<%0%>"
    assert map_param["TabPropertyId"] == "p-map" and map_param["Variable"] == []
    first, second = map_param["Value"]
    assert first["destination"] == {"value": "customer", "variable": []}
    assert first["source"]["value"] == "<%1%>"
    assert first["source"]["variable"][0]["variableId"] == QUOTE_VAR
    assert first["source"]["variable"][0]["attribute"]["attributeId"] == "attr-customer"
    assert second == {"id": 1, "source": {"value": "Cluj", "variable": []},
                      "destination": {"value": "city", "variable": []}}


def test_schema_accepts_a_map_binding():
    schema = json.loads((Path(builder.__file__).parent / "config.schema.json").read_text("utf-8"))
    config = {"title": "t", "actions": [{"id": "mm", "action": "Word Mail Merge", "params": {
        "Word Mail Parameters": {"map": {"customer": {"var": "quote", "path": ["customer"]},
                                         "total": 10}}}}]}
    jsonschema.validate(config, schema)
