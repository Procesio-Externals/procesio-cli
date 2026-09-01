# PROCESIO resource model — the `.procesio` export DTO (reference)

What a `.procesio` export bundle actually contains, field by field, across every
resource type. Derived from analysis of live production `.procesio` exports
(`docs_info/Exports/`). This is **additive reference** for the tool and agent: it
documents the shapes the builders read/merge onto. It does not change any builder.
Auth/export mechanics stay in [PROCESIO-API-NOTES.md](PROCESIO-API-NOTES.md); casing
rule (live=camelCase, export=PascalCase) applies to everything here.

Top-level keys (every bundle): `DataTypes, Credentials, Webhooks, DocumentTemplates,
Flows, Forms, DataStores, TimeStamp`. `Webhooks` and `DataStores` are present but
**empty at top level** — webhooks live inside `Flows[].Webhooks`; a `DataStore` is a
real resource type but is its own thing, not embedded here.

---

## 1. The canvas / flow graph (load-bearing for any layout work)

A flow's diagram is a **nested directed graph**. Nodes = `Flows[].Actions[]`; edges =
each action's `Ports[]`. There is no separate node/edge table — geometry and topology
live on the actions.

### Node geometry — `Action.CustomData`
```
CustomData = {
  type: "square" | "diamond" | "circle" | "area",
  name, description, icon,
  position: { x, y },                 // canvas coords, top-left of the node
  areaSize: { width, height, x, y },  // 48x48 for normal nodes; real WxH for "area"
  inputPorts: int, outputPorts: int,  // port counts (drive validation 390/391)
  configuration: [ { id, label, settings:[...] } ],  // designer mirror of Parameters
  wasDropped: bool
}
```
- **`type` is dictated by the action, not chosen at placement.** Each action template
  carries its shape: `square` = standard action, `diamond` = a branching action
  (Decisional), `circle` = a terminal (Start/Stop), `area` = a container frame. A
  builder or layout tool **inherits this from the action config and must never change
  the shape** when it places or moves a node — only the `position` (and an area's
  `areaSize`) is the tool's to set.
- Terminals: **Start** = `in0/out1` (the single source); **Stop** = `in1/out0`. A flow
  has one Start and may have several Stops. Normal nodes are 48x48.

### Edges — `Action.Ports[]`
```
Port = { Id, FlowId, SourceId, DestinationId, Type, State, Data:{}, Errors:{}, Config:{} }
```
- `SourceId` / `DestinationId` are **action Ids** (not port ids). A port stored on an
  action represents an edge leaving/entering the flow graph; iterate every action's
  `Ports[]` to get the full edge set.
- **`Type`**: `0` = normal flow edge, `1` = **error-port** edge. The error port is how
  "on failure go here" is wired (best-practices §5 global try/catch).
- A **Decisional** (diamond) fans out **any number of normal (Type 0) edges**, one per
  case — there is no branch limit. Branches do **not** have to re-converge: a branch can
  run to a `Stop`, or several branches can merge at one or more `Join` actions at
  different points. A `Join` is the explicit merge point when paths should reunite.

### Containment / nesting — `Action.ParentId` + `area` nodes
An `area` node is a **frame that contains other actions**; the contained actions carry a
`ParentId` pointing at that area, and are drawn inside its `areaSize` rectangle.
- The container in active use is the **`For Each` loop body**: a `For Each` action
  renders as an area frame (`CustomData.name == "For Each"`, icon `loop`) and the actions
  it iterates over are parented to it.
- **A `For Each` cannot contain another `For Each`.** To nest a loop, put a
  `Call Subprocess` (or `Trigger Subprocess`) inside the `For Each` and place the inner
  `For Each` in that subprocess.
- The Process Designer currently supports **only the `For Each` area** as a container —
  it does not yet work with other/free-form areas. Treat `area` containment as For-Each
  containment for now.

So layout is **hierarchical**: lay out a container's children within the container's
box, size the box to fit, then place the box at the parent level. `areaSize` on an
area node is the frame rectangle.

### Viewport — `Flow.CanvasData`
`{x, y, zoom}` (e.g. `{0,0,1}`) — the pan/zoom of the designer viewport. **Not** node
positions. A re-layout tool rewrites each `Action.CustomData.position` and may reset
`CanvasData` to `{0,0,1}`; it never needs anything else for geometry.

### Cross-process edges (the Resource Map graph)
A process calls another via a **`Call Subprocess`** (synchronous) or
**`Trigger Subprocess`** (async) action. The target flow id is the action's config
setting `type:"flow-list"` `value` (a flow GUID). Input mapping is a
`type:"process-inputs"` setting holding `[{ id, subprocess:<subVarId>, process:<parentVarId> }]`.
Build the process→process dependency graph by scanning these settings — that is the
input to the Resource-Map (LVL-1/LVL0/LVL+n) layout.

---

## 2. Action catalog — common actions by family

`Action.Category` is `"cat1"` (a UI bucket, not a useful classifier). The actions a
builder reaches for most, grouped by what they do (the full per-action config schema is
the golden `docs_info/Procesio Platform Actions.json`):

- **Control / flow:** `Start`, `Stop`, `Decisional` (branch), `Join` (merge),
  `For Each` (loop), `Delay`, `Throw` (raise a controlled error into the error port).
- **Subprocess:** `Call Subprocess` (run another process synchronously, map vars),
  `Trigger Subprocess` (async fire-and-forget).
- **Scripting:** `Node` (NodeJS — raw output; needs Timeout>0), `Javascript` (JS — wraps
  output `{result:v}`), `Python`. (Output-wrapping differences: see PROCESIO-API-NOTES.)
- **Data shaping:** `Map Data`, `Extract Objects`, `Extract List`, `Extract Object`,
  `Extract Text`, `String To JSON`, `Object To String`, `Object To File`, `Get Element`,
  `Has Elements`, `List Keys`, `Length`, `Trim`, `Concatenate`, `Replace`,
  `RegEx Replace`, `Add`.
- **Integration:** `Call API` (REST), `Execute Query` (SQL SELECT; V1/V2 variants),
  `Execute Command` (SQL non-query; V1 variant), `Send Email` (SMTP — see
  PROCESIO-SEND-EMAIL-NOTES).
