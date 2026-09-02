# Phase 4 — end-to-end use case (AAT_ "Company Intelligence Brief")

A full working demo in workspace **4Export** (`3fd85e9d-121e-415b-877f-f488cd685ce3`)
exercising every DTO sub-tool: 2 data models, 2 credentials, 1 document, 2 processes,
1 webhook, 1 form. All resources prefixed `AAT_`. Built entirely programmatically.

## Resource ids (4Export)

| Resource | id |
|---|---|
| Data model AAT_SearchHit | `f675610e-8ac9-40a3-a909-e963841b72c9` |
| Data model AAT_SearchReport | `cfa383c7-1a36-410b-852e-bcc57c53a614` |
| Credential AAT_GoogleSearch (REST API) | `77b6f02b-d111-4ff4-b67a-264b571b9957` |
| Credential AAT_SendGrid (SMTP) | `7b38b993-9141-4533-995d-44d73d9932fb` |
| Document AAT_CompanyBrief | `503f33b4-8653-497d-8f77-ae52d909cae1` |
| Webhook AAT_BriefRequested | `9b700656-4619-41e1-96ce-4be561fd7bc1` (model `9b3e2e82-b8c0-4a63-be98-4098e3e17d7f`, attr searchTerm `18c90bb9-391d-4853-a843-658afebd27a9`) |
| Process AAT_Process_Notify | `564d2934-ffb2-44a5-8d5e-4e0979b3ccaa` |

## Learnings (verified live 2026-06-24)

1. **Webhook -> process variable binding maps the WHOLE body, not a field.**
   `WebhookVariables` is exactly `{VariableId, VariableType}` where VariableType
   1=header, 2=query, 3=body (confirmed against real exported flows). There is NO
   per-field mapping. The body (type 3) must bind to a **model-typed** process
   variable whose DataType is the webhook's generated data model — then downstream
   actions read its attributes. Binding the body to a *primitive* (string) variable
   dumps the raw JSON (`{ "searchTerm": "..." }`) into it. Real exports confirm the
   body var is model-typed (Type=10 input, DataType = a custom model id).

2. **Builder enhancement — attribute paths inside text templates.** To embed a
   model attribute into a text field (email Subject = "Brief for <%0%> is ready"
   where the value is `payload.searchTerm`), the process builder's `{template,vars}`
   binding now accepts `vars` items as either a name string OR `{"var": name,
   "path": ["attrIdOrName"]}`. `_make_parameter` builds the VariableAttributeDto
   chain; `config.schema.json` `binding.template.vars.items` widened to `anyOf
   [string, {var,path}]`. Without this, model attributes could not be placed into
   text. (attr_index isn't pre-populated for webhook models, so pass the attribute
   **id** in `path`.)

3. **REST API key credential — key as a query param.** For Google Custom Search
   (needs `?key=...&cx=...`): REST API credential, Authentication method = "API key
   authentication", Key=`key`, Value=`<apikey>`, **Header(`10101010-0001-0009`)=false,
   Query Parameters(`10101010-0001-0010`)=true**. `/api/Credentials/test` with Test
   endpoint `?cx=722c82f83dd77489f&q=...` returned a real `customsearch#search`
   body -> placement confirmed. The action then adds `cx`+`q` query params.

4. **SendGrid over SMTP.** Credential type "Outbound e-mail (SMTP)":
   Server=`smtp.sendgrid.net`, Port=`587`, Encryption=`TLS` (587 None/TLS/Auto all
   pass the connection test; 465 timed out), Username=`apikey`, Password=<sendgrid
   api-key>, From=`<verified-sender>@procesio.com` (a SendGrid verified sender). `/test` ->
   `{"isSuccess":true,"body":"Connection was successful"}`. Email delivered live to
   a personal Gmail inbox.

5. **google-mail account selection** is the `GOOGLE_ACCOUNT` env var (values:
   `default` = the work mailbox, `personal`), NOT an `--account` flag.
   Verified the SendGrid email by Cc'ing the readable default inbox.

6. **Process GET shape.** `GET /api/Projects/{id}` wraps everything under a top-level
   `flow` key. Instances: `GET /api/Projects/{id}/instances` (paged); per-instance
   detail endpoints return 401 (not exposed over this surface). Instance `status:50`
   = finished, `actionsConsumed` counts non-Start/Stop actions, `errorMessage` null
   on success. A webhook-launched run is async (launch returns empty 200).

7. **Send Email action** properties: `Select SMTP credentials` (literal credential
   id), `To`/`Cc`/`Bcc`, `From (Entity)` (must be a verified sender), `From (Display
   Name)`, `Subject`, `Body` (code-editor), `Body is Html` (check-box, literal true).

## Process 2 (search -> PDF) — the hard-won scripting/document learnings

Process `AAT_Process_SearchGenerate` (`11bf8d6d-3e7a-4355-a37e-75c9608d8443`):
Call API (Google CSE) -> Javascript (build full branded HTML) -> Generate Document
(shell template, docMap) -> branded PDF with the live search table + hero image.
Verified live: PDF rendered with SUBJECT, 6 real LinkedIn results, the search image.

