"""Guard: the credential SCOPE (profile + workspace) reaches every inner
`procesio` call.

Regression. `verify` and `audit` used to forward only `--profile`, so any
process outside the profile's default workspace failed with HTTP 400
`{"statusCode": 501, "value": "User is not authorized for the requested
resource."}` - and a user/password profile cannot carry a workspace of its own,
so there was no workaround at all. The scope must be splatted into EVERY inner
invoke, not just the first one: the gate fetches, validates, runs, and reads
instance status, and each of those is a separately scoped call.
"""
from __future__ import annotations

import argparse

from agents.procesio import verifylib
from agents.procesio.handlers import audit as audit_h
from agents.procesio.handlers import verify as verify_h
from agents.procesio.tests.conftest import action, flow

WS = "3fd85e9d-121e-415b-877f-f488cd685ce3"
START = action("Start")
CONFIGURED = action("Add", params=[{"Value": "x", "Variable": []}],
                    settings=[{"value": "x"}])
STOP = action("Stop")


class _Ctx:
    def __init__(self, invoke):
        self.invoke = invoke


def _parse(add_args, argv):
    p = argparse.ArgumentParser()
    add_args(p)
    return p.parse_args(argv)


def _flags(call_args: list, flag: str):
    """The value passed for `flag` in one recorded invoke, or None."""
    return call_args[call_args.index(flag) + 1] if flag in call_args else None


def test_scope_args_builds_both_flags():
    assert verifylib.scope_args("account", WS) == [
        "--profile", "account", "--workspace-id", WS]


def test_scope_args_omits_what_was_not_given():
    assert verifylib.scope_args(None, None) == []
    assert verifylib.scope_args("account", None) == ["--profile", "account"]
    assert verifylib.scope_args(None, WS) == ["--workspace-id", WS]


def test_verify_forwards_workspace_to_every_inner_call(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    fake_invoke.set("run-process", {"result": {"id": "iid", "status": 50}})
    fake_invoke.set("get-instance-status", {"result": {"status": 50, "actions": []}})

    verifylib.verify_process(fake_invoke, "pid", profile="account",
                             workspace_id=WS, run=True)

    seen = {a for _, a, _ in fake_invoke.calls}
    assert seen == {"get-process", "request", "run-process", "get-instance-status"}
    for _tool, action_name, args in fake_invoke.calls:
        assert _flags(args, "--workspace-id") == WS, f"{action_name} lost the workspace"
        assert _flags(args, "--profile") == "account", f"{action_name} lost the profile"


def test_verify_without_workspace_sends_no_flag(fake_invoke):
    """Omitting it must stay a no-op, so the profile's own workspace still works."""
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    verifylib.verify_process(fake_invoke, "pid", profile="account")
    assert all("--workspace-id" not in args for _t, _a, args in fake_invoke.calls)


def test_verify_handler_threads_the_flag(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    fake_invoke.set("request", {"result": {"isValid": True}})
    args = _parse(verify_h._args,
                  ["--process-id", "pid", "--profile", "account", "--workspace-id", WS])
    verify_h._verify(_Ctx(fake_invoke), args)
    assert _flags(fake_invoke.calls[0][2], "--workspace-id") == WS


def test_audit_handler_threads_the_flag(fake_invoke):
    fake_invoke.set("get-process", flow([START, CONFIGURED, STOP]))
    args = _parse(audit_h._args,
                  ["--process-id", "pid", "--profile", "account", "--workspace-id", WS])
    report = audit_h._audit(_Ctx(fake_invoke), args)
    assert report["process_id"] == "pid"
    tool, action_name, call_args = fake_invoke.calls[0]
    assert (tool, action_name) == ("procesio", "get-process")
    assert _flags(call_args, "--workspace-id") == WS
    assert _flags(call_args, "--profile") == "account"