- **Date/time & id:** `UTC Now`, `Today`, `Format DateTime`, `Update DateTime`,
  `Generate GUID`.
- **Files / Excel:** `Upload File`, `Get File Data`, `Move File v1`, `Create Folder`,
  `Read Range`, `Get Last Used Row`, `Export To XLSX`.
- **Documents:** `Generate Document` (renders a document template — §5).

Icons (for renderers): `icon-stop, icon-start, call_split` (decisional), `icon-join,
icon-nodejs, icon-call_api, icon-mssql` (SQL), `icon-json, icon-workflow` (subprocess),
`loop` (For Each), `find_replace, send` (email), `code` (JS), `settings_applications`
(Map Data).

---

## 3. Credentials — `Credentials[]`

```
Credential = { name, tname, type, gid, gtid, gtpid, status,
               properties: [ { id, value }, ... ] }
```
- **`gid`** = the credential **instance** id. **`gtid`/`gtpid`** = the credential
  **template** id (the *type*: SQL Server, SMTP, REST API key, Azure GPT, …).
- `properties[]` = the filled fields, each `{id, value}` where `id` is the template's
  property-definition id. Different credential types have different property sets. A
  property value can itself be a GUID pointing at **another credential** (chained
  credentials — e.g. an LLM credential referencing a key credential).
- `status` (bool) = tested/enabled state. Secrets are excluded when exported with
  `exportSensitiveData:false`.

