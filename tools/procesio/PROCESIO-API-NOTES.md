# PROCESIO API — behaviors learned (not in Swagger)

Live-validated facts that the Swagger doesn't make obvious. Auth itself is in
[PROCESIO-AUTH-NOTES.md](PROCESIO-AUTH-NOTES.md); this file is everything else.
Append here as we learn more (CLAUDE.md Hard rule 6).

## DTO casing — live API is camelCase, exports are PascalCase (⚠ bites parsers)

The **live Web-API returns camelCase** (`flow.actions[].actionTemplateName`,
`parameters[].value`, `customData.configuration`, `title`, `isValid`), while the
offline **`.procesio` export bundles use PascalCase** (`Actions`, `Parameters`,
`Value`, `CustomData`, `Title`). Same DTOs, different case. Code that consumes
BOTH (e.g. the agent reads live processes; goldens/tests read exports) must access
keys **case-insensitively** — verified live 2026-06-25, after the agent's `audit`
first returned 0 actions on a live process because it only looked for `Actions`.
(`agents/procesio/audit.py:ci()` is the shared case-insensitive getter.)

## Workspace scoping (both auth modes)

- A request is scoped to a workspace by the **`workspaceid` request header** (the
  workspace GUID). API keys: required for workspace-scoped keys. Userpass cookie
  session: optional, sets the *active* workspace (defaults otherwise). Same header
  for both. *(The tool's userpass mode does not yet expose `--workspace-id`.)*
- **Prefer userpass for owner/admin and cross-workspace reads** — wider access.

## Workspaces

- `GET /api/Workspaces` (plural) — all workspaces the caller can see, **active
  only**. Items: `{type, licenseType, hasAccess, workspace (=name), id, parentId}`.
  Derive a master's children by filtering `parentId == <masterId>`.
- `GET /api/Workspace/{parentId}/subworkspaces` — **all** children of a master,
  **including soft-deleted ones**. Items: `{userCount, workspaceState, createdOn,
  canExceedPaidTime, workspace (=name), id, parentId}`. Requires owner/admin
  context — **API keys get 401, use userpass**. To match the UI, filter
  `workspaceState == "active"` (deleted ones carry `workspaceState: "removed"`,
  `userCount: 0`). Detail: `GET /api/Workspace/{parentId}/subworkspaces/{id}`.
- `GET /api/Workspace` (singular) has **no GET** — don't use it for listing.

## Processes (a.k.a. Flows / Projects)

- List: `GET /api/Projects` → envelope `{totalItemCount, pageNumber,
  pageItemCount, pageItems}` (params `pageNumber`, `pageItemCount`, `searchName`).
- **The display name is in `title`, NOT `name`** — `name` is null in the list.
  Item keys: `id, parentId, status, title, description, isValid, active, timeout,
  currentActionId, debugMode, isNotification, workspaceId, created*/updated*`.
- Run: `POST /api/Projects/{id}/run` body `{"payload":{}, "connectionid":null}`.
- **An action's canvas label lives in TWO fields and both must be written together:**
  the DTO's `ActionName` and `CustomData.name`. The designer renders
  `CustomData.name`; list/inspect surfaces read `ActionName` — write only one and the
  two views disagree about what a node is called. `rename-actions` sets both.
- **Action labels are cosmetic — every reference is by id**, so renaming can never
  break wiring: ports use `SourceId`/`DestinationId`, a Decisional case points at
  `actionid`, and a parameter binds `variableId`. Nothing resolves an action by name.
- A newly built flow arrives with every node carrying its template's default label
  (`Node`, `Call API`, `Decisional`). A canvas of a dozen identical `Node` boxes is
  unreadable — each one has to be opened to find out what it does. Rename in bulk
  (`rename-actions --map`) as the last step of building a process, not as polish.

## Data models, documents, forms

- **Data models** = `DataTypes`. `GET /api/DataTypes` with
  `includeProcesioEntries=false&includeExternalEntries=true` → the workspace's
  custom data models only (`{name, id, ...}`).
- **Documents (document designer)** = `DocumentTemplate`. List
  `GET /api/DocumentTemplate` (scoped by `workspaceid`).
- **Forms** = `FormTemplate`. `GET /api/FormTemplate` (scoped by `workspaceid`);
  `status`: `1` = active/published, `0` = draft. Also `GET /api/FormTemplate/all/basic`.

## Export / Import — the `.procesio` bundle (Transport)

- `POST /api/Transport/export-entities` — **requires `Workspace.Admin`** (use
  userpass). Scope to the source WS via `workspaceid`. Body:
  ```json
  { "dataModelIds": [], "flowIds": [], "credentialIds": [], "webhookIds": [],
    "documentIds": [], "formIds": [], "exportSensitiveData": false }
  ```
  `flowIds` = process IDs. `exportSensitiveData=false` excludes credential secrets.
- Response: `200`, `Content-Type: application/octet-stream`,
  `Content-Disposition: attachment; filename="ExportedEntities-<MM/DD/YYYY HH:MM:SS>.procesio"`.
  The body **is** the `.procesio` file — a JSON bundle with top keys:
  `DataTypes, Credentials, Webhooks, DocumentTemplates, Flows, Forms, TimeStamp`.
  Each entity carries a **stringified** `Data` field (escaped JSON).
- `GET /api/Transport/export` and `POST /api/Transport/import` also require
  `Workspace.Admin`.
- Verified 2026-06-23: exported lazarusDM + 2 flows + 1 document, no credentials,
  from WS "MD test 4 support" (`4159b568-…`) → 92,868-byte bundle, sections matched.

## Validation oracles (use before committing a create/edit)

`POST /api/Projects/validate`, `POST /api/Credentials/test`,
`POST /api/Actions/test` — PROCESIO's own validators; cheapest place to catch a
bad DTO. (Used by the DTO sub-tools and by the **procesio agent** `verify` gate —
see DTO-SUBTOOLS-NOTE.md and `agents/procesio/`.)

- **`/api/Projects/validate` body = the BARE flow object** (exactly the object you
  get back under `result.flow` from `GET /api/Projects/{id}`). Verified live
  2026-06-25. Wrapping it (`{"flow": …}` or `{"project": …}`) returns **HTTP 500
  "Value cannot be null. (Parameter 'source')"** — don't wrap.
- **A valid process returns 2xx; an INVALID one returns HTTP 400** whose body is
  `{"body": [ {statusCode, value, target}, … ]}` — the validation messages, NOT a
  request error. Seen: `390 "Action has too few input ports."`, `391 "Action has
  too few output ports."`. So a 400 here is a *result*, not a transport failure —
  parse `details.body.body` for the messages (the agent's verify does this).

## Authoritative DTO source

`tools/procesio/docs_info/` is the **source-of-truth** for every DTO (extracted
from the BE microservice repos, API v1.19 — 297 endpoints with full field lists +
enums). Prefer it over `data/endpoints.json` (Swagger index, no bodies). The 12
`.procesio` bundles in `docs_info/Exports/` are **live production resources** —
the golden saved-DTO shapes the builders merge onto (Flows/DataTypes/Credentials/
Forms each carry an internal stringified `Data`/`CanvasData`). Webhooks live
embedded in Flows (`Flows[].Webhooks[]`), not as a standalone export section.
`docs_info/Procesio Platform Actions.json` = `{"actions":[213]}`, each with
`actionId` + `configuration[tabs].settings[properties]` — the golden source for
action-node building.

## Action-node building — worked examples

- **Send Email (SMTP) with attachment + dynamic recipient** —
  [PROCESIO-SEND-EMAIL-NOTES.md](PROCESIO-SEND-EMAIL-NOTES.md): the
  `Parameters[]` variable-binding pattern (`{TabPropertyId, Variable[], Value}`
  with `<%N%>` placeholders), the full Send Email TabPropertyId map, File-typed
  attachment binding, comma-joined String recipient, built-in dataTypeIds, and a
  verbatim real-flow example. The pattern (`Parameters[]` + `<%N%>`) generalizes
  to any action node.

## Auth & client gotchas (verified 2026-06-24)

- **`x-version: 1.19` header** — the client now sends it on every call
  (`config.api_version`, overridable via `PROCESIO_API_VERSION`). NOT strictly
  required in prod (the gateway assumes the default when omitted — verified live),
  but the docs recommend pinning it; harmless and future-proof.
- **Access cookie is a ~30 min JWT.** `auth.login` now records the real expiry
  from the JWT `exp` claim (the `x-session-expires-at` header is the *refresh*
  expiry ~24h, not the access one). `_is_fresh` distrusts an unknown/None expiry
  and re-logins. The userpass session works for ALL gateway routes (DataTypes/
  Projects/Actions/…), not just `/api/Workspaces` — earlier "401 only on gateway
  routes" was the path-mangling bug below, not an auth limitation.
- **requests cookie-jar contamination** — the client clears the Session jar
  before each send (`_clear_jar`) so only the explicit `Cookie` header is sent;
  otherwise a stale jar `__Host-procesio.access` collides with the fresh one.
- **⚠ Git Bash MSYS path mangling (TESTING artifact, not a tool bug).** Passing
  `--path /api/DataTypes` through the **Bash tool** rewrites the leading-slash arg
  to `/C:/Program Files/Git/api/DataTypes`, which 401s. Prefix Bash commands with
  `MSYS_NO_PATHCONV=1` (or call from PowerShell, or drive the client in-process
  via Python). From PowerShell the path is fine. This wasted hours once — don't
  re-debug it as "auth".

---

## Session findings 2026-06-25 (AAT_ end-to-end v2 — live-verified)

### Download a flow-instance file — `GET /api/File/download` (HAR-verified)
The file identifiers are **HEADERS, not query params** (a query-only call returns NRE
"Object reference not set"). Query: `?isArchived=false`. Headers (+ normal auth):
`uploadFilePath` (the file DTO `path`, e.g.
`flow/flow-<flowId>/flow-instance-<instanceId>/variable-<varId>/<fileId>`),
`variableId`, `instanceId`, `flowTemplateId`, `workspaceId`. Returns raw bytes
(`content-disposition: attachment; filename=...`). Confirmed against the browser HAR
"download file from instance". **Shipped** as the `file-download` action (`tools/procesio/handlers/files.py`; `--from-run` derives the ids from a run-process result).

### `Call API` -> a TYPED model output = the way to feed a typed list
A `Call API` whose **Response Body** targets a variable typed as a **data model**
DESERIALIZES the JSON into it by **`jsonProperty`**, INCLUDING `List<itemModel>`:
Google `items[]` -> `AAT_GoogleResponse.items : list<AAT_SearchHit>` = 6 populated rows, live.
This is the ONLY way to feed a typed repeating-table list from DYNAMIC data — the **Javascript**
scripting action canNOT output a typed list. Inlining the SAME item model into two parents
(`AAT_SearchReport.hits` and `AAT_GoogleResponse.items`) yields the SAME child attr ids
(shared, not copied) -> any `list<item>` binds to a document's repeating table built on it.

### Scripting actions — output WRAPPING DIFFERS by action
The catalog has distinct scripting actions: **Javascript**, **Node**, **Python**.
- **Javascript** (`setOutput(v)`): the output variable receives **`{ result: v }`** — a
  WRAPPER. Mapping a primitive to a string var stringifies the whole `{result:...}`. To get
  clean values either (a) feed a typed ENVELOPE model `{ result: { ...fields } }` and docMap
  each field `path:[resultAttrId, fieldAttrId]`, or (b) use **Node**.
- **Node** (NodeJS): returns the script's result **RAW — no wrapper** (confirmed with the PROCESIO team).
  A Node script returning `{ searchTerm, generatedOn, ... }` maps straight onto a flat typed
  model, no `result` envelope needed. **Prefer Node when you need clean / typed scalar output.**
- **NEVER feed a Javascript-action output var DOWNSTREAM as a scalar** (e.g. a Call API query
  param): the `{result:...}` wrapper leaks — a JS-computed `searchTerm` made
  `q = "{ 'result': 'Example Company' }"` -> empty search -> empty table + leaked cells.
  Drive downstream actions (the search query, the file name) from the ORIGINAL inputs.

### `Generate Document` has an "HTML string" OUTPUT
Its configuration includes `"HTML string"` (`id 79c77296-37a6-43d7-b002-ba346860b6f1`,
`type=datatype`, **direction=3 / OUTPUT**) alongside `"Document Output"` (file). So a
document template can render to an HTML STRING variable — e.g. to feed a `Send Email` Body
from a document template (requirement-2.3 path), not only to a PDF/DOCX file.

### Process builder global `<%N%>` indexing is correct across an action's params
For a multi-param action (Send Email To/Subject/Body/Map attachment) the builder assigns a
GLOBAL `<%N%>` counter and remaps each templated Value to it (To `<%0%>`, Subject `<%1%> <%2%>`,
Body `<%3%> <%4%>`, attachment `<%5%>`) with matching `Variable[].id`. Verified aligned —
adding a `To` variable does NOT misalign later params (the rendered Subject was correct live).

## Scheduler (/api/Schedules)

Curated actions live in `handlers/schedules.py` (list/get/create/update/delete a
schedule, enable/disable, get/set notifications, list a project's schedules). All
verified live 2026-06-29 against the `account` (userpass) profile. The
create/update **body shape is NOT in our Swagger index** — captured here so the
next session doesn't re-derive it.

### Endpoints + methods (tag Schedules; permission in parens)
- `GET  /api/Schedules` — list. Supports `pageNumber` / `pageItemCount` /
  `searchName` query params. (Schedule.Read)
- `GET  /api/Schedules/{scheduleId}` — get one (rich read DTO). (Schedule.Read)
- `POST /api/Schedules` — create (body). (Schedule.Write)
- `PUT  /api/Schedules` — update (body, includes `id`). (Schedule.Update)
- `DELETE /api/Schedules/{scheduleId}` — delete; returns a plain string
  `"Deleted schedule with id <guid>"`. (Schedule.Delete)
- `PATCH /api/Schedules/{scheduleId}/status?enable=true|false` — enable/disable.
  ⚠ The query flag is **`enable`** (NOT `active`); our `set-schedule-status`
  exposes `--active true|false` and maps it to `enable`. Returns an empty 2xx body
  (the client surfaces `{"raw_text": ""}`). (Schedule.Update)
- `GET  /api/Schedules/notifications/{scheduleId}` — notification config + a copy
  of `recurrence`/`scheduleName`/`scheduleStatus`. (Schedule.Read)
- `POST /api/Schedules/notifications` — set notifications (body). (Schedule.Update)
- `GET  /api/Projects/{id}/restricted/schedules` — returns the **flow detail**
  (variables[], title, active), i.e. the target process whose `variables` feed a
  schedule's `processInputs`. (Schedule.Read)

### Create / update body shape (live-captured, camelCase)
```json
{
  "name": "string",
  "description": "string",
  "status": false,                      // see gotcha: ignored on create
  "targetProcess": "<process/flow guid>",
  "processInputs": [],                  // input-variable values for the run; [] = none
  "notification": {
    "emailList": "a@example.com",             // comma/semicolon-separated string, NOT a list
    "isEnabled": false,
    "onSuccess": true,
    "onFail": true
  },
  "recurrence": {
    "info": "every 5th of every month", // human label
    "every": 0,
    "onDay": 5,
    "onThe": [2, 1],                    // [ordinal, weekday] enums; [] when isOnThe=false
    "endDate": "2022-04-19T15:30:00Z",
    "isOnThe": false,
    "isEndDate": false,
    "startDate": "2026-07-01T06:00:00Z",
    "recurrence": 6,                    // recurrence-TYPE enum (see below)
    "isWeekendExcluded": false
  }
}
```
The GET-by-id read DTO returns this same nested shape **plus** read-only fields
(`id`, `status`, `firstName`/`lastName`, `workspaceId`, `createdBy`/`createdOn`,
`updatedBy`/`updatedOn`). For **update** (`PUT`), include the schedule `id` in the
body.

### Gotchas (live-verified 2026-06-29)
- **The write body must mirror the read DTO closely.** A hand-simplified daily
  payload (`recurrence.every:1, recurrence:1, onThe:[]`) returned HTTP 400
  `{"statusCode":502,"value":"Invalid request due to missing or incorrect resource
  parameters.","target":"schedules"}`. Cloning the existing schedule's exact
  `recurrence` block (monthly, `recurrence:6, onDay:5, onThe:[2,1]`) was accepted.
  When in doubt, GET an existing schedule and adapt its shape rather than build
  from scratch. The numeric `recurrence` enum values are not documented in our
  index — `6` is the monthly/"every Nth of every month" type seen live; other
  values (daily/weekly/etc.) need to be discovered from a real example or the live
  scheduler UI before relying on them.
- **`status:false` is ignored on create.** POST with `status:false` returned a
  schedule with `status:true` (created active). To create-then-disable, follow the
  create with `set-schedule-status --active false` (verified: status flipped
  true→false). So a "disabled test schedule" is a two-step: create, then patch.
- **`notification.emailList` is a single string**, not an array (e.g.
  `"a@example.com,c@example.org"`).
- **DELETE returns a bare string**, not JSON — the curated action wraps it as
  `{"result": "Deleted schedule with id <guid>"}`.
- Round-trip proven live: create (id `9cbe…`) → get → set-status false → get
  (status=false) → delete → list confirms cleanup. No residue left.

### Node scripting action — list output + MANDATORY Timeout
- `return <value>` at top level returns the value **RAW** (no `{result}` wrapper, unlike the
  Javascript action's `setOutput`). An **array** return binds to the **List Result** output
  (id `60237e88-e95c-c74c-a130-036964e6fc28`); a non-list to **Single Result** (id
  `51b9fcdc-b18b-2a40-a73b-fc04657657bc`). Variables inject as `<%0%>` (same as Javascript).
  Example — build a `list<File>` from a single `File`: Code `return [<%0%>];`, vars `[briefFile]`,
  bind **List Result** → a `list<File>` var. (Code field id `1e6a5523-2091-6c4c-94ac-c7984074673d`.)
- **`Timeout` is REQUIRED and must be > 0** (id `d3e52aab-b9d0-2d42-911e-b0e6de177a57`, number =
  seconds). If unset it defaults to `00:00:00` and the run ERRORS at the Node action:
  `value ('00:00:00') must be greater than '00:00:00'`. Real flows use `60` or `300`.

### Registry resilience (framework)
`registry.get_tool(name)` loads each `tools/*/tool.yaml` until a name match, so ONE broken /
transiently-unreadable sibling manifest used to throw and block EVERY tool (hit live when
`mysql`/`sqlserver` half-built manifests intermittently failed `load_tool` on the FUSE mount
even though `yaml.safe_load` passed). `get_tool` now skips an unloadable SIBLING manifest
(stderr warning) and only re-raises if the broken manifest IS the requested tool.

### Generate Document "HTML string" output — proven + froala wrapper (2026-06-25)
Renders the doc body to HTML with placeholders filled; feeds `Send Email` Body from a document
(AAT_EmailBody → emailHtml → Body ← {var:emailHtml}, status 50 live — requirement 2.3 done).
Gotchas: (a) the output is WRAPPED in a Froala editor shell
(`<html><head><link froala_style.min.css><body><div class='fr-box fr-document'><div class='fr-view'>…</div>`)
— INLINE styles survive (brand colors/fonts render in email), but the external Froala CSS may
not load in email clients, so style with INLINE css, not `fr-*` classes. (b) Bind doc vars by
NAME in docMap (builder resolves name→id). (c) A Generate Document used ONLY for the HTML string
needs no `Document Output` / `Save document as` / `File Name`.

### Custom actions (connectors) — lifecycle (HAR-verified 2026-06-25)
Shipped as `customaction-upload` / `customaction-delete` / `customaction-list`
(`tools/procesio/handlers/customaction_ops.py`).
- **Upload / install:** `POST /api/actions`, `multipart/form-data`, single field **`package`** =
  the `.nupkg` (Content-Type `application/x-compressed`) + `workspaceid` header →
  `{"id":"<actionId>"}`. Perm `CustomActions.Write`. `client.request_multipart()` leaves
  Content-Type UNSET so `requests` writes the multipart boundary. Live: a 312 KB
  `Procesio.CustomActions.ProcesioWebApi` nupkg installed and returned an id.
- **Delete / uninstall:** `DELETE /api/actions/{id}` (+ `workspaceid`) → 200. Perm `CustomActions.Delete`.
- **List custom:** `GET /api/actions/node?getFullAction=true&isCustom=true` → `{"actions":[...]}`
  (custom only; each has `isProcesioAction:false`). `GET /api/actions` = the FULL catalog
  (built-in + custom). A freshly-uploaded action's `name` is empty until configured in the designer.
- `POST /api/actions/event` calls are in-DESIGNER config (output mappings while editing the
  action), NOT package management — intentionally out of scope for the lifecycle tool.

### AI Decisional action + AI OpenAI Compatible credential (2026-07-01 — 3 exports + live-verified)
- **Action `AI Decisional`** (`actionId 772aac51-…-30001`). Params: Select AI Configuration
  (credential, template `27272727-…-aaaa`), Model (text), Endpoint (select `1`=Chat Completions
  / `2`=Responses), User Prompt (code-editor, `<%var%>`), Timeout, LLM Response (datatype OUTPUT,
  `dataTypeId 0317bfee-…-1221`) + an **Extra AI Configuration side-panel FLATTENED at runtime**
  into Temperature / Top P / Max Output Tokens / Presence Penalty / Frequency Penalty / Seed /
  Store (ids `…30116–30122`). No new Swagger surface — it runs through the normal process endpoints.
- **Bespoke type `ai-decisional-case`** (Cases, `…30124`): RUNTIME Parameter Value =
  `[{id, actionid, condition:<NL string>}]`; DESIGNER config value =
  `[{id, name, target(=actionid), condition, internalId}]` (runtime drops name/internalId, renames
  target→actionid). Default (`…30125`, `decisional-default`) = the target action id; each case + the
  default gets a branch Port (default `Data:{isDefault:"default"}`). In the builder: `_build_decisional`
  handles the AI variant (string condition), `_ai_decisional_cases_config` mirrors the designer shape,
  `_BESPOKE_REQUIRED` guards it; `action_catalog.json` refreshed to include AI Decisional. Config uses
  `branches:[{name?, to, condition}]` + `{to, default:true}`. Tests: `test_process_ai_decisional_branches`,
  `test_ai_decisional_cases_config_designer_shape`.
- **Credential `AI OpenAI Compatible`** is fully handled by the EXISTING credential builder (dynamic
  `/api/Credentials/types`, no code change). Fields: URL, Key, Value(password), Auth Header Prefix,
  Structured Output Mode(select), Supports Tool Choice/Strict Schema(checkbox), Max Tokens Param Name,
  Context Window Tokens, Max Recommended Input Tokens, Method(GET/POST test), Test endpoint. For OpenAI:
  URL `https://api.openai.com/v1`, Key `Authorization`, Prefix `Bearer `, Max Tokens Param Name
  `max_completion_tokens`, test **Method GET + `/models`** (POST /models → 405).

### Running a process with a File INPUT variable — verified live (2026-07-03)
The one-call `run` endpoint can't carry file bytes; use the three-step sequence
(shipped as the **transcribe** tool's pipeline, `tools/transcribe/pipeline.py`):
1. `POST /api/Projects/{templateId}/instances/publish` — body = payload where the
   file var carries METADATA only: `{"audioFile": {"path":"","size":N,"mimeType":
   "audio/ogg","name":"f.ogg","id":"<client-generated GUID>","hash":""}}`.
   Response is a flat object — read **`id`** at the top level (NOT nested under
   `flows`); it also echoes all `variables` incl. process-var defaults.
2. `POST /api/File/upload/flow` — multipart part **`package`** = the bytes; ids go
   in HEADERS: `flowInstanceId`, `flowTemplateId`, `variableName` (var NAME, not id),
   `fileId` (= the GUID you put in the publish payload). Returns the bare fileId
   string as the whole JSON body.
3. `POST /api/Projects/instances/{instanceId}/launch` — body
   `{"flowTemplateId": <templateId>, "connectionId": null}` → `{"instanceId": ...}`.
Then poll `GET /api/Projects/instances/{id}/status?flowTemplateId=...` —
`instance.status`: 30 running, 50 finished, 40 finished-with-errors, 6 stopped.
`GET /api/Projects/instances/{id}/output?flowTemplateId=...` returns
`{"instance": {"instanceId", "status", "variable": {<outputVarName>: <value>, ...},
"error": []}}` — output vars are keyed BY NAME under `instance.variable`.
Verified against a Speech2Text process with a workspace-scoped api-key profile — an API key CAN publish/upload/launch/read.
Note: `GET /api/Projects/{id}` wraps the template as `{"flow": {...}}`.

---

## `Data Store` — what builds today, and the two properties that do not (2026-08-31)

The `Data Store` action performs row-level operations on a Data Store table. Its
REST surface is **not in the tool's endpoint index** but the endpoints exist:

| Call | Behaviour |
|---|---|
| `GET /api/DataStore` | lists the workspace's tables (paged) |
| `POST /api/DataStore` `{"name": ...}` | creates one; system columns (`CreatedOn`, `UpdatedOn`, `CreatedById`, `UpdatedById`) are added automatically |
| `PUT /api/DataStore` `{id, name, columns:[...]}` | sets the columns. **At least one column must be `isPrimaryKey: true`** or it 400s |
| `DELETE /api/DataStore/{id}` | deletes it. **A Data Store IS deletable**, unlike a used Custom Action |

A column: `{"columnId": null, "name": ..., "dataTypeId": ..., "isList": false,
"isPrimaryKey": bool, "isRequired": bool, "isSystemColumn": false}`.

**What builds from the process builder:** a **SELECT with no `Where`**.
`Total Count` must bind an **integer** variable — a `number` variable fails BE
validation with a data-type mismatch, the same rule as `Response Status` on Call
API. `Result Rows` binds a json variable with `isList: true`.

**⚠ What does NOT build: `Set Values` (INSERT/UPDATE) and `Where` (filtered
SELECT/UPDATE/DELETE).** Both properties carry a serialisation the API does not
describe — `"options": null` and no sub-structure, in the bundled catalog AND in
the live `GET /api/Actions?getFullAction=true`. Every shape tried returns one
generic back-end error:

```
{"valid": false, "errors": "Nullable object must have a value."}
```

Shapes tried and rejected: the Decisional case shape `[{id, condition:[{id,
operator, logicOperator, leftOperator, rightOperator, auxOperator}]}]`, the same
without `auxOperator`, the same with `columnId`/`attribute`/`dataTypeId` added, a
flat condition list, `[{columnId, value}]` for Set Values, and the document-mapper
runtime row `[{id, source, destination}]`.

**The front-end validator is SATISFIED by the document-mapper row shape** (FE
error count drops to zero) **while the back end still refuses**, so FE and BE
disagree about the format and the FE gate cannot be used to search for it.
`flowmodel/fevalidation.py` maps `data-store-mapper` onto the document-mapper
validator and `data-store-decisional` onto a list whose first element carries a
`condition` list — that is the FE's view and evidently not the BE's.

**To recover the format:** build one INSERT and one filtered SELECT in the
designer UI, save, then `GET /api/Projects/{id}` and read the two `Parameters`
entries verbatim. Spec on file:
`todo/procesio-datastore-mapper-and-where-format.md`.

### ⚠⚠ A Node's `<%i%>` INLINES THE VALUE AS RAW TEXT (2026-08-24)

> **NEVER INTERPOLATE A STRING INTO A NODE. PASS ONE JSON OBJECT AND READ FIELDS FROM IT.**

An OBJECT inlines as valid JS. A STRING inlines **unquoted** and breaks the script, and
the origin makes no difference: payload value, json variable, string variable, or a
previous action's output all behave the same.

| binding | result |
|---|---|
| `json` var <- object | works, `typeof` = `object` |
| `string` var <- `"hello"` | `hello is not defined` |
| `json` var <- plain string | `Unexpected identifier` |
| `json` var <- JSON-encoded string | `Unexpected identifier` |

⚠ **Quoting the placeholder in the code (`var t = "<%0%>";`) is NOT a safe workaround.**
It passes on plain text and fails on real documents:

| input contains | result |
|---|---|
| a double quote | syntax error |
| a newline | syntax error |
| **a backslash** | ⚠ **SILENTLY WRONG**: `C:	emp` came back with `	` read as a TAB |

The working shape is one JSON object per Node, unwrapped in the body:

```js
var __i = <%0%>;
var text = __i.__t, sid = __i.__s;
```

⚠ **The mapper is NOT affected.** `Set Values` and `Where` bind variables as operands,
not as JavaScript, so string variables are fine there. Only JS interpolation breaks. A
loop body therefore needs small "pick" nodes that turn object fields into plain string
variables the mapper can bind.

### ⚠ A `For Each` needs its FULL parameter set, and TWO outgoing edges (2026-08-24)

⚠⚠ **AND THE BODY'S LAST ACTION MUST RETURN TO THE FOR EACH NODE.** The back end
demands the last body action have an output port, and it is tempting to send it onward to
the next node (which is also what auto-chaining does). That wiring makes the loop run
**exactly ONE iteration**, silently: status 50, no errors, and only the first item
processed.

```
Value -> Write token map -> Join        1 of 5 rows written, status 50, no error
Value -> Write token map -> For Each    5 of 5 rows written
```

⚠ **It fails as a wrong ANSWER, not as an error.** A document with one entity round-trips
perfectly and a document with five silently loses four. Test any loop with N > 1 before
believing it.

⚠ A first diagnosis of this blamed loop-carried variable scope ("a For Each body cannot
accumulate across iterations"). That was WRONG: the loop had never run twice, so
accumulation was never exercised. Whether it works is **NOT ESTABLISHED**.

**On using a `Decisional` as a hand-rolled loop instead:** it costs about **+2 actions per
item** (the Decisional plus an increment node) where a For Each costs none, and
`actionsConsumed` is the meter that moves. It also runs into the recorded constraint that
two Decisional branches cannot target the same node. And it would not have helped here:
the defect was topological, so a hand-rolled loop wired the same way fails the same way.
**Where the work can be done without a loop at all, that is cheaper than either** - one
filtered read plus one Node has a CONSTANT action count regardless of document size.

⚠ **Omitting `Action start time` (declared default `2010-01-01T00:00:00.0000000Z`) makes
the loop fail IMMEDIATELY with `Foreach timeout exceeded!`** The message names a timeout;
raising the timeout to 600 changed nothing and the error still fired at once. `Zero based
list index` defaults to `-1`. This is the runtime counterpart of the designer defect
below: a partial parameter set breaks BOTH surfaces.

Topology, learned by elimination against the back-end validator:

| wiring | back end says |
|---|---|
| body entry only | `too few output ports` on the For Each |
| continuation only | `too few input ports` on the first body node |
| **both** | accepted |
| both arriving at `Stop` | `too many input ports` — **merge them with a `Join`** |

Also confirmed: **`Total Count` must bind an INTEGER variable**; a `number` fails BE
validation with `Data type mismatch ... TotalCount`.

### ⚠ JS OFFSETS ARE UTF-16 CODE UNITS, SO A PYTHON ORACLE MUST NOT SLICE BY THEM

A detector running in a Node action reports `start`/`end` as **UTF-16 code units**. Python
strings are code points. One astral character (an emoji) makes them differ by one per
character:

```
text with one emoji   python len 33, JS utf-16 length 34
engine reports        start 7, end 30
python slicing at 7   lands one position late and leaves a stray character
```

⚠ **The PLATFORM round trip is correct; the PYTHON-side comparison is what breaks.** A
differential oracle that slices by these offsets reports a false mismatch on any document
containing an emoji. Slice by UTF-16 units (`s.encode('utf-16-le')`, offset*2) or compare
on the JS side.

### ✅ RESOLVED (2026-08-24). The `Where` format (`data-store-decisional`)

Recovered the same way as the mapper: by reading a filtered SELECT a person built in
the DESIGNER, then proved through the API.

```json
[{"id": "<GUID>",
  "condition": [{"id": 0,
                 "operator": "EQUALS",
                 "logicOperator": 0,
                 "leftOperator":  {"value": "<COLUMN NAME>", "variable": []},
                 "rightOperator": {"value": "<%0%>",
                                   "variable": [{"id": 0,
                                                 "variableId": "<guid>",
                                                 "attribute": null}]},
                 "auxOperator": null}]}]
```

- the OUTER element carries a **GUID string** `id` and a `condition` LIST; each condition's
  `id` is an **int**
- `operator` is a **STRING NAME** (`EQUALS`), not a numeric code
- **`leftOperator` is the COLUMN NAME** in `value` with an empty `variable` array
- **`rightOperator` is a process variable** via the `<%i%>` placeholder plus its own inline
  `variable` array, or a literal in `value` with `variable: []`
- the PARAMETER itself carries `"variable": []`; the variable list lives inside the operand
- `Where` sits on tabPropertyId `...a106` and applies to `SelectRows`, `UpdateRows`,
  `DeleteRows`

**Measured through the API**, not just saved: a reader that returned all 18 rows returned
exactly 1 for an existing key and 0 for a key that cannot match. Proving only the hit would
be satisfied by a SELECT that happened to return one row.

### ⚠ THE RULE BOTH RECOVERIES TAUGHT, and it is now twice

> **AN OPERAND IS AN OBJECT `{"value": ..., "variable": [...]}`, NEVER A BARE STRING.**

E-45 recorded this exact outer `Where` shape as **tried and rejected**. It had the outer
shape right and the OPERANDS wrong. The same block spent fourteen attempts on the mapper by
varying field NAMES while holding the value SHAPE constant. **When a wire format is refused,
vary the SHAPE of the operands before varying any more names, and recover it by reading a
live example from the designer rather than guessing.**

### ⚠ A Data Store action's sub-fields are GATED ON THE OPERATION VALUE

`Set Values` renders only for `InsertRows`/`UpdateRows`; `Where` only for
`SelectRows`/`UpdateRows`/`DeleteRows`; `Page Number`, `Page Item Count`, `Sort By`, `Desc`,
`Result Rows`, `Total Count` only for `SelectRows`. Options are
`SELECT->SelectRows`, `INSERT->InsertRows`, `UPDATE->UpdateRows`, `DELETE->DeleteRows`.

⚠ **Storing the dropdown LABEL instead of the VALUE suppresses every dependent field.**

### ⚠⚠ INSTRUMENT RULE: A PERMISSIONS FACT COMES FROM THE ASSIGNABLE ROLE MODEL

> **Establish a permissions fact from `GET /api/UserPermissions/entities` (the
> assignable role model), NEVER from a Swagger `Permission required:`
> annotation — and NAME THE SOURCE LAYER in the finding.**

The two layers disagree in wording and both are accurate about themselves:

| layer | reports |
|---|---|
| **assignable role model** | 15 entities, including `DataStoreSchema` (#14) and `DataStoreRows` (#15) |
| endpoint annotation | `DataStore.Read` / `DataStore.Write` |

⚠ **This has now flipped the record twice.** A note asserting the split was
withdrawn on the strength of endpoint annotations, then re-instated on the
strength of the role model. Neither reading was wrong about the layer it looked
at; the error each time was **inferring across layers** — reading a name or an
annotation as evidence about a thing it does not describe.

⚠ **Why this is not housekeeping.** The assignable model is what a customer's
admin actually grants against, so it is the only layer that answers "what can
this principal be limited to". **Any isolation or least-privilege claim rests on
it**, and anything going to counsel must be **read from the live role model and
DATED**, never carried forward from a block report.

### ⚠ AN API KEY INHERITS ITS OWNER'S AUTHORISATION. IT CARRIES NO SCOPE OF ITS OWN.

Establishing this BEFORE minting a key changed what provisioning means.

| can it be limited to one WORKSPACE? | ✅ **YES.** Keys are bound to the workspace they were created in |
|---|---|
| can it be limited to one PERMISSION? | ✅ **YES, but only via the OWNER.** `DataStoreRows: Write` with everything else `None` is expressible |
| does the KEY itself carry a scope? | ⚠ **NO.** On use the gateway "loads the owning user's profile and authorization" |

⚠ **So a key minted by an Owner is an OWNER key** — Admin on all 15 entities,
including `Credentials`, `ApiKey`, `ProcessDesigner` and `Workspace`. A narrow
key requires a **dedicated service user** holding only the roles it needs.

⚠ **And creating that user needs an EMAIL INVITATION** (`POST
/api/Workspace/invite` takes a `SimpleEmailDto` and answers "The invitation was
sent"), so it is an out-of-band step with a real mailbox, not an API call that
completes on its own.

**The provisioning shape for a credential that lets a workspace act on itself:**

1. invite a dedicated service user to that workspace
2. grant it `DataStoreRows: Write` and `None` on the other fourteen entities
3. mint the API key AS THAT USER, in that workspace
4. store the key in the credential, never in a file

Limit 25 keys per user per workspace, and the plaintext value is returned
**once** on creation and never again.

### ✅ `POST /api/DataStore/{id}/rows` IS WHOLE-BATCH ATOMIC (2026-08-24)

The batch endpoint takes `DataStoreRowsDto` with `Rows` as an ARRAY, and its
failure semantics are the property that decides whether it is usable:

| a CLEAN batch of 100 | **100 rows land** |
|---|---|
| a DUPLICATE key at position 47 of 100 | **HTTP 409, ZERO rows written, the store unchanged** |

⚠ **Nothing partial.** That is the safe answer: the caller fails loudly and
retries the whole batch. A partial prefix would have been the dangerous one for
a token map, because a row that never landed leaves a token with no map entry,
and restore then returns a document with placeholders still in it and **reports
no error**.

⚠ **The clean control is what makes the failing case readable.** Without
"100 lands 100" first, "0 landed" is indistinguishable from a batch-size limit.

**Measured ceiling:** no break to **5,000 rows / 1.06 MB** in one call (8.1 s).
E-26 had measured no size break to 100 KB EMBEDDED, but an array is a different
shape — many small objects rather than one long string — and it scales further.

| rows | 100 | 500 | 1000 | 2500 | 5000 |
|---|---|---|---|---|---|
| bytes | 21 K | 105 K | 212 K | 530 K | 1.06 M |
| landed | all | all | all | all | all |

**Measured cost, at a hundred and not extrapolated:**

| route | actions | wall clock |
|---|---|---|
| per-row loop (`InsertRows` in a `For Each`) | **406** | 13.4 s |
| one batch call | **1** | 3.2 s |

⚠ **A batch write from a PROCESS needs a credential the loop does not**, and
`export` EXCLUDES credentials by default, so every receiving workspace has to be
provisioned with one. That is a deployment step the loop route does not carry,
and it belongs in the cost of the decision rather than discovered at handover.

### ⚠ `InsertRows` TAKES ELEMENT 0 OF A LIST. THERE IS NO NATIVE BATCH WRITE.

A `Data Store` action with `InsertRows` whose `Set Values` mapper binds **LIST**
variables, given five distinct keys, wrote **one row**:

```
status 50, affected = 1, one row in the store, actionsConsumed = 1
```

⚠ **It does not error.** It silently takes the first element, so a caller
reading `status` or even `affected` against its own expectation sees a plausible
number rather than a refusal. Judge on the STORE COUNT.

The consequence is a cost shape, not a style point: one write per entity means
**4 `actionsConsumed` per entity**, so a 100-entity document costs ~406 actions
to tokenise against 2 to restore. The API DOES batch
(`POST /api/DataStore/{id}/rows` takes `Rows` as an ARRAY), so a `Call API`
action is the only route to a constant cost, at the price of a credential, a
hop and a Decisional.

### ⚠ REPORT THE AMBIGUITY RATHER THAN PICKING A WINNER

Two registers can claim the same value on BOTH pattern and checksum
(RO_CNP/SI_EMSO at 13 digits; Baltic/HU_SZEMELYI at 11). Building a
discriminator is the expensive answer, and it may be to the wrong question.

**Check first whether the class drives a POLICY difference.** Measured here:
both pairs are identical on `class` and on `reversible`, so nothing downstream
forks on which one wins. Where that holds, `"personal code, one of RO_CNP or
SI_EMSO"` is **more accurate than asserting either**, costs nothing, and needs
no discriminator. Build discriminators only where a policy actually forks.

### ⚠ A GATE THAT CHECKS A CONTAINER HAS NOT CHECKED ITS CONTENTS

The load gate asserted the OUTER validation kind and never the nested
`selector`, so an unimplemented selector loaded and answered wrongly instead of
refusing. This is the same shape as a check that a key is GONE standing in for a
check that two copies MATCH: in both, the container was inspected and the
contents were not.

**Walk every nested kind a spec can carry, and prove the refusal with a
falsifier PER LEVEL, not per gate.**

### ⚠ VERIFY A FIXTURE CONTAINS WHAT IT CLAIMS BEFORE MEASURING ON IT

A cost harness generated five identifier values of the wrong length, the
document contained ZERO valid entities, and the run was reported as "five
entities". The number was a floor wearing a measurement's clothes.

**A fixture claiming N must be minted through the validator or COUNTED first. A
generator is not evidence about its own output.** `UC7/build/fixture_guard.py`
is the shared, tested helper; it also raises on the fail-closed sentinel rather
than counting `-1` as a number.

### ⚠⚠ BUILD THROUGH THE BUILDER. A RAW PUT IS A DEBUGGING INSTRUMENT.

The consequences of hand-building a process through `put-projects` are now all
measured, and they compound:

| an empty `customData.configuration` | the designer CANNOT OPEN the process |
|---|---|
| a partial `parameters` set | a `For Each` fails instantly with a misleading `Foreach timeout exceeded!` |
| both together | the EXPORT re-spells the Data Store mapper, so the pack ships a process that cannot run |

A process built through `dto/process/builder.py` carries a full
`customData.configuration` and exported with the mapper INTACT in the accepted
`column`/`source` spelling; a hand-built one exported re-spelled. So the export
defect E-47 found looks like a CONSEQUENCE of hand-building rather than
unconditional platform behaviour.

> **Build through the builder. Use a raw PUT to inspect or to control an id that
> the builder cannot express, and treat anything it produces as unshippable
> until re-read.**

E-45 used a raw PUT legitimately, to pin ids. That is the exception, not the
pattern. `procesio repair-datastore-mapper` stays in the shipping path
regardless: it is idempotent and costs nothing on a correct pack.

### ⚠ A FAIL-CLOSED COMPONENT REPORTS FAILURE IN ITS OUTPUT, NOT AS AN ERROR

The UC-7 detection engine returns `entity_count: -1` with the message in
`config_version` on any internal error, by design, so a consumer can never
mistake a broken detector for a clean zero. ⚠ **A harness that reads
exceptions therefore sees SUCCESS.** Reading `ok`/`err` instead of the sentinel
reported eighteen false zeros in one run and briefly convicted a working
evaluator.

**Read the sentinel the component documents, not the transport's idea of an
error.**

### ⚠ A FAIL-CLOSED GATE MUST REACH NESTED SPEC KINDS

The engine asserts every DECLARED validation is IMPLEMENTED and throws at load
otherwise. It checked the OUTER kind only. A spec whose nested `selector.kind`
was unimplemented therefore LOADED and produced a **wrong answer instead of a
refusal**, which is the exact failure the gate exists to prevent, one level
down.

**A gate that validates only the top level of a spec is not fail-closed.** Walk
every nested kind the spec can carry, and prove the refusal with a falsifier per
level, not per gate.

### ⚠ AN API-BUILT ACTION WITH A PARTIAL PARAMETER SET IS UNOPENABLE IN THE DESIGNER

A Data Store action built through the API carrying only the parameters it needs (2) could not
be opened in the designer at all. The panel reported:

```
Unable to find current action configuration. Please check Toolbar > Custom Actions tab.
```

⚠ That message names Custom Actions and is **misleading**: the template id was correct, the
action is `isProcesioAction: true`, and the same action dragged fresh from the palette
rendered perfectly with **11** parameters. The designer appears to require an entry for every
setting it would render, not just the ones that carry values.

⚠ **This ships.** A customer receiving a pack built this way gets processes they cannot
open or edit, and the error tells them to go and reinstall a custom action that does not
exist. When building a process through the API, write the FULL parameter set.

### ⚠ RESOLVED (2026-08-24). The mapper row format

The mapper row deserialises into `Domain.Models.CallSubProcess.MapFromVariables`,
so **the back end reuses the Call SubProcess variable-mapping model**. Reading a
live Call SubProcess action's rows and applying that shape is what recovered the
format; varying field NAMES while holding the value SHAPE constant does not find
it, because the answer is a different shape rather than a different name.

```json
{"id": 0,
 "source": {"value": "<%0%>",
            "variable": [{"id": 0, "variableId": "<guid>", "attribute": null}]},
 "column": "<COLUMN NAME>"}
```

- **`column` is resolved BY NAME, not by id.** `document` as the field name gives
  `column reference cannot be null or empty`; `column` holding a GUID gives
  `does not match any Data Store column`; `column` holding the name resolves.
- **`source` is an OPERAND OBJECT carrying its own inline `variable` array**, and
  the `<%i%>` placeholder index matches the `id` INSIDE that array — not an index
  into a variable list on the parameter.
- **The operation is the option's VALUE, not its label.** `INSERT` saves happily
  and dies at runtime with `Unsupported operation`; the runtime wants `InsertRows`.
- **`Result Rows` must bind a NON-LIST variable.**
- **A `Where` is REFUSED AT CREATE** even though the FE validator accepts it.

### ⚠ `row_key` uniqueness, and why a presence check is not a landing check

A Data Store enforces uniqueness on the primary-key column and answers
**status 40** with `Duplicate key violation: "A row with the specified key already
exists."` The insert does not become an update: **`InsertRows` has no upsert
semantics**, so any writer that may re-write a key needs an explicit read-then-
update rather than a second insert.

⚠ This has a measurement consequence that bit a probe here. Re-running a writer
with a FIXED key leaves the row from the first run in place, so a check of the
form "is the row present afterwards" passes while nothing was written this time.
**Existence alone proves nothing about a particular write; only the row COUNT
moving does.** Give probe rows a per-invocation unique key and assert
`rows_before + n == rows_after`.

### Fidelity and durability, measured

Values round-trip byte-identical **by code point** through a process write and a
separate process read: ASCII, Arabic with combining diacritics, Latin-1 umlauts
and sharp s, and Romanian **comma-below** (U+0218/U+021A/U+0219/U+021B), which is
the pair most likely to be silently normalised into cedilla (U+015E/U+015F/
U+0162/U+0163). Compare by code point, never by eye: the two render almost
identically in most terminals and fonts. Rows also survive across a day, not only
between two runs minutes apart.

### Cross-workspace triggering: PROCESS ids are workspace-scoped too (2026-08-24)

A process id resolves only inside its own workspace; another workspace answers **HTTP 400**.
So **`Call SubProcess` is workspace-local** and cannot invoke a process in another workspace.

**A process CAN make outbound HTTP calls** (`Call API` action), so the cross-workspace
trigger is an HTTP call, not a sub-process call. The natural target is the platform's own
`api/Webhooks/launch/{id}`, which is `[AllowAnonymous]`: no JWT and no API key, with the
**unguessable webhook id as the only access control**. Treat that id as a bearer secret.

⚠ **Diagnosing "can a process call out".** A dead target yields a DNS/connect error NAMING
THE HOST AND PORT while the action still returns its `api_status` / `api_body` / `elapsed_ms`
outputs. That is evidence the HTTP client RAN, not evidence the capability is missing. A
scoring rule of "finished with no errors" answers the wrong question, because the remote
being dead is not a fact about the caller. Distinguish a network-layer failure from a
platform refusal before concluding anything.

**The pattern this enables** where a store must serve several workspaces (it cannot be shared
- see below): the owning workspace hosts the only writer, fronted by a webhook; other
workspaces call that webhook to REQUEST a change. They then need no permission on the store
and no credential, and the owner validates before writing. A mediated write is both the only
option and the safer one. Two caveats: a launch acknowledges the flow STARTED and is not the
outcome (and a non-2xx completes as SUCCESS here), so confirm by reading back; and because the
primary key is unique with no upsert, a retried trigger needs an idempotency key and a
read-then-update on the writer side.

### ⚠ A Data Store id is WORKSPACE-SCOPED, not a global handle (2026-08-24)

A store cannot be shared between workspaces, so one store cannot serve a master workspace
and its sub-workspaces as a single source of truth. Measured by asking ONE store id of
every accessible workspace: **HTTP 404 in five of them**, and the two that hold it return
**different row counts**.

⚠ Different contents under one id means different OBJECTS. This is the only test that
distinguishes them, because an import PRESERVES ids: "a store with that id exists here" is
true in both workspaces and proves nothing. A cross-workspace shared store therefore has to
be built (master holds it and the others read it over HTTP, or it is replicated per
workspace), and neither is a platform feature.

⚠ **A process does not carry its Data Store in an export pack.** The store travels
only when the export request NAMES it; rows never travel. Export a flow without
naming the store and the pack hands the target workspace processes pointing at a
store id it has never had.

### ⚠ An imported process carrying a Data Store mapper CANNOT RUN (2026-08-24)

**THE FIX IS A TOOL ACTION (2026-08-24):**

```
python scripts/run-tool.py procesio repair-datastore-mapper --in pack.procesio --out fixed.procesio
```

Run it on every pack before shipping (`--dry-run` reports what would change).
Idempotent, so it is safe to run unconditionally and becomes a no-op if the export is
ever fixed. Proved end to end: re-broken target, import the tool's output, run, target
store row count moved.

**THE FIX, measured 2026-08-24.** The re-spelling is done by the **EXPORT**: the `.procesio`
pack on disk already contains `document`/`process` and zero `column`/`source`. The damage
precedes the target, so no import-side handling can help.

Two repairs both work, judged on the target store's row count moving:

| | what | verdict |
|---|---|---|
| **A** | rewrite the mapper rows IN THE PACK before import | **works - the design** |
| **B** | re-apply the mapper via `put-projects` AFTER import | works - a workaround |

Prefer **A**: it fixes the artefact before dispatch, needs nothing from the recipient, and
is verifiable before shipping. Keep **B** for packs already shipped.

The transform, per mapper row, is mechanical and **idempotent** (pass through any row that
already has `column`, so it becomes a no-op if the export is ever fixed):

```
{"id": i, "process": "<flowId>.<variableId>", "document": "<COLUMN NAME>"}
  ->
{"id": i,
 "source": {"value": "<%i%>",
            "variable": [{"id": i, "variableId": "<variableId>", "attribute": null}]},
 "column": "<COLUMN NAME>"}
```

In the pack it lives at `Flows[].Actions[].Parameters[].Value` (a LIST, not a JSON string),
and the parameter's own `Variable` stays `[]` - the variable array belongs INSIDE the source
operand.

⚠ When testing a repair, RE-BREAK between the two candidates. Re-importing the original pack
restores the broken mapper; without that control the second repair is measured on a process
the first already fixed and passes for the wrong reason.

The export/import round trip **re-spells every mapper row into the Call SubProcess
wire shape and never translates it back**:

| | in the source | after import |
|---|---|---|
| row keys | `column`, `id`, `source` | `document`, `id`, `process` |
| the column | `"column": "<NAME>"` | `"document": "<NAME>"` |
| the variable | inline `source.variable[]` array | `"process": "<flowId>.<variableId>"` |

Running the imported process in the target then fails with, verbatim:

```
Error while building input model: A Data Store Decisional column reference cannot be null or empty.
```

⚠ **Nothing is lost in the translation.** The column names survive inside `document`
and the variable GUIDs survive inside the `process` composite, and the row count is
unchanged. That is what makes this dangerous: **every structural check passes.** The
import reports success, resource ids are PRESERVED, the store reference resolves to
the target's own store, and the mapper still has all its rows. The defect appears
only on execution, so an inventory-style verification after import will pass on a
process that cannot run.

⚠ **Verify an imported process by RUNNING it, not by inspecting it.** For a store,
the check that works is the row count moving in the target, which is only meaningful
because rows do not travel and the target's store therefore starts empty.

Consistent with the mapper deserialising into
`Domain.Models.CallSubProcess.MapFromVariables`: the transport evidently serialises
it back out in that model's own spelling. Until the transport round-trips the
accepted spelling, shipping a pack requires a post-import step that re-applies the
Data Store mapper in the target. That is a workaround, not the design.

**Do not work around it with a SELECT-all plus in-flow filtering** when the table
is partitioned for isolation: that pulls other partitions' rows into process
variables, which is the leak the partition exists to prevent.

## Call API + publish semantics (learned live 2026-07-30, Livespace PoC)

### `publish` WITHOUT `launch` leaves a zombie instance in "starting"
`POST /api/Projects/{id}/instances/publish` (`post-projects-by-id-instances-publish`)
**creates a process instance in state `1` = "starting" with 0 action runs** and does
NOT execute it. The pair is publish -> **launch**
(`post-projects-instances-by-id-launch`); `run-process` does both internally.

**For a webhook-triggered flow you do NOT need to publish at all** - the webhook
launch publishes + launches on its own (verified: webhook-launched instances land in
status 50 with 7 action runs, `Submitted by: Webhook: <name>`). Calling publish
"to activate it" is a mistake: it just accumulates instances stuck at "starting"
attributed to the API user. They have to be stopped from the UI
(`post-projects-instances-by-id-stop` returned 400 "Stopping process failed" for a
0-action-run starting instance).

Also: publish requires a body (`--body '{}'`) or it 415s; `...instances-by-id-stop`
takes NO `--body`.

### Call API - the full `Request Parameters` wire format
`Request Parameters` (property `...0003`, type `tabs-payload-v2`) is a nested dict:
```jsonc
{"body": {"type": "RAW|X_WWW_FORM_URLENCODED|FORM_DATA|BINARY",
          "value": {"BINARY": "", "FORM_DATA": [],
                    "RAW": {"format": "json", "value": "<raw string, may hold <%N%>>"},
                    "X_WWW_FORM_URLENCODED": [{"key": "k", "value": "v",
                                               "id": "<uuid>", "type": "TEXT"}]}},
 "headers":     [{"key": "Content-Type", "value": "...", "id": "<uuid>", "type": "TEXT"}],
 "queryParams": [{"key": "", "value": "", "id": "<uuid>", "type": "TEXT"}]}
```
Bind it with the builder's **`{"template": <that dict>, "vars": [...]}`** - `_remap`
walks dict/list leaves, so `<%N%>` placeholders inside the nested strings resolve.

Property labels: `Select REST API credentials` (`{"credential": <gid>}`), `Verb`,
`Endpoint`, `Request Parameters`, `Time Out`; outputs `Response Status`,
`Response Body`, `Response Headers`, `Response File`.
- **`Verb` is an OPTION GUID, not a word.** All five recovered live 2026-08-30 from
  **`GET /api/Credentials/verbs/{templateId}`** (pass the REST-API credential template id, e.g.
  `10101010-0001-0000-0000-aaaaaaaaaaaa`) — the catalog serves the `verb` property with
  `options: null`, so this endpoint is the only place the mapping exists:

  | verb | option guid |
  |---|---|
  | GET | `3ab385bd-f8ae-b641-9176-e7db886aec01` |
  | POST | `eb0b6e47-858e-fd43-a616-d8ffc1baec02` |
  | PUT | `f0e5b463-9207-c44d-8ed5-937e5f4aec03` |
  | PATCH | `2e1515c5-06e8-e24d-bc0d-b2c8ae1aec04` |
  | DELETE | `cdf1a1fe-d4eb-e342-87d4-211c800aec05` |

  The ACTION catalog cannot tell you this: the property comes back typed `"verb"` with
  `"options": null` in the bundled catalog *and* in the live
  `GET /api/Actions?getFullAction=true`, which is why this looked undiscoverable until the
  CREDENTIALS route was tried. Name-to-guid resolution has nothing to resolve against there. Sending the word `"GET"`
  passes FE validation, passes BE validation, saves, and then dies at RUNTIME with
  `Http verb is invalid.` on the action — a save-time-clean / run-time-fatal class, so it
  survives every pre-flight check. Until a guid for another verb is recovered from the
  designer, build Call API actions as **POST** and put any parameters in the endpoint query
  string or the request body.
- **`Response Status` must bind an `integer` variable** (`...121212121211`). A
  `number` var fails BE validation with "Data type mismatch ... StatusOutput".
  `Response Body` binds a `json` var (`...121212121220`).

### THE KILLER: credential option properties must be GUIDs
A REST API credential's **`Method`** and **`Authentication method`** are option
properties whose values are **GUIDs**. `credential-create` happily stores a raw
string like `"Method": "POST"`, the credential still saves, but **every Call API
run using it dies at runtime with:**
```
Error while building input model: Unrecognized Guid format.
```
The error names the Call API action, NOT the credential - so it sends you hunting in
the wrong place (cost hours). Correct values:
- `Authentication method`: NoAuth `10101010-0001-0004-0001-cccccccccccc`,
  Basic `...-0002-...`, ApiKey `...-0003-...`
- `Method`: GET `10101010-0001-0002-0001-cccccccccccc` (the credential's Method is
  only used by the *test connection*; Call API carries its own `Verb`)

**Smell test:** after create, `credential-get` -> `status: False` means the test
connection failed. Do not paper over it with `--force`; fix the config until
`status: True`. A `status:False` credential is the tell that a value is wrong.

### Instance introspection via the API is unreliable
`get-instance-status` -> 400/450 when `flowTemplateId` is omitted (see the corrected section below)
"Database requested information not found" for webhook-launched instances. To see a
run's variables, use `run-process --synchronous` (returns `{instanceId,status,
variable,error}`; `status 50` = finished) or read the instance in the UI. Bind an
`Error` output variable on every scripting node so failures surface in `variable`.

### Node scripting can do outbound HTTPS + crypto
(Module availability table: [PROCESIO-NODE-MODULE-WHITELIST.md](PROCESIO-NODE-MODULE-WHITELIST.md). The two files disagreed until 31/08/2026;
that file carried the narrower rule and has been corrected.)
Proven live: `require('crypto')` (sha1) and `require('https')` both work, and an
async `return new Promise(...)` resolves correctly. `fetch` is NOT defined. So a
single Node node can do a full signed API dance - but prefer Call API + a credential
when the point is a maintainable, credential-managed integration.

### Guards added for the three footguns above (2026-07-30)

The notes above describe failures that cost hours; each now has a mechanism so it
cannot recur silently (`tools/procesio/tests/test_guards.py` locks all three):

1. **`dto/credential/builder.py::_resolve_option`** now RAISES `UsageError` when a
   credential property whose options are guid-valued is given a value that is
   neither an option `name`, its `be_value`, nor the guid — instead of storing the
   raw string. The message names the valid options AND the runtime symptom
   ("Unrecognized Guid format"), because the runtime error blames the Call API
   action, not the credential. Checkbox-style (non-guid) option sets still pass
   through unchanged.
2. **`main.py::ADVISORIES` / `_advise`** attach a `warning` to the emitted JSON for
   actions that succeed but leave an unintended state. First entry:
   `post-projects-by-id-instances-publish` explains publish-vs-launch and that a
   webhook-triggered flow needs no publish. Add one line per new footgun.
3. **`flowmodel/fevalidation.py::_default_datatype_check`** adds a `hint` to every
   `TYPE_MISMATCH` warning naming the expected vs actual type ("binds number; this
   property expects integer"). The `text` is unchanged for FE parity.

## Instance history is retention-bound — count and list disagree (verified 2026-08-06)

Three endpoints report on a process's runs and they are NOT consistent:

- `GET /api/Projects/{id}/instances/count` — can return a non-zero count
- `GET /api/Projects/{id}/instances` — returned an empty page for the SAME process
- `GET /api/Projects/{id}/history` — also empty for that process

So a non-zero count is not proof that any instance rows are retrievable: the
count survives the data-retention purge that removes the rows. Treat the count
as an upper bound only, and take `/instances` + `/history` as the authority for
"what can I actually inspect". If both come back empty, the run history is gone
(or the process never ran) — do not keep probing paging.

Paging/filter probing on `/instances` is a dead end when the rows are purged:
`pageNumber` 0 and 1 behave identically (the response always echoes
`pageNumber: 1`), and `filterStatus` accepts only some values — 2, 3 and 4
return **HTTP 400**, while 1 and 5 return an (empty) page.

**Per-process schedules:** `GET /api/Projects/{id}/restricted/schedules` does
NOT return a `schedules` key — it answers with the flow object (id, title,
variables) and nothing else, so it cannot be used to decide whether a process is
scheduled. Use `GET /api/Schedules` (workspace-wide) instead and match on the
`processName` field of each row.

**`GET /api/Actions?getFullAction=true` is about 2x slower than `getFullAction=false`,
and that is all. RETRACTED: the earlier claim that it "hangs for minutes" did not
survive re-measurement.** Measured on a deliberately quiet instance, three repeats
each: `=false` 1.76-1.81s for a 280 KB payload, `=true` 3.55-3.64s for a 794 KB
payload. Twice the time for 2.8x the bytes, with no outliers. Every other endpoint
measured in the same window was also healthy (`check-auth` 1.1s, `list-processes`
0.8s, `GET /api/DataTypes` 0.9s, `GET /api/Projects/{id}` 1.5s, `/restricted` 0.9s,
`POST /api/Projects/validate` 3.0s, `flow-lint` 3.8s, `export` 4.2s).

The stalls that produced the original claim were **contention, not the endpoint**:
concurrent tool invocations competing for one session, which this file already warns
about two paragraphs down ("a killed shell does not kill the tool's Python child").
Diagnose a slow catalog fetch as an orphaned-worker problem first. The DTO builder's
`prepare_ctx` does call this endpoint on every `process-create` / `process-edit`
including `--dry-run`, so it is on the hot path and worth ~3.6s of budget, but it is
not pathological.

**The trap below is unaffected by the retraction and still stands. Do NOT "fix" a
slow catalog fetch by switching to `getFullAction=false`:** `catalog_index(extra=live)` lets LIVE entries WIN
over bundled ones, and the lightweight variant omits `configuration`, so stub
entries would silently replace complete templates and every property binding in the
built DTO would break. The live fetch exists only to pick up custom/connector
actions; a flow built purely from stock actions is served correctly by the bundled
catalog alone.

**A killed shell does not kill the tool's Python child.** Wrapping a long PROCESIO
call in a shell timeout leaves the worker running against the API; several
abandoned workers then compete for the same session. Check for and reap orphans
before retrying a call that appeared to hang. Run the call as `( exec timeout -s
KILL <n> <python> ... )` so the shell is REPLACED by the worker and the kill lands
on the process that actually holds the connection. Because abandoned workers keep
issuing requests for as long as they survive, they are a **plausible (unproven)
contributor to later 403s and to slow/stalling heavy endpoints** on the same
instance — treat a rate-limit or stall that follows a burst of killed calls as
possibly self-inflicted before reporting it as a platform fault.

**Concurrency: a PROCESIO instance is shared across every session and tool run.**
Heavy writes from ONE working session (form create/delete, process-edit) coincide
with heavy READ endpoints stalling for another — the full-object reads
(`GET /api/Projects/{id}`, `GET /api/Projects/{id}/restricted`,
`POST /api/Projects/validate`, Transport `export`) degrade first and hardest,
while light endpoints (auth, project LIST, flow-lint) stay sub-second throughout.
Before diagnosing a stall as a platform fault, enumerate the OTHER live processes
hitting the same instance (`ps` for concurrent tool invocations, including other
agent sessions and other workspaces/profiles) — contention from a parallel session
reproduces the exact same signature and is the cheaper explanation.

## Instance variables: `/status` needs `flowTemplateId`; a 450 means the QUERY was incomplete

**CORRECTED 12/08/2026. The earlier version of this section was WRONG** and is
kept only as a warning about how the error text misleads. It claimed that
retrospective instance-variable reads fail platform-wide. They do not.

`GET /api/Projects/instances/{id}/status` **requires a `flowTemplateId` query
parameter.**

| Call | Response |
|---|---|
| `/api/Projects/instances/{id}/status` | HTTP 400, `[{"statusCode":450,"value":"Database requested information not found.","target":"flow"}]` |
| `/api/Projects/instances/{id}/status?flowTemplateId={processId}` | HTTP 200 with the full record, variables populated |

So the 450 reports an **incomplete request**, not a missing record and not a
retention purge. Variables, including the base64 content of submitted input
files, are readable from a completed instance for as long as the record is
retained. The tool's own poll loop passes `{"flowTemplateId": args.id}` on this
route, which is why polling during a run always worked while ad-hoc reads did
not.

Two related claims in the earlier version also did not reproduce and are
withdrawn: `/instances/{id}/output` returns HTTP 200, not a 500 wrapping a 403;
and `/api/Resources/analytics/instances/{id}/details` can return an empty array
even for an instance that ran (it is per-workspace, see the
ResourceTrackingConfig note).

**The lesson worth keeping:** an error string naming a database and a missing
record sent several sessions after a retention or existence problem, when the
request was simply missing a parameter. Before believing a 450 here, add
`flowTemplateId` and read it again.

Capturing variables from the synchronous run response is still the simplest
route when you already have the response in hand, but it is a convenience, not a
necessity.

## Fingerprinting a flow: hash it CANONICALLY, never the raw bundle

A `.procesio` export carries a **top-level `TimeStamp` recording when the export
ran**, so two exports of a byte-identical, untouched flow produce **different**
sha256 digests. A hash of the whole bundle is therefore not a fingerprint: it
cannot reproduce, and any change-detection gate built on it fires on every run.
Verified 12/08/2026 — two exports taken 11 minutes apart, no edit between them,
differed only in `TimeStamp` (`…05:02:12` vs `…05:13:26`) yet hashed
`097d4975…` vs `a5309e50…`.

**Fingerprint like this instead:** parse the bundle, drop the top-level
`TimeStamp`, re-serialise with sorted keys, hash that. Corroborate with two
independent signals that do NOT move on their own — the flow's `updatedOn`
(compare to the second) and the action count. In the same test the canonical
digests matched exactly (`4a03a97c…`) while `updatedOn` and action count were
identical, which is what proves the process was untouched.

**Operationally:** treat a raw-bundle hash mismatch as a defect in the
measurement until the canonical hash disagrees too. A gate that fires on every
run trains people to wave it through, which costs more than having no gate.

## Verifying a run actually executed: both signals LAG, and null is not zero

Terminal status carries almost no information here (a run can report finished
having executed nothing), so execution must be verified separately. Two signals
exist and **both are eventually consistent**, so neither is usable as an
immediate check straight after a run:

- `GET /api/Resources/analytics/instances/{id}/details` — returns an EMPTY array
  for a few seconds after a run that demonstrably executed, then fills in with
  real per-action rows. Verified 12/08/2026: two runs read as empty immediately
  and, re-read moments later, both returned `Node totalRuns 3` and
  `File To Base64 totalRuns 1`.
- `/history` — the instance simply is not there yet for a short window after the
  run, so `actionsConsumed` reads back as **`null`**.

**`actionsConsumed: null` means the instance is not yet in `/history`. That is
ABSENCE OF EVIDENCE, not evidence of zero execution. Only an explicit `0`
counts as a void signal.** Treating null as zero condemns healthy runs.

**The void test:** a result is void only when analytics is empty **on re-read**
AND `actionsConsumed` is an explicit `0`. One signal alone never settles it,
and neither signal settles it immediately.

**The reliable immediate source is the synchronous RUN RESPONSE**, which returns
the full `variable` map at execution time. Reading variables back later also
works, provided `/instances/{id}/status` is called WITH `flowTemplateId`; a 450
there means the query was incomplete, not that the data is gone.

## Action catalog schemas: the list hides them, the detail exposes them

`GET /api/Actions` (the toolbar catalog) returns each action's identity
(actionId, name, description, ports, permissions, documentation URL) but its
`prototypes` array can come back EMPTY, so the list is NOT a source for an
action's parameter schema. `GET /api/Actions/{actionId}` returns the full
side-panel configuration DTO (grouped `configuration[].settings[]` with
`dataTypeId`, `label`, `type`, `direction`, `isRequired`, `expects`, `isList`,
`rowId`), i.e. the real I/O contract. Verified 12/08/2026 against the "Data
Store" action. Rule: enumerate with the list call, read schemas with the detail
call, never assume the list carries them.

## DataStore (live from 12/08/2026)

- One toolbar action, verbatim name **"Data Store"** (grouping
  `DataStoreConnector`): row-level insert / select / update / delete on a Data
  Store table, with Where / Sort By / paging settings and outputs Result Rows,
  Total Count, Affected Rows. Docs: docs.procesio.com/how-to/data-store.
- Table management and API-side queries are a separate REST surface (in live
  swagger v1.19, not necessarily in older bundled copies): `/api/DataStore`
  CRUD, `/{id}/column`, `/from-json`, `/from-data-model`, `/{id}/rows`,
  `/{id}/rows/filter` (POST, the queryable-ledger read), import/export jobs,
  plus read-only `/api/Form/dataStore/{id}/rows[...]` variants.
- The bundled endpoint index predates such releases; for anything released
  after the bundle, grep the LIVE swagger.json rather than `list-endpoints`.

## API-key scoping is strict: cross-workspace reads answer 403

A workspace-scoped API key returns **HTTP 403 "Unauthorized"** for a request
carrying any other `workspaceid`, even for read-only listings the key's user
could see in the UI. (`GET /api/Workspaces` still lists sibling workspaces the
account can see; visibility in that listing does not grant request scope.)
Consequence: cross-workspace probes/reads need a userpass profile with
`--workspace-id`, and any cross-workspace CALLER of a process integrates via
Call API with an API key for the TARGET workspace, never by assuming shared
scope. Verified 12/08/2026.

## Recording state is per-workspace and off by default on fresh workspaces

`GET /api/ResourceTrackingConfig` (with the workspace scope) returns
`isRecordingEnabled` for the ACTIVE workspace; a freshly created workspace
reads `false` until someone enables recording in workspace settings. Any plan
that relies on instance recording must probe this flag per workspace, never
assume it. Verified 12/08/2026.

## Node action injection RAW-INSERTS the value — never inject free-form text (2026-08-08)

`<%N%>` in a Node's `Code` template is a **literal text splice**, not a JSON-encode. This has a sharp consequence for which variables are safe to inject:

- A variable whose value is **valid JSON** (a sheet read `{"values":[...]}`, an API response) is safe bare-injected: `var x = <%0%>;` becomes `var x = {"values":[...]};` — a valid JS literal. This is why `PICK`/`PARSE` work.
- A **plain-text / free-form** value is NOT safe. `var g = <%0%>;` with the value `hello "x"\nworld` splices in raw → `var g = hello "x"[newline]world;` → **syntax error**, and the Node silently returns null. Even an **empty** value breaks it: `var g = ;`. (Confirmed: a Google-Doc export injected bare produced an empty `textBody`, so the downstream Gemini call got no `contents` and returned 400.)

**Rule:** never inject Doc/HTML exports, user prose, or any free-form string into a Node. Source arbitrary text from **inside a JSON structure** — e.g. put the text in a **sheet cell**, read the row via the Sheets API, and reference it as a field of the safely-injected object (`bp.brand_guide`). The object carries the escaping for you. (This is why the social brand *guide text* lives in a `brand_packs` sheet column, while the Drive folder holds only binary assets like reference images.)

If a possibly-empty value must be bare-injected anyway, wrap it so empty stays valid syntax: `var v = (function(){return <%0%>;})();` (empty → `return ;` → `undefined`).

**Addendum (2026-08-08):** even a JSON-ENCODED string is not enough when the value transits process
variables: **the platform converts the two-character `\n` escape into a REAL newline** before the Node
splice (same family as the `join('\n')` collapse), un-terminating the injected literal — while `\"`
survives intact (verified by bisection: `"hello"` OK, `"has \"inner\" quotes"` OK, `"two\nlines"` dies).
Transport recipe for free-form text into a process input: strip/replace backslashes, JSON.stringify,
then replace the `\n` sequences with a token (e.g. `%%NL%%`); the receiving Node bare-injects inside an
empty-safe IIFE `(function(){return <%N%>;})()` and decodes with `split('%%NL%%').join(String.fromCharCode(10))`.
Live example: `social_media/Set Decision`'s `editedCopy` (multi-line captions with quotes land intact).

## Call API — absolute URLs, response outputs, LinkedIn recipe (2026-08-10)

- **An absolute URL in `Endpoint` does NOT bypass the credential base** — the base is prepended and
  the call goes to the wrong host (seen as a 405 from the base host). To call a DIFFERENT host than
  the credential's base (e.g. a pre-signed upload URL), create a SECOND credential whose base IS that
  host and pass only the PATH+QUERY as the endpoint. Endpoint-with-query is safe when the credential
  injects its key as a HEADER (the double-`?` clash only exists with query-param key injection).
- **`Response Status` binds an INTEGER variable** (config var type `integer`) — binding a text var
  fails BE validation with "data type mismatch" (statusCode 142). `Response Headers` binds a text/json
  var and is the ONLY place some APIs return the created id (LinkedIn `/rest/posts` → `x-restli-id`
  header, empty body). `Response File` turns the body into a File var (works with Drive
  `files/{id}?alt=media` for real binaries — do NOT use the public thumbnail endpoint from code;
  it 302s into HTML error pages for non-browser clients).
- **Path parameters containing URNs must be pre-encoded** (`encodeURIComponent` in a Node) before
  endpoint injection — raw `urn:li:...` colons in the path 400.
- **LinkedIn REST versioning:** `LinkedIn-Version` header is REQUIRED (YYYYMM); an inactive version
  fails with 426 NONEXISTENT_VERSION — probe for a live one (202601 verified live 2026-08-10) and
  expect to bump it over time. `X-Restli-Protocol-Version: 2.0.0` alongside.
- **Delay action shape** (proven in production): `{"Delay Type": "1", "Delay value": {"value":
  {"value": "<n>", "interval": 2}}}` = n MINUTES.

## Empirical reliability profile (2026-08-11)

Learned driving a form + its processes hard against the live Web API. The operating
doctrine distilled from this lives in `agents/procesio/PROCESIO-API-RELIABILITY-DOCTRINE.md`
(`run-agent.py procesio guidance --topic reliability`); this section records the raw
findings and the design decisions they drove.

**What stalled, what didn't.** With multiple calls in flight (synchronous `run-process`
executions mixed with definition GET/PUTs), `GET /api/Projects/{id}` (~120 KB) and
`GET /api/FormTemplate/{id}` (~420 KB) stalled for minutes and had to be killed;
strictly sequential calls to the same endpoints then succeeded. Consistently fast
throughout: `POST /api/Projects/{id}/run`, `GET /api/Schedules`, `GET /api/Projects`
(list), `form-set-code`. Stalls were intermittent, not size-deterministic. **Rule:
one PROCESIO call in flight at a time** (doctrine §1).

**Hypothesis verdicts.**
- **No total client deadline — CONFIRMED (root cause).** `requests`' scalar `timeout`
  is a per-read *inactivity* guard, not a wall-clock ceiling: a connection that is
  accepted then dribbles/held never trips it, so a stalled call ran until SIGKILL — no
  structured timeout ever surfaced. Fixed: `reliability.run_with_deadline` imposes a
  class-aware TOTAL deadline (reads ~90 s, writes ~180 s) on a daemon thread →
  `deadline_exceeded`. `run-process` is exempt (a synchronous run legitimately takes
  minutes; aborting client-side does NOT stop the server run).
- **Queueing vs flakiness — UNTESTED hypothesis.** That definition reads/writes queue
  behind saturated execution capacity (finite EEs; a many-action process consuming
  them) is the leading explanation but was NOT proven with a controlled experiment.
  Treat it as a hypothesis. The platform DOES expose the shape that would confirm it —
  `GET /api/analytics/executionEnvironment/concurrency` returns per-workspace
  `instancesInRun` / `instancesInWaiting` / `maxThreads` — but with an apikey and no
  date range it returns a zeroed epoch skeleton (needs a range and/or
  `MasterWorkspace.Read`). Because it is unproven, the fix is NOT a concurrency
  governor; it is the sequential-calls rule plus the deadline that makes any stall
  surface.
- **Empty-body PUT can lie — CONFIRMED.** A `put-projects` returned success with an
  empty body while the change did not persist. Behavioural verification (run the
  process, observe) is the only trustworthy check; a re-read/diff is second best. Never
  trust a write's own echo. `put-projects` now warns on an empty body.

**Workspace is never idle.** Server-side schedules (a dispatcher tick every few
minutes, token refreshers, reconcilers) execute processes around the clock; the client
cannot see them. When latency looks wrong, check `GET /api/Schedules` next-run times
before blaming your own call.

**Guardrails shipped** (all offline-tested; opt-outs `AAT_PROCESIO_NO_DEADLINE=1` /
`AAT_PROCESIO_NO_RETRY=1`): total class-aware deadline; GET-only retry on
`429/502/503/504` + network errors with jittered backoff (POST/PUT NEVER retried — a
retried execution double-runs, a timed-out write may already have applied);
`put-projects` empty-body warning; `form-update` DTO lints (phantom `parentId`,
duplicate id/name, `{"Data":{…}}` wrapping mistake, multiple-select missing `isList`);
`form-set-element-event --replace-action` (replace one action's events, keep the rest
in order — bare `--replace` warns before discarding more than one).

## Custom actions — upload, naming, and Min/Max fields (live-verified 2026-08-10)

**A value-type input with no `DefaultValue` fails at RUN time, and the seed is where it
bites.** The designer instantiates every property when an action is dropped, so a `bool`,
`JObject` or `JArray` with no `DefaultValue` reaches the engine as an empty string. The
platform's `TypeConverter` guarded the empty string only for numeric types, so every other
type threw `Value could not be converted to property TYPE` - a message that names no
property, on an action the designer reports as valid. Seeding a built-in connector has the
same trap from the other side: write `properties.Value` as `NULL` and you drop the
decorator's `DefaultValue`, reproducing the failure in SQL.

Seed `'False'` for a bool, `'{}'` for a JObject and `'0'` for an int. An empty `JObject`
parses and is then skipped when the request is built, so the default changes nothing that
reaches the vendor. Outputs deliberately keep `Value = NULL`: they are not bound on the way
in.

The platform guard has since been generalised, so an OPTIONAL empty input normalises to
null, while a REQUIRED non-nullable value type is rejected with `Input '<name>' is required
but was empty`. Numerics keep their long-standing behaviour of becoming null, because
changing that would alter processes already running.

Learned while installing and exercising an uploaded `.nupkg` connector end to end.

1. **The designer display name comes from the `name` REQUEST HEADER, not the package.**
   `POST /api/actions` takes `name` and `path` as `[FromHeader]` values, and the
   backend assigns `actionTemplate.Name = headers.ActionName`. The assembly's
   `ClassDecorator.Name` is validated as non-empty and then **discarded**. Upload
   without the header and the action installs with an EMPTY name: it appears in
   `/api/Actions/node` but a designer cannot find it in the toolbar. `Description`,
   `Tooltip`, `Shape`, `Classification` and `IsTestable` DO come from the decorator —
   only the name is header-driven, which is why the omission looks like a package bug.
   `customaction-upload` now always sends a name (`--action-name`, defaulting to the
   package stem) and `--icon-path`.

2. **A failed upload still burns the version.** Package validation runs AFTER the
   package is pushed to the internal NuGet repository, so a rejected upload leaves that
   PackageId+Version registered. Retrying the same version fails with statusCode **207**
   ("Failed to upload Action Template package to repository") — which reads like an
   infrastructure fault but means "duplicate version". **Increment the version after
   every failed attempt, not only after a successful one.** Use 3-segment SemVer.

3. **Decorator constraints enforced at upload** (`statusCode` → meaning):
   - `265` / `266` — `Min`/`Max` are accepted only on a **non-nullable `int`**. An
     `int?` is rejected. `261` accompanies it when `Validator.Expects` no longer
     matches the property type.
   - `151` — a literal bound to a `Min`/`Max` property is outside the allowed range;
     rejected by the BACK END, so `--force` cannot bypass it.

4. **A `Min`/`Max` number property is effectively LITERAL-ONLY.** Binding a process
   variable to one produces designer errors `LIMIT_NAN` + `LIMIT_RANGE` (the validator
   evaluates the `<%N%>` binding token as a number). Force-saving past the designer
   does not rescue it: at run time the value **does not arrive** — the platform
   substitutes the property's `Min`, silently. Net effect: any run-time range guard
   inside the action is unreachable, and the field cannot vary per run. When authoring
   a connector, choose designer-enforced `Min`/`Max` with a fixed literal, OR omit
   `Min`/`Max` and guard at run time to keep the field bindable — not both.

5. **An unselected credential is NOT null in the action.** The platform injects an
   `APICredentialsManager` with a non-null `Client`; only `CredentialConfig.Host` is
   empty. Actions that null-check the manager or client will pass the guard and then
   fail deep in the HTTP layer with `Invalid URL: <relative path>`. Check `Host`.

6. **`POST /api/Actions/test` (the side-panel test) returns its result over SignalR**,
   not in the HTTP response — it takes a `ConnectionId`. For headless verification,
   build a real process and run it with `run-process --synchronous`, which returns
   `{instanceId, status, variable, error}` directly. `status` 50 = finished, 40 =
   error, and `error[].errorMessage` carries the action's exception text verbatim —
   which makes it the practical oracle for testing an action's guards.

7. **A public form URL requires a real workspace.** `POST /api/CustomUrl/FormTemplate`
   fails with statusCode **1008** ("Not working on workspace") unless the call is
   scoped with a `workspaceid` header, and the custom URL only resolves when the FORM
   itself lives in that same workspace. A form created in the personal workspace
   (`workspaceId` all-zeros) cannot be published under a workspace custom URL — create
   the whole chain (credential, process, form) inside one workspace when the flow has
   to be reachable by a human.

## Forms: `form-create` takes an AUTHORING CONFIG, never a stored DTO

A form that already exists cannot be handed back to the create route. The two
shapes are different languages, and the gap is structural rather than a missing
field:

| Stored DTO | Authoring config (`dto/form/config.schema.json`) |
|---|---|
| elements carry a GUID `id`, a `configs` array, `parentId` | nested `children`, **no `id` property exists** |
| `theme` = sections of properties | `theme` = flat `{cssVariable: value}` |
| RUN_PROCESS maps are GUID to GUID | wired **by name** |
| `dataModel` stored explicitly | **not expressible**, generated |

The schema sets `additionalProperties: false`, and `dataModel` is not among the
permitted top-level keys, so there is no passthrough. **Rebuilding an existing
form therefore requires a reverse transform (DTO -> config), not a copy.**

**Ids cannot be preserved across a rebuild.** `builder.py` mints a fresh GUID for
every element, config and event unconditionally; no code path accepts a supplied
id. This is not a fidelity loss in practice: the builder rebuilds the dataModel
paths against the ids it mints, so internal consistency holds. **The references
that survive a rebuild are the BINDING NAMES** (each element's `id`/`name`
config), which the wiring resolves against. Carry those verbatim and the form
wires itself correctly; a rebuilt form is nonetheless a NEW form with a new id,
so it can never be a drop-in replacement for the original.

**`_set_config` fails silently.** It overwrites a config key only if that key
already exists on the golden control template in `dto/form/elements/<type>.json`.
A key the golden lacks is dropped with no error and no warning. Before trusting a
generated config, **measure coverage**: for every element, assert every source
config key exists in its golden. A silent drop is indistinguishable from success
in the response.

**Process variables resolve by name at build time, and an unresolved name passes
through as a literal string.** The result is a form that looks correct and runs
nothing. Gate on it: after building, assert every `inputMap`/`outputMap` `left`
matches a GUID pattern, and every `right` is a 4-part dataModel path.

**Map direction** (documented in `builder.py`, both maps put the process variable
on the LEFT; only which spec key names it differs):

    kind 'in':  {to: procVar,   from: formField}  -> left=pvar(to),   right=field(from)
    kind 'out': {to: formField, from: procVar}    -> left=pvar(from), right=field(to)

**`--dry-run` is the correct pre-write gate.** It builds the real DTO locally and
posts nothing, so assertions can run against the actual payload rather than the
config that produced it. Use it whenever a create is expensive to undo.

**Form-level CSS/JS (`Data.code`) is AES-encrypted, and a blob the public
renderer cannot decrypt prevents the form mounting at all** - a permanent
spinner plus `Malformed UTF-8 data`, every control lost, not merely unstyled.
A working form built through this route stores `code` as an empty string.
Express styling through `theme` and per-element `style` configs, which are
ordinary DTO fields, and leave `code` out of the config entirely.

## Editing a credential without destroying its secret

`credential-edit` is a **desired-state rebuild**: the DTO's `properties` list is
built only from the `properties` map in the config you pass, so **any property
you do not restate is DROPPED**. On a REST API credential that holds an API key,
a config carrying just `{"URL": ...}` wipes the key, and restoring it would mean
putting the secret back in plain text on a command line, which Hard rule 1
forbids.

**Use the raw `put-credentials` action instead when you only need to change one
field.** GET the credential, map its `properties` to `{id, value}` pairs,
substitute the one field, PUT it back. The DTO shape the tool's own builder
produces is:

```
gid, gtid, gtpid, name, tname, type, status, description,
properties: [{id, value}]
```

Restoration is then provably the original object, and the secret is copied field
to field inside the process without ever being rendered.

**Two related mechanics.** `config.template` on `credential-edit` is the
credential type NAME (e.g. `"REST API"`), not its guid. And option-valued
properties (`Authentication method`, `Method`) are GUID-valued: sending a raw
string saves fine and then makes every Call API run using that credential die at
runtime with `Unrecognized Guid format`.

**A Call API node references a credential by id and the URL lives in the
credential**, not in the process definition. So repointing an endpoint is a
credential edit and does not touch a frozen process.

## The Node action's library allowlist

`docs.procesio.com/how-to/node` publishes the libraries usable inside a Node
action, and it reads as an allowlist rather than as examples:

`uuid, axios, cheerio, underscore, ramda, validator, lodash, xml, hash.js,
html-to-json-parser, xml-js, moment, date-fns, marked, big.js, @faker-js/faker,
joi, mathjs, csv-parse, papaparse, simple-statistics, luxon, string-similarity,
qrcode`

**A Node BUILT-IN such as `crypto` is not on it.** Do not assume built-ins
resolve. Hashing and HMAC are available through **`hash.js`**. Imports are
CommonJS `require()` only, and the page states plainly that the Node action
**does not support working with files**. Syntax errors set only the `Error`
output, leaving the value outputs null.

## Fetching the documentation

`docs.procesio.com` is **403 from the sandbox proxy** and reachable only from a
browser session. `/llms.txt` returns the index (345 pages); **`/llms-full.txt`
returns the entire corpus in one document** (~1.2 MB). The route
`/llms.mdx/{path}/content.md` that older notes cite **returns 404**.

## `process-edit` is a desired-state rebuild, not a patch

`process-edit` PUTs the WHOLE process. Every field you do not restate is
replaced by whatever is in the config you pass, so **a second edit to the same
process silently reverts the first** unless the first change is carried forward
into the second desired state.

The response is `{"edited": true, ...}` either way. **A revert is invisible in
the response**, and it is equally invisible in any check that only exercises the
part you meant to change.

Two consequences worth designing around:

- When making N edits to one process, either build ONE desired state carrying all
  N, or read the live definition back between edits and carry each landed change
  into the next payload. Reading it back from a local build file is not enough:
  that file is the last state you *authored*, not the state that is *deployed*.
- Verify each edit with a check that would fail if an earlier edit had been
  reverted, not only with a check aimed at the newest change.

The same shape applies to any PROCESIO desired-state action (`credential-edit`,
`datatype-edit`, `form-edit`): the DTO is the complete object. `form-update`
exists precisely because it deep-merges a patch instead of rebuilding, and it is
the safer choice when only one field should move.

## Capacity is measured in TIME, not in execution environments (2026-08-30)

Nothing a workspace-scoped account can reach states a **reserved execution-environment
(EE) count**. What the read-only surface exposes is a *time* budget:

- `GET /api/Resources/used` → `subscriptionType`, `time.limit.soft` / `time.limit.hard`
  (milliseconds), `time.consumed`, `time.masterConsumed`, `notifyThreshold`,
  `expirationDate`, `autoRenewable`, plus platform/custom averages. **No EE count.**
- `GET /api/Subscriptions` → often `[]` on a sub-workspace.
- `GET /api/ResourceTrackingConfig` → recording flags and a storage limit only.

Consequence for any planning that needs a concurrency ceiling: **it is a licensing fact
held outside the API surface**, so get it from whoever owns the subscription rather than
expecting an endpoint to yield it. Do not infer it from the time budget — they measure
different things.

### The `Resources` / `analytics` endpoints are MasterWorkspace-scoped

`GET /api/analytics/executionEnvironment/concurrency`,
`GET /api/Resources/used` and `GET /api/Resources/used/subworkspaces` are documented
`MasterWorkspace.Read`. Called with a **sub-workspace** id, the ones that answer at all
return workspace-level data with no capacity figure; called with the **master**
workspace id, an account without that permission gets **HTTP 403 "Unauthorized"** — the
same shape as the cross-workspace rule above. So a "the platform cannot tell me X"
conclusion must try BOTH scopes before it is written down, or it is really "my scope
cannot tell me X".

### `statsType` is an INTEGER enum, and the error tells you which failure you hit

On `…/executionEnvironment/concurrency`, a string such as `Daily` fails ASP.NET model
binding with a 400 whose body names the field:
`{"errors":{"statsType":["The value 'Daily' is not valid."]}}`. An integer passes
binding and the request proceeds to the authorisation/resource check, which fails
differently (`statusCode 502`, `"Provided resource is not able to be created or
modified"`, `target: "workspaceId"`, or a 403). **Two different 400s mean two different
things**: distinguish a malformed request from a forbidden one by whether the error body
names the query field or the workspace, otherwise a permission limit gets recorded as a
broken call.

### `PATCH /api/Projects/{id}/toggle-activation` is ONE-WAY, and reports success in both directions

Measured 31/08/2026 on a valid, active process and on a duplicate of one:

| call | HTTP result | `active` afterwards |
|---|---|---|
| toggle an **active, valid** process | success | `true` → `false` ✅ |
| toggle it back | success | `false` → **`false`** ❌ |
| toggle an **inactive** duplicate | success | `false` → **`false`** ❌ |

It **deactivates and will not activate**, and answers the same either way, so a caller
that checks only the return value records a state the platform does not hold. Re-ordering
the call so that no later write could undo it changes nothing.

**Activate through the DEFINITION instead:** read the flow, set `active: true`, and
`PUT /api/Projects` with the whole body. That takes effect immediately and is readable
back. The general rule this is an instance of: **a control that refuses is not the same
as a state that cannot be reached** — when an endpoint declines to produce a state, look
for another route to it before recording the state as unreachable.

### An ACTIVE process cannot be deleted, and the delete reports failure rather than raising

`DELETE /api/Projects/{id}` against an active process does not remove it and returns a
failure body; a harness that ignores the return value leaves the object behind and its
cleanup listing will show it. Deletion is therefore **two steps**: PUT the definition
with `active: false`, then delete. (This is also why leftover `… (Copy)` processes
accumulate: the duplicate is created inactive, but anything that activated it in between
makes the tidy-up silently fail.)

### A duplicate lands INACTIVE and INVALID-launchable; a hand-built minimal flow needs a Stop action

`POST /api/Projects/{id}/duplicate` returns the new id under `result.copy_id` and the
copy lands `active: false`. A launch of an inactive flow is refused with
`HTTP 400 "Flow … is inactive."`, and a launch of an invalid one with
`HTTP 400 "Process needs to be valid in order to be launched."`

Do not infer *why* a flow is invalid from the launch refusal — ask the platform's own
validator, `POST /api/Projects/validate`, which names the broken rule. For a flow built
from a Start action alone it answers `statusCode 382`,
`"Couldn't find at least one stop action."`, `target: "flow. Stop action."`. Note that
the validate call itself **succeeds** while reporting `isValid: false`: the call result
and the validity verdict are different things.

### Classify an action by its OPERATION, never by its name

The tool exposes ~352 actions over ~247 endpoints, so most endpoints have **two** names:
a generated one (`post-projects-by-id-run`) and an ergonomic curated one
(`run-process`). They are the same HTTP call. Any guard, audit or policy that matches
**action names** is therefore defeated by a synonym — measured once as **34 operations**
that create, delete or execute being classified as harmless reads, including every
`*-delete`, both actions that `PUT /api/Projects` over a live process, launching a
process and launching a webhook.

The method and path are available without guessing: generated actions carry
`METHOD /path` at the front of their description, many curated ones carry `(METHOD /path)`
inside it, and `data/endpoints.json` is the spec index. Two cases need care:

* **`request`** takes `--method`/`--path` and can reach every endpoint, so its kind is a
  property of its **arguments**, not of its name;
* **composite** actions (`*-create`, `*-edit`, `form-update`, `relayout-process`,
  `rename-actions`, `run-*-with-file`) perform several calls and must be classified by
  what the sequence does, not by the first call in it.

Anything unclassified should default to **write**: over-refusing stops a script, and
under-refusing sends a request.

### `POST /api/Projects/validate` REPORTS validity; it does not CONFER it

Measured 31/08/2026. A flow that the validator answers with **zero errors** can
still be stored `isValid: false`, and a launch of it is refused with
`statusCode 373 "Process needs to be valid in order to be launched."` Note also
that the validate CALL succeeds while reporting `isValid: false` in its body: the
call result and the validity verdict are different things, and a harness that
checks only the former learns nothing.

`isValid` is written the same way `active` is: **put it in the definition**. A PUT
carrying `{"active": true, "isValid": true}` takes effect immediately and the flow
then launches.

**The pattern, which is the part worth keeping:** on this platform a state is
written through the definition, and an endpoint named after a state is usually an
opinion about it rather than a setter. Two instances so far, activation and
validity. Before recording "the platform will not let me reach state X", try
writing X into the definition and re-reading.

### A minimal launchable flow needs Start AND Stop, wired

`POST /api/Projects/validate` on a flow containing only a Start action answers
`statusCode 382, "Couldn't find at least one stop action."`, `target: "flow. Stop
action."` Build the minimal flow from a real captured flow's Start and Stop
actions (so the template ids are genuine), give both a fresh id and flowId, and
**re-point the Start's outbound port at the Stop's id** - a Stop that no port
reaches is an orphan. With `active` and `isValid` written into the definition,
such a flow launches and reaches terminal status 50.

### A `node`-backed engine driver must use a UNIQUE temp file per call

If a driver generates a script, writes it to a **fixed** path and runs `node` on
it, two concurrent callers race: A writes its script, B overwrites it, and A's
`node` executes B's. **The symptom is not an error, it is a plausible result** -
A receives the entities B's documents contained, or a shorter list than it asked
about, and nothing in the return value indicates either.

Measured with two workers on disjoint inputs: **12 of 24 concurrent calls returned
the other worker's identifier and 12 lost their own; 0 and 0 with a per-call temp
file.** Two mitigations, both required:

* a unique temp file per call (`tempfile.NamedTemporaryFile(dir=..., delete=False)`,
  removed in a `finally`);
* **assert the result count equals the input count.** The race also produced short
  lists, and a caller zipping results against its own input list pairs document
  *i* with document *j*'s spans silently.

Generalised: any helper that stages work through a **fixed** filesystem path is
single-caller-only by construction, and the failure mode of breaking that is a
wrong answer rather than a crash. Treat a constant path in a subprocess driver as
a defect on sight.

## DataStore (/api/DataStore) — new module (2026-08)

Tenant-defined dynamic tables (Data-Store service, MySQL-backed), proxied by Web-Api.
Curated actions: `datastore-*` (handlers/datastore_ops.py).

⚠⚠ **RE-CORRECTED 2026-08-24 (E-56). BOTH LAYERS ARE REAL, AND E-48's
CORRECTION WAS ITSELF PARTLY WRONG.** The live role model
(`GET /api/UserPermissions/entities`) returns **15 assignable entities**, and two
of them are **`DataStoreSchema` (#14)** and **`DataStoreRows` (#15)**. So the
split DOES exist, and the note E-48 withdrew was describing this layer.

| layer | what it says |
|---|---|
| **role assignment** (`/UserPermissions/entities`) | `DataStoreSchema` and `DataStoreRows` are SEPARATE assignable entities |
| **endpoint annotation** (Swagger `Permission required:`) | `DataStore.Read` / `DataStore.Write` |

⚠ Both are true and they describe DIFFERENT LAYERS. E-48 read the endpoint
annotations and concluded about the assignable model — the same shape as
checking one surface and reporting about another. **The assignable model is what
a customer's admin actually grants against**, so for any question about limiting
a principal, that is the layer to read.

**The consequence is practical: `DataStoreRows: Write` with `DataStoreSchema:
None` IS expressible**, which is a genuinely narrow grant for a service
principal that only needs to write rows.

⚠ **CORRECTED 2026-08-24. There is ONE permission entity, `DataStore`**, with the verbs
`Read` / `Write` / `Update` / `Delete` (controller-level entity; see
`docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md`). An earlier version of
this note claimed two entities, `DataStoreSchema` (metadata) and `DataStoreRows`
(rows + CSV). **Neither exists.** Both names are a CONTROLLER and a DTO
(`DataStoreRowsController`, `DataStoreRowsDto`) read as if they were permission entities.

⚠ The consequence is not cosmetic: the claimed split is exactly the metadata-versus-contents
separation an access design would reach for, so the wrong note answers "yes, natively" to a
question whose real answer is narrower. **Read-only IS expressible** (grant `DataStore.Read`,
withhold the rest), but the grant is **per entity type, per workspace - never per individual
store.** There is no per-store ACL, so a principal with `DataStore.Write` can write EVERY
store in that workspace. By contrast `ProcessDesigner` and `ProcessInstance` ARE separate
entities, so for processes the design and the runs are independently grantable.

- Metadata: POST/PUT /api/DataStore, PATCH /api/DataStore/{id}/column, DELETE/GET
  /api/DataStore/{id}, GET /api/DataStore, POST /api/DataStore/from-data-model,
  POST /api/DataStore/from-json, GET /api/DataStore/{id}/data-model,
  GET /api/DataStore/restricted.
- Rows (verified vs Web-Api main 2026-08): **read = `POST .../rows/filter`** with
  **pagination on the query string** (`?pageNumber=&pageItemCount=`) and body
  `InternalDataStoreGetRowsDto {filter:<group tree>, sort:[{column,direction}]}` (empty body
  = read all). The old `GET .../rows` query-string form is GONE. **update = `PUT .../rows`**
  body `{values:{col:val}, filter:<group>}`; **delete = `DELETE .../rows`** body
  `{filter:<group>}` — a non-empty filter is MANDATORY on both (no key-array form). add =
  `POST .../rows` `{rows:[{displayName:value}]}`. The filter <group> is a recursive tree:
  `group{id,logic(0 NONE|1 AND|2 OR),items:[node]}`, `node{id,type(1 Condition|2 Group),
  logic,condition|group}`, `condition{id,column,operator(QueryOperators 0..20),value,
  auxValue?}` (auxValue = 2nd bound for Between; In/NotIn take a list value; IsNull/IsTrue
  take none).
- CSV jobs: POST .../export-start, GET .../export-download/{jobId}, POST .../import-start
  (multipart), GET .../import-failures/{jobId}.
- Rows are JSON dicts keyed by **column DISPLAY name** (never the alias). PK columns
  identify a row for update/delete; 4 system columns are read-only.
- Filter operator enum is the FULL `QueryOperators` (0..20): Equals=1, NotEquals=2,
  GreaterThan=3 … Between=7, Like=9, In=11, IsNull=13, Contains=17, StartsWith=19,
  EndsWith=20 (NOT the 1-8 subset in the stale doc). `datastore-get-rows` maps operator
  NAMES to these numbers; recently-changed row/CSV actions also take a raw `--body`.
- Process node: native **"Data Store"** action (SELECT/INSERT/UPDATE/DELETE), FE mapper
  `Data_Store_Mapper`, dispatched by IsProcesio (no code GUID — DB-seeded; resolve by
  name from /api/Actions).
- Form trigger: `RUN_DATA_STORE_OPERATION` event; runtime hits anonymous
  `api/Form/dataStore/{id}/rows(/filter)` with form context in headers.

## Scheduler — crontab recurrence (PRC-3282, 2026-08)

Addendum to the Scheduler section above. New recurrence type **`CRON = 8`**
(RecurrenceTypes: NONE=0, ONCE=1, MINUTES=2, HOURS=3, DAILY=4, WEEKLY=5, MONTHLY=6,
YEARLY=7, CRON=8). The recurrence block gains a `RecurrenceCron` shape: `cronExpression`
(5-field standard crontab, Cronos library), `timeZone` (IANA), optional start/end window.
Preview endpoint: **POST /api/Schedules/validate-crontab** — body
`{cronExpression, timeZone?, count?(default 5, 1..20), startDate?, endDate?}` → a
description + next occurrences (UTC). Tool: `procesio validate-crontab`; create/update
-schedule take `--cron`/`--timezone` (built over the JSON `--payload`). The exact camelCase
field names of the cron block are best-effort pending a live GET of a created cron schedule.

## Scheduler — what a create/update body must actually look like (live, 2026-08-30)

**A cron recurrence must carry the cron keys and NOTHING else.** This is the whole
trap. The block is:

```json
"recurrence": {
  "recurrence": 8,
  "cronExpression": "*/2 * * * *",
  "timeZone": "Europe/Bucharest",
  "info": "Every 2 minutes",
  "isEndDate": false,
  "startDate": "2026-08-30T06:00:00"
}
```

Leave any calendar-recurrence field in beside them — `every`, `onDay`, `onThe`,
`isOnThe`, `isWeekendExcluded`, or an `endDate` while `isEndDate` is false — and the
whole request is refused with the generic HTTP 400
`[{"statusCode":502,"value":"Invalid request due to missing or incorrect resource
parameters.","target":"schedules"}]`, which names no field. That reply is easy to
misread as "this deployment does not support cron", especially since the advice
everywhere else here is to CLONE a live schedule and edit it — and cloning is exactly
what drags the forbidden keys in. `--cron` therefore REPLACES the recurrence block
rather than overlaying onto the payload (`_apply_cron`), and
`tests/test_schedule_cron_shape.py` pins the key set.

**`POST /api/Schedules/validate-crontab` proves nothing about create.** It returned
`isValid: true` with a description and next occurrences for the very expression whose
create was being refused. The preview endpoint validates the EXPRESSION; the create
endpoint validates the BODY. A green preview beside a red create means the recurrence
block is wrong, not the cron.

**For the calendar recurrence types the opposite rule holds: mirror the read DTO even
where you do not care.** A MINUTES body (`recurrence: 2`, `every: N`) with
`endDate: null` and `onThe: []` was rejected; the same body with a far-future `endDate`
and `onThe: [2, 1]` copied from a live schedule was accepted, both with
`isEndDate: false` / `isOnThe: false`. So those fields are shape-validated before the
flags that switch them off are read. Cron is the exception because its block is a
different shape, not a superset.

**A schedule belongs to a workspace, and the create response does not show it.** The
POST reply came back with `workspaceId: null` and `createdOn: null` — it echoes the
request, not the stored row. The schedule really was filed under the `workspaceid`
header's workspace, which `GET /api/Schedules` then filters on: new schedules were
absent from an unscoped list and present in a scoped one. Always confirm with a
workspace-scoped list, where `nextDate` is the first hard evidence the recurrence was
accepted.

**`status` is still ignored on create** (Gotchas above): a schedule posted with
`status: false` came back `status: true`, live from the first tick. Create it only when
you want it running, or disable it immediately with the status PATCH.

**Proof of a working schedule is an instance, not a next-run date.**
`GET /api/Projects/{id}/instances` stamps each run with the `scheduleName` that launched
it, so a scheduled run is distinguishable from a manual one in the same list — that
field is the only thing separating "the scheduler fires" from "I ran it myself two
minutes ago".

## Forms: FORM_LOAD runs only its FIRST process (live, 2026-08-30)

A form's `Data.events` may list several `FORM_LOAD` handlers, and the designer accepts them, but
**only the first `RUN_PROCESS` in that list actually executes.** Verified live on a published form:
with two RUN_PROCESS handlers the network shows `POST /api/formProcess/{form}/{proc}/publish` and a
`launch` for the FIRST one and *no request at all* for the second, while every `RUN_JAVASCRIPT`
after them still runs — and therefore reads an empty variable. The same two processes wired to an
element's `onInput` both run, so this is a property of FORM_LOAD, not of the handler list.

**Consequence for authoring:** everything a page needs before anyone touches it must come back from
ONE process. Build a bootstrap process that returns each piece as its own output variable and map
them all in that single call's `outputMap` (a form variable per output; an output can also be mapped
straight onto a control's config, which is how a select's `sourceValue` is filled). Two pages here
were rebuilt this way and both got faster as a side effect: three sequential calls became one.

## Forms: a handler with no `id` never registers - and that is what "FORM_LOAD runs only its first process" was

Every entry in an event list (`Data.events`, or an element's `onClickEvents` / `onInputEvents` /
`onOpenEvents` / `onTabChangeEvents`) needs a **unique `id`**. Without one it is stored, shown in
the designer, and never runs. Two entries sharing an id behave the same way: one of the pair is
dropped. `copy.deepcopy` of an existing handler is the usual source of a duplicate.

Nothing reports this. The page loads, the code is right there in the form, and it simply never
executes - which reads as a platform limitation rather than a missing field.

**This corrects the note above it.** "FORM_LOAD executes only its FIRST RUN_PROCESS" was measured on
a form where 38 of 68 handlers had no id. Once every handler was given one, a second FORM_LOAD
RUN_PROCESS ran and its output map landed. A trigger runs *every* handler on it, in order; a handler
that appears not to run is missing its id, or shares one.

The bootstrap-in-one-call advice in that note still stands, for a different reason: each call is a
`publish` + `launch` round trip of one to five seconds, so fewer calls is faster whatever the trigger
allows.

## Forms: the runtime property names are not the designer's config keys

A control's stored config key and the property the runtime exposes on
`ProcesioForm.data.fields.<name>` are different names for several controls, and assigning the wrong
one fails silently - it invents a property nothing reads, and the value is there when you read it
back. Seen on a date control:

| designer config     | runtime property        |
|---------------------|-------------------------|
| `minDate` / `maxDate` | `minValue` / `maxValue` |
| `availableDates`    | `availableIntervals`    |
| `disabledDates`     | `disabledIntervals`     |
| `inline`            | `inlineView`            |
| `hasNow`            | `hasTodayNowOption`     |
| `setNowByDefault`   | (not exposed)           |

Ask a live control rather than guessing: from a handler, write `Object.keys(fld('Name')).join(',')`
into a paragraph's `label` (a paragraph renders its label, never its value). One probe per control
type settles it.

## Forms: what a control reads from a handler, and what it only reads from the output map

Three different behaviours, all silent when you pick the wrong one:

* **A select's options** come from the RUN_PROCESS **output map** written onto the control's
  `sourceValue` config path. Assigning `sourceValue` from a handler leaves the control showing its
  placeholder. The list the map delivers must be objects with `name` and `value`; a query can return
  those two columns alongside the display columns, so one call can feed a table and a picker at once.
* **A dynamic table's rows** live in the runtime's `value`, not `sourceValue`, and the control reads
  them when it draws. A table filled at page load can be painted from a handler; one that has
  already drawn will not repaint that way, so refresh it through the output map instead.
* **A date control's value** is accepted at any time but only read when it draws. Setting it after
  the fact leaves the calendar on the previous month while the page shows another day. Hiding and
  re-showing the control (`visible = false`, then `true` on a `setTimeout(..., 0)`) makes it draw
  again - do it only when the MONTH changes, and re-assert the value inside that timeout, because
  the redraw re-reads the control's own configuration.

## Forms: a control inside a table row is addressed through the row, or not at all

A control placed in a table row's action column exists once per row.
`ProcesioForm.data.fields.<name>.value` is `undefined` for it, and a process map pointing at its own
four-segment field path sends nothing - so Save is refused for want of values that are plainly on
screen, and Delete sends a null id. The row path is five segments and ends at the CHILD ELEMENT:

```
<formId>.<fieldsNs>.<rowElementId>.<the row's "$.fields" attribute id>.<childElementId>
```

`$.fields` lives in the row's data-model sub-model, next to `$.item` (the row a handler was
triggered from) and `$.cellValue`. **A table added to a live form by splicing does not get them**:
`form-add-element` builds a sub-model from the element's own configs, so the row has `value` and
nothing else. Adding the three attributes to the stored model does not help - the runtime builds its
own and ignores them.

So, for a spliced table: keep the row read-only and put the actions on the tab, or copy what the
action needs out of the row into a control outside it. `$.item` still works on a table the designer
built, so a panel opened from such a row can read it and write the id to a field at tab level, which
a map can then read. Where `$.item` is absent too, a picker listing the rows is the honest fallback.

## Forms: a failed process ends the chain, so the handler that would explain it never runs

When a RUN_PROCESS errors - an invalid value that its SQL cannot bind, for instance - the handlers
after it do not run, so a page whose only feedback is a JS `say()` after the call stays silent and
the person sees nothing at all. Validate the SHAPE of a value where it is typed (an `onInput`
handler on the field) and let the database stay the boundary for whether it is allowed.

Related: an `Execute Command` node returns the number of rows it affected. "A result variable
exists" is not "it saved" - a refusal and a save both produce one, and reporting on existence alone
tells a person their change was written when it was not.

## Forms: an empty control bound to a typed process variable kills the call before it starts

A form maps its controls onto the process's own variables, and those are TYPED. An empty string
assigned to an `INT` variable fails at launch: the process never runs, and because a failed call ends
the handler chain (above), the handler that would have reported it never runs either. On screen the
button does nothing at all - no message, no error, no network call worth noticing.

This is what "I cannot add any new ones" turned out to be: a create panel whose hidden id field was
blank, mapped onto an `INT`. Give such a field the value the procedure reads as "this is a new one",
usually `0`, in the control's default AND on the panel's open handler, so a previous edit cannot
leave something else in it.

The same shape applies to SQL: a node that pastes `@p0` straight into `EXEC proc @Id = @p0` fails to
bind when the form sends `''`. Convert first - `DECLARE @id INT = TRY_CAST(NULLIF(@p0, '') AS INT);`
- and guard the EXEC, so a bad value becomes a no-op with zero rows affected rather than a dead
click. `Execute Command` returns the affected-row count, which is then the difference between "saved"
and "refused" in the message.

## Forms: a panel opened from a table row is filled by the ROW, not by assigning its controls

Writing a row's values into the panel's controls when the panel opens does not reach the copy of
those controls that belongs to the row - that is the `Actions` object on the row object, and a
process map addressing the control through the row reads exactly that. Assigning the controls left
`Actions` empty, so the panel showed blanks and Save sent nothing.

Fill `Actions` while PAINTING the table instead, one entry per control in the row's action column:

```js
el.value = list.map(function (r) {
  return { /* the display columns */, Actions: { StartTime2: r.StartTime, ... } };
});
```

Then the panel opens on the right values and the buttons send them, with no dependence on `$.item`
and no handler ordering to get right. Controls SPLICED into a row later are not in its `$.fields`
and can never be read by a map; keep the original hidden field as the one the map reads and have the
visible control mirror into it, or read the row's own copy as above.

## Forms: how a spliced control inside a table row can still be READ

A control added to a table row after the table was built is in neither the row's `$.fields` nor
anything a process map can address, and `fld('Name').value` for it is `undefined` however correct it
looks on screen. What a person types nevertheless lands on the ROW, in its `Actions` object:

```js
var row = (fld('DynamicRow1') || {})['$.item'];
var typed = row && row.Actions ? row.Actions.MyNewField : null;   // what was typed
```

So the working shape for a field that has to be added to an existing row editor is: show it in the
row (put its value in `Actions` while painting), read what was typed from `$.item.Actions` in an
`onInput` handler, and copy that to a hidden field at TAB level, which the save maps. Three hops,
but every one of them uses a mechanism that works; the direct routes silently send nothing.

## Processes: adding a variable or a node to a LIVE process without regenerating its ids

`process-edit` rebuilds a process from a config and mints new ids for everything, which breaks every
form map that references a variable. For a surgical change, GET the flow, mutate, PUT `/api/Projects`
- the process twin of the form patcher. Two things learned doing it:

* **A node stores only the port LEAVING it.** Start additionally carries an entry stub with
  `sourceId` all-zeroes; Stop carries none. Giving a spliced node an incoming port as well declares
  the same connection twice and the PUT is refused with "Duplicate connection port". To splice N
  between A and B: re-point A's outgoing port at N, and give N one outgoing port to B.
* **CLONE a node rather than authoring one.** An action carries a template id, a parameter list
  keyed by `tabPropertyId`, and a `customData` block; a hand-built one that is subtly wrong fails at
  run time with nothing to read. Copy the node that already does that kind of work, change the
  endpoint/credential/code, and repoint its variable bindings.
* **A `<%N%>` with no binding is not an error.** The clone's code used one variable; the new code
  used two, and the second placeholder simply read `undefined` - the node ran and returned null.
  Every placeholder needs its own entry in that parameter's `variable` list.
* A variable only reaches the outside world if its `type` marks it as an OUTPUT (30 here, against 20
  for a working variable). A process-scoped variable is invisible to `run-process` AND to a form's
  output map.

**PUT the flow in-process, not through the CLI.** A real flow does not fit in one command-line
argument on Windows: the whole JSON trips the 32 KB limit and the call fails before the tool starts
(WinError 206).

## Forms: validation lives on three configs, and they are all off by default

An `input` carries `type` (which maps to the HTML input type - `email`, `url`, `tel`, `number`),
`regex` (the pattern the platform checks) and `required` (which also draws the asterisk). All three
default to permissive, so a page built by clicking accepts anything anywhere - a time field takes
"abc", a notification address takes a sentence, a date filter takes free text, and each one is only
discovered later as a query that returns nothing or a message that never arrives.

Write patterns without lookarounds and with the fewest escapes that will do: a pattern has to
survive JSON, the form DTO and the browser, and one that loses a backslash on the way fails when
someone types, with nothing to point at. A number control has no min/max, so state the range in its
info text and enforce it where the value is read.

## Performance: the unit of cost is the CALL, not the work inside it

Every process a form calls costs a `publish` and a `launch` - one to five seconds of round trip
before any of its work begins. Reading one extra list in a process of its own added ~1.7s to every
page load; the same two nodes folded into the existing bootstrap cost a fraction of that. Making the
separate call ASYNCHRONOUS was worse than leaving it synchronous: the call still happens, and the
page then draws twice.

Measure with `performance.getEntriesByType('resource')` filtered to the API host, grouped by
endpoint - it shows the publish/launch pairs directly, so the cost of each process is visible
rather than inferred.

## Forms: a time control renders only the times that land on ITS grid, not the list you give it

`availableIntervals` on a time control is a FILTER, not the list. The control generates candidates by
stepping `minuteInterval` + `minutesBetweenIntervals` from the start of the day and shows the ones
that also appear in `availableIntervals`. Setting those two from the meeting's own duration and gap
therefore produces a regular grid, and any offered time that does not fall on it is dropped in
silence - the page said "5 times free" and drew one of them, because only the first was on both
lists.

Set `minuteInterval` to 1 and `minutesBetweenIntervals` to 0, and let whatever produced the list
enforce the spacing. The times a calendar-aware engine produces start wherever the diary frees up,
which is not a round number.

The visible symptom is worth remembering on its own: **a count that disagrees with the number of
items rendered means something downstream is filtering the list**, not that the count is wrong.

## Forms: do not match handlers by a substring of their code

Appending a painter to "every handler that mentions `typeViewVar`" caught the SUBMIT handler, which
had recently started reading the day from that same variable. The appended code referenced a
variable the submit handler does not define, so it threw on the way out - and because the throw was
at the END of the handler, the submit itself had already run. The result was a booking that reached
the database while the page sat on "Booking your time..." for ever, since the handler that reports
the outcome never got that far.

Match handlers by what they ARE - their element and trigger - not by a word that happens to appear
in them. And when appending to a shared handler, check the appended code only uses names the handler
itself defines.

## Forms: the global JavaScript runs in a SANDBOXED FRAME

A form's global JS is not executed in the page. `document` there is the frame's own - it holds none
of the form's controls, so a listener bound to it is registered and never fires, silently. The page
is `window.parent.document` (equal to `window.top.document`), and writing to `document.title` from
the frame does reach the page, which makes it a usable probe.

Even reaching the right document is not enough for input handling: a capture listener on the page's
document is bound and still never fires, because the framework stops input events before they get
there. Binding to each control works, but the controls inside side panels do not exist until the
panel opens, so it needs a MutationObserver as well.

**The conclusion that actually holds:** do not try to police a free-text field. Use a control that
cannot hold the wrong value - a `datetime-input` in `time` or `date` mode, marked `readonly` so it
can only be picked from. A read-only picker is the only arrangement here that a person cannot type
into, and it removes the whole class of problem rather than reporting it afterwards.

## Forms: a table filled only by a handler races its own render

A table whose rows are assigned by the page-load painter shows them SOMETIMES: on a slower load the
control draws before the handler runs and the table says it is empty until something else redraws
it. Fill it through the RUN_PROCESS output map, which applies as the answer arrives, and leave the
handler to add only what a query cannot express - the per-row `Actions` object.

Related, and the reason a column can go blank after a save: a list is usually fetched by more than
one process - once at page load, and again after each write so the table refreshes. Anything derived
in the page-load painter alone is missing from every other path. Derive it in SQL instead, so every
reader gets the same columns.

## Booking engines: validate the RULES, not membership of a regenerated list

A booking guard that regenerates the offered slots and demands the requested start appear in that
list is correct only while the list is a fixed grid. Once the list is built from an external diary
the server cannot see, the two sides answer different questions: the page places a meeting at the
moment the diary frees up, the database regenerates from the top of the working day, and every
correct booking is refused with "that slot is no longer available" while the visitor is looking at
it. Check the constraints the database owns - inside a working window, not overlapping an existing
booking padded by the gap, not inside a blocked period, later than the minimum notice - and leave
the external diary to the call that can actually read it. Alignment inside a free stretch was never
a rule, only a side effect of how the list was generated.

## Forms: async RUN_PROCESS + a JS handler that reads its result is a race, not a pipeline

The common designer pattern — `RUN_PROCESS` with `syncRun: false`, then `RUN_JAVASCRIPT` reading the
variable that process fills — is a race the JS usually LOSES. It is not a hang or an error: the
handler runs, sees the variable's previous value (often empty), and quietly does nothing.

Seen live as two different-looking bugs with one cause: a time picker that showed all 48 half-hours
of the day instead of the 13 real slots (the handler that narrows it ran before the slots arrived),
and a settings page whose fields "populated one by one" (three async loads each painting when it
happened to return). `syncRun: true` fixes both. Use async only when nothing reads the result.

## Forms: `ProcesioForm.data.fields` keys are re-derived in LOWER CASE by a designer save

Documented in the form sub-tool notes and worth repeating here because it silently disarms handlers
that were working: after a save from the designer, `ProcesioForm.data.fields.DefaultTimeZone` is
`undefined` while `...defaulttimezone` is the control. Every handler should open with

```js
var _F = ProcesioForm.data.fields, _fl = {};
for (var _k in _F) { _fl[_k.toLowerCase()] = _F[_k]; }
function fld(n) { return _fl[String(n).toLowerCase()]; }
```

and address controls as `fld('Name')`.

## Forms: three more control traps found while rebuilding a live page

- **A control defined `visible: false` is never mounted, so JS cannot reveal it.** Setting
  `.visible = true` on it from a handler does nothing at all — there is no DOM node to show. Define
  it visible with empty content instead; a paragraph with an empty `label` paints nothing.
- **Hiding a container beats hiding its children.** Hiding controls one by one left one paragraph
  standing whatever was tried on it (`visible`, clearing `label`); hiding the `columns` container
  they sit in removed the whole block in one operation.
- **`.defaultValue` is not `.value`.** A row-detail panel that copies a table row into its fields via
  `.defaultValue` looks correct on screen, but a `RUN_PROCESS` input map reads `.value` — so the
  process receives an empty field. This is what made a working Delete button look dead. Write both.
- **A handler appended to an existing one shares its scope.** A block appended after a handler that
  declares `function say(text)` had its own three-argument `say(field, text, show)` shadowed, so it
  wrote a field NAME into the wrong control. Appended blocks must not reuse an identifier.

## Forms: `form-add-element` models a spliced control FLAT, whatever it is parented into

A control the designer placed inside a `dynamic-table-row` is modelled twice — under
`fields > <row> > $.fields` (addressed `ns.rowId.rowSubModelId.elementId`, with no value segment) and
flat. A control added by `form-add-element` exists ONLY in the flat namespace, so its field path is
`ns.elementId.valueAttrId` even when it renders inside that row. Borrowing the row prefix from a
sibling points the map at a node that does not exist, and the map fails silently.

## Data models drop columns they do not declare

A SQL row mapped into a typed data model keeps only the attributes that model declares; extra
columns are discarded without a warning. Adding a column to a stored procedure that feeds a
`For Each` over a typed list therefore changes nothing until the DATA MODEL gains the matching
attribute (`datatype-add-attribute`). Seen live: a template body added to a notification query
arrived as `undefined` in the loop, and the flow correctly fell back to its built-in text — a
failure that looks exactly like "the feature does not work".

## Forms: a spliced child is invisible until its CONTAINER lists it

A `tabs` container draws the tab NAMES in its own `tabs` config; a `table` draws the row names in
`rows`. Setting a child's `parentId` is not enough. A tab added with the right parent and nothing
else **exists, saves, validates, lints clean, renders nowhere** — and every process behind it keeps
working when called directly, so the feature tests green while being unreachable on screen. Two
whole tabs were built, wired and reported done in this state before anyone tried to click them.

`form-add-element` now registers a spliced child in its container's list (`_LIST_CONFIG`:
tabs->`tabs`, table->`rows`, stepper->`steps`), covered by `test_form_add_element.py`. When adding a
container child by any other route, set that list by hand and then LOAD THE PAGE: neither the
validator nor the linter can see this one.

## Booking availability must consult the connected calendar, on BOTH sides

A slot engine that only knows its own bookings tells a visitor a time is free while the owner's
calendar has a meeting in it. The rules table is not the diary.

The shape that works, with the two halves that are easy to get half-right:

- **On the screen** — after the rules produce candidate slots, `POST calendar/v3/freeBusy` with
  `{timeMin, timeMax, items:[{id: <calendarId>}]}` over a window a day either side of the local
  date, then drop any slot that overlaps a busy interval. Compare INSTANTS, not dates, and use a
  half-open test (`slotStart < busyEnd && slotEnd > busyStart`) so a meeting ending exactly when a
  slot starts does not block it.
- **At the boundary** — the booking procedure is SQL and cannot call the calendar, so the same
  free/busy question has to be asked in the FLOW, for exactly the requested window, before the
  procedure runs. Without it the screen is stricter than the write path and a direct POST books
  over a real meeting.

**A calendar that cannot be read must never widen availability.** Both checks treat a non-200 as
"unknown" and fall back to the rules rather than to "free" — the database stays the authority for
everything it can see, and an outage cannot silently open the diary.

## PROCESIO can read its own workspace through its own API

A form cannot enumerate credentials, but a flow can: `POST /api/ApiKey` mints a workspace key
(`GET /api/ApiKey` never returns the value again — it is shown once, in the create response), and a
`REST API` credential with API-key auth holds it. PROCESIO's api-key auth is three headers —
`key` (the key's NAME), `value` (the secret), `workspaceid`. Put the SECRET in the credential
(`Key` = `value`), and the other two as plain node headers: neither is sensitive, and an export
encrypts a credential's designated secret field while leaving node headers in clear.

That turns "type a credential GUID into a settings box" into a dropdown fed by
`GET /api/Credentials`, filtered on the TEMPLATE name (`tname`) rather than the credential's own
name, which a user is free to change.

## Testing a PROCESIO form: wait for the DATA, never for the DOM

The single most expensive mistake made against these pages. A form renders its controls
immediately and fills them from a process a moment later, so a check that waits for a selector which
already exists — `input`, a table, the time-picker's own default grid — photographs the page BEFORE
its data arrives. Every field reads empty, every handler looks dead, and the conclusion "the trigger
does not fire" follows naturally and is wrong.

It cost two false diagnoses in one session: "handlers built through the API never register" and
"the admin page's processes need authentication". Both were the same artifact; the pages were
working the whole time. Real damage followed — working improvements were reverted to undo a
breakage that had never happened.

**Wait on a string only the loaded state can produce.** Playwright `text=` selectors are ideal:

```json
{"do": "wait_for", "selector": "text=/times available|No times left/", "timeout": 40000}
{"do": "wait_for", "selector": "text=Google Calendar - <account name>", "timeout": 45000}
```

Corollary for reading values: `extract_attr` with `attr: "value"` returns the ATTRIBUTE, which for
an input is its initial value, not what the control now holds. A populated field reads `None`
through it. Take a screenshot, or read the property in page script.

## Slot generation: reduce the day to free intervals, then place meetings in them

Stepping `duration + gap` from the start of the availability window and discarding whatever
collides makes the offer depend on when the WINDOW opens rather than on when the person is free. A
two-hour hole opening at 14:00 yielded a 14:40 slot, because that is where the grid from 09:00
happened to land — forty minutes lost for a reason no one can see on screen, and a different
window start would move it again.

Build the busy set first (bookings of EVERY meeting type, blackouts, and the connected calendar),
pad it by the gap, then walk each availability window jumping to the end of whatever is in the way.
Meetings then start where the diary actually frees up.

**The external calendar must feed the GENERATOR, not a filter after it.** Filtering afterwards
throws the alignment away again: the grid is laid without knowing the calendar, and the filter can
only delete. Pass the busy intervals into the query (JSON + `OPENJSON`) so they are exactly as
authoritative as a row in the bookings table.

## One gap, not two

"Free minutes before" and "free minutes after" describe the same interval from opposite sides — the
time after one meeting IS the time before the next — so two numbers can disagree and nothing says
which wins between a pair. One `MinutesBetweenMeetings`, seeded from the MAX of the two so an
upgrade cannot loosen anything, and the arithmetic becomes explainable: a 2-hour hole fits two
60-minute meetings at gap 0, and exactly one at any gap above zero.

## Exports and secrets — what is encrypted and what is NOT (audited 2026-08-17)

**The rule: a `.procesio` export is a secret-bearing artifact. Treat every export
as sensitive until scanned, and never commit one unscanned.**

An export does NOT encrypt uniformly. Two different storages sit in the same
file, and only one of them is protected:

- **Encrypted (safe to commit).** The designated secret fields of a *Credential*
  entity — `Credentials[].properties[].value` — are AES-encrypted at rest in the
  export. Evidence: the base64 blobs decode to byte lengths that are exact
  multiples of 16 (32/48/64/80/96/128/192/256 …), the decoded bytes are ~37%
  printable (the ratio for uniform random bytes, i.e. ciphertext, vs ~100% for
  text), and a credential whose *name* says SendGrid contains no `SG.`-prefixed
  value anywhere. Non-secret fields of the same credential (base URL, username,
  account identifier) stay plaintext, which is why an account SID can appear in
  the clear beside an encrypted token.
- **PLAINTEXT (leaks).** Every other author-typed string. Confirmed live in:
  - `Flows[].Actions[].Parameters[].Value.headers[].value` — a token typed
    straight into a Call API `Authorization` header
  - `Flows[].Actions[].Parameters[].Value.queryParams[].value` — an API key
    passed as a query parameter
  - `Flows[].Actions[].CustomData.configuration[].settings[].value[].value.headers[].value`
    — headers inside a *custom action's* saved configuration
  - `Flows[].Variables[].DefaultValue` — a token baked into a process variable's
    default value
  - `Credentials[].properties[].value[].Value` — the nested default-header array
    inside a credential. Note this is INSIDE a Credential yet still plaintext:
    encryption covers the designated secret *fields*, not arbitrary nested
    structures hanging off them.

**Consequence for authoring:** binding a Credential protects the secret; typing
the same token into a header, query parameter, custom-action setting, or variable
default does not. The platform gives no visual cue that one is encrypted and the
other is not. So the discipline is *always bind a Credential* — and when
reviewing someone's flow before export, look at the header/param fields, because
that is where a hardcoded token hides.

**Classify by shape before believing a hit.** In the exports audited, 40 of 57
`Bearer <x>` occurrences were GUIDs — PROCESIO *variable references*, not
secrets. Others were placeholders. Only non-GUID, non-placeholder, high-entropy
values were real. A scanner without a shape classifier reports ~7x noise and gets
ignored.

**Scanning them requires a windowed reader.** An export is ONE JSON line, tens of
MB wide. Any line-oriented scanner — or one that skips long lines — reports
"clean" on exactly the files most likely to carry a credential. This is not
hypothetical: the first audit pass here skipped lines over 4000 chars and missed
every finding. Use `scripts/secret_scan.py`, which reads fixed-size chunks with
an overlap wider than the longest token, and is enforced by
`tests/test_no_secrets.py` plus the `.githooks/pre-commit` hook.

```bash
python scripts/secret_scan.py --path tools/procesio/docs_info/Exports
```

**Remediation without breaking the fixtures.** These exports are load-bearing —
`tools/procesio/tests/test_form_parity.py` reads them as the platform's own
ground truth for form structure. So scrub in place rather than deleting: replace
only the confirmed-plaintext values (`scripts/scrub_secrets.py --fingerprint …`,
which targets by sha256 prefix) and leave the encrypted credential blobs intact.
Never bulk-replace "anything high-entropy" — that would destroy the AES
ciphertext the fixtures legitimately contain. Verify after scrubbing: re-scan
clean, every export still parses as JSON, and the parity tests still pass.

**Never print a credential value** — not in a report, a log, a commit message, or
a test failure. A sha256 prefix, length and entropy identify one well enough to
match it against a vault entry or confirm a rotation.

## Credential templates — deriving one so an action sees only its own credentials
(live-verified 2026-08-18)

By default a connector's credential dropdown lists **every** credential of that kind in
the workspace. A REST connector shows every REST credential, whoever created it and
whatever service it points at. To narrow it to one service, give the service its own
credential template **derived from an existing one**, and pin the action to it.

### The mechanism

`credentials_template` carries `Gid`, **`Pid`**, `Name`, `Type`, `Icon`, `Properties`,
`IsProcesio`. `Pid` is the parent. A root template has `Gid == Pid`; a derived one keeps
its own `Gid` and points `Pid` at the parent. `DapperCredentialsTemplateRepository`
exposes `GetByPid`, and the designer resolves an action's credential `TemplateId` **as a
Gid first, then falls back to Pid**.

Live shape of the REST family: `REST API` is the root
(`10101010-0001-0000-0000-aaaaaaaaaaaa`, `Type = REST_API`) with 29 children, all
`Type = REST_API_OAUTH_PREDEFINED`, every one carrying `Pid` = that root.

**`Type` decides behaviour, `Pid` decides grouping.** `CredentialsServicesFactory`
switches on `Type` alone:

```csharp
case CredentialsType.REST_API:
case CredentialsType.REST_API_OAUTH_PREDEFINED:
    return new CredentialsAPI(...);
```

So a derived template that keeps `Type = REST_API` reuses the existing client and needs
**no backend change**. Only a new enum value would, and that is a platform change across
three repos — `CredentialsType`, the factory, and whatever builder the new type needs.

### Pinning the action to it

Set `CustomCredentialsTypeGuid` on the `FEDecorator`, and **leave the type as
`Credentials_Rest`**. The attribute name misleads: it does not declare a special
credential type, it fixes which template `Gid` the selector accepts. Every shipped
connector that narrows its dropdown does this — `GitHubConnector`,
`GoogleSheetsConnector` (twice), `RedisConnector`.

```csharp
[FEDecorator(Label = "Prelude Credentials", Type = FeComponentType.Credentials_Rest,
    Tab = "Configuration", RowId = 0,
    CustomCredentialsTypeGuid = "9be10de9-0002-0000-0000-aaaaaaaaaaaa")]
```

For a built-in connector the seed registers the property, so `properties.TemplateId` must
carry the same Gid. **Set both.** The seed is generated from the decorator surface, so a
decorator without the Gid regenerates a seed pointing back at the stock template and
silently undoes the filter — the same decorator-versus-SQL drift that produced the
Min/Max defect.

### Writing the template's Properties

`Properties` is a JSON array. Each entry's **`be_id` must come from the
`CredentialApiKeys` enum** — the runtime looks properties up by that name and ignores
anything else: `URL`, `Method`, `AuthenticationMethod`, `UserName`, `Password`, `Key`,
`Value`, `Header`, `Query`, `Path`, `Scopes`, `ClientId`, `ClientSecret`,
`AuthorizationUrl`, `AccessTokenUrl`, `RefreshTokenUrl`, `CertificateFile`,
`CertificatePassword`, and the OAuth field tables.

**THE NAME MUST CONTAIN A SLASH, or the template is unusable from the UI.** This one
mechanic cost more than everything else in this section put together, and nothing about
it is discoverable from the API.

The credential type selector builds its tile list by grouping on `name.split("/")`. A
template whose name has **no** slash is treated as a root, and the tile it creates takes
its gid from the template's `Pid`:

```ts
options.push({ ...type, name: nameParts[0], gid: type.pid, pid: null, ... })
```

Selecting a tile sets the credential's `gtid` to that gid. So a DERIVED template named
`Prelude` produces a tile that selects its PARENT — the form loads the parent's fields,
nothing from the derived template appears, and the new tile behaves as a duplicate of the
parent's. For a root template `Gid == Pid`, so the same code is harmless, which is why the
trap only springs on derived ones.

Name a derived template `Parent/ Child`. With **no space before the slash**, the first
part matches the parent option's name exactly and the child nests inside it carrying its
own `Gid`. A space before the slash creates a second, near-identical group instead. Every
shipped derived template follows the shape (`OAuth2 (REST API) / Azure Storage`), which is
why none of them hits this.

**Verify a naming change by simulating the grouping over the live template list** rather
than by reading the form. The list is one `GET /api/Credentials/types` call, and the
grouping is a dozen lines, so a wrong name is provable in seconds instead of guessed at
through the UI.

**Reuse the PARENT's property ids.** They are slots, not identifiers you mint: in the REST
family `...0001...` is URL, `...0002...` the test method, `...0003...` the test endpoint,
`...0004...` the authentication method, `...0007/0008/0009/0010...` key, value, header and
query. Every shipped derived template — Azure Storage, GitHub, the whole Google family —
keeps the parent's ids and its option ids, and overrides only `label`, `placeholder`,
`value` and `message`. Minting fresh ids has no precedent anywhere in the data.

**Nothing is inherited.** `Properties` is the complete list the form renders, so a field
you do not want is simply left out. That is why the 30 shipped OAuth templates carry six
properties and ZERO conditions: they never hide anything. Only a derived `REST_API`
template with API-key auth has to keep plumbing present-but-hidden, because the runtime
reads `Key`, `Header`, `Query` and `AuthenticationMethod` out of `Properties`.

**Hide with a REAL dependency, one the form can resolve.** The form short-circuits to
VISIBLE before it even looks the dependency up:

```ts
if (!operator || !dependencyId || dependencyId === nullableGuid) { return true; }
```

So a null operator and the all-zero dependency BOTH force the property on screen — the
opposite of what they look like they do. All 15 conditional properties
in the REST template name another property's id and the option value that reveals them.
The reliable way to say "never" is to name a property that exists and a value it can never
hold — for an API-key template, reveal only when `AuthenticationMethod` equals the OAuth 2
option, which such a template does not offer:

```json
{"condition": {"dependencyId": "<the AuthenticationMethod property id>",
               "operator": "equals",
               "value": "<an option guid this template does not offer>"}}
```

**The all-zero `dependencyId` is NOT a hiding idiom, despite appearances.** The stock REST
template does carry it on "Test parameters configuration" — and that block RENDERS in the
REST credential form. The form has to find the property named by `dependencyId` before it
can evaluate the condition, so a dependency that matches nothing leaves the control on
screen. The operator is a red herring either way.

That is how you present one field to the user while still supplying everything the
runtime needs. For API-key auth: show `URL` and `Value`, hide `AuthenticationMethod`
(pinned to the option whose `be_value` is `ApiKey`), `Key`, `Header`, and `Query`.

**`message` is help text that shows under the field**, unlike `tooltip`, which needs a
hover. It accepts HTML, so the Azure template uses it for a link to the vendor's endpoint
documentation. Prefer it for anything the user must read in order to fill the field in.

**Open question, still unconfirmed on a live form:** whether the form applies a property's
`value` as a prefill when CREATING a credential, or only when editing one. A template can
carry a value and still show an empty field. Confirm against the running front end before
promising a prefilled field to a user; the copy in `Git FE Repos` is from 2022 and no
longer matches what is deployed.

**Type the secret as `password`.** The stock REST template types its `Value` as `text`,
so the token is readable by anyone with credential-read access on the workspace. A
derived template can fix that for its own service.

**There is no header prefix on `REST_API`.** The runtime copies the value straight into
the header:

```csharp
httpClientConfig.AuthorizationHeader = new HttpClientApiKeyAuthConfig()
{ Key = key, Value = value, KeyLocation = ApiKeyLocation.Header };
```

So for `Authorization: Bearer <token>` the stored value must literally start with
`Bearer `. Say so in the field's placeholder and tooltip. Only `AI_OPENAI_COMPATIBLE`
has an "Auth Header Prefix" field, and it comes with its own branch in the factory.

**Give the template a `Method`, or Test Connection cannot run.** Validating a credential
whose template has no `Method` property fails with
`Invalid verb: Verb not found. Only GET and POST are allowed! (400)`. The probe has no
verb to use. A `select` with a single `GET` option is enough.

**`isTest: true` keeps a property out of the RUNTIME config — it is not a cosmetic
flag.** `CredentialsApiBuilder.SetBaseUrl` reads `CredentialApiKeys.Path` (labelled
"Test endpoint" in the UI) and **appends it to the base URL**:

```csharp
credentialKeys.TryGetValue(CredentialApiKeys.Path, out var path);
var testEndpoint = path?.Trim() ?? string.Empty;
...
var fullUrl = baseUrl + testEndpoint;
```

Without `isTest`, a user who fills in a test endpoint silently repoints the base URL, and
every relative path the action calls hangs off the test path instead of the API root. The
stock REST template sets `isTest` on `Method`, `Path` and its test-parameters block for
exactly this reason. Copy the flag whenever you copy those fields.

State the consequence in the tooltip too: a test endpoint that hits a metered endpoint
spends real quota on every press of the button.

**An EMPTY test endpoint is not "skip the test".** The probe still fires, against the bare
base URL. APIs that serve nothing at their root answer with whatever their gateway says,
which is rarely about the credential: one returned `403 Invalid key=value pair (missing
equal-sign) in Authorization header` — an AWS SigV4 parse error that reads like a rejected
key even though the key was valid. Tell the user in the tooltip to supply a real path, and
pick one that is cheap and read-only.

### Seeding it

There is no API. Seed `credentials_template` from `BE/DataBase-Update`, the same way the
MySQL and OpenAI templates were seeded. Guard the insert on the parent existing, so a
missing parent fails loudly instead of creating an orphan. **Run the template seed before
the connector seed**, because the connector references the template's Gid — number the
files if both live in the same folder.

## Writing a flow definition: three ways the write layer misreports itself

Verified live against `PUT /api/Projects` while editing a real flow.

> ### ⚠ A PUT that answered HTTP 400 STILL PERSISTED
>
> A definition that fails server-side validation is **written anyway**, and the
> flow is left live in exactly the invalid shape the error names. Observed with
> `{"statusCode": 383, "value": "Action has too many input ports.", "target":
> "Stop: Stop"}` — the tool reported a failure, and the two new actions were in
> the definition on the next read.
>
> This is the companion to the documented empty-body hazard (O4), where a
> SUCCESS lies about landing. **Neither the success nor the failure of a
> `PUT /api/Projects` may be read as the outcome.** Only re-reading the
> definition settles what is stored.
>
> Practical consequence: an edit routine must **reconcile from whatever state it
> finds** rather than assume a clean starting point — remove what a previous
> attempt left behind, restore the original wiring, then build. A precondition
> that refuses to edit a definition whose current form is not what was read is
> what surfaces this at all.

> ### ⚠ `flow.isValid` is a STORED flag, and the launcher gates on it
>
> `POST /api/Projects/{id}/run` refuses with `{"statusCode": 373, "value":
> "Process needs to be valid in order to be launched."}` based on the **stored**
> `isValid` field, not on live validation. A failed PUT stamps it `false`, and
> because the normal edit pattern is read-modify-write, **every later PUT carries
> that stale `false` forward** — so a flow stays unlaunchable long after the
> problem is fixed.
>
> `POST /api/Projects/validate` (`process-validate`) **recomputes and does not
> persist**: it can return `isValid: true, errors: []` while the stored flag is
> still `false`. A flow can therefore be provably valid and still refuse to run.
>
> The fix is to write the flag **from the validator's verdict** and then re-prove
> by actually running the process. Hand-asserting `isValid: true` claims a
> property instead of propagating one.

> ### ⚠ A scripting node stores its code TWICE, and editing one copy is invisible
>
> | where | what it is |
> |---|---|
> | `action.parameters[<n>].value` | the **executed** copy; placeholders spelled `<%N%>` |
> | `action.customData` → `configuration[]` → `settings[]` (`label: "Code"`) | the **designer's** copy: the same source with the **variable IDs substituted** for the placeholders |
>
> Changing only `parameters` changes behaviour — the run proves it — while the
> designer still renders the old source, including any comment that is now
> false. A save from the UI writes the designer's copy back, so a one-copy fix
> can be undone by someone opening the node and pressing save. (That overwrite
> direction is reasoned, not measured here; the disagreement between the copies
> is measured and is reason enough to keep them in step.)
>
> **Edit both copies in the same write**, and remember the substitution differs:
> `<%3%>` in `parameters` is the literal variable GUID in `customData`.

### Two validators, and they answer different questions

- `process-validate` (`POST /api/Projects/validate`) — the back-end oracle.
  Blocks the save.
- `process-fe-validate` — the designer-layer check. Reports codes such as
  `MISSING_STOP` and `TYPE_MISMATCH` that the back end does not, including
  warnings that do not block anything.

Ask both when a flow misbehaves: a run refusal says only "invalid", while the BE
validator names the action and the FE validator explains what the designer would
show. When attributing an FE warning to your own change, compare the relevant
sub-structure across the before/after exports — a warning about binding types is
not yours if the bindings are byte-identical and you changed only script text.

### Flow-control wiring constraints worth knowing before you design a branch

`Stop` has `inputPorts: 1`. A branch that must terminate cannot simply add a
second edge into it (`statusCode 383`), and a terminal action with no outgoing
port is refused too (`statusCode 391` plus the FE validator's `MISSING_STOP`).
Converge branches through a `Join` (`fb6a9d14-…`, `inputPorts: -1`) and let the
Join own the single edge into `Stop`. Template port limits come from
`get-actions` (`inputPorts` / `outputPorts`, `-1` meaning unlimited), so read
them rather than discovering the limit through a failed write.

## Enumerating a workspace: which surface answers, and what an empty list means

An empty list and a refused call are indistinguishable once both are rendered as
"0 items", so an inventory must record whether each surface actually **answered**.
Two live traps:

- **`list-credentials` rejects `--workspace-id`** (it is profile-level) and returns
  a usage error. `get-credentials` is the workspace-scoped surface and keys the id
  as **`gid`**, not `id`. Treating the first one's refusal as an empty result
  reports zero credentials for a workspace that holds several.
- **The rows of a Data Store are not where the other lists are.** Processes and
  credentials page under `result.pageItems`; `datastore-get-rows` returns
  `result.columns` plus a nested envelope at **`result.rows.pageItems`** with its
  own `totalItemCount`. Reaching for `result.pageItems` yields `None`, which reads
  as "not established" when the number was there to be had.

## `Data Store` is an ACTION, and what it can do

Template `02577ada-0000-0100-0000-00000000a001`, one input port and one output.
Settings: `Select Data Store`, `Operation` (**SELECT / INSERT / UPDATE / DELETE**)
and a side-panel `Configure Operation`. So a process can read and write rows.

⚠ **The action existing is not the mechanism working.** That a process CAN insert
and select says nothing about whether a row written by one run is readable by a
later, separate run, which is the property a token-map or audit design actually
rests on. That needs two runs to settle and cannot be read off the catalogue.

⚠ **A Data Store row is mutable by design** — the same action offers UPDATE and
DELETE — so nothing in the mechanism makes a row tamper-evident. An audit trail
built on one inherits that.

## Exports: what can be named, and what a pack section proves

The export request names components by type: `--data-models`, `--processes`,
`--documents`, `--webhooks`, `--forms`, `--credentials`, building a body of
`dataModelIds / flowIds / documentIds / webhookIds / formIds / credentialIds`.
⚠ **There is no way to name a Data Store in an export request.**

The resulting `.procesio` file is JSON (not a zip) whose top level is
`DataTypes, Credentials, Webhooks, DocumentTemplates, Flows, Forms, DataStores,
TimeStamp`. ⚠ **A section existing in the format is not evidence that anything
populates it.** Measured live: a selection of `--data-models all --processes all`
resolved one data-model id — the backing model of the workspace's only Data Store
— and the resulting pack reported `DataTypes: 0` and `DataStores: 0`, with the
store's id absent. Whether a store travels when an exported flow *references* it
is a separate question and needs a referencing flow to answer.

⚠ **Scan every export before it goes anywhere** (CLAUDE.md hard rule 1).
`--export-sensitive-data` is off by default and `Credentials: 0` in the sections
is not the same as "no secret anywhere in the file".

## Flow control: what blocks, what does not, and what is absent

Read from the 233-template catalogue:

| action | semantics |
|---|---|
| `Call Subprocess` | the child runs **sequentially** and control returns to the parent when it completes — **it blocks** |
| `Trigger Subprocess` | the child runs **asynchronously**; the parent does not wait |
| `Delay` | suspends execution for a **specified time**, not until an event |
| `Form Trigger` | creates a form instance and returns; it does not block |

⚠ **No action in the catalogue waits on an external event.** A poll is therefore
expressible (raise a form, then loop a Delay plus a Data Store SELECT until the
row appears) but a durable hold-for-a-human is not a primitive. Whether such a
poll survives depends on the process timeout, on whether a loop construct exists,
and on whether a suspended instance survives a platform restart — none of which
the catalogue answers.

⚠ **There is no logging or audit action at all.** Nothing in the catalogue matches
log, audit, trace or history, so an audit trail has no home other than a Data
Store.

## The `Data Store` action: what it takes, and four ways it refuses

Template `02577ada-0000-0100-0000-00000000a001`. Settings: `Select Data Store`
(a101), `Operation` (a102) and a side panel (a109) holding `Set Values` (a103,
type `data-store-mapper`), paging, `Where` (a106, `data-store-decisional`),
sort, and the outputs `Result Rows` (a10a), `Total Count` (a10b) and
`Affected Rows` (a10c).

> ### ⚠ `Operation` takes the option's `value`, not its display name
>
> The select's options read `name: "INSERT"` / `value: "InsertRows"`. Sending
> `INSERT` **saves and validates cleanly**, then fails only at run time with
> `Unsupported operation 'INSERT'`. The runtime wants `InsertRows`,
> `SelectRows`, `UpdateRows`, `DeleteRows`. Same trap as the REST credential's
> authentication method: a plausible raw string is accepted by every check and
> dies on the first real call. **For any `select` setting, resolve the option
> and send its `value`.**

> ### ⚠ `Result Rows` must bind a NON-LIST variable
>
> Bound to a variable declared `isList: true`, the whole process is refused at
> CREATE with `HTTP 500 "Nullable object must have a value."` - a .NET unwrap
> that names no field. Bound to a non-list variable of the same data type it is
> accepted, and it returns the rows as a list anyway. Isolated by posting the
> same flow twice with one field changed.

> ### ⚠ A mapper row's target is `column`, and it resolves by NAME
>
> `Set Values` reuses the document-mapper control, so the front-end validator
> checks a `document` field and never notices that the data-store backend wants
> something else. Three distinct errors mark the path:
>
> | row carries | runtime says |
> |---|---|
> | `document: <columnId>` | `A Data Store Decisional column reference cannot be null or empty.` |
> | `column: <columnId>` | `Data Store Decisional column '<guid>' does not match any Data Store column.` |
> | `column: <columnName>` | resolves |
>
> ### The SOURCE side: a `source` operand with its own inline variable array
>
> **Resolved 23/08/2026.** A mapper row is the same DTO the Call Subprocess
> input mapping uses (`Domain.Models.CallSubProcess.MapFromVariables`), and the
> working row for a Data Store is:
>
> ```json
> {"id": 0,
>  "source": {"value": "<%0%>",
>             "variable": [{"id": 0, "variableId": "<processVarId>",
>                           "attribute": null}]},
>  "column": "row_key"}
> ```
>
> ⚠ **The variable array lives INSIDE the source operand, not on the
> parameter**, and the placeholder index matches the `id` within that inline
> array. The parameter's own `variable` list stays empty.
>
> The Call Subprocess form of the same row names its target `destination`
> (a variable); a Data Store names it `column` (by NAME, per the table above).
>
> ⚠ **Why this took two attempts to find.** A first pass tried fourteen shapes
> by varying the field NAME while holding the value SHAPE constant - `process`,
> `value`, `variable`, `input`, `data`, `source` as a bare string, `process` as
> an operand object. The answer was a different SHAPE under a name already
> tried. When an error names a type, read that type from a live example rather
> than guessing another field name: one export of a real Call Subprocess action
> settled it on the first try.

> ### ⚠ A `Where` in the Decisional shape is refused at CREATE
>
> `[{"id":0,"condition":[{operator, leftOperator, rightOperator}]}]` satisfies
> the platform's own front-end validator (which requires only an operator and a
> non-empty `leftOperator.value`) and the backend still answers HTTP 500. A
> SELECT without a `Where` is accepted and returns every row.

**Finding which parameter refuses.** A failed POST creates nothing, while a
successful one leaves an object that may not be deletable under the block's
rules. So climb **down** from the fullest configuration, removing one parameter
per attempt: every refusal costs nothing and the first acceptance leaves exactly
one object, the best configuration that works.

**Writing rows from outside a process:** `datastore-add-rows --id <store>
--rows @file`, where the file is a JSON **array** of dicts keyed by column
**display name**. It is `--rows`, not `--payload`.

**Reading them:** `datastore-get-rows` returns `result.columns` plus a paged
envelope at **`result.rows.pageItems`** with its own `totalItemCount` - not the
top-level `pageItems` that processes and credentials use.

## Data Stores in an export pack: measured, after the tool was fixed

> **History, because two earlier readings were wrong and both are easy to repeat.**
> First: "a Data Store does not travel even when a referencing process is
> exported - a platform defect." Second: an import's `HTTP 403` read as a licence
> gate. Both came from a tool that could not make the request - `export` sent no
> `dataStoreIds` and `import` posted the wrong part name with none of the required
> headers. ⚠ **When a request cannot name a thing, its absence from the response
> says nothing about the server.**

Both actions now send the documented request. What the platform actually does:

| | |
|---|---|
| **the store travels** | `export --data-stores <name>` yields `DataStores: 1`, carrying `Id`, `Name`, `Description`, `DataTypeId` and every column |
| **its backing data model travels with it** | `DataTypes: 1` appeared without being asked for |
| ⚠ **rows do NOT travel** | schema only. Fixtures sitting in a build workspace are not shipped |
| **the id is PRESERVED on import** | the imported store keeps the source's GUID, the way a flow keeps its client-supplied Id |
| **a referencing process resolves correctly** | the imported process's store parameter points at a store that exists in the target |

⚠ **Do not confirm that last row by checking that the id resolves.** Because the
id is preserved, "a store with that id exists here" is true whether the target
has its own store or the reference dangles back into the source workspace. The
two are told apart by CONTENT: rows do not travel, so the target's store must be
**empty** while the source keeps its rows. Measured: source 5 rows, target 0.
Same id, different contents, therefore different objects.

⚠ **A process does NOT carry its store.** Exporting a flow that reads or writes a
store, without naming the store, produces a pack whose process definitions carry
a store id the receiving workspace does not have. The export summary counts the
`DataStores` section precisely so that case is visible.

**Import:** `POST api/Transport/import` wants the multipart part named
**`importedData`** and **seven required boolean headers** (`overrideData`,
`importDataTypes`, `importFlows`, `importCredentials`, `importDocuments`,
`importForms`, `importDataStores`), plus `Workspace:Admin`. ⚠ **It answers `403
Forbidden` with the body `MIGRATE` on ANY error**, so a malformed request and a
permission failure are indistinguishable from the response alone. The tool now
echoes the headers it sent, so a 403 can be read against the request that caused
it.

## DataStore error surface — read the code and target BEFORE bisecting

⚠ **A first version of this note claimed the create endpoint returns a generic
500 that names no field, so "any create failure has at least two candidate
causes and bisection is the only route". That was generalised from ONE cause and
it is WRONG.** Measured with 15 single-fault payloads against
`POST /api/DataStore`, each mutating exactly one thing away from a payload
verified to create:

| fault kind | example | HTTP | statusCode | target |
|---|---|---|---|---|
| length | `description` over cap | **500** | **1001** | `data_store` |
| length | `name` far over cap | **500** | **1001** | `data_store` |
| emptiness | `name` is `""` | 400 | 1005 | `Name` |
| structural | no `name` member | 400 | 1005 | `Name` |
| emptiness | a column name is `""` | 400 | 1005 | **`Columns[1].Name`** |
| duplication | two columns share a name | 400 | 463 | **`Columns[1].Name. Duplicate name: row_key`** |
| cardinality | no primary key | 400 | 502 | `Columns` |
| collision | column named like a system column | 400 | 502 | `Columns` |
| referential | `dataTypeId` is a guid naming no type | 400 | 1004 | `Columns` |
| syntactic | `dataTypeId` is not a guid | 400 | model-validation | **`columns[1].dataTypeId`** |

**8 of 10 refusals NAME the offending field, several down to the array index and
one down to the offending value.** Six distinct status codes, two distinct HTTP
statuses. The endpoint is not generic at all.

> **The generic `500 / 1001 / data_store` is the LENGTH-LIMIT signature
> specifically.** It is not what a create failure looks like in general.

**Apply:** read `statusCode` and `target` first — usually they name the field and
no bisection is needed. Bisect **only** on `500 / 1001`, and then start with the
free-text fields, because that code has so far only ever meant a length cap.
A create that returns 500 leaves nothing behind (verified by re-listing), so
bisecting upward from a minimal payload is safe.

### The known length cap

`description` accepts at most **256 characters**; 256 is accepted, 257 refused
(bisected). `name` also has a cap, not narrowed.

⚠ **The cap is on METADATA, not on data.** A **5,000-character value** written
into a string COLUMN via `POST /api/DataStore/{id}/rows` was accepted and stored
in full, at the same time the store's own description was capped at 256.

### Target granularity VARIES BY ENDPOINT — do not carry the create behaviour over

| endpoint | fault | HTTP | statusCode | target |
|---|---|---|---|---|
| `GET /api/DataStore/{id}` | guid names no store | 404 | 1004 | `data_store` |
| `POST /api/DataStore/{id}/rows` | unknown column | 400 | 502 | `rows` |
| `POST /api/DataStore/{id}/rows` | required column absent | 400 | 502 | `rows` |

The rows endpoint names only the **collection** (`rows`), never the offending
row or column, while create names `Columns[1].Name`. **So "the API names the
field" is true of create and NOT true of the rows endpoint** — which is exactly
the over-generalisation this note was corrected for. Measure the endpoint you
are on.

### Two paging shapes on the same tool, and they differ

- `datastore-list` → items at **`result.pageItems`**
- `datastore-get-rows` → items at **`result.rows.pageItems`**, count at
  `result.rows.totalItemCount`

A reader written for one returns an empty list against the other **and looks
like an empty store**. Both mistakes were made here: a populated workspace read
as "0 stores", and a row-count control silently returned `None` on both sides of
a write so it could not report that a probe had landed.

### `datastore-delete-rows` operator vocabulary

`eq` is not an operator. The accepted set is `between, contains, endswith,
equals, greaterthan, greaterthanorequal, in, isfalse, isnotnull, isnull, istrue,
lessthan, lessthanorequal, like, none, not…` — use **`equals`**. The tool lists
the full set in its refusal, so read the error rather than guessing again.

### Faults `POST /api/DataStore` does NOT reject

Measured accepted, so do not assume the platform is validating these:

- an **empty `columns` list**, and a payload with **no `columns` member at all**
- **two columns both marked `isPrimaryKey`**
- a **column name containing a space**
- a **duplicate store name** — two stores may share a name, so any
  "find the store called X" helper is ambiguous by construction

## `PATCH /api/Projects/{id}/toggle-activation` reports success and does not activate

Measured: a process duplicated with `POST /api/Projects/{id}/duplicate` is
created **inactive**, and the toggle endpoint does not change that.

```
before  : active=false
PATCH .../toggle-activation  ->  rc 0, {"result":{"value":null,"errors":[]}}
after   : active=false
```

Not the tool wrapper — the raw endpoint behaves identically. `errors` is empty
and the HTTP status is success, so **nothing in the response indicates the write
did not land.** This is the mirror of the more familiar failure: here a write
reports SUCCESS and does not take effect.

⚠ **`status` on the flow is NOT the activation flag.** `GET /api/Projects/{id}`
returns `status: 0` for an active process and an inactive one alike. The field
that distinguishes them is **`active`**, and it appears only in the
**`list-processes`** projection. Reading `status` to check activation returns the
same value in both states, so it cannot report the difference.

**Apply:** never infer activation from the toggle's response or from `status`.
Read `active` from the process list before and after, and treat an unchanged
value as failure regardless of what the call returned.

**Consequence for launching:** `POST .../run` on an inactive process refuses with
`statusCode 373 "Process needs to be valid in order to be launched."`, whose
`target` carries the real reason — `Flow with id ... is inactive` — while
`process-validate` independently reports `isValid: true`. **Valid and active are
two different things and the message leads with the wrong one.**

**Route that works:** `process-create --config-file` produces a process that is
active on creation, which is how the existing slice processes were built. A
duplicate has to be activated some other way, and this endpoint is not it.

⚠ **`PUT /api/Projects` does NOT reset activation** - measured directly on an
active process: `active` is `true` before the save and `true` after it. An
earlier draft of this note claimed the opposite. That claim was INFERRED from a
sequence (toggle, then save, then observe inactive) and never isolated; the real
explanation is simply that **the toggle never took effect at any point**. The
save was innocent.

The lesson is the one this file keeps re-learning: with two suspects and one
observation, isolate before writing it down.

## Node action: `<%N%>` interpolates a variable RAW into the JavaScript source

This is the single most expensive thing to not know about the Node action.

`<%0%>` is **not** a bound parameter. The variable's value is pasted into the
script text before it is parsed. So a `string`-typed variable holding
`probe-input` produces the source `var IN = probe-input;`, which JavaScript reads
as the expression `probe - input`, and the action fails with:

```
l0_err: "probe is not defined"
```

⚠ **A BARE SCALAR is injected as CODE.** Anything that is not a valid JS
expression is a syntax or reference error, and anything that IS a valid JS
expression executes.

⚠ **A STRUCTURED value is NOT — it is JSON-encoded, and that is a security
property, not an ergonomic one.** Measured 25-08-2026: a json-typed variable
carrying an ARRAY of row objects, one of whose string fields contained a double
quote, interpolated with the quote **escaped**; the body parsed and ran and the
value round-tripped. So the `{"__t": …}` wrapper is not merely the workaround
that makes interpolation valid — **it is what makes customer-supplied data safe
to pass**, because a structure forces JSON encoding where a bare string gets
pasted raw.

An earlier version of this note said "the value is injected as code, not as
data" without qualification. That was generalised from a single bare-string
sample and is **wrong for structures**. The distinction matters in production:
a gazetteer populated from a customer's HR system reaches the Node action inside
an array, and is therefore escaped.

**The convention that works**, and the reason the existing processes look the way
they do: declare the variable as **`json`** and pass an **object**, so the
interpolation lands as a valid JS object literal, then unwrap inside the script.

```
variable:  {"name": "text", "type": "json", "direction": "input"}
payload :  {"text": {"__t": "the real string"}}
script  :  var __w = <%0%>;
           var text = (__w && __w.__t !== undefined) ? __w.__t : __w;
```

A `json`-typed variable is **not on its own sufficient** — measured: a json
variable holding the bare string `probe-input` still interpolates unquoted and
still throws. The value has to be a JSON *object* (or otherwise a self-contained
literal).

### An error variable declared `process` is invisible

`run-process` returns only **output**-direction variables. A Node action that
throws writes its message to the variable bound to `Error`, and if that variable
is `process`-direction the response carries `null` for the result and **nothing
else**. A thrown script and a script that returns nothing are then
indistinguishable, and `status` is **50 = finished** in both cases.

**Always declare the Error variable as `output` while developing.** One line
(`"probe is not defined"`) replaced several rounds of guessing here.

### Node `Timeout` is constrained to 60..300

A value outside it is refused at save with a designer error that names the
action and the range: `LIMIT_RANGE  "Please make sure that the value is between
60 and 300."`

### Instance status codes

`30` running, `40` finished-with-errors, `50` finished, `6` stopped. ⚠ **50 does
not mean the script succeeded** — an action whose error was captured into a
variable still finishes 50 with an empty top-level `error: []`.

### The script engine's capabilities, MEASURED on Internal-PROD 25-08-2026

| | |
|---|---|
| `String.prototype.normalize` | present; NFC composes (`e`+U+0301 → 1 char), NFKC works |
| `Array.from`, `codePointAt`, `String.fromCodePoint` | present |
| astral code points | `"\u{1D400}"` → UTF-16 length 2, `Array.from` length 1 |
| regex Unicode property escapes `/\p{L}/u` | supported |
| `toLowerCase()` | ⚠ does **not** fold: eszett stays eszett, Greek final sigma stays final sigma |
| `process` global | **absent** — not Node; a sandboxed engine |

⚠ **A regex property escape the engine did not support would be a PARSE-time
SyntaxError**, which no `try`/`catch` inside the script can contain — it kills
the whole body. Capability probes must therefore put each risky construct in its
own deployment, not in one wrapped block.

## What a `Data Store` SelectRows hands a Node action

Measured 25-08-2026: bound to `Result Rows` and passed into a Node action via
`<%N%>`, a SelectRows result arrives as a **bare JSON array of row objects**,
each keyed by **column name** — not wrapped under `rows`, `pageItems`, `items`
or `data`, and not paged.

```js
var rows = <%1%>;        // [{row_key:"…", tenant_id:"…", declared_value:"…"}, …]
rows.length              // 27, the whole store
```

Note the asymmetry with the REST surface, which is where the guessing comes
from: `POST /api/DataStore/{id}/rows/filter` returns the rows nested at
**`result.rows.pageItems`** with the count at `result.rows.totalItemCount`, while
the in-flow action hands over the array directly. **Two shapes for the same
data, depending on which surface you read it from.**

⚠ The `Data Store` action has **no `Error` property**. Its settings are
`Select Data Store`, `Operation`, and the `Configure Operation` side panel
(`Set Values`, paging, `Where`, sort, `Result Rows`, `Total Count`,
`Affected Rows`). A Node action has an `Error` binding; this one does not, so a
failing store read has nowhere to put its message.

## A pack is a SKELETON: structure travels, bindings do not

Measured twice, by two different mechanisms, and together they define what an
export actually is.

| what | measured |
|---|---|
| Data Store **schema** | travels |
| Data Store **rows** | **do NOT travel** — 0 rows in the target |
| Process **flows** | travel (`Flows: 1`) |
| **Credentials** | **do NOT travel** — `Credentials: 0`, and `credentials in target: []` |

A `Call API` action carries the credential **id**, so an imported process
references a credential that does not exist at the far end. The import succeeds,
the process is valid, Layer 1 runs, and the outbound call never happens.

⚠ **Both gaps are silent in their own way.** An empty store returns zero results
with status 50; a missing credential leaves the Call API without even a status.
Neither raises anything a structural check can see.

> **This is a permanent property, not a defect to close.** Every deployment has a
> provisioning step the pack cannot carry: seed the data, create the credential,
> point it at the address. Budget it as a deployment step, and verify each part
> by **counting** at the far end rather than by the import succeeding.

## PROCESIO's outbound calls identify themselves

Captured from a tunnel's request inspector while a `Call API` action ran:

```
User-Agent: ProcesioRuntime/2.1.0
```

⚠ **Prefer the user-agent over the source IP as the discriminator.** A single
observed egress address is one sample: the platform may call from a pool, and an
allowlist built from one call is a firewall rule that works until it doesn't.

⚠ **AND CHECK WHOSE REQUEST YOU ARE LOOKING AT.** A warm-up request sent from the
build machine to prove the tunnel works appears in the same log, and on a quiet
tunnel it may be the ONLY entry. Reporting it as the platform's egress produces a
rule that admits the developer and blocks the platform. Force a real call from a
workspace that can make one, then separate them by user-agent.


## ⚠ A REST credential's connection test proves only what its Test endpoint requires

`credential-test` (and the designer's "test connection") issues a **GET to the
credential's configured `Test endpoint`**. That is the whole of the test.

Two consequences that are easy to get wrong:

| | |
|---|---|
| ⚠ **an unauthenticated test endpoint makes the test meaningless as an auth check** | it will **PASS with any credential value, including one that cannot work**. It validated the ADDRESS. Measured: a credential holding a deliberately invalid bearer passed its test, because the endpoint was a public health route |
| **`Method` is test-only** | a REST credential's `Method` is used **only** by the connection test, and its only option is `GET`. The Call API action carries its own `Verb`. Setting it does not change how the credential behaves in a flow |

**So a green connection test is evidence of reachability, not of authorisation.**
If the credential is meant to prove a token works, point `Test endpoint` at a
route that actually requires the token — otherwise verify auth by exercising a
protected route through the flow that uses it.

⚠ **`Method` is an option list valued by GUID.** Sending a raw string saves
fine and then fails at runtime with `Unrecognized Guid format`. Pass an option
name or its GUID.

## ⚠ Create a process with `process-create`. NEVER provision one by duplicating.

Measured 2026-08-25, on the same workspace, minutes apart:

| route | `active` on arrival | runnable |
|---|---|---|
| `duplicate-process` | **False** | ⚠ **refused** |
| `process-create` | **True** | ✅ runs to status 50 |

⚠ **A duplicated process cannot be made runnable through the API.**
`process-toggle-activation` returns `{"value": null, "errors": []}` — no error —
**and `active` stays False.** Activation needs the designer.

**Duplication is a designer convenience, not a provisioning mechanism.** Any
programmatic path that builds a flow by copying one produces something that
validates, reports no error anywhere, and cannot be launched.

### ⚠ And the launch refusal names the wrong cause

Launching an inactive-but-valid process returns:

```
statusCode 373  "Process needs to be valid in order to be launched."
target          "Flow with id <guid> is inactive"
```

⚠ **The message says VALID; the cause is ACTIVE.** Measured on the same process:
`process-validate` → `{"isValid": true, "errors": []}`. A reader who trusts the
message goes and audits a flow graph that was never the problem — the real cause
is only in the `target` string.

## Building a process through `process-create` — the parameter names

The high-level config is
`{"title", "variables":[…], "actions":[{"id", "action", "params":{…}}]}`.
Property names are validated, and the error **lists the valid ones**, so probe
with a deliberate bad key rather than guessing:

| action | properties |
|---|---|
| `Data Store` | `Select Data Store`, `Operation`, `Configure Operation` |
| `Node` | `Code`, `Error`, `List Result`, `Single Result`, `Timeout` |
| `Javascript` | `Code`, `Output` |

**`Operation`** takes `SelectRows` · `InsertRows` · `UpdateRows` · `DeleteRows`.

⚠ **`Operation` is NOT validated against those at build time** — a nonsense verb
passed `--dry-run` cleanly. Same hazard as a credential's GUID-valued option
list: it saves fine and fails later.

**`Configure Operation`** carries mapper rows in the accepted shape:

```
{"id": i,
 "source": {"value": "<%i%>",
            "variable": [{"id": i, "variableId": "<guid>", "attribute": null}]},
 "column": "<COLUMN NAME>"}
```

⚠ **The placeholder index must match the row's own `id`, and the `id` inside its
inline `variable` array.** A filtered operation adds the `Where` shape, whose
operands are objects and never bare strings.

---

# ⚠ ONE PROPERTY OF THE ERROR SURFACE, NOT SIX DEFECTS

Six separate findings in this file share a single shape, and reading them as six
entries hides the thing they have in common:

> ## ⚠ THE PLATFORM RETURNS A CONFIDENT ANSWER ABOUT SOMETHING OTHER THAN WHAT IT NAMES.

None of them looks broken. Each returns a well-formed, plausible result — the
kind a caller acts on — and each is measuring, naming, or reporting a different
subject than the one the caller asked about.

| # | what it names | what it actually reports |
|---|---|---|
| 1 | a create failure | ⚠ **a 500 naming no field.** Any create failure then has at least two candidate causes and bisection is the only route |
| 2 | `toggle-activation` succeeded | `{"value": null, "errors": []}` and **nothing was activated** |
| 3 | the credential works | ⚠ **only that its `Test endpoint` answered.** Aimed at an open route it passes with a bearer that cannot work |
| 4 | the process is not valid | ⚠ **the process is INACTIVE.** `process-validate` returns `isValid: true` on the same process; the real cause is only in the `target` string |
| 5 | the flow config is valid | ⚠ **`Operation` is not checked against its verb list.** A nonsense write verb passes `--dry-run` and fails at runtime |
| 6 | one dataset | **two paging shapes**, so a reader written against one silently mis-reads the other |

## What to do about it, as a rule

⚠ **Never accept a platform success as evidence about the subject you care
about. Establish what the call actually measured, then assert on the subject
directly — by counting at the far end, or by exercising the protected path.**

Concretely, and each of these is the direct consequence of a row above:

| a green from | proves | so verify by |
|---|---|---|
| a connection test | the test endpoint answered | exercising a route that requires the credential |
| `toggle-activation` | the request was accepted | **re-reading `active`** |
| a build-time validation | the shape parsed | **running it, and counting what moved** |
| a create call | something was created | **re-reading the created thing** |

> ⚠ **A guard, a test or a validator that cannot fail on the subject it names is
> decoration.** Prove each one able to fail against a deliberately broken case
> before trusting it against a healthy one.


## The `Python` action returns what the script PRINTS — assignment is silently useless

Measured 2026-08-25, five conventions against one action.

| construct | returns |
|---|---|
| `print('x')` | `{"result": "x"}` ✅ |
| `output = 'x'`, `result = 'x'`, a bare expression, a `def` returning a value | ⚠ `{"result": ""}` |
| a module that is not available | `{"error": "The X module is not available at the moment."}` |

⚠ **The failure mode is silent.** An assignment-style script completes with
status 50 and an empty `result`, which is **indistinguishable from a script that
ran and produced nothing** — and therefore from an engine that is not answering.
Any probe built on the wrong convention reports a false negative about whatever
it was testing.

⚠ **A REFUSED IMPORT ARRIVES ON `error`; A RESULT ARRIVES ON `result`.** They are
different findings and must not be read as one: a module-allowlist entry read as
a network outcome turns a sandbox rule into a false security claim.

**Parameters:** `Python` exposes only `Code` and `Output` — **no `Error`
binding**, unlike `Node` (`Code`, `Error`, `List Result`, `Single Result`,
`Timeout`). So a Python action's failure detail is only ever visible through the
`error` key of its `Output`.

**Module allowlist, still enforced (2026-08-25):** `os` and `sys` return the
orderly refusal above and the flow continues normally.


## ⚠ There is NO crypto module in the `Node` action. Hashing must be implemented in full.

`require` inside a `Node` action resolves **image contents only** — so `crypto`,
and any other module not baked into the image, is unavailable. There is no
`crypto.createHash`, and no `SubtleCrypto`: the action is not a browser context.

**Consequence for design, not just for one script:** any scheme that needs a
digest inside a flow — an idempotency key, a row key, a content fingerprint, a
signature check — **carries its own implementation**, in the action body, at the
cost of the source it adds to every request.

⚠ **And if the digest must agree with one computed outside the platform, the
ENCODING is the whole risk.** JavaScript strings are UTF-16; most references
hash UTF-8 **bytes**. A digest fed raw `charCodeAt` values **agrees on ASCII and
diverges on everything else** — which is the worst shape, because it passes any
test built from English sample data.

**Prove such a digest with three things, never one:**

| | |
|---|---|
| **published vectors** | that it is really the algorithm, not merely self-consistent |
| **the REAL corpus** | agreement on invented ASCII proves nothing about the data |
| ⚠ **a wrong-encoder negative control** | it must **disagree** on the non-ASCII rows. If it agrees, the corpus is not exercising the encoding and the test is decorative |

**Measured 2026-08-25:** on a live gazetteer, 22 of 27 values were non-ASCII, and
a `charCodeAt` encoder disagreed with the UTF-8 reference on 22 of 22 of them.

## ⚠ `process-create`'s config CANNOT express a Data Store mapper. Create, then patch.

The high-level authoring config binds each action property to a **binding** —
a literal, `{value}`, `{var}`, `{credential}` or `{template, vars}`. A
`Data Store` action's `Set Values` is none of those: it is a **mapper row list**,
and each row's `source` carries its own **inline** variable array:

```
{"id": i,
 "source": {"value": "<%i%>",
            "variable": [{"id": i, "variableId": "<GUID>", "attribute": null}]},
 "column": "<COLUMN NAME>"}
```

⚠ **`variableId` is a GUID the platform mints when the process is created.** It
does not exist while the create config is being written, so no binding form can
supply it. `{template, vars}` fills the `<%i%>` leaf and sets the PARAM-level
`Variable`, leaving the row's inline array empty — which fails as:

| FE | `REQUIRED` · `Data Store - Set Values (row 1)` |
|---|---|
| BE | `"Nullable object must have a value."` |

**The route that works is two-step, and it is the same one the pack-repair tool
uses:**

1. `process-create` the flow **without** the mapper — everything else configured
2. read the created flow back and take the **minted variable GUIDs**
3. `PUT /api/Projects` (`put-projects`) with the mapper rows carrying those GUIDs

⚠ **`Where` does NOT have this problem** and validates from the create config via
`{template, vars}`, because its operands can carry `<%i%>` with an empty inline
array. **Only the mapper needs the second step.**

### The `Data Store` side panel, in full (its properties are addressed at TOP level)

`Configure Operation` is a `side-pannel`, and its children are flattened into the
same label index — so they are passed as ordinary `params` keys, **not** nested
under `Configure Operation`.

| property | shown for |
|---|---|
| `Set Values` (data-store-mapper) | `InsertRows`, `UpdateRows` |
| `Where` (data-store-decisional) | `SelectRows`, `UpdateRows`, `DeleteRows` |
| `Page Number`, `Page Item Count`, `Sort By`, `Desc`, `Result Rows`, `Total Count` | `SelectRows` |
| ⚠ **`Affected Rows`** | `InsertRows`, `UpdateRows`, `DeleteRows` |

⚠ **`Affected Rows` is a built-in count of what the operation touched** — the
cheapest way to tell a filter that matched nothing from one that matched. **But
it is what the write REPORTS, not proof of what landed:** on this platform a
write that reports success without landing is measured, so a state change still
needs a read-back.

## Surgical flow edits — one literal, not a whole rebuild

`process-edit` (and the DTO builders) are DESIRED-STATE: they rebuild the entire flow from a
config and replace it. That is right when you own the config and wrong for a flow a human
built in the designer years ago, where reconstructing the config risks losing everything the
config cannot express. For "one literal moved" — an endpoint whose host changed, a timeout, a
SQL statement, a script body — use the surgical trio instead (all three GET the flow, patch it,
regenerate the designer layer where the normalizer can, then BE-validate + designer flow-lint
and only then PUT; `--dry-run` stops before the PUT and an invalid flow is never written):

- **`node-params --id <proc> [--node <label|id>]`** — read-only. Lists each node's runtime
  parameters with the DESIGNER label (`Endpoint`, `Time Out`, `Query`, `Second number`), the
  current value, whether it is editable text, and which variables it binds. This is the map you
  need before patching, and it costs a fraction of dumping the DTO.
- **`node-set-param --node X --property "Endpoint" --value "..."`** — set one parameter's
  literal text. It refuses a non-string (structured) value, and it refuses a new text whose
  `<%N%>` set differs from the old one: the placeholder set IS the contract with `variable[]`,
  so dropping or inventing one silently unbinds a variable with no validation error.
- **`node-replace-text --node X --find "-12-01" --replace "-01-01" --expect 4`** — exact-literal
  replace across every string leaf of the node's runtime parameters AND designer settings. This
  is how you reach a value nested inside a structured parameter (a Map Data row's source
  expression, a decisional case's literal) that the two above refuse and that the normalizer
  deliberately never regenerates. It is safe there precisely because the same literal appears
  verbatim in both layers — the runtime row holds `<%1%>-12-01` and the designer mirror
  `<var-guid>-12-01`, so one literal swap keeps them consistent without either shape having to
  be understood. `--expect N` asserts the hit count and writes nothing on a mismatch.
- **`variable-set-type --variable X --data-type <id> [--is-list true]`** — retype one flow
  variable. It REFUSES an input (type 10) or output (type 30) variable unless
  `--allow-contract-change`, because those two are the process's public contract: the run
  payload and the response a caller parses. Internal (type 20) variables are free to retype.

Built-in primitive dataType ids share the prefix `0317bfee-b2f5-4bde-bfe8-1212…`; the two that
get confused are **`…121220` = `Json`** and **`…121221` = `Object`**. An `Execute Query` Output
must be a **list<Object>** — a `list<Json>` runs correctly but the designer paints a "data type
mismatch" on the node (flow-lint `EXECQUERY_OUTPUT_TYPE`). Retyping that internal list variable
to Object fixes the designer without touching the response shape.

## An arithmetic `Add` node can be a silent no-op

Seen live on a flow that computed `year = year + (-1)`: an **`Add`** action (template
`fea7cedc-…`, "Add operation for two objects") whose `First number` and `Result` both bind the
SAME variable and whose `Second number` is a literal **did not write the result** — the variable
kept its pre-Add value and the flow ran on happily. Nothing surfaces it: the run finishes
`status 50`, `POST /api/Projects/validate` is clean, and the designer shows no error. Only the
downstream effect reveals it.

**Because it fails silently, never trust an arithmetic node from reading the canvas — prove it.**
The cheap proof is to give the operand a value whose result would make a DOWNSTREAM step fail
loudly (here: an operand large enough that the computed year produced a URL the server 502s),
run it, and see whether the run still succeeds. A successful run is then proof the arithmetic
never applied. Restore the operand to a value that keeps the OBSERVED behaviour afterwards — a
node that is currently a no-op will start doing something the day the platform fixes it, so
leaving `-1` in place is a latent behaviour change; `0` is not.

Watch for this whole class: an action whose input and output bind the same variable. Prefer a
separate result variable, and rename any node whose label describes arithmetic it does not do —
a canvas that lies costs the next reader more than the bug did.

## Deleting a node over the API: heal the edges yourself (`node-delete`)

The designer removes a node and reconnects its neighbours in one gesture. Over the API those are
two separate things, and doing only the first strands the tail of the flow: every port whose
`destinationId` was the deleted node has to be re-pointed at that node's own successor, or dropped
when it has none. `procesio node-delete --id <process> --node <label|id>` does both, then
validates + flow-lints before the PUT.

It refuses rather than guesses: `Start` / `Stop` (a flow needs both) and any node with more than
one outgoing port (which successor inherits the incoming edges is a design decision). Healing never
creates a self-loop or a duplicate edge — the designer renders both and the engine follows them, so
a missing edge is the safer failure. Variables are left alone: another node may still read them,
and there is no API to delete a flow variable, so an orphaned one simply stays (an output variable
left behind still advertises itself in the process's public contract, always null — worth removing
by hand in the designer).

`canvasData` is only the viewport (`{x, y, zoom}`), so it needs no cleanup when a node goes.

**Why a dead node is worth deleting rather than disabling:** it still executes, still bills an
execution, and still throws into whatever error variable it was given. A node whose upstream
contract moved on (a stored procedure that renamed its output columns, say) fails on every single
run while the flow reports success, because its output is no longer read by anything.

## Publishing a form to an anonymous visitor: TWO switches, not one

A form is reachable by a stranger only when both of these are true, and each is set through a
different endpoint. Getting one and not the other produces a URL that exists and refuses.

**1. A CustomUrl entity** (`POST /api/CustomUrl/FormTemplate`, scoped by the `workspaceid`
header — without it, statusCode 1008 "Not working on workspace"). Body:

```json
{"workspaceId":"<ws>","entityId":"<formTemplateId>","entityType":1,"type":3,"url":"<slug>"}
```

The server mints a `tinyUrl` in the response and the form renders at
`https://forms.procesio.app/{tinyUrl}`. The human-readable `url` slug is stored but the tinyUrl is
what resolves; a bare `/forms/{id}` 404s. Read an existing one back with
`GET /api/CustomUrl/FormTemplate/{formTemplateId}` — that is the fastest way to learn the shape
from a form that is already published.

**2. `IsPrivate: false` on the form itself**, together with `Status: 1` (published). This is the
reachability switch, and it is separate from the custom URL: a form with a tinyUrl but
`IsPrivate: true` still demands a PROCESIO login. `form-update --is-private false --status 1`
sets it; `build_put_body` leaves `IsPrivate` echoed untouched otherwise, because opening a form to
the public is a publishing decision that no unrelated save should make by accident.

**An anonymous form really does run its processes.** A `FORM_LOAD` / `CLICK` `RUN_PROCESS` on a
public form launches under the form's own anonymous `FormProcess` route, not the caller's session:
verified by loading a public form with no account and finding finished instances attributed to it
(`list-instances` shows `formName`). A 401 in the page console does not by itself mean the form is
broken — check for the instance rather than trusting the console.

**To prove "public" end to end, call it with no credentials at all**: publish -> launch ->
variables against `webapi.procesio.app` with only `Content-Type` and `formTemplateWorkspaceId`
headers. A test that runs under your own token proves nothing about a stranger.

## Processes have no folders — group by name prefix

`/api/Actions/folders` is the ACTION catalog's folders. There is no equivalent for processes
(`/api/Projects`), so a workspace's process list is flat. To keep maintenance/scratch processes out
of the way of the real ones, rename them with a shared prefix so they sort together, and put the
warning in the name itself where a process is dangerous to run (a seed script that duplicates rows
on a second run). A name is the only signal the list gives a reader.

**Verify a rename by re-reading.** `PUT /api/Projects` answers 200 with an EMPTY body, and an
empty-body success has been observed not to persist. `list-processes` after the PUT is the
assertion; the 200 is not.

## Adding a control to a form that already exists (`form-add-element`)

`form-create` speaks an authoring config and `form-edit` rebuilds a whole form from one, so neither
can add a control to a form built in the designer — the two shapes are different languages (an
authoring config has no element ids at all). `form-add-element --id <form> --elements '<json>'
[--parent <name|id>]` fills that gap, and the reason a splice is safe is a structural invariant:

**A control's data-model sub-model id IS its element id, and its attribute ids ARE that element's
own config ids.** So new controls only ever contribute new sub-models. The live `Data.dataModel` is
appended to, never regenerated — which matters because a RUN_PROCESS/MAP trigger references a field
by the path `root.fields.elementId.valueAttrId`. Rebuilding the model would mint new ids and break
every mapping already on the form, silently.

A duplicate control NAME is refused: the designer resolves a field path back to a name, so two
controls sharing one make every reference to it ambiguous.

### Designer forms carry EMPTY map rows, and they are not harmless
A hand-built form's RUN_PROCESS config routinely contains a row like
`{"id":1,"left":{"value":""},"right":{"value":""}}` — designer litter from an added-then-abandoned
mapping. It sits there doing nothing until a tool tries to resolve it, so strip empty rows from
`inputMap`/`outputMap` before writing an event back. Seen on more than one form in the same
workspace.

### Extending a process's input contract without breaking its form
`process-edit` reuses variable ids BY NAME, so adding inputs to a live process keeps every existing
form mapping valid: declare the existing variables with their existing names plus the new ones, and
only the new ones get fresh ids. Confirm it with `--dry-run` first — and note that the dry-run only
became trustworthy for this once it was routed through the edit path (see DTO-SUBTOOLS-NOTE.md).

## An OAuth2 predefined credential needs a human click before it can be used

The `REST_API_OAUTH_PREDEFINED` family (Google Calendar/Drive/Mail/…, Microsoft Graph, Outlook, …)
can be CREATED over the API but not AUTHORIZED over it: the type carries a property of type
`google-auth-button`, and the token only exists after a person completes Google's consent screen.

Creating one: `credential-create` with `template` = the exact type name (e.g.
`"OAuth2 (REST API) / Google Calendar"`). Two fields are required even though the UI pre-fills them,
and omitting either fails with `statusCode 113 "Required credentials fields should not be empty"`
naming only the first one:

- **`Method`** — a select whose only option is `GET` (it is the TEST call's verb, not the verb your
  Call API nodes use).
- **`URL`** — the service base, pre-filled on the template (`https://www.googleapis.com`).

`Scopes` is a pills list and defaults to the full recommended set; narrow it at creation time rather
than after, since changing scopes later means re-consenting anyway.

Then `GET /api/Credentials/authorize/{id}` returns `{url, headers}` — the Google consent URL,
carrying a one-shot `state`. Hand that to the person who owns the calendar, or have them press the
Google button on the credential in the designer, which mints a fresh one. Nothing else about the
credential works until that returns.

**Plan the work around it:** everything else (the stored procedures, the data model, the flow) can
be built while the credential sits unauthorized. Only the first live run is blocked.

## `Call API`: use the unversioned action, and copy a live node for the payload

`Request Parameters` is a `tabs-payload-v2` structured property (body / headers / query tabs), and
the process builder has no special handling for it — it is not a value a config can express by
label. Authoring one blind is guesswork; take the shape from a live node that already works
(`node-params` on a real flow, or a `.procesio` export) rather than inventing it.

And use the unversioned `Call API`, never `Call API v3`: the v-pinned ones are older generations
with differently named outputs (`Status Output`/`Body Output` instead of
`Response Status`/`Response Body`).

## `Call API` needs `Request Parameters` even for a bodyless verb

A DELETE (or GET) node authored without the `Request Parameters` property fails at RUN time with
`Error while building input model: CallApi has NULL value on request parameters.` — it is not
optional just because the verb carries no body. Give it the empty payload:

```json
{"body": {"type": "RAW", "value": {"BINARY": "", "FORM_DATA": [],
                                   "RAW": {"format": "json", "value": ""},
                                   "X_WWW_FORM_URLENCODED": []}},
 "headers": [], "queryParams": []}
```

That whole object is the shape the property stores; the RAW `value` string is where `<%N%>`
placeholders go for a request that does have a body. Same save-clean / run-fatal class as the verb
guid: FE and BE validation both pass.

## An untyped `object` variable cannot carry an attribute path

`{"var": "responseBody", "path": ["id"]}` against a variable declared `type: "object"` fails the
save with `Error converting value "id" to type 'System.Guid'`: there is no model to resolve the
name against, so the name is written where an id belongs. Bind a Call API's `Response Body` (or any
output you intend to read a field out of) to a variable typed by a MODEL — even a three-field one
covering just the fields you need. The response's other fields are simply ignored.

## A loop-scoped variable reads back NULL after the loop

The final instance output of a flow shows a `For Each` body's variables as null even when every
iteration set them — they are the loop's scope, not the flow's. Do not read that as "the body never
ran": check the side effect instead (the row it wrote, the resource it created). A run that reports
`status: 50` with a null loop variable and a correctly updated database is working exactly as it
should.

## Regenerate a stored procedure from its LIVE definition when adding one condition

Changing one line in a long, carefully-written procedure by retyping it invites silent drift in the
other fifty. Read the live body (`SELECT m.definition FROM sys.sql_modules m JOIN sys.objects o …`),
do a string replace of the exact block being changed, assert the block was found, swap
`CREATE   PROCEDURE` for `CREATE OR ALTER PROCEDURE`, and write THAT as the migration:

```python
assert old in src, "the block moved; re-read the live procedure before regenerating"
src = src.replace(old, new, 1).replace("CREATE   PROCEDURE", "CREATE OR ALTER PROCEDURE", 1)
```

The assert is the point: if the procedure changed underneath you, the migration refuses to generate
rather than quietly reverting somebody else's edit.

## A validation that only hides an option in the UI is not a validation

Slot availability is filtered in `sp_GetAvailableSlots`, and it would have been easy to leave a new
exclusion there alone. But `sp_BookMeeting` re-derives the offered list from that same procedure
INSIDE its transaction and refuses anything absent from it — so a rule added to the slot engine is
automatically enforced at the booking boundary too, against a hand-crafted POST that never saw the
form. Prove it that way round: call the booking procedure directly with a time the rule should
forbid, and check it is refused. A filtered dropdown proves nothing.

`DATETIME2` also does not accept `'2026-09-07T12:00'` from a string literal — seconds are required
(`'2026-09-07T12:00:00'`), and the failure is a bare `Error converting data type varchar to
datetime2` with no hint that precision is what it wants.

## A table added through the API has no row context — reach its rows through the page

A `dynamic-table-row` created by `form-add-element` renders and behaves like a designer-built one
until something inside it needs to know **which row it is in**. It never does. Measured on a spliced
table, in every handler that fires from inside a row:

- `fld('<RowName>')['$.item']` is **undefined** — on a side-panel's `onOpen`, on a button's
  `onClick`, and on a control's `onInput` alike. On a designer-built table the same expression is
  the row and is the basis of that table's whole edit mechanism.
- A row-scoped control read by name gives a field object whose `.value` is `undefined`, whatever is
  displayed in that row.
- A five-segment row path (`<form>.<ns>.<row>.<the row's "$.fields" attr>.<child>`) in a process map
  resolves to nothing, so a save silently sends empty parameters. Adding `$.fields` to the stored
  data model does not help; the runtime builds its own sub-model from the element's configs.
- `document.activeElement` is already back on `<body>` by the time a click handler runs, so the
  pressed button cannot be recovered that way either.

The row's values are not lost, though — the table binds the row's `Actions` object into that row's
controls, so **the values are on the page**, in the DOM, exactly as the person sees them. That gives
a working pattern for per-row edit and delete on a spliced table:

1. **Paint each row with an `Actions` object** keyed by the names of the controls in its action
   column. The table fills those controls from it when the row's panel opens.
2. **Record which row was pressed, in the page, before the framework's handler runs.** The form's
   global JavaScript attaches a `mousedown` listener to every `tbody tr button` and writes the row's
   cell texts onto `<body>` as a data attribute. This is the only reliable moment: a listener on the
   control fires, one on `document` does not, and after the click the row is unidentifiable.
3. **In the handler, read that attribute through `window.parent.document`** (the form's own
   `document` is a sandboxed frame holding none of the form) and match the cells against the list
   the page already has in a variable, to recover the row's primary key.
4. **Read the rest off the open panel** — its inputs, by their labels — and write everything into
   plain hidden fields at TAB level, which four-segment paths address normally. The process map
   reads those.

Two failure modes this avoids are worth naming, because neither reports anything: without the key,
an upsert quietly **creates a second record** instead of changing the one on screen; and an empty
value bound to a typed process variable fails at LAUNCH, so the process never starts and the handler
chain ends with no message anywhere.

### Smaller facts from the same build

- **A select's options come only from a process output map.** Assigning `sourceValue` from a handler
  leaves "No data available" on screen. To feed a second select from data already fetched, clone the
  existing output-map row and repoint its right-hand side at the new element's `sourceValue` config
  — do not write a handler.
- **`readonly: true` on a `datetime-input` closes its calendar as well as its keyboard**, which
  makes the value unchangeable rather than merely untypeable. A date control already refuses
  anything that is not a date, so leave it writable.
- **An option's label is not its name.** A list rendered as `<name> (<detail>)` cannot be matched
  back to an id by comparing the shown text to the stored name; strip the trailing parenthetical
  first.
- **A form's global CSS/JavaScript is stored encrypted** in `Data.code`; read and write it with
  `form-get-code` / `form-set-code`, and pass `--workspace-id` (the call returns HTTP 400 without
  it). It can be empty on a form whose behaviour appears to depend on it — a local draft that was
  never deployed looks exactly like a deployed one until you fetch it.

### A column header's capitals may exist only in CSS

Table headers on a form render upper-cased, but that is `text-transform`, not the text. `textContent`
returns what was authored ("Status"), while `innerText` returns what is painted ("STATUS"), so a
guard written against the screen — `head.textContent.indexOf('STATUS')` — never matches and the code
after it silently does nothing. Compare case-insensitively, or read `innerText` deliberately.

The same distinction bites when checking whether an action is still on screen: `textContent` includes
the text of hidden elements, so a button that has been hidden still shows up in a row's text. Assert
on the element's own `style.display`, not on what the row reads.

### Editing a spliced table's rows: what the page will and will not tell you

Building per-row edit and delete on an API-added table turned up a set of traps that are each cheap
to avoid and expensive to diagnose, because none of them raise anything.

- **Carry the record's key in the row, not its description.** Matching a row by the fields it shows
  works until one of those fields is edited: the save then finds no record and does nothing, and the
  delete has no id to send. Give the table a column holding the primary key and read that.
- **Do not hide that column with `display: none`.** These cells are flex items; removing one from the
  line leaves the row a column short and the remaining columns mis-sized - in practice the action
  column collapsed to zero width and its buttons became unclickable. Collapse it instead
  (`flex: 0 0 0`, zero width and padding, `overflow: hidden`, transparent text): it keeps its place
  in the layout and its text is still in `textContent`, which is all the reading code needs.
- **`textContent` includes hidden text; `innerText` does not.** A "hidden" column still shows up in
  `textContent`, which makes a hidden column look broken when it is fine - and makes a hidden button
  look present. Assert visibility on `style.display` or `innerText`, never on the row's text.
- **A control's mode token is `datetime`, not `date-time`.** The wrong token is accepted silently and
  behaves as a date. Even in `datetime` mode the FIELD still renders the date alone - the time
  picker is added to the popup but never shown in the value - so a time chosen there cannot be read
  back off the page. Where the time must be recoverable, give it its own `time`-mode control.
- **A `time`-mode control wants a whole moment**, not `"09:30"`: feed it `2000-01-01T09:30:00` or it
  displays `NaN:NaN`.
- **A framework re-render keeps classes you add and discards attributes you add.** A message element
  appended to a field's wrapper disappears on the next render; a class survives. If a message has to
  persist, drive it from CSS on a class rather than from injected nodes.
- **`classList.toggle(name, undefined)` is a plain toggle, not toggle-to-false.** A flag read from an
  uninitialised property is `undefined`, not `false`, so a state check written as
  `toggle(cls, a || b)` flips the class on every pass and marks everything. Coerce with `!!`.
- **The framework focuses and blurs its own controls while rendering.** Treating that as interaction
  marks every required field as "you left this empty" before the visitor has done anything;
  `event.isTrusted` is what separates a person from a render.
- **Browser automation cannot always press a row's buttons even where a person can.** The row's own
  container is the top element at the button's centre, so the actionability check refuses the click,
  and forcing it lands on the container. Driving `mousedown`/`mouseup`/`click` on the element is the
  faithful substitute - and dispatch `mousedown` too, since click alone skips any handler that
  records what was pressed.

#### Addendum: scope a table-cell rule to the cell row, not to `td`

Collapsing a table's key column has one more trap. Each rendered row is itself wrapped in a `td`, so
a rule written as `<table-scope> td:first-child { width: 0 }` matches that WRAPPER as well as the
first data cell, and every row collapses to zero width. The symptom is a table drawing its header
over an empty body while every row sits in the DOM with the right content - and it looks exactly
like a data or binding fault, which is where the time goes. Scope the rule to the row that holds the
cells (`tr.<cell-row-class> > *:first-child`, plus the header row) so the structural wrapper is left
alone.

The general form of this: when a framework renders rows through wrapper elements of the same tag,
a structural selector aimed at "the first cell" will hit the wrapper too. Confirm what a rule
matched by measuring the row's own box, not the cells' - cells that measure correctly inside a row
of zero width is the signature.

#### Delegate the listener that identifies a row - do not attach one per button

Reading the pressed row from the page needs a listener, and where that listener is attached decides
whether the feature works sometimes or always. Attaching to each button as it appears - from a
periodic sweep, or from a mutation callback - leaves a window in which the button is drawn, looks
ready, and has nothing listening to it. A click there is lost: the handler runs with no row, the
process is sent an empty key, and it affects nothing. Nothing on screen changes and nothing is
reported, so it reads as "sometimes the button does nothing", which is the hardest kind of fault to
pin down and the easiest to fix.

One delegated listener on the document, in the CAPTURE phase, has no such window: it is in place
before the table is drawn and covers every row that will ever be drawn, including rows added by a
later refetch. (A delegated `mousedown` does fire on these controls, unlike a delegated `input`,
which the framework consumes before it reaches the document.) Use `event.target.closest(...)` to
find the button and its row.

Pair it with a loud failure. When the handler cannot name its row it should say so rather than send
an empty key and let the process no-op - an action that silently does nothing invites the person to
repeat it, which keeps not working for a reason the page never mentions.

#### One result variable per outcome, and clear it once it is read

Two actions on the same table wrote their results into the same form variable, and the step that
repaints the table read that variable as if it always belonged to a save. Removing a row therefore
reported "It was not saved", followed by the raw result object - about a delete that had just
worked. Give each action its own variable, or let each action speak for itself and clear the
variable once it has, so the next refresh does not re-report an outcome from an action taken
minutes ago.

The related judgement call: a delete that matches NO row is not an error to raise. It means the
record is already gone, which is what was asked for - and it is exactly what a repeated press
produces, which is what people do when the first press appeared to do nothing. Report it as "already
removed" rather than as a failure. `SELECT CASE WHEN @@ROWCOUNT = 1 THEN 1 ELSE 0 END` is a fine
thing for a procedure to return; treating that 0 as an alarm is the mistake.

#### Scope that delegated listener to the ROW, not to the button

`event.target.closest('button')` is the obvious way to tell which control was pressed, and it drops
real presses. A mouse can land on the row's own container rather than on the control drawn inside
it - these tables paint a container over their cells, which is the same thing that makes an
automated click get refused - and then `closest('button')` is null and the press is ignored. Record
the row whenever a press lands anywhere inside it. Recording a row that no action follows costs
nothing, because only a row action ever reads it, whereas losing the press costs the whole feature
intermittently.

Note the shape of this class of bug: every one of these failures is silent and intermittent, and
each has a different cause (listener not attached yet, target not the button, result variable
belonging to another action). The common lesson is that the handler must be able to say "I could not
tell which row this was" - without that, all three look identical from the outside, and identical to
"the button does nothing sometimes".

#### Correction: the row is not reachable with `closest('tr')` from where a mouse actually lands

The previous two notes on this got the mechanism half right and the lookup wrong, which is worth
recording because the wrong version passed every automated test.

Each rendered row is wrapped in a container element that is a direct child of the `tbody` - it sits
OUTSIDE any `tr`. A real mouse lands on that container often enough to matter, and from there
`closest('tr')` walks past the row and returns null, so the press is not recorded and the action
reports that it cannot identify its row. Automation never sees this: dispatching an event on the
button gives a target inside the row, which `closest('tr')` resolves perfectly. That asymmetry is
the whole reason it read as "works sometimes" to the person using it and "always works" to the tests.

The lookup that holds for every press position:

```js
var tr = target.closest('tr.<cell-row-class>');
if (!tr) {
  var holder = target.closest('.<row-container-class>') || target.closest('tr');
  if (holder) { tr = holder.querySelector('tr.<cell-row-class>') || holder; }
}
var cells = tr.querySelectorAll(':scope > td');   // direct children: a wrapper row's descendants
if (!cells.length) { cells = tr.querySelectorAll('td'); }   // would read as its cells
```

Verified against every target a press can reach: the button, a node inside the button, the action
cell, the cell row, the wrapper row, the row container, and another cell - all seven resolve to the
same record. When automating a UI whose framework paints containers over its own controls, dispatch
the button-DOWN on the container and the click on the control: dispatching both on the control tests
a path no person takes.

### The frame a form's global JavaScript runs in is DESTROYED and rebuilt while the form is used

This is the most consequential fact about that code, and it invalidates the obvious way to write it.

The global JavaScript runs in a sandboxed frame. That frame does not live as long as the page: it is
torn down and recreated when the theme is switched, and when a choice re-renders the form. Every
timer, listener and observer the script installed dies with it. The page's own DOM survives
untouched, so whatever the script last wrote stays frozen on screen and nothing reports a problem.

What that looks like from outside is a feature that works, then quietly stops: a submit guard that
never re-enables its button, a row-tagging listener that stops recording presses so every row action
starts saying it cannot tell which row it belongs to. It gets blamed on whatever the person did
last, and it cannot be diagnosed from inside the frame - by the time the frame is gone there is
nothing left to notice. A heartbeat counter written to the page on each pass is what settles it: the
number stops advancing at the exact moment the frame is replaced.

**Use the frame only to INSTALL.** Put the logic in a named function, and from the frame inject it
into the page as a script element of its own, where it runs in the page's realm and outlives every
frame the form rebuilds:

```js
function guard() { window.__guardRunning = true; /* ... uses `document`, which is the page ... */ }

(function install() {
  var page;
  try { page = (window.parent && window.parent.document) ? window.parent : window; }
  catch (e) { page = window; }
  if (page.__guardRunning) { return; }                 // a previous frame already installed it
  try {
    var el = page.document.createElement('script');
    el.textContent = '(' + guard.toString() + ')();';
    (page.document.head || page.document.body).appendChild(el);
  } catch (e) { /* checked below */ }
  if (!page.__guardRunning) { guard(); }               // page refused the script: run here instead
})();
```

Three details matter. `Function.prototype.toString` carries the source across, so the code is written
normally rather than as a string. Inside the injected copy `document` IS the page, so the
`window.parent` juggling disappears. And a page that refuses an inline script does so SILENTLY - no
exception - so verify by checking the flag the guard sets, not by trusting `appendChild`.

Form event handlers (`RUN_JAVASCRIPT`) still run in the frame and still reach the page through
`window.parent.document`; only the long-lived part needs to move.

## Adding a leg to a live flow: four things that each cost an hour

Cloning an existing branch is still the right way to extend a process - the templates, port pairs and
parameter plumbing come with it. These are the parts cloning does NOT get right on its own.

**A For Each is an AREA, and the nodes it repeats are its CHILDREN.** They carry `parentId` = the
loop's id. Cloned from another loop's body, they arrive still naming THAT loop as their parent, so
one loop ends up owning four body nodes and the new one owns none. What the platform reports is
`Action has too many input ports` and `too many output ports` - on the EMPTY loop, which is the one
place the problem is not. Repoint `parentId` on every cloned body node.

**A cloned VARIABLE must keep the source's exact key set.** Hand-building one with plausible fields
(`isReadonly` instead of `isError`/`isRequired`, no `contextId`) is rejected as a bare HTTP 400 with
no field named. Deep-copy the variable it stands in for and change only id, name, type and isList.

**`isValid` is a STORED flag, not a computed one.** A flow can pass both `POST /api/Projects/validate`
and the designer-layer lint and still refuse to launch with "Process needs to be valid in order to be
launched", because the stored flag is what the launcher reads and it is only refreshed by a save that
says so. Set `flow["isValid"] = True` on the PUT once validation passes.

**A body parameter's `<%N%>` slots are numbered across the whole ACTION**, not per parameter, so
adding one means renumbering the ones after it. When the value can be computed upstream, send it as
an existing slot instead: building the whole text in SQL and placing it with one `<%N%>` avoids the
renumbering entirely, and puts the escaping somewhere it can be done once.

### Google Calendar: a deleted event answers 200, not 404

Reconciling an app's bookings against a calendar turns on one fact that is easy to assume wrongly.
Deleting an event through the API does not make it disappear: a later `GET .../events/{id}` returns
**HTTP 200 with the event, and `status: "cancelled"`**. A reconciliation that looks only for a 404
therefore never fires for the case it exists to catch - the organiser deleting the meeting in their
own calendar. Treat `200 + status == 'cancelled'` as gone, and keep 404/410 for an event aged out
entirely. Everything else - a timeout, a 401, a 500 - is the calendar failing to answer, which is not
evidence of anything and must not release a booking.

Two related cautions for a reconciliation that CANCELS things:

- **An empty list is not evidence.** If the check is "which of my events does the calendar still
  hold", an empty answer reads identically whether the window is genuinely empty or the call came
  back filtered, truncated or unauthorised - and acting on it cancels everything at once. Refuse to
  act on an empty list. A missed pass is recoverable on the next run; a wrongly cancelled booking is
  not recoverable at all.
- **A create leg that writes the id back can double-create.** If the sweeper runs again in the window
  between creating the event and storing its id, it creates a second event, and only one id is ever
  stored - so the other is an orphan that nothing will ever delete. Seen once in practice after the
  stored id was cleared by hand. Either make the create idempotent (search by a key the event
  carries) or ensure only one instance of the sweeper can be in flight.

### A non-ASCII character can survive the process and still arrive wrong

An organiser's name holding `â` (U+00E2) arrived in the inbox as `ā` (U+0101). The value was correct
in the database - `UNICODE()` on the character returned 226 - and correct in every process variable.
It is re-read under a different single-byte code page somewhere on the way to the mail client, and
nothing in the flow controls which.

Encode non-ASCII as NUMERIC HTML ENTITIES in the step that builds the HTML, and do it AFTER the
ampersand escape or the entities get escaped themselves:

```js
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  .replace(/[\u0080-\uFFFF]/g, ch => '&#' + ch.charCodeAt(0) + ';');
```

Do NOT encode it in SQL instead: the flow's own escaper turns the `&` of the entity into `&amp;` and
the reader sees `&#226;` as text. Whichever layer escapes markup is the layer that must encode the
characters - one place, one pass, after the escaping.

A tooling note from chasing it: **the SQL runner truncates a response at about 4 KB and emits raw
control characters inside its JSON**, so a long `OBJECT_DEFINITION` cannot be read back in one go.
Parse with `json.loads(..., strict=False)` and fetch the definition as base64 in `SUBSTRING` slices,
then decode locally - the text comes back with its newlines and comments intact, which a
whitespace-collapsing read does not.

### Resolve an address once, and fall back rather than hard-code

Two settings named the same cancel page and nothing kept them agreeing, while the form itself could
be reached three ways: a custom path someone configured, the short code the designer minted, or the
plain form id. One function now answers for every caller and falls back in that order. Worth copying
as a shape: the configured value wins, the platform's own identifier is the safety net, and the id
always works. Anything that builds a link calls the function, so an email, a calendar invitation and
a button cannot spell the same address three ways.

### Creating a Google Meet room takes two things, and one of them is silent

`conferenceData.createRequest` in the event body creates nothing on its own. The request also needs
**`conferenceDataVersion=1` as a query parameter**; without it the body is accepted, the event is
created, and the conference is simply not made - no error, no warning, an event that looks correct
and has nowhere to meet. Both together:

```json
"conferenceData": { "createRequest": {
    "requestId": "<a value unique per request and stable across a retry>",
    "conferenceSolutionKey": { "type": "hangoutsMeet" } } }
```

The room's address comes back as `hangoutLink` on the response.

### A new SQL column does not reach a Node script until the MODEL has it

This cost two rounds in one afternoon. Adding a column to a stored procedure makes it visible to SQL
and to nothing else: the flow parses each row into a declared data model, and a script reading
`row.NewColumn` gets `undefined` while the query plainly returns it. Same for a response object -
`hangoutLink` was in Google's JSON and absent from the parsed event until the model was told.

`procesio datatype-add-attribute --id <model> --name <column> --data-type string` fixes both. The
symptom is always the same and always misleading: the data is right everywhere you look, and empty
where it is used.

### Two smaller ones

**Order of the sweepers is part of the contract.** The confirmation email is the only place a client
is given a link to join, and it was being sent before the sweeper had created the room - so it went
out without one, and nothing ever sends a corrected copy. The client's confirmation now waits for
the room, bounded by a few minutes so a calendar outage delays the email rather than losing it.

**The Send Email action rejects plus-addressed recipients** (`name+tag@domain`) as "Invalid emails",
though they are valid and route normally. Worth knowing before using one as a test address.

## `datatype-add-attribute` on a store-backing model: reported destructive, NOT reproduced (B-048 cluster 4a)

B-048 reported that `POST /api/DataTypes/attribute/{modelId}` on the data model a **data
store** is built on returns 200 for both POSTs and then breaks the store (columns read
`[]`, rows unreadable). **Re-tested live 2026-09 on a real store and it did NOT reproduce.**
The setup: create a data model, `POST /api/DataStore/from-data-model` (which gives the store
its OWN COPY model, a distinct id from the source), populate it, then add an attribute to
the store's copy model with `--force`. Result: the add landed and the store SURVIVED intact
- 6 columns, 2 rows still readable. Adding to the SOURCE model likewise left the store
untouched. So on the current platform, for a from-data-model store, the destruction is not
reproducible. It may still bite a store made a different way (or the platform fixed it since
the original measurement); treat it as a caution, not a certainty.

**Tool guard (shipped, non-blocking).** `datatype-add-attribute` detects when the target
model backs a store - it reads `GET /api/DataStore`, then each store's
`GET /api/DataStore/{id}/data-model`, and matches that model id against the target (this is
the store's OWN copy model, confirmed live). On a match it attaches a WARNING advising a
re-read of the store afterward, but it does NOT refuse (the destruction did not reproduce,
so blocking a working add would be wrong). Fail-open on any read error; `--force` suppresses
the warning.

**Related cluster-4 platform defects, and where each is handled in the tool:**
- **4b — `PATCH /api/Projects/{id}/toggle-activation` reports success either way** and does
  not report the real outcome (`GET …/{id}.status` is not the activation flag either). The
  tool's `process-toggle-activation` now re-reads the `active` field from the list-processes
  projection after the PATCH and reports THAT, warning when it cannot confirm. See the
  toggle-activation sections above.
- **4c — a `PUT /api/Projects` that fails validation can answer 400 and still persist** the
  invalid definition (and stamp a stored `isValid:false` the launcher gates on). Discipline:
  never trust a write's echo — re-read and reconcile. `put-projects` warns on an empty-body
  success (see the empty-body PUT note); after any process PUT, re-read and verify.
- **4d — sub-workspace create/delete is lossy** (`POST /api/Workspace` can answer 500 and
  still create; a "removed" delete still counts against the cap). No clean tool guard; the
  workspace list is `--include-removed`-aware so soft-deleted rows are visible. Do not quote
  a numeric workspace cap — the documented `soft/hardLimit` is a time/thread budget.

### Adding an input to a SQL action: two ways it silently arrives NULL

Extending an existing SQL node (a new `@pN` on the stored procedure, fed by a new process
variable) fails quietly in two places. Both look identical from outside: the process runs,
reports success, the statement executes — and the parameter is NULL. Nothing is logged, and
the procedure's own validation sees only a missing value.

**1. `<%N%>` slots are numbered across the WHOLE action, not per parameter.** The mapping
array is not the only parameter that carries placeholders: the action's other parameters
(the ones holding the connection and the command) reference variables through the same
counter. A row added with the next free id *inside the mapping list* can therefore collide
with a slot another parameter already owns, and the engine resolves it to that parameter's
variable. Before adding a row, collect every `<%(\d+)%>` across `action["parameters"]` and
take a number no one uses:

```python
used = {int(n) for n in re.findall(r"<%(\d+)%>", json.dumps(action["parameters"]))}
slot = max(used) + 1          # row["id"], row["source"]["value"], and variable[0]["id"]
```
The destination (`p5`, `p6`) is the SQL parameter name and is independent of the slot — they
do not have to match, and forcing them to match is what causes the collision.

**2. A mapping row copied from a neighbour keeps its `attribute`.** Rows that read a field
of an object variable carry `"attribute": {"attributeId": …}`. Deep-copied as a template for
a plain string/number variable, that attribute is preserved, and asking for an attribute of a
value that has none yields nothing. Set `variable[0]["attribute"] = None` for a scalar.

Symptom in both cases: the procedure's `ISNULL(@New, existing)` keeps the old value, so a save
appears to work and changes nothing. Worth a one-off probe when a new input misbehaves — have
the procedure write what it received into a settings row, run the process directly with a known
value (bypassing the form), and read it back. That separates "the form did not send it" from
"the process did not deliver it" in one step, which guessing at either end cannot.

### A control added to a table row through the API is invisible to a save

`form-add-element` can place a control inside a dynamic table row, and it renders and works on
screen — but it is not part of the row's own field model, so a RUN_PROCESS map pointing at its
path (whether the four-segment own path or the five-segment row path) sends nothing. The fix
is a field at tab level that carries the value: an `onInput` handler on the row control writes
it there, and the save reads the carrier. Handlers on such a control DO fire; the row model
only limits what a *map* can address.

When that handler recovers the value from the DOM rather than the field model, filter the
candidates by rendered size (`getBoundingClientRect()`), because the create panel usually holds
a control with the same label. Reading the first match writes the create panel's default over
the user's choice on every save, and the symptom — the value reverting to a constant — looks
exactly like a save that never received anything.

### A radio list draws each option's record id as the input's `name`

A select/radio control fed from a list of `{name, value}` renders the option's VALUE as the `name`
attribute of the radio input, not as its `value` (every radio in the group reads `value="on"`).
That attribute is the only place an option's identity reaches the page, so page-side code that has
to act per record - a share link, a per-row control, anything keyed to the underlying id - reads it
there rather than trying to match on the visible text, which is a label and changes.

Painting per-option decoration from page-side code works the same way as everything else here: a
re-render keeps classes and strips appended nodes, so a node that has to persist is re-added by the
sweep and its press handled by ONE delegated listener. A handler bound to the button at creation
belongs to the node that got stripped, and the redrawn button then looks identical and does nothing.

### `navigator.clipboard.writeText` refuses by REJECTING, not by throwing

It needs a secure page and a real user gesture, and when either is missing it returns a promise that
rejects - a `try/catch` around the call sees nothing. Code that ignores the promise reports success
while the clipboard is untouched. Await it (or attach both callbacks), fall back to a hidden
textarea plus `document.execCommand('copy')`, and report only what actually succeeded. A synthetic
click dispatched from a script is not a user gesture, so an automated test must drive a real press
to exercise the working path.
