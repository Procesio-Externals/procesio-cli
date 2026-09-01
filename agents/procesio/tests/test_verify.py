from __future__ import annotations

from agents._lib.toolrunner import ToolError
from agents.procesio import verifylib
from agents.procesio.tests.conftest import action, flow

START = action("Start")
STOP = action("Stop")
CONFIGURED = action("Add", params=[{"Value": "x", "Variable": []}],
                    settings=[{"value": "x"}])


def _check(report, cid):
    return next(c for c in report["checks"] if c["id"] == cid)


def test_clean_process_passes_without_run(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    rep = verifylib.verify_process(fake_invoke, "pid")
    assert rep["verdict"] == "pass"
    assert _check(rep, "validate-process")["status"] == "pass"
    assert _check(rep, "config-parity-audit")["status"] == "pass"
    assert _check(rep, "run-instance")["status"] == "skip"
    # manual checks must always be surfaced
    assert any(s["id"] == "form-behavior" for s in rep["manual_checks"])


def test_designer_blank_drops_verdict_to_warn(fake_invoke):
    blank = action("Send Email", params=[{"Value": "<%0%>", "Variable": [{"id": 0}]}],
                   settings=[{"value": ""}])
    fake_invoke.set("get-process", flow([START, blank, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    rep = verifylib.verify_process(fake_invoke, "pid")
    assert rep["verdict"] == "warn"
    assert _check(rep, "config-parity-audit")["status"] == "warn"


def test_run_finished_status_50_passes(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    fake_invoke.set("run-process", {"result": {"id": "iid", "status": 50}})
    fake_invoke.set("get-instance-status", {"result": {"status": 50, "actions": []}})
    rep = verifylib.verify_process(fake_invoke, "pid", run=True)
    assert rep["verdict"] == "pass"
    assert _check(rep, "run-instance")["status"] == "pass"


def test_run_with_errors_status_40_fails(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    fake_invoke.set("run-process", {"result": {"id": "iid", "status": 40}})
    fake_invoke.set("get-instance-status", {"result": {
        "status": 40, "actions": [{"name": "Add", "errorMessage": "boom"}]}})
    rep = verifylib.verify_process(fake_invoke, "pid", run=True)
    assert rep["verdict"] == "fail"
    rc = _check(rep, "run-instance")
    assert rc["status"] == "fail"
    assert rc["detail"]["action_errors"][0]["errorMessage"] == "boom"


def test_validate_surfaces_400_validation_messages_as_warn(fake_invoke):
    # PROCESIO returns HTTP 400 + a list of validation messages for an invalid
    # process; verify must surface them as a warn, not skip.
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", ToolError(
        "procesio", "invalid_argument", "HTTP 400",
        {"status": 400, "body": {"body": [
            {"statusCode": 390, "value": "Action has too few input ports.",
             "target": "prc"}]}}))
    rep = verifylib.verify_process(fake_invoke, "pid")
    vc = _check(rep, "validate-process")
    assert vc["status"] == "warn"
    assert vc["detail"]["errors"][0]["statusCode"] == 390
    assert rep["verdict"] == "warn"


def test_validate_endpoint_error_is_skip_not_fail(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", ToolError("procesio", "server_error", "no validate here"))
    rep = verifylib.verify_process(fake_invoke, "pid")
    assert _check(rep, "validate-process")["status"] == "skip"
    assert rep["verdict"] == "pass"  # a skipped optional check does not fail the gate


def test_verify_reads_live_camelcase_shapes(fake_invoke):
    # regression: live get-process/instance status are camelCase and nest actions
    # under instance.actions; verify must parse both.
    fake_invoke.set("get-process", {"result": {"flow": {
        "title": "Live", "actions": [
            {"actionTemplateName": "Start", "parameters": []},
            {"actionName": "a", "actionTemplateName": "Add",
             "parameters": [{"value": "x"}],
             "customData": {"configuration": [{"settings": [{"value": "x"}]}]}},
            {"actionTemplateName": "Stop", "parameters": []}]}}})
    fake_invoke.set("request", {"result": {"isValid": True}})
    fake_invoke.set("run-process", {"result": {"id": "iid", "status": 50}})
    fake_invoke.set("get-instance-status",
                    {"result": {"instance": {"status": 50, "actions": []}}})
    rep = verifylib.verify_process(fake_invoke, "pid", run=True)
    assert rep["title"] == "Live"
    assert rep["verdict"] == "pass"
    assert _check(rep, "run-instance")["status"] == "pass"


def test_fetch_failure_fails_fast(fake_invoke):
    fake_invoke.set("get-process", ToolError("procesio", "not_found", "no such process"))
    rep = verifylib.verify_process(fake_invoke, "pid")
    assert rep["verdict"] == "fail"
    assert _check(rep, "fetch")["status"] == "fail"
