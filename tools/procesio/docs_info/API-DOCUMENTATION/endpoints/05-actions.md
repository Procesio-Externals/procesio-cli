# Actions endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ActionInfoController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ActionNodeController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ActionPrototypeController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ActionTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ConnectorActionController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/CustomActionController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ProcessInstanceActionTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/TestActionController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Actions/ProcesioAdmin/PlatformActionController.cs`

**Actions** are the building blocks placed inside PROCESIO processes. This domain covers the catalog of available **action templates** (the predefined operations a designer can drop onto a flow), the **action node tree** (folders that organize templates and prototypes), **action prototypes** (user-saved action presets, a.k.a. "user templates"), **custom actions** (user-uploaded NuGet packages that introduce new action types), and the **test/connector execution** endpoints that let the designer run a single action standalone (outside a flow) for previewing connector results. It also exposes static design-time metadata such as the decisional-matrix operator catalog.

All controllers are public (none carry `[SecureInternalController]`, none use an `internal/` route). Every method requires a Bearer JWT — there are no `[AllowAnonymous]` methods. Most controllers share the route prefix `api/Actions`; the ProcesioAdmin uploader uses `api/PlatformAction`.

Permission strings are derived from the controller-level `[AuthorizationEntity(...)]` and method-level `[AuthorizationAction(...)]`. Note that several `SwaggerOperation` summaries say "ProcessDesigner.Write" while the actual attribute is `AuthorizationActionType.Create` — both are reported below; the attribute is authoritative.

---

## Endpoints

### ActionInfoController (`api/Actions`)

Entity: `ProcessDesigner`.

#### `GET api/Actions/decisional/operators`

- **Operation:** `GetDecisionalMatrixRules` — returns the static catalog of operators usable in a decisional matrix / condition action (operator name, type, icon, operand rules, and the data types each operator supports). Sourced from configured options (`DecisionMatrix`), not the database.
- **Auth:** Bearer JWT — **Permission:** `None` (authenticated, no specific permission)
- **Hidden from Swagger:** yes (`[ApiExplorerSettings(IgnoreApi = true)]`)
- **Responses:**
  - `200 OK` → array of `DecisionMatrixRule`
  - `400 Bad Request` → empty body when the matrix-rules list is null or empty

---

### ActionNodeController (`api/Actions`)

Entity: `ProcessDesigner`. Manages the action-node folder tree (organizational folders in the action catalog). In the JSON these endpoints use the `folders` sub-route.

#### `GET api/Actions/folders/{id}`

- **Operation:** `GetNode` — get a single action node (folder) by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger: "Permission required: ProcessDesigner.Read")
- **Path params:** `{id}` — `string (uuid)`, required — node id.
- **Responses:**
  - `200 OK` → a result object wrapping the node (the manager returns a `Result`-style envelope; on success the node payload, see Notes).
  - `400 Bad Request` → `ErrorResponse` (composed action errors) when the manager returns errors.
- **Notes:** On success the controller serializes the whole manager response object (`new JsonResult(response)`), which is a result wrapper containing the node value plus an (empty) errors collection. Treat the node shape as `ActionNodeDto`.

#### `GET api/Actions/folders`

- **Operation:** `GetNodes` — get all action nodes (the full folder tree).
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Responses:**
  - `200 OK` → array of `ActionNodeDto` (tree; children nested via the `children` field)
  - `400 Bad Request` → `ErrorResponse` (not-found message) when null.

#### `POST api/Actions/folders`

- **Operation:** `StoreNode` — create a new action node (folder).
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Create` (Swagger says "ProcessDesigner.Write")
- **Request body** (`application/json`): `SimpleActionNodeDto`
  - `nodeId` — `string (uuid)`, optional — unique node id (inherited from `BaseActionNodeDto`).
  - `name` — `string`, optional — folder name (inherited).
  - `parentId` — `string (uuid)`, optional — parent node id.
  - `id` — `string (uuid)`, optional — id of the element, or null if it is a node/folder.
  - `order` — `number`, required — order index within the parent.
- **Responses:**
  - `200 OK` → the created node value (`response.Value`).
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.

#### `PATCH api/Actions/folders/rename`

- **Operation:** `UpdateNodeName` — rename an action node.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update`
- **Request body** (`application/json`): `BaseActionNodeDto`
  - `nodeId` — `string (uuid)`, optional — id of the node to rename.
  - `name` — `string`, optional — new name.
