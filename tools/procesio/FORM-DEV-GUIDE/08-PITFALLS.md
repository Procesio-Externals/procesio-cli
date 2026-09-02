# 08 — Pitfalls: symptom → cause → rule

Every one of these was found by breaking something real. Scan the **symptom**
column first; that is how you will meet them.

---

## Runtime / JavaScript

### The code works on first load, then stops
**Cause.** Listeners and observers were declared in the form-level JS scope. That
scope is a throwaway sandbox iframe, destroyed and rebuilt on every re-trigger.
**Rule.** Anything that must outlive one run is injected once into
`window.parent.document`. Installer + runtime, two layers, two guards
([02](02-CODE-INJECTION.md) §4).

### Doubled toasts / doubled ripples / the process launches twice
**Cause.** The file re-ran and installed a second copy of everything.
**Rule.** Guard the installer on a DOM id **and** the payload on a `window` flag.
Every DOM-touching function marks its work with a `data-*` attribute or an injected
child, and returns early if the mark is there.

### `querySelector` finds nothing, but the element is clearly on screen
**Cause.** You are querying the sandbox iframe's `document`, not the page's.
**Rule.** The runtime lives in the parent document; inside it, `document` is
correct. From the installer scope it is not.

### Something is processed on first render and never again
**Cause.** Processed nodes were remembered in a `Set`. The renderer destroyed them
and made new ones; the set is full of corpses.
**Rule.** Never track nodes across a rebuild. Mark the node itself, and recompute
everything from the current DOM on every pass.

### `refresh()` runs dozens of times per frame during a step change
**Cause.** The MutationObserver fires per mutation; a step change makes dozens.
**Rule.** Coalesce with a `pending` flag + `requestAnimationFrame`.

### An attribute rewrite feeds your own MutationObserver in a loop
**Cause.** Writing the attribute unconditionally on every pass.
**Rule.** Compare before writing: `if (next !== current) { set(next); }`.

---

## Visibility and state

### An entire step renders completely blank
**Cause.** A class that sets `opacity: 0` was removed only in response to an
observed DOM mutation — and that mutation did not arrive (or the observer's target
had been replaced). Measured: `at200 opacity=0.002 → at1500 opacity=0`, never
lifting.
**Rule.** **A visual state must never depend on an event that may not come.** Lift
it on a timer. Clear it by sweeping `all('.leaving')` rather than a held node
reference, because the renderer may have swapped the container.

### The loader veil never lifts and the form is unusable
**Cause.** Dismissal was tied to a network call that failed or a quiet-timer that
never settled.
**Rule.** Every veil has a **hard ceiling** in both modes, and when the ceiling
fires the user is told what to do instead ([05](05-STEPPER-AND-MOTION.md) §5).

### The next button can never be reached
**Cause.** Readiness counted hidden fields. A field that is gated can never be
filled, so the gate never opens.
**Rule.** Only `el.offsetParent !== null` fields count toward readiness.

### A field is invisible but Tab still lands in it
**Cause.** Hidden with `visibility: hidden` or `opacity: 0`.
**Rule.** `display: none !important`. A control you can reach but cannot see is a
worse bug than a visible one.

### Hiding a button leaves an empty row
**Cause.** The button was hidden, not its element wrapper.
**Rule.** Hide `b.closest('.form-builder--element')`.

### Buttons belonging to a later view are visible on a fresh load
**Cause.** The form's own logic hides them inside a click handler that has never run.
**Rule.** Gate on an observable phase, e.g. "the stepper is on screen".

---

## Values and Vue

### Writing `info-text` from the field model does nothing at all
**Cause.** The runtime renders `info-text` from the element's STATIC config array, not
from the reactive field object. `ProcesioForm.data.fields.<name>` exposes only `value`,
`visible`, `required` and `readonly`, so assigning `infoText` is a silent no-op, and no
`setConfigValue`-style API is exposed to form JS.
**Rule.** Drive live text — counters, running totals, quota hints — by writing the DOM
node. Note that when `info-text` is empty the message component is never rendered at all
(`v-if` on a truthy value), so there is no node to write into: either set a non-empty
`info-text` in the designer, or create the node yourself.
See [`../dto/form/description.md`](../dto/form/description.md) for the selector details —
the control's DOM `id` equals its `name` config and sits on the `.pds-c-input-group`
wrapper, not on the `<input>`.

### A field looks filled and submits empty
**Cause.** `input.value` / `input.checked` was set directly. The renderer is
Vue-bound and never saw it.
**Rule.** Click the real control. If you must write, dispatch `input` **and**
`change` with `bubbles: true`.

