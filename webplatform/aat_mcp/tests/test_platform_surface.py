"""The platform's typed surface: its gates against the registry, and what a named call does.

platform_surface.yaml declares which actions the platform's assistant gets as named tools.
The registry stays the source of truth for what exists. As for the public surface, the two
may drift, never silently, and never past CI:

    1. conformance  every declared target, argument and fixed flag still exists and still
                    means the same thing, and nothing declared is irreversible.
    2. snapshot     the exact tools/list payload is checked in, so a change to what the
                    assistant is offered arrives as a reviewable diff.
    3. isolation    the two declared surfaces share surface.py and nothing else.

Regenerating the snapshot after a deliberate change:
    python -c "import sys; sys.path.insert(0,'webplatform/aat_mcp'); \
import json, platform_server as p; \
open('webplatform/aat_mcp/platform_surface.snapshot.json','w',newline='\\n').write( \
json.dumps(p.build_tools(p.load_surface()), indent=2, ensure_ascii=False)+'\\n')"
"""
from __future__ import annotations

import ast
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import bridge
import chat_server
import gate
import http_server
import metrics
import platform_server
import pytest
import registry
import server
import surface

_HERE = Path(__file__).resolve().parents[1]
SNAPSHOT = _HERE / "platform_surface.snapshot.json"
SPECS = platform_server.SURFACE["tools"]
OK = {"ok": True, "data": {"rows": []}, "error": None, "returncode": 0}


def _action(spec):
    """The manifest action a declared tool runs, or None."""
    kind, who, action = platform_server._target(spec)
    try:
        manifest = registry.get_tool(who) if kind == "tool" else registry.get_agent(who)
    except Exception:  # noqa: BLE001
        return None
    return {a.name: a for a in manifest.actions}.get(action)


# --- gate 1: conformance -------------------------------------------------------------------

def test_every_declared_target_still_exists():
    missing = [f"{s['name']} -> {s['target']}" for s in SPECS if _action(s) is None]
    assert not missing, (
        "declared in platform_surface.yaml but not in the registry (an action was renamed "
        f"or removed; update the declaration deliberately): {missing}")


def test_every_declared_argument_and_fixed_flag_still_exists():
    problems = []
    for spec in SPECS:
        action = _action(spec)
        if action is None:
            continue
        manifest = {a.name for a in action.args}
        for flag in [a["flag"] for a in spec.get("args") or []] + list(spec.get("fixed") or {}):
            if flag not in manifest:
                problems.append(f"{spec['name']}: --{flag} no longer exists")
    assert not problems, problems


def test_a_declared_type_is_one_the_action_can_take():
    """A scalar must be declared as the manifest types it. A JSON argument is declared as an
    object or an array where the manifest says string: the bridge encodes it into the one
    flag. That only works for a flag given ONCE, so a repeatable flag is never declared
    as an object."""
    problems = []
    for spec in SPECS:
        action = _action(spec)
        if action is None:
            continue
        manifest = {a.name: a for a in action.args}
        for arg in spec.get("args") or []:
            have = manifest.get(arg["flag"])
            if have is None:
                continue
            want = arg.get("type", "string")
            if want in ("object", "array"):
                if have.type not in ("string", want) or (want == "object" and have.repeatable):
                    problems.append(f"{spec['name']}: --{arg['flag']} is {have.type}, declared {want}")
            elif want != have.type:
                problems.append(f"{spec['name']}: --{arg['flag']} is {have.type}, declared {want}")
    assert not problems, problems


def test_no_required_argument_is_left_undeclared():
    """A new required argument on a declared action leaves the schema valid and every call
    failing, because the surface has no way to supply it. It has to fail here instead."""
    problems = []
    for spec in SPECS:
        action = _action(spec)
        if action is None:
            continue
        supplied = {a["flag"] for a in spec.get("args") or []} | set(spec.get("fixed") or {})
        for arg in action.args:
            if arg.required and arg.name not in supplied and arg.default is None:
                problems.append(f"{spec['name']}: --{arg.name} is required by {spec['target']} "
                                f"but the surface cannot supply it")
    assert not problems, problems