- **Responses:**
  - `200 OK` → empty body.
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.

#### `DELETE api/Actions/folders/{id}`

- **Operation:** `RemoveNode` — delete an action node (folder) by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — node id.
- **Responses:**
  - `200 OK` → empty body.
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.

---

### ActionPrototypeController (`api/Actions`)

Entity: `ProcessDesigner`. Manages action prototypes (user-saved action presets, a.k.a. "user templates"). In the JSON these use the `templates` sub-route.

#### `GET api/Actions/templates/{id}`

- **Operation:** `GetPrototype` — get a single action prototype by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Path params:** `{id}` — `string (uuid)`, required — prototype id.
- **Responses:**
  - `200 OK` → `ActionPrototypeDto` (`response.Value`).
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.

#### `POST api/Actions/templates`

- **Operation:** `StorePrototype` — create a new action prototype.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Create`
- **Hidden from Swagger:** yes (`[ApiExplorerSettings(IgnoreApi = true)]`)
- **Request body** (`application/json`): `ActionPrototypeDto`
- **Responses:**
  - `200 OK` → the created prototype value (`response.Value`).
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.

#### `DELETE api/Actions/templates/{id}`

- **Operation:** `RemovePrototype` — delete an action prototype by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — prototype id.
- **Responses:**
  - `200 OK` → empty body.
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.

---

### ActionTemplateController (`api/Actions`)

Entity: `ProcessDesigner`. Read access to the action-template catalog (the predefined actions a designer can use).

#### `GET api/Actions/{id}`

- **Operation:** `GetAction` — get a single full action template (with tabs/properties) by id.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Path params:** `{id}` — `string (uuid)`, required — action template id.
- **Responses:**
  - `200 OK` → `DetailedActionTemplateDto` (or `null`/`204`-style null body if not found).

#### `GET api/Actions`

- **Operation:** `GetActions` — get all action templates, optionally filtered by name and optionally including full configuration.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Query params:**
  - `actionFilter` — `string`, optional, default `null` — name search filter.
  - `getFullAction` — `boolean`, optional, default `false` — when `true`, returns full templates (tabs/properties); when `false`, returns simple templates.
- **Responses:**
  - `200 OK` → grouping object: `DetailedActionGroupingDto` when `getFullAction=true`, else `SimpleActionGroupingDto`. When no templates match and no filter is supplied, an empty array `[]` is returned instead of a grouping object.
  - `400 Bad Request` → `ErrorResponse` (not-found message) when the manager returns null.
- **Notes:** Response shape is polymorphic — either a grouping object (`{ grouping, prototypes, actions }`) or a bare empty array. Clients should handle both.

#### `GET api/Actions/category/{category}`

- **Operation:** `GetActionsByCategory` — get all action templates within a category.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Path params:** `{category}` — `string`, required — category name.
- **Query params:**
  - `getFullAction` — `boolean`, optional, default `false` — full vs. simple templates.
- **Responses:**
  - `200 OK` → `DetailedActionGroupingDto` or `SimpleActionGroupingDto` (see `GetActions`), or empty array.
  - `400 Bad Request` → `ErrorResponse` when null.

#### `GET api/Actions/node`

- **Operation:** `GetActionsByNode` — get the custom/template/prototype actions under an action node (folder), or all custom actions.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Query params:**
  - `getFullAction` — `boolean`, optional, default `true` (defaults to `true` when omitted) — full vs. simple templates.
  - `isCustom` — `boolean`, optional, default `false` — when `true`, returns custom actions instead of templates under the node.
- **Special headers:** `id` — `string (uuid)`, optional `[FromHeader]` — the parent action-node id. When omitted, returns root-level items.
- **Responses:**
  - `200 OK` → inline object `{ "actions": [...], "prototypes": [ActionPrototypeDto] }`. Each entry in `actions` is a `DetailedActionTemplateDto` (when `getFullAction=true`) or `SimpleActionTemplateDto` (when `false`).
- **Notes:** The node id is passed as an HTTP header named `id`, not a query/route param.

---

### ProcessInstanceActionTemplateController (`api/Actions`)

Entity: `ProcessInstance`. A restricted, instance-scoped view of the action catalog (e.g. for run-time/process-instance consumers that have ProcessInstance permission rather than ProcessDesigner).

#### `GET api/Actions/restricted`

- **Operation:** `GetSimpleActions` — get all action templates in simple form (never full), optionally name-filtered.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read`
- **Query params:**
  - `actionFilter` — `string`, optional, default `null` — name search filter.
