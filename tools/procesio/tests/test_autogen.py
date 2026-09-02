"""Spec-driven actions: naming, full coverage, path/query/body handling, dry-run."""
from __future__ import annotations

from tools.procesio import autogen, main, swagger
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(profile, session):
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


def test_action_name_mappings():
    assert autogen.action_name("GET", "/api/Projects") == "get-projects"
    assert autogen.action_name("POST", "/api/Projects/{id}/run") == "post-projects-by-id-run"
    assert (autogen.action_name("GET", "/api/Projects/instances/{id}/status")
            == "get-projects-instances-by-id-status")
    assert (autogen.action_name("DELETE", "/api/DataTypes/attribute/{rootDataTypeId}/{attributeId}")
            == "delete-datatypes-attribute-by-rootdatatypeid-by-attributeid")


def test_one_action_per_endpoint():
    gen = autogen.build_actions()
    assert len(gen) == len(swagger.all_endpoints())


def test_every_endpoint_is_reachable():
    """Each spec endpoint must map to an action in the merged dispatcher."""
    names = set(main.ACTIONS)
    missing = [(ep["method"], ep["path"])
               for ep in swagger.all_endpoints()
               if autogen.action_name(ep["method"], ep["path"]) not in names]
    assert not missing, f"endpoints without an action: {missing[:5]}"


def test_generated_get_substitutes_path():
    sess = FakeSession(queue=[FakeResp(200, {"ok": 1})])
    out = main.dispatch("get-projects-by-id-payload", ["--id", "PID"],
                        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess))
    assert out["result"] == {"ok": 1}
    assert sess.calls[0]["url"] == "https://webapi.procesio.app/api/Projects/PID/payload"


def test_generated_post_passes_query_and_body():
    sess = FakeSession(queue=[FakeResp(200, {"id": "x"})])
    main.dispatch(
        "post-projects-by-id-run",
        ["--id", "PID", "--runSynchronous", "true",
         "--body", '{"payload":{},"connectionid":null}'],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess),
    )
    c = sess.calls[0]
    assert c["url"] == "https://webapi.procesio.app/api/Projects/PID/run"
    assert c["params"] == {"runSynchronous": "true"}
    assert c["json"] == {"payload": {}, "connectionid": None}


def test_generated_dry_run_does_not_send():
    sess = FakeSession(queue=[])
    out = main.dispatch("delete-projects-by-id", ["--id", "PID", "--dry-run"],
                        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess))
    assert out["dry_run"] is True
    assert out["method"] == "DELETE" and out["path"] == "/api/Projects/PID"
    assert sess.calls == []


def test_path_param_id_not_duplicated_as_query():
    """/api/Projects/instances/{id}/status lists 'id' among params; it must be a
    single required path arg, not also a query arg."""
    gen = autogen.build_actions()
    defn = gen["get-projects-instances-by-id-status"]
    import argparse
    p = argparse.ArgumentParser()
    defn.add_args(p)
    opts = [o[2:] for a in p._actions for o in a.option_strings
            if o.startswith("--") and o != "--help"]
    assert opts.count("id") == 1
    assert "flowTemplateId" in opts        # the real query params remain