def test_an_argument_the_action_requires_is_required_here_too():
    """Otherwise the client lets the call through and the tool refuses it: one round trip
    for a mistake the schema could have stopped."""
    problems = []
    for spec in SPECS:
        action = _action(spec)
        if action is None:
            continue
        declared = {a["flag"]: bool(a.get("required")) for a in spec.get("args") or []}
        for arg in action.args:
            if arg.required and arg.name in declared and not declared[arg.name]:
                problems.append(f"{spec['name']}: --{arg.name} is required by the action")
    assert not problems, problems


def test_nothing_declared_is_irreversible():
    """This surface has no confirmed twin, so it must carry nothing that needs one."""
    bad = []
    for spec in SPECS:
        _, who, action = platform_server._target(spec)
        verdict = gate.classify(who, action)
        if not verdict["reversible"]:
            bad.append(f"{spec['name']} ({verdict['verb']}/{verdict['blast_class']})")
    assert not bad, bad


def test_no_tool_takes_a_workspace_an_environment_a_profile_or_a_file():
    """A turn runs in one workspace with one credential, and the model's files are not on
    this machine. An argument for any of them is a call that can only fail."""
    for spec in SPECS:
        assert not spec.get("common"), spec["name"]
        for arg in spec.get("args") or []:
            assert arg["flag"] not in ("workspace-id", "environment", "profile"), spec["name"]
            assert not arg["flag"].endswith("-file") and arg["flag"] != "out", (spec["name"], arg["flag"])


def test_a_schema_taken_from_the_manifest_is_the_manifest_s():
    spec = platform_server._BY_NAME["procesio_edit_process_nodes"]
    built = {t["name"]: t for t in platform_server.TYPED_TOOLS}[spec["name"]]
    published = {a.name: a for a in _action(spec).args}["changes"].json_schema
    changes = built["inputSchema"]["properties"]["changes"]
    assert changes["items"] == published["items"]
    assert changes["description"] == "The changes, applied in order."


def test_every_tool_is_named_for_its_domain_and_says_what_it_does():
    names = [t["name"] for t in platform_server.TYPED_TOOLS]
    assert len(names) == len(set(names))
    for tool in platform_server.TYPED_TOOLS:
        assert tool["name"].startswith("procesio_"), tool["name"]
        assert tool["title"] and len(tool["description"]) > 40, tool["name"]
    assert not set(names) & {t["name"] for t in server.TOOLS}


def test_the_definitions_stay_small_enough_to_send_with_every_request():
    """Every definition rides in every model request. The limit is a prompt to ask whether a
    new tool earns its place, not a number that is right for ever: raise it when the list
    grows by a choice, and never to let a tool in unasked."""
    assert len(json.dumps(platform_server.TYPED_TOOLS)) < 45_000


# --- gate 2: snapshot ---------------------------------------------------------------------

def test_the_typed_tool_list_matches_the_checked_in_snapshot():
    built = platform_server.build_tools(platform_server.load_surface())
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert built == saved, (
        "the platform's typed tool list changed. If that was intended, regenerate the "
        "snapshot (command in this module's docstring) and let the diff be reviewed.")


def test_the_public_surface_is_built_the_same_way_as_before():
    """Both declared surfaces now go through surface.py. The public one must not move."""
    saved = json.loads((_HERE / "chat_surface.snapshot.json").read_text(encoding="utf-8"))
    assert surface.build_tools(chat_server.load_surface()) == saved


# --- gate 3: isolation --------------------------------------------------------------------

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_the_shared_surface_module_imports_no_server_and_runs_nothing():
    assert not _imports(_HERE / "surface.py") & {
        "server", "chat_server", "platform_server", "bridge", "gate", "protocol"}


