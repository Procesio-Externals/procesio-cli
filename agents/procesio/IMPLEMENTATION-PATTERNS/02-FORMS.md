# Form patterns: generalized techniques (PROCESIO forms ↔ processes)

These patterns were distilled from a production multi-step form workspace. Only reusable mechanics
are kept here: no client, id or business value. Each pattern says how it relates to
`tools/procesio/FORM-DEV-GUIDE/`: **NEW** (not covered), **REFINES** (adds to or corrects a
section) or **CONFIRMS+** (covered, plus a field-tested detail).

---

## P1. Hidden status field as a JS → no-code bridge — NEW
- **Problem.** Validation logic lives in JavaScript, but the reaction (show a button, lock fields,
  reveal a step) is easiest to express as MAP_FORM_DATA conditions. A JS block cannot stop or steer
  the rest of an event chain.
- **Mechanics.** Add a number-input per step (`validation-of-<step>`) and hide it with CSS
  (`display:none` on the control and, through `:has()`, on its wrapper). The JS block, placed before
  the MAP blocks in the same click chain, computes pass or fail and writes `"1"` / `"0"` using the
  **native value setter** (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input, v)`)
  followed by `input`, `change` and `blur` events. The native setter plus events is what makes Vue's
  `v-model` take the value. The next events are `MAP_FORM_DATA when validation-of-<step>.value EQUALS 1`
  (success actions) and `EQUALS 0` (failure actions).
- **When.** Any rule too complex for MAP conditions (regex sets, cross-field rules, repeated rows)
  whose outcome should drive no-code visibility or locking.
- **Pitfalls.**
  - **A MAP in the SAME chain as the JS never sees the flag it just wrote** (verified live): input
    values reach the model after a 500 ms debounce, so the first click always reads the old value
    and users learn to click twice. Read the flag from a LATER chain, through the trigger field of
    P2 (FORM-DEV-GUIDE 04 §16), never from the button's own chain.
  - The field must be *rendered* for JS to find it, so hide it with CSS, not `visible=false` (a
    hidden element is not in the DOM).
  - Also re-check silently on later edits and reset the flag to 0, or a user can pass, edit and still
    confirm.
  - Make a "Modify" action reset the flag through MAP as well.

## P2. Forward-only step unlocking: one-click Validate + Modify — NEW (supersedes the triad)
- **Current form (build new steps this way).** One **Validate** button per step. Its chain runs the
  validator, then asks a global runtime to write the button's branch into a hidden
  `step-flow-branch` field and increment a hidden `step-flow-trigger` field. That field's own
  `onInput` chain holds one MAP per step and branch on `flag == 1 AND branch == <its branch>`:
  lock the step, hide Validate, show **Modify**, reveal the next step. Its last JS block clicks
  Next. The branch comes from the clicked button, never from a Boolean form variable (P3). **Modify**
  unlocks the step, resets its flag, hides every later step and resets them to their first-pass
  state. Measured at about 0.8 s from click to the next step. Recipe, rules and the renderer facts
  behind it: FORM-DEV-GUIDE 04 §16. Wiring: `procesio form-set-element-chains`.
- **Legacy form (what production forms were built with).** The triad below needs three clicks per
  step (validate twice because of the P1 pitfall, then confirm). Migrate it rather than copy it.
- **Problem.** The native stepper lets users move freely, and a step's data should be final before
  the next step unlocks.
- **Mechanics (legacy triad).**
  - Every step after the first is `visible=false` in the designer.
  - Each step ends with three buttons: **Validate** (visible), **Modify** and **Confirm** (hidden).
  - When Validate passes (P1): MAP sets `disabled=true` on every field of the step and shows Modify
    and Confirm.
  - Modify: re-enables the fields, resets the flag, hides Confirm.
  - Confirm: `MAP set <next-step>.visible = true`, then a JS block clicks the stepper's own Next
    (`.form-builder--stepper--buttons--next button`).
  - The first step can be unlocked by a process instead (for example a "compute allowed date range"
    process returns `e_ok` → `<step>.visible`).
- **When.** Long regulated forms: KYC, contracts, onboarding.
- **Pitfalls.**
  - The lock and unlock field lists are hand-maintained in two MAP blocks. Generate or diff them,
    because copy-paste slips (a field locked twice, another never locked, Modify hiding the wrong
    button) are the typical bug.
  - The programmatic Next still passes through any capture-phase Next guard (P6), which is
    intentional.

## P3. Server-side "render" process drives visibility and options — NEW
- **Problem.** Which blocks, selects and validate buttons appear depends on a few configuration
  choices (applicant type × product type × date), and option lists are master data.
- **Mechanics.** One process takes the configuration selects and returns primitive Booleans
  (`isA`, `isB`…) plus JSON option lists. The outputMap fans **one Boolean out to many targets**:
  a form variable (for later conditions), `visible` of each block, and `visible` of that branch's
  Validate button. Each option list goes to a select's `sourceValue`, and one list can feed several
  selects.
- **When.** More than two or three configuration axes, or options that must stay in sync with a DB.
- **Pitfalls.**
  - **Never test these Boolean variables with `IS_TRUE` / `IS_FALSE`.** The designer default is the
    TEXT "False"/"false", and a condition reads any non-empty text as true (measured live). Until
    the process result lands, every `isX IS_TRUE` passes, so exclusive branches all run. Give the
    variables a `null` default, or branch with `EQUALS` on the source select. `formlint` flags it.
  - If later events in the **same** chain read the form variables this process writes, the process
    must be `syncRun:true`, or they read the previous values (see P13).
  - Feed downstream processes from the source selects, not from the derived variables.

## P4. Outcome flag pair (`e_ok` / `e_not_ok`) → screen swap — NEW
- **Problem.** Show a result screen or keep the input screen after an action, without JS.
- **Mechanics.** Every action process declares two Boolean outputs, `e_ok` (default **false**) and
  `e_not_ok` (default **true**), and sets them at the end. The outputMap writes `e_ok` → `visible` of
  the success section and `e_not_ok` → `visible` of the input section or stepper (or of a "retry"
  button).
- **When.** Any submit, accept or deny, or sign action.
- **Pitfalls.**
  - Keep the defaults pessimistic. A process that stops early then leaves the form on the input
    screen instead of showing a false success.
  - Keep one spelling across the workspace (`e_not_ok`, not `e_noOk` / `e_notOk`), or outputMaps
    silently target nothing.
  - Never map a Boolean into a file or value slot.

## P5. Cross-step value store read from the Vue model — REFINES 02 §7 / 04 §1
- **Problem.** The renderer destroys other steps' controls (`v-if`), so client-side validation or a
  semantic payload spanning steps cannot read their DOM. `ProcesioForm.data.fields` is incomplete
  for some props (08 "info-text").
- **Mechanics.** Walk the Vue 3 vnode tree from every element carrying `_vnode`
  (`vnode.component` → `component.subTree` → `children`, depth-capped). For each component with
  `props.modelValue`, match it to a field wrapper by DOM containment (`wrap === el ||
  wrap.contains(el)`). For each id in an explicit `FIELD_IDS` list, store the model value when the
  field is rendered (even when it is empty, since the model is the truth) and keep the last known
  value when it is not. Fall back to the DOM value (`checked` for checkboxes). Refresh on a debounced
  capture listener (`input/change/click/focusout`) and on every `get()`. Expose
  `get()/json()/values` on `window.parent`.
- **When.** Multi-step forms whose validation or payload needs values from earlier steps.
- **Pitfalls.**
  - `FIELD_IDS` must be the **union** of all steps and **identical** wherever the script is attached.
    With two copies at the same version and different lists, the first installed wins and later
    fields are never collected.
  - Dynamic-table rows repeat ids, so read them separately (P9).
  - Internals (`_vnode`, `modelValue`) are undocumented. Guard every access.

## P6. Rules-table client validator with step scoping and a Next click-guard — CONFIRMS+ 04 §7 / §15
- **Mechanics.**
  - `RULES = { <fieldId>: {required, regex, regexMessage, when(values), optional, date, stripSpaces} }`.
  - Only fields **currently rendered** are validated, which scopes validation per step for free.
  - `when` handles conditional branches (for example document type A vs B).
  - `optional` means "validate the format only if filled". `date:true` means "any parseable date".
    Date values arrive as ISO, display text or Date objects depending on the read path, so a strict
    ISO regex gives false negatives.
  - `stripSpaces` suits bank or ID numbers typed in groups.
  - Treat arrays, selector option objects (`{label/value}`) and file objects (`{id,name}`) as filled
    when they have content. A naive `String(value)` check marks them empty.
  - Errors render under the field, scroll to the first one and clear on edit (only for fields
    already in error, so the user is not scolded at the first keystroke).
  - A document **capture** click listener on the stepper's Next blocks navigation on failure and
    hides any loader.
  - Also expose semantic payload builders whose keys equal the ones the process-side code expects,
    so the client and server share one vocabulary.
- **Pitfalls.**
  - Port the regexes from the server-side validation and keep them in sync.
  - See P12 for versioning.

## P7. Global branded loader API bracketing every process chain — REFINES 05 §5
- **Problem.** Async processes give no feedback, and chains mix JS, process and MAP events.
- **Mechanics.**
  - Form-level JS defines `window.parent.__<name>Loader = {show(text,{unsafe,timeout,timeoutMessage}), hide()}`.
    The overlay and style are injected once by id into the parent document.
  - Every chain that triggers a process is bracketed: first event `RUN_JAVASCRIPT show('<message>')`,
    last event `RUN_JAVASCRIPT hide()`, or the navigation block that hides in `finally`.
  - An optional `unsafe` timeout switches the overlay to a warning state and auto-closes it.
- **When.** Any form whose processes take over a second.
- **Pitfalls.**
  - `hide()` at the end of a chain whose processes are **async** fires before the result arrives,
    so the loader only covers the launch. Use `syncRun:true` when the loader must cover the work.
  - Every guard that blocks a click must also call `hide()`, or the veil stays up (08 "loader never
    lifts").
  - The element-script `try/catch` around `window.parent.__loader` keeps forms without the loader
    working.

## P8. Programmatic Next + multi-point scroll reset — REFINES 04 §14
- **Mechanics.**
  - Click the stepper's own Next button instead of changing the step index.
  - Then reset scroll on every candidate (parent window, `top`, `document.scrollingElement`, and any
    element with `scrollTop>0 && scrollHeight>clientHeight`) at several delays (≈100/400/900 ms)
    to catch the async re-render.
  - **Skip** the reset when a validation error element exists, because the validator has already
    scrolled to the error.
- **Pitfalls.** The frame hierarchy decides which element scrolls, which is why every candidate is
  reset.

## P9. Repeated-id rows: pick the visible instance, iterate rows by cell order — CONFIRMS+ 04 §15
- **Mechanics.** Dynamic-table rows repeat the child's DOM id. Use `querySelectorAll('[id="x"]')`
  and keep the instance with `offsetParent!==null || offsetWidth>0`. For per-row work, find the
  enclosing `tr` / `[role=row]` and read the cells in `tableColumnsSourceValue` order. Fall back to
  row text plus regex when the cell count does not match.
- **Pitfalls.** Keep row inputs out of the scalar collector and validate them per row instance.

## P10. Whole-form object → declarative SPEC mapper Node — NEW
- **Problem.** A final submit needs ~150 fields reshaped into a semantic JSON. Mapping each field to
  a process input is unmaintainable.
- **Mechanics.**
  - Map the special source `form` into one JSON process input. It carries `fields.<ElementName>…`
    plus `instance.*` / `flow.*`.
  - A reusable subprocess Node holds a SPEC: target keys mapped to source strings like
    `"Input2.value"` or `"FileUpload1.value.id"`, with annotations after " =" or " (" ignored.
  - Directives handle the irregular cases: an array from table rows, "first available of A|B",
    "value of the active sub-select chosen by another select".
  - A guarded fallback (`SelectN` ↔ `InputN`) is used **only when the source is missing**, and every
    use is reported in `warnings`.
  - Dates are normalized. A `SCRIPT_VERSION` marker is emitted in the output so the running version
    is visible in instance data.
- **When.** Any large form submit, and any process shared by several variants of the same form.
- **Pitfalls.**
  - Field keys are element **names**, so a duplicate name silently collides.
  - Names can be re-derived in lower case after a designer save (see `PROCESIO-API-NOTES.md`), so
    resolve case-insensitively.
  - Files needed as `File` inputs should still be mapped explicitly.

## P11. Process-built HTML into a paragraph label — NEW
- **Mechanics.** A Node builds a self-contained, **inline-styled** HTML string (counts, percentage
  bars, inline SVG icons) and returns it as a String output mapped to a paragraph's `label`. Static
  decoration (separators, section cards, footers) uses the same trick directly in designer labels.
- **When.** Read-only dashboards, extraction summaries and status cards, with no JS needed.
- **Pitfalls.**
  - Only inline styles are reliable, because the page CSS may not target injected markup (08 "A
    `<div>` written into a paragraph…").
  - Escape any user or DB text you interpolate, since the label is rendered as HTML.

## P12. Versioned idempotent installers for element-event scripts — REFINES 02 §4–5
- **Mechanics.**
  - Each shared script family installs itself on `window.parent.__<family>` with a numeric `v`.
  - The guard is "install if missing or `v` differs". It runs its action on every execution: install
    once, act every click.
  - Iron rule: guard version == exported version, and one file identical everywhere it is attached.
- **Pitfalls (observed).**
  - If different buttons carry **different versions**, every step reinstalls. The old document
    listeners are never removed, so N runtimes then run per click and keystroke.
  - Header comments drift from the runtime `v`.
  - A shared style tag guarded by one id keeps the **first** version's CSS.
  - Prefer the form-level injected-runtime pattern (02 §4), or at minimum keep one canonical file and
    diff all attachments before publishing.
  - Listeners created in the sandbox realm are more fragile than an injected `<script>` in the
    parent.

## P13. Async RUN_PROCESS: outputs do land, but the chain does not wait — REFINES 06 §1 / 08 "outputMap populates nothing"
- **Observation.** Production forms here map dozens of outputs from `syncRun:false` events (71 async
  events against 12 sync) and depend on them for visibility and tables. This matches
  `PROCESIO-API-NOTES.md`: async outputs **arrive later**. It contradicts the guide's "fire and
  forget, outputMap can never populate" and should be re-verified live.
- **Rule.** Async is fine when the outputs only paint the UI. Use `syncRun:true` whenever a **later
  event in the same chain** (MAP condition, JS, another process's inputMap) reads those outputs, or
  when a loader or Next must wait for them.
- **Pitfall.** Several async processes on one click (status change + notify + refresh) have no
  ordering guarantee. Chain them inside one process instead.

## P14. File outputs: `src` to preview, upload `value` to download or carry — NEW
- **Mechanics.** Map a generated or fetched File output to a file-viewer's `src` (preview) **and** to
  a file-upload's `value`. The upload then acts as a download link or holds the file so a later
  event can pass it on as a File input. For uploads, pair the extraction process with a
  "convert to PDF" process on the same trigger so the preview works for photos too.
- **Pitfalls.** Keep outputMap targets pointed at existing elements. A deleted viewer leaves a raw
  path target that fails silently.

## P15. Row object as process input (master/detail) with an explicit reset — NEW
- **Mechanics.**
  - A button inside a dynamic row maps `DynamicRowN.$.item` (the whole row object) into a JSON or
    typed process input.
  - The detail process returns files and flags. A MAP swaps the list section for the detail section
    and copies the row into a form variable for later actions.
  - A "back" button re-loads the list and runs **one MAP that clears every field, viewer and
    visibility the detail view set**.
- **Pitfalls.**
  - Ship only the columns needed. Whole DB rows in a table reach the browser.
  - Conditions on detail outputs need `syncRun:true` (P13).

## P16. Identity gate via FORM_LOAD → exclusive sections — NEW (with a security caveat)
- **Mechanics.** FORM_LOAD passes `instance.currentUser.email/name` to a process that returns
  mutually exclusive Booleans (anonymous / known-but-unregistered / pending / approved), mapped to
  `visible` of four sections (or of the stepper).
- **Pitfall (critical).** `visible` is presentation, not authorization. Any data-loading process on
  the same FORM_LOAD still runs and ships its outputs to the browser. Load protected data only in a
  process that re-checks the current user itself and returns nothing otherwise.
  - A condition does not fix that either. `when isConfirmed IS_TRUE` on the data-loading event is
    evaluated on the variable's default, the TEXT "false", which a condition reads as true (measured
    live, P3). The load therefore runs for every visitor, and a correct condition would still be only
    a browser-side check.

## P17. CSS by attribute-id families — NEW
- **Mechanics.** Style with `[id="…"]` and prefix families (`[id^="separator"]`,
  `[id^="button-header-"]`) inside `:is()`. Class-level specificity is kept, and decorative elements
  intentionally share ids so a new one inherits its styling. Hide helper fields on the control and
  on its wrapper through `:has(> …)` / `:has(> * > …)` so no empty row remains. Every rule is
  `!important` against the builder's styles.
- **Pitfalls.**
  - Duplicate **ids** are fine for decoration only. Keep element **names** unique.
  - Never reuse a decorative id prefix for a field.

## P18. Process-computed input constraints — NEW
- **Mechanics.** A load-time or click-time process returns `start_date`, `end_date`, `error` and
  `e_not_ok`, mapped to a datetime input's `minValue`, `maxValue`, `defaultValue` and `readonly`,
  and to an error paragraph `label`. Business calendars stay server-side.

## P19. Public token-addressed signing form — NEW
- **Mechanics.** An email link opens a public form with the token prefilled into an input inside a
  hidden section. FORM_LOAD verifies the token and returns the documents to viewers plus `e_ok` →
  section visible. The signature-pad value (a File) plus the token go to a signing process, and a
  flag pair swaps to a thank-you section.
- **Pitfalls.**
  - The token is attacker-controlled. Never interpolate it into SQL: use parameters or validate the
    format.
  - Make tokens single-use and expiring.
