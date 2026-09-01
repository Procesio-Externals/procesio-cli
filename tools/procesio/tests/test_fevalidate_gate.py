"""Save-gate tests: FE (designer) + BE validation must block a process save unless
--force. Uses a fake client so no network is touched."""
import pytest

from tools.procesio.errors import ValidationBlocked
from tools.procesio.handlers import fevalidate
from tools.procesio.dto.process import builder as pb


class _FakeClient:
    """Minimal client: serves an empty datatype catalog, an empty subprocess flow, and a
    scripted /api/Projects/validate response."""

    def __init__(self, be_valid=True):
        self.be_valid = be_valid
        self.posts = []

    def get(self, path, query=None):
        if path.startswith("/api/DataTypes"):
            return {"pageItems": []}
        if path.startswith("/api/Projects/"):
            return {"flow": {"variables": []}}
        return {}

    def post(self, path, body=None, query=None):
        self.posts.append(path)
        if path == "/api/Projects/validate":
            return {"raw_text": ""} if self.be_valid else {"errors": ["bad runtime"]}
        return {}


def _valid_dto():
    def act(aid, name, tmpl, ports):
        return {"id": aid, "actionName": name, "actionTemplateName": tmpl,
                "customData": {"type": "square", "name": name, "configuration": []},
                "ports": ports}
    return {"actions": [
        act("start", "Start", "Start", [{"sourceId": "start", "destinationId": "mid"}]),
        act("mid", "Mid", "Concatenate", [{"sourceId": "mid", "destinationId": "stop"}]),
        act("stop", "Stop", "Stop", [])], "variables": []}


def _broken_dto():
    # no Stop, unconnected Start -> FE errors
    dto = _valid_dto()
    dto["actions"] = [dto["actions"][0]]  # only Start, no ports target
    dto["actions"][0]["ports"] = []
    return dto


def test_gate_passes_on_valid_flow():
    rep = fevalidate.pre_save_validate(_FakeClient(be_valid=True), _valid_dto(), force=False)
    assert rep["blocked"] is False
    assert rep["fe"]["clean"] and rep["be"]["valid"]


def test_gate_blocks_on_fe_errors():
    with pytest.raises(ValidationBlocked) as ei:
        fevalidate.pre_save_validate(_FakeClient(be_valid=True), _broken_dto(), force=False)
    assert ei.value.report["fe"]["error_count"] > 0


def test_gate_blocks_on_be_invalid():
    with pytest.raises(ValidationBlocked):
        fevalidate.pre_save_validate(_FakeClient(be_valid=False), _valid_dto(), force=False)


def test_force_bypasses_block():
    rep = fevalidate.pre_save_validate(_FakeClient(be_valid=False), _broken_dto(), force=True)
    assert rep["blocked"] is True and rep["forced"] is True  # reported, not raised


def test_process_component_has_save_gate_wired():
    # the wiring the create/edit paths depend on
    assert pb.COMPONENT.save_gate is not None


def test_edit_runs_gate_and_blocks(monkeypatch):
    # _edit builds the DTO then gates before PUT; a broken build must never reach PUT
    calls = {"put": 0}
    fake = _FakeClient(be_valid=True)

    def fake_build(config, ctx):
        return _broken_dto()

    monkeypatch.setattr(pb, "build", fake_build)
    fake.put = lambda *a, **k: calls.__setitem__("put", calls["put"] + 1)  # noqa: E731
    with pytest.raises(ValidationBlocked):
        pb._edit(fake, "some-id", {"title": "t", "actions": []}, {"_force": False})
    assert calls["put"] == 0  # gate aborted before the PUT


def test_flowlint_extras_folded_into_gate():
    # flow-lint's unique designer save-blockers (here: Node code binding an error-scope
    # variable) are merged into run_fe_validation as blocking errors.
    from tools.procesio.handlers.flowlint import CODE_PID
    flow = {"actions": [{
        "actionName": "Compose", "actionTemplateName": "Node",
        "customData": {"name": "Compose", "type": "square", "configuration": []},
        "parameters": [{"tabPropertyId": CODE_PID, "value": "x",
                        "variable": [{"id": 0, "variableId": "e1"}]}]}],
        "variables": [{"id": "e1", "name": "err_x", "type": 20, "isError": True}]}
    rep = fevalidate.run_fe_validation(_FakeClient(be_valid=True), flow, include_types=False)
    assert any(e["code"] == "CODE_ERROR_SCOPE" for e in rep["errors"])