def test_the_platform_surface_and_the_public_one_do_not_import_each_other():
    assert "chat_server" not in _imports(_HERE / "platform_server.py")
    assert "platform_server" not in _imports(_HERE / "chat_server.py")
    assert "platform_server" not in _imports(_HERE / "server.py")


# --- which surface is served --------------------------------------------------------------

@pytest.mark.parametrize("value, served", [
    (None, "generic"), ("", "generic"), ("generic", "generic"), ("typed", "typed"),
    ("both", "both"), (" Both ", "both"), ("everything", "generic")])
def test_the_setting_chooses_the_surface_and_an_unknown_value_is_generic(monkeypatch, value, served):
    if value is None:
        monkeypatch.delenv(platform_server.SURFACE_ENV, raising=False)
        assert platform_server.mode() == served
    else:
        monkeypatch.setenv(platform_server.SURFACE_ENV, value)
        assert platform_server.mode() == served and platform_server.mode(value) == served


def test_each_mode_lists_its_tools_named_ones_first():
    generic = [t["name"] for t in server.TOOLS]
    typed = [t["name"] for t in platform_server.TYPED_TOOLS]
    assert [t["name"] for t in platform_server.tools_for("generic")] == generic
    assert [t["name"] for t in platform_server.tools_for("typed")] == typed
    assert [t["name"] for t in platform_server.tools_for("both")] == typed + generic


def test_the_default_serves_exactly_what_was_served_before():
    assert platform_server.MODE == "generic"
    assert platform_server.TOOLS == server.TOOLS
    assert platform_server.SERVER_INFO == server.SERVER_INFO


@pytest.fixture
def serving(monkeypatch):
    """Serve one mode for a test. Returns a function that sets it."""
    def serve(mode):
        monkeypatch.setattr(platform_server, "MODE", mode)
        monkeypatch.setattr(platform_server, "TOOLS", platform_server.tools_for(mode))
    return serve


@pytest.fixture
def ran(monkeypatch):
    """The bridge, replaced by a recorder. `ran.answer` is what the next call returns."""
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    seen = type("Ran", (), {"calls": [], "answer": dict(OK)})()

    def run(kind):
        def fake(who, action, args, **kwargs):
            seen.calls.append((kind, who, action, args))
            if isinstance(seen.answer, Exception):
                raise seen.answer
            return seen.answer
        return fake
    monkeypatch.setattr(platform_server.bridge, "run_tool", run("tool"))
    monkeypatch.setattr(platform_server.bridge, "run_agent", run("agent"))
    return seen


def test_a_generic_tool_is_unknown_when_only_named_tools_are_served(serving, ran):
    serving("typed")
    payload, is_error = platform_server.call_tool("run_tool", {"tool": "procesio"})
    assert is_error and "unknown tool" in payload["error"] and ran.calls == []


def test_a_named_tool_is_unknown_when_only_generic_tools_are_served(serving, ran):
    serving("generic")
    payload, is_error = platform_server.call_tool("procesio_list_processes", {})
    assert is_error and "unknown tool" in payload["error"] and ran.calls == []


def test_both_modes_reach_both_kinds_of_tool(serving, ran, monkeypatch):
    serving("both")
    monkeypatch.setattr(server.bridge, "_scan_registry", lambda: ([], [], []))
    _, is_error = platform_server.call_tool("procesio_list_processes", {})
    assert not is_error and ran.calls[-1][:3] == ("tool", "procesio", "list-processes")
    payload, is_error = platform_server.call_tool("capabilities", {})
    assert not is_error and payload == {"count": 0, "capabilities": []}


def test_tools_list_and_tools_call_go_through_the_served_surface(serving, ran):
    serving("both")
    listed = platform_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, modern=False)
    assert listed["result"]["tools"] == platform_server.tools_for("both")
    called = platform_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "procesio_list_processes", "arguments": {"search": "invoice"}}}, modern=False)
    assert called["result"]["isError"] is False
    assert ran.calls == [("tool", "procesio", "list-processes", {"search": "invoice"})]


