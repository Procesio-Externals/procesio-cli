"""Targeted capability discovery: one action, keyword search, and the size degrade.

Why this exists: dumping a big tool's full schema (procesio: ~369 KB / 379 actions)
is not a large answer, it is NO answer - the driver truncates it to a single-line
file that read/grep/bash cannot open, and the turn is lost. Measured against real
transcripts, 27% of all tool calls in an autonomous run were the model guessing
argument names. These tests pin the four doors that replace the guessing.

The registry is faked so the assertions are about behaviour, not about whichever
tools happen to be installed; one test runs against the real manifests to prove
the threshold actually trips on the tool that motivated it.
"""
from __future__ import annotations

import json

import bridge
import pytest
import registry
import server


def _tool(name, actions, description="a tool"):
    return {"name": name, "description": description, "ready": True,
            "missing_secrets": [], "actions": actions, "args": [],
            "routing": {"primary_action": "", "example": ""}}


def _action(name, description="", args=()):
    return {"name": name, "description": description,
            "args": [{"name": a, "type": "string", "required": r,
                      "description": ""} for a, r in args]}


FAKE_TOOLS = [
    _tool("bigtool", [
        _action("datastore-create", "Create a Data Store.",
                [("payload", True), ("workspace-id", False)]),
        _action("datastore-update", "Update a Data Store's columns.",
                [("payload", True)]),
        _action("datastore-get-rows", "Read rows from a Data Store.",
                [("id", True)]),
        _action("export", "Export a process as a .procesio bundle.",
                [("process-id", True), ("out", False)]),
        _action("list-processes", "List processes."),
    ]),
    _tool("smalltool", [_action("ping", "Ping.", [("host", True)])]),
]
FAKE_AGENTS = [
    _tool("bigagent", [_action("guidance", "Serve the playbook.", [("topic", False)])]),
]


@pytest.fixture(autouse=True)
def fake_registry(monkeypatch):
    monkeypatch.setattr(bridge, "_scan_registry",
                        lambda: (FAKE_TOOLS, FAKE_AGENTS, []))


# --- door 1: one action's schema -----------------------------------------

def test_name_plus_action_returns_only_that_action():
    out = bridge.capabilities(name="bigtool", action="datastore-create")
    cap = out["capability"]
    assert cap["name"] == "bigtool"
    assert cap["action"]["name"] == "datastore-create"
    assert [a["name"] for a in cap["action"]["args"]] == ["payload", "workspace-id"]
    assert [a["name"] for a in cap["action"]["args"] if a["required"]] == ["payload"]
    # No sibling actions leak in - that is the whole point.
    assert "export" not in json.dumps(out)


def test_one_action_payload_stays_small():
    out = bridge.capabilities(name="bigtool", action="datastore-create")
    assert len(json.dumps(out)) < 2000


def test_one_action_carries_the_literal_call_shape():
    cap = bridge.capabilities(name="bigtool", action="export")["capability"]
    assert cap["call"]["aat_run_tool"]["tool"] == "bigtool"
    assert cap["call"]["aat_run_tool"]["action"] == "export"
    assert "hyphens" in cap["hint"]


def test_agent_action_names_the_agent_runner():
    cap = bridge.capabilities(name="bigagent", action="guidance")["capability"]
    assert cap["kind"] == "agent"
    assert "aat_run_agent" in cap["call"]


def test_unknown_action_suggests_close_names():
    out = bridge.capabilities(name="bigtool", action="datastore-crate")
    assert out["unknown_action"] == "datastore-crate"
    assert "datastore-create" in out["did_you_mean"]
    assert out["action_count"] == 5


def test_suggestion_survives_word_order_and_plurals():
    """The mistake a model actually makes: right words, wrong order (`credential-list`
    for `list-credentials`). Edit distance alone scores those as far apart."""
    names = ["list-credentials", "credential-test", "credential-get", "run-process"]
    assert bridge._suggest("credential-list", names)[0] == "list-credentials"
    assert bridge._suggest("instances-list", ["list-instances"])[0] == "list-instances"