- **Responses:**
  - `200 OK` → `SimpleActionGroupingDto` (always simple — `getFullAction` is forced to `false`), or empty array `[]` when no matches and no filter.
  - `400 Bad Request` → `ErrorResponse` (not-found message) when null.

---

### ConnectorActionController (`api/Actions`)

Entity: `ProcessDesigner`. Executes a connector action standalone (used by the designer to trigger a connector property/event and fetch results, e.g. populating dynamic dropdowns). Results are produced asynchronously and pushed over SignalR; a polling GET is also provided.

#### `POST api/Actions/event`

- **Operation:** `ExecuteConnectorAction` — execute a connector action / connector property event.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update`
- **Request body** (`application/json`): `ConnectorActionRequestDto`
  - `Gid` — `string (uuid)`, required — connector action id.
  - `Gtid` — `string (uuid)`, required — action template id.
  - `Trigger` — `string (uuid)`, optional — id of the property triggering the connector execution.
  - `EventType` — `number`, required — `ControlEventType` if `Trigger` is present, otherwise `ActionEventType` (action-level event).
  - `Variables` — array of `VariableDto`, optional (defaults to empty) — variables used by the connector action.
  - `Parameters` — array of `ParametersDto`, optional (defaults to empty) — parameters used by the connector action.
  - `ConnectionId` — `string`, optional — SignalR connection id to receive async results.
- **Responses:**
  - `200 OK` → `ConnectorActionResponseDto` (the queued/initial execution record).
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.
- **Notes:** Wire field names are PascalCase (no `[JsonProperty]` overrides on this DTO; Newtonsoft default keeps the C# names as-is). Execution is asynchronous — final results arrive via SignalR (using `ConnectionId`) and/or by polling the GET below.

#### `GET api/Actions/event/{id}`

- **Operation:** `GetConnectorActionResults` — fetch the results of a previously executed connector action.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update`
- **Path params:** `{id}` — `string (uuid)`, required — connector action id (the `Gid`).
- **Responses:**
  - `200 OK` → `ConnectorActionResponseDto`.
  - `400 Bad Request` → `ErrorResponse` (not-found message) when null.

---

### TestActionController (`api/Actions`)

Entity: `ProcessDesigner`. Runs a single action standalone ("test action") outside any flow, with caller-supplied test values, and returns its output. Like connectors, execution is async with SignalR delivery plus a polling GET.

#### `POST api/Actions/test`

- **Operation:** `ExecuteTestAction` — execute a single action in test mode.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update`
- **Request body** (`application/json`): `DetailedTestActionRequestDto`
  - `variables` — array of `VariableDto`, optional — variables (inherited from `BaseTestActionDto`).
  - `Gid` — `string (uuid)`, required — id of the action instance being tested.
  - `TestValues` — array of `ActionAttributeDto`, optional — values to feed the action under test.
  - `Action` — `object (TestActionDto)`, optional — the action being tested (template id + parameters).
  - `ConnectionId` — `string`, optional — SignalR connection id for async results.
- **Responses:**
  - `200 OK` → the test execution result value (`response.Value`; shape produced by the test-action manager — see Notes).
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.
- **Notes:** `Gid`, `TestValues`, `Action`, `ConnectionId` have no `[JsonProperty]` overrides → wire names are their PascalCase C# names. `variables` is overridden to lowercase via `[JsonProperty("variables")]` on the base. The 200 payload type is not a named DTO in this service (manager returns the action result object); poll the GET below for the resolved result.

#### `GET api/Actions/test/{id}`

- **Operation:** `GetTestActionResults` — fetch the results of a previously executed test action.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update`
- **Path params:** `{id}` — `string (uuid)`, required — test action id.
- **Responses:**
  - `200 OK` → the test action result object.
  - `400 Bad Request` → `ErrorResponse` (not-found message) when null.