### Clearing a radio group immediately re-selects the same option
**Cause.** A `change` event was re-dispatched after clearing. The Vue handler reads
the option's value and re-selects it.
**Rule.** Clear the model (`window.ProcesioForm.data.fields`, guarded) and the DOM
state, and dispatch nothing.

### Every field-matching function silently returns null, on every field
**Cause.** The form's inputs carry an **empty `label` config** — their visible label
is a separate `paragraph` element sitting above each one, which is a common way to
build a form whose labels need styling the control does not offer. The label-matching
handle then has nothing to match on: `.pds-c-input-group--label` is absent and the
control's own `textContent` is empty (a placeholder is an attribute, not text). Found
on a live form where an entire step's gating had never once executed, with no error
anywhere and no visible symptom other than the feature simply not happening.
**Rule.** Before building anything on label matching, **check that the labels exist**
— one `querySelectorAll('.pds-c-input-group--label')` on the rendered form answers it.
When they do not, fall back to an **element-id → field-name map generated from the
DTO**, say in a comment where it came from and how to regenerate it, and keep the rest
of the code speaking names. Ids are the weaker handle, but a weak handle that resolves
beats a strong one that returns null.

### A feature "does nothing" and no error is ever logged
**Cause.** A lookup returned null and every caller guarded it with `if (!key) return;`.
Defensive early-returns turn a wiring failure into silence.
**Rule.** When a mapping function can legitimately return null for SOME nodes, assert
that it resolves for **at least one** — a `console.warn` when a whole pass resolves
zero fields would have caught the above on first load.

### The wrong field gets a value / a label match hits the wrong control
**Cause.** A substring label match, ordered shortest-first. `'id — series'` matches
inside `'id representative — series'`.
**Rule.** Order the label table **most specific first**, and normalize diacritics
and case on both sides of every comparison.

---

## Mapping and processes

### `[object Object]` lands in every field
**Cause.** A structured variable was mapped as a whole, or the row's `path`
attribute chain was dropped during a rewrite. The form side's path shape is typed
`any` in the renderer — it is **not derivable** and cannot be guessed correctly.
**Rule.** Eliminate paths: one process output variable per field, all primitives,
split by small Node actions ([06](06-PROCESS-INTEGRATION.md) §4).

### The designer shows raw guids and the launch 400s
**Cause.** A variable **name** on the left of a map row. The API accepts it.
**Rule.** The process-variable GUID goes on the left, always. Let
`form-set-element-event` resolve names — it fails before writing if one is unknown.

### The designer cannot render a mapping row you wrote via the API
**Cause.** The sides were written as bare strings.
**Rule.** Each side is an object: `{value, isList, path}`, with `path: {}` on the
process side and `path: null` on the form side.

### The process runs but the outputMap populates nothing
**Cause.** `syncRun: false` — the form fired and forgot.
**Rule.** `syncRun: true`. Verified to hold the line open across a multi-second
external call.

### The process launches twice per interaction
**Cause.** Two `RUN_PROCESS` events on the same trigger.
**Rule.** One event per trigger; rewire with `--replace`.

### A Node action is rejected at save time
**Cause.** `Timeout` outside 60–300, or a superseded action (`Call API v3`).
**Rule.** `Timeout` 60–300; use `Call API` with `Response Status` / `Response Body`
/ `Time Out`. Remember `Node` returns raw while `Javascript` wraps as `{result: v}`.

### Fields come back empty but the call succeeded (status 200, valid body)
**Cause.** Extraction quality — the model returned mostly nulls for a partially
legible document. Not a wiring failure.
**Rule.** Carry a `warning_status` / `warning_message` pair out of the process so
the form can tell the two apart, and never throw inside a parse Node — return a
diagnosable object.

### A file variable is rejected
**Cause.** `file` is not a type.
**Rule.** Use the `FileDataModel` model.

---

## CSS

### The page will not scroll; the bottom of the form is unreachable
**Cause.** `overflow: hidden` on `.form-builder--form`.
**Rule.** Never. Clip with a **background** instead — backgrounds honour
`border-radius` for free.

### The pinned footer lands on top of the content
**Cause.** A `transform` on `.form-builder--form` made the card the containing block
for `position: fixed` descendants.
**Rule.** Animate the card's `opacity` only. No `transform`, `filter`,
`perspective`, or `will-change: transform` on the card.

### An animated gradient bar vanishes after the first cycle
**Cause.** `background-repeat: no-repeat` while animating `background-position` —
the gradient simply slid away.
**Rule.** `repeat-x`, gradient starting and ending on the same colour, travel
exactly one tile per cycle.