def test_suggestion_ignores_unrelated_names():
    assert bridge._suggest("datastore-create", ["send-email", "run-process"]) == []


def test_unknown_capability_still_raises():
    with pytest.raises(KeyError):
        bridge.capabilities(name="ghost")


# --- door 2: keyword search ----------------------------------------------

def test_search_finds_actions_across_capabilities():
    out = bridge.capabilities(search="datastore")
    names = {m["action"] for m in out["matches"]}
    assert names == {"datastore-create", "datastore-update", "datastore-get-rows"}
    assert all("args" not in m for m in out["matches"])  # compact, not schemas


def test_search_is_and_not_or():
    out = bridge.capabilities(search="datastore rows")
    assert [m["action"] for m in out["matches"]] == ["datastore-get-rows"]


def test_search_matches_description_too():
    out = bridge.capabilities(search="bundle")
    assert [m["action"] for m in out["matches"]] == ["export"]


def test_search_ranks_name_matches_above_description_matches():
    out = bridge.capabilities(search="export")
    assert out["matches"][0]["action"] == "export"


def test_search_can_be_scoped_to_one_capability():
    assert bridge.capabilities(search="guidance", name="bigtool")["count"] == 0
    assert bridge.capabilities(search="guidance", name="bigagent")["count"] == 1


def test_search_can_be_scoped_by_kind():
    out = bridge.capabilities(search="guidance", kind="tool")
    assert out["count"] == 0


def test_search_reports_total_when_capped(monkeypatch):
    out = bridge._search_actions("datastore", limit=2)
    assert len(out["matches"]) == 2
    assert out["total_matches"] == 3


def test_empty_search_is_a_readable_error():
    with pytest.raises(KeyError):
        bridge.capabilities(search="   ")


# --- door 2b: a strict-AND miss relaxes instead of dead-ending -------------
#
# A caller's words come from the TARGET system's vocabulary, not ours, so one wrong
# word must not hide the whole family. Live cost of the empty answer: a search for
# "form create template" returned 0 because no description says "template"; the run
# abandoned the curated create action, fell back to the raw HTTP endpoint, tripped
# the irreversibility gate and blocked on step 0 having built nothing.

def test_one_unmatched_word_still_returns_the_family():
    out = bridge.capabilities(search="datastore create template")
    assert out["matches"], "a strict miss must not come back empty"
    assert out["matches"][0]["action"] == "datastore-create"


def test_relaxed_result_says_which_word_it_ignored():
    out = bridge.capabilities(search="datastore create template")
    assert out["relaxed"] is True
    assert out["dropped_terms"] == ["template"]
    assert set(out["matched_terms"]) == {"datastore", "create"}
    assert "template" in out["hint"]


def test_a_result_that_matches_every_word_is_not_marked_relaxed():
    out = bridge.capabilities(search="datastore rows")
    assert "relaxed" not in out
    assert "dropped_terms" not in out


def test_dropped_terms_are_measured_against_the_top_match():
    """Different matches cover different words, so a set-wide calculation reports
    'relaxed, dropped nothing' — a contradiction that says nothing about the action
    the caller is about to read."""
    out = bridge.capabilities(search="datastore export bundle")
    top = out["matches"][0]
    hay = f"{top['name']}.{top['action']} {top['description']}".lower()
    for term in out["dropped_terms"]:
        assert term not in hay
    for term in out["matched_terms"]:
        assert term in hay


def test_scoping_word_does_not_make_every_action_a_match():
    """Scoped by name, a token equal to the capability is free for all of its actions.
    Left in the scoring, a query whose real words all miss would still score 1
    everywhere and hand back the whole catalog — worse than the empty answer this
    relaxation exists to fix."""
    out = bridge.capabilities(name="bigtool", search="bigtool zzzz qqqq")
    assert out["count"] == 0
    assert out["total_matches"] == 0
    assert "conclusive" in out["hint"].lower()


