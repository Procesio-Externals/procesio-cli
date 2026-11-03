# Subscriptions / Billing, Resource quotas & Analytics endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Subscriptions/SubscriptionsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Subscriptions/ProcesioAdmin/SubscriptionsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Resources/ResourcesController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Resources/ResourceTrackingConfigController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Resources/ResourcesProcessAnalyticsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Resources/ResourcesProcessInstanceAnalyticsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AnalyticsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/ExecutionEnvironmentAnalyticsController.cs`

This domain covers subscription/billing plan management, resource-usage quotas, per-action analytics configuration, and a family of analytics read endpoints (per-process, per-instance, per-user, and execution-environment concurrency). Every endpoint in these controllers is a **thin proxy** to the downstream **Resource Tracking Service** — the Web-Api gateway validates auth/permissions, then forwards the call and relays the downstream response. As a consequence, success-response bodies are **passthrough payloads** produced by Resource Tracking and are **not statically typed in this service** (managers return generic `CustomResponse` / `ResponseHelper` wrappers whose `.Value` / `ResponseObject` is the downstream JSON, or `IEnumerable<object>`). Where a response body is opaque, this is stated explicitly.

All routes are served under the Web-Api gateway base URL. Versioning is via the optional `x-version` request header (default `1.19`; `CURRENT_API_VERSION = "1.19"`). All controllers declare `[Consumes("application/json")]` and `[Produces("application/json")]`.

Auth note: every controller here requires **Bearer JWT** (none declare `[AllowAnonymous]`). Permissions are `{AuthorizationEntity}:{AuthorizationActionType}` from the controller-level `[AuthorizationEntity(...)]` and method-level `[AuthorizationAction(...)]`. `AuthorizationActionType.None` means authenticated but no specific permission required.

## Endpoints

---

### SubscriptionsController — `api/Subscriptions`

Controller entity: `MasterWorkspace`. Visible in Swagger.

#### `GET api/Subscriptions`

