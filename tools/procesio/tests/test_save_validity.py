"""The validity mark a save leaves behind, and the value a save reports.

These pin behaviour measured against the live platform, not a reading of the docs:

  * PROCESIO never computes `isValid`. It stores whatever the PUT body carries, and
    defaults it to TRUE when the body omits the field.
  * So a writer that passes a fetched flow straight through leaves a corrected process
    marked broken for ever, and a writer that reports its own pre-save validation
    describes the flow it sent rather than the one the platform kept.

Both were real: `node-set-param` on a correct process marked invalid reported
`isValid: true, put: true` while the server went on holding `isValid: false`.

A fake client throughout - no network.
"""
import pytest

from tools.procesio.handlers import fevalidate


class _Server:
    """A PROCESIO that stores `isValid` verbatim and never recomputes it - which is
    exactly what the live one was measured doing."""

    def __init__(self, stored_valid=False, fe_clean=True, be_valid=True):
        self.stored = {"id": "p1", "isValid": stored_valid, "variables": [], "actions": []}
        self.fe_clean = fe_clean
        self.be_valid = be_valid
        self.puts = []

    def get(self, path, query=None):
        if path.startswith("/api/DataTypes"):
            return {"pageItems": []}
        if path.startswith("/api/Projects/"):
            return {"flow": dict(self.stored)}
        return {}

    def post(self, path, body=None, query=None):
        if path == "/api/Projects/validate":
            return {"raw_text": ""} if self.be_valid else {"errors": ["bad runtime"]}
        return {}

    def put(self, path, body=None, query=None):
        self.puts.append(body)
        self.stored["isValid"] = body.get("isValid")   # verbatim, like the real one
        return {"raw_text": ""}


def test_a_clean_save_clears_a_stale_invalid_mark():
    """The reported symptom: fix the process, save it, and it stays marked broken."""
    srv = _Server(stored_valid=False)
    flow = {"id": "p1", "isValid": False}
    out = fevalidate.save_flow(srv, flow, flow_id="p1", valid=True)
    assert srv.stored["isValid"] is True, "the save must clear the stale mark"
    assert out["isValid"] is True, "and must report what the server now holds"


def test_the_reported_value_is_re_read_not_the_value_we_sent():
    """A server that disagrees with the body must be believed over our own measurement."""
    srv = _Server(stored_valid=False)

    def stubborn_put(path, body=None, query=None):
        srv.puts.append(body)          # accepts the write, keeps its own answer
        return {"raw_text": ""}
    srv.put = stubborn_put

    out = fevalidate.save_flow(srv, {"id": "p1"}, flow_id="p1", valid=True)
    assert out["stamped"] is True, "we asked for valid"
    assert out["isValid"] is False, "but the server kept false, and that is what is reported"


def test_an_invalid_flow_is_stamped_invalid_rather_than_left_alone():
    """Saving a half-built process is intended; marking it valid is not."""
    srv = _Server(stored_valid=True)
    out = fevalidate.save_flow(srv, {"id": "p1", "isValid": True}, flow_id="p1", valid=False)
    assert srv.stored["isValid"] is False
    assert out["isValid"] is False


def test_the_field_is_never_omitted():
    """Omitting it makes the platform default to true, which marks broken work valid."""
    srv = _Server()
    fevalidate.save_flow(srv, {"id": "p1"}, flow_id="p1", valid=False)
    assert "isValid" in srv.puts[0], "the body must carry the mark explicitly"
    assert srv.puts[0]["isValid"] is False


def test_a_failed_read_back_does_not_fail_a_save_that_landed():
    srv = _Server()

    def blind_get(path, query=None):
        if path.startswith("/api/Projects/"):
            raise RuntimeError("read-back unavailable")
        return {"pageItems": []}
    srv.get = blind_get

    out = fevalidate.save_flow(srv, {"id": "p1"}, flow_id="p1", valid=True)
    assert srv.puts, "the PUT still happened"
    assert out["isValid"] is None
    assert "readback_error" in out


def test_every_surgical_writer_goes_through_the_stamping_save():
    """No handler may PUT a fetched flow directly: that is how the mark went stale."""
    import pathlib
    root = pathlib.Path(fevalidate.__file__).resolve().parent
    for name in ("nodeparams.py", "sqlactions.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert 'client.put("/api/Projects", flow)' not in src, (
            f"{name} PUTs a fetched flow directly; use fevalidate.save_flow so the "
            "validity mark is stamped and the stored value re-read")


def test_a_forced_save_does_not_file_a_broken_process_as_valid():
    """build() hardcodes IsValid=True; the gate must overwrite it with the verdict.

    Without this, `process-edit --force` - the supported way to save half-finished work -
    marked every broken process valid, and the designer's own error list disagreed with
    the flag stored beside it.
    """
    from tools.procesio.dto.process import builder as pb

    class _C:
        def get(self, path, query=None):
            return {"pageItems": []} if path.startswith("/api/DataTypes") else {"flow": {"variables": []}}

        def post(self, path, body=None, query=None):
            return {"raw_text": ""}          # BE says valid; the designer will not

    dto = {"IsValid": True, "Actions": [], "Variables": []}
    pb._save_gate(_C(), dto, {"_force": True})
    assert dto["IsValid"] is False, "a flow with no Start/Stop is not valid, forced or not"


def test_a_clean_save_still_stamps_valid():
    from tools.procesio.dto.process import builder as pb

    class _C:
        def get(self, path, query=None):
            return {"pageItems": []} if path.startswith("/api/DataTypes") else {"flow": {"variables": []}}

        def post(self, path, body=None, query=None):
            return {"raw_text": ""}

    def act(aid, name, tmpl, ports):
        return {"id": aid, "actionName": name, "actionTemplateName": tmpl,
                "customData": {"type": "square", "name": name, "configuration": []},
                "ports": ports}

    dto = {"IsValid": True, "Variables": [], "actions": [
        act("start", "Start", "Start", [{"sourceId": "start", "destinationId": "stop"}]),
        act("stop", "Stop", "Stop", [])]}
    pb._save_gate(_C(), dto, {})
    assert dto["IsValid"] is True
