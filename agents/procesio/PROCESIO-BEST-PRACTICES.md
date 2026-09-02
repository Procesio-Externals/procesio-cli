# PROCESIO implementation best practices (distilled)

Agent-scoped guidance: the standards a build must meet, not tool mechanics. The
agent applies these when designing and reviewing any process, form, or use case.

**Source:** Google Doc "Best practices for implementing with PROCESIO"
(`docId 1t0nqrVKEJwkuubhiIDpRcXd3OubClmfmmbfav953dZo`, captured 2026-06-25).
Captured here per Hard rule 6 so the standard survives chat compaction. Re-pull the
doc if it changes; this is a distillation, the doc is the source of truth.
Platform tricks: https://docs.procesio.com/platform-tricks

The source doc has 6 image-only examples (bad vs good parameter handling; the
5-Decisional ~2s vs single-Decisional <200ms speed comparison; the JSON-to-Data-Model
extraction diagram) that carry no alt text and are not reproduced here - open the doc
for the visuals. The principles they illustrate are captured in sections 2, 9 and 10.

---

## 1. Frame the work

- One measurable KPI per process (e.g. "reduce onboarding cycle time by 30%").
- Map as-is -> to-be: triggers, systems, data contracts, SLAs, exceptions.
- Define RACI early: business owner, builder(s), reviewer/QA, approver, operator.
  Use the `bpof-expert` skill for process mapping and RACI.

## 2. Solution design

- **Modularize:** one main process + small reusable subprocesses (auth, paging,
  validation, notifications). Trade-off both ways: too many subprocesses = harder
  debugging + extra execution time; none = a monolith that re-runs steps it should
  not. Choose deliberately.
- **Stable contracts:** standardize inputs/outputs as DTO-style variables. Do not
  pass raw API payloads between steps.
- **Idempotency:** a retry or a double-trigger must not create duplicates. Use
  external IDs and dedupe/once-only keys. Triggering twice must not change records.
- **Error ports:** wire them for error capture and error-handling logic.
- **Stateless core:** anything that must survive across runs (checkpoints, last-sync
  time, job status, idempotency keys, approvals) lives in a durable system of record
  (CRM/ERP/ticketing or a DB you own). PROCESIO variables are ephemeral - use them
  only within a single execution (pass data between steps, hold tokens, page
  cursors, correlation IDs).
- **Perceived speed is non-negotiable.** Users must feel the UI helps them, not that
  they wait on PROCESIO. A slow form reads to the client as "PROCESIO is slow". Do
  not let this happen. See sections 9 and 10.
- **Secrets:** never in processes. Credential Manager only.
- **Centralize parameters:** a value used in many processes (and that will change)
  is set in ONE place and shared, so one change propagates. Never hardcode it in
  many places. Hardcoding + scattering always creates future effort.

## 3. Integrations (target 1-2 days for the first system)

- Wrap each external API in reusable subprocesses: `auth-get-token`,
  `<system>-get-by-id`, `<system>-search`, `<system>-upsert`, plus a pagination
  helper and a rate-limit handler.
- Exponential backoff with jitter. Example attempt -> wait: 1 -> ~5s, 2 -> ~10s,
  3 -> ~30s, 4 -> ~1min.
- Idempotency keys so the same logical action runs once even on retry/double-trigger.
- Standard error object across integrations.

## 4. Data contracts

- Define DTO variables (Customer, OrderLine, Address).
- Reuse data-model children of the same data model where appropriate.

## 5. Robustness

Global try/catch via Error Port + Decisional action. Classify and handle:
- **Retryable:** retry(max=3, backoff=2^n).
- **Business:** send to queue + notify owner.
- **Hard fail:** alert, capture context, stop.

## 6. Observability

- Generate a correlation ID at start; pass it to all logs/requests.
- Store the main process instance ID; set an explicit status (success/fail/custom).
- Alert on thresholds when something fails repeatedly.

## 7. Document & handover

- Document each process. Map the order processes trigger in (visual map if needed).
- Write SOPs so someone without prior context can debug or follow the logic.

## 8. DB actions (SQL Server / MySQL) + Data Store

The DB credential (catalog type **`SQL`**) is now multi-engine: it carries a **server
type** (`DbClientType` — `MSSQL=1`, `MYSQL=2`), so the same `Execute Query` / `Execute
Command` actions run against **MySQL** by binding a MySQL-typed DB credential (PRC-3696).
**Redis** shipped as its own credential type + connector. No new action families — pick
the engine on the credential. Outbound DB hosts are SSRF-guarded by a host blacklist, so
a private/blacklisted host is rejected at connect time. Bind values as **parameters**,
never inline — the injection-safe `@param` map is engine-agnostic. **Data Store** (the
tenant table feature) is separate — see the `datastore` guidance topic; scheduling a
process on a cron is the `scheduling` topic.

Use the `sql-server-optimizer` skill for any SQL in a SQL action. Core rules:
- Inject data via action parameters; centralize all params at the top of the
  statement for visibility.