8. **Javascript output is ALWAYS wrapped `{result: <v>}`.** It maps cleanly only
   into a model whose `result` field is a **primitive** (e.g. `AAT_HtmlEnvelope
   {result: string}` -> `result` = the string). Mapping `{result: v}` into a model
   whose `result` is a nested **model** or **list-of-model** creates the structure
   but leaves inner fields EMPTY — PROCESIO does **not** map a plain JS object's
   keys onto a typed model's attributes. Consequence: **you cannot build a typed
   list/model from a JS action** to feed a document's repeating table. (Confirmed by
   reading the real output variable, not just customResponse, which is lossy for
   nested models.) Bind the output to `AAT_HtmlEnvelope` id `303b0e3b-557f-4667-ac76-fc436999b023`
   (result attr `7950ac90-aded-46f1-ad18-b5f3d2c99357`).

9. **To put dynamic data in a document: build the whole HTML in JS, render via a
   shell template.** `AAT_BriefShell` (`2c172798-0a96-4911-9c2e-16aebf5afabc`) body
   is a single `<%htmlContent%>` placeholder (string var). Generate Document docMap:
   `htmlContent <- {var: htmlEnv, path: [result_guid]}`. The placeholder substitutes
   **raw HTML** (not escaped) -> the PDF renders the full branded layout, table,
   image. This is the robust pattern given the JS->typed-model limitation.

10. **Generate Document REQUIRES `Select Document Template`** (else 502/"Missing
    document information"). The **`HTML string` property is an OUTPUT** (the rendered
    HTML is written there) — not an input; binding a var to it gets it overwritten.

11. **docMap attribute paths must be GUIDs.** Navigating a `json` var by key fails:
    `Error converting value "result" to ... Guid ... attribute.attributeId`. So a
    `json` variable can't be navigated in docMap — must be a typed model with real
    attribute GUIDs.

12. **Compiled-model cache.** An attribute added to a data model via *edit* (after
    creation) is NOT in the runtime's compiled model: Generate Document fails
    "Unable to find attribute <guid> in data type <id>" even though GET shows it.
    **Always create a data model with all attributes up front**; don't rely on
    datatype-edit add for attributes consumed by Generate Document.

13. **Call API for Google CSE.** `Request Parameters` (tabs-payload-v2) =
    `{body:{type:RAW,value:{...}}, headers:[], queryParams:[{key,value,id,type:"TEXT"}]}`.
    cx as a literal, `q` as `<%var%>`, `num` literal. `Verb` GET =
    `3ab385bd-f8ae-b641-9176-e7db886aec01`. `Response Body` -> a **string** var. The
    API key is injected by the credential (API-key-as-query). No Endpoint path needed
    (credential URL already ends `/customsearch/v1`). Use the UNVERSIONED `Call API` action (id cd8bd0bc-...804de) = the LATEST/live one (outputs Response Status/Body/Headers/File); `Call API v1/v2/v3` are frozen pins and there is NO `v4` action ("Call API - v4" is only a palette folder). See [[aat-to-procesio-migration]].

14. **JS JSON injection: inject as a BARE object literal** (`var data = <%0%>;`), NOT
    inside backticks. A backtick template literal un-escapes the JSON's `\n`/`\"`
    sequences and corrupts it (JSON.parse then throws -> 0 results). Bare injection
    treats the CSE JSON as a JS object literal directly.

