"""flowTemplateId on the instance endpoints.

The API spec marks it optional and the server cannot do without it, so a caller that
trusts the spec gets a failure that never names the parameter. These actions refuse
the call up front instead, and the generated wrappers must not lose that when the
endpoint snapshot is refreshed from Swagger.
"""
from __future__ import annotations

import pytest

from tools._lib.manifest import load_tool
from tools.procesio import autogen, main, swagger
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

CURATED = ["stop-instance", "get-instance-status", "get-instance-output"]
WRAPPERS = ["post-projects-instances-by-id-stop", "get-projects-instances-by-id-status",
            "get-projects-instances-by-id-output",
            "delete-projects-instances-by-id-dataretention"]


def _builder(session):
    profile = {"type": "apikey", "key": "N", "value": "V"}
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


@pytest.mark.parametrize("action", CURATED + WRAPPERS)
def test_refused_before_any_request_without_the_process_id(action):
    sess = FakeSession(queue=[])
    with pytest.raises(UsageError):
        main.dispatch(action, ["--id", "IID"], client_builder=_builder(sess))
    assert sess.calls == []


@pytest.mark.parametrize("action,flag", [
    ("stop-instance", "--flow-template-id"),
    ("post-projects-instances-by-id-stop", "--flowTemplateId"),
])
def test_stop_sends_the_process_id_as_a_query_parameter(action, flag):
    sess = FakeSession(queue=[FakeResp(200, "Stop process instance is complete.")])
    out = main.dispatch(action, ["--id", "IID", flag, "PID"], client_builder=_builder(sess))
    assert out["result"] == "Stop process instance is complete."
    call = sess.calls[0]
    assert call["url"].endswith("/api/Projects/instances/IID/stop")
    assert call["params"] == {"flowTemplateId": "PID"}


def test_a_refused_stop_points_at_the_process_id():
    """The server's whole answer is a bare 400 "Stopping process failed.", also for a
    process id that is not this instance's."""
    sess = FakeSession(queue=[FakeResp(400, "Stopping process failed.")])
    with pytest.raises(ProcesioAPIError) as caught:
        main.dispatch("stop-instance", ["--id", "IID", "--flow-template-id", "WRONG"],
                      client_builder=_builder(sess))
    assert caught.value.status == 400
    assert "--flow-template-id" in str(caught.value)
    assert "Stopping process failed" in str(caught.value.details)


def test_another_stop_failure_is_passed_through_unchanged():
    sess = FakeSession(queue=[FakeResp(403, {"message": "forbidden"})])
    with pytest.raises(ProcesioAPIError) as caught:
        main.dispatch("stop-instance", ["--id", "IID", "--flow-template-id", "PID"],
                      client_builder=_builder(sess))
    assert caught.value.status == 403
    assert "--flow-template-id" not in str(caught.value)


def test_every_required_query_entry_is_still_in_the_spec():
    """A key that no longer matches an endpoint would stop protecting anything, silently."""
    spec = {(ep["method"], ep["path"]): ep for ep in swagger.all_endpoints()}
    for key, params in autogen.REQUIRED_QUERY.items():
        assert key in spec, f"{key} is not in data/endpoints.json"
        assert params <= set(spec[key].get("params", [])), f"{key}: {params}"


def test_other_generated_query_parameters_stay_optional():
    """The override is per endpoint: status keeps its own flags optional."""
    sess = FakeSession(queue=[FakeResp(200, {"status": 50})])
    main.dispatch("get-projects-instances-by-id-status",
                  ["--id", "IID", "--flowTemplateId", "PID"], client_builder=_builder(sess))
    assert sess.calls[0]["params"] == {"flowTemplateId": "PID"}


@pytest.mark.parametrize("action,arg", [(a, "flow-template-id") for a in CURATED]
                         + [(a, "flowTemplateId") for a in WRAPPERS])
def test_manifest_says_it_is_required(action, arg):
    """The sync guard only checks one direction by name, so state this contract outright."""
    from pathlib import Path
    manifest = load_tool(Path(main.__file__).resolve().parent / "tool.yaml")
    spec = {a.name: a for a in manifest.get_action(action).args}
    assert spec[arg].required is True