- Parameters go on the RIGHT-hand side of an operation only. `WHERE I.Id =
  @Param_Id` good; `SELECT *, @Param_Id` or `SET @Parameter = @SQLVariable` errors.
- Param names may match internal SQL variable names (the compiler resolves safely);
  use each parameter once. After injection, clean the SQL variables holding param
  data before the rest of the statement runs.
- FROM/JOIN: smallest record set first, largest last.
- Join conditions: most restrictive first. INNER joins before LEFT joins.
- Max 5-6 joins. Beyond that the engine cannot compute an optimal plan (5!=120,
  6!=720, 7!=5040) and falls back to running it as written.
- WHERE: most restrictive condition first.
- Pre-calculate values; do not call functions per row (no `ISNULL(...)`/`CASE` in a
  per-row WHERE/SELECT when it can be computed once into a variable).
- Filters activate only when set: `(@p IS NULL OR (<col> LIKE '%'+@p+'%'))`, not a
  `CASE` that always evaluates.

## 9. Forms & Tasks - UX timing (outcome rules)

- **>=90% of clicks under 1s.** Limit calls to processes (Forms have features that
  avoid most calls). When you must call a process, keep it to a minimum number of
  actions (1 ideal, 3 still ok, 5 bad, >5 really bad) and optimize it for speed
  (section 10). Use scoped loading visuals for the affected section, not a full
  screen. Paginate and filter tables that can grow large.
- **<=10% of clicks in the 1-3s band.** Break a long task into steps each under 3s,
  updating the UI as each finishes, so the UI feels faster.
- **No click ever over 3s.** Use an async mechanism: let the user continue and
  notify them when done.

## 10. Optimize for speed

- Every action costs ~10ms. Some are natively slower (Decisional), some faster
  (numeric Add). An action gets slower when it parses/injects large data, or talks
  to an external system (Call API, SQL, FTP).
- Levers: reduce action count at all costs; use scripting actions effectively
  (do more per action); optimize the external systems (SQL statement + DB; use
  Call API/FTP only where needed when form-call latency matters).
- Example: 5 Decisional actions ~2s -> a single Decisional <200ms -> best, a single
  scripting action that does the whole thing.
- Do not extract from JSON with chains of actions. Model the JSON into a Data Model
  and use the variable as `<DataModel>`; then read attributes directly, often with
  no action at all.

---

## Name every Call/Trigger Subprocess node suggestively (never leave the generic label)

When a flow contains a `Call Subprocess` / `Trigger Subprocess`, set the node's **`name`**
(the builder accepts `name` on any action) to describe **what that call does in this flow**,
or the **called process's name** — whichever reads clearer for the context. Never ship the
generic "Call Subprocess" label: on a canvas with several subprocess calls they become
indistinguishable and the flow is unreadable. Examples: `"Citește Contacte proprietari
(read-range)"`, `"Adaugă rândul în Colectare acte (append-row)"`, `"Creează folder Ap.<nr>
(create-folder)"`. The right name varies by context — pick the one that makes the canvas
self-explanatory.

## Form: pre-fill controls from URL query params (validated live 2026-07-22)

A published PROCESIO form pre-fills a control from a URL query parameter **whose key
equals the control's binding `name`**. Open `https://forms.procesio.app/{tinyUrl}?<name>=<value>`
and the control renders with `<value>`. The match is on the config `name` (field/binding
name), NOT the DOM `id`/`name` (empty on the rendered input). Unmatched params are ignored.
Undocumented by PROCESIO, but confirmed live (form with `cod`+`apartament` controls opened
at `?cod=TEST123&apartament=27` → both pre-filled).

Use it to **seed a form from a per-record link**: give each record a stable, URL-safe token,
name a control after the query key, distribute `…?token=<value>`. Then a form event (e.g.
`on: open → do: process`) can read that seed control and fetch the rest. This is the mechanism
behind the Uranus 100 „colectare acte" access model (unique link per apartment, `?cod=`).
To make a form public + get the link: `isPrivate:false` + publish, then
`POST /api/CustomUrl/FormTemplate {Type:3,EntityType:1,EntityId:<formTemplateId>,Url:<slug>}`
→ `tinyUrl` → `forms.procesio.app/{tinyUrl}`.

## Recipe: a dynamic, TYPED PROCESIO document (AAT_ Company Brief — live)
A branded PDF whose repeating table + scalars are filled from a live API call:
1. **Table rows <- `Call API` -> a typed `list<item>` model.** Point the Call API Response
   Body at e.g. `AAT_GoogleResponse {items: list<AAT_SearchHit>}`; PROCESIO deserializes by
   `jsonProperty`. docMap the doc's `hits` list `<- {var: googleResponse, path:[items_attr]}`.
   (The Javascript action canNOT build a typed list — see tool PROCESIO-API-NOTES.)
2. **Scalars** — use the **Node** scripting action (raw output) and map straight onto the doc
   vars; OR with the **Javascript** action route through an envelope model
   `{result:{searchTerm, generatedOn, resultCount, heroImageUrl}}` + docMap `path:[result,
   field]`. Build the envelope model via the attribute-endpoint create flow so it COMPILES.
