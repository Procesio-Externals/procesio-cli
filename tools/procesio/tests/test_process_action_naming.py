"""Build-time auto-naming of process actions + Decisional/AI Decisional branches.

Two behaviours are locked here:
  * an un-named action is labelled by what it DOES (derived from literal config),
    never left as the generic template label when we can do better;
  * a non-default Decisional case is labelled by its condition instead of "Case N".
Both are cosmetic (wiring is by id) and both re-evaluate on every build/edit, so an
edited process stays legible. An explicit name always wins; a param bound to a
variable is unknowable at build time and falls back to the template label.
"""
from __future__ import annotations

import itertools

from tools.procesio.dto.process import builder as pb
from tools.procesio.dto.process import naming


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}


def _names(dto):
    return [a["ActionName"] for a in dto["Actions"]]


def _template(dto, template_name):
    return next(a for a in dto["Actions"] if a["ActionTemplateName"] == template_name)


def _cases_config(node, ctype):
    return next(s for tab in node["CustomData"]["configuration"]
               for s in tab["settings"] if s.get("type") == ctype)["value"]


# -- naming module (pure) -----------------------------------------------------

def test_derive_action_name_enriches_high_value_templates():
    assert naming.derive_action_name(
        {"params": {"Verb": "get", "Endpoint": "https://api.x.com/v1/users?q=1"}},
        "Call API") == "GET /v1/users"
    assert naming.derive_action_name(
        {"params": {"For Each Item": {"var": "items"}}}, "For Each") == "For each items"
    assert naming.derive_action_name(
        {"params": {"Code": "// resolve the period\nreturn 1;"}}, "Node") == "resolve the period"
    assert naming.derive_action_name(
        {"params": {"Query": "SELECT * FROM clients WHERE id=@id"}},
        "Execute Query") == "SELECT clients"
    assert naming.derive_action_name(
        {"params": {"File Name": "invoice.pdf"}}, "Generate Document") == "Generate invoice.pdf"


def test_derive_action_name_returns_none_when_it_cannot_beat_the_template():
    # a variable-bound param is unknowable at build time
    assert naming.derive_action_name({"params": {"Endpoint": {"var": "u"}}}, "Call API") is None
    # a Node with no leading comment has nothing to summarise
    assert naming.derive_action_name({"params": {"Code": "return 1;"}}, "Node") is None
    # a template with no enricher
    assert naming.derive_action_name({"params": {}}, "Generate GUID") is None


def test_derive_branch_name_rule_based_and_ai():
    assert naming.derive_branch_name(
        {"when": [{"left": {"var": "amount"}, "op": "GREATER_THAN", "right": 1000}]},
        is_ai=False) == "amount > 1000"
    assert naming.derive_branch_name(
        {"when": [{"left": {"var": "cod"}, "op": "IS_NOT_EMPTY"}]}, is_ai=False) == "cod present"
    assert naming.derive_branch_name(
        {"when": [{"left": {"var": "a"}, "op": "EQUALS", "right": 1},
                  {"left": {"var": "b"}, "op": "IS_TRUE", "logic": "and"}]},
        is_ai=False) == "a = 1 and b"
    assert naming.derive_branch_name(
        {"condition": "the client is a new customer"}, is_ai=True) == "the client is a new customer"


def test_disambiguate_only_suffixes_collisions():
    out = naming.disambiguate([("a", "GET /x", True), ("b", "GET /x", True),
                               ("c", "Send Mail", False), ("d", "Send Mail", False)])
    assert out == {"a": "GET /x", "b": "GET /x 2", "c": "Send Mail", "d": "Send Mail"}


# -- build integration --------------------------------------------------------

def test_unnamed_actions_are_auto_named_and_collisions_disambiguated():
    cfg = {"title": "t", "variables": [{"name": "items", "type": "json", "direction": "input"}],
           "actions": [
               {"id": "c1", "action": "Call API",
                "params": {"Verb": "GET", "Endpoint": "https://api.example.com/v1/users"}},
               {"id": "c2", "action": "Call API",
                "params": {"Verb": "GET", "Endpoint": "https://api.example.com/v1/users"}},
               {"id": "loop", "action": "For Each", "params": {"For Each Item": {"var": "items"}}},
           ]}
    names = _names(pb.build(cfg, _ctx()))
    assert "GET /v1/users" in names and "GET /v1/users 2" in names   # collision disambiguated
    assert "For each items" in names


def test_explicit_name_wins_over_derivation():
    cfg = {"title": "t", "actions": [
        {"id": "c", "action": "Call API", "name": "Fetch users",
         "params": {"Verb": "GET", "Endpoint": "https://api.example.com/v1/users"}}]}
    assert "Fetch users" in _names(pb.build(cfg, _ctx()))


def test_template_fallback_names_are_shared_not_disambiguated():
    """Two un-named Stops (no enricher) both stay 'Stop' — only ENRICHED names are made
    unique, so template-label duplicates keep behaving exactly as before auto-naming."""
    cfg = {"title": "t", "actions": [
        {"id": "g", "action": "Generate GUID"},
        {"id": "s1", "action": "Stop"}, {"id": "s2", "action": "Stop"}],
        "edges": [["start", "g"], ["g", "s1"]]}
    names = _names(pb.build(cfg, _ctx()))
    assert names.count("Stop") == 2 and "Stop 2" not in names


def test_regular_decisional_branch_named_from_condition_default_untouched():
    cfg = {"title": "t",
           "variables": [{"name": "amount", "type": "integer", "direction": "input"},
                         {"name": "cod", "type": "string", "direction": "input"}],
           "actions": [
               {"id": "d", "action": "Decisional", "branches": [
                   {"to": "a", "when": [{"left": {"var": "amount"}, "op": "GREATER_THAN", "right": 1000}]},
                   {"name": "has code", "to": "b", "when": [{"left": {"var": "cod"}, "op": "IS_NOT_EMPTY"}]},
                   {"to": "j", "default": True}]},
               {"id": "a", "action": "Generate GUID"}, {"id": "b", "action": "Generate GUID"},
               {"id": "j", "action": "Join"}],
           "edges": [["start", "d"], ["a", "j"], ["b", "j"], ["j", "stop"]]}
    dto = pb.build(cfg, _ctx())
    dec = _template(dto, "Decisional")
    branch_names = [c["name"] for c in _cases_config(dec, "decisional-case")]
    assert branch_names == ["amount > 1000", "has code"]   # derived, then explicit-wins
    # the default is a port, not a case, so it never gets a case label
    assert any(p.get("Data", {}).get("isDefault") == "default" for p in dec["Ports"])


def test_ai_decisional_branch_named_from_condition():
    cfg = {"title": "t",
           "variables": [{"name": "animal", "type": "string", "direction": "input"}],
           "actions": [
               {"id": "ai", "action": "AI Decisional",
                "params": {"User Prompt": {"template": "which? <%0%>", "vars": ["animal"]}},
                "branches": [
                    {"name": "bear", "to": "a", "condition": "Is it a bear?"},
                    {"to": "b", "condition": "Is it a fish?"},
                    {"to": "d", "default": True}]},
               {"id": "a", "action": "Generate GUID"}, {"id": "b", "action": "Generate GUID"},
               {"id": "d", "action": "Generate GUID"}],
           "edges": [["start", "ai"], ["a", "stop"], ["b", "stop"], ["d", "stop"]]}
    dto = pb.build(cfg, _ctx())
    ai = _template(dto, "AI Decisional")
    names = [c["name"] for c in _cases_config(ai, "ai-decisional-case")]
    assert names == ["bear", "Is it a fish?"]              # explicit wins, else condition
