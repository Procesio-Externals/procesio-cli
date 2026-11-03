# PROCESIO Public API Reference

This is an exhaustive reference of the **public HTTP API** exposed by the PROCESIO low-code automation platform, plus its realtime (SignalR) channel. It is written so that **another AI can generate applications that use PROCESIO as their backend**, without reading the microservice source.

- **Scope:** every public, externally-reachable endpoint of the **Web-Api gateway** (325 REST endpoints across 14 domains) + the System-Notifications SignalR hub. Internal/inter-service endpoints are listed separately and are explicitly out of scope.
- **Source:** extracted from the PROCESIO Back-End microservice repositories (see [`provenance`](#provenance)). No source was modified.
- **Language/format:** English, Markdown.

> **What is PROCESIO?** A platform where users design *processes* (automation flows) out of *actions*, optionally fed by *forms*, *files*, *data-store tables*, *credentials*, and triggered manually, on a *schedule*, or via *webhooks*. The public API lets your app do everything the PROCESIO UI can: authenticate, manage these resources, **launch processes and read their results**, and receive realtime events.

---

## Start here

1. **[01 — Authentication & Authorization](01-authentication.md)** — how to get a token (or API key), the permission model, workspaces. **Read this first.**
2. **[02 — Conventions](02-conventions.md)** — base URL, headers, `x-version`, error format, type mapping, pagination, async/realtime. **Read this second.**
3. Then jump to the domain you need (table below). To *run an automation* — the most common goal — go straight to **[04 — Processes](endpoints/04-processes.md)**.

---

## Endpoint reference (by domain)

| # | Document | Endpoints | What it covers |
| --- | --- | --- | --- |
| 03 | [Auth, Users, Workspaces, Permissions](endpoints/03-auth-users-workspaces.md) | 52 | Login/SSO/OTP, sign-up, self-service account, user CRUD, workspaces & master workspaces, permissions, preferences |
| 04 | [Processes & Schedules](endpoints/04-processes.md) | 39 | Process templates (designer), **launching & running instances**, instance status/output, debugger, schedules |
| 05 | [Actions](endpoints/05-actions.md) | 21 | Action prototypes/templates/nodes, connector actions, custom-action upload, platform actions, test runs |
| 06 | [Files](endpoints/06-files.md) | 8 | Upload/download of files for flows, connector actions, schedules, test actions (multipart + binary stream) |
| 07 | [Forms](endpoints/07-forms.md) | 64 | Form templates/instances/applications/chains, **anonymous public form submission & flow launch**, form-backed data store rows, document signing (in-app, public form, designer documents) |
| 08 | [Document templates](endpoints/08-documents.md) | 7 | Document templates with placeholder variables, restricted per-instance and per-template reads |
| 09 | [Credentials](endpoints/09-credentials.md) | 21 | Credential vault CRUD, templates, OAuth2 authorization flow, certificate upload |
| 10 | [Data Store](endpoints/10-datastore.md) | 22 | Dynamic tables (schema + **rows query/CRUD**), CSV import/export jobs |
| 11 | [Data Types](endpoints/11-datatypes.md) | 20 | Platform data-type definitions: data models, attributes, cloning, generation from sample content |
| 12 | [Custom URLs & public launch URLs](endpoints/12-custom-urls.md) | 19 | Vanity/short URLs mapping to forms, webhooks, workspaces; **anonymous catch-all launch routes** |
| 13 | [Subscriptions, Resources & Analytics](endpoints/13-subscriptions-resources-analytics.md) | 26 | Billing/subscriptions, quota config, process & execution-environment analytics |
| 14 | [Webhooks](endpoints/14-webhooks.md) | 15 | Webhook CRUD and designer tooling, **anonymous inbound webhook trigger**, payment-provider callbacks |
| 15 | [Notifications, API Keys, Transport](endpoints/15-notifications-apikeys-transport.md) | 11 | Notification inbox, **API-key management**, import/export of platform entities |
| 16 | [Realtime (SignalR hub)](endpoints/16-realtime-signalr.md) | hub | WebSocket connection, `connectionId` model, server→client events for async results |
| 99 | [Internal & other services (appendix)](endpoints/99-internal-and-other-services.md) | — | What is **not** public, and why |

**Total public REST endpoints documented: 325** (+ the SignalR hub).

Each domain file lists, per endpoint: HTTP method + full route, auth mode + required permission, path/query params, special headers, request body DTO (every field with wire name, type, required/optional), responses, and notes. Nested/shared DTOs are defined once per file in a "Shared DTOs" section.

---

## Common recipes

> Replace `{baseUrl}` with your deployment's gateway host (e.g. `https://api.procesio.app`). Send `x-version: 1.19` on every call.

### A. Authenticate
```bash
curl -X POST "{baseUrl}/api/Authentication" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=USER" --data-urlencode "password=PASS"
# → access_token, refresh_token, expires_in
```

### B. Run a process and get the result (one-shot, synchronous)
```bash
# id = the process TEMPLATE id; body = the flow's input variables
curl -X POST "{baseUrl}/api/Projects/{templateId}/run?runSynchronous=true&secondsTimeOut=60" \
  -H "Authorization: Bearer <token>" -H "x-version: 1.19" \
  -H "Content-Type: application/json" \
  -d '{ "payload": { /* input variables */ }, "connectionId": null }'
```
Async variant: omit `runSynchronous` → response is `{ "instanceId": "<guid>" }`, then poll:
```bash
curl "{baseUrl}/api/Projects/instances/{instanceId}/status?flowTemplateId={templateId}" \
  -H "Authorization: Bearer <token>" -H "x-version: 1.19"
```
The two-step path (`publish` → `launch`) and the full input-variable shape are in [04 — Processes](endpoints/04-processes.md).

### C. Trigger a process from an external system (no auth)
```bash
# id = the webhook id configured in PROCESIO; body becomes the trigger payload
curl -X POST "{baseUrl}/api/Webhooks/launch/{webhookId}" \
  -H "Content-Type: application/json" -d '{ "any": "payload" }'
```
Add `?respondOk=true` for a bare 200, or `?payload=<json>` to override the body. See [14](endpoints/14-webhooks.md).

### D. Read/write Data Store rows
- Query: `POST {baseUrl}/api/DataStore/{dataStoreId}/rows/filter?pageNumber=1&pageItemCount=50` with a recursive filter tree in the body:
  ```json
  { "Filter": { "Logic": 1, "Items": [
      { "Type": 1, "Logic": 1, "Condition": { "Column": "Email", "Operator": 1, "Value": "a@example.com" } }
  ] } }
  ```
  Send no body to read every row.
- Insert/update/delete rows are JSON dictionaries keyed by **column display name**. See [10](endpoints/10-datastore.md).

### E. Receive async results in realtime
Connect to the SignalR hub at `{notificationsHost}/hub/notification?userId=<guid>`, invoke `GetConnectionId()`, pass that `connectionId` to connector/test/CSV start endpoints, and handle the server→client events. See [16](endpoints/16-realtime-signalr.md).

---

## Conventions recap (see [02](02-conventions.md) for detail)

- **Auth:** `Authorization: Bearer <jwt>` *or* `key` + `value` headers (API key). Some endpoints are `[AllowAnonymous]` (login, webhook trigger, public forms, custom-URL launch).
- **Version:** `x-version` header, default `1.19`. No version in the URL path.
- **Bodies:** JSON (Newtonsoft) unless noted; auth endpoints use `x-www-form-urlencoded`; uploads use `multipart/form-data` (file part usually named `package`).
- **Workspace:** select with `workspaceId` header or `?targetWorkspace=<guid>`.
- **Errors:** array of `{ statusCode (PROCESIO error code), value (message), target (field) }`; HTTP status carries the category.

---

## Provenance

Generated from the PROCESIO Back-End workspace. Repositories were synced on their default branches before extraction:

The public surface is the **Web-Api** gateway (`api/*` routes, port 8000). The SignalR hub is hosted by **System-Notifications** (`/hub/notification`). Extraction date: 2026-06-24. API version at extraction: **1.19**.

> If PROCESIO's source changes, re-sync the repos (`/be-pull`) and re-run the extraction; the `x-version` value and endpoint set may shift.
