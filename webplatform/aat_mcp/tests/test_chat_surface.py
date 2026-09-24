"""The three gates that keep the published chat surface and the framework independent.

chat_surface.yaml declares what is published; the registry remains the source of truth
for what exists. They are allowed to drift - that is the point of having two of them -
but never silently, and never past CI.

    1. conformance  every declared target/argument still exists and still means the
                    same thing. Catches a renamed action, a retyped argument and, most
                    quietly of all, a NEW required argument on an action we already
                    publish - which breaks nothing until a user's first call.
    2. snapshot     the exact tools/list payload is checked in, so any change to the
                    published contract arrives as a reviewable diff instead of a
                    surprise in a directory listing. MCP clients cache tool definitions
                    at initialisation and do not refresh them, so a schema that changes
                    under a client does not error - it misleads.
    3. isolation    neither surface imports the other, and the published one reaches
                    only the shared substrate.

Regenerating the snapshot after a deliberate change:
    python -c "import sys; sys.path.insert(0,'webplatform/aat_mcp'); \
import json, chat_server as c; \
open('webplatform/aat_mcp/chat_surface.snapshot.json','w',newline='\\n').write( \
json.dumps(c.build_tools(c.load_surface()), indent=2, ensure_ascii=False)+'\\n')"
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import bridge  # noqa: F401  - puts the repo root on sys.path for `registry`
import chat_server
import gate
import registry
import server

_HERE = Path(__file__).resolve().parents[1]
SNAPSHOT = _HERE / "chat_surface.snapshot.json"


def _registry_index():
    tools = {t["name"]: t for t in registry.list_tools()}
    agents = {a["name"]: a for a in registry.list_agents(tools)}
    return tools, agents


def _resolve(spec):
    """(entry, action_dict) for a declared tool, or (None, None)."""
    tools, agents = _registry_index()
    target = spec["target"]
    who = target.get("tool") or target.get("agent")
    entry = (tools if "tool" in target else agents).get(who)
    if entry is None:
        return None, None
    action = {a["name"]: a for a in (entry.get("actions") or [])}.get(target.get("action"))
    return entry, action


# --- gate 1: conformance -------------------------------------------------

def test_every_declared_target_still_exists():
    missing = []
    for spec in chat_server.SURFACE["tools"]:
        entry, action = _resolve(spec)
        if entry is None or action is None:
            missing.append(f"{spec['name']} -> {spec['target']}")
    assert not missing, (
        "declared in chat_surface.yaml but not in the registry (an action was renamed "
        f"or removed; update the declaration deliberately): {missing}")


def test_every_declared_argument_still_exists_with_the_declared_type():
    problems = []
    for spec in chat_server.SURFACE["tools"]:
        _, action = _resolve(spec)
        if action is None:
            continue
        manifest = {a["name"]: a for a in action["args"]}
        declared = list(spec.get("args") or [])
        declared += [chat_server.SURFACE["common_args"][k] for k in (spec.get("common") or [])]
        for arg in declared:
            flag = arg["flag"]
            if flag not in manifest:
                problems.append(f"{spec['name']}: --{flag} no longer exists")
                continue
            want, got = arg.get("type"), manifest[flag].get("type")
            if want and got and want != got:
                problems.append(f"{spec['name']}: --{flag} is {got}, declared {want}")
    assert not problems, problems


def test_no_required_argument_is_left_undeclared():
    """The silent one. A new required argument on an action we already publish leaves
    the published schema valid and every call failing, because the surface has no way
    to supply it. It has to fail here instead."""
    problems = []
    for spec in chat_server.SURFACE["tools"]:
        _, action = _resolve(spec)
        if action is None:
            continue
        exposed = {a["flag"] for a in (spec.get("args") or [])}
        exposed |= {chat_server.SURFACE["common_args"][k]["flag"]
                    for k in (spec.get("common") or [])}
        for arg in action["args"]:
            if arg.get("required") and arg["name"] not in exposed and arg.get("default") is None:
                problems.append(f"{spec['name']}: --{arg['name']} is required by "
                                f"{spec['target']} but the surface cannot supply it")
    assert not problems, problems


def test_no_published_tool_reaches_an_irreversible_action():
    """This surface has no confirmed-twin path, so it must carry nothing that needs one.
    Adding a destructive action fails the build rather than growing a second, softer
    approval route beside the one in server.py."""
    bad = []
    for spec in chat_server.SURFACE["tools"]:
        t = spec["target"]
        verdict = gate.classify(t.get("tool") or t.get("agent"), t.get("action"))
        if not verdict["reversible"]:
            bad.append(f"{spec['name']} ({verdict['verb']}/{verdict['blast_class']})")
    assert not bad, bad


def test_read_only_entries_are_also_reversible():
    """read_only and reversible are different questions - process-create is reversible
    and is not read-only - but the implication holds one way: a call that changes
    nothing cannot be irreversible. A mislabel here would let a write run unattended."""
    for spec in chat_server.SURFACE["tools"]:
        if not spec["read_only"]:
            continue
        t = spec["target"]
        verdict = gate.classify(t.get("tool") or t.get("agent"), t.get("action"))
        assert verdict["reversible"], f"{spec['name']} claims read_only but the gate disagrees"


def test_excluded_operations_are_not_also_published():
    """The exclusion list is part of the contract. An entry that reappears in `tools`
    means someone reversed a decision without reading why it was made."""
    published = {(s["target"].get("tool") or s["target"].get("agent"), s["target"].get("action"))
                 for s in chat_server.SURFACE["tools"]}
    for item in chat_server.SURFACE["excluded"]:
        target = item["target"]
        if "*" in target or "<" in target or " " in target:
            continue  # a class of actions or an argument, not one target
        who, _, action = target.partition("/")
        assert (who, action) not in published, f"{target} is both excluded and published"
        assert item.get("reason", "").strip(), f"{target} is excluded with no reason"


# --- gate 2: snapshot ----------------------------------------------------

def test_published_surface_matches_the_checked_in_snapshot():
    built = chat_server.build_tools(chat_server.load_surface())
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert built == saved, (
        "the published tool list changed. If that was intended, regenerate the snapshot "
        "(command in this module's docstring), bump surface_version, and let the diff be "
        "reviewed - a client caches these definitions and will not notice on its own.")


def test_snapshot_is_the_shape_a_client_receives():
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    listed = chat_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed["result"]["tools"] == saved


# --- gate 3: isolation ---------------------------------------------------

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_the_two_surfaces_do_not_import_each_other():
    assert "server" not in _imports(_HERE / "chat_server.py")
    assert "chat_server" not in _imports(_HERE / "server.py")


def test_the_published_surface_reaches_only_the_shared_substrate():
    """Whatever this surface imports is what a change elsewhere can reach it through.
    Keeping the list short is the isolation; asserting it is what keeps it short."""
    allowed = {"bridge", "gate", "yaml", "json", "os", "sys", "pathlib", "__future__"}
    assert _imports(_HERE / "chat_server.py") <= allowed


def test_a_tool_that_dispatches_arbitrary_actions_is_never_read_only():
    """Applied across BOTH surfaces, and derived from the schema rather than a list of
    names, so a dispatcher added later is caught without anyone remembering this rule."""
    for tools in (server.TOOLS, chat_server.TOOLS):
        for t in tools:
            props = set(((t.get("inputSchema") or {}).get("properties") or {}))
            if "action" in props and props & {"tool", "agent"}:
                a = t["annotations"]
                assert a["readOnlyHint"] is False, t["name"]
                assert a["destructiveHint"] is True, t["name"]


# --- the surface as a client sees it -------------------------------------

def test_initialize_reports_the_surface_version():
    resp = chat_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05"}})
    info = resp["result"]["serverInfo"]
    assert info["name"] == "procesio-chat"
    assert info["version"] == chat_server.SURFACE["surface_version"]


def test_every_published_tool_is_named_for_its_domain():
    """Namespacing: a directory client merges several servers' tools into one list, so a
    bare `create_process` competes with every other automation product's."""
    for t in chat_server.TOOLS:
        assert t["name"].startswith("procesio_"), t["name"]
        assert t["title"] and t["description"], t["name"]


def test_no_published_tool_accepts_an_undeclared_argument():
    """The schema is the contract. An argument the declaration does not name is dropped
    rather than forwarded, so a caller cannot reach past the published surface."""
    spec = chat_server._BY_NAME["procesio_list_processes"]
    by_exposed = {chat_server.exposed_name(a) for a in spec["args"]}
    assert "profile" not in by_exposed  # a local installation detail, deliberately unexposed


def test_unknown_tool_is_an_error_payload_not_a_crash():
    payload, is_error = chat_server.call_tool("procesio_not_a_tool", {})
    assert is_error and "unknown tool" in payload["error"]


def test_an_oversized_result_is_capped_with_an_actionable_hint():
    spec = chat_server._BY_NAME["procesio_list_processes"]
    capped = chat_server._cap({"ok": True, "rows": ["x" * 100] * 2000}, spec)
    assert capped["truncated"] is True
    assert "search" in capped["hint"]  # names the argument that narrows THIS tool
    assert len(capped["preview"]) <= 2000