# --- what a named call does -----------------------------------------------------------------

def test_a_named_call_runs_its_action_with_flags_for_the_exposed_names(ran):
    platform_server.call_typed("procesio_list_processes", {"search": "invoice", "page_size": 5})
    assert ran.calls == [("tool", "procesio", "list-processes", {"search": "invoice", "page-size": 5})]


def test_an_exposed_name_that_differs_from_the_flag_is_mapped_back(ran):
    platform_server.call_typed("procesio_read_process", {"id": "p-1"})
    platform_server.call_typed("procesio_get_instance_status", {"id": "i-1", "process_id": "p-1"})
    assert ran.calls[0][3] == {"in": "p-1"}
    assert ran.calls[1][3] == {"id": "i-1", "flow-template-id": "p-1"}


def test_a_structured_argument_reaches_the_bridge_as_it_was_given(ran):
    """The bridge encodes an object into the one flag. The surface must not do it first."""
    changes = [{"op": "set", "node": "Get rates", "property": "Endpoint", "value": "https://x"}]
    platform_server.call_typed("procesio_edit_process_nodes", {"id": "p-1", "changes": changes})
    assert ran.calls[0][:3] == ("tool", "procesio", "node-edit-batch")
    assert ran.calls[0][3] == {"id": "p-1", "changes": changes}


def test_a_fixed_flag_is_always_sent_and_cannot_be_changed_by_the_caller(ran):
    platform_server.call_typed("procesio_run_process_and_wait", {"id": "p-1", "timeout_seconds": 60})
    assert ran.calls[0][3] == {"id": "p-1", "timeout": 60, "synchronous": True}
    payload, is_error = platform_server.call_typed(
        "procesio_run_process_and_wait", {"id": "p-1", "synchronous": False})
    assert is_error and "no argument synchronous" in payload["error"]["message"]
    assert len(ran.calls) == 1


def test_the_plain_run_does_not_wait(ran):
    platform_server.call_typed("procesio_run_process", {"id": "p-1", "payload": {"year": 2026}})
    assert ran.calls[0][3] == {"id": "p-1", "payload": {"year": 2026}}


def test_a_list_of_values_reaches_the_bridge_as_a_list(ran):
    """The bridge turns a list into one flag per item for an argument the manifest marks as
    repeatable. The surface must hand the list on as it is: joined or encoded here, the tool
    would read all of it as one value."""
    platform_server.call_typed("procesio_set_form_element_config", {
        "id": "f-1", "element": "firstName", "set": ["label=First name", "required=true"]})
    platform_server.call_typed("procesio_get_form_element", {
        "id": "f-1", "element": "firstName", "keys": ["label", "required"]})
    assert ran.calls[0] == ("tool", "procesio", "form-set-element-config", {
        "id": "f-1", "element": "firstName", "set": ["label=First name", "required=true"]})
    assert ran.calls[1][3] == {"id": "f-1", "element": "firstName", "key": ["label", "required"]}


def test_a_list_of_texts_says_which_of_the_two_ways_the_tool_reads_it():
    """A tool reads a list of texts in one of two ways: a flag given once per item, or one flag
    that takes a JSON list. The bridge sends the first only for a flag the manifest marks as
    repeatable, and the second for any other. A declaration that means the second says so
    (`json: true`), so that a list which reaches the tool as one JSON value is a choice
    someone made and not a repeatable flag the manifest forgot to mark."""
    problems = []
    for spec in SPECS:
        action = _action(spec)
        if action is None:
            continue
        manifest = {a.name: a for a in action.args}
        for arg in spec.get("args") or []:
            have = manifest.get(arg["flag"])
            if have is None or arg.get("type") != "array" or arg.get("items", "string") != "string":
                continue
            if arg.get("json") and have.repeatable:
                problems.append(f"{spec['name']}: --{arg['flag']} is repeatable, not one JSON value")
            if not arg.get("json") and not have.repeatable and have.type != "array":
                problems.append(f"{spec['name']}: --{arg['flag']} is not marked repeatable; "
                                f"declare `json: true` if the tool takes a JSON list in one flag")
    assert not problems, problems


