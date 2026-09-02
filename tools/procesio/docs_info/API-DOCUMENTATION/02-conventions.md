# API conventions

> Shared rules that apply to every Web-Api endpoint in this reference. Read this once; the per-domain files assume it.

---

## 1. Base URL

All paths in this reference are **relative to the Web-Api gateway host** of your PROCESIO deployment:

| Deployment | Example gateway base URL |
| --- | --- |
| PROCESIO public cloud (historical SaaS) | `https://api.procesio.app` |
| On-prem / self-hosted | your install's gateway host (e.g. `https://procesio.your-company.internal`) |
| Local dev | `http://localhost:<port>` (the container binds Kestrel on port `8000`) |

A full request URL is therefore `{baseUrl}` + the route shown, e.g. `https://api.procesio.app/api/Projects`.

> The FE origins allowed by CORS in the reference config are `https://procesio.app`, `https://dev.procesio.app`, `https://qa.procesio.app`, `https://forms.procesio.app` (+ a few customer hosts). Server-to-server clients are not subject to CORS.

There is **no version segment in the path** — see §3.

---

## 2. Standard headers

| Header | Direction | When | Notes |
| --- | --- | --- | --- |
| `Authorization: Bearer <jwt>` | request | JWT auth | See [authentication](01-authentication.md) |
| `key` + `value` | request | API-key auth | Alternative to `Authorization` |
| `x-version` | request | optional | API version selector; defaults to `1.19` |
| `Content-Type` | request | bodies | `application/json` unless an endpoint says `x-www-form-urlencoded` or `multipart/form-data` |
| `workspaceId` / `?targetWorkspace=` | request | optional | Select the active workspace |
| `x-session-expires-at` | response | cookie clients | Refresh-token expiry (epoch) |
| `x-requested-by: playground-v1` | request | SPA only | Marks the official UI/BFF cookie flow |

---

## 3. API versioning

- Versioning uses the **`x-version` request header** (`HeaderApiVersionReader("x-version")`), **not** a URL segment or query string.
- Current/default version is **`1.19`** (`WebApiConstants.CURRENT_API_VERSION`). If the header is omitted the gateway assumes the default (`AssumeDefaultVersionWhenUnspecified = true`).
- The server reports supported versions back via the `api-supported-versions` response header (`ReportApiVersions = true`).
- **Recommendation:** always send `x-version: 1.19` so your client is pinned to a known contract.

---

## 4. Content types & serialization

- Request/response bodies are **JSON** serialized with **Newtonsoft.Json** unless stated otherwise.
- A handful of endpoints use other content types:
  - `application/x-www-form-urlencoded` — the auth endpoints (`api/Authentication/*`).
  - `multipart/form-data` — file/package uploads (file controllers, custom-action & platform-action upload, credential certificate upload, CSV import). The file part name is usually **`package`** (`file` for CSV import); other inputs ride as **request headers**, not form fields. See the relevant domain doc.
  - Binary streams — file/document **downloads** return raw bytes with the stored MIME type and a download filename (not JSON), despite the class-level `[Produces("application/json")]`.
- **Wire field names:** JSON property names follow the C# property unless overridden by `[JsonProperty("...")]` or, for form fields, `[ModelBinder(Name="...")]` / `[FromForm(Name=...)]`. The per-domain docs list the **wire name** for every field.

### C# → JSON type mapping used throughout

| C# type | Wire type |
| --- | --- |
| `Guid` | `string` (uuid) |
| `DateTime` / `DateTimeOffset` | `string` (ISO-8601 date-time) |
| `bool` | `boolean` |
| `int` / `long` / `decimal` / `double` | `number` |
| `string` | `string` |
| `enum` | `number` (the underlying int) — or its name; enums are listed with values per field |
| `List<T>` / `T[]` | `array` of `T` |
| nested class | `object` (defined in that file's **Shared DTOs** section) |
| `object` / `JToken` | free-form JSON (shape not constrained server-side) |

---

## 5. Error responses

Most validation/domain errors return an **array of `ApiErrorResponse`** (`Infrastructure.Core.CustomError.ApiErrorResponse`):

```json
[
  { "statusCode": 1001, "value": "Entity not found.", "target": "id" }
]
```

| Field | Type | Meaning |
| --- | --- | --- |
| `statusCode` | number | A PROCESIO **`ErrorCodes`** enum value (a domain error code) — **not** the HTTP status |
| `value` | string\|object | Human-readable message (resolved from the error-code map) |
| `target` | string\|object | The offending field/property name, when applicable |

Notes:
- The **HTTP status** conveys the category: `400` validation/bad request, `401` unauthenticated, `403` forbidden (insufficient permission), `404` not found *(also returned intentionally for unauthorized `internal/` calls)*, `409` conflict (e.g. CSV job not finished), `413` payload too large (uploads), `415` unsupported media type (webhook/custom-URL body), `500` server error.
- A few endpoints return a **bare exception-message string** instead of the array on unhandled errors — clients should tolerate both shapes on `400`/`500`.
- Anonymous endpoints (forms, custom-URL launch) deliberately apply a small randomized delay (`TimeDelay.RandomWait`) as a timing-attack mitigation.

---

## 6. Pagination, filtering, sorting

There is no single global paging envelope; patterns vary by domain:
- **Common `Pagination` DTO** (subscriptions/resources): `PageNumber` (only applied when > 1), `PageItemCount` (only applied when > 0). See `11-subscriptions-resources-analytics.md`.
- **Data Store rows** use **query-string** filters, not a JSON body: `filters[N].displayName`, `filters[N].operator` (numeric `DataStoreRowsFilterOperator`), `filters[N].value`, plus `sort.displayName` + `sort.direction` (1=Asc, 2=Desc). See `09-datastore-datatypes.md`.
- Many list endpoints expose `searchName`, `count` sibling endpoints, and entity-specific filters — documented inline.

---

## 7. Async operations & realtime

Several operations are **asynchronous**: the HTTP call starts the work and the result is delivered later.
- **Process launch** can be synchronous (`runSynchronous=true`, blocks up to `secondsTimeOut`) or async (returns `{ "instanceId": "<guid>" }`; poll `GET api/Projects/instances/{id}/status`). See `04-processes.md`.
- **Connector/test-action runs and CSV import/export** push their results over **SignalR**. Obtain a `connectionId` from the hub and pass it (body `ConnectionId` or header `connectionId`) to the start endpoint. See `13-realtime-signalr.md`.

---

## 8. Health

- `GET /health` — liveness/readiness (anonymous, bypasses the auth chain). Not part of the business API.
- Prometheus metrics are exposed on a separate port (`9090`, `/metrics`) and are not reachable through the public API path.
