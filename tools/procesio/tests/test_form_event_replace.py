"""form-set-element-event: safe replace (O8).

An element commonly carries [RUN_PROCESS, RUN_JAVASCRIPT] on one click trigger.
--replace-action replaces only one action's events and keeps the rest in order;
bare --replace wipes everything and must warn."""
from __future__ import annotations

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(session):
    return lambda prof: ProcesioClient(
        profile={"type": "apikey", "key": "N", "value": "V"}, name="t", session=session)


def _form():
    """A button whose click trigger already carries two events (a process run and a
    JS handler), in that order."""
    return {
        "id": "F1", "name": "F", "type": 0, "status": 1, "state": True,
        "data": {"elements": [
            {"id": "btn", "type": "button", "configs": [
                {"key": "name", "value": "btn"},
                {"key": "onClickEvents", "value": {"debounce": 0, "events": [
                    {"id": "ev-proc", "type": "onClick", "action": "RUN_PROCESS",
                     "config": {"processId": "p"}},
                    {"id": "ev-js", "type": "onClick", "action": "RUN_JAVASCRIPT",
                     "config": {"code": "old"}},
                ]}},
            ]},
        ]},
    }


def _events_in_put(sess):
    put = sess.calls[-1]
    assert put["method"] == "PUT"
    assert put["url"].endswith("/api/FormTemplate")
    els = put["json"]["Data"]["elements"]
    cfg = next(c for c in els[0]["configs"] if c["key"] == "onClickEvents")
    return cfg["value"]["events"]


def test_replace_action_preserves_other_events_and_order():
    # GET (fetch) then PUT; no concurrency token on the form -> no extra refetch.
    sess = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    main.dispatch(
        "form-set-element-event",
        ["--id", "F1", "--element", "btn", "--on", "click",
         "--action", "RUN_JAVASCRIPT", "--config", '{"code": "new"}',
         "--replace-action", "RUN_JAVASCRIPT"],
        client_builder=_builder(sess))
    events = _events_in_put(sess)
    assert [e["action"] for e in events] == ["RUN_PROCESS", "RUN_JAVASCRIPT"]
    assert events[0]["id"] == "ev-proc"          # the process event survived, in place
    assert events[1]["id"] != "ev-js"            # the JS event was replaced


def test_bare_replace_warns_when_discarding_multiple():
    sess = FakeSession(queue=[FakeResp(200, _form())])
    out = main.dispatch(
        "form-set-element-event",
        ["--id", "F1", "--element", "btn", "--on", "click",
         "--action", "RUN_JAVASCRIPT", "--config", '{"code": "new"}',
         "--replace", "--dry-run"],
        client_builder=_builder(sess))
    assert out["event_count"] == 1               # everything replaced
    assert "warning" in out
    assert "RUN_PROCESS" in out["warning"] and "--replace-action" in out["warning"]


def test_replace_and_replace_action_are_mutually_exclusive():
    from tools.procesio import errors
    sess = FakeSession(queue=[FakeResp(200, _form())])
    try:
        main.dispatch(
            "form-set-element-event",
            ["--id", "F1", "--element", "btn", "--on", "click",
             "--action", "RUN_JAVASCRIPT", "--config", '{"code": "x"}',
             "--replace", "--replace-action", "RUN_JAVASCRIPT"],
            client_builder=_builder(sess))
        assert False, "expected UsageError"
    except errors.UsageError as e:
        assert "not both" in str(e)
