# PROCESIO build-and-test playbook (agent operating procedure)

How the PROCESIO agent works when it creates or edits any resource or use case. The
rule: a build is not done when it is created. It is done when it has been run,
validated, and verified against real behavior, the learnings captured, and the
defects fixed. Building without testing is not allowed.

This is agent behavior. Tool mechanics live in `tools/procesio/` - this playbook
points at them, it does not duplicate them.

---

## The loop (run on every build/edit)

1. **Frame** - state the outcome and KPI in one sentence, the scope, the
   constraints, the RACI. (best practices section 1)
2. **Design** - pick the approach; where it matters, weigh 2-3 with trade-offs.
   Apply best practices up front: modular, DTO contracts, idempotent, stateless,
   secrets in Credential Manager, centralized parameters.
3. **Build programmatically** - via the `procesio` tool DTO sub-tools. Create data
   models complete with all attributes up front (the runtime compiled-model cache
   will not see attributes added by a later edit - PHASE4-E2E learning 12).
4. **Self-test rigorously** - the checklist below. Non-negotiable.
5. **Capture learnings** - write every discovery to the right durable note (routing
   below). Compounding, not chat-only.
6. **Fix** - bugs, inefficiencies, UX gaps, and any suggestion surfaced. Structural
   defects get fixed in the builder/tool code, not just patched on the live
   resource, so a fresh session builds it correctly.
7. **Re-verify** - re-run the relevant checklist items on what changed.
8. **Document & handover** - SOP, trigger order, resource ids. (best practices 7)

## Definition of Done (outranks your own judgement)

Measured failure (a GPT-driven session, 2026-09-05): the agent said "verified / works
/ done" over and over on FALSE evidence - a PDF existed, a DTO field existed, a call
returned `ok:true` - while the cache never cached, the button never fired, and the
report was empty. Nine hours, thirty user turns, because the human was the only oracle.
Do not repeat it.

- **A build is done only when `verify --process-id <id> --run` returns a passing
  verdict** - not when you inspected it, not when a file was produced, not when the API
  accepted the write. `ok:true` proves *acceptance*, never *effect*. If `verify` cannot
  cover a step (forms/browser/E2E), it lists it in `manual_checks`; run those, do not
  wave them through.
- **Clarify before you build.** In the Frame step, ask the questions that pin scope and
  the load-bearing decisions first - the data source, and especially the **cache
  mechanism** (native Data Store vs SQL; a cache MUST be a real Data Store / SQL action,
  never a Call API dressed with a cache icon - `audit` now hard-fails that masquerade).
  A task you *could* finish without asking finishes better, with fewer wrong-path loops,
  when the spec is pinned up front.
- **A process is called from a form ONLY through a native `RUN_PROCESS` event**, never
  by injected JS. Verify the event is actually bound (`form-get-element-events`), not
  just that JS "should" trigger it.
- **Author processes through `process-create` / `process-edit`, never a raw
  `PUT /api/Projects`.** The builder sets validity and the designer-config correctly; a
  hand-authored flow JSON pushed via `request PUT /api/Projects` lands `isValid:false`
  and the process will not launch (and hand-setting `isValid:true` only lies about it -
  `verify --run` still fails because the flow itself is invalid). Build Data Store
  read/write nodes with the builder's `dsWhere`/`dsMap` config, not by guessing DTOs.
- **Fix the cause in the generic tool, never patch the use case in the repo.** If a
  capability is missing (e.g. the builder could not author a Data Store node), EXTEND
  the builder with tests - the way `process-create` gained native Data Store authoring -
  never drop a `patch_<usecase>.py` into `scripts/`. Use-case artefacts live in a
  scratch dir; the guard `tests/test_no_usecase_scripts.py` fails the build otherwise
  (CLAUDE.md Hard rules 5 + 10).

## Self-test checklist - what "tested" actually means

Each item names the tool and the verified mechanic. Do not skip a layer because the
one above passed.

**The agent enforces the automatable layers.** Run them instead of doing them by hand:
- `python scripts/run-agent.py procesio verify --process-id <id> [--run]` - validates
  the process (real PROCESIO validator), audits designer-vs-runtime parity, and with
  `--run` executes it and reads the real instance status. Returns a `verdict`
  (pass/warn/fail) and a `manual_checks` list of the steps it cannot run.
