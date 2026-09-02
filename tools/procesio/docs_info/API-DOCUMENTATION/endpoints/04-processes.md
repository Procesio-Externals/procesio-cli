# Processes & Schedules endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Processes/ProcessTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Processes/ProcessInstanceController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Processes/ScheduleProcessesController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Processes/DebuggerController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/SchedulesController.cs`

This is the core of the PROCESIO platform: defining automation **processes** (a.k.a. "projects"/"flows" — a graph of actions with typed input/process/output variables), launching **instances** of them (synchronously or asynchronously), reading instance status/output, debugging a paused instance, and managing **schedules** that launch a process on a recurrence.

Terminology note: in the codebase a "process template" / "project" / "flow" all refer to the **process definition** built in the designer. A "process instance" is one launched run of that definition. The route prefix `api/Projects` is used for both templates and instances.

All endpoints in this file are **public** (none of these controllers are `[SecureInternalController]`; no routes start with `internal/`). All are versioned by the optional `x-version` header (default `1.19`). All accept/produce `application/json` (controller-level `[Consumes("application/json")]` / `[Produces("application/json")]`). No method here is `[AllowAnonymous]`, so every endpoint requires a **Bearer JWT** (or API key via `key`+`value` headers where the gateway supports it).

---

## Launch-a-process flow (most important for app builders)

There are **two** distinct ways a client starts a process, plus a third "publish" step that some clients do first. Read this before the per-endpoint reference.

### Option A — Publish, then Launch (the two-step FE flow)

1. **`POST api/Projects/{id}/instances/publish`** — `{id}` = the **process template (project) id**. Body = an arbitrary JSON payload (the input-variable values). This materializes a new runtime **instance** from the template and returns the created instance (a `FlowResponseDto`; read its `id` — that is the **instance id**).
2. **`POST api/Projects/instances/{id}/launch`** — `{id}` = the **instance id** from step 1. Body = `LaunchFlowPayload` which carries `flowTemplateId` (the template id) and optional `connectionId` (a SignalR/websocket connection id used to push live updates). Query flags:
   - `runSynchronous=true` → the call blocks until the instance reaches a terminal status (or `secondsTimeOut`, default 60s) and returns the **instance status object**.
   - `runSynchronous=false` (default) → returns immediately as `{ "instanceId": "<guid>" }`; poll status separately.
   - `debugMode=true` → launches paused for the debugger. **Cannot** be combined with `runSynchronous=true` (returns 400).

### Option B — Run (single-call convenience)

- **`POST api/Projects/{id}/run`** — `{id}` = the **process template id**. Body = `RunFlowPayload` (`payload` = input-variable values, `connectionId` optional). This creates **and** launches an instance in one call. Same `runSynchronous` / `secondsTimeOut` query semantics as launch. Returns the synchronous status object, or `{ "instanceId": "<guid>" }` when async. This is the simplest entry point for an external app that just wants to fire a process by template id.

### Reading results

- **`GET api/Projects/instances/{id}/status`** — `{id}` = instance id, with `flowTemplateId` query param. Returns the full instance snapshot wrapped as `{ "instance": { ... } }`, including action states, variables, and (optionally) webhook/scheduler/consumed-resource extras. This is how you read output variables and final status of an async run. The instance `status` field is a `FlowStatus` (see Shared DTOs); terminal values are `STATUS_FINISH (50)`, `STATUS_RUNNING_WITH_ERRORS (40)`, `STATUS_STOP_BY_USER (6)`.
- **`POST api/Projects/instances/{id}/stop`** — terminate a running instance.

### How input variables are shaped on the wire

- For **publish** and **run**, the request body is typed as `object` (free-form JSON) in C#. In practice the platform expects the process **payload** shape — the same shape returned by `GET api/Projects/{id}/payload` (the "payload example" endpoint). Call that endpoint on a template to discover the exact JSON keys/structure the process expects, then send those values back. The process's input variables are described by `VariableDto` entries (with `type = INPUT (10)`) on the template; each has a `dataType` (a Guid referencing a data type), `name`, `isList`, `isRequired`, and `defaultValue`.
- For **debugger variable edits** (`PUT api/Debugger/instances/{id}/variables`), the body is a strongly typed `IList<PayloadVariable>` — see `PayloadVariable` in Shared DTOs.

---

## Endpoints

### ProcessTemplateController — `api/Projects` (process definitions / designer)

Controller permission entity: `ProcessDesigner`. Swagger summaries quote the human-readable permission (e.g. `ProcessDesigner.Write`); the derived permission tuple is shown as `Entity:Action`.

---

#### `POST api/Projects`