def test_a_json_list_of_texts_reaches_the_bridge_as_a_list_too(ran):
    """The bridge encodes it. The surface hands on what it was given, whichever way it is read."""
    platform_server.call_typed("procesio_set_form_query", {
        "id": "f-1", "name": "by status", "sql": "select 1", "parameters": ["status", "owner"]})
    assert ran.calls[0][:3] == ("tool", "procesio", "form-set-saved-statement")
    assert ran.calls[0][3] == {"form-id": "f-1", "name": "by status", "sql": "select 1",
                               "parameters": ["status", "owner"]}
    assert bridge._repeatable_args("tool", "procesio", "form-set-saved-statement") == frozenset()


def test_a_choice_of_values_is_in_the_schema():
    """The client then refuses a value outside the choice before the call is made."""
    tools = {t["name"]: t for t in platform_server.TYPED_TOOLS}
    direction = tools["procesio_add_process_variable"]["inputSchema"]["properties"]["direction"]
    state = tools["procesio_set_process_active"]["inputSchema"]["properties"]["state"]
    assert direction["enum"] == ["input", "process", "output"]
    assert state["enum"] == ["true", "false"] and state["type"] == "string"


def test_a_tool_that_changes_what_a_process_does_can_carry_its_documentation():
    """The surgical writers refuse a change without the documentation it needs. A named tool
    over one of them that had no `doc` could only ever be refused."""
    missing = []
    for spec in SPECS:
        action = _action(spec)
        if action is None:
            continue
        takes_doc = any(a.name == "doc" for a in action.args)
        offers_doc = any(a["flag"] == "doc" for a in spec.get("args") or [])
        if takes_doc and not offers_doc and not spec["read_only"]:
            missing.append(spec["name"])
    assert not missing, missing


def test_the_guidance_tool_runs_the_agent(ran):
    platform_server.call_typed("procesio_get_guidance", {"topic": "playbook"})
    assert ran.calls == [("agent", "procesio", "guidance", {"topic": "playbook"})]


def test_an_argument_the_tool_does_not_declare_is_an_error_that_lists_the_valid_ones(ran):
    payload, is_error = platform_server.call_typed(
        "procesio_list_processes", {"search": "x", "workspace_id": "w", "profile": "p"})
    assert is_error and ran.calls == []
    assert payload["error"] == {"code": "invalid_argument",
                                "message": "procesio_list_processes has no argument profile, workspace_id"}
    assert [a["name"] for a in payload["valid_args"]] == ["search", "page", "page_size"]
    assert "Nothing ran" in payload["hint"]


def test_a_missing_required_argument_is_refused_before_anything_runs(ran):
    payload, is_error = platform_server.call_typed("procesio_get_instance_status", {"id": "i-1"})
    assert is_error and ran.calls == []
    assert payload["error"]["message"] == "procesio_get_instance_status needs process_id"
    assert {"name": "process_id", "required": True} in payload["valid_args"]


@pytest.mark.parametrize("arguments", [None, [], "text"])
def test_arguments_that_are_not_an_object_are_read_as_none_given(ran, arguments):
    payload, is_error = platform_server.call_typed("procesio_list_workspaces", arguments)
    assert not is_error and ran.calls[0][3] == {}