3. **Never** feed a Javascript-action output downstream as a query/filename — the `{result}`
   wrapper leaks. Drive the Call API query + file name from the ORIGINAL form inputs.
4. Build every data model via the attribute-endpoint create flow (empty model -> POST each
   attribute) so it's COMPILED — else the document renders "Unknown".

## Email a generated file (Send Email)
- **Map attachment is `list<File>`** — declare the file input `isList:true`; a single File
  -> designer "data type mismatch" + NO attachment (run still status 50, so green != attached).
  Pass `[fileDTO]`. Form file-upload controls already hold a list.
- **To** can be a variable for a dynamic recipient (`<%0%>` + Variable[recipientEmail]).
- The Body can come from a document template via Generate Document's "HTML string" output,
  or a templated HTML string.

## Form: an "Email me" button enabled only once the file exists
Conflict: btnSearch must run with no file yet; btnEmail only once the file is present.
Resolve via FIELD VALIDITY, not JS `.disabled` toggling:
- `briefFile` (file-upload) **`required:true`** -> the form is invalid until the PDF lands.
- `btnEmail` **`disabledIfFormIsInvalid:true`** -> enabled only when ALL required (company +
  valid email + file) are present.
- `btnSearch` **`disabledIfFormIsInvalid:false`** -> always clickable (it GENERATES the file).
- email field: `required:true` + `regex` = email pattern; file-upload `readonly:true` for a
  download-only control.

## Type-matching across resources + Required inputs (LOAD-BEARING)

**Variable TYPES must match EXACTLY for anything that passes between Process / Document /
Form.** An input's type, an output's type, and a binding's type must be identical, or the
consumer rejects it. Real failure (AAT_ v2): Send Email "Map attachment" is `List<File>`, so
Process 3's input was made `List<File>` — but the FORM sends a single `File`, so the form
**could not START the process** (a silent type mismatch between the form output and the
process input). Always check the chain: Form control type → process INPUT type → action
PARAMETER type → next resource. One mismatch anywhere breaks the hand-off.

**Bridge a single `T` → `List<T>` INSIDE the process** (do NOT change the upstream resource):
1. Keep the process INPUT as the single `T` (so it matches what the form/webhook sends).
2. Add a **Node** action: `return [<%0%>];` (Node returns RAW — no wrapper) bound to its
   **List Result** output → a `List<T>` process var. **Node REQUIRES `Timeout` > 0** (it
   defaults to `00:00:00`, which errors `value must be greater than 00:00:00`); set `Timeout: 60`.
3. Feed that `List<T>` var to the action (e.g. Send Email Map attachment ← briefFileList).
   (Use **Single Result** instead when the script returns a non-list value.)

**Required inputs block the start.** A process input marked `Required` that the trigger does
NOT supply prevents the process from starting at all. Ensure every Required input is provided
by the caller — the form button's inputMap, the webhook payload, or the run payload — or do
not mark it Required. Audit the form↔process input map against the process's Required vars.


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


### Validation: trust the designer's Process Errors (2026-07-06, corrected)
**A 2026-07-05 note wrongly dismissed the designer's Process Errors as stale phantoms. They are REAL
and block SAVE. Trust them.** There are two layers:
- **Runtime** — `POST /api/Projects/validate` (the only server validate endpoint): checks
  `parameters[]`, returns EMPTY when valid. Does NOT catch designer-layer problems — a flow can pass
  it yet be unsavable.
- **Designer** — the client-side "Process Errors" panel blocks SAVE; it validates `customData`
  (designer maps + code chips). No server endpoint exists for it.
- **Replicate the designer check offline with `procesio flow-lint --id <flow> --workspace-id <ws>`**
  (a Node binding an error-scope/undeclared variable in code; a required subprocess input left
  unmapped or with a dead source in the `customData` process-inputs map). Never call a flow "done"
  on `/validate` alone — always run flow-lint too, and if you can, confirm SAVE in the designer.
- **The recurring cause:** cloning a subprocess-call node copies its `customData` process-inputs, so
  the clone keeps the SOURCE's subprocess-input ids and the real required input reads as "missing"
  (the panel shows the stale ids as raw GUIDs). Fix: regenerate `customData` process-inputs from the
  correct runtime map. Never bind an `isError` variable (an action's error-port output) into Node code.

### How to actually find a designer validation error (2026-07-06)
When the designer's "Process Errors" flags a node but the data "looks correct", DON'T reverse-engineer
the rule from that one node (I guessed wrong twice). Instead COMPARE THREE THINGS: the FLAGGED node,
a HEALTHY node of the SAME actionTemplateName that the designer accepts, and the CLEAN template from
`GET /api/Actions?getFullAction=true`. The one field that differs between flagged and healthy is the
cause. That method found it in one shot: flagged subprocess nodes had a stale side-pannel setting id
(`1da555da`) vs the template's `5456caf0`; the designer couldn't find the mapping. Then encode the rule
into `procesio flow-lint` so it's caught mechanically next time — never call a flow done on
`/Projects/validate` alone.