---

### CustomActionController (`api/Actions`)

Entity: `CustomActions`. Lets users upload a custom action as a NuGet package, which registers a new action template, and soft-delete it.

#### `POST api/Actions`

- **Operation:** `Upload` — upload a custom-action NuGet package; registers a new action template.
- **Auth:** Bearer JWT — **Permission:** `CustomActions:Create` (Swagger says "CustomActions.Write")
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the NuGet `.nupkg` of the custom action. Must be non-empty.
- **Special headers:**
  - `name` — `string` `[FromHeader]`, required — the action display name (mapped to `CustomActionHeaders.ActionName`).
  - `path` — `string` `[FromHeader]`, required — icon path (mapped to `CustomActionHeaders.IconPath`).
- **Responses:**
  - `200 OK` → the new action template id (`string (uuid)`) on success.
  - `400 Bad Request` → `ErrorResponse` when the package is empty (`UPLOAD_ACTION_NOT_FOUND`) or when the upload finishes with errors.
- **Notes:** `Consumes("multipart/form-data")` overrides the controller's JSON default. `name`/`path` travel as HTTP headers, not form fields. The manager returns `object` — a Guid template id on success or a `List<ErrorPayload>` on failure.

#### `DELETE api/Actions/{id}`

- **Operation:** `SetActionActiveState` — soft-delete a custom action (sets active state to `false`).
- **Auth:** Bearer JWT — **Permission:** `CustomActions:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — custom action id.
- **Responses:**
  - `200 OK` → empty body.
  - `400 Bad Request` → `ErrorResponse` when the manager returns errors.
- **Notes:** Soft delete only (the action is deactivated, not physically removed).

---

### PlatformActionController (`api/PlatformAction`)

Entity: `ProcesioAdmin`. Internal admin tool to upload PROCESIO platform (built-in) actions as NuGet packages, optionally registering them into the action-node tree. Route token `[controller]` resolves to `PlatformAction` → full route `api/PlatformAction`.

#### `POST api/PlatformAction`

- **Operation:** `Upload` — upload a custom-action NuGet for PROCESIO platform templates (admin only).
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes (controller-level `[ApiExplorerSettings(IgnoreApi = true)]`)
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the NuGet `.nupkg`. Must be non-empty.
- **Special headers:**
  - `name` — `string` `[FromHeader]`, required — action display name (→ `CustomActionHeaders.ActionName`).
  - `icon` — `string` `[FromHeader]`, required — icon path (→ `CustomActionHeaders.IconPath`).
  - `actionClass` — `string` `[FromHeader]`, required — the action class name (→ `PlatformActionHeaders.ActionClassName`). If empty/missing → `401 Unauthorized`.
  - `addNode` — `boolean` `[FromHeader]`, required — whether to add an action node for this action (→ `AddActionNode`).
  - `parentNode` — `string (uuid)` `[FromHeader]`, optional — parent node id; if omitted the node is created at root level (→ `ActionParentNode`).
  - `nodeOrder` — `number` `[FromHeader]`, required — node order index (→ `ActionNodeOrder`).
- **Responses:**
  - `200 OK` → the new action template id (`string (uuid)`) on success.
  - `401 Unauthorized` → when `actionClass` header is empty/missing.
  - `400 Bad Request` → `ErrorResponse` when the package is empty (`UPLOAD_ACTION_NOT_FOUND`) or when upload finishes with errors.
- **Notes:** Same uploader as `CustomActionController.Upload` but adds platform-action metadata (class name, node placement). Requires PROCESIO admin permission.

---

## Shared DTOs

> JSON wire names follow Newtonsoft.Json. A field marked with `[JsonProperty("x")]` or `[JsonPropertyName("x")]` uses `x`; otherwise the C# property name is used verbatim (PascalCase). Required = non-nullable value type or `[Required]`; everything nullable/defaulted is optional.

### `BaseActionNodeDto`
- `nodeId` — `string (uuid)`, optional — unique node id.
- `name` — `string`, optional — element/folder name.

### `SimpleActionNodeDto` (extends `BaseActionNodeDto`)
- `nodeId` — `string (uuid)`, optional — (inherited).
- `name` — `string`, optional — (inherited).
- `parentId` — `string (uuid)`, optional — parent node id.
- `id` — `string (uuid)`, optional — id of the element, or null if it is a node/folder.
- `order` — `number`, required — order index.

### `ActionNodeDto` (extends `SimpleActionNodeDto`)
- (all inherited fields above) plus:
- `type` — `number`, required — element type code.
- `isProcesio` — `boolean`, required — whether the folder is a PROCESIO (built-in) folder.
- `children` — array of `ActionNodeDto`, optional — nested child nodes (tree).

### `ActionPrototypeDto`
- `id` — `string (uuid)`, optional — prototype id.
- `parentNodeId` — `string (uuid)`, optional — parent folder id.
- `name` — `string`, optional — prototype name.
- `icon` — `string`, optional — icon (inherited from the parent template).
- `isProcesio` — `boolean`, required — whether the prototype is a PROCESIO (built-in) one.
- `actionTemplate` — `object (ActionDto)`, optional — the saved action configuration.

### `SimpleActionTemplateDto` (extends `OwnershipAuditDto`)
- (all `OwnershipAuditDto` fields) plus:
- `key` — `string (uuid)`, required — action template id.
- `name` — `string`, optional — action name.
- `description` — `string`, optional — action description.
- `icon` — `string`, optional — icon.
- `shape` — `string`, optional — node shape.
- `inputPorts` — `number`, required — number of input ports.
- `outputPorts` — `number`, required — number of output ports.
- `isProcesioAction` — `boolean`, required — whether the action is developed by PROCESIO.
- `permissions` — `object (PermissionsDto)`, optional — action permissions.
- `isTestable` — `boolean`, required — can be tested outside a flow.
- `isDebuggable` — `boolean`, required — supports debug.
- `isDisableable` — `boolean`, required — can be disabled.
- `tooltip` — `string`, optional — tooltip text.
- `documentation` — `object (UserGuideDTO)`, optional — user guide links.

### `DetailedActionTemplateDto` (extends `SimpleActionTemplateDto`)
- (all `SimpleActionTemplateDto` fields) plus:
- `configuration` — array of `ActionTabDto`, optional — all tabs of the template (the full config).
- `events` — array of `PropertyEventDto`, optional — action-level events (for connector actions); defaults to `null`.
- `updatedOn` — `string (date-time, ISO-8601)`, required — last update time.

### `OwnershipAuditDto`
Audit/ownership base for list responses.
- `firstName` — `string`, optional — (legacy; being replaced by `createdBy`).
- `lastName` — `string`, optional — (legacy).
- `workspaceId` — `string (uuid)`, optional — owning workspace.
- `createdBy` — `string`, optional — "FirstName LastName" of creator.
- `updatedBy` — `string`, optional — "FirstName LastName" of last updater.
- `createdById` — `string (uuid)`, optional — creator user id.
- `updatedById` — `string (uuid)`, optional — last updater user id.
- `createdOn` — `string (date-time, ISO-8601)`, optional — creation time.
- `updatedOn` — `string (date-time, ISO-8601)`, optional — last update time.

### `PermissionsDto`
- `canDelete` — `boolean`, optional (default `false`).
- `canAddFromToolbar` — `boolean`, optional (default `false`).
- `canDuplicate` — `boolean`, optional (default `false`).
- `canSaveActionAsTemplate` — `boolean`, optional (default `false`).

### `UserGuideDTO`
- `url` — `string`, optional — documentation URL.
- `image` — `string`, optional — documentation image.

### `ActionTabDto`
- `key` — `string (uuid)`, required — tab id.
- `label` — `string`, optional — tab label.
- `orderId` — `number`, required — tab order.
- `settings` — array of `TabPropertyDto`, optional — the tab's properties.

### `TabPropertyDto`
- `id` — `string (uuid)`, required — property id.
- `dataTypeId` — `string (uuid)`, optional — property data type id.
- `label` — `string`, optional — label.
- `type` — `string`, optional — property type.
- `language` — `string`, optional — text format (JSON/SQL/PLAINTEXT/etc.) — wire name `language`, C# `TextFormat`.
- `credentialsTemplateId` — `string (uuid)`, optional — credential template id.
- `value` — `object` (string or JSON), optional — constant value or nested sub-properties.
- `options` — `object` (JSON), optional — options for the property.
- `isRequired` — `boolean`, optional — required by the normal action flow.
- `expects` — `string`, optional — restriction enum (as string).
- `isList` — `boolean`, required — value is a list of objects.
- `direction` — `number` (ushort), optional — input vs. output.
- `rowId` — `number`, required — row order.
- `columnId` — `number`, required — column order within a row.
- `columnSize` — `number`, required — column size.
- `tooltip` — `string`, optional — tooltip.
- `limits` — `object (LimitsDto)`, optional — value limits.
- `dependencies` — array of `PropertyDependencyDto`, optional — property dependencies; defaults to `null`.
- `events` — array of `PropertyEventDto`, optional — property-triggered events; defaults to `null`.

### `LimitsDto`
- `Min` — `object`, optional — minimum limit.
- `Max` — `object`, optional — maximum limit.

### `PropertyDependencyDto`
- `target` — `string (uuid)`, required — id of the property targeted next.
- `operator` — `string|number (enum: Operator)`, required — condition operator. **Enum defined externally** (NuGet `Ringhel.Procesio.Action.Core`); values not resolvable in this repo.
- `logicalOperator` — `string|number (enum: LogicalOperator)`, optional — logical operator when multiple dependencies exist. **Enum defined externally**; values not resolvable in this repo.
- `value` — `object`, optional — value affected by the triggering property.

### `PropertyEventDto`
- `type` — `number`, required — event type triggering the connector execution.
- `inputs` — array of `string (uuid)`, optional — property ids used as connector inputs.
- `outputs` — array of `string (uuid)`, optional — property ids that become connector outputs.
- `outputTarget` — `string|number (enum: OutputTarget)`, optional — target output type for dynamic FE refresh. **Enum defined externally** (NuGet `Ringhel.Procesio.Action.Core`, namespace `Ringhel.Procesio.Action.Core.Utils`); one named value is `None`; full value list not resolvable in this repo.

### `BaseActionGroupingDto`
- `grouping` — array of `ActionNodeDto`, optional — all action nodes (the folder tree); defaults to `[]`. (C# property `Nodes`.)
- `prototypes` — array of `ActionPrototypeDto`, optional — action prototypes; defaults to `[]`. (C# property `PrototypeActions`.)

### `SimpleActionGroupingDto` (extends `BaseActionGroupingDto`)
- (inherited `grouping`, `prototypes`) plus:
- `actions` — array of `SimpleActionTemplateDto`, optional — action templates; defaults to `[]`.

### `DetailedActionGroupingDto` (extends `BaseActionGroupingDto`)
- (inherited `grouping`, `prototypes`) plus:
- `actions` — array of `DetailedActionTemplateDto`, optional — full action templates; defaults to `[]`.

### `ConnectorActionRequestDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `Gid` — `string (uuid)`, required — connector action id.
- `Gtid` — `string (uuid)`, required — action template id.
- `Trigger` — `string (uuid)`, optional — trigger property id.
- `EventType` — `number`, required — `ControlEventType` (if `Trigger` set) or `ActionEventType`.
- `Variables` — array of `VariableDto`, optional (default empty).
- `Parameters` — array of `ParametersDto`, optional (default empty).
- `ConnectionId` — `string`, optional — SignalR connection id.

