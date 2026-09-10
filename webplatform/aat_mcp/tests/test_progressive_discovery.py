from __future__ import annotations

import json

import bridge
import server


def _payload(response):
    return json.loads(response["result"]["content"][0]["text"])


def _call(name, arguments):
    return server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})


def test_capabilities_query_routes_to_bounded_search(monkeypatch):
    monkeypatch.setattr(server.bridge, "search_capabilities",
                        lambda query, kind, name, limit: {"query": query, "count": limit})
    response = _call("capabilities", {"query": "schedule", "limit": 3})
    assert _payload(response) == {"query": "schedule", "count": 3}


def test_get_skill_without_resource_preserves_original_operation(monkeypatch):
    monkeypatch.setattr(server.bridge, "get_skill",
                        lambda name: {"name": name, "content": "# Skill", "resources": {}})
    response = _call("get_skill", {"name": "demo"})
    assert _payload(response)["content"] == "# Skill"


def test_get_skill_resource_uses_index_path(monkeypatch):
    monkeypatch.setattr(server.bridge, "get_skill_resource",
                        lambda name, path: {"name": name, "resource": {"path": path}})
    response = _call("get_skill", {"name": "demo", "resource": "references/guide.md"})
    assert _payload(response)["resource"]["path"] == "references/guide.md"


def test_get_skill_resource_failure_is_structured(monkeypatch):
    def fail(name, path):
        raise ValueError("resource path must stay inside the skill")
    monkeypatch.setattr(server.bridge, "get_skill_resource", fail)
    response = _call("get_skill", {"name": "demo", "resource": "../secret"})
    assert response["result"]["isError"] is True
    assert "stay inside" in _payload(response)["error"]


def test_optional_fields_are_advertised_without_new_tools():
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    schemas = {t["name"]: t["inputSchema"] for t in response["result"]["tools"]}
    assert len(schemas) == 6
    assert schemas["get_skill"]["required"] == ["name"]
    assert "resource" in schemas["get_skill"]["properties"]
    assert {"query", "limit"} <= schemas["capabilities"]["properties"].keys()


def test_real_installed_skill_and_nested_sql_resource():
    response = _call("get_skill", {"name": "sql-server-optimizer"})
    assert response["result"]["isError"] is False
    skill = _payload(response)
    root = bridge.registry.get_skill("sql-server-optimizer").path
    assert skill["content"] == (root / "SKILL.md").read_text(encoding="utf-8")
    path = "references/scripts/export-indexes.sql"
    assert path in skill["resources"]["references"]
    result = _call("get_skill", {"name": "sql-server-optimizer", "resource": path})
    assert result["result"]["isError"] is False
    assert _payload(result)["resource"]["content"] == (root / path).read_text(encoding="utf-8")
    assert "content" not in _payload(result)
    legacy_path = "references/scripts/export-tables.sql"
    assert legacy_path in skill["resources"]["references"]
    rejected = _call("get_skill", {"name": "sql-server-optimizer", "resource": legacy_path})
    assert rejected["result"]["isError"] is True
    assert "not UTF-8" in _payload(rejected)["error"]


def test_real_resource_rejections_at_protocol_boundary(monkeypatch, tmp_path):
    root = tmp_path / "demo"
    (root / "assets").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: demo\ndescription: Demo\n---\n# Demo\n")
    (root / "assets" / "binary.bin").write_bytes(b"\xff\xfe")
    (root / "assets" / "large.txt").write_bytes(b"x" * 512_001)
    monkeypatch.setattr(bridge.registry, "SKILLS_DIR", tmp_path)
    for path in ("../outside", "/outside", "", "assets/missing", "assets/binary.bin",
                 "assets/large.txt", "assets/" + "x" * 256, "assets/\x00"):
        response = _call("get_skill", {"name": "demo", "resource": path})
        assert response["result"]["isError"] is True, path
        payload = _payload(response)
        assert "error" in payload and "content" not in payload
        assert str(tmp_path) not in payload["error"]