- `python scripts/run-agent.py procesio audit --process-id <id>` - static
  best-practice + correctness smells (action count, slow actions, error handling,
  inline secrets, parity).
- `python scripts/run-agent.py procesio checklist` - the full structured checklist.

`verify` cannot drive a real browser, so the forms/webhook/E2E steps below stay
manual - it names them in `manual_checks` precisely so they are not forgotten.

### A. Static validation (before running anything)
- Validate the process: `procesio` -> `POST /api/Projects/validate`.
- Test credentials: `POST /api/Credentials/test` (returns a real upstream body when
  the placement is right - PHASE4-E2E learnings 3-4).
- Test actions: `POST /api/Actions/test`.
- Designer-vs-runtime parity: every action's runtime `Parameters[]` must be mirrored
  into the designer `CustomData.configuration` or the designer shows "not
  configured" and Validate fails even when the process runs. The builder enforces
  this with a build audit; if you hand-edit a DTO, re-check it. Bespoke shapes
  (document-mapper, decisional-case) differ between runtime and designer - PHASE4-E2E
  "CRITICAL process-builder fix" + rounds 3 and 5.

### B. Run + instance verification
- Run synchronously: `run-process --synchronous`; read output vars under
  `result.variable`.
- Read the instance status, do not assume success: 50 = finished, 40 = ran with
  errors. Check per-action `errorMessage` via
  `GET /api/Projects/instances/{iid}/status?flowTemplateId={pid}` (PHASE4-E2E 6, 15).
- Webhook-launched runs are async (launch returns an empty 200) - then poll
  `GET /api/Projects/{id}/instances`.
- Download and open any generated file: `GET /api/File/download` with headers
  `uploadFilePath`, `variableId`, `instanceId`, `flowTemplateId`.

### C. Forms - render AND behavior, with diagnostics (MANDATORY before "done")
A form is NOT done until EVERY tab, EVERY control, and EVERY event/action has been
exercised live and the runtime diagnostics are clean. Screenshots alone are not enough
(they hide JS errors, failed launches, flicker). Steps:

1. **Publish + URL:** publish, create a CustomUrl (`POST /api/CustomUrl/FormTemplate`),
   open `https://forms.procesio.app/{tinyUrl}`. SPA needs ~15-20s to render; `wait`.
2. **Drive every control/action with the `web` tool** (`run` steps: click tabs, `fill`
   inputs, click buttons, open selects/dropdowns/side-panels, click menu items). The
   CURRENT ui-builder forms (forms.procesio.app, pds/BootstrapVue design system) WORK
   HEADLESS - verified 2026-06-29: `fill` updates the value, `RUN_JAVASCRIPT` form JS
   fires, `RUN_PROCESS` triggers flow end-to-end (output mapped back into the field).
   (The old "headless can't test forms / Angular model" caveat applied to the legacy
   engine; it is superseded for these forms.)
3. **Read `diagnostics` from the web-tool result** (added 2026-06-29). It returns
   `{console, page_errors, failed_requests, bad_responses}`. **A build with any
   page_error, any console error, or any 4xx/5xx on the form's OWN calls is NOT done** -
   that is how a real failure shows (e.g. the RUN_PROCESS launch 400, a JS exception,
   the icon-font break). Fix, re-run, confirm clean.
4. **Assert the expected EFFECT per capability**, not just "it rendered": typed value
   reflected, computed/JS output appears, dropdown opens un-clipped, process result
   fills the target field, side-panel content shows, no flicker/scroll-trap.
5. **Test the NEGATIVE / dismiss path of every stateful interaction**, not just the happy
   click: open a dropdown/menu then **click OUTSIDE** it → only the menu should close,
   nothing else should fire (a form-level click handler that substring-matches a menu label
   up the ancestor chain will clear/trigger on outside-click — match exactly ONE label; see
   form `description.md`). For a **chat reply via a process**, send a message and confirm a
   bot reply renders (wire `messagesent`, NOT `messagesfetch`; produce the array with a
   **Node** action `return …`→`List Result`, not JS `setOutput` which wraps `{result}`).
- **Process triggers:** RUN_PROCESS in/out maps must put the PROCESS variable GUID on
  the LEFT (resolved from name->id) and the form value-path on the RIGHT, in BOTH maps;
  a name or a form-path on the left = the designer can't render it / launch 400s
  (2026-06-29). The builder resolves this (prepare_ctx); guarded by `test_form_parity.py`.