### `ConnectorActionResponseDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `Gid` — `string (uuid)`, required — connector action id.
- `Gtid` — `string (uuid)`, required — action template id.
- `Trigger` — `string (uuid)`, optional — triggering property.
- `EventType` — `number`, required — event type.
- `Status` — `string|number (enum: ActionStatus)`, required — execution status.
- `Variables` — array of `VariableDto`, optional (default empty).
- `Parameters` — array of `ParametersDto`, optional (default empty).
- `OutputValues` — array of `ConnectorControlValueDto`, optional (default empty) — execution result.
- `ErrorMessage` — `string`, optional — error message.
- `ErrorCode` — `number`, optional — error code.
- `CreatedById` — `string (uuid)`, required — user who triggered the step.
- `WorkspaceId` — `string (uuid)`, required — workspace id.

### `ConnectorControlValueDto`
- `PropertyId` — `string (uuid)`, required — output property id.
- `OutputTarget` — `string|number (enum: OutputTarget)`, optional (default `None`). **Enum defined externally** (see `PropertyEventDto.outputTarget`).
- `Value` — `object`, optional — the output value.

### `DetailedTestActionRequestDto` (extends `BaseTestActionDto`)
- `variables` — array of `VariableDto`, optional — (inherited; wire name `variables`).
- `Gid` — `string (uuid)`, required — action instance id being tested.
- `TestValues` — array of `ActionAttributeDto`, optional — test input values.
- `Action` — `object (TestActionDto)`, optional — the action being tested.
- `ConnectionId` — `string`, optional — SignalR connection id.

