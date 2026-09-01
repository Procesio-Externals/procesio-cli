"""Webhook builder — PURE config -> WebhookDto.

A webhook ties an inbound HTTP request to a process flow. Its payload shape is a
*webhook-type* data model (DataModelTypeParam.Webhook = 2) generated from a sample
payload via POST /api/Webhooks/generate-data (done in prepare_ctx).

Working create recipe (cracked live 2026-06-24): POST /api/Webhooks with the
generated DataModel embedded + DataModelId + the sample Definition + IsEdited=true
(PascalCase). Without the generated webhook-type DataModel the gateway returns a
generic 502 "resource is not able to be created or modified".

API:
  - generate model: POST /api/Webhooks/generate-data {Definition: "<json>"} -> {dataModel, payloadIsList}
  - Create: POST /api/Webhooks (WebhookDto) -> created webhook
  - Get:    GET  /api/Webhooks/{id}
  - Edit:   PUT  /api/Webhooks
  - Trigger (anonymous): GET|POST /api/Webhooks/launch/{id}
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from tools.procesio import config
from tools.procesio.dto.framework import Component
from tools.procesio.errors import UsageError

DIR = Path(__file__).resolve().parent

_TYPE = {"auto": 0, "manual": 1}
_RESP_TYPE = {"staticjson": 1, "static": 1, "javascript": 2, "js": 2, "jsonpath": 3}


def _new_id(ctx) -> str:
    return (ctx.get("new_id") or (lambda: str(uuid.uuid4())))()


def _custom_response(cfg):
    if not cfg:
        return None
    ct = cfg.get("type", "staticjson")
    return {"ConfigType": _RESP_TYPE.get(str(ct).strip().lower(), ct),
            "Config": cfg.get("config", "")}


def build(config: dict, ctx: dict) -> dict:
    dm = ctx.get("data_model")
    if dm is None:
        raise UsageError("webhook build needs a generated data model in ctx "
                         "(prepare_ctx calls /api/Webhooks/generate-data on the sample)")
    sample = config.get("sample", {})
    definition = config.get("definition") or json.dumps(sample)
    wtype = config.get("type", "manual")
    return {
        "Id": ctx.get("webhook_id") or _new_id(ctx),
        "Name": config["name"],
        "PayloadIsList": bool(config.get("payloadIsList", ctx.get("payload_is_list", False))),
        "HasHeader": bool(config.get("hasHeader", False)),
        "HasQuery": bool(config.get("hasQuery", False)),
        "DataModelId": dm.get("id"),
        "Type": _TYPE.get(str(wtype).strip().lower(), wtype),
        "Definition": definition,
        "IsEdited": True,
        "DataModel": dm,
        "CustomResponseConfig": _custom_response(config.get("customResponse")),
    }


def prepare_ctx(client, config: dict) -> dict:
    """Generate the webhook-type data model from the sample payload."""
    sample = config.get("sample")
    definition = config.get("definition") or (json.dumps(sample) if sample is not None else None)
    if not definition:
        raise UsageError("provide config.sample (a representative payload object) "
                         "so the webhook data model can be generated")
    gen = client.post("/api/Webhooks/generate-data", {"Definition": definition})
    return {"data_model": gen.get("dataModel"), "payload_is_list": gen.get("payloadIsList", False)}


def _extract_id(resp, dto):
    if isinstance(resp, dict):
        return resp.get("id") or resp.get("Id") or dto.get("Id")
    return dto.get("Id") if isinstance(dto, dict) else None


def _edit(client, resource_id, config, ctx):
    ctx = dict(ctx)
    ctx["webhook_id"] = resource_id
    dto = build(config, ctx)
    client.put("/api/Webhooks", dto)
    return client.get(f"/api/Webhooks/{resource_id}")


def _create(client, dto, ctx):
    """Create the webhook. For an AUTO webhook (Type=0) run the listen+capture flow
    the designer uses: create -> get URL -> start listening -> send a request to the
    URL -> capture the data -> stop. (The gateway won't persist Type=0 via REST, so
    the stored webhook is Type=1; AUTO is the capture *method*.) The capture log is
    returned under `_capture`."""
    auto = dto.get("Type") == 0
    body = dict(dto)
    if auto:
        body["Type"] = 1
    resp = client.post("/api/Webhooks", body)
    rid = resp.get("id") if isinstance(resp, dict) and resp.get("id") else dto.get("Id")
    if not auto:
        return resp
    capture = {"method": "AUTO listen+capture", "webhookId": rid,
               "url": f"{config.web_base(client.profile)}/api/Webhooks/launch/{rid}"}
    conn = str(uuid.uuid4())
    listen = {"ConnectionId": conn, "Listen": True, "ListenType": 1, "WebhookId": rid,
              "WebhookName": dto.get("Name"), "HasQuery": dto.get("HasQuery", False),
              "HasHeader": dto.get("HasHeader", False), "HandshakeConfig": None}
    try:
        client.post("/api/Webhooks/listen", listen)        # start listening
        capture["listening"] = True
        sample = dto.get("Definition")                     # send a request to the URL
        client.post(f"/api/Webhooks/launch/{rid}", json.loads(sample) if sample else {})
        capture["sent_sample"] = True
        client.post("/api/Webhooks/listen", {**listen, "Listen": False})  # stop
        capture["captured"] = True
    except Exception as e:  # noqa: BLE001 - the webhook exists either way
        capture["error"] = str(e)[:200]
    out = client.get(f"/api/Webhooks/{rid}")
    if isinstance(out, dict):
        out["_capture"] = capture
    return out


COMPONENT = Component(
    name="webhook",
    description="PROCESIO webhook: an inbound HTTP trigger whose payload is a generated data model.",
    dir=DIR,
    build=build,
    create_endpoint=("POST", "/api/Webhooks"),
    get_path="/api/Webhooks/{id}",
    extract_id=_extract_id,
    prepare_ctx=prepare_ctx,
    create=_create,
    edit=_edit,
)
