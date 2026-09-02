# Webhook sub-tool

Create/edit a PROCESIO **webhook** — an inbound HTTP trigger. Its payload shape is
a webhook-type data model generated from a sample; attach the webhook to a process
to fire the flow when the URL is called.

## Config

```json
{
  "name": "Order webhook",
  "sample": {"orderId": "abc", "amount": 12.5, "items": ["a", "b"]},
  "type": "manual",
  "hasHeader": false,
  "hasQuery": false,
  "customResponse": {"type": "staticjson", "config": "{\"ok\":true}"}
}
```

- **sample** — a representative payload; the builder calls `generate-data` to infer
  the webhook data model from it (or pass a raw `definition` string).
- **type** — `manual` (1, fires on call — verified) or `auto` (0).
- **customResponse** — optional synchronous response: `staticjson` / `javascript` / `jsonpath`.

## API contract (verified live 2026-06-24)

- **Generate model:** `POST /api/Webhooks/generate-data {Definition}` → `{dataModel, payloadIsList}`
  (the `dataModel` is a webhook-type model, `type:2`).
- **Create:** `POST /api/Webhooks` (`WebhookDto`) — must embed the generated
  `DataModel` + `DataModelId` + `Definition` + `IsEdited:true`, else a generic 502.
- **Get:** `GET /api/Webhooks/{id}`. **Edit:** `PUT /api/Webhooks`. **Delete:** `DELETE /api/Webhooks/{id}`.
- **Trigger (anonymous):** `GET|POST|PUT|PATCH|DELETE /api/Webhooks/launch/{id}`
  (body = payload; `?respondOk=true` for a bare 200). Verified: returns 200.

## Triggering a process

Attach the webhook to a flow via the flow's `Webhooks[]` (`WebhookInstanceDto`),
binding webhook payload fields to the flow's input variables; activate the flow;
then `POST /api/Webhooks/launch/{id}` fires a process instance.

## AUTO vs MANUAL (verified live 2026-06-24)

Per the docs, **AUTO is the listen/capture method**, MANUAL is paste-the-payload:
- **`type:"manual"`** — you supply `sample`; the builder generates the model from it.
- **`type:"auto"`** — the builder runs the designer's flow: create the webhook →
  get its URL → **start listening** → **send the sample to the URL** → capture →
  stop. The `capture` log (`listening/sent_sample/captured`) is returned. The
  webhook is functional (triggers processes) either way.
  - The gateway does **not persist `Type:0`** via REST (`POST` → 502), so the
    stored webhook is `Type:1`; AUTO is the capture *method*, not a stored type.
    The capture step is real (listen + a live request to the URL).

## Custom webhook responses

The custom response is configured **on the process** (per the docs: "Custom
Response: configured within a process; settings persist"): set the flow's
`customResponse` (in `process-create`) to a process variable —
`"customResponse": {"var": "responseVar"}`. **A synchronous run returns this value
directly** (verified: `POST /api/Projects/{id}/run?runSynchronous=true` returns
the `customResponse` value, not the status object), and so does a form's
RUN_PROCESS trigger with `syncRun:true`. It's also stored on the instance
(`GET …/instances/{iid}/customResponse`).
- The webhook **definition**'s `CustomResponseConfig` (static/JS/JSON-path) is
  designer-only (not persisted by REST). The anonymous webhook **launch** fires the
  flow asynchronously, so it doesn't block on the response — that webhook-side
  "respond synchronously" toggle isn't exposed over REST. The custom-response
  *value* mechanism itself is fully working via synchronous run / form trigger.

## Gotchas

- `HasHeader`/`HasQuery` only persist if the data model includes header/query
  sub-models — a body-only sample resets them to false.