### `BaseTestActionDto`
- `variables` — array of `VariableDto`, optional — variables (wire name `variables`).

### `TestActionDto`
- `gtid` — `string (uuid)`, required — action template id.
- `parameters` — array of `ParametersDto`, optional — parameters.

### `VariableDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `Id` — `string (uuid)`, required — variable id.
- `ContextId` — `string (uuid)`, optional — context id.
- `DataType` — `string (uuid)`, required — data type id.
- `Type` — `string|number (enum: VariableOrientation)`, required — `INPUT=10`, `PROCESS=20`, `OUTPUT=30`.
- `Name` — `string`, optional — variable name.
- `DefaultValue` — `object`, optional — default value.
- `IsList` — `boolean`, required — whether the value is a list.
- `IsError` — `boolean`, required — whether it is an error variable.
- `IsRequired` — `boolean`, optional (default `false`).

### `ParametersDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `TabPropertyId` — `string (uuid)`, required — the tab property this parameter binds to.
- `Variable` — array of `ParameterVariableDto`, optional — variable bindings.
- `Value` — `object`, optional — literal value.

### `ParameterVariableDto`
- `id` — `number`, required — binding id.
- `variableId` — `string (uuid)`, optional — referenced variable id.
- `attribute` — `object (VariableAttributeDto)`, optional — attribute path.