### A CSS rule has no effect on the form's own markup
**Cause.** The form author wrote an inline `style` attribute; an inline declaration
beats a stylesheet one.
**Rule.** `!important`, and target it with `[style*="border-left"]`-style attribute
selectors when the structure is unknown.

### A `<div>` written into a paragraph is not where the CSS expects it
**Cause.** `Paragraph.component.vue` renders `<p v-html="sanitizeHtml(...)">`, and the
HTML parser cannot nest a `<div>` inside a `<p>` — the block is hoisted out and lands
as a SIBLING of an now-empty `<p>`. Selectors written against `p > .my-block` match
nothing, and the wrapper is `display: flex`, so the hoisted block becomes a flex ITEM
sized to its content: a centred block sits off to one side of the column it should fill.
**Rule.** Style the wrapper's children, not the `<p>`:
`.form-builder--paragraph { align-items: stretch } .form-builder--paragraph > * { flex: 1 1 auto; min-width: 0 }`.
DOMPurify's defaults keep `class`, `style` and `data-*`, so authored paragraph HTML can
carry real classes — do that instead of inline styles, which only `!important` can
override later.

### An `<img>` icon will not take a colour
**Cause.** The colour is baked into the icon service URL; `color` does nothing and
`filter` only approximates.
**Rule.** Rewrite the URL's colour parameter.

### The loader's indicator is invisible on a long form
**Cause.** It was centred inside a card taller than the viewport, so it sits below
the fold.
**Rule.** `position: sticky; top: 40vh` on the inner block.

### A completed-field glow overhangs the next column
**Cause.** An outer `box-shadow`.
**Rule.** `inset`.

### The entrance stagger makes a long step take seconds to appear
**Cause.** An uncapped `nth-child` delay ramp.
**Rule.** Cap it: `nth-child(n+4) { animation-delay: 180ms; }`.

### A toast appears instantly with no transition
**Cause.** The class was added in the same frame as the insertion.
**Rule.** Add it inside `requestAnimationFrame`.

### The dropzone stays stuck in the drag state
**Cause.** `dragleave` fires on children; targeted removal missed.
**Rule.** On `dragleave`/`drop`, sweep **all** zones.

---

## Stepper

### A second, native stepper appears next to the custom one
**Cause.** The platform's nav renders as soon as the stepper's `steps` config names
the real step elements — which happens the next time the form is saved.
**Rule.** If you draw your own rail, hide theirs explicitly:
`.form-builder--stepper--nav { display: none !important; }`.

### The step indicator jumps to a wrong position (e.g. straight to 100%)
**Cause.** Step detection failed and the code guessed.
**Rule.** Return `-1` for unknown and **leave the indicator untouched**. Wrong
information is worse than a stale frame.

### Step detection breaks after a redesign
**Cause.** Matching on a design-system wrapper class.
**Rule.** Match on the visible banner text — that text is the form's own content.

### Custom step labels drift from the form's
**Cause.** A second, hand-maintained list.
**Rule.** Copy the labels off the platform's nav items before hiding it, and fall
back to the hard-coded list only if the counts disagree.

### A gated "next" button lets a fast clicker straight through
**Cause.** Two independent leaks, both measured on a replica:
1. the gate was a **class on the button**, and the renderer destroys and recreates the
   nav buttons on every step change — the class is gone by the next click;
2. a step change is **not synchronous**. Until the swap lands, `currentStep()` still
   reports the step you just left, so a burst of clicks each read "this step is fine"
   and each advances one step. Three clicks jumped from step 1 to step 4, past two
   ungated steps.
**Rule.** The class is presentation; **enforce in a capture-phase click listener on
the document**, recomputing the verdict at click time and calling `stopPropagation()`
so the platform's own handler never sees it. Add a short lock keyed on the step you
last advanced FROM, released when `currentStep()` actually changes.

### The gate can never be satisfied because the fields are hidden
**Cause.** A step hides its fields until some prerequisite (a document read, a lookup)
arrives, and readiness counts those hidden required fields. If the prerequisite fails,
the step is unreachable in both directions.
**Rule.** Whenever a step hides what it also requires, ship the **manual way out in the
same change** — an always-visible control that opens the fields — not a timeout. A
toast promising "you can fill these in by hand" over fields that are still hidden is
worse than no promise.