@pytest.mark.parametrize("name, arguments, read_only, dry_run", [
    ("procesio_list_processes", {}, True, False),
    ("procesio_create_process", {"config": {"name": "x"}}, False, False),
    ("procesio_create_process", {"config": {"name": "x"}, "dry_run": True}, False, True),
    ("procesio_create_process", {"config": {"name": "x"}, "dry_run": False}, False, False),
    ("procesio_edit_process_nodes", {"id": "p", "changes": [{}], "dry_run": True}, False, True),
])
def test_every_answer_says_whether_the_call_reads_only_and_whether_it_was_a_dry_run(
        ran, name, arguments, read_only, dry_run):
    payload, is_error = platform_server.call_typed(name, arguments)
    assert not is_error
    assert payload["read_only"] is read_only and payload["dry_run"] is dry_run
    assert payload["data"] == OK["data"]          # the tool's answer is still all there


def test_the_two_statements_are_the_first_keys_of_every_answer(ran):
    """A caller that keeps only the head of a long answer must still be able to read them."""
    answers = [platform_server.call_typed("procesio_list_processes", {})[0],
               platform_server.call_typed("procesio_list_processes", {"nope": 1})[0]]
    ran.answer = {"ok": True, "data": {"rows": ["x" * 100] * 1000}}
    answers.append(platform_server.call_typed("procesio_list_processes", {})[0])
    ran.answer = {"ok": False, "error": {"code": "invalid_argument", "message": "bad"}}
    answers.append(platform_server.call_typed("procesio_list_processes", {})[0])
    ran.answer = RuntimeError("boom")
    answers.append(platform_server.call_typed("procesio_list_processes", {})[0])
    for answer in answers:
        assert list(answer)[:2] == ["read_only", "dry_run"], list(answer)
        assert json.dumps(answer).startswith('{"read_only": true, "dry_run": false,')


def test_a_failed_call_says_it_too_and_keeps_the_tool_s_error(ran):
    ran.answer = {"ok": False, "data": None, "returncode": 2,
                  "error": {"code": "invalid_argument", "message": "change 1: node not found"}}
    payload, is_error = platform_server.call_typed(
        "procesio_edit_process_nodes", {"id": "p", "changes": [{}], "dry_run": True})
    assert is_error and payload["read_only"] is False and payload["dry_run"] is True
    assert payload["error"]["message"] == "change 1: node not found"
    assert "does not mean you lack access" in payload["hint"]
    assert "do not look it up" in payload["hint"]


def test_a_refused_call_and_a_raised_one_say_it_as_well(ran, monkeypatch):
    payload, _ = platform_server.call_typed("procesio_list_processes", {"nope": 1})
    assert payload["read_only"] is True and payload["dry_run"] is False
    ran.answer = RuntimeError("boom")
    payload, is_error = platform_server.call_typed("procesio_list_processes", {})
    assert is_error and payload["error"] == "RuntimeError: boom" and payload["read_only"] is True


@pytest.mark.parametrize("code", sorted(server._FINAL_REFUSAL_CODES))
def test_a_refusal_that_no_retry_can_fix_reaches_the_model_without_a_retry_hint(ran, code):
    ran.answer = {"ok": False, "error": {"code": code, "message": "stop"}}
    payload, is_error = platform_server.call_typed("procesio_list_processes", {})
    assert is_error and "hint" not in payload and payload["error"]["code"] == code


def test_a_result_over_the_cap_is_cut_with_a_hint_that_names_how_to_ask_for_less(ran):
    ran.answer = {"ok": True, "data": {"rows": ["x" * 100] * 1000}}
    payload, is_error = platform_server.call_typed("procesio_list_processes", {})
    assert not is_error and payload["truncated"] is True
    assert payload["max_response_bytes"] == platform_server.MAX_RESPONSE_BYTES == 24000
    assert "search" in payload["hint"] and len(payload["preview"]) <= 2000
    assert payload["read_only"] is True


def test_a_tool_can_declare_its_own_cap(ran):
    ran.answer = {"ok": True, "data": "x" * 60000}
    payload, _ = platform_server.call_typed("procesio_get_guidance", {"topic": "playbook"})
    assert "truncated" not in payload
    payload, _ = platform_server.call_typed("procesio_list_workspaces", {})
    assert payload["truncated"] is True