### `VariableAttributeDto`
- `attributeId` — `string (uuid)`, required — attribute id.
- `nextAttribute` — `object (VariableAttributeDto)`, optional — linked next attribute (recursive path).

### `ActionAttributeDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `VariableId` — `string (uuid)`, optional — variable id.
- `Value` — `object`, optional — value.
- `Attribute` — `object (VariableAttributeDto)`, optional — attribute path.

### `ActionDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `Id` — `string (uuid)`, required — action instance id.
- `FlowId` — `string (uuid)`, required — flow id.
- `TemplateId` — `string (uuid)`, required — action template id.
- `ParentId` — `string (uuid)`, optional — parent action id.
- `VariableErrorId` — `string (uuid)`, optional — error variable id.
- `Status` — `string|number (enum: ActionStatus)`, required — action status.
- `Category` — `string`, optional — category.
- `ActionName` — `string`, optional — action name.
- `ActionTemplateName` — `string`, optional — template name.
- `Ports` — array of `PortDto`, optional — connection ports.
- `Parameters` — array of `ParametersDto`, optional — parameters.
- `CustomData` — `object`, optional — free-form custom data.
- `IsTestable` — `boolean`, required — can be tested.
- `IsDisabled` — `boolean`, required — disabled flag.
- `BreakPoint` — `object (BreakPointDto)`, optional — breakpoint config.
- `TestValues` — `object`, optional — stored test values.
- `ErrorMessage` — `string`, optional — error message.
- `Events` — array of `PropertyEventDto`, optional — events; defaults to `null`.

