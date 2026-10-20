"""prepare_ctx must surface a workspace's custom (connector) actions into the
action catalog GENERICALLY - any installed custom action resolvable by name or
actionId, with no per-action code - and must do so even when the full live
catalog fetch (`GET /api/Actions?getFullAction=true`) is slow or fails.

The full-catalog endpoint is occasionally pathologically slow, so the build
falls back to the bundled, built-in-only catalog. Before the fix that fallback
silently dropped every connector, so a process that used one failed with
"unknown action ... not in the action catalog". The fix fetches the workspace's
custom actions separately via the narrow, fast
`GET /api/Actions/node?getFullAction=true&isCustom=true` (the same endpoint
`customaction-list` uses) and merges them in unconditionally.
"""
import tools.procesio.dto.process.builder as pb


CUSTOM = {
    "actionId": "517cf512-6a26-4bb7-b0c6-c6f8116e12a4",
    "name": "HTML to Word (.docx)",
    "isProcesioAction": False,
    "configuration": [],
}


class _Client:
    """Minimal fake: the full-catalog fetch is the failure path, the scoped
    custom-action fetch is the fast path that carries the connector."""

    def __init__(self, full_fails=True, full_actions=None):
        self.full_fails = full_fails
        self.full_actions = full_actions or []
        self.calls = []

    def get(self, path, params=None, **kw):
        # accepts read_timeout=/deadline= (the client's real knobs), like ProcesioClient.get
        self.calls.append((path, params))
        if path == "/api/Actions":
            if self.full_fails:
                raise RuntimeError("full catalog pathologically slow")
            return {"actions": self.full_actions}
        if path == "/api/Actions/node":
            assert params == {"getFullAction": "true", "isCustom": "true"}
            return {"actions": [CUSTOM]}
        raise AssertionError(f"unexpected GET {path}")


def test_custom_action_resolves_when_full_catalog_fetch_fails():
    c = _Client(full_fails=True)
    ctx = pb.prepare_ctx(c, {"title": "t", "variables": [], "actions": []})
    idx = ctx["catalog"]
    # resolvable by name (lowercased) AND by actionId
    assert idx.get("html to word (.docx)") is CUSTOM
    assert idx.get(CUSTOM["actionId"]) is CUSTOM
    # and a built-in is still present from the bundled catalog
    assert idx.get("generate guid"), "bundled built-ins must remain available"
    # the scoped custom-action endpoint was actually consulted
    assert any(p == "/api/Actions/node" for p, _ in c.calls)


def test_resolve_template_finds_custom_action_by_name_and_id():
    c = _Client(full_fails=True)
    ctx = pb.prepare_ctx(c, {"title": "t", "variables": [], "actions": []})
    assert pb._resolve_template("HTML to Word (.docx)", ctx) is CUSTOM
    assert pb._resolve_template(CUSTOM["actionId"], ctx) is CUSTOM


def test_custom_action_merged_even_when_full_catalog_omits_it():
    # Full fetch succeeds but returns only built-ins (connectors absent); the
    # scoped fetch must still add the custom action.
    c = _Client(full_fails=False, full_actions=[])
    ctx = pb.prepare_ctx(c, {"title": "t", "variables": [], "actions": []})
    assert ctx["catalog"].get(CUSTOM["actionId"]) is CUSTOM