- **Operation:** `StoreTemplate` — create a new process template (project) from a full flow definition.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Create` (Swagger: "Permission required: ProcessDesigner.Write")
- **Request body** (`application/json`): `FlowRequestDto`
- **Responses:**
  - `200 OK` → empty body on success
  - `400 Bad Request` → validation errors payload (`response.Value`) when the flow fails validation

---

#### `PUT api/Projects`

- **Operation:** `UpdateTemplate` — update an existing process template.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger: "Permission required: ProcessDesigner.Update")
- **Request body** (`application/json`): `FlowRequestDto` (the `id` field identifies the template to update)
- **Responses:**
  - `200 OK` → empty body on success
  - `400 Bad Request` → validation errors payload

---

#### `POST api/Projects/validate`

- **Operation:** `ValidateTemplate` — validate a flow definition without persisting it.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger: "Permission required: ProcessDesigner.Update")
- **Request body** (`application/json`): `FlowRequestDto`
- **Responses:**
  - `200 OK` → empty body when valid
  - `400 Bad Request` → validation errors payload

---

#### `DELETE api/Projects/{id}`

- **Operation:** `RemoveTemplate` — delete a process template by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Delete` (Swagger: "Permission required: ProcessDesigner.Delete")
- **Path params:** `{id}` — `string (uuid)`, required — process template id (`:guid` constrained).
- **Responses:**
  - `200 OK` → empty body on success
  - `400 Bad Request` → composed flow-error response

---

#### `GET api/Projects`

- **Operation:** `GetTemplates` — list process templates with pagination and optional name search.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Query params:**
  - `pageNumber` — `number`, required — page index.
  - `pageItemCount` — `number`, required — page size.
  - `searchName` — `string`, optional, default `null` — name filter; ignored (treated as null) if trimmed length < 3.
- **Responses:**
  - `200 OK` → JSON list/paged result of process templates
  - `400 Bad Request` → not-found error message

---

#### `GET api/Projects/count`

- **Operation:** `CountTemplates` — total count of process templates accessible to the caller.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Responses:**
  - `200 OK` → `number` (count)
  - `400 Bad Request` → not-found error message (when count < 0)

---

#### `GET api/Projects/{id}`

- **Operation:** `GetTemplate` — get a single full process template by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `{ "flow": FlowResponseDto }`
  - `400 Bad Request` → authorization/not-found error payload

---

#### `POST api/Projects/{id}/duplicate`

- **Operation:** `DuplicateTemplate` — create a copy of an existing process template.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Create` (Swagger: "Permission required: ProcessDesigner.Write")
- **Path params:** `{id}` — `string (uuid)`, required — template id to duplicate.
- **Responses:**
  - `200 OK` → `{ "hasWebhook": boolean }` — indicates whether the duplicated process contains a webhook
  - `400 Bad Request` → exception message string

---

#### `GET api/Projects/{id}/payload`

- **Operation:** `GetPayloadExample` — get an example input payload for the process (the JSON shape a client should send when launching/running it).
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Path params:** `{id}` — `string (uuid)`, required — flow (template) id.
- **Responses:**
  - `200 OK` → JSON payload example (free-form object; shape mirrors the process's input variables)
  - `400 Bad Request` → composed flow-error response
- **Notes:** Use this to discover the exact body to pass to `run` / `instances/publish`.

---

#### `GET api/Projects/{id}/used`

- **Operation:** `GetDependencies` — list the parent processes that use (call) this process as a sub-process.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → JSON list of dependent parents
  - `400 Bad Request` → not-found error message

---

#### `PATCH api/Projects/{id}/toggle-activation`

- **Operation:** `ToggleActivation` — enable/disable (activate/deactivate) a process template.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger: "Permission required: ProcessDesigner.Update")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Special headers:** `state` — `boolean`, required `[FromHeader]` — desired active state (true = activate).
- **Responses:**
  - `200 OK` → result object (the manager response)
  - `400 Bad Request` → composed context-error response

---

#### `POST api/Projects/notifications`

- **Operation:** `CreateProcessNotification` — create/update the email-notification settings for a process.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger: "Permission required: ProcessDesigner.Update")
- **Request body** (`application/json`): `NotificationDto` (the `id` field carries the process/notification target id)
- **Responses:**
  - `200 OK` → `response.Value` (stored notification)
  - `400 Bad Request` → composed flow-error response

---

#### `GET api/Projects/notifications/{flowId}`

- **Operation:** `GetProcessNotification` — get the notification settings for a process.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Path params:** `{flowId}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `NotificationDto`
  - `400 Bad Request` → composed flow-error response

---

#### `PATCH api/Projects/{id}/dataRetention`

- **Operation:** `ChangeDataRetentionSettings` — update the data-retention policy for a process template.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger: "Permission required: ProcessDesigner.Update")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Request body** (`application/json`): `DataRetentionPolicyDto`
- **Responses:**
  - `200 OK` → `response.Value`
  - `400 Bad Request` → composed flow-error response

---

### ProcessInstanceController — `api/Projects` (running / launched instances)

Controller permission entity: `ProcessInstance`.

---

#### `GET api/Projects/{id}/instances`