def test_nothing_matches_at_all_is_conclusive_and_says_so():
    out = bridge.capabilities(search="zzzz qqqq wwww")
    assert out["matches"] == []
    assert "list-actions-catalog" in out["hint"]     # points at the other catalog


def test_a_relaxed_search_does_not_lead_with_a_destructive_action(monkeypatch):
    """'generate form' and 'delete form' match the same one word. Offering the
    deletion first is how a near-miss becomes an incident."""
    tools = [_tool("t", [_action("form-delete", "Delete a form."),
                         _action("form-create", "Create a form.")])]
    monkeypatch.setattr(bridge, "_scan_registry", lambda: (tools, [], []))
    out = bridge.capabilities(search="form generate")
    assert out["matches"][0]["action"] == "form-create"
    # …but a caller who DID ask to delete still gets it.
    out = bridge.capabilities(search="form delete")
    assert out["matches"][0]["action"] == "form-delete"


def test_a_relaxation_surviving_only_on_the_capability_name_is_conclusive():
    """Unscoped, the tool's name cannot be stripped up front (naming the tool is how you
    narrow there), so a query whose substantive words all miss stays alive on that one
    token and answers with the tool's whole catalog. Live: 405 rows, none of them about
    what was asked."""
    out = bridge.capabilities(search="bigtool nosuchthing")
    assert out["matches"] == []
    assert out["total_matches"] == 0
    assert out["dropped_terms"] == ["nosuchthing"]
    assert "conclusive" in out["hint"].lower()
    assert "list-actions-catalog" in out["hint"]


def test_a_relaxation_that_explains_nothing_says_it_is_too_vague(monkeypatch):
    tools = [_tool("t", [_action(f"form-op-{i}", "About a form.") for i in range(70)])]
    monkeypatch.setattr(bridge, "_scan_registry", lambda: (tools, [], []))
    out = bridge.capabilities(search="form nosuchword")
    assert out["relaxed"] is True
    assert "too vague" in out["hint"].lower()


def test_action_without_name_falls_back_to_search():
    out = bridge.capabilities(action="datastore-create")
    assert out["matches"][0]["action"] == "datastore-create"
    assert out["matches"][0]["name"] == "bigtool"


# --- door 3: the size degrade --------------------------------------------

