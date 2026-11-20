"""form-embed: what a web page needs to embed a form with the PROCESIO form SDK.

The facts asserted here were checked on production on 2026-11-20 with the SDK built from
PROCESIO/procesio-form-sdk: a public, published form embeds and reports ready / resize /
submit / error; `values` is applied before the form's onLoad events; the production runtime
build answers none of the page's requests (its bundle has the bridge, not the request names),
while forms-dev answers them."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools.procesio.handlers import form_embed as fe
from tools.procesio.errors import UsageError


def _el(eid, kind, name, *, parent=None, events=None, label=None):
    configs = [{"id": f"{eid}-n", "key": "name", "value": name},
               {"id": f"{eid}-v", "key": "value", "value": ""}]
    if label:
        configs.append({"id": f"{eid}-l", "key": "label", "value": label})
    if events:
        configs.append({"id": f"{eid}-e", "key": "onClickEvents",
                        "value": {"debounce": 0, "events": events}})
    return {"id": eid, "type": kind, "parentId": parent, "configs": configs}


def _form(**over):
    form = {
        "id": "F1", "name": "Contact", "isPrivate": False, "status": 1, "state": True,
        "workspaceId": "WS1",
        "data": {
            "elements": [
                _el("e1", "input", "email", label="Email"),
                _el("e2", "select", "plan"),
                _el("t1", "table", "items"),
                {"id": "r1", "type": "dynamic-table-row", "parentId": "t1",
                 "configs": [{"id": "r1-n", "key": "name", "value": "itemsrow"}]},
                _el("c1", "input", "rowsku", parent="r1"),
                _el("b1", "button", "send", events=[{"id": "EV1", "type": "CLICK",
                                                     "action": "RUN_PROCESS",
                                                     "config": {"processId": "P1"}}]),
            ],
            "events": [{"id": "EV2", "type": "FORM_LOAD", "action": "RUN_DATA_STORE_OPERATION",
                        "config": {"operation": "READ"}}],
        },
    }
    form.update(over)
    return form


BUNDLE_FULL = "x embedOrigin y set-values z run-trigger"
BUNDLE_EVENTS = "x embedOrigin y"


def _http(bundle, npm=None):
    def get(url):
        if url.endswith("/"):
            return '<script type="module" src="/assets/index-AB12.js"></script>'
        if "/assets/" in url:
            return bundle
        if "registry.npmjs.org" in url:
            return json.dumps({"dist-tags": {"latest": npm}}) if npm else '{"error":"Not found"}'
        return ""
    return get


class _Client:
    def __init__(self, form, tiny="abc123"):
        self.form, self.tiny = form, tiny
        self.profile = {"forms_base": "https://forms.procesio.app"}
        self.workspace_id = "WS1"

    def get(self, path, *a, **k):
        if path.startswith("/api/CustomUrl/"):
            return {"tinyUrl": self.tiny}
        return self.form


def _args(**over):
    base = dict(id="F1", framework="html", values=None, sdk_url=None, out=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_only_a_public_published_enabled_form_can_be_embedded():
    assert fe.embeddability(_form()) == []
    why = fe.embeddability(_form(isPrivate=True, status=0, state=False))
    assert len(why) == 3 and "private" in why[0] and "draft" in why[1] and "disabled" in why[2]


def test_fields_are_the_named_value_holders_outside_table_rows():
    assert [f["name"] for f in fe.fields(_form())] == ["email", "plan"]


def test_triggers_cover_element_and_form_events():
    rows = fe.triggers(_form())
    assert [(t["id"], t["element"], t["on"]) for t in rows] == [
        ("EV1", "send", "onClickEvents"), ("EV2", None, "form onLoad")]
    assert rows[0]["does"] == "process P1" and rows[1]["does"] == "data store READ"


@pytest.mark.parametrize("bundle,embed,requests", [(BUNDLE_FULL, True, True),
                                                   (BUNDLE_EVENTS, True, False),
                                                   ("plain", False, False)])
def test_runtime_support_is_read_from_the_bundle(bundle, embed, requests):
    got = fe.runtime_support("https://forms.example", _http(bundle))
    assert (got["embed"], got["requests"]) == (embed, requests)


def test_a_runtime_that_cannot_be_read_is_unknown_not_an_error():
    def boom(url):
        raise OSError("offline")
    assert fe.runtime_support("https://forms.example", boom)["embed"] is None


def test_the_action_reports_everything_a_page_needs():
    out = fe.form_embed(_Client(_form()), _args(values='{"email": "ana@example.com", "nope": 1}'),
                        http_get=_http(BUNDLE_EVENTS))
    assert out["embeddable"] is True and out["path"] == "abc123"
    assert out["create_options"] == {"formId": "F1", "workspaceId": "WS1",
                                     "values": {"email": "ana@example.com", "nope": 1}}
    assert "baseUrl" not in out["create_options"]          # production is the SDK default
    joined = " ".join(out["warnings"])
    assert "['nope']" in joined and "does not answer the page's requests" in joined
    assert "not on the public npm registry" in joined
    assert "ProcesioForm.create('#procesio-form'" in out["snippet"]


def test_another_environment_passes_its_forms_host_and_a_published_sdk_is_not_flagged():
    client = _Client(_form())
    client.profile = {"forms_base": "https://forms-dev.procesio.app"}
    out = fe.form_embed(client, _args(), http_get=_http(BUNDLE_FULL, npm="1.2.0"))
    assert out["create_options"]["baseUrl"] == "https://forms-dev.procesio.app"
    assert out["sdk"]["npm_latest"] == "1.2.0" and out["warnings"] == []


def test_a_private_draft_form_is_reported_with_its_reasons():
    out = fe.form_embed(_Client(_form(isPrivate=True, status=0)), _args(),
                        http_get=_http(BUNDLE_FULL, npm="1.0.0"))
    assert out["embeddable"] is False and len(out["warnings"]) == 2


@pytest.mark.parametrize("kind,marker", [("html", "<script src="), ("module", "import { create }"),
                                         ("react", "useEffect")])
def test_each_snippet_flavour(kind, marker):
    code = fe.snippet(kind, {"formId": "F1"}, "https://x/sdk.js")
    assert marker in code and '"formId": "F1"' in code


def test_an_unknown_flavour_is_refused():
    with pytest.raises(UsageError):
        fe.snippet("svelte", {}, "u")


def test_out_writes_a_page_that_loads_the_sdk_and_logs_events(tmp_path):
    target = tmp_path / "embed.html"
    out = fe.form_embed(_Client(_form()), _args(out=str(target), sdk_url="/sdk.js"),
                        http_get=_http(BUNDLE_FULL, npm="1.0.0"))
    html = target.read_text(encoding="utf-8")
    assert out["page"] == str(target.resolve())
    assert '<script src="/sdk.js"></script>' in html and "ProcesioForm.create" in html
    assert "'submit'" in html and "http(s)" in html


def test_the_action_is_registered():
    from tools.procesio import main
    assert "form-embed" in main.ACTIONS