### `PortDto`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `Id` — `string (uuid)`, required.
- `FlowId` — `string (uuid)`, required.
- `SourceId` — `string (uuid)`, required.
- `DestinationId` — `string (uuid)`, required.
- `Type` — `number`, required.
- `State` — `number`, required.
- `Data` — `object`, optional.
- `Errors` — `object`, optional.
- `Config` — `object` (map of `string` → `number`), optional.

### `BreakPointDto`
- `Enabled` — `boolean`, required.

### `DecisionMatrixRule`
- `operatorName` — `string`, optional — operator name.
- `operatorType` — `string`, optional — operator type (e.g. UNARY/BINARY/TERNARY).
- `operatorIcon` — `string`, optional — icon.
- `rightOperandAsListRequired` — `boolean`, required — whether the right operand must be a list.
- `operandsAsListOptional` — `boolean`, required — whether operands may optionally be lists.
- `dataTypes` — array of `DecisionDataType`, optional — supported data types.
- (`operatorCategory` and `operator` C# properties are `[JsonIgnore]` and not serialized.)

### `DecisionDataType`
(No `[JsonProperty]` overrides → wire names are PascalCase.)
- `Id` — `string (uuid)`, required — data type id.
- `Name` — `string`, optional — data type name.

### Enums

#### `ActionStatus` (`number`)
- `NONE = 1`
- `STARTING = 10`
- `INPUT_DONE = 15`
- `EXECUTED = 20`
- `FOREACH_ITERATION_DONE = 30`
- `CALL_SUBPROCESS_CHILD_STARTED = 35`
- `CALL_SUBPROCESS_CHILD_FINISHED = 36`
- `OUTPUT_DONE = 40`
- `ERROR = 90`

#### `VariableOrientation` (`number`)
- `INPUT = 10`
- `PROCESS = 20`
- `OUTPUT = 30`

#### `AuthorizationActionType` (`number`) — permission action (context, not a wire field)
- `None = 1`, `Read = 2`, `Update = 3`, `Create = 4`, `Delete = 5`, `Admin = 6`

#### `AuthorizationEntityType` (`number`) — permission entity (context, not a wire field)
- `MasterWorkspace = 1`, `Workspace = 2`, `ProcessDesigner = 3`, `ProcessInstance = 4`, `CustomActions = 5`, `DataModels = 6`, `Credentials = 7`, `DocumentDesigner = 8`, `Webhook = 9`, `Schedule = 10`, `ApiKey = 11`, `FormTemplate = 12`, `FormInstance = 13`, `DataStore = 14`, `ProcesioAdmin = 101`, `None = 102`

#### `OperatorType` (`number`) — used internally by `DecisionMatrixRule` (`[JsonIgnore]`, not on the wire)
- `NONE = 0`, `UNARY = 1`, `BINARY = 2`, `TERNARY = 3`

---

## Unresolved / external DTOs & enums

- `Operator`, `LogicalOperator`, `OutputTarget` enums — defined in the external NuGet package `Ringhel.Procesio.Action.Core` (namespace `Ringhel.Procesio.Action.Core.Utils`), not in this repo. They serialize as enum values (string or number); `OutputTarget` is known to include a `None` member but the full value list is not available here.
- `ErrorResponse` (the `400` body) — composed by `CustomErrorHelper.ComposeResponse(...)` from action error definitions plus `ErrorPayload`s; shape is the standard Web-Api error envelope (documented in conventions). Each `ErrorPayload` carries an error code and message.
- `ExecuteTestAction` 200 body — the test-action manager returns an action result object that is not a named DTO in this service; consumers should poll `GET api/Actions/test/{id}` for the resolved result.
