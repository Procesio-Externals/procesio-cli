# PROCESIO DTO sub-tools — design note (IMPLEMENTED 2026-06-24)

Captured 2026-06-23; **built and live-verified 2026-06-24**. The plan below was
followed; implementation status is at the bottom (see "Implementation status").

## Purpose (obey this above the mechanism)

Create/edit PROCESIO objects so the result is:
1. **Deterministic & reliable** — DTOs built by scripts from known structures/patterns, reused.
2. **Fast** — script execution, not LLM inference.
3. **Cheap** — no tokens spent assembling the DTO.
4. **Independent** — builders usable outside this tool.
5. **Scalable** — portable into other solutions.

If a mechanism serves this purpose better than what's below, change the mechanism.

## Pipeline (the contract)

```
user request
 → [LLM]      minimal config — smallest correct input, per component   ← the ONLY non-deterministic step
 → [validate] config against the component's JSON Schema (fail-fast)
 → [build]    deterministic builder MERGES config onto a golden DTO template → full PROCESIO DTO
 → [validate@source] call PROCESIO's own validate/test endpoint where one exists
 → [send]     create (POST)  OR  edit (GET current → apply config delta → PUT)
 → [confirm]  return id; for edits, re-GET and diff
```

## Per-component artifacts — the "3-part doc" is **executable files, not prose**

Per component, a folder `tools/procesio/dto/<component>/` containing:

1. `description.md` — what it is, when to use, gotchas *(the general description)*.
2. `config.schema.json` — JSON Schema the LLM fills *(point-2 "config structure")*.
   Maximally constrained: enums for types, required-minimal surface, references
   resolvable against live PROCESIO data.
3. `template.dto.json` — a **real, captured** golden DTO with placeholders
   *(point-3 "actual DTO structure")*.
4. `builder.py` — **pure** function `config → DTO` (template-merge + expansion
   rules). No I/O, no auth, no network. Separately unit-tested.
5. `fixtures/` — golden `config → DTO` pairs (regression tests) + a captured live
   object for drift detection.

The schema + template **are** the documentation. Prose drifts; tested artifacts don't.

## Design principles (the challenge refinements)

- **Template-merge, not from-scratch translation.** The golden template carries
  every undocumented boilerplate field (ids, positions, default flags) verbatim;
  the builder only fills/repeats the semantic slots the config names. Less code,
  higher fidelity, fewer ways to be wrong.
- **Use PROCESIO's own validation as a correctness oracle** before committing —
  `POST /api/Projects/validate`, `POST /api/Credentials/test`,
  `POST /api/Actions/test`, and any per-component validate. The cheapest place to
  catch a bad DTO is PROCESIO itself, deterministically.
- **Builders are pure libraries.** `config → DTO`, zero side effects. The tool
  wraps auth/transport; the builder ports into a process, a service, anything.
  (serves *independent* + *scalable*.)
- **Win reliability at the config schema.** The LLM step is the only soft spot;
  constrain it hard (enums, validated ID references, minimal required fields) so
  mistakes fail at the schema, not in production.
- **Versioned templates + drift test.** Capture each template with date/API
  version; a round-trip test re-GETs a known object and diffs it against the
  template to detect platform drift before it breaks a build.
- **Composable builders.** A process references data models, credentials, and
  actions — its builder composes the smaller builders. Build simple→complex so
  the complex ones reuse the simple ones.

## DTO source (decided)