def test_an_irreversible_target_is_refused_even_if_it_was_declared(ran, monkeypatch):
    monkeypatch.setattr(platform_server.gate, "classify", lambda who, action: {
        "reversible": False, "verb": "delete", "blast_class": "data", "reason": "x"})
    payload, is_error = platform_server.call_typed("procesio_list_processes", {})
    assert is_error and "irreversible" in payload["refused"] and ran.calls == []


def test_a_named_tool_s_target_is_known_for_the_log_and_no_other_name_s_is():
    assert platform_server.target_of("procesio_edit_process_nodes") == ("procesio", "node-edit-batch")
    assert platform_server.target_of("procesio_get_guidance") == ("procesio", "guidance")
    assert platform_server.target_of("run_tool") is None
    assert platform_server.target_of(None) is None


# --- over HTTP ----------------------------------------------------------------------------

@pytest.fixture
def httpd(serving, ran):
    serving("both")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), http_server._make_handler(None))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _request(httpd, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    try:
        conn.request(method, path, body=json.dumps(body) if body is not None else None,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read() or b"null")
    finally:
        conn.close()


def test_the_health_answer_names_the_surface_and_lists_the_tools_being_served(httpd):
    status, body = _request(httpd, "GET", "/health")
    assert status == 200 and body["surface"] == "both"
    assert body["tools"] == [t["name"] for t in platform_server.tools_for("both")]


def test_a_named_tool_is_listed_and_called_over_http(httpd, ran):
    _, listed = _request(httpd, "POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert "procesio_edit_process_nodes" in [t["name"] for t in listed["result"]["tools"]]
    _, called = _request(httpd, "POST", "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                 "params": {"name": "procesio_read_process",
                                                            "arguments": {"id": "p-1"}}})
    payload = json.loads(called["result"]["content"][0]["text"])
    assert called["result"]["isError"] is False and payload["read_only"] is True
    assert ran.calls == [("tool", "procesio", "flow-digest", {"in": "p-1"})]


def test_the_access_line_names_the_action_behind_a_named_tool(serving):
    serving("both")
    asked = http_server._asked_for({"method": "tools/call", "params": {
        "name": "procesio_edit_process_nodes", "arguments": {"id": "p-1", "changes": []}}})
    assert asked == ("tools/call", "procesio_edit_process_nodes", "procesio", "node-edit-batch")
    generic = http_server._asked_for({"method": "tools/call", "params": {
        "name": "run_tool", "arguments": {"tool": "procesio", "action": "list-processes"}}})
    assert generic == ("tools/call", "run_tool", "procesio", "list-processes")


def test_a_named_tool_is_other_on_the_access_line_while_it_is_not_served(serving):
    serving("generic")
    asked = http_server._asked_for({"method": "tools/call", "params": {
        "name": "procesio_edit_process_nodes", "arguments": {"id": "p-1"}}})
    assert asked == ("tools/call", "other")


def test_the_metric_label_for_the_mcp_tool_is_the_served_list(serving):
    serving("generic")
    assert http_server._mcp_tool_names() == {t["name"] for t in server.TOOLS}
    serving("both")
    names = http_server._mcp_tool_names()
    assert "procesio_edit_process_nodes" in names and "run_tool" in names
    assert len(names) == len(platform_server.TYPED_TOOLS) + len(server.TOOLS)


def test_a_named_call_is_counted_under_its_own_name(serving, ran, monkeypatch):
    serving("both")
    monkeypatch.setattr(bridge, "_METRIC_NAMES", {})
    metrics.reset()
    metrics.enable()
    try:
        with metrics.mcp_request({"method": "tools/call",
                                  "params": {"name": "procesio_read_process"}},
                                 http_server._mcp_tool_names()) as seen:
            seen.response = {"result": {"isError": False}}
        text = metrics.render()
    finally:
        metrics.enable(False)
        metrics.reset()
    assert 'mcp_tool="procesio_read_process"' in text