def test_full_schema_returned_when_under_the_limit(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", "100000")
    cap = bridge.capabilities(name="bigtool")["capability"]
    assert "truncated" not in cap
    assert len(cap["actions"]) == 5
    assert isinstance(cap["actions"][0], dict)  # full entries, with args


def test_oversized_schema_degrades_to_the_action_index(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", "200")
    cap = bridge.capabilities(name="bigtool")["capability"]
    assert cap["truncated"] is True
    assert cap["action_count"] == 5
    assert cap["actions"] == ["datastore-create", "datastore-update",
                              "datastore-get-rows", "export", "list-processes"]
    assert "action='<one of actions>'" in cap["hint"]
    assert "grep" in cap["hint"]


def test_degrade_names_the_sizes_so_the_reason_is_legible(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", "200")
    cap = bridge.capabilities(name="bigtool")["capability"]
    assert "200-byte limit" in cap["reason"]


def test_degrade_drops_the_index_when_even_that_is_too_big(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", "10")
    cap = bridge.capabilities(name="bigtool")["capability"]
    assert "actions" not in cap
    assert "search=" in cap["hint"]


def test_small_tool_is_never_degraded(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", str(bridge._DEFAULT_MAX_BYTES))
    cap = bridge.capabilities(name="smalltool")["capability"]
    assert "truncated" not in cap
    assert cap["actions"][0]["args"][0]["name"] == "host"


def test_limit_zero_disables_the_degrade(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", "0")
    assert "truncated" not in bridge.capabilities(name="bigtool")["capability"]


def test_bad_limit_env_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("AAT_CAPABILITIES_MAX_BYTES", "not-a-number")
    assert bridge._max_bytes() == bridge._DEFAULT_MAX_BYTES


def test_compact_list_is_unchanged_by_any_of_this():
    out = bridge.capabilities()
    assert out["count"] == 3
    assert {c["name"] for c in out["capabilities"]} == {"bigtool", "smalltool", "bigagent"}


# --- door 0: usage errors answer themselves -------------------------------

def test_action_help_lists_valid_args():
    help_ = bridge.action_help("bigtool", "datastore-create")
    assert [a["name"] for a in help_["valid_args"]] == ["payload", "workspace-id"]
    assert help_["valid_args"][0]["required"] is True


def test_action_help_suggests_names_for_an_invented_action():
    help_ = bridge.action_help("bigtool", "datastore-crate")
    assert help_["unknown_action"] == "datastore-crate"
    assert "datastore-create" in help_["did_you_mean"]


def test_action_help_is_none_for_an_unknown_capability():
    assert bridge.action_help("ghost", "whatever") is None


def _run_call(tool, action, error_message):
    """Drive server._run with a tool that fails with `error_message`."""
    def fake(target, act, args):
        return {"ok": False, "error": {"code": "invalid_argument",
                                       "message": error_message}}
    return fake


def test_usage_error_is_enriched_with_the_valid_args(monkeypatch):
    monkeypatch.setattr(server.bridge, "run_tool",
                        _run_call("bigtool", "datastore-create",
                                  "unrecognized arguments: --workspace_id x"))
    payload, is_error = server._run(
        "tool", {"tool": "bigtool", "action": "datastore-create",
                 "args": {"workspace_id": "x"}}, confirmed=False)
    assert is_error is True
    assert [a["name"] for a in payload["schema"]["valid_args"]] == ["payload", "workspace-id"]


def test_unknown_action_error_is_enriched_with_did_you_mean(monkeypatch):
    monkeypatch.setattr(server.bridge, "run_tool",
                        _run_call("bigtool", "datastore-crate",
                                  "unknown action: datastore-crate. Known: a, b, c"))
    payload, _ = server._run("tool", {"tool": "bigtool", "action": "datastore-crate"},
                             confirmed=False)
    assert "datastore-create" in payload["schema"]["did_you_mean"]


def test_missing_required_arg_error_is_enriched(monkeypatch):
    monkeypatch.setattr(server.bridge, "run_tool",
                        _run_call("bigtool", "datastore-create",
                                  "the following arguments are required: --payload"))
    payload, _ = server._run("tool", {"tool": "bigtool", "action": "datastore-create"},
                             confirmed=False)
    assert payload["schema"]["action"] == "datastore-create"


def test_remote_api_error_is_not_enriched(monkeypatch):
    """A 403 from the remote system is real feedback, not a naming problem - adding
    a schema there would just be noise."""
    monkeypatch.setattr(server.bridge, "run_tool",
                        _run_call("bigtool", "export", "HTTP 500"))
    payload, _ = server._run("tool", {"tool": "bigtool", "action": "export"},
                             confirmed=False)
    assert "schema" not in payload
    assert "hint" in payload


def test_enrichment_never_masks_the_original_error(monkeypatch):
    monkeypatch.setattr(server.bridge, "action_help",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(server.bridge, "run_tool",
                        _run_call("bigtool", "export", "unknown action: nope"))
    payload, is_error = server._run("tool", {"tool": "bigtool", "action": "nope"},
                                    confirmed=False)
    assert is_error is True
    assert payload["error"]["message"] == "unknown action: nope"


def test_hint_points_at_the_narrow_doors(monkeypatch):
    monkeypatch.setattr(server.bridge, "run_tool",
                        _run_call("bigtool", "export", "HTTP 500"))
    payload, _ = server._run("tool", {"tool": "bigtool", "action": "export"},
                             confirmed=False)
    assert "action='export'" in payload["hint"]
    assert "search=" in payload["hint"]


# --- the MCP surface ------------------------------------------------------

def test_capabilities_schema_advertises_action_and_search():
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    caps = next(t for t in resp["result"]["tools"] if t["name"] == "capabilities")
    # `full` trims the NO-NAME listing; the doors below narrow the WITH-NAME lookup.
    assert set(caps["inputSchema"]["properties"]) == {"kind", "name", "action", "search", "full"}


def test_capabilities_call_threads_action_and_search_through():
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "capabilities",
                                     "arguments": {"search": "datastore rows"}}})
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["matches"][0]["action"] == "datastore-get-rows"


# --- against the real manifests ------------------------------------------

@pytest.mark.parametrize("tool_name", ["procesio"])
def test_real_oversized_tool_degrades_and_stays_usable(monkeypatch, tool_name):
    """The case that motivated all of this: the full schema is ~369 KB, which the
    driver cannot read back. It must come back as an index instead."""
    monkeypatch.undo()  # drop the fake registry for this one
    tools = registry.list_tools()
    if not any(t.get("name") == tool_name for t in tools):
        pytest.skip(f"{tool_name} is not registered on this machine")

    full = bridge.capabilities(name=tool_name)["capability"]
    assert full["truncated"] is True
    assert full["action_count"] > 100
    assert len(json.dumps(full, ensure_ascii=False)) < 60_000

    # ...and the narrow door still answers, in about a kilobyte.
    one = bridge.capabilities(name=tool_name, action=full["actions"][0])
    assert len(json.dumps(one, ensure_ascii=False)) < 6_000


# --- managed turn: no competing orchestration loop -----------------------

def test_orchestrator_drive_refused_during_a_managed_turn(monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_agent",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("executed!")))
    token = bridge.set_managed_turn(True)
    try:
        res = bridge.run_agent("orchestrator", "drive", {"run-id": "r1"})
    finally:
        bridge.reset_managed_turn(token)
    assert res["ok"] is False
    assert res["refused"]["reason"] == "managed_turn"
    assert "second orchestration loop" in res["refused"]["message"]


def test_orchestrator_drive_allowed_outside_a_managed_turn(monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_agent",
                        lambda agent, argv, **k: {"ok": True, "data": {"ran": agent}})
    assert bridge.run_agent("orchestrator", "drive", {"run-id": "r1"})["data"]["ran"] == "orchestrator"


def test_managed_turn_still_allows_the_rest_of_the_orchestrator(monkeypatch):
    """Only the competing DRIVER is refused: intake/route/record stay available so a managed step
    keeps the doctrine and the run ledger."""
    monkeypatch.setattr(bridge.runner, "run_agent",
                        lambda agent, argv, **k: {"ok": True, "data": {"argv": argv}})
    token = bridge.set_managed_turn(True)
    try:
        for action in ("intake", "route", "record", "guidance"):
            assert bridge.run_agent("orchestrator", action, {})["ok"] is True
    finally:
        bridge.reset_managed_turn(token)


def test_managed_turn_blocklist_is_configurable(monkeypatch):
    monkeypatch.setenv("AAT_MCP_MANAGED_TURN_BLOCK", "orchestrator:drive,deputy:decide")
    monkeypatch.setattr(bridge.runner, "run_agent",
                        lambda *a, **k: {"ok": True, "data": {}})
    token = bridge.set_managed_turn(True)
    try:
        assert bridge.run_agent("deputy", "decide", {})["ok"] is False
        assert bridge.run_agent("deputy", "digest", {})["ok"] is True
    finally:
        bridge.reset_managed_turn(token)


def test_managed_turn_flag_does_not_leak_between_requests(monkeypatch):
    monkeypatch.setattr(bridge.runner, "run_agent", lambda *a, **k: {"ok": True, "data": {}})
    token = bridge.set_managed_turn(True)
    bridge.reset_managed_turn(token)
    assert bridge.run_agent("orchestrator", "drive", {})["ok"] is True