15. **Reading results.** `run-process --synchronous` returns output vars under
    `result.variable`. Download a generated file: `GET /api/File/download` with
    headers `uploadFilePath` (the file's `path`), `variableId`, `instanceId`,
    `flowTemplateId` (parse variableId/instanceId from the path). Instance status +
    per-action errors: `GET /api/Projects/instances/{iid}/status?flowTemplateId={pid}`
    (`.instance.actions[].errorMessage`). Status 50 = finished, 40 = ran-with-errors.

16. **Builder enhancements made for this (generic, reusable):** template-binding
    `vars` items may be `{var, path}` (attribute paths in text/object templates), and
    a `template` may be a JSON **object/array** (not just a string) — `<%i%>` is
    remapped in all string leaves. `config.schema.json` widened to match. Lets Call
    API `Request Parameters` and attribute-path subjects be expressed declaratively.

## CRITICAL process-builder fix — designer config vs runtime Parameters

**Symptom (reported live):** every action's parameters showed EMPTY in the designer
("Send Email - Not configured", To/Subject/Body blank), `Validate` flagged "action is
not defined/configured properly" — yet the process **ran fine** (email sent, PDF made).
Clicking `Validate` in the designer then cleared the errors.

**Root cause:** a PROCESIO action stores its parameter values in TWO places that must
mirror each other — `Parameters[]` (`{TabPropertyId, Value, Variable}`, what the
RUNTIME reads) AND `CustomData.configuration[].settings[].value` (what the DESIGNER
reads/validates). The builder filled only `Parameters[]` and left the configuration
tree as the empty template defaults → designer blank + invalid, runtime correct.

**Fix (in `_action_node`, applies to every process the tool builds):** deep-copy the
template `configuration` and set each setting's `value` to mirror its Parameter via
`_config_value_from_param` — same value, but a variable reference is the raw
`variableId` (with `.attrId` for attribute paths) in the config where the Parameter
uses a `<%N%>` placeholder (verified against real exports: Call API `Response Body`
config value = the var id; Parameter value = `<%3%>`). Structured/object values are
walked recursively. Confirmed live: settings now carry values, Validate passes,
runtime unchanged.

**Canvas origin fix (also reported):** flow started "way-left". Real flows start at
~x500/y480; `_layout` now uses `_X0,_Y_MAIN,_X_PITCH = 480,480,260` (was 100,300,320).
Verified: Start(480,480) → actions 740/1000/1260 → Stop(1520), all on y=480.

## CRITICAL fixes round 2 — stale variable ids + form data model

Two more designer-vs-runtime issues (reported live):

**A. Process variable ids drift on every edit.** `build()` reassigned a fresh id to
every variable on each create/edit. External references (a form's RUN_PROCESS
inputMap/outputMap bind a process variable by id) therefore went stale after any
process re-edit -> the form's "Process input variable" column showed EMPTY. **Fix:**
process-`_edit` now fetches the existing flow and reuses variable ids by name
(`ctx["existing_var_ids"]`), so ids are stable across edits. (Action ids can still
change - they're internal; only variable ids are referenced externally.) Re-aligned
the form to Process 2's current ids after the fix.

**B. Form fields had no data model -> mapping paths unresolvable.** A PROCESIO form
backs every control with a **data-model attribute**: `Data.dataModel` root "form"
(id = the form id) -> a `fields` container (**id `11223344-5566-7788-99aa-aabbccddeeff`,
a platform constant in every form**) -> one sub-model per element (**id = element id**)
-> an attribute per config, incl. `value`. A RUN_PROCESS/MAP trigger references a
field by the path `formId.fields.elementId.valueAttrId`, and the **runtime stores the
field's value in that attribute**. The form builder only emitted `elements` and used
the shell's empty `fields` container -> the path pointed at nothing -> designer showed
raw guids AND values didn't flow. **Fix:** `_build_data_model` now mirrors every
element into the `fields` container (sub-model id = element id; a typed attribute per
non-event config; `value` typed by control kind incl. file-upload -> FileDataModel),
sets the dataModel root id = form id, and `field_paths` reference the real `value`
attribute id. Verified live: dataModel has 8 field sub-models with value attrs, the
inputMap paths reference existing attributes, root id = form id, and a form-triggered
Process 2 instance ran to status 50.

**Headless caveat (still true):** Playwright `fill`/`press` set the native input but
don't update the Angular-bound form model, so in automation `fields.X.value` stays
empty and the path resolves to itself (a filename came out as the path). A real
keyboard user populates the bound model and the value flows. Verify form value-flow
in a REAL browser.

## CRITICAL fixes round 3 — bespoke config shapes + build audit

`Map Document Data` (and, the user predicted, Decisional conditions) showed EMPTY in
the designer + failed Validate. Cause: a few property types store a **different
shape** in the designer config than in the runtime Parameter, and the round-1 mirror
just copied the runtime shape. Confirmed against real exports:

- **document-mapper** — runtime `{id, source:{value,variable}, destination:{variableId}}`
  but designer `{id, process:<varId|literal>, document:<docVarId>}`.
- **decisional-case** — runtime `{id, actionid, condition:[{operator, leftOperator:{value:"<%N%>",
  variable:[...]}, ...}]}` but designer `{id, name, target, condition:[{id, uid, operator,
  leftOperator:{variable:"", attribute:{id:"",nextAttribute:null}, value:<varId>}, ...}]}`.

**Fix:** `_apply_values_to_config` dispatches by setting `type` — `_docmapper_config`
and `_decisional_cases_config` emit the designer shape; everything else uses the
`<%N%>`->varId mirror. **Plus a build audit (`_audit_config`, requested by the user):**
after building, every Parameter must map to a config setting, bespoke types must carry
their required keys (process/document; target/condition), and a runtime value must not
leave the designer field empty — otherwise the build **raises** (the designer would
flag "not configured"). Verified: Render PDF's Map Document Data config is now
`[{id, process:<htmlEnv.result>, document:<htmlContent>}]`, the audit passes, the flow
still runs to status 50. Regression tests added (config mirror, docMap shape, form
data model).

## Round 4 — document list-table is a dead end (designer "Unknown")

The showcase doc `AAT_CompanyBrief` (typed `hits` list + repeating table) shows the
table cells (`<%hitsId.attrId%>`) as **"Unknown"** chips in the document designer,
even though the attr ids match AAT_SearchHit exactly. There is no documented repeating
syntax, and (decisive) **you cannot populate a typed list anyway** — a typed list can
only be produced by a Scripting action, and PROCESIO doesn't map a JS object onto a
typed model's attributes. So **list-bound document tables don't work on this platform**;
scalar `<%name%>` binding DOES (chips resolve, renders). The working pattern for
dynamic/repeating content is the **HTML-string shell** (one `<%htmlContent%>`
placeholder fed a full HTML string from a script via an `{result:string}` envelope) —
proven by `AAT_BriefShell` + `AAT_Process_SearchGenerate`. Tool guard added:
`document` builder `prepare_ctx` now prints a WARNING when a body references a
list-variable attribute, steering to the shell pattern; `document/description.md`
documents it.

## Tool-implementation status (gap review)

All fixes are in the BUILDER CODE (so a fresh session's create/edit is correct), not
just applied to live resources — verified by grep + 38 tests:
- process: config-value mirror, document-mapper/decisional-case config transforms,
  build audit, canvas origin, variable-id preservation on edit, template `{var,path}`
  + object templates, scripting global index, error ports/Join/decisional/custom-resp.
- form: flat elements, events/triggers, field-name->value-path resolution, full
  data-model mirror (fields container + per-element sub-models + value attrs).
- document: scalar binding + name->id; active list-table warning.
- schema widened; goldens regenerated; regression tests added (config mirror, docMap
  shape, form data-model mirror).
Remaining items are PLATFORM limits, not tool bugs, captured in docs/memory so a fresh
session avoids them: JS output is `{result:v}` and won't fill typed models (use
HTML-string shell); RUN_JAVASCRIPT form events + Angular model don't run under headless
Playwright (verify form JS in a real browser); compiled-model cache (create data models
complete, don't rely on datatype-edit add for attrs consumed by Generate Document).

## Round 5 — decisional condition needs the full field set

The round-3 decisional-case transform was incomplete: a real decisional condition (full
shape from the chat Bot export) also carries `value: null`, `rightOperandAsListRequired:
false`, `operandsAsListOptional: true` (besides id/uid/operator/logicOperator/left/right/
auxOperator). Omitting them made the designer fail to render the condition — empty/red
right operand, "Case (not configured)", and the **Validate button hung**. Also a literal
operand value (e.g. `50`) must be a **string** ("50") in the config. Fixed in
`_decisional_cases_config` / `_operand_config`; regression test added.

A throwaway dev process `zzz_comprehensive` (`669722ec-…`) was repaired in place (GET ->
re-mirror config with the fixed transforms -> PUT). Its 4 Concatenate `Input String 2`
fields were genuinely empty in the test data (a required field) — filled with a literal;
that's process data, not a tool bug. **Reusable recovery move:** any older process showing
"not configured" can be fixed without its source config by GET -> `_apply_values_to_config`
per action (normalize camelCase params to TabPropertyId/Value/Variable) -> PUT.

## Round 6 — form data-model ROOT id must be separate from the form id (THE form bug)

Runtime symptom: typing in a field threw `Cannot read properties of undefined
(reading 'searchTerm')` from the onInput concat — i.e. `ProcesioForm.data.fields` was
**undefined**, even though real forms' onClick handlers do `ProcesioForm.data.fields.X
.visible = …` fine. Same root cause as the designer "Unknown" mappings. Decisive find
from a real export: the form's `Data.dataModel` **root id is a SEPARATE generated id,
NOT the form template id** (real: root `a07641ba…` ≠ form `70876314…`), the fields
container's `parentDataTypeId` is that root id, and the field-reference path's FIRST
segment is that root id. My builder set the root id = the form id and used the form id
as the path's first segment — that collision broke the runtime's `data.fields`
construction and the designer resolution.

**Fix:** `build()` now generates `ctx["dm_root_id"]` (separate), `_build_data_model`
uses it as the dataModel root id + the fields container's parentDataTypeId, and the
field paths use it as segment 0. Verified structurally (root id != form id, fields
container hangs off it, inputMap path[0] == root id). RUNTIME confirmation needs a real
browser — headless Playwright can't fire the Angular onInput; the concat is now
defensive (no hard error) + logs an `AAT diag` line if `data.fields` is still missing.

## Round 11 — ROOT CAUSE (definitive): element goldens were stale, not what the toolbar produces

User's brilliant move: added a FRESH "Text input" from the toolbar (`input1`) next to my
generated `companyName`, mapped the input variable to `input1` (which resolved), and saved.
This put a canonical control beside a generated one in the same form. The diff:

- The variable picker showed `input1 -> value` but `companyname -> defaultValue` only, NO
  `value`. So my field had no `value` property to map -> "Unknown".
- **PROCESIO RECOMPILES the data model from the ELEMENTS on save**, and only emits a `value`
  data-model attr when the element's `value` config is CANONICAL. Canonical input value
  config = `{key:"value", label:"Value", type:"hidden", value:"", exposed:true,
  events:["EMIT_INPUT"]}`. My golden had `{label:"", value:null}` with no `exposed`/`events`
  -> compiler dropped the value attr.
- My goldens were hand-trimmed captures: a real input has 18 configs (all `exposed:true`)
  incl `type`/`disabled`/`visible`/`onFocus`/`onBlur`/`style`; mine had 12 and lacked
  `exposed` everywhere. (The earlier "visible" round was a partial symptom, not the cause.)

Fix (the real one): **re-captured all 27 element goldens from real toolbar-created controls
in the repo exports** (`docs_info/Exports/*.procesio` -> `Forms[].Data.elements`). A real
input there matches the user's fresh `input1` byte-for-byte (verified). Extractor
(`tools/procesio/dto/form/capture_goldens.py`): per type, pick the export instance with the
most `exposed:true` configs; neutralize event/option/style values. Builder data-model build
now mirrors PROCESIO's compiler: one attr per non-event/non-`style` config, attr name =
camelCase(key) (`info-text`->`infoText`), id == config id, isPublic/hidden false; removed the
visible-synthesis hack (canonical goldens include it in the right position). 42 tests green.

Live AAT form re-applied: companyName/country/searchTerm sub-models are now byte-identical
(14 attrs incl `value`) to PROCESIO's compiled `input1`; both buttons' input/output map
value-segments resolve to the field's value config id; diagnostic `input1` removed. (User to
confirm the input "Form variable" now shows companyName/country and the field exposes `value`.)

## Round 10 — input-side "Unknown" = field sub-model missing a `visible` attr

After Round 9's isPublic/attr-id fix the OUTPUT form-variable resolved (`form.fields
.brieffile.value`) but the INPUT side STILL showed "Unknown" for companyName/country.
Same form, same data model, same dotted4 path format. The asymmetry: output references
briefFile (file-upload), input references companyName/country (text inputs).

Deep key-by-key diff of my companyName sub-model vs the reference `cui` field (input,
referenced on the input side of a real form): mine was MISSING `visible`, `disabled`,
`type` attrs and had `info-text` (vs ref `infoText`). The decisive correlation:
**briefFile RESOLVES and HAS a `visible` attr; companyName was UNKNOWN and LACKED it.**
briefFile resolves WITHOUT `type`/`disabled`, so only `visible` is load-bearing for the
trigger-map input-side resolver — a field with no `visible` attr is treated as
non-mappable. Root cause in the tool: the `input` element golden was captured incomplete
(no `visible` config), while `file-upload` includes it — which is exactly why output
worked and input didn't.

Verified the mechanism with real data: 199 real-form elements have onInput/onChange
events AND are RUN_PROCESS inputMap targets (so events aren't the cause); input- and
output-referenced fields are BOTH isPublic:false (so isPublic-by-direction isn't it).
Fix: form builder synthesizes a `visible:true` config on any element golden lacking one,
so every field sub-model carries a `visible` attr (id == the element's visible config id,
preserving the attr-id==config-id invariant). 42 tests green; new guard
`test_form_every_field_submodel_has_visible_attr`. Live AAT form re-applied: companyName,
country, searchTerm, briefFile all now have a `visible` attr. (User to confirm the
trigger-map input "Form variable" now shows companyName/country instead of "Unknown".)

## Round 9 — map "Unknown"/blank ROOT CAUSE + searchTerm concat actually fixed (ground truth from 163 real forms)

User: after Round 8 the input form-variable went from raw-guid to **"Unknown"** and output
was still blank — "a step in the right direction, but still not solved". Also: **bring back
the Search Term field — fix the issue, don't go around it.** (Dropping searchTerm in the
earlier round was avoidance.)

Got GROUND TRUTH two ways: (a) mined the repo's real project exports
`docs_info/Exports/*.procesio` (each has a `Forms` array with stringified `Data`); (b) a
12-way parallel workflow scanned all 145 live workspaces → 163 real UI-built forms with
RUN_PROCESS maps / in-form JS. Reference form for both bugs: **OMS Homepage** (also
HUB-Overview-Tabs, eTransport HUB).

BUG A — "Unknown"/blank. The dotted4 map path `<root>.11223344.<el>.<valueAttr>` and
root==variables[0] were already correct (identical to real forms). The real differences,
both properties of platform-GENERATED data models that my builder violated:
  1. **data-model attr id == the element's CONFIG id** of the same key. Real forms reuse
     the element config ids as the fields sub-model attr ids (OMS 15/16; the value-attr id
     == the element's `value` config id). My builder minted FRESH attr ids (0/11 match) →
     the path's value-segment resolved to nothing the designer could name → "Unknown".
  2. **`isPublic:false`** on every field sub-model AND leaf attr. 100%-consistent across
     all 163 real forms; my builder set `isPublic:true` → resolver won't index the node.
Fix (form builder): `_build_element` uses the element's `value` config id as the field-path
value segment; `_build_data_model` reuses each config's id as the attr id and sets
isPublic:false (+ hidden:false). Live AAT form now: 70 attrs, 0 id-mismatches, 0
isPublic≠false, all 3 map value-segments == element value config ids.

BUG B — **in-form JS field access WORKS** (Round 7's "JS can't read fields / ProcesioForm is
a stub" was WRONG — that probe ran outside the live form-runtime iframe). Real API, embedded
verbatim in a real form's own JS doc-comment: `ProcesioForm.data.fields.<elementName>.value`
to read/write (also `.visible/.required/.readonly`), `ProcesioForm.variables.<name>` for form
vars. The field key is the element name and the runtime LOWERCASES it (downloadButton →
downloadbutton). So searchTerm is BACK as a read-only field, auto-filled by an onInput
handler on companyName+country: `setv('searchTerm', companyName + ' ' + country)` (defensive
`F[n]||F[n.toLowerCase()]`). 41 builder tests green; new guards
`test_form_datamodel_attr_ids_match_element_config_ids_and_are_private`. (User to confirm in
a designer refresh: trigger-map shows field NAMES, and typing fills Search Term live.)

## Round 8 — process<->form data map showed form variables as guids (input) / blank (output)

User (designer "Map data" panel for the Search & Generate trigger): the **input** form
variable rendered as the raw path guid `<root>.11223344...<element>.<valueAttr>` and the
**output** form variable rendered as **nothing**. Same class of "form vars look like
guids" reported earlier - but this one is in the RUN_PROCESS data map, not the data model.

Root cause (found by probing the live form + the shell): the designer resolves a stored
field path back to its NAME by walking from the form HANDLE variable `Data.variables[0]`
(id `65396456-36bf-4d9f-8d32-63a4a9e5c8c0`, the FORM-scope root, `scopes:["FORM"]`, a
shell constant) into `Data.dataModel`. So `dataModel.id`, the field-path first segment,
and `variables[0].id` must ALL be the SAME id. The form builder was generating a FRESH
`dm_root_id` for `dataModel.id` + field paths (live form had `ae1d596d...`) while
`variables[0]` stayed `65396456...` - so the resolver started at `65396456`, found no
root, and fell back to printing the raw path (input) / blank (output). The earlier
"root != form id" fix had over-corrected: it must be `variables[0].id` (which is ALSO
!= form id), not a random id.

Fix (in the builder, so it never recurs): `build()` derives `ctx["dm_root_id"]` from the
shell's "form" variable (`dataType`/`id`) instead of `_new_id()`, and a build-time guard
raises unless `dataModel.id == variables[0].id` and every `field_paths` value roots at it.
New regression test `test_form_field_paths_root_matches_form_handle_variable`. Removing
the `_new_id()` call shifted the deterministic test id sequence by one -> regenerated
`fixtures/reg.elements.json` (verified structurally identical, pure -1 id shift). 40 tests
green. Re-applied `form_final.json` to the live form; probe confirms `dataModel.id ==
variables[0].id == 65396456...`, both buttons' input paths + btnSearch output path now
root at `65396456...`, and the `fields` container holds element sub-models named
companyName/country/briefFile each with their value attr - so the designer now shows the
field NAMES on both sides. (User to confirm visually after a designer refresh.)

## Round 7 — in-form JavaScript CANNOT read field values (current runtime)

Probed the live runtime layer by layer (no Chrome MCP, headless can't fire onInput, so
read the object shape through the console). Result: in `forms.procesio.app`'s current
runtime, the in-form JS sandbox (about:srcdoc) exposes only a STUB:
`ProcesioForm == {data: "<formId-string>", variables: {form: ""}}` — **no field
values**. The old `ProcesioForm.data.fields.X.value` API (from exports) is a previous
runtime version and no longer works. So **any form JS that reads/writes field values
fails** — the read-only searchTerm oninput concat is impossible, and so is a webhook
`fetch` button that needs the typed values in its payload.

**What works: RUN_PROCESS triggers** — they map field values to the process
SERVER-SIDE (not via JS), so they get the real typed values. Final form design (user
chose "drop searchTerm, map fields directly"): Company + Country inputs, a file-upload,
**Search & Generate** = RUN_PROCESS Process 2 (companyName+country -> PDF into the
upload), **Email me** = RUN_PROCESS Process 3 (companyName+country -> SendGrid email).
No searchTerm field, no field-reading JS -> no console errors. Process 3 restructured
to take companyName+country (was the webhook payload model). The webhook
`AAT_BriefRequested` remains a standalone API-triggerable artifact.
**Rule for the form builder going forward: never rely on form JS to read field values
— use RUN_PROCESS inputMap/outputMap (server-side) for anything that needs them.**

## Form (AAT_CompanyBriefForm `1c515f94-ef1a-4696-aa62-43fb78e55221`)

Render URL: `https://forms.procesio.app/iG5-IMmbNP` (CustomUrl tinyUrl). 8 controls:
heading, paragraph, 2 inputs (companyName/country), read-only searchTerm, file-upload
(briefFile), Search & Generate button, Email-me button. Renders perfectly with the
enterprise theme (verified by screenshot).

17. **Form trigger config (verified against real exports):** per-control config key
    `onClickEvents`/`onInputEvents` = `{debounce:0, events:[{id, type:"CLICK"|"INPUT",
    action, config}]}`. `RUN_PROCESS` config = `{processId, syncRun, inputMap,
    outputMap, conditions:[], areConditionsConfigured:true}`. `RUN_JAVASCRIPT` =
    `{code}`. Both inputMap & outputMap rows are `{id, left: <processVarId>, right:
    <formFieldPath>}`.

18. **Form field value-path = `formId.11223344-5566-7788-99aa-aabbccddeeff.elementId
    .valueConfigId`** (the middle GUID is a platform "fields" container constant,
    confirmed across forms). The form builder now resolves a field **name** in a
    trigger's inputMap/outputMap/mapping to this full path (`ctx['field_paths']`), so
    triggers reference fields by name. Fields must be declared **before** the buttons
    that reference them (paths are registered as elements build in order).

19. **RUN_PROCESS from a form WORKS end-to-end (verified live):** clicking Search &
    Generate ran Process 2 synchronously and placed the generated PDF into the
    file-upload control (download icon appeared). The form runtime executes the
    process with the workspace context — an anonymous public form can run a process
    that uses credentials.

20. **Make the process robust to the form, not the reverse.** Process 2 takes
    `companyName`+`country` and concatenates server-side (Call API `q` =
    `"<%0%> <%1%>"` over both vars). So the brief is correct from the two filled
    fields directly; it does NOT depend on the client-side concat firing. The
    read-only `searchTerm` field + its oninput concat is a display convenience only.

21. **Known limitation — RUN_JAVASCRIPT form events + headless verification.** Under
    headless Playwright, `fill()` and even per-key `press()` set the native input's
    visible text but do NOT update PROCESIO's Angular form **model** (custom input
    components) — so an empty model field, when read by an inputMap path, resolves to
    the *path string* itself (e.g. a filename came out as the field path). Separately,
    `RUN_JAVASCRIPT` events (the oninput concat, and the webhook `fetch`) did not fire
    in the headless runtime even though the event structure matches real exports
    exactly (a dead-simple constant assignment to `searchTerm.value` also didn't
    show). The webhook `fetch` is additionally cross-origin (form -> webapi) so it
    needs `mode:'no-cors'`. These are form-RUNTIME/headless-automation concerns, not
    DTO-builder correctness — the form is built per the documented contract; real
    keyboard users drive the Angular model. Verify form JS interactions manually in a
    real browser, not headless.

## Round 12 — DECISIVE functional test: list-bound document tables DO render; Round 4 was WRONG

A scratch process functional render test settled the AAT_CompanyBrief "Unknown" mystery
definitively. Two runs in the AAT workspace (`3fd85e9d-…`), Generate Document -> PDF,
typed `hits` list fed via a **process-variable DefaultValue containing a JSON array**
(option 2 — no Call API echo, no Javascript needed; it worked first try):

- **Run A — original `AAT_SearchHit` (f675610e) + original `AAT_CompanyBrief` doc
  (503f33b4):** status **40**, single error: `Unable to find attribute
  5625a0c7-… (title) in data type f675610e-… (AAT_SearchHit). Please ensure the data
  model attributes are defined correctly.` The run REACHED document rendering and
  iterated the list (so the typed list WAS populated) — it failed resolving the item
  attribute against the **runtime's compiled model**.
- **Run B — FRESH model (all 6 attrs created up front) + FRESH doc (same `<%hits.attr%>`
  table, one `<tr>`):** status **50**, 0 errors, produced `render_test_fresh.pdf`
  (19,395 bytes). Extracted text = **all 3 rows, one per hit** (3 titles / 3 sources /
  3 summaries) + the scalar searchTerm in the header. **Zero "Unknown".**

CONCLUSIONS (overturning Round 4 + the document/description.md "dead end"):
1. **List-bound repeating document tables DO render** — a single `<tr>` with
   `<%hits.attr%>` placeholders expands to one row per list element. The repeating
   syntax is exactly that (bind the list var's attributes in ONE row).
2. **A typed list CAN be fed without scripting** — a process variable typed as the
   item model, `isList:true`, with `DefaultValue` = a JSON array of objects hydrates
   into the typed list at runtime. (This also validates the "Process 2 list feed":
   the same DefaultValue-JSON / one-mapping docMap with `destination.attribute=null`
   binds the whole list to the doc's list variable.)
3. **ROOT CAUSE of AAT_CompanyBrief "Unknown" = the DATA MODEL (the user was right).**
   The original `AAT_SearchHit`'s attributes are present in `GET /api/DataTypes/{id}`
   and look byte-identical to a working model's, but they are **missing from the
   runtime's COMPILED model** — the same stale-compiled-cache failure as learning #12
   (attributes added via `POST/PUT /api/DataTypes/attribute/{rootId}` edit are not
   recompiled). The document designer reads that same compiled model, so the cells
   show "Unknown"; Generate Document throws "Unable to find attribute". A FRESH model
   created with all attributes up front compiles correctly and renders.
   **FIX:** recreate `AAT_SearchHit` from scratch with all attributes in the initial
   `POST /api/DataTypes` (never rely on attribute-edit for attrs consumed by a
   document), repoint `AAT_CompanyBrief.hits` at the new model id, re-map the table
   cell `<%hits.attr%>` ids to the new attribute ids.

NOTE: `document/description.md` lines 43-64 ("repeating tables ... DO NOT work ... a
dead end") and PHASE4 Round 4 are now FALSIFIED and should be corrected — the pattern
works; the prior failure was the stale-compiled-model, not a platform limitation.

## Round 13 — ROOT CAUSE PINNED + LIVE FIX APPLIED: child model `parentIds` back-link drives the runtime compiled model

Round 12 proved the AAT_CompanyBrief "Unknown" / "Unable to find attribute" failure
is a DATA-MODEL defect (fresh model rendered, original threw). Round 13 isolated the
EXACT load-bearing field, fixed the LIVE model, and re-rendered the ORIGINAL model+doc
to green.

THE ONE FIELD THAT MATTERS: an item (child) model's `parentIds` must contain the id of
each parent data model whose `isList`+`isDataModel` attribute references it.
- Broken: `AAT_SearchHit.parentIds = []` (created standalone, never linked back).
- Working refs: a live process with `Details.parentIds=[Invoice]`, `url.parentIds` non-empty,
  `technicalDataElectricity.parentIds` = 2 parents.

RED HERRING (do NOT chase again): the inlined `attributes[]` array on the PARENT's list
attribute (`AAT_SearchReport.hits.attributes`) being `[]` vs 14 on the working process. After the fix
the render is GREEN while that GET array is STILL `[]`. So the inlined-children array in
`GET /api/DataTypes/{parent}` is a lazy/volatile projection, NOT the cause. The runtime
compiled model is keyed off the child's `parentIds`, not that array.

HOW THE LINK IS WRITTEN (and how PUT fails):
- `PUT /api/DataTypes` (top-level) IGNORES `parentIds` — sending the full child body with
  parentIds populated does nothing (and DataType edit only renames; it can't change attrs).
- `PUT /api/DataTypes/attribute` returns **401 Unauthorized** on the userpass session
  (endpoint not permitted) — do not use it.
- `POST /api/DataTypes/attribute/{parentId}` (status 200) is the working path: adding the
  list-of-model attribute on the PARENT makes the platform (a) write the child's
  `parentIds` back-link AND (b) recompile the child into the runtime model. Side effect:
  if an attribute of that name already exists, the server auto-renames the new one
  (`hits` -> `hits_1`); delete the duplicate afterwards via
  `DELETE /api/DataTypes/attribute/{parentId}/{dupAttrId}`. The original attribute id (and
  thus all document cell references `<%hits.attr%>`) is preserved.

LIVE FIX APPLIED (AAT workspace 3fd85e9d-…):
1. `POST /api/DataTypes/attribute/cfa383c7-…(AAT_SearchReport)` with a `hits` list attr
   pointing at `f675610e…(AAT_SearchHit)` → this set
   `AAT_SearchHit.parentIds = ["cfa383c7-…"]` and recompiled the model.
2. Deleted the auto-created duplicate `hits_1` attribute; original `hits`
   (id 0101e404-…) intact, so the doc's cell refs still resolve.

VERIFICATION (decisive, end-to-end, ORIGINAL model + ORIGINAL doc 503f33b4):
- Built a minimal Generate Document process (typed `hits` list fed by a process-var
  DefaultValue JSON of 3 fake hits + 4 scalars), ran synchronous.
- Status **50**, `error: []`, body contains NEITHER "Unable to find attribute" NOR the
  title-attr guid `5625a0c7`. (Round 12's run was status 40 with exactly that error.)
- Downloaded the rendered file via `GET /api/File/download` (path/varId/instanceId/
  flowTemplateId in HEADERS, NOT query) — 3784 bytes text/html — containing all 3 hit
  rows (3 titles, 3 displayLinks, 3 snippets) and **zero "Unknown"**.
- Scratch process deleted (404). No live AAT showcase resource other than the one
  intended back-link was changed.

DTO BUILDER FIX (tools/procesio/dto/datatype/builder.py) — prevent regression:
The builder's `build()` hardcodes child `Content.ParentIds: []` and, when a list attribute
references an EXISTING model via `model:`, never writes the child's back-link — that is how
AAT_SearchHit regressed (created standalone, then referenced). Two-part fix:
1. PREFER inline children: a list-of-model should be authored as `attributes:` (inline
   nested sub-model) so parent+child are created together in the SINGLE initial
   `POST /api/DataTypes` — the platform writes parentIds at create time. Document `model:`
   + `isList` as the regression path.
2. For `model:`+`isList` against a PRE-EXISTING child (and in the `_edit` reconcile path),
   after the parent list attribute is created via `POST /api/DataTypes/attribute/{parentId}`,
   RE-FETCH the child and assert `parentId ∈ child.parentIds`; if absent, the link did not
   take — re-issue the attribute POST (or fail loudly) rather than leaving a silently-broken
   model. Never rely on top-level `PUT /api/DataTypes` to set parentIds (it is ignored), and
   never use `PUT /api/DataTypes/attribute` (401 on userpass).
Add a manifest/runtime guard test: create parent with a list-of-model child, then assert the
child's `parentIds` contains the parent id (the structural invariant that makes documents
expand the list and resolve item-attribute cells).