### The recompute loop stops the moment nobody is looking
**Cause.** `requestAnimationFrame` does not fire in a **backgrounded or hidden tab**,
and the recompute loop hangs entirely off it. Harmless for a person (nothing to see),
but it makes the form look frozen to any automated check — the page renders once and
never updates, with no error to find.
**Rule.** Know this before debugging a "form.js stopped working" in a headless or
side-panel browser. Give the local replica a switch (`?raf=timeout`) that swaps rAF for
a timer, and drive tests through that. Note that background tabs also throttle
`setTimeout` heavily, so allow generous waits before concluding anything is broken.

### The page scrolls itself on the very first render
**Cause.** `scrollIntoView` fired on the initial step assignment.
**Rule.** Only scroll when `lastStep > -1`.

---

## Deployment

### The form loses all its elements
**Cause.** `form-edit` (a desired-state editor) was used to change one thing.
**Rule.** Surgical actions only: `form-set-code`, `form-set-element-event`. Watch
the `elements` count in every write result.

### `len(None)` / a crash on a form that has never had code
**Cause.** `{"JAVASCRIPT": null, "CSS": null}` is the designer's **initial** state,
not a corrupt blob.
**Rule.** Normalize `null → ""` before any length or concatenation.

### Decryption fails and it is unclear whether the key or the blob is wrong
**Cause.** Both surface identically as a `UnicodeDecodeError`.
**Rule.** Round-trip `encrypt_code`/`decrypt_code` with a throwaway key. If that
works, the blob is fine and the key is wrong. Also check you are not confusing the
workspace API key with the form-code passphrase — both are short opaque tokens.

### A PUT starts failing for no visible reason
**Cause.** An unexpected extra field from the GET was echoed back, or camelCase was
sent where PascalCase is required.
**Rule.** Map the envelope explicitly (`_PUT_KEYS`), never spread the GET body.

### A fix on the process side breaks a branch that used to work
**Cause.** It was published straight to the live process.
**Rule.** Duplicate, change the copy, test the copy, promote. And when something
does break: revert fully and immediately, then re-approach.

---

## Silent DTO acceptance (the server takes it and says nothing)

These are accepted with a 2xx and no error, then cost a debugging session because
nothing points at them. `form-update` now emits non-blocking **lint** warnings for
the first three (see `tools/procesio/formlint.py`); the doctrine is in
`agents/procesio/PROCESIO-API-RELIABILITY-DOCTRINE.md`.

### An element saves fine but renders on NO tab / pane
**Symptom.** The element exists in the DTO and the PUT succeeds, but it appears on
no tab — invisible in the rendered form.
**Cause.** Its `parentId` references no element on the form (a phantom parent). Tab
and container membership is by `parentId` = a container element's id (§01-ANATOMY);
a dangling id is silently placed nowhere.
**Rule.** Point `parentId` at a real container/tab element id, or `null` for a
top-level element. (Lint: "phantom parent — renders on NO pane".)

### A form-update patch changes nothing, silently
**Symptom.** `form-update` returns applied, but the form is unchanged.
**Cause.** The `--data` patch was wrapped as `{"Data": {...}}` (or a top-level key
was mistyped). The deep-merge adds it as a NEW key inside `Data` — inert junk — and
never touches the field you meant. Deep-merge also REPLACES arrays wholesale and
sets `null` rather than deleting.
**Rule.** Pass the INNER fields directly: `--data '{"hideBranding": true}'`, not
`--data '{"Data": {"hideBranding": true}}'`. To change one item of an array, pass
the whole new array. (Lint: "wrapping mistake" / "not an existing Data field".)

### Two elements fight over selectors or process mapping
**Symptom.** CSS/JS targets the wrong element, or a process input maps from the
wrong field.
**Cause.** Two elements share the same `id` or `name` config value.
**Rule.** Keep every element's `id`/`name` config unique. (Lint: "N elements share
the same … config".)

### A multi-select maps a list into a single value
**Symptom.** A `multiple=true` select sends only one value (or a stringified list)
into a process.
**Cause.** Its `value` config / mapped data-model attribute is not marked `isList`.
**Rule.** Set `isList` on the value config / the data-model attribute for any
multiple-select. (Lint: "multiple-select … not marked isList".)

### Wiring one event on an element wipes the others
**Symptom.** After adding a click handler, a previously-working handler on the same
element is gone.
**Cause.** The write replaced ALL events on the trigger. An element commonly carries
`[RUN_PROCESS, RUN_JAVASCRIPT]` on one click trigger; a blanket replace discards
both.
**Rule.** Replace only the action you mean:
`form-set-element-event --replace-action RUN_PROCESS` keeps the sibling event in
order. Bare `--replace` now warns before discarding more than one; append (no flag)
to add alongside.