Primary: **a human annotates example DTOs** (the non-Swagger rules — required
fields, enums, what references what, what the UI auto-fills). Supplement only as
needed by round-tripping a live object (GET an existing one) and HAR-capturing
designer saves (for Documents/Forms whose save isn't a clean REST PUT).

## Tool surface (per component, once taught)

```
<component>-create --config '<json>' [--dry-run]
<component>-edit   --id <id> --config '<json>' [--dry-run]
```
`--dry-run` returns the built DTO + the PROCESIO validate result and sends
nothing. These sit alongside the raw `post-*` / `put-*` endpoint actions already
generated (those remain the escape hatch).

## Build sequence (simple→complex; prove the pattern early)

1. **Webhooks** — small DTO, high frequency. First; establishes the pattern.
2. **Credentials** — small, has a `test` endpoint (built-in validation oracle).
3. **Data Models** (DataTypes) — medium; referenced by everything else.
4. **Forms & Tasks** — medium; depend on data models.
5. **Documents** (document designer) — designer payload; likely HAR-sourced.
6. **Processes** — largest (nodes, edges, variables, actions); composes the above.

## What I need from you to start a component

1. One or two **real example DTOs** (a create + an edit), exported or pasted.
2. **Notes on the non-obvious rules**: required fields, allowed enums, references,
   what the UI fills automatically.
3. The create/edit endpoints (already generated) + any validate/test endpoint.

From those I produce `config.schema.json` + `template.dto.json` + `builder.py` +
`fixtures/`, and the two `<component>-create` / `-edit` actions.

## Open questions (resolve when we start)

- **Reference resolution** — builder fetches live IDs (datatype/credential/
  workspace) to validate config references at build time, or assumes the LLM
  supplies valid IDs? (Lean: resolve where cheap.)
- **Edit config shape** — full desired-state vs delta. (Lean: desired-state for
  create; delta merged onto the re-GET for edit.)
- **Create idempotency** — guard against duplicates on retry.

## Implementation status (2026-06-24)

All six components built and **live-verified** in a real workspace
(`3fd85e9d-…`). Surface: `<component>-create` / `<component>-edit` actions
(`--config '<json>'` | `--config-file`, `--dry-run`), generated by
`handlers/dto_actions.py` from `dto/registry.py`. Framework: `dto/framework.py`
(jsonschema validate → pure `build` → create/validate/edit). Bundled reference:
`dto/data/platform_types.json`, `dto/data/action_catalog.json` (231 actions),
`dto/form/elements/*.json` (27 golden controls) + `data_shell.json`.

| Component | action(s) | live proof |
|---|---|---|
| **datatype** | datatype-create/edit | create+GET+edit; all primitives, lists, model-ref, inline nesting |
| **process** | process-create/edit | validate→create→**run→STATUS_FINISH**; any catalog action; literal/var/template/attr-path/output bindings; linear+explicit edges; **decisional branching**; webhook attach |
| **credential** | credential-create/edit | create + `POST /test` live connection (GitHub 200); **used in a process** via Call API v3 → 200 |
| **document** | document-create/edit | create; **used in a process** via Generate Document → rendered HTML |
| **webhook** | webhook-create/edit | create (generate-data model) + `launch` → **triggered a process instance** |
| **form** | form-create/edit | create + publish + **rendered at runtime** (forms.procesio.app/{tinyUrl}); 27 control types |

Resolved open questions: **reference resolution** = `prepare_ctx` resolves live
ids (models/credentials/catalog) into ctx, builders stay pure. **Edit** =
desired-state rebuild + PUT (datatype reconciles attributes via the attribute
endpoints). **Idempotency** = not guarded (each create is a new resource).

Tests: `tests/test_dto.py` (pure builders + golden fixtures + schema validation).
Manifest is regenerated by `python -m tools.procesio.gen_manifest` (the file is
too large to hand-edit). Per-component `description.md` + `template.dto.json` +
`fixtures/` document each contract.

### Key live-verified facts (also in PROCESIO-API-NOTES.md)
- **Forms render from `Data.elements`** — the encrypted `Data.code` blob is NOT
  needed (proven: code="" + modified elements rendered the change). Forms are
  reachable at runtime only via a **CustomUrl** (`POST /api/CustomUrl/FormTemplate`
  → `tinyUrl` → `forms.procesio.app/{tinyUrl}`); a bare `/forms/{id}` 404s.
- **Processes** keep the **client-supplied Id** (POST returns empty). Ports live
  on the source action; a `00000000…`→Start entry edge is required; each branch
  needs its own **Stop** (a Stop accepts one input port).
- **Webhooks** need the generated webhook-type DataModel (`generate-data`) +
  `IsEdited:true`; MANUAL works, AUTO needs different handling.

## Phase 2 enhancements (2026-06-24, all live-verified)

**Process**
- **Scripting actions** (Javascript, Python) work via the generic builder: `Code`
  (a `{template, vars}` binding with `<%0%>` index injection) + `Output` ({var},
  typed `json`/`object`). JS outputs via `setOutput(v)` → `{"result": v}`; Python
  outputs via `print(v)` → `{"result": "<stdout>"}`. Inputs inject by **index
  `<%0%>`**, NOT by name. SQL = Execute Query (`list<object>`) / Execute Command
  (rows-affected) with `@param`.
- **Global `<%N%>` indexing per action** — variable indices are now unique across
  ALL of an action's parameters (was per-param), required for actions that reuse a
  property facet for multiple params (JS Code+Output, Decisional Cases+Default,
  document-mapper). `{template}` local `<%i%>` are remapped to the global index.
- **Error ports** — `onError: "<handlerId>"` on an action creates an
  `ErrorDataModel` variable (`10c6ac59-…220`, `IsError`), sets `VariableErrorId`,
  and adds an error port (`Type:1, Data:{isDefault:"error"}`) to the handler.
- **Join** convergence — the flow-control Join is `fb6a9d14-…` (`inputPorts=-1`,
  accepts many); a list-`Join` shares the name, so control actions
  (start/stop/join) are **pinned by id** in `_CONTROL_TEMPLATE`. Branches converge
  via Join (each branch otherwise needs its own Stop — a Stop accepts 1 input).
  Decisional **default** port = `Type:0, Data:{isDefault:"default"}` (done).
- **Canvas layout** — build-time positions come solely from the shared layout
  engine (`_engine_layout` → `layout/engine.py`): nodes laid left-to-right by
  layer, happy path on the main lane, parallel nodes fan into lanes, error
  handlers drop to a low rail. Implements the PROCESIO design directives
  (one-direction flow, minimize crossings, ≤50 actions, Join to declutter). The
  legacy provisional `_layout()` was removed 2026-07-07 (it was always overwritten
  by the engine; DTOs stayed byte-identical) — see
  `todo/done/procesio-retire-builder-layout.md`.
- **`docMap`** (Generate Document) — maps document-template variables to process
  variables: `[{id, source:{value:"<%N%>", variable:[…]}, destination:{id, variableId:<docVarId>, attribute}}]`.
  `prepare_ctx` resolves the doc's variable ids from `Select Document Template`.
- All 231 catalog actions are reachable (data-driven by label); ~19 names are
  ambiguous (versioned variants) → reference by actionId when it matters.

**Document**
- Body authored with friendly `<%name%>` placeholders is translated to
  `<%varId%>` at build time (the render engine resolves by **variable id**, and the
  server keeps client-supplied ids). URLs/images = plain HTML `<a>`/`<img>` in the
  body. Repeating tables over a list var = one `<tr>` with `<%listId.attrId%>`
  cells (the builder substitutes the leading var name → id; the `.attr` must be an
  attribute id). End-to-end verified: a variable document populated via Generate
  Document `docMap` rendered the values + the link.

**Forms**
- **Events + triggers** — `events: [{on, do, …}]` per control. `on` ∈
  click/input/focus/blur/open/tabchange/rowadded/rowdeleted/paginated →
  the right `on*Events` config = `{debounce, events:[{id, type, action, config}]}`.
  `do` ∈ **map** (MAP_FORM_DATA), **process** (RUN_PROCESS: processId, syncRun,
  inputMap/outputMap), **js** (RUN_JAVASCRIPT: code), **form** (RUN_FORM).
- **Tasks/assignees/approvals** — `assignee`/`assigneeReplacement` on
  section/tabs/table; `approver`/`approverReplacement` on the approval control.
- **Themes/CSS** — `theme: {"--c-primary":"#…", …}` overrides the shell theme
  (19 sections of `{type,label,value,cssVariable}`). All control properties are
  settable via the named convenience keys or the raw `configs` passthrough.

## Phase 3 — systematic coverage (2026-06-24, live-verified)

- **All-actions audit** — every one of the **210 distinct catalog actions builds
  AND validates** (`/api/Projects/validate`): 210/210, zero structural failures.
  The data-driven builder genuinely covers all PROCESIO actions (versioned
  duplicate-name variants → reference by actionId).
- **Error-port exclusions** — `onError` is rejected on Start/Stop/Join/For Each
  (they have no error port), per PROCESIO.
- **Forms use a FLAT elements list + parentId** (NOT nested `children`) — corrected
  a real bug: nested-children containers did **not** render. Now section/columns/
  tabs children are flat with `parentId`, and columns/tabs keep an ordered
  child-name list. **Verified live**: section child, 2-column layout, and a table
  all render.
- **Form tables** — `{"type":"table","columns":[{"key","label","cell":{…}}]}` builds
  the table + a `static-table-row` + the cell controls wired via
  `childrenIdPerColumn` (colId→[cellId]). **Verified live** (PRODUCT/QUANTITY columns
  with input/number cells render).
- **Document tables with variables** — a repeating table over a list-model variable:
  one `<tr>` with `<%items.product%>` cells (friendly names → `<%listId.attrId%>`
  via model-attribute resolution). **Verified live**: a 2-row table rendered from a
  mapped list (Widget/Gadget), plus a scalar var + hyperlink.
- **Data Model from JSON** (platform trick) — `datatype-create … "fromJson":{…}`
  infers the model via `/api/DataTypes/generate`. **Verified**: nested object +
  list inferred. Other platform tricks are UI-only (canvas shortcuts); the
  `group/name` process-naming convention is supported (just the name field).
- **Form events expanded** to the full documented vocabulary (ready/hover/
  stepchange/nextstep/previousstep/before|afterapprove|reject/messages…) on top of
  the export-verified click/input/focus/blur/tabchange/row/pagination set.
- **Design directives applied**: error-port→handler pattern, one-direction
  left-to-right auto-layout with lanes + a low error lane, ≤50-action guidance,
  secrets only in the credential vault, distinct action names (user-supplied).

**Webhooks — AUTO (listen+capture) + custom responses (corrected & verified).**
The docs clarified that **AUTO = the listen/capture METHOD** (not a stored type):
`type:"auto"` runs the real designer flow in the webhook `create` override —
create → get URL → `POST /api/Webhooks/listen` (start) → send the sample to
`/api/Webhooks/launch/{id}` → stop — returning a `capture` log. Verified: the
AUTO webhook is created via listen+capture and triggers a process. (The gateway
won't persist `Type:0` via REST — `POST Type:0` → 502 — so the stored type is 1;
AUTO is the method.) **Custom webhook responses are configured ON THE PROCESS**
(per docs): `process-create … "customResponse":{"var":"responseVar"}` sets the
flow `CustomResponseDto` (`{Variable, Value:"<%0%>"}`, matching production); the
value is computed and stored on the instance
(`GET …/instances/{iid}/customResponse` → verified "OK-"). The webhook-definition
`CustomResponseConfig` (static/JS/JSON-path) and the synchronous HTTP return are
designer-only (not persisted/exposed by REST). MANUAL + AUTO + trigger all work.

---
## These capabilities are CURATED ACTIONS — do not reimplement
Everything described above is reachable through a runnable action (run `python scripts/run-tool.py procesio`
to list all ~330). In particular:
- Parse a flow/export into a node/edge graph → **`read-flow-graph`**; structural summary/smells → **`inspect-flow`**.
- Auto-layout a canvas (legacy or `LAYOUT_ENGINE=elk`) → **`layout-flow`**; verify positions → **`verify-layout`**;
  cross-process map → **`layout-resource-map`**; re-lay-out a LIVE process in place → **`relayout-process`**.
- Duplicate a process → **`duplicate-process`**; validate one → **`process-validate`**; delete → **`process-delete`**.
Reach for the action first; only drop to a raw `<method>-<path>` wrapper or `request` if no curated action fits.

## Two builder gaps that only appear at SAVE time (fixed 2026-08-27)

Both were invisible to `--dry-run` reading and to the offline schema, and both blocked the save of
any config using them.

**1. `{"var": x, "path": [...]}` wrote the attribute NAME.** `attr_index` was documented but never
populated, so the name went straight into `attribute.attributeId` — a field the API parses as a
Guid — and the save died with `Error converting value "ToEmail" to type 'System.Guid'`. Every
model-typed attribute binding was affected. `prepare_ctx` now fetches each referenced model
(`GET /api/DataTypes/{id}`, recursively for model-typed attributes) and indexes its attributes by
name; each step of a path is resolved against the model the PREVIOUS step lands in, which is what
makes a nested path work. A value that already looks like a Guid passes through, an unknown name
raises and lists the attributes that do exist, and a variable with no known model still passes the
name through (offline behaviour unchanged).

**2. A SQL node was built without its `Parameters config tab`.** The builder emits only the
properties a config names; the designer renders that one from the TEMPLATE, finds no value, and
blocks the save with "Please make sure that the action is defined/configured properly". So NO
`process-create` config containing an Execute Query / Execute Command could be saved, bound or not.
The builder now always appends it (empty when unbound), keyed per family — the Command bind id is
not the Query one.

### A `For Each` needs its ports wired explicitly
The implicit linear chain walks every action including the loop BODY, which leaves the For Each with
one outgoing port and the last body action with none. Two BE errors, both `statusCode 391 "Action
has too few output ports"`, one after the other. The shape that validates:

```
["start","getPending"], ["getPending","loop"],
["loop","buildBody"],   ["loop","stop"],     <- body entry AND the continuation after the loop
["buildBody","send"], ["send","mark"], ["mark","loop"]   <- the body closes back onto the For Each
```

So: a `For Each` takes TWO outgoing edges, and the last action of the body loops back to it. Body
actions still carry `parent: "<forEachId>"` as well — `parent` sets containment, `edges` set flow.

## The warm toolrunner daemon serves STALE tool code

`scripts/run-tool.py` routes through a persistent worker pool by default, and those workers keep the
modules they imported at start. **After editing any tool source, `run-tool.py` keeps running the OLD
code** — the same command produces the same pre-fix output while pytest against the same file is
green, which reads exactly like "my change did not apply". Nothing warns.

Use `AAT_RUNNER=0` (or `AAT_RUNNER_DIRECT=1`) for the first call after a code change, or restart the
daemon. The give-away is a fix that is provably present on import (`inspect.getsource`) and provably
absent from the tool's output.

## Engine-STATE properties: a `For Each` times out on iteration one without them

A template can declare properties of `type: "ignore"` — engine state the designer never shows and
no config names, carrying their seed value ON THE TEMPLATE. The builder emitted only the properties
a config named, so it dropped them, and the engine then fell back to its own defaults.

On `For Each` that is fatal and reads like a configuration problem: without **`Action start time`**
(template seed `2010-01-01T00:00:00.0000000Z`) elapsed time is measured from year one, so the loop
fails instantly with `Foreach timeout exceeded!` — whatever `Action timeout` says, including a
generous 300. The other one is `Zero based list index` (seed `-1`). `Call Subprocess` declares one
too; nothing else in the catalog does.

The builder now copies every `ignore`-typed property from the template. **Diagnosing this from the
error is impossible** — the fix came from diffing the node against a For Each in a working export,
which is the general technique: when an action fails on configuration the validator accepts, dump a
live working instance of the same action and compare `Parameters[]` property-by-property.

A working `For Each` in a live flow also sets `Action timeout` to `0` (no cap).

### `Send Email`: the From address is a property, and SendGrid checks it
`From (Display Name)` and `From (Entity)` differ only in their last four characters
(`…ca11e4ef116c` vs `…ca11e4ef11c6`), and only the second one is the ADDRESS. A config that names
neither gets neither emitted, so there is no property to patch afterwards — `node-set-param` answers
"property not found on node", because the builder only writes what the config asked for.

Over a SendGrid relay an unverified or blank From fails the send outright: *"The from address does
not match a verified Sender Identity"*. The SMTP credential's own `From` may be blank, in which case
the address must come from the action. `sendgrid list-verified-senders` lists what the account will
actually accept.

## `<component>-edit --dry-run` used to preview a CREATE, not the edit

The dry-run branch built the DTO straight from the config, skipping the component's own edit
preparation — which for a process is exactly what reuses the live flow's VARIABLE IDS by name and
its canvas positions. So the preview showed brand-new ids while the real edit kept them.

That is the worst direction for a preview to be wrong, because a process variable is referenced BY
GUID from outside the process (a form's RUN_PROCESS inputMap/outputMap binds it by id), so "do the
ids survive this edit?" is the question a dry-run is run to answer. It answered wrongly both ways: a
preserved id shown as changed, and a genuine rename shown as if nothing external would break.

Fixed by extracting the live-resource enrichment into a `Component.edit_ctx` hook that both the real
edit and the new `framework.build_edit_dto` call. A component without the hook is unaffected, and an
unreadable live resource still produces a preview rather than refusing one.

**The general lesson:** a dry-run is only as good as the code path it shares with the real write. If
it builds through a different path, it is a different operation wearing the same name.
