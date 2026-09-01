"""Dispatch + handler routing tests with a FakeClient (zero network)."""
from __future__ import annotations

import pytest

import cb_main as main


def _run(action, argv, fake_client):
    return main.dispatch(action, argv, client_factory=lambda: fake_client)


def test_unknown_action_raises(fake_client):
    import cb_errors as errors
    with pytest.raises(errors.UsageError):
        _run("nope", [], fake_client)


def test_check_hits_auth_me(fake_client):
    fake_client.responses[("GET", "/auth/me")] = {
        "email": "x@example.com", "role": "admin", "has_llm_key": True}
    out = _run("check", [], fake_client)
    assert out["ok"] is True and out["role"] == "admin"
    assert fake_client.calls[0][:2] == ("GET", "/auth/me")


def test_create_build_requires_a_source(fake_client):
    import cb_errors as errors
    with pytest.raises(errors.UsageError):
        _run("create-build", ["--user-requirements", "do x"], fake_client)


def test_create_build_posts_body(fake_client):
    _run("create-build", ["--api-url", "https://docs", "--user-requirements", "x"],
         fake_client)
    method, path, _params, body = fake_client.calls[0]
    assert (method, path) == ("POST", "/builds")
    assert body["api_url"] == "https://docs" and body["user_requirements"] == "x"


def test_answer_wraps_answers_object(fake_client):
    _run("answer", ["--build-id", "B1", "--answers", '{"q1":"a1"}'], fake_client)
    method, path, _p, body = fake_client.calls[0]
    assert (method, path) == ("POST", "/builds/B1/answers")
    assert body == {"answers": {"q1": "a1"}}


def test_answer_rejects_bad_json(fake_client):
    import cb_errors as errors
    with pytest.raises(errors.UsageError):
        _run("answer", ["--build-id", "B1", "--answers", "not-json"], fake_client)


def test_override_stage_payload(fake_client):
    _run("override-stage",
         ["--build-id", "B1", "--target-step", "3", "--target-status", "waiting_user"],
         fake_client)
    method, path, _p, body = fake_client.calls[0]
    assert (method, path) == ("POST", "/builds/B1/override-stage")
    assert body == {"target_step": 3, "target_status": "waiting_user"}


def test_download_artifact_streams_to_out(fake_client):
    out = _run("download-artifact", ["--build-id", "B1", "--out", "pkg.nupkg"],
               fake_client)
    assert out["bytes"] == 123
    assert fake_client.calls[0][:2] == ("DOWNLOAD", "/builds/B1/artifact")


def test_update_file_requires_content(fake_client):
    import cb_errors as errors
    with pytest.raises(errors.UsageError):
        _run("update-file", ["--build-id", "B1", "--filename", "A.cs"], fake_client)


def test_knowledge_create_validates_module_type(fake_client):
    import cb_errors as errors
    with pytest.raises(errors.UsageError):
        _run("knowledge-create",
             ["--module-type", "bogus", "--name", "x.md", "--content", "y"],
             fake_client)


def test_knowledge_update_puts_content(fake_client):
    _run("knowledge-update",
         ["--module-type", "prompt", "--name", "clarify.md", "--content", "hi"],
         fake_client)
    method, path, _p, body = fake_client.calls[0]
    assert (method, path) == ("PUT", "/admin/knowledge/prompt/clarify.md")
    assert body == {"content": "hi"}


def test_api_escape_hatch_get(fake_client):
    out = _run("api", ["--method", "GET", "--path", "/builds", "--query", '{"page":1}'],
               fake_client)
    assert out["method"] == "GET" and out["path"] == "/builds"
    assert fake_client.calls[0][:2] == ("GET", "/builds")


def test_all_actions_present():
    # Sanity: the full surface is wired (auth+builds+files+telemetry+admin+raw).
    for a in ("check", "create-build", "gather", "answer", "approve-plan",
              "approve-generate", "download-artifact", "telemetry",
              "knowledge-list", "build-selftest", "api"):
        assert a in main.ACTIONS