- Form data model: the field-value path is `root.<fields-const>.<elementId>.
  <valueConfigId>`, attr ids must equal the element config ids, and the dataModel
  root id must equal the form handle variable id - else the designer shows "Unknown"
  and values do not flow. The builder handles this; verify after any manual change.
- **Structural parity is auto-tested:** `pytest tools/procesio/tests/test_form_parity.py`
  (+ `test_form_sync`) assert the builder's DTO matches real exports. Run before shipping.
- **CSS/JS gotcha:** form CSS/JS lives in encrypted `Data.code`; never force a font on
  `#app *` (breaks Material-Icons glyphs); the form JS runs in `iframe.trigger-sandbox`
  (use `window.parent.document`). See `tools/procesio/dto/form/FORM-STYLING-NOTES.md`.
- **Theme + alignment (new):** if the form uses dark mode, toggle it and confirm the
  16-var palette applies; if it uses element alignment, confirm the `--fd/--jc/--ai`
  vars lay the container out — both only in a REAL browser (`form-theme-render`).
- **Data Store trigger (new):** a `RUN_DATA_STORE_OPERATION` control must run its
  READ/ADD/UPDATE/DELETE against the store and map the result back
  (`form-datastore-trigger`). See the `datastore` guidance topic.

### C2. Data Store (standalone)
- Round-trip a store: add → filtered read → update-by-PK → delete, asserting
  `affectedRows` and that the filtered read returns exactly the expected rows
  (`datastore-roundtrip`). Rows are keyed by column DISPLAY name; reads go through
  `POST …/rows/filter`. Full guidance: the `datastore` topic.

### C3. Scheduling
- Preview any crontab with `validate-crontab` before creating the schedule, then
  `get-schedule` to confirm the stored recurrence (`schedule-cron`). See the
  `scheduling` topic.

### D. Webhooks
- Trigger the webhook with a real payload; confirm an async instance launches and
  reaches status 50. The webhook body binds as a WHOLE to a model-typed variable
  (not per-field) - bind it to a primitive and you get raw JSON (PHASE4-E2E 1).

### E. End-to-end
- Exercise the use case as a user would: form -> process(es) -> document/email/SQL ->
  external system. Verify the real artifact: open the file, confirm the email
  delivered, confirm the record in the system of record.
- Idempotency: trigger twice, confirm no duplicate side effects (best practices 2).
- Timing: check against the forms UX rules (best practices 9) and the
  optimize-for-speed rules (best practices 10 - action count, ~10ms each).

## Implement the learnings (this is where it compounds)

Testing that does not change the build is wasted. After each test pass:

- **Fix every defect found.** Bugs; inefficiencies (too many actions, slow SQL,
  unscoped loading screens, an avoidable process call from a form); UX gaps; and any
  improvement you spotted. Address it, do not just note it.
- **Structural/tool defects go into the builder code + a regression test**, not only
  the live resource. PHASE4-E2E is the proof of this discipline: every fix landed in
  the builder so a fresh session's create/edit is already correct, backed by tests.
- **Platform limits you cannot fix** get documented so the next build avoids them
  (e.g. JS output is always `{result:v}` and will not fill a typed model - use the
  HTML-string shell pattern; PHASE4-E2E rounds 4 and 8-10).
- **Route the learning:**
  - tool / platform API / DTO quirk / builder behavior -> `tools/procesio/*-NOTES.md`
    (or the relevant tool folder).
  - methodology / how to build well -> this folder (`agents/procesio/`).
  - cross-cutting standing preference -> user memory.


## Tools the agent drives

The registry is the source of truth - `python scripts/list-tools.py`, never a
hardcoded list. Core for building in PROCESIO:
- `procesio` - create/edit resources, validate, run, read instances.
- `web` - real-browser form render + behavior testing, screenshots, UX timing.

## Read these (do not duplicate)

- Tool mechanics + verified gotchas: `tools/procesio/PHASE4-E2E-NOTES.md`,
  `PROCESIO-API-NOTES.md`, `PROCESIO-AUTH-NOTES.md`, `DTO-SUBTOOLS-NOTE.md`,
  `PROCESIO-SEND-EMAIL-NOTES.md`.
- Standards the build must meet: `PROCESIO-BEST-PRACTICES.md` (this folder).