- **Operation:** `GetInstances` — list current runtime instances of a process template, paginated, optionally filtered by status.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
  - `filterStatus` — `array of FlowStatus` (string|number enum), optional — repeat the query key to pass multiple statuses.
- **Responses:**
  - `200 OK` → JSON paged list of instances
  - `400 Bad Request` → not-found error message

---

#### `GET api/Projects/{id}/history`

- **Operation:** `GetHistoryInstances` — list finished/historical instances of a process template (non-archived) within a time window.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
  - `filter` — `ProcessTimeSpanFilterType` (string|number enum), optional, default `Last30Days (5)` — time window.
  - `monthFilter` — `string (date-time, ISO-8601)`, optional — specific month, used with `CertainMonth (14)`.
- **Responses:**
  - `200 OK` → JSON paged list of historical instances
  - `400 Bad Request` → not-found error message

---

#### `GET api/Projects/{id}/archive`

- **Operation:** `GetArchiveInstances` — list archived (Cassandra) historical instances within a time window.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Hidden from Swagger:** yes (`[ApiExplorerSettings(IgnoreApi = true)]`)
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Query params:** same as `/history`: `pageNumber` (required), `pageItemCount` (required), `filter` (`ProcessTimeSpanFilterType`, optional default `Last30Days`), `monthFilter` (`string date-time`, optional).
- **Responses:**
  - `200 OK` → JSON paged list of archived instances
  - `400 Bad Request` → not-found error message

---

#### `GET api/Projects/{id}/instances/count`

- **Operation:** `CountInstances` — count current runtime instances for a process template.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `number` (count)
  - `400 Bad Request` → not-found error message (when count < 0)

---

#### `GET api/Projects/instances/{id}/output`

- **Operation:** `GetInstanceOutput` — get a runtime instance snapshot/output.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id.
- **Query params:** `flowTemplateId` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `{ "instance": { ... } }`
  - `400 Bad Request` → not-found error message
- **Notes:** Marked in code as possibly deprecated / "Not used by FE+BE" (logs a critical "check if in use before removal"). Prefer `instances/{id}/status`. Still reachable.

---

#### `GET api/Projects/instances/{id}/status`

- **Operation:** `GetInstanceStatus` — get the full runtime status snapshot of an instance (status, actions, variables, extras). **Primary endpoint for reading process results.**
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id.
- **Query params:**
  - `flowTemplateId` — `string (uuid)`, required — process template id.
  - `isArchived` — `boolean`, optional, default `false` — read from archive instead of live store.
  - `getActions` — `boolean`, optional, default `true` — include per-action states.
  - `getVariables` — `boolean`, optional, default `true` — include variables (input/process/output values).
  - `getInternalVariables` — `boolean`, optional, default `true` — include internal variables.
  - `addExtras` — `boolean`, optional, default `true` — include webhook/scheduler/consumed-resource extras.
- **Responses:**
  - `200 OK` → `{ "instance": { ... } }` — instance object includes `status` (`FlowStatus`), and (per flags) actions and variables.
  - `400 Bad Request` → not-found error message
- **Notes:** Query options map to `InstanceStatusOptions` server-side. Poll this after an async launch to detect terminal status and read output variables.

---

#### `GET api/Projects/{id}/instances/{instanceId}/customResponse`

- **Operation:** `GetInstanceCustomResponse` — get the process's configured custom response value for an instance.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:**
  - `{id}` — `string (uuid)`, required — process template id.
  - `{instanceId}` — `string (uuid)`, required — process instance id.