**How an action uses a credential.** The action's `CustomData.configuration[].settings[]`
contains a setting of `type:"credentials"` with `credentialsTemplateId` = the template
(matches the credential's `gtid`) and `value` = the credential **instance `gid`**. Real
shape — an `Execute Query` action: `{label:"Select Database Server", type:"credentials",
credentialsTemplateId:"<template guid>", value:"<credential instance gid>"}`. So: pick a
credential by template, bind the instance gid into the action setting. Never put the
secret in the process — only the gid reference (best-practices §2 holds).

---

## 4. Webhooks — `Flows[].Webhooks[]` (embedded, not a top-level section)

```
Webhook = { Id, WebhookId, IsObsoleted,
            WebhookVariables: [ { VariableId, VariableType } ],
            FilterRules: { Value:[], Parameters:[] } }
```
A webhook is **attached to a flow** and binds the flow's **process variables** to
incoming request parts via `WebhookVariables` (`VariableType` enumerates where the value
comes from — body/header/query). `FilterRules` gates which requests trigger the run
(empty = accept all). The webhook URL/secret is referenced by `WebhookId` (the standalone
webhook resource), not stored inline. Webhook-launched runs are async (launch returns
empty 200 — playbook §D). The whole body binds to a model-typed variable, not per-field
(PHASE4-E2E 1).

---

## 5. Document templates — `DocumentTemplates[]`

```
DocumentTemplate = { id, name, description,
  body: "<html… escaped, may embed base64 images>",
  placeholderDelimiterStart: "<%", placeholderDelimiterStop: "%>",
  documentPageSize: "A4", documentPageOrientation: 0,
  variables: [ { id, dataType, type, name, defaultValue, isList, isInput, isOutput } ] }
```
A document is an **HTML body with `<% %>` placeholders** bound to **typed `variables`**.
`isList:true` variables drive **repeating tables**; `dataType` is the data-model id, so a
placeholder can be a typed scalar or a typed list. Page size + orientation are
configurable. This is what the `Generate Document` action renders: it has a file output
(**Document Output**) AND an **HTML string** output (direction OUTPUT) — see
PROCESIO-API-NOTES "Generate Document HTML string". Bind doc variables by **name** in
docMap (builder resolves name→id), and build the backing data model via the
attribute-endpoint create flow so it COMPILES (else placeholders render "Unknown").

---

## 6. Forms — `Forms[]` (the forms-designer model)

```
Form (outer) = { Id, Name, IsPrivate, Type, Status, State, Assignees:[], Data,
                 CustomUrl, WorkspaceName, workspaceId, created*/updated* }
```
- **`Type`**: `1` = standard form; `0` = the other variant. **`Status`**: `1` =
  active/published, `0` = draft (per API notes). **`Assignees`** non-empty = a **task /
  approval form** routed to specific users.
- A single `.procesio` export can be just one form or a form alongside its flows.

### `Form.Data` (stringified JSON in the export; object once parsed)
```
Data = { browserTitle, elements:[…], valueMap:{}, code:"<encrypted>", images:{},
         hideBranding, messages:[…], dataModel:{…}, variables:[…], events:[…],
         theme:[…], dataModelAttributeFormatVersion, notification, chainConfig:{…} }
```

**Controls — `Data.elements[]`** (flat list, nested via `parentId`). Each element =
`{ id, category, type, configs:[…], parentId, section, hidden }`. The control catalog
seen in production, by family:

- Layout: `section`, `columns`/`column`, `tabs`/`tab`, `divider`, `side-panel`.
- Display: `paragraph`, `heading`, `image`, `icon`, `file-viewer`, `chart`.
- Input: `input`, `textarea`, `number-input`, `datetime-input`, `select`, `dropdown`,
  `checkbox`, `radiobox`, `file-upload`.
- Data: `table` with `dynamic-table-row` / `static-table-row`, `list`.
- Action: `button`, **`approval`**.

Containment uses `parentId` exactly like the canvas (section/column/tab hold children).

**Per-control config — `configs[]`.** Each entry =
`{ id, key, label, type, value, category, subCategory, exposed, events? }`. The control's
behavior is spread across these settings. Common keys: `name, id, visible, label,
tooltip, style, info-text, readonly, value, required, defaultValue, placeholder, regex,
disabled, sourceType, sourceValue, submit, disabledIfFormIsInvalid, multiple, searchable,
clearable, rows`, table keys (`hasHeader, hasIndexColumn, tableColumnsSourceType/Value,
canAdd, canRemove, hasPagination, countPerPage, totalItemsCount`), and the **event keys**
below.

**Data-source binding — `sourceType` / `sourceValue`** (for select/table/list options):
`JSON` (a static JSON array literal in `sourceValue`), `static-list`, `URL` (fetch options
from a URL), or `None`. Process-driven option data arrives instead by a RUN_PROCESS event
writing into the field (below).

**Validation / conditional**: `required`, `regex` (e.g. email pattern), `readonly`,
`disabledIfFormIsInvalid` (enable only when all required are valid — the AAT_ "email me"
pattern in best-practices), and **`visibility`** rules like
`{type:"task-assignees", users:null}` (show a field only to the task's assignees — part
of the approval mechanism).

### Events — three layers
1. **Form lifecycle — `Data.events[]`**: `FORM_LOAD` and `FORM_SUBMIT`. Fire on render /
   on submit.
2. **Per-control runtime events** live in config keys: `onClickEvents`, `onInputEvents`,
   `onFocusEvents`, `onBlurEvents`, `onTableRowAddedEvents`, `onTableRowDeletedEvents`,
   `onPaginationChangedEvents`. Each holds a list of event objects:
   ```
   { id, type: "CLICK"|"INPUT"|"TABLE_PAGINATED"|"TABLE_ROW_ADDED"|…,   // trigger
     action: "RUN_PROCESS" | "RUN_JAVASCRIPT",                          // what runs
     config: {…} }
   ```
3. **Designer-time events** (e.g. `"EMIT_ELEMENTS_UPDATE"` on a `name` config) — editor
   plumbing, not runtime behavior.

**`action:"RUN_PROCESS"` config** (how a form calls a process — extends the memory note):
```
config = { syncRun: bool, processId: "<flow guid>",
           inputMap:  [ { id, left:"<PROCESS var GUID>", right:"<form value-path>" } ],
           outputMap: [ { id, left:"<form field path>", right:"<process out var path>" } ] }
```
- **`syncRun`** chooses synchronous (wait, fill outputs) vs async fire-and-forget.
- The **process variable GUID is on the LEFT** in BOTH maps; the form value-path on the
  RIGHT (4-part `elementId.dataModelId.attrId.valueConfigId`). A name or form-path on
  the left = the designer can't render it and the launch 400s. The builder resolves this
  (prepare_ctx); guarded by `test_form_parity.py`.
- Triggers that can drive RUN_PROCESS: `CLICK` (button), `INPUT` (live field change),
  `TABLE_PAGINATED` (server-side paging), `TABLE_ROW_ADDED`, etc.

**`action:"RUN_JAVASCRIPT"` config**: `{ code:"<js>" }`. Runs in the form's
`iframe.trigger-sandbox`; reach the page via `window.parent.document` (e.g. toggling a
custom loader's `display`). The custom CSS/JS authored in the designer lives in
**`Data.code`, AES-encrypted** (the value starts with `U2FsdGVkX1…` = OpenSSL/CryptoJS
`Salted__` — key in Credential Manager; see `dto/form/FORM-STYLING-NOTES.md`). Inline
event `code` (above) is stored in clear inside the event config.

### Styling — `Data.theme[]`
A list of **CSS-variable sections**: each `{label, properties:[{label, value, cssVariable,
type}]}`. E.g. section "Colors" → `--c-primary`, `--c-primary-variant`, `--c-on-primary`,
`--c-error`, `--c-on-error`, … `type:"css-color-preview"`. The sections cover the theme
(Colors, Typography, etc.). So form styling = setting CSS-variable values per section;
custom overrides go in `Data.code`. Never force a font on `#app *` (breaks Material-Icons
glyphs).

### Approval — the `approval` control + task routing
The `approval` control's `configs` carry the approval model:
- **`approver`** (`type:"user-select"`, value = a user GUID) — the designated approver.
- **`approverReplacement`** (`type:"approver-replacement"`, value = list of user GUIDs)
  — fallback approvers.
- Captured outcome: **`response`**, **`comment`**, **`responseDate`**, **`responseUser`**,
  **`approved`** (hidden, filled at runtime).
- Multi-step: a table-level **`approvalSteps`** key sequences several approvals.
- Task routing at form level: outer `Assignees` + `Type`, plus per-field
  `assignee`/`assigneeReplacement` configs and the `visibility:{type:"task-assignees"}`
  rule. So an approval flow = assign the form/step to users, show the right fields to
  assignees, capture approve/reject + comment, and branch the downstream process on the
  result.

### Multi-form "apps" — `Data.chainConfig`
`{columns:[…]}` describes a **dashboard of linked forms/tiles** arranged in columns — the
"App" concept (e.g. an Overview / Production-Dashboard / Marketplace landing page). This
is how several forms are composed into one navigable application.

---

## What is genuinely new here (vs prior notes)

Prior notes already cover: export/import mechanics, casing, validation oracles,
scripting-action output wrapping, Send Email, scheduler, Generate Document HTML string,
RUN_PROCESS map orientation, form CSS/JS encryption. **New in this file:** the canvas
geometry/edge/containment model (positions, action-dictated node shape, `area` =
For-Each container, `ParentId`, `Type` 0/1 edges, unlimited decisional fan-out), the
action catalog by family, the credential template-vs-instance model + action binding, the
webhook embed shape, the document-template DTO, the forms control catalog + config-key
inventory, the three-layer event model with the RUN_PROCESS/RUN_JAVASCRIPT config shapes,
`sourceType` data binding, the theme CSS-variable structure, the approval-control model,
and `chainConfig` apps. None of this changes a builder; it documents what the builders
read.

---
## These capabilities are CURATED ACTIONS — do not reimplement
Everything described above is reachable through a runnable action (run `python scripts/run-tool.py procesio`
to list all ~330). In particular:
- Parse a flow/export into a node/edge graph → **`read-flow-graph`**; structural summary/smells → **`inspect-flow`**.
- Auto-layout a canvas (legacy or `LAYOUT_ENGINE=elk`) → **`layout-flow`**; verify positions → **`verify-layout`**;
  cross-process map → **`layout-resource-map`**; re-lay-out a LIVE process in place → **`relayout-process`**.
- Duplicate a process → **`duplicate-process`**; validate one → **`process-validate`**; delete → **`process-delete`**.
Reach for the action first; only drop to a raw `<method>-<path>` wrapper or `request` if no curated action fits.

---

## Editing a flow via API: runtime is `parameters[].value`, NOT the setting (CRITICAL)

`PUT /api/Projects` persists what you send but does NOT recompile
`action.parameters[]` from `action.customData.configuration[].settings[]`. The
**runtime executes `parameters[].value`**; the setting is only the designer/UI copy.
Edit one without the other and the canvas shows new logic while the flow runs the old
one (validation passes regardless). Linkage: `parameters[i].tabPropertyId == settings[j].id`.

- Code nodes (`code-editor`): setting.value == param.value (same raw-JS form) → copy
  setting→param for the matching tabPropertyId.
- SQL nodes (`Execute Query`/`Command`): SQL is a nested `side-pannel` → `Query`
  sub-setting. **Setting uses GUID var refs `N'<guid>'`; param uses positional `<%N%>`.**
  Different syntaxes — edit the param's positional SQL directly; never copy setting→param.
- datatype/credentials/variable-binding params legitimately hold `<%N%>` while the setting
  holds a 36-char GUID — never sync those.

Helper `work/networky/migrations/flowpatch.py`: `setscript` now updates the linked param;
`syncparams` bulk-syncs code-editor params. (Discovered 2026-07 during the Networky
overhaul: a swapped router prompt kept emitting the old canned refusal because the old
code was still in `parameters[].value`.)

---

## Hand-building a multi-node flow: node-shape recipes (from the Send Contact Card build, 2026-07)

Building a new subprocess by **duplicate + surgically transform the DTO in Python** is the
safest path (every id/port/param stays internally consistent). Duplicating keeps the source's
variable + action ids — fine, they're only referenced within the one flow. Recipes proven live:

- **Graph = `ports[]`.** Each `action.ports[i]` = `{sourceId, destinationId, type:0, state:1,
  data:{}}`. A `Start` node also has an *entry* port `{sourceId:"0000…", destinationId:StartId}` —
  keep it. A **Decisional** emits one port per case + one default port
  (`data:{"isDefault":"default"}`). A **`Stop` takes exactly ONE input port** — if two branches
  both end, you need **two Stop nodes** (validate error 383 "Action has too many input ports").

- **Decisional operators:** only `EQUALS / IS_EMPTY / IS_NOT_EMPTY / IS_TRUE / IS_FALSE` are
  reliable in this workspace. Numeric `LESS_THAN` / `GREATER_THAN_OR_EQUAL` **throw at validate**
  ("Decisional action: … Exception was thrown"). For an HTTP-status gate use `Status EQUALS "200"`
  (WhatsApp/most Cloud APIs return 200 on success) as the success case, default → error branch.
  Dual form: `parameters[].value` = `[{id, actionid, condition:[{operator, logicOperator,
  leftOperator:{value:"<%0%>", variable:[…]}, rightOperator:{value:"200", variable:[]}}]}]` and
  a separate default param `{value: <targetActionId>}`; `customData…decisional-case` mirrors it
  with GUID refs in `leftOperator.value` (+ a `decisional-default` setting). Template
  `f5dcbb04-253d-4061-99a1-9b2822c2e6d2`, case tabProperty `11d4044a-…f30`, default `…f45`.

- **Execute Query node** (template `a9f851c2-e0ba-4fee-9a06-5445ba000001`): credential setting
  `…bc000011` (DB credential, e.g. `45a1dd18` "Database"), a `side-pannel` `…bc000012` holding
  `Query` (code-editor, `…bc000014`), `Timeout` (`…bc000015`), `Output` (type "any", isList true,
  direction 3, `…bc000013`). SQL setting uses `N'<guid>'` var refs; **param uses `N'<%N%>'`** with
  a `variable[]` map — different syntaxes, never copy setting→param for SQL.

- **Node (NodeJS)** setting ids are per-instance: Code `code-editor`, Timeout, Single Result
  (`datatype`, dir 3), List Result (`datatype`, isList, dir 3), Error (`datatype`, dir 3). Output
  goes to whichever var the Single Result value points at (its own type governs; the setting's
  `dataTypeId` is decorative). Injection convention: an **object/list** var → bare `let x = <%0%>;`
  (NOT in backticks — backticks corrupt JSON); a **string** var → `` `<%1%>` `` in backticks.

- **Call Subprocess** (template `c37e56fe-d924-4604-a86f-7c93f863fcdf`): `Select Subprocess`
  (`bc93d0be-…`) = child flow id; inputs (`process-inputs`, `62cdd318-…`) = list of
  `{subprocess:<child input var id>, process:<parent var id>}` — child var on the LEFT.
  - **The target subprocess MUST be `active:true`** or the parent's `validate` returns
    504 "Called suprocess is not valid… Target flow is inactive". A working callable
    subprocess is `active:true, status:0` (draft-status is fine; *inactive* is not).
    `process-toggle-activation` (PATCH …/toggle-activation) only arms/disarms triggers —
    it does **NOT** flip `active`. To publish for call, set `active:true` on the flow DTO
    and PUT it (`flowpatch put`), then re-fetch to confirm. (Networky Send Contact Card
    wire-up, 2026-07.)

- **Call API whole-body injection:** the RAW body value can be a **single `<%0%>`** bound to a
  **string/Text-typed** var whose content is the full JSON (proven by `Chat Flow/Call LLM Fast`:
  RAW body `<%0%>` bound to a Text `Payload`). So a Node can `JSON.stringify(body)` → a Text var →
  Call API posts it verbatim. If a live run ever shows double-encoding, switch the var to Object
  and `return body` (object) from the Node instead.

- **Variable PUT schema:** `{id, contextId:null, dataType, type, name, defaultValue:null, isList,
  isError:false, isRequired}`. `type` 10=input, 20=output/local, 40=ProcessInfo. Common dataTypes:
  `…121214` string, `…121211` number, `…121210` bool, `…121220` text/JSON-string, `…121221`
  object, `…121222` uniqueidentifier.

Networky flow ids: `Send Contact Card` = `cd3d9bad-45e9-4f05-99f3-fcb86936c0e8` (native
WhatsApp `type:"contacts"` card; inputs SessionId+UserPhone). Report:
`work/networky/migrations/reports/vcard-subprocess.md`.

---

## Node/Call-API/generic-passthrough gotchas (from the Networky DB-wire build, 2026-07)

Five non-obvious PROCESIO behaviors that each silently broke a live flow. All cross-cutting.

- **`<%N%>` substitutes inside COMMENTS too.** PROCESIO does a blind textual replace of every
  `<%N%>` in a Node's code, including `// comment` lines. If the injected value is a JSON
  list/object, the `:` / quotes inside break the surrounding line and the Node dies with
  "Unexpected token ':'" (returns null). **Never put `<%N%>` in a Node comment.** (The Node body is
  syntactically valid on its own `node --check`, so this only reproduces live — check by
  substituting a REAL value, not a stub.)

- **Execute Query always returns a LIST of row-objects**, and **bare-injecting a list whose column
  value is a JSON STRING corrupts the JS** (PROCESIO unescapes the inner `\"` -> invalid literal).
  Fix: return **scalar columns** (`JSON_VALUE(cd,'$.a.b') AS x`) so the injected list has no nested
  quotes, OR strip the JSON into a scalar string bound in backticks. A list of simple scalar
  columns bare-injects cleanly.

- **The "generic" datatype `8daff4fc-206c-4151-9bad-1cfdec59bfbd` is NOT free-form — it is a fixed
  10-column model** (the LLMFastData schema). Any extra column a proc SELECTs (e.g. an appended
  `currentSessionId`, or your own scalar columns) is **silently DROPPED** when coerced into a var of
  that type. For a truly column-preserving passthrough use the **object datatype `…121221`** (as a
  list). This dropping can happen at MULTIPLE hops — fix the var type at every hop (subprocess output
  var AND the parent var it maps into).

- **Whole-body RAW `<%0%>` for a dynamic JSON body works only with an OBJECT var + Node `return
  body` (object)** and the Node's **Single Result dataTypeId set to object `…121221`**. A Text var
  holding `JSON.stringify(body)` sends a double-encoded string (WhatsApp: "messaging_product is
  required"); an inline template with an unquoted `"k":<%1%>` fails PROCESIO's pre-substitution
  RAW-JSON validator ("invalid Json format for RAW type value"). Proven working precedent:
  `Chat Flow/Call LLM Fast` (`<%0%>` <- object-return Node).

- **A proc that ends with `SELECT …` (e.g. `SELECT @@ROWCOUNT`) adds a result set.** Calling it via
  `EXEC` inside an Execute Query that already returns one set -> "Expected maximum one table but
  received 2 tables!". For a fire-and-forget pointer/side-effect write, inline the `UPDATE` in the
  SQL (no `SELECT`) instead of `EXEC`-ing the proc.

- **Required subprocess inputs abort the caller.** A `Call Subprocess` whose target has an
  `isRequired=true` input var will abort the WHOLE parent with "Missing required input for
  variables: <type>" if that input resolves to null/missing at runtime — silently killing everything
  downstream. (This is how the DB-wave `Escape Quotes - search_id` node broke all new-contact
  persistence: a fresh extraction has no search_id.) Guard the value, or don't route an
  optional/empty value through a required-input subprocess.

- **A proc-parameter value cannot be a T-SQL expression.** `EXEC sp_X @p = CASE WHEN … END` is a
  syntax error ("Incorrect syntax near the keyword 'CASE'"). Compute into a local first:
  `DECLARE @v bit = CASE …; EXEC sp_X @p = @v`.

Networky flow ids added this wave: `Resolve And Patch` = `cd337769-d9e0-4f13-9787-b4a219aeb0ec`
(sp_FindContact + patch ResponseLLM target + pending write); `Get Pending` =
`98e3fd5f-a6b9-4da0-87fc-e2d88180818c`. Report:
`work/networky/migrations/reports/dbwire-e2e.md`.

---

## AI Decisional action + Map Data + subprocess-extraction recipes (Networky AI-router refactor, 2026-07)

Building the single-router refactor of `Start` (87→43 nodes) surfaced concrete recipes for three
constructs. All verified via `flowpatch validate` (POST /api/Projects/validate → 200) on a live clone.

### AI Decisional node (template `772aac51-73f5-471d-bf9f-f5099cb30001`, diamond, in1/out-1)
- **Credential is NOT a validation blocker.** A probe with the platform-export credential gid
  `adc0e765-…` (template `27272727-0001-0000-0000-aaaaaaaaaaaa`, a system/global instance) validated
  fine even though no AI credential exists in the target workspace. Validation checks node/port SHAPE,
  not credential ownership. For LIVE RUNS you still need a workspace-owned, tested AI credential of that
  template (create + `credential-test`, then rebind param `…30111` + the customData `credentials`
  setting). The `/api/Credentials/types` + `/list/{typeId}` endpoints 403 with the userpass tool token.
- **Params** (tabPropertyId suffixes off `772aac51-73f5-471d-bf9f-f5099cb3____`): `0111` credential,
  `0112` Model (text), `0113` Endpoint (select 1=Chat Completions/2=Responses), `0114` User Prompt
  (code-editor, `<%N%>`), `0115` Timeout, `0123` LLM Response (datatype dir3 OUTPUT, diagnostic),
  `0116`-`0122` temp/topP/maxtok/presence/freq/seed/store, `0124` Cases (`ai-decisional-case` list),
  `0125` Default (`decisional-default`).
- **Cases** param value = `[{id, actionid:<targetActionId>, condition:"<free text>"}]`; customData mirror
  = `[{id,name,target,condition,internalId}]`. **First true case (declared order) wins.**
- **Ports:** one Type-0 port per case target + one Type-0 default port (`data:{"isDefault":"default"}`)
  + one **Type-1 error port** (`data:{"isDefault":"error"}`). Node carries `variableErrorId` = an
  **IsError var whose datatype MUST be `10c6ac59-3929-49e6-99dc-121212121220`** (validate error 395
  "invalid data type for error variable" if you use plain string `…214`).
- **User Prompt type gotcha:** the User Prompt (`0114`) is a STRING slot — injecting an OBJECT-typed var
  via `<%0%>` fails validate 142 "data type mismatch". Also a `text`-typed var (`…220`) mismatches; it
  wants a **string** var (`…214`). To feed a structured object to the prompt, add a `Node` before it that
  `return JSON.stringify(<%0%>)` into a **string** Single-Result var, and inject THAT.

### Map Data node (template `f183b48e-25b0-4a28-b6ec-310344feaa18`, `icon-variables`)
- ONE side-pannel setting `a5f92824-…` → child `map-process-data` setting `d7ffa148-…`.
- **customData** map value = `[{id, destination:<targetVarId[.attr]>, source:<srcVarId[.attr]>}]`
  (destination = LEFT/assigned var, source = RIGHT/value).
- **Runtime param** `d7ffa148-…` value = `[{id, source:{value:"<%N%>", variable:[{variableId,attribute}]},
  destination:{variableId,attribute}}]`. destination assigned FROM source. Used here as `Map Route A/B`
  to normalize two per-branch router DTOs into one shared `Route` var + a `routeSessionId` guid.

### Extract a duplicated tail into a subprocess (the higher-value merge)
- **POST /api/Projects 403s** with the tool token — you cannot create a process from scratch. Instead:
  **`duplicate-process` any small flow → get a fresh flow id → overwrite its actions/variables with your
  DTO (keep the duplicate's id, propagate it to every action.flowId + port.flowId) → validate → PUT.**
- A **Call Subprocess input/output map** entry (in `parameters[].value`) is
  `{id, source:{value:"<%N%>", variable:[{variableId, attribute}]}, destination:{id, variableId, attribute}}`.
  For an INPUT map: source=PARENT var, destination=CHILD input var. For an OUTPUT map: source=CHILD output
  var, destination=PARENT var. When re-homing onto a new subprocess you must remap BOTH
  `source.variable[].variableId` AND `destination.variableId` when they are parent vars (missing the
  destination side leaves stale refs). customData mirror uses `{subprocess:<child id>, process:<parent
  id[.attr]>}`.
- **A called subprocess needs `active:true` AND `isValid:true`** or the parent validate returns 504
  "Called suprocess is not valid". After building, `flowpatch validate` the subprocess, set `isValid:true`,
  and PUT it BEFORE validating the parent that calls it.

### Networky ids added this wave (AI-router refactor, on a CLONE — not live)
- Refactored clone `Start [AI-Decisional REFACTOR - not live]` = `5dabbaaa-5de0-44cc-ab89-9a307fb90c5e`
  (43 nodes, active:false, isValid). Report: `work/networky/migrations/reports/ai-decisional-refactor.md`.
- New subprocess `Chat Flow/Handle Complex Turn` = `68a0c9d1-f55b-44bc-ba36-748397093f25` (single copy of
  the complex/enrichment/persist tail; input `session_id` guid required + conversation/User/userMsg/route).
- The live `fastLLM` router DTO (`be898da6-5e1a-42a0-a6c4-6ad653e8f7e9`) has exactly 7 fields:
  response_text(17522760) send_message(723db89f) need_LLM_complex(0b778bf1) language(77c01d02)
  new_session(4b0fc63b) target_session_id(926d5723) intent(7f56f2b4). `need_contact_search` is NOT a typed
  field — it lives only in the RAW router JSON text var `fastLLMRaw`, read by the `Check Search` Node.
- The WTB webhook `db92281a-17b5-451f-b9f4-2a7f6a70f1fc` stays bound to LIVE `Start`
  `c6754fc4-…`; a duplicated process carries the same webhookId reference but is inert while `active:false`.


## Creating nodes/actions in a flow via API (WORKS - userpass; verified 2026-07-05)

Adding a NEW node to a flow via `PUT /api/Projects` works with the default userpass `account` profile.
No designer UI needed. The one trap: do NOT copy an existing node to make a new one - a copied node
carries the source flow's stale variable bindings in `customData.configuration`, and the validator then
throws a diagnostic-free `HTTP 500 "Object reference not set to an instance of an object"`. Instead:

1. Fetch the CLEAN action template: `GET /api/Actions?getFullAction=true`, find by `actionId`/`name`.
   `copy.deepcopy(template.configuration)` and fill only your setting values. A clean config makes the
   validator return REAL errors (141/142) instead of the 500.
2. A JS "Node" (templateId e0fc20c3): settings are Code (1e6a5523) = JS + input `<%N%>` bound in the
   Code param's `variable` list; **Single Result** (51b9fcdc) = the JS `return` output (NOT Error
   9e0110c9); List Result (60237e88); Error (9e0110c9) = error port; Timeout (d3e52aab).
3. New variables use key **`dataType`** (a type id) + `type` (10 input / 20 process / 30 output / 40 sys).
   Missing type -> `statusCode 141 "type cannot be empty"`. Param/var type must MATCH the setting's
   expected `dataTypeId` -> else `statusCode 142 data type mismatch`. Primitive ids: `...1211` number,
   `...1214` string, `...1221` any/object; file `10c6ac59-...-121212121219` = FileDataModel
   `{name,mimeType,path,size,id,hash}` (blob reference, NOT inline content).
4. Files from text: a Node cannot return a FileModel (no inline content). Use **`Base64 To File`**
   (actionId 6fad5599; settings Base64 String, File Name -> File output) to turn a base64 string into a
   stored FileModel; then Call API `/media` upload (FORM_DATA `file`=FILE type, `type`=mime).
5. Validate via `POST /api/Projects/validate` (empty body = valid) before PUT.

Best path: `tools/procesio/dto/process/builder.py` already builds correct DTOs data-driven from the live
catalog (`_action_node` = clean template config + values; `_edit` rebuilds a whole flow and PUTs). Prefer
it for full-flow builds; replicate `_action_node`'s recipe for a surgical single-node insert into a
fetched (lowercase-keyed) flow. Worked example: added Build VCF (Node) + Base64 To File to Chat Flow/Send
Export to produce a `.vcf` bulk export (scratchpad build_vcf_flow3.py pattern).


## Field learnings 2026-07-05 (designer review + real-corpus E2E) — AUTHORITATIVE

1. **Decisional icon**: when creating a Decisional via API set `customData.icon = "call_split"` (the
   designer standard). `icon-decisional` or anything else renders NO icon in the run view. Same rule
   class: give decisional CASES meaningful `name`s — the designer shows them as chips on the canvas.
2. **Scripting (Node) actions FAIL SILENTLY**: a JS code error does NOT raise / does NOT take the
   type-1 error port. The action reports SUCCESS and writes the error text to its **Error output**
   setting (9e0110c9). ALWAYS: (a) bind Error output to a string var on every Node; (b) on hot paths,
   follow the Node with a Decisional `errVar IS_NOT_EMPTY -> error join`; (c) compose the user-facing
   error message from the error vars in one downstream Node (values from the FAILED action are unset —
   never map them into the notice directly). Proven: 6 silently-dying turns became 6 successes.
3. **Huge values (base64 media, 100KB+)**: SQL param binding and subprocess input maps carry them fine;
   Node `<%N%>` JS injection and Decisional operands materialize them as EMPTY. For emptiness/length
   checks on big attributes use the native **Length** action (template 057d754a: Input String, Result)
   — NOT an Execute Query (overkill) and NOT JS injection (silently empty).
4. **For Each via API** (template dbef0804-66a9-4f8f-872c-ece1b89b8fdb, shape `area`): params =
   For Each Item (57b5b1eb…, the per-iteration var) + In List (2d5f230f…) + timeout + 2 ignore
   literals. The FE node has TWO type-0 ports: first -> loop-body entry child, second -> the after-loop
   node. Children carry `parentId` = FE id; the LAST child ports BACK to the FE (loop-back edge).
5. **Workspace header is mandatory on run/launch**: `ProcesioClient(workspace_id=…)`. Without it,
   `/api/Webhooks/launch` and `run-process` bind LARGE attribute values as EMPTY (looks like an engine
   bug, is actually your missing header), and admin flows 400/502.
6. **WhatsApp bulk contact export**: document sends get the MIME's extension APPENDED by WhatsApp
   (filename `Contacts.vcf` + text/plain ⇒ phone receives `Contacts.vcf.txt`, unimportable). No allowed
   /media MIME maps to .vcf. Correct approach: native `type:"contacts"` messages (array, chunk ~15 per
   message, For Each over chunks) — renders as a tappable contact stack ("X and N other contacts").


## Layout engine upgrade 2026-07-05 (brief: "fix the tool so it layouts right")

Four engine changes in `tools/procesio/layout/engine.py` (all covered by the existing test suite):
1. **Error-region detection stops AT error targets**: main-flow reach may point INTO an error-port
   target (e.g. a script-gate's normal case edge into the shared error Join) but never THROUGH it.
   Before, one normal edge into the sink pulled the whole notify subtree into the main graph.
2. **ALAP layer pull with branch-head anchoring**: single-successor chains get pulled RIGHT adjacent
   to their join (kills 8-layer join edges), but a branch HEAD (predecessor fans out) keeps its ASAP
   layer so it stays next to its decisional.
3. **Error components anchor independently, laid VERTICALLY**: each weakly-connected component of the
   error region becomes a vertical rail below the canvas, anchored at the median x of ITS OWN feeders.
   Vertical rails cannot cross the horizontal main flow.
4. **MINIMIZE_CROSSINGS defaults ON** (strictly better in every measurement).

FLOW-side pattern that finishes the job: with feeders spread across a wide canvas, a SINGLE shared
error Join forces ~feeder-span-length edges (geometry, not layout). Split into ONE ERROR RAIL PER
CANVAS REGION (Networky v2: rails A/left/right - Join+Compose+notice+Stop each, cloned). Result on
the 78-node v2: crossings 10 -> 0 (proper-intersection; report's endpoint-touch counter: 2),
max edge 3729 -> ~1500, all four Networky flows re-laid clean.
LEGACY engine remains the default (ELK is opt-in backup via LAYOUT_ENGINE=elk).


### Layout round 2 (same day, after the designer re-review)
5. **At most ONE folded dead-end chain per branch node** (`_deadend_chains` cap): several chains
   folding onto the same column stacked into overlapping piles (the AI Router 5-way fan). The
   shortest chain folds; the rest lay out normally. Result incl. label-aware collision check:
   v2 = 0 crossings, 0 label collisions; ALL FOUR flows 0/0 by layout-report.
6. **Designer code sync for authored Nodes**: when creating a Node via API, the customData Code
   setting must hold the GUID-reference form (variableId[.attributeId]), NOT the runtime `<%N%>`
   form — the designer renders `<%N%>` literally and the variable picker breaks. Convert with
   the param's variable map (flowpatch `_config_value_from_param` pattern). Synced on 9 authored
   Nodes across v2/HCT/SendExport/PEC.


### TWO validation layers — runtime vs designer (2026-07-06, corrected)
**A 2026-07-05 note here WRONGLY called the designer's Process Errors "stale phantoms." They were
REAL and blocked designer SAVE. Corrected below — trust the designer's Process Errors.**

- There are TWO validation layers and they disagree:
  - **Runtime layer** — `POST /api/Projects/validate` (the only server validate endpoint; by-id
    variants 403). It checks `parameters[]` (the runtime maps). Returns an EMPTY body when valid.
    It does NOT look at the designer layer, so a flow can pass /validate yet be UNSAVABLE.
  - **Designer layer** — a CLIENT-SIDE check in the Angular designer that populates the "Process
    Errors" panel and BLOCKS SAVE. It reads `customData` (the designer maps + code chips). There is
    NO server endpoint for it — you must replicate it.
- **Replicate the designer layer with `procesio flow-lint --id <flow> --workspace-id <ws>`** (rewritten
  2026-07-06 to check the DESIGNER layer, not the runtime one): Node code binding an error-scope
  (`isError=true`) or undeclared variable; and every REQUIRED subprocess input having a `customData`
  process-inputs row (`subprocess`==input id) whose source resolves (GUID source must be a declared
  var; a non-GUID source is a literal and is fine). Call inputs pid 62cdd318…, Trigger 9823b4d9-7a0c….
- **Root cause we hit twice:** cloning a Call/Trigger-Subprocess node copies its `customData`
  process-inputs verbatim, so the clone keeps the SOURCE node's subprocess-input ids. The real target
  requires DIFFERENT ids → those read as "mapping missing," and the panel shows the stale ids as raw
  GUIDs (they don't resolve in the new target). Fix: regenerate `customData` process-inputs from the
  (correct) runtime map — row `{id, subprocess: <dest varId>, process: <srcVarId>[.<attrId>]}`;
  literals go in `process` verbatim.
- **Runtime map ≠ designer map.** A node's runtime `parameters` map can be correct while its
  `customData` designer map is stale (Networky v2: Resolve And Patch). The designer validates the
  DESIGNER map. Always sync both when authoring/cloning subprocess nodes and Node code.
- Error-scope variables (`isError=true`, usually FileDataModel) are an action's error-PORT output;
  they live in the designer's "Error" tab, never appear in the Process tab, and are never
  free-initialized. NEVER bind one as a Node code INPUT — the designer flags it (tooltip shows type
  "Error"). Networky v2's Compose Error wrongly swept 9 of them in via a `name.startswith("err_")`
  filter; rebuilt to bind only the real String gate-error vars.
- Overhaul-era subprocesses do use VANITY input ids (11111111-0000-4000-…, a1b2c3d4-0000-4000-…) that
  are REAL — but that does not make a mapping to them automatically correct; check that the id belongs
  to THIS node's target, not a sibling's.
- `flowpatch.py validate` USED to print `validated:True` unconditionally without reading the response
  (fixed 2026-07-06 to inspect the body + fail loudly). Any pre-fix "validate: True" was meaningless.

### Designer-layer validation: the concrete rules (2026-07-06, hard-won)
`procesio flow-lint --id <flow>` now checks ALL of these (the designer's client-side "Process Errors"
that block SAVE; POST /Projects/validate does NOT catch them). Root causes found by comparing a
FLAGGED node against a HEALTHY node of the same template against the CLEAN /api/Actions template — that
comparison is the reliable method; reverse-engineering from a single node's data is not.

1. **Stale subprocess side-pannel id (THE big one).** A Call/Trigger Subprocess node's
   "Subprocess Configuration" side-pannel setting has an `id` that MUST equal the CURRENT template's
   side-pannel id: Call = `5456caf0-be8e-4a04-86cb-dbae203af978`, Trigger =
   `8540605e-2f4d-1746-9059-8bb7b944e0d3`. PROCESIO bumped this id across template versions; nodes
   built/cloned against an older template keep the OLD id (seen: `1da555da…`, `15af8b81…`). The
   designer looks the mapping up BY this id — wrong id ⇒ it finds nothing ⇒ reports EVERY required
   input as "Mapping of required subprocess variable (X) is missing." The mapping CONTENT is fine;
   only the wrapper id is stale. Fix: set the side-pannel `id` to the current template's; leave the
   nested process-inputs/outputs untouched. This is safe and mechanical.
2. **Required subprocess input unmapped / dead source.** Every target input (type 10, isRequired)
   needs a process-inputs row `{id, subprocess:<targetInputId>, process:<srcVarId>[.<attrId>]|literal}`;
   a GUID source must resolve to a declared var (a non-GUID is a literal, fine).
3. **Subprocess output must map a type-30 var.** A subprocess only EXPOSES `type==30` variables as
   outputs. Mapping a `type==20` internal var (e.g. an Execute Query `dbout`) as a process-output ⇒
   designer "Check data mapping." To read a value out of a subprocess, that var must be type 30 there.
4. **Execute Query requires a non-null Output.** The Output subsection (label "Output", pid
   `8aa02e91-1a1e-a44a-b09b-6965d67da04d`) must be set to a variable, both as a runtime param and in
   customData. Null ⇒ "make sure the action is defined/configured properly."
5. **Node code must not bind an isError variable** (an action's error-port output; type shown as
   "Error", never free-initialized) nor an undeclared var.

### Designer-layer rule #6 — Execute Query Output must be a list<Object> (2026-07-06)
Another client-side "data type mismatch" the server /validate does NOT catch. An `Execute Query`
returns a SQL result SET, so its **Output** variable must be a `list<Object>`: `isList = true` AND the
element type an Object - the generic `0317bfee-b2f5-4bde-bfe8-121212121221` (any/Object) OR any custom
DataModel (whose GUID does not share the `0317bfee-b2f5-4bde-bfe8-1212…` scalar prefix). A scalar
(e.g. a `number` output `…1211`, isList=false) or a `list<primitive>` (e.g. `list<text>` `…1220`)
trips "Error: data type mismatch" and blocks SAVE. Typed-DM lists (`list<UserDM>`, `list<MessageDM>`)
are fine - a DataModel IS an Object. `procesio flow-lint` now checks this (EXECQUERY_OUTPUT_TYPE).
Fix: set the Output var's dataType to the generic Object (or a DM) and isList=true; the var id on the
Output setting is unchanged. Found live on `Persist search_id` (SalesOMMO, scalar number) and
`sp_MessageAdd` (Add Message, list<text>) - both corrected to list<Object>.

## Shapes (canvas-engine PRC-4391, 2026-08)

Decorative canvas Shapes (rectangle / ellipse / diamond) are NOT flow nodes: no ports, no
config, no execution. They persist as `ICanvasShape[]` under the flow DTO's opaque
**`canvasData.shapes`** blob (live API camelCase `canvasData`; PUT DTO PascalCase
`CanvasData`) — NOT a top-level `Flow.shapes` field. Z-order sits below the connectors.
Designer save/load of shapes is platform Phase 2. **Tool rule: never drop `canvasData` on
a round-trip.** `process-edit` now carries the live `canvasData` into the rebuilt DTO
(build() resets it to None); the layout/relayout engine already leaves `canvasData`
byte-identical. A hand-authored PUT must preserve it or every shape is wiped.

## DataStore form event (2026-08)

`EventAction.RUN_DATA_STORE_OPERATION`; config `EventRunDataStoreOperationConfig
{dataStoreId, operation, inputMap, outputMap, filters?, areFiltersConfigured?}`.
`operation` = DataStoreOperation READ/ADD/UPDATE/DELETE; filters apply to every op except
ADD (`dataStoreOperationSupportsFilters`). Map items are `{id, left, right}`
(DataStoreMapItem). Wired via `form-set-element-event --action RUN_DATA_STORE_OPERATION`
(surgical) or the builder `do: datastore`. Operation wire encoding (string vs numeric) +
map orientation confirmed live post-launch.