- **Operation:** `GetWorkspaceSubscriptionPlans` — get the current workspace's subscription plans (proxied from Resource Tracking).
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read`
- **Swagger summary:** "Permission required: MasterWorkspace.Read"
- **Responses:**
  - `200 OK` → passthrough array/object of subscription plans (downstream-defined; not typed in this service)
  - `400 Bad Request` → composed error response (`CustomErrorHelper.ComposeResponse`) when downstream returns errors
- **Notes:** Proxy to Resource Tracking Service.

#### `GET api/Subscriptions/{subscriptionId}`

- **Operation:** `GetSubscriptionPlanById` — get a single subscription plan by id.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read`
- **Swagger summary:** "Permission required: MasterWorkspace.Read"
- **Path params:** `{subscriptionId}` — `string (uuid)`, required — the subscription plan id.
- **Responses:**
  - `200 OK` → passthrough subscription plan object (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `POST api/Subscriptions/refund/{id}`

- **Operation:** `RefundSubscription` — start the refund of a subscription plan by its PROCESIO id.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Admin`
- **Swagger summary:** "Permission required: MasterWorkspace.Admin"
- **Path params:** `{id}` — `string (uuid)`, required — subscription plan id to refund.
- **Request body** (`application/json`): `RefundReasonDto`
  - `RefundReason` — `string`, optional — reason for the refund (default `"Other"`).
  - `RefundReasonDetails` — `string`, optional — free-text details (default empty string).
- **Responses:**
  - `200 OK` / `204 No Content` → relayed via `GetResponse` (status + body mirror the downstream `ResponseHelper`)
  - `400 Bad Request` → on null/failed downstream response
- **Notes:** Proxy to Resource Tracking Service. Starts an asynchronous refund flow; acknowledgement is a separate step (see ProcesioAdmin `PUT api/Subscriptions/refund`).

#### `POST api/Subscriptions/renew/{id}/{state}`

- **Operation:** `RenewSubscription` — set the auto-renew state of a subscription plan.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Admin`
- **Swagger summary:** "Permission required: MasterWorkspace.Admin"
- **Path params:**
  - `{id}` — `string (uuid)`, required — subscription plan id.
  - `{state}` — `boolean`, required — `true` to enable auto-renew, `false` to disable.
- **Responses:**
  - `200 OK` / `204 No Content` → relayed via `GetResponse`
  - `400 Bad Request` → on null/failed downstream response
- **Notes:** Proxy to Resource Tracking Service.

---

### SubscriptionsController (ProcesioAdmin) — `api/Subscriptions`

Controller entity: `ProcesioAdmin`. **Hidden from Swagger** (`[ApiExplorerSettings(IgnoreApi = true)]` at controller level) — all methods below inherit this. Each method is also tagged `Tags = ["ProcesioAdmin"]`. Requires PROCESIO admin privileges.

> Note: This controller shares the same `api/Subscriptions` route base as the public `SubscriptionsController` above but exposes different HTTP method/sub-route combinations (POST/PUT/DELETE and `reusable`, `externalReference/...`, `externalOrder/...`, `refund`). All actions require the `ProcesioAdmin` entity.

#### `POST api/Subscriptions`

- **Operation:** `CreateSubscriptionPlan` — create a subscription plan.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes
- **Request body** (`application/json`): `SubscriptionDto`
- **Responses:**
  - `200 OK` → passthrough created-plan payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `PUT api/Subscriptions`

- **Operation:** `UpdateCurrentWorkspaceSubscriptionPlan` — update the current workspace's subscription plan.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Update`
- **Hidden from Swagger:** yes
- **Request body** (`application/json`): `SubscriptionDto`
- **Responses:**
  - `200 OK` → passthrough payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `PUT api/Subscriptions/{subscriptionId}`

- **Operation:** `UpdateSubscriptionPlanById` — update a subscription plan by id.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Update`
- **Hidden from Swagger:** yes
- **Path params:** `{subscriptionId}` — `string (uuid)`, required — plan id to update.
- **Request body** (`application/json`): `BaseSubscriptionDto` (note: the base type, **not** `SubscriptionDto` — no `id`/`workspaceId`/external-reference fields).
- **Responses:**
  - `200 OK` → passthrough payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `DELETE api/Subscriptions`

- **Operation:** `CancelCurrentWorkspaceSubscriptionPlan` — cancel the current workspace's subscription plan.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Delete`
- **Hidden from Swagger:** yes
- **Special headers:** `workspaceIdToDeleteSubscriptions` `[FromHeader]` — `string (uuid)`, required — workspace whose subscriptions are cancelled.
- **Responses:**
  - `200 OK` → passthrough payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `DELETE api/Subscriptions/{subscriptionId}`

- **Operation:** `CancelSubscriptionPlanById` — cancel a subscription plan by id.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Delete`
- **Hidden from Swagger:** yes
- **Path params:** `{subscriptionId}` — `string (uuid)`, required — plan id to cancel.
- **Responses:**
  - `200 OK` → passthrough payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `GET api/Subscriptions/reusable`

- **Operation:** `GetReusableSubscriptionPlans` — get subscription plans that can be reused.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Responses:**
  - `200 OK` → passthrough array of reusable plans (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service. Relates to `SubscriptionOptions.canBeReused`.

#### `GET api/Subscriptions/externalReference/{externalRef}`

- **Operation:** `GetSubscriptionPlanByExternalReference` — get a subscription plan by its external reference.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Path params:** `{externalRef}` — `string`, required — external reference value.
- **Special headers:** `type` `[FromHeader]` — `number` (int), optional, default `2` — external-reference type discriminator.
- **Responses:**
  - `200 OK` → passthrough subscription plan (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `GET api/Subscriptions/externalOrder/{refNo}`

- **Operation:** `GetOrderByRefNo` — fetch an external (Verifone) order by reference number; requests the order from the Verifone server.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Path params:** `{refNo}` — `string`, required — Verifone order reference number.
- **Responses:**
  - `200 OK` → passthrough Verifone order payload (downstream/3rd-party-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service, which in turn calls the external Verifone payment provider.

#### `PUT api/Subscriptions/refund`

- **Operation:** `RefundSubscription` (acknowledge) — acknowledge the refund of a subscription plan by external id. Called only by PROCESIO admins from an internal process.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Update`
- **Hidden from Swagger:** yes
- **Special headers:** `id` `[FromHeader]` — `string`, required — external subscription/refund id to acknowledge.
- **Responses:**
  - `200 OK` / `204 No Content` → relayed via `GetResponse`
  - `400 Bad Request` → on null/failed downstream response
- **Notes:** Proxy to Resource Tracking Service. This is the acknowledgement counterpart to `POST api/Subscriptions/refund/{id}`.

---

### ResourcesController — `api/Resources`

Controller entity: `Workspace`. Visible in Swagger.

#### `GET api/Resources/used`

- **Operation:** `GetMainResources` — get main resource (quota) usage between two dates.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Read`
- **Swagger summary:** "Permission required: Workspace.Read"
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
- **Responses:**
  - `200 OK` → passthrough main-resources usage payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `GET api/Resources/used/subWorkspaces`

- **Operation:** `GetSubWorkspacesUsage` — get usage broken down per sub-workspace between two dates.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Read`
- **Swagger summary:** "Permission required: Workspace.Read"
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
- **Responses:**
  - `200 OK` → passthrough sub-workspaces usage payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

---

### ResourceTrackingConfigController — `api/ResourceTrackingConfig`

Controller entity: `Workspace`. Visible in Swagger. Controls the per-action analytics toggle for the caller's current scope.

#### `GET api/ResourceTrackingConfig`

- **Operation:** `GetConfig` — read the analytics-toggle config for the current scope.
- **Auth:** Bearer JWT — **Permission:** `None` (authenticated, no specific permission required)
- **Swagger summary:** "Permission required: None"
- **Responses:**
  - `200 OK` → passthrough config object (downstream-defined; reflects the analytics enabled/disabled state)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

#### `PUT api/ResourceTrackingConfig/toggle/{enabled}`

- **Operation:** `Toggle` — enable/disable per-action analytics for the current scope.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Admin`
- **Swagger summary:** "Permission required: Workspace.Admin"
- **Path params:** `{enabled}` — `boolean`, required — `true` to enable per-action analytics, `false` to disable.
- **Responses:**
  - `200 OK` / `204 No Content` → relayed via `GetResponse`
  - `400 Bad Request` → on null/failed downstream response
- **Notes:** Proxy to Resource Tracking Service.

---

### ResourcesProcessAnalyticsController — `api/Resources/analytics/processes`

Controller entity: `ProcessDesigner`. Visible in Swagger; methods tagged `Tags = ["Resources"]`.

#### `GET api/Resources/analytics/processes`

- **Operation:** `GetProcesses` — paginated analytics for all processes run between two dates.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Swagger summary:** "Permission required: ProcessDesigner.Read"
- **Query params:**
  - `pageNumber` — `number` (int), required — page number. (See pagination note below.)
  - `pageItemCount` — `number` (int), required — items per page.
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
- **Responses:**
  - `200 OK` → passthrough paged analytics payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service. Params are wrapped into a `Pagination` object (see Shared DTOs) before forwarding. Pagination quirk: `PageNumber` only updates when the supplied value is `> 1` (so both `0` and `1` resolve to page `1`), and `PageItemCount` only updates when `> 0`.

#### `GET api/Resources/analytics/processes/{id}/details`

- **Operation:** `GetProcessDetails` — detailed analytics for one process between two dates (per-action run counts inside the process).
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Swagger summary:** "Permission required: ProcessDesigner.Read"
- **Path params:** `{id}` — `string (uuid)`, required — process id.
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
- **Responses:**
  - `200 OK` → passthrough process-details analytics payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

---

### ResourcesProcessInstanceAnalyticsController — `api/Resources/analytics/instances`

Controller entity: `ProcessInstance`. Visible in Swagger; method tagged `Tags = ["Resources"]`.

#### `GET api/Resources/analytics/instances/{id}/details`

- **Operation:** `GetInstanceDetails` — detailed analytics for one process instance (per-action run counts inside the instance).
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read`
- **Swagger summary:** "Permission required: ProcessInstance.Read"
- **Path params:** `{id}` — `string (uuid)`, required — process instance id.
- **Responses:**
  - `200 OK` → passthrough instance-details analytics payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service.

---

### AnalyticsController — `api/Analytics`

Controller entity: `ProcesioAdmin`. **Hidden from Swagger** (`[ApiExplorerSettings(IgnoreApi = true)]` at controller level) — all methods inherit this. Methods tagged `Tags = ["ProcesioAdmin"]`. Platform-wide (cross-tenant) usage analytics for PROCESIO admins.

#### `GET api/Analytics/user/usage/all`

- **Operation:** `GetAllUserUsage` — get all users' usage between two dates.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
- **Responses:**
  - `200 OK` → array of objects (`IEnumerable<object>`) — untyped usage rows (downstream-defined). Always `200 OK` (no error-wrapping branch in this controller).
- **Notes:** Proxy to Resource Tracking Service / analytics manager.

#### `GET api/Analytics/user/usage/update`

- **Operation:** `UpdateUserUsage` — refresh/recompute the user-usage materialized view for a date range.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Update`
- **Hidden from Swagger:** yes
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
- **Responses:**
  - `200 OK` → `number` (nullable int) — rows affected / null. Always `200 OK`.
- **Notes:** Proxy to analytics manager. Side effect: rebuilds/updates the user-usage view (despite being an HTTP GET).

#### `GET api/Analytics/user/all/activity`

- **Operation:** `GetNewUserActivities` — get new-user activity for a given year/month with a configurable lookback count.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Query params:**
  - `year` — `number` (int), required — target year.
  - `month` — `number` (int), required — target month.
  - `monthActivityCount` — `number` (int), required — number of months of activity to include.
- **Responses:**
  - `200 OK` → array of objects (`IEnumerable<object>`) — untyped activity rows. Always `200 OK`.
- **Notes:** Proxy to analytics manager.

#### `GET api/Analytics/user/Segmentation`

- **Operation:** `GetUserSegmentation` — get user-segmentation analytics.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Responses:**
  - `200 OK` → array of objects (`IEnumerable<object>`) — untyped segmentation rows. Always `200 OK`.
- **Notes:** Proxy to analytics manager. Route casing is `user/Segmentation` (capital S) as declared.

---

### ExecutionEnvironmentAnalyticsController — `api/analytics/executionEnvironment`

Controller entity: `MasterWorkspace`. Visible in Swagger; methods tagged `Tags = ["Resources"]`.

#### `GET api/analytics/executionEnvironment/concurrency`

- **Operation:** `GetExecutionEnvironmentConcurrency` — execution-environment concurrency over time (chart data).
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read`
- **Swagger summary:** "Permission required: MasterWorkspace.Read"
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
  - `statsType` — `string|number (enum EEAnalyticsStatsType: None=0, Max=1, Average=2)`, required — aggregation type for the series.
- **Special headers:**
  - `nrPoints` `[FromHeader]` — `number` (int), required — number of data points to return in the series.
  - `masterWorkspaceId` `[FromHeader]` — `string (uuid)`, required — master workspace id.
  - `workspaceId` `[FromHeader]` — `string (uuid)`, required — workspace id.
- **Responses:**
  - `200 OK` → passthrough concurrency-chart payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service. `masterWorkspaceId`/`workspaceId`/`nrPoints` are passed via headers, not query string.

#### `GET api/analytics/executionEnvironment/topProcesses`

- **Operation:** `GetTopConsumingProcesses` — top execution-environment-consuming processes (with process names) for a date range.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read`
- **Swagger summary:** "Permission required: MasterWorkspace.Read"
- **Query params:**
  - `startDate` — `string (date-time, ISO-8601)`, required — range start.
  - `endDate` — `string (date-time, ISO-8601)`, required — range end.
  - `topCount` — `number` (int), optional, default `10` — number of processes to return.
- **Special headers:**
  - `workspaceId` `[FromHeader]` — `string (uuid)`, required — workspace id.
- **Responses:**
  - `200 OK` → passthrough top-processes payload (downstream-defined)
  - `400 Bad Request` → composed error response
- **Notes:** Proxy to Resource Tracking Service. `workspaceId` is passed via header, not query string.

---

## Shared DTOs

### `RefundReasonDto`

Request body for `POST api/Subscriptions/refund/{id}`. No `[JsonProperty]` overrides — wire names default to the C# property names (Newtonsoft default).

- `RefundReason` — `string`, optional — refund reason; defaults to `"Other"`.
- `RefundReasonDetails` — `string`, optional — free-text details; defaults to empty string.

### `BaseSubscriptionDto`

Base subscription plan payload. Request body for `PUT api/Subscriptions/{subscriptionId}` and base of `SubscriptionDto`. Wire names from `[JsonProperty]`.

- `name` — `string`, optional — plan name (defaults to empty string).
- `parentId` — `string (uuid)`, optional (nullable) — parent plan id.
- `subscriptionPrice` — `number` (float), required — subscription price.
- `discount` — `number` (float), required — discount amount/percentage (interpretation depends on `discountType`).
- `discountType` — `string|number (enum DiscountType: None=0, Percentage=1, Fixed=2)`, required — discount kind.
- `realPrice` — `number` (float), optional (nullable) — real/effective price.
- `currency` — `string`, optional (nullable) — currency code.
- `type` — `string|number (enum LicenseType: None=0, Time=1, Thread=2)`, required — license type (defaults to `Time`). Determines the meaning of `softLimit`/`hardLimit`.
- `softLimit` — `number` (float), required — paid time or paid threads depending on `type`.
- `hardLimit` — `number` (float), required — max limit (0 when `type` is `Thread`).
- `price` — `number` (float), required — overhead price.
- `notifyThreshold` — `number` (float), required — usage threshold at which to notify.
- `refund` — `string|number (enum Refund: None=0, Refundable=1, Refunded=2)`, required — refund state.
- `refundUntil` — `string (date-time, ISO-8601)`, optional (nullable) — refund window end.
- `renew` — `string|number (enum AutoRenew: None=0, AutoRenew=1, Cancel=2)`, required — auto-renew state.
- `options` — `object (SubscriptionOptions)`, optional (nullable) — plan options.
- `startDate` — `string (date-time, ISO-8601)`, required — plan start.
- `endDate` — `string (date-time, ISO-8601)`, required — plan end.

### `SubscriptionDto` (extends `BaseSubscriptionDto`)

Request body for `POST api/Subscriptions` and `PUT api/Subscriptions` (current workspace). Inherits **all** `BaseSubscriptionDto` fields, plus:

- `id` — `string (uuid)`, required — subscription plan id.
- `workspaceId` — `string (uuid)`, optional (nullable) — owning workspace id.
- `externalSubscriptionId` — `string (uuid)`, optional (nullable) — external subscription id.
- `externalReference` — `string`, optional — external reference value.

### `SubscriptionOptions`

Nested in `BaseSubscriptionDto.options`. Wire names from `[JsonProperty]`.

- `canBeReused` — `boolean`, required — whether the plan can be reused (see `GET api/Subscriptions/reusable`).
- `isMultiPack` — `boolean`, required — whether the plan is a multi-pack.

### `Pagination`

Not a wire DTO on these endpoints — `pageNumber` and `pageItemCount` are sent as separate query params and assembled server-side into this object before being forwarded to Resource Tracking. Documented for behavior:

- `PageNumber` — `number` (int) — only assigned when the input is `> 1`; otherwise stays at default `1` (so `0` and `1` both mean page 1).
- `PageItemCount` — `number` (int) — only assigned when the input is `> 0`; otherwise stays at default `0`.
- `StartIndex` — derived: `PageItemCount * (PageNumber - 1)`.

### `EEAnalyticsStatsType` (enum)

Used as the `statsType` query param of `GET api/analytics/executionEnvironment/concurrency`.

- `None` = 0
- `Max` = 1
- `Average` = 2

### Success response bodies (general note)

All "passthrough" responses above are the raw payloads returned by the downstream **Resource Tracking Service**, relayed by the Web-Api manager layer (`CustomResponse.Value` / `ResponseHelper.ResponseObject`). They have **no statically-typed C# model in the Web-Api service**, so exact field shapes must be obtained from the Resource Tracking Service contracts. `400 Bad Request` bodies are produced by `CustomErrorHelper.ComposeResponse(...)` (the gateway's standard composed-error envelope — see conventions doc).