- **Query params:** `isArchived` — `boolean`, optional, default `false`.
- **Responses:**
  - `200 OK` → the custom response value (free-form; shape defined by the process's `CustomResponse`)
- **Notes:** Logs a critical "check if in use before removal" but is still reachable.

---

#### `POST api/Projects/{id}/instances/publish`

- **Operation:** `PublishProcess` — materialize a new runtime instance from a process template (step 1 of the publish→launch flow).
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Create` (Swagger: "Permission required: ProcessInstance.Write")
- **Path params:** `{id}` — `string (uuid)`, required — process **template** id.
- **Request body** (`application/json`): `object` — free-form input payload (input-variable values). Use `GET api/Projects/{id}/payload` to discover the expected shape.
- **Responses:**
  - `200 OK` → the created instance (`FlowResponseDto`); read its `id` to get the **instance id** for the subsequent launch
  - `400 Bad Request` → composed flow-error response

---

#### `POST api/Projects/instances/{id}/launch`

- **Operation:** `LaunchInstance` — launch a previously-published instance (step 2 of publish→launch). Supports sync/async and debug modes.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Create` (Swagger: "Permission required: ProcessInstance.Write")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id (from publish).
- **Query params:**
  - `runSynchronous` — `boolean`, optional, default `false` — when true, block until terminal status and return the status object.
  - `debugMode` — `boolean`, optional, default `false` — launch paused for the debugger.
  - `secondsTimeOut` — `number`, optional, default `60` — sync wait timeout in seconds.
- **Request body** (`application/json`): `LaunchFlowPayload`
- **Responses:**
  - `200 OK (async)` → `{ "instanceId": "<guid>" }`
  - `200 OK (sync)` → the instance status object (`instanceStatus.Value`)
  - `400 Bad Request` → `"Launch failed!"`, or `"Launch failed! Cannot run a process in sync mode and debug mode at the same time."` when both `debugMode` and `runSynchronous` are true.
- **Notes:** `debugMode=true` + `runSynchronous=true` is rejected. `connectionId` in the body is the live-updates (SignalR) connection id.

---

#### `POST api/Projects/instances/{id}/stop`

- **Operation:** `StopInstance` — terminate a running process instance.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Update` (Swagger: "Permission required: ProcessInstance.Update")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id.
- **Query params:** `flowTemplateId` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `"Stop process instance is complete."`
  - `400 Bad Request` → `"Stopping process failed."` or exception message

---

#### `POST api/Projects/{id}/run`

- **Operation:** `RunProcess` — create and launch an instance from a template in a single call (convenience entry point).
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Create` (Swagger: "Permission required: ProcessInstance.Write")
- **Path params:** `{id}` — `string (uuid)`, required — process **template** id.
- **Query params:**
  - `runSynchronous` — `boolean`, optional, default `false` — block until terminal status and return it.
  - `secondsTimeOut` — `number`, optional, default `60` — sync wait timeout in seconds.
- **Request body** (`application/json`): `RunFlowPayload`
- **Responses:**
  - `200 OK (async)` → `{ "instanceId": "<guid>" }`
  - `200 OK (sync)` → the instance status object
  - `400 Bad Request` → composed flow-error response, or `"invalid instance"` if the launch did not produce a valid instance
- **Notes:** The `payload` field carries input-variable values (shape per `GET api/Projects/{id}/payload`). `connectionId` is optional (live updates).

---

#### `GET api/Projects/{id}/restricted`

- **Operation:** `GetTemplateForInstance` — get a restricted/limited view of the process template (used to render an instance without full designer access).
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read` (Swagger: "Permission required: ProcessInstance.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `{ "flow": <restricted template> }`
  - `400 Bad Request` → authorization error payload

---

#### `DELETE api/Projects/instances/{id}/dataRetention`

- **Operation:** `DeleteProcessInstanceData` — delete the stored data for a process instance per the retention policy.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Delete` (Swagger: "Permission required: ProcessInstance.Delete")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id.
- **Query params:** `flowTemplateId` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `response.Value`
  - `400 Bad Request` → composed flow-error response or exception message

---

### ScheduleProcessesController — `api/Projects` (restricted template list for scheduling)

Controller permission entity: `Schedule`. Both methods are tagged in Swagger under `ProcessTemplate`.

---

#### `GET api/Projects/restricted/schedules`

- **Operation:** `GetProcessTemplates` — list restricted process templates available to attach to a schedule, paginated.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Read` (Swagger: "Permission required: Schedule.Read")
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
- **Responses:**
  - `200 OK` → JSON paged list of restricted templates
  - `400 Bad Request` → not-found error message

---

#### `GET api/Projects/{id}/restricted/schedules`

- **Operation:** `GetProcessTemplate` — get a single restricted process template by id (for use in scheduling).
- **Auth:** Bearer JWT — **Permission:** `Schedule:Read` (Swagger: "Permission required: Schedule.Read")
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → `{ "flow": <restricted template> }`
  - `400 Bad Request` → authorization error payload

---

### DebuggerController — `api/Debugger`

Controller permission entity: `ProcessInstance`. Used to drive a process instance that was launched with `debugMode=true` (paused at break points).

---

#### `POST api/Debugger/instances/{id}/operation`

- **Operation:** `DebuggerOperation` — run a debugger control operation (resume or step) on a paused instance.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Update` (Swagger: "Permission required: ProcessInstance.Write")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id.
- **Request body** (`application/json`): `DebuggerOperationDto`
- **Responses:**
  - `200 OK` → `"Debugger operation in progress..."`
  - `400 Bad Request` → `"Debugger operation failed!"`

---

#### `PUT api/Debugger/instances/{id}/variables`

- **Operation:** `DebuggerVariables` — update variable values on a paused instance during debugging.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Update` (Swagger: "Permission required: ProcessInstance.Write")
- **Path params:** `{id}` — `string (uuid)`, required — process **instance** id.
- **Request body** (`application/json`): `array of PayloadVariable`
- **Responses:**
  - `200 OK` → JSON of the updated variables (`response`)
  - non-200 → on `HttpResponseException`, returns `ex.Value` with `ex.Status` as the HTTP status code
  - `400 Bad Request` → `"Debugger variables update failed!"`

---

### SchedulesController — `api/Schedules`

Controller permission entity: `Schedule`. The `[controller]` token resolves to `Schedules`. Manages schedules that launch a target process on a recurrence.

---

#### `GET api/Schedules`

- **Operation:** `GetSchedules` — list schedules with pagination and optional name search.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Read` (Swagger: "Permission required: Schedule.Read")
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
  - `searchName` — `string`, optional, default `null` — ignored if trimmed length < 3.
- **Responses:**
  - `200 OK` → JSON paged list of schedules
  - `400 Bad Request` → not-found error message

---

#### `GET api/Schedules/{scheduleId}`

- **Operation:** `GetSchedule` — get a single schedule by id.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Read` (Swagger: "Permission required: Schedule.Read")
- **Path params:** `{scheduleId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → schedule object (`DetailedScheduleDto` shape)
  - `400 Bad Request` → authorization error payload

---

#### `DELETE api/Schedules/{scheduleId}`

- **Operation:** `DeleteSchedules` — delete a schedule by id.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Delete` (Swagger: "Permission required: Schedule.Delete")
- **Path params:** `{scheduleId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `"Deleted schedule with id <scheduleId>"`
  - `400 Bad Request` → composed schedules-error response

---

#### `POST api/Schedules`

- **Operation:** `CreateSchedule` — create a schedule that launches a target process on a recurrence.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Create` (Swagger: "Permission required: Schedule.Write")
- **Request body** (`application/json`): `DetailedScheduleDto`
- **Responses:**
  - `200 OK` → created schedule (`response.Value`)
  - `400 Bad Request` → composed schedules-error response

---

#### `PUT api/Schedules`

- **Operation:** `UpdateSchedule` — update an existing schedule.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Update` (Swagger: "Permission required: Schedule.Update")
- **Request body** (`application/json`): `DetailedScheduleDto` (the `id` field identifies the schedule)
- **Responses:**
  - `200 OK` → updated schedule (`response.Value`)
  - `400 Bad Request` → composed schedules-error response

---

#### `PATCH api/Schedules/{scheduleId}/status`

- **Operation:** `SetScheduleStatus` — enable or disable a schedule.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Update` (Swagger: "Permission required: Schedule.Update")
- **Path params:** `{scheduleId}` — `string (uuid)`, required.
- **Query params:** `enable` — `boolean`, required — true = enable, false = disable.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → composed schedules-error response

---

#### `POST api/Schedules/notifications`

- **Operation:** `CreateScheduleNotification` — create/update email-notification settings for a schedule.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Update` (Swagger: "Permission required: Schedule.Update")
- **Request body** (`application/json`): `NotificationDto` (the `id` field carries the schedule id)
- **Responses:**
  - `200 OK` → `response.Value`
  - `400 Bad Request` → composed flow-error response

---

#### `GET api/Schedules/notifications/{scheduleId}`

- **Operation:** `GetScheduleNotification` — get the notification settings for a schedule.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Read` (Swagger: "Permission required: Schedule.Read")
- **Path params:** `{scheduleId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `NotificationDto`
  - `400 Bad Request` → composed flow-error response

---

## Shared DTOs

### `LaunchFlowPayload`

Request body for `POST api/Projects/instances/{id}/launch`. Uses `System.Text.Json` attribute names.

| wire field | type | req | description |
|---|---|---|---|
| `connectionId` | `string` | optional | Live-updates (SignalR) connection id to receive push updates; may be null/empty. |
| `flowTemplateId` | `string (uuid)` | required | The process template id the instance belongs to. |

### `RunFlowPayload`

Request body for `POST api/Projects/{id}/run`. No JSON attributes → Newtonsoft default names (PascalCase property names serialized as-is unless global camelCase is configured; treat as `Payload` / `ConnectionId`).

| wire field | type | req | description |
|---|---|---|---|
| `Payload` | `object` (free-form JSON) | optional | Input-variable values for the process. Shape mirrors `GET api/Projects/{id}/payload`. |
| `ConnectionId` | `string` | optional | Live-updates (SignalR) connection id. |

### `FlowRequestDto`

Request body for `StoreTemplate`, `UpdateTemplate`, `ValidateTemplate`. Extends `BaseFlowDto` (inherits all its fields + the `OwnershipAuditDto` audit fields). Adds:

| wire field | type | req | description |
|---|---|---|---|
| `Variables` | `array of VariableDto` | optional | Process variables (input/process/output). |
| `Actions` | `array of ActionDto` | optional | Action nodes of the flow. |
| `Webhooks` | `array of WebhookInstanceDto` | optional | Webhook triggers attached to the flow. |
| `CustomResponse` | `object (CustomResponseDto)` | optional | Custom synchronous response definition. |
| `DataRetention` | `object (DataRetentionPolicyDto)` | optional | Data-retention policy. |
| `CanvasData` | `object` (raw JSON token) | optional | Designer canvas layout (opaque). |

### `FlowResponseDto`

Returned by `GetTemplate` (wrapped as `{ "flow": ... }`) and as the published-instance result of `PublishProcess`. Extends `BaseFlowDto`. Fields:

| wire field | type | description |
|---|---|---|
| `Variables` | `array of VariableDto` | Process variables. |
| `Actions` | `array of ActionDto` | Action nodes. |
| `Webhooks` | `array of WebhookInstanceDto` | Webhook triggers. |
| `CustomResponse` | `object (CustomResponseDto)` | Custom response definition. |
| `ParentFlow` | `object (ParentFlowDto)` | Parent flow linkage (defaults to empty object). |
| `DataRetention` | `object (DataRetentionPolicyDto)` | Data-retention policy. |
| `CanvasData` | `object` (raw JSON token) | Designer canvas layout. |
| *(plus all `BaseFlowDto` + `OwnershipAuditDto` fields)* | | |

### `BaseFlowDto`

Base for `FlowRequestDto` / `FlowResponseDto`. Extends `OwnershipAuditDto`.

| wire field | type | req | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required(value type) | Flow id (template id, or instance id on instance responses). |
| `ParentId` | `string (uuid)` | optional | Parent flow id; null by default. |
| `Status` | `FlowStatus` (string|number enum) | required(value type) | Current status. |
| `Title` | `string` | optional | Process title. |
| `Description` | `string` | optional | Process description. |
| `IsValid` | `boolean` | required(value type) | Whether the flow passed validation. |
| `Active` | `boolean` | required(value type) | Whether the template is active. |
| `Timeout` | `number` | required(value type) | Execution timeout. |
| `CurrentActionId` | `string (uuid)` | optional | Currently executing action (instances). |
| `DebugMode` | `boolean` | required(value type) | Whether launched in debug mode. |
| `IsNotification` | `boolean` | optional (default false) | Notification flag. |

### `OwnershipAuditDto`

Audit fields inherited by `BaseFlowDto` and `BaseScheduleDto`. Uses Newtonsoft `[JsonProperty]` names.

| wire field | type | description |
|---|---|---|
| `firstName` | `string` | (legacy) creator first name. |
| `lastName` | `string` | (legacy) creator last name. |
| `workspaceId` | `string (uuid)` (nullable) | Owning workspace. |
| `createdBy` | `string` | "FirstName LastName" of creator. |
| `updatedBy` | `string` | "FirstName LastName" of last updater. |
| `createdById` | `string (uuid)` (nullable) | Creator user id. |
| `updatedById` | `string (uuid)` (nullable) | Updater user id. |
| `createdOn` | `string (date-time, ISO-8601)` (nullable) | Created timestamp. |
| `updatedOn` | `string (date-time, ISO-8601)` (nullable) | Updated timestamp. |

### `VariableDto`

A process variable (input/process/output).

| wire field | type | req | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required(value type) | Variable id. |
| `ContextId` | `string (uuid)` | optional | Context id. |
| `DataType` | `string (uuid)` | required(value type) | References a data-type definition (Guid). |
| `Type` | `VariableOrientation` (string|number enum) | required(value type) | INPUT / PROCESS / OUTPUT. |
| `Name` | `string` | optional | Variable name (the JSON key clients use in the payload). |
| `DefaultValue` | `object` | optional | Default value (any JSON). |
| `IsList` | `boolean` | required(value type) | Whether the variable is a collection. |
| `IsError` | `boolean` | required(value type) | Whether it is an error variable. |
| `IsRequired` | `boolean` | optional (default false) | Whether a value is required at launch. |

### `ActionDto`

An action node in the flow (designer-level; relevant mainly for template authoring).

| wire field | type | description |
|---|---|---|
| `Id` | `string (uuid)` | Action id. |
| `FlowId` | `string (uuid)` | Owning flow id. |
| `TemplateId` | `string (uuid)` | Action template id. |
| `ParentId` | `string (uuid)` (nullable) | Parent action id. |
| `VariableErrorId` | `string (uuid)` (nullable) | Error-variable id. |
| `Status` | `ActionStatus` (string|number enum) | Action runtime status. |
| `Category` | `string` | Action category. |
| `ActionName` | `string` | Display name. |
| `ActionTemplateName` | `string` | Underlying template name. |
| `Ports` | `array of PortDto` | Connections to other actions. |
| `Parameters` | `array of ParametersDto` | Configured parameters. |
| `CustomData` | `object` | Opaque per-action data. |
| `IsTestable` | `boolean` | Whether the action supports test runs. |
| `IsDisabled` | `boolean` | Whether the action is disabled. |
| `BreakPoint` | `object (BreakPointDto)` | Debugger break point. |
| `TestValues` | `object` | Test input values. |
| `ErrorMessage` | `string` | Last error message. |
| `Events` | `array of PropertyEventDto` (nullable) | Dynamic connector events. |

### `PortDto`

| wire field | type | description |
|---|---|---|
| `Id` | `string (uuid)` | Port id. |
| `FlowId` | `string (uuid)` | Owning flow. |
| `SourceId` | `string (uuid)` | Source action. |
| `DestinationId` | `string (uuid)` | Destination action. |
| `Type` | `number` | Port type. |
| `State` | `number` | Port state. |
| `Data` | `object` | Opaque port data. |
| `Errors` | `object` | Opaque errors. |
| `Config` | `object` (map of `string`→`number`) | Port config dictionary. |

### `ParametersDto`

| wire field | type | description |
|---|---|---|
| `TabPropertyId` | `string (uuid)` | Parameter/tab property id. |
| `Variable` | `array of ParameterVariableDto` | Bound variables. |
| `Value` | `object` | Configured value. |

### `ParameterVariableDto`

Newtonsoft `[JsonProperty]` names.

| wire field | type | description |
|---|---|---|
| `id` | `number` | Numeric id. |
| `variableId` | `string (uuid)` (nullable) | Bound process-variable id. |
| `attribute` | `object (VariableAttributeDto)` | Attribute path. |

### `VariableAttributeDto`

Recursive attribute path. Newtonsoft `[JsonProperty]` names.

| wire field | type | description |
|---|---|---|
| `attributeId` | `string (uuid)` | Attribute id. |
| `nextAttribute` | `object (VariableAttributeDto)` | Next attribute in the chain (recursive; null-terminated). |

### `BreakPointDto`

| wire field | type | description |
|---|---|---|
| `Enabled` | `boolean` | Whether the break point is enabled. |

### `PropertyEventDto`

Dynamic connector event metadata. Newtonsoft `[JsonProperty]` names.

| wire field | type | description |
|---|---|---|
| `type` | `number` | Event type. |
| `inputs` | `array of string (uuid)` (nullable) | Property ids used as connector inputs. |
| `outputs` | `array of string (uuid)` (nullable) | Property ids produced as connector outputs. |
| `outputTarget` | `OutputTarget` (string|number enum) (nullable) | Target output type. **DTO not resolved: `OutputTarget`** — defined in external NuGet `Ringhel.Procesio.Action.Core.Utils`, not in this repo. |

### `WebhookInstanceDto`

| wire field | type | description |
|---|---|---|
| `Id` | `string (uuid)` | Webhook instance id. |
| `WebhookId` | `string (uuid)` | Webhook definition id. |
| `WebhookVariables` | `array of WebhookVariableDto` | Variable bindings. |
| `IsObsoleted` | `boolean` | Whether the event is obsoleted. |
| `FilterRules` | `object (WebhookRulesDto)` | Filter rules. |

### `WebhookVariableDto`

| wire field | type | description |
|---|---|---|
| `VariableId` | `string (uuid)` | Process-variable id. |
| `VariableType` | `WebhookVariableType` (string|number enum) | Source of the value: Header / Query / Body. |

### `WebhookRulesDto`

| wire field | type | description |
|---|---|---|
| `Value` | `object` | Rule value (opaque). |
| `Parameters` | `array of WebhookEventRulesDto` | Decision conditions. |

`WebhookEventRulesDto` extends `DecisionCondition` (in `Domain.Models.Webhooks`). **DTO not fully resolved: `DecisionCondition`** — designer-internal decision-rule model; not expanded here (not needed for launching processes).

### `CustomResponseDto`

| wire field | type | description |
|---|---|---|
| `Variable` | `object (ParameterVariableDto)` | The variable whose value is returned as the custom response. |
| `Value` | `object` | Static/override value. |

### `ParentFlowDto`

| wire field | type | description |
|---|---|---|
| `ParentId` | `string (uuid)` | Parent flow instance id. |
| `FlowTemplateId` | `string (uuid)` | Parent flow template id. |
| `ActionId` | `string (uuid)` | Action that triggered the child flow. |

### `DataRetentionPolicyDto`

Newtonsoft `[JsonProperty]` names. Used by `ChangeDataRetentionSettings` and embedded in flow DTOs.

| wire field | type | req | description |
|---|---|---|---|
| `deleteOnSuccess` | `FlowDataRetentionType` (string|number enum) | required(value type) | Retention when the run succeeds. |
| `deleteOnError` | `FlowDataRetentionType` (string|number enum) | required(value type) | Retention when the run errors. |
| `deleteOnStopped` | `FlowDataRetentionType` (string|number enum) | required(value type) | Retention when stopped by user. |

### `NotificationDto`

Request/response body for process and schedule notification endpoints.

| wire field | type | req | description |
|---|---|---|---|
| `Id` | `string (uuid)` (nullable) | optional | Target id (process or schedule). |
| `EmailList` | `string` | optional (default `""`) | Comma/semicolon-separated recipient emails. |
| `IsEnabled` | `boolean` | optional (default false) | Whether notifications are enabled. |
| `OnSuccess` | `boolean` | optional (default true) | Notify on success. |
| `OnFail` | `boolean` | optional (default true) | Notify on failure. |

### `PayloadVariable`

Request body element for `PUT api/Debugger/instances/{id}/variables` (sent as an array). Newtonsoft default names except `nextAttribute`.

| wire field | type | req | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required(value type) | Variable id to update. |
| `Value` | `object` | optional | New value (any JSON). |
| `nextAttribute` | `object (VariableAttribute)` | optional | Attribute path for nested/structured values (recursive; same shape as `VariableAttributeDto`: `attributeId` + `nextAttribute`). |

### `DebuggerOperationDto`

Request body for `POST api/Debugger/instances/{id}/operation`.

| wire field | type | req | description |
|---|---|---|---|
| `DebuggerActionType` | `DebuggerOperationType` (string|number enum) | required(value type) | RESUME or STEP. |
| `ConnectionId` | `string` | optional | Live-updates (SignalR) connection id. |

### `DetailedScheduleDto`

Request body for `CreateSchedule` / `UpdateSchedule`; also the read shape of a schedule. Extends `BaseScheduleDto` (which extends `OwnershipAuditDto`).

| wire field | type | req | description |
|---|---|---|---|
| `TargetProcess` | `string (uuid)` | required(value type) | The process template launched by this schedule. |
| `Description` | `string` | optional | Schedule description. |
| `Notification` | `object (NotificationDto)` | optional | Email-notification settings. |
| `ProcessInputs` | `array of ScheduleVariableDto` | optional | Input-variable values passed to the process on each run. |
| `Recurrence` | `object` (free-form JSON) | optional | Recurrence rule. Typed as `object` server-side — opaque structure (cron-like / interval definition); shape not constrained at the controller. |
| *(plus `BaseScheduleDto` + `OwnershipAuditDto` fields)* | | | |

### `BaseScheduleDto`

| wire field | type | req | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required(value type) | Schedule id. |
| `Name` | `string` | optional | Schedule name. |
| `Status` | `boolean` | required(value type) | Enabled/disabled. |
| *(plus `OwnershipAuditDto` fields)* | | | |

### `ScheduleVariableDto`

One input-variable value for a scheduled run.

| wire field | type | req | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required(value type) | Variable id. |
| `Value` | `object` | optional | Value to inject (any JSON). |

---

## Shared enums

### `FlowStatus` (number-valued)

| name | value | meaning |
|---|---|---|
| `STATUS_NONE` | 1 | None. |
| `INACTIVE` | 5 | Flow inactive (used for filtering). |
| `STATUS_STOP_BY_USER` | 6 | Terminated by the user. |
| `STATUS_INITIALIZING` | 15 | Initializing. |
| `STATUS_DISPATCHED_ACTIONS` | 20 | Actions dispatched (state-machine only; not persisted). |
| `STATUS_RUNNING` | 30 | Running. |
| `STATUS_RUNNING_WITH_ERRORS` | 40 | Finished/running with errors. |
| `BREAK_POINT` | 45 | Paused at a debugger break point. |
| `STATUS_FINISH` | 50 | Finished successfully. |
| `STATUS_TEMPORARY_WAITING` | 60 | Transient waiting (state-machine only). |

### `ProcessTimeSpanFilterType` (number-valued)

`LastHour`=1, `Last24Hours`=2, `Last3Days`=3, `Last7Days`=4, `Last30Days`=5 (default), `ThisMonth`=6, `ThisQuarter`=7, `ThisYear`=8, `LastMonth`=9, `LastQuarter`=10, `Last3Months`=11, `Last6Months`=12, `LastYear`=13, `CertainMonth`=14 (used with `monthFilter`).

### `DebuggerOperationType` (number-valued)

| name | value | meaning |
|---|---|---|
| `RESUME` | 0 | Resume the flow. |
| `STEP` | 1 | Step to the next action. |

### `VariableOrientation` (number-valued)

| name | value | meaning |
|---|---|---|
| `INPUT` | 10 | Input variable. |
| `PROCESS` | 20 | Internal/process variable. |
| `OUTPUT` | 30 | Output variable. |

### `FlowDataRetentionType` (number-valued)

| name | value | meaning |
|---|---|---|
| `Never` | 0 | Never auto-delete. |
| `AtEndOfRuntime` | 1 | Delete when the run ends. |
| `AtMoveToHistory` | 2 | Delete when moved to history. |

### `WebhookVariableType` (number-valued)

| name | value | meaning |
|---|---|---|
| `Header` | 1 | Value sourced from a request header. |
| `Query` | 2 | Value sourced from a query parameter. |
| `Body` | 3 | Value sourced from the request body. |

### `ActionStatus` (number-valued)

`NONE`=1, `STARTING`=10, `INPUT_DONE`=15, `EXECUTED`=20, `FOREACH_ITERATION_DONE`=30, `CALL_SUBPROCESS_CHILD_STARTED`=35, `CALL_SUBPROCESS_CHILD_FINISHED`=36, `OUTPUT_DONE`=40, `ERROR`=90.
