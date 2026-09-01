"""`<component>-edit --dry-run` must preview the EDIT, not a create.

The bug: the dry-run branch called `build_dto` straight from the loaded config, skipping the
component's own edit preparation. For a process that preparation is what reuses the live flow's
VARIABLE IDS by name and its canvas positions — so the preview showed brand-new variable ids while
the real edit would have kept them.

That is the worst possible direction for a preview to be wrong. A process variable is referenced by
GUID from outside the process (a form's RUN_PROCESS inputMap/outputMap binds it by id), so "do the
ids change?" is exactly the question a dry-run is run to answer, and it answered it wrongly in both
directions: a preserved id shown as changed, and — for a config that renames a variable — a change
shown as if nothing external would break.
"""
from __future__ import annotations

import argparse

from tools.procesio.dto import framework
from tools.procesio.dto.process import builder as process_builder


LIVE_VAR_ID = "11111111-1111-1111-1111-111111111111"


class _Client:
    """Serves one live flow, the way GET /api/Projects/{id} does."""

    def __init__(self):
        self.gets = []

    def get(self, path, query=None):
        self.gets.append(path)
        return {"flow": {"id": "flow-1", "title": "P", "actions": [],
                         "variables": [{"id": LIVE_VAR_ID, "name": "Row", "isError": False}]}}


def _component(calls: list) -> framework.Component:
    """A minimal component whose build simply reports the ctx it was handed."""
    def build(config, ctx):
        calls.append(ctx)
        return {"Variables": [{"Name": "Row",
                               "Id": (ctx.get("existing_var_ids") or {}).get("row", "NEW-ID")}]}

    def edit_ctx(client, resource_id, config, ctx):
        cur = client.get(f"/api/Projects/{resource_id}")
        flow = cur.get("flow", cur)
        return {**ctx, "existing_var_ids": {(v["name"] or "").strip().lower(): v["id"]
                                            for v in flow.get("variables") or []}}

    return framework.Component(
        # the real process dir, so validate_config finds a schema; the config below satisfies it
        name="process", description="", dir=process_builder.DIR,
        build=build, create_endpoint=("POST", "/x"), get_path="/x/{id}",
        extract_id=lambda r, d: None, edit_ctx=edit_ctx)


def _args(**kw):
    return argparse.Namespace(id="flow-1", config=None, config_file=None,
                              dry_run=True, force=False, no_types=False, **kw)


def test_the_dry_run_preview_reuses_the_live_variable_ids():
    calls: list = []
    comp = _component(calls)
    client = _Client()

    dto = framework.build_edit_dto(comp, client, "flow-1", {"title": "P"}, {})

    assert dto["Variables"][0]["Id"] == LIVE_VAR_ID, (
        "the preview must show the id the edit would actually write")
    assert calls and calls[0].get("existing_var_ids") == {"row": LIVE_VAR_ID}


def test_a_component_without_an_edit_ctx_hook_is_unaffected():
    calls: list = []
    comp = _component(calls)
    comp.edit_ctx = None
    client = _Client()

    dto = framework.build_edit_dto(comp, client, "flow-1", {"title": "P"}, {})

    assert dto["Variables"][0]["Id"] == "NEW-ID"
    assert client.gets == [], "no live read when the component has nothing to preserve"


def test_an_unreadable_live_resource_falls_back_to_a_plain_build():
    """A preview must still be produced when the live flow cannot be read."""
    calls: list = []
    comp = _component(calls)

    class Broken(_Client):
        def get(self, path, query=None):
            raise RuntimeError("gone")

    dto = framework.build_edit_dto(comp, Broken(), "flow-1", {"title": "P"}, {})
    assert dto["Variables"][0]["Id"] == "NEW-ID"
