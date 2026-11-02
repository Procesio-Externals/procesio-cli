# 08 - Pitfalls: symptom → cause → rule

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
observed DOM mutation - and that mutation did not arrive (or the observer's target
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

### The runtime cannot see what the form-load process was sent
**Cause.** The form-load RUN_PROCESS publishes before the `Data.code` runtime has installed
its XHR / fetch hook, so the request body (the inputs, for example the signed-in user's name
and e-mail from `instance.currentUser`) is never captured. The browser's resource-timing
buffer lets the runtime see that the call happened, never what it carried. Seen on a live
form: the greeting stayed without a name while the same code worked on a replica, where the
hook was in place first.
**Rule.** Read anything the runtime needs from a call the runtime itself triggers (a hidden
RUN_PROCESS button it clicks after installing), or have the process return it as an output.
Never depend on the body of a request that leaves before the runtime exists.

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

### The native form shows for about a second before any script runs
**Cause.** The renderer draws the form first and runs the form-load event about a
second later (measured: 1.0 s on a live form). Every script sits behind an event,
including the `Data.code` JavaScript, which the front end injects as a form event. So
no script, however small or early in the list, can hide anything from the first frame.
Setting `visible = false` from a load script is no faster, and it removes the node from
the page within milliseconds ([01](01-ANATOMY.md) §4), which breaks any field a script
reads or clicks in the DOM.
**Rule.** Make the form presentable without its scripts. The first element is a plain
line that says what is loading; hidden helper fields come after it. If something must be
invisible from the first frame, the form-level CSS in `Data.code` is the only surface
applied at render that can hide it. Per-element `style` takes only theme variables
([01](01-ANATOMY.md) §4), and writing `Data.code` needs the right key
([07](07-DEPLOY-WORKFLOW.md) §2).
When every section stays hidden until a load process answers (an account check that shows one
of several sections), the card is empty for those seconds. Give every state paragraph a shared
class and draw a skeleton from CSS alone:
`.form-builder--form-body:not(:has(.state-a)):not(:has(.state-b))::before { … }`. It shows from
the first frame and leaves by itself when any section renders, with or without the JS. The
scoper keeps `:has()` written this way, one simple selector per `:has()` (verified on a live
form, 2026-10-26).

---

## Values and Vue

### Writing `info-text` from the field model does nothing at all
**Cause.** The runtime renders `info-text` from the element's STATIC config array, not
from the reactive field object, so assigning `infoText` on
`ProcesioForm.data.fields.<name>` changes nothing on screen, and no
`setConfigValue`-style API is exposed to form JS. (The field object itself is wider
than `value`, `visible`, `required` and `readonly`: on a select built through the API it
carried 15 properties, `label` and `placeholder` among them. What it carries follows the
form's data model; see *A script reads a select's options and gets nothing*.)
**Rule.** Drive live text - counters, running totals, quota hints - by writing the DOM
node. Note that when `info-text` is empty the message component is never rendered at all
(`v-if` on a truthy value), so there is no node to write into: either set a non-empty
`info-text` in the designer, or create the node yourself.
See [`../dto/form/description.md`](../dto/form/description.md) for the selector details - 
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
**Cause.** The form's inputs carry an **empty `label` config** - their visible label
is a separate `paragraph` element sitting above each one, which is a common way to
build a form whose labels need styling the control does not offer. The label-matching
handle then has nothing to match on: `.pds-c-input-group--label` is absent and the
control's own `textContent` is empty (a placeholder is an attribute, not text). Found
on a live form where an entire step's gating had never once executed, with no error
anywhere and no visible symptom other than the feature simply not happening.
**Rule.** Before building anything on label matching, **check that the labels exist**
 - one `querySelectorAll('.pds-c-input-group--label')` on the rendered form answers it.
When they do not, fall back to an **element-id → field-name map generated from the
DTO**, say in a comment where it came from and how to regenerate it, and keep the rest
of the code speaking names. Ids are the weaker handle, but a weak handle that resolves
beats a strong one that returns null.

### A feature "does nothing" and no error is ever logged
**Cause.** A lookup returned null and every caller guarded it with `if (!key) return;`.
Defensive early-returns turn a wiring failure into silence.
**Rule.** When a mapping function can legitimately return null for SOME nodes, assert
that it resolves for **at least one** - a `console.warn` when a whole pass resolves
zero fields would have caught the above on first load.

### The wrong field gets a value / a label match hits the wrong control
**Cause.** A substring label match, ordered shortest-first. `'id - series'` matches
inside `'id representative - series'`.
**Rule.** Order the label table **most specific first**, and normalize diacritics
and case on both sides of every comparison.

---

### A button has to be clicked twice before its MAP_FORM_DATA reacts
**Cause.** A JS block wrote a value (for example a validation flag) and a MAP
condition later in the SAME chain reads it. `input`/`number-input` values reach the
form model 500 ms after the DOM write (`onInputDebounced`), so the MAP sees the
value from before the click. The second click works only because the first one's
value has landed by then. Verified live, with a MAP that never saw the value its
own chain had written.
**Rule.** Never branch a MAP on a value the same chain's JS just wrote. Hand off
through a field's own `onInput` chain instead: [04](04-INTERACTION-RECIPES.md) §16.

### A programmatic click on another form button, from inside a chain, does nothing
**Cause.** While a button's chain runs the form is locked: every element is
`disabled`, and a disabled button ignores the click. The stepper's Next/Previous
are not form elements and still respond.
**Rule.** Do not chain one button into another. Trigger the follow-up through a
field's `onInput` chain ([04](04-INTERACTION-RECIPES.md) §16), or click the stepper.

### A MAP guarded by `<variable> IS_TRUE` runs although the variable is "false"
**Cause.** The designer stores a Boolean form variable's default as TEXT (`"False"`
or `"false"`), and a condition treats any non-empty text as true. Measured live:
text `"false"` → `IS_TRUE` passes and `IS_FALSE` fails; `null` → the opposite. Two
mutually exclusive branches both run, and a load gated on `isConfirmed IS_TRUE`
runs for every visitor. A render process that later writes a real boolean does not
help a condition evaluated before its result lands.
**Rule.** Do not branch or gate on a Boolean form variable with `IS_TRUE`/`IS_FALSE`.
Branch on a value that really is text (`EQUALS` on a select's value, or on a field
your own flow writes), or give the variable a `null` default. And a condition in
the browser is never access control: re-check the user inside the process.
`formlint` flags the pattern.

### A MAP that writes a field also runs that field's handlers, at once
**Cause.** A value set by MAP_FORM_DATA (or by a process outputMap) reaches the
element with no debounce and fires its `onInputEvents` chain immediately, in
parallel with the chain that wrote it. JS blocks of concurrent chains share one
sandbox iframe, so they can cancel each other.
**Rule.** A field that must trigger logic is written by exactly one party. Keep
flags that MAPs reset apart from the field that triggers work.

### A script reads a select's options and gets nothing
**Cause.** Two gaps, both silent. On a form built through the API before 2026-10-01, the
select's field object has no `sourceType` and no `sourceValue`: `form-create` wrote them
as element configs but left them out of the form's data model, and only data-model
attributes reach `ProcesioForm`. A save in the designer adds them, and `form-create` and
`form-add-element` now write them too, for a static option list. The page is no fallback either:
the option nodes are not drawn until the list is opened once (none before, the
options after). A local replica that draws its own select hides both gaps, so the list is fine
in every test and empty on the live form.
**Rule.** On a form built or rebuilt since then, read a static list from the field's
`sourceValue`, through a lookup that ignores case and separators. For an older form, a
JSON or URL source (whose shape was never captured, so the builder leaves it out), or a
list the page has to supply, hand the script the list directly: write it in at build
time, or return it from a process call the form already makes. Opening the select from
code so that it draws works, but it leans on markup and timing. Spec and the one
remaining live check: `todo/procesio-form-create-select-source-in-data-model.md`.

### Field reads that worked stop working after a designer save
**Cause.** A form built through the API keeps its field names exactly as written, and
`ProcesioForm.data.fields` is keyed by them. A save in the designer re-keys them: it
splits each name on underscores, lowercases the parts and joins them in camelCase, so
`orderList` becomes `orderlist` and `order_id` becomes `orderId`. A read that
worked for weeks returns `undefined` the first time anyone saves the form in the
designer, and a lowercase snake_case name is not safe either.
**Rule.** Read fields through a lookup that ignores case and separators
([`../dto/form/description.md`](../dto/form/description.md)). Only a name that is a single
lowercase word survives a designer save unchanged. `form-create`, `form-edit` and
`form-update` return a warning naming every field a designer save would re-key, and
what it would become. They never rename: scripts in use read the names as built. When no name is given, the builder generates a single lowercase word from the label, so auto-named fields are safe by default; only a name you set yourself can trip the warning.
**Why it happens, and the 2026-10-05 fix.** The re-key is the designer's legacy format
`"0"`, which it applies to a form with no `dataModelAttributeFormatVersion`; under `"1"` (what
the designer writes for its own new forms) it keeps every name as written. The builder wrote
no version until 2026-10-05 and now writes `"1"`, so a form built since then keeps
`orderList`, `order_id` and `Customer_First_Name` through a designer save (measured on QA,
read back by form JS) and draws no warning. The lookup above is still right for a script that
may run on an older form.

### A designer save changes far more than the edit you made
**Cause.** Saving in the designer rewrites the whole definition. On an API-built form, one
save with no edit at all re-keyed the field names (above), added an encrypted `Data.code`
blob, gave every element a `class` config, replaced the theme layout, swapped `type` for
`rows` on text fields and removed `disabledIfFormIsInvalid` from buttons. The form-load
scripts survived it.
**Rule.** Treat a designer save of an API-built form as a migration: export the definition
before and after and diff them, rerun the form's live checks, and Publish. Better still,
change API-built forms only through the builder.

### A validator reports filled fields as empty, but only after an earlier step ran
**Cause.** Two element scripts install the same shared runtime (a field collector, a validator)
behind the same version guard (`if (!W.__x || W.__x.v !== 14)`) but with different payloads, for
example a short field list on step 1 and the full list on step 2. Whichever runs first wins; the
second sees "v14 already there" and never installs, so its fields are never collected and every
one of them reads as empty. Each script is correct alone, so testing a step on its own passes.
**Rule.** One payload per version number, identical wherever it is pasted. A script with a
different payload gets its own version (or its own global). When auditing, list every copy of a
runtime with its guard and a hash of its payload: same guard + different hash = this bug.

### A "checked" rule on a table's checkbox passes only when the FIRST row is ticked
**Cause.** A control placed in a dynamic table row renders once per row with the same `id`. A
collector that reads `[id="checkboxN"]` takes the first rendered match, so a validator rule
"checkboxN must be checked" really means "row 1 must be checked". Any valid selection that leaves
row 1 out (a line in another currency, the other half of a 50/50 pair) fails, with the error
anchored under row 1. It hides well: the first test usually ticks row 1.
**Rule.** A rule about a table's selection is a rule about ALL its rows: call the selection
guard's own `check()` (the one the submit button already runs) instead of reading one id.

### Buttons drawn over a radio group never show the selection
**Cause.** The design system's radio renders the option value as a `modelvalue` ATTRIBUTE on the
`<input type="radio">` and gives it no `value` attribute, so `input.value` is the browser default
`"on"` for every option. Code that matches options by `input.value` never finds one, and code that
reads the checked input's `.value` reads `"on"`. The click still lands (the model changes), so the
form looks unclickable while the data is right. A local replica that draws its own radios with a
`value` attribute passes every test. Measured in the forms bundle (Radiobox.component), 2026-10-26.
**Rule.** Read a radio's value with `input.getAttribute('modelvalue')`, falling back to `.value` only
when the attribute is absent. Each option is `label.pds-c-radiobox--group > input.pds-c-radiobox--field
+ span[role=radio][aria-checked] + span.pds-c-radiobox--label`. Draw it the same way in a replica.

### Every row of a dynamic table comes with two empty padded strips and a frame inside the frame
**Cause.** The design system's table puts each item between two helper rows
(`tr.pds-c-table--row--before` / `--after`, one `td[colspan]` each) and a dynamic row nests its own
`table.pds-c-table` inside the Table's `tbody` ([03](03-DOM-CONTRACT.md)). A stylesheet rule that gives
every `td` a padding and a bottom border, and every `.pds-c-table--container` a frame, turns each data
row into three bands and draws a second frame inside the first. A column defined with no key and no
label still draws an empty `th#th` and an empty cell in every row.
**Rule.** Hide the helper rows, take the frame and padding off the inner container and its wrapper
cells, and style only the data rows (`tr.pds-c-table--row:not(.pds-c-table--row--before):not(.pds-c-table--row--after)`)
as flex rows sharing the header's columns. Hide `th#th` and a cell holding neither an element nor
text. Measure on the live structure: a replica that builds tables with one `innerHTML` cannot nest a
`div` in a `tbody` or a `tr` in a `tr` (the parser moves them), so build that structure with
`createElement`.

### Changing anything on an earlier step throws the user forward to the step they left
**Cause.** A copy of the "go to the next step" script (click the stepper's Next, scroll to the top)
was left at the end of input chains (a select, an upload) where a loader-hide belongs. While the later
steps are hidden, Next has nowhere to go and nothing shows. Once they are open, every change on the
earlier step (a new choice, a re-uploaded document) jumps forward without the change being confirmed.
**Rule.** An input chain ends by hiding the loader, nothing else; only a confirm or validate button
moves the stepper. When auditing a form, hash the last script of every chain and look at where each
copy of a navigation script sits.

### Re-confirming an earlier step leaves the later steps built for the old choice
**Cause.** A step's confirm chain renders the next step for the current choice (which branch shows,
which Validate button, the lists), but nothing resets what the later steps already did: their
Validate / Modify buttons, their validation flags, their visibility. After switching a choice and
confirming again, a later step can show the old branch, or a Modify next to a Validate, until every
step is passed again.
**Rule.** Lock an earlier step once it is confirmed, the way validated steps are locked, and give it
its own Modify. Make its confirm chain reset the later steps with the same MAP rows their Modify
buttons write (fields unlocked, flags 0, later steps hidden), generated from those buttons rather
than typed again. Keep the forward navigation closed while the earlier step is open for changes.

### Injecting an icon next to process-drawn content breaks the code that reads that content
**Cause.** Code located the chart a process drew with the first `svg[viewBox]` in the element's
wrapper. A header added at the top of that wrapper carried icons, which are `svg[viewBox]` too, so the
next pass read an icon as the chart, found no data, turned the feature off and removed the header, and
the pass after found the chart again: an on/off loop every refresh, a DOM that never went quiet and a
loader that waited for quiet and never closed.
**Rule.** Query process-drawn content inside its own container (`.form-builder--paragraph svg`), never
by tag in a wrapper you also decorate. A loader or "settled" check that waits for a quiet DOM turns
any such loop into a frozen form, so when one hangs, count mutations per target for two seconds first.

### A choice drawn over a select falls back to the native list for good
**Cause.** Buttons that pick through the real vue-multiselect (open it, click the option, check the
shown label) verified the pick on the nodes the pick started on. The option's own chain often
re-renders that select (a MAP showing the fields of the chosen document type), so the check read a
detached node, counted the pick as failed and switched that field to the native dropdown for the rest
of the session, while the value had in fact been set.
**Rule.** Verify on the field as it is now: query it again by id, and after a failed check wait for the
chain to finish and compare the value attribute before calling it a failure. A fallback to the native
control lasts until the field has a value, then the buttons come back showing it.

### One control that changes form with the data reads as two controls
**Cause.** A picker laid over a chart a process had drawn (each chart row matched to its table row)
gave the table back whenever one row could not be matched. Depending on the document, the user met
either the chart as a selector or the table as a selector, and reported it as a bug.
**Rule.** One selector, always in the same form. A chart drawn by a process stays a picture; the choice
is made in a control of its own, preferably the one the form's own checks already measure.

### A field shows a required mark that nothing enforces
**Cause.** The step validators were scripts that each carried the WHOLE form's rules but checked only
the fields rendered on their own step. Required marks taken from "whichever validator has a rule for
this field" marked fields that the validator of their own step had dropped on purpose (a legal
representative's personal-ID number on a company client), so the page claimed a requirement that no
validation ever applied.
**Rule.** Take a field's required flag only from a validator of its own step or branch; a rule found
only in another step's validator may still lend its format hint, never the mark. Apply the same test
before trusting the platform's own `required` flag on a field: when no validator of its step checks it,
say so to whoever owns the form instead of guessing which one is wrong.

### A process warning outlives the file it was about, or shows in two looks
**Cause.** An upload's process wrote its warning into a paragraph (visible + label from the outputs),
and the page also showed its own message under the dropzone. The paragraph was hidden only while the
page's message was up: when the message cleared (the file was removed) the paragraph, still holding
the old warning, came back, and on the paths where the page's message did not fire the paragraph
showed alone in its own design.
**Rule.** When the page reports an upload's outcome, it owns that warning paragraph completely: the
paragraph never shows, its text appears in the page's message, and only while the file is there.

### The page runs hot with nothing happening
**Cause.** A decorative full-screen canvas (gradients, particles) redrawn on every animation frame at
the device pixel ratio. On a 2x screen that is four times the pixels of the CSS size, sixty times a
second. The script time per frame is small (about 0.25 ms measured), so a JS profile hides it: the
cost is the painting, which a headless measurement on a 1x screen does not show either.
**Rule.** Draw a soft background at 1 pixel per CSS pixel and cap it at about 30 frames a second; stop
it when the page is hidden. Keep the refresh pass that styles the form cheap and measured (a counter of
passes and milliseconds per pass), and keep a network log's response bodies to the newest per address:
a polled answer otherwise stays in memory once per poll.
Measured at 4x CPU throttling (`web perf-probe`), the 1x / 30 fps canvas still held the main thread at
about 100% (16 fps, every frame a long task) while its script took under 1 ms a frame: the four
full-screen gradient fills were the cost. Draw the soft gradients on a second canvas at an eighth of
the pixels, let the compositor scale it up (identical to the eye), redraw it a few times a second, and
keep only the small shapes on a transparent full-size canvas, links batched into a few strokes. On a
machine that is still too slow, freeze one frame instead of animating
([05](05-STEPPER-AND-MOTION.md) §7).

### The whole page jumps when the runtime arrives (layout shift above 1)
**Cause.** The runtime mounted its body-level UI (a background canvas, a header, a loader) before it
copied the form's CSS scope onto `<html>` ([02](02-CODE-INJECTION.md) §2). Until then the scoped
sheet does not reach those nodes: the canvas is an inline element sized by its `width` / `height`
attributes, a full screen tall, and pushes the whole app below the fold; the header shows its logo
SVG at natural size. One refresh pass later the scope arrives and everything jumps back. Two shifts of
about 0.57 each, invisible on a fast machine, a visible flash on a slow one.
**Rule.** Propagate the scope before the first mount, not inside the first refresh. As a backstop, put
one rule in the critical (unscoped) import: `html:not([data-form-css-scope]) body > .<runtime-root>
{ position: fixed !important; visibility: hidden !important; }`.

### A thin moving strip on the card repaints the whole form every frame
**Cause.** The strip was the card's own background, animated with `background-position`. A background
change repaints the element, so the card, its content and its large shadow were painted again on
every frame, forever.
**Rule.** Move whatever moves into a pseudo-element no bigger than the moving part. A strip along the
top edge: `::before`, absolutely positioned, as tall as the corner radius, `border-radius: inherit`
with the bottom corners at 0, so the same corners clip it. The look is the same; the repaint is a band.

### With the canvas gone, the repeating CSS animations still take half the main thread
**Cause.** Two dozen `infinite` animations on paint properties (`box-shadow` pulses, `background-position`
sheens, `fill` waves on SVG dots, `left` sweeps), each repainted and restyled every frame. Measured at
4x: about 50% of the main thread, against 3-6% with them stopped.
**Rule.** Keep them for devices that can afford them and stop them on the others behind an attribute
on `<html>`. Generate the stop rules from the CSS at build time (every rule with a repeating
animation gets a twin under the attribute that keeps only its finite parts), so a new animation is
covered the day it is written; exempt the loops that report progress (spinners, skeletons, a loader).

### A heading (or paragraph) holding a banner shrinks to its text
**Cause.** The element wrapper is a flex item in the step's layout; `width: 100%` on the inner
heading is 100% of a wrapper that has already shrunk to its content.
**Rule.** Widen the innermost wrapper that holds the banner and everything below it:
`.form-builder--element:has(.banner):not(:has(.form-builder--element .banner))` and its
`:has(.banner)` descendants. Never `.form-builder--element:has(.banner)` alone: the step and
stepper wrappers contain the banner too, and a `display` rule there shows the hidden steps.

### Columns stacked on top of each other leave a tall empty band under short ones
**Cause.** The theme sizes every column wrapper with `.form-builder--columns > .form-builder--element
{ flex: 1 0 var(--min-w-column) }` (150px by default) and every column with `height: 100%`. Turn the
block into a vertical stack (`flex-direction: column`) and that flex-basis becomes a 150px minimum
HEIGHT: a two-line question in the first column gets ~80px of nothing under it. The theme's column
defaults add more: 16px paddings, `--min-h-column: 84px`, a grey column background, and a block
frame whenever a `Border color` is enabled in the element's style config (the width defaults to 1px).
**Rule.** When you stack columns, set the wrappers to `flex: 0 0 auto` and the column and its
`--content` to `height: auto`, and zero the theme variables (`--pv-column`, `--ph-column`,
`--min-h-column`, `--bw-columns`) on the block. Measure in a browser that loads the platform's own
stylesheet; a replica without it shows none of this.

### A dialog's content jumps up when someone ticks a box in it
**Cause.** A visually hidden checkbox (1px, absolutely positioned) got focus on the click and the
browser scrolled it into view. The nearest scrollable ancestor was the dialog card itself:
`overflow: hidden` still lets the browser scroll an element from code, so the header, body and
footer slid up inside the card and left an empty block below.
**Rule.** Give dialog cards `overflow: clip` (it cannot be scrolled at all), lay the real input over
its own label (`position: absolute; inset: 0; opacity: 0`) so focusing it needs no scrolling, and
reset `scrollTop` on the card's `scroll` event as a fallback.

### A rule that hides an element loses to an older `display: flex !important`
**Cause.** Two `!important` declarations: the one with higher specificity wins, wherever it sits.
`.element--inline:has(> .button)` (two classes) beats a single-class `.is-hidden`.
**Rule.** A state class that hides an element needs at least the specificity of every rule that
displays it (`.form .element.is-hidden`), and a check in the browser that it is really hidden
(`getClientRects().length === 0`), not just a class on the node.

### Icons injected into a paragraph come out huge
**Cause.** A rule written for the paragraph's own content (`.paragraph svg { width: 100%
!important }`, to scale a chart) also hits every icon a runtime appends there later.
**Rule.** Scope content rules to what the content is (`svg[role="img"]` for a chart the process
draws), never to the tag alone.

### A long AI extraction is reported as failed while it is still running
**Cause.** One fixed ceiling was used both to close the loader and to declare failure; a
multi-page PDF read by a language model can take longer, and the result then lands on a screen
that already said "nothing found".
**Rule.** Separate a soft ceiling (the message changes to "taking longer than usual", the wait
goes on) from a hard cap. Count what the run produced from the page when it lands (tables and
charts arrive only after the MAP that follows the process), not at the moment the run ends. In
the `/variables` answer, instance status 6 (stopped) and 40 (finished with errors) end the wait
as failures.

### A value written to `<element>.<config>` lands on a different element
**Cause.** Config ids are NOT unique across a form: elements built from the same template share
config ids (several steps carried the same id for `visible`). A lookup keyed by config id alone
resolves the value path `{root}.{FIELDS_NS}.{elementId}.{configId}` to whichever element was
indexed last.
**Rule.** Resolve by the pair (element id, config id), always. The tool's handlers do; a script
or a replica that builds its own index must too.

## Mapping and processes

### `[object Object]` lands in every field
**Cause.** A structured variable was mapped as a whole, or the row's `path`
attribute chain was dropped during a rewrite. The form side's path shape is typed
`any` in the renderer - it is **not derivable** and cannot be guessed correctly.
**Rule.** Eliminate paths: one process output variable per field, all primitives,
split by small Node actions ([06](06-PROCESS-INTEGRATION.md) §4).

### The designer shows raw guids and the launch 400s
**Cause.** A variable **name** on the left of a map row. The API accepts it.
**Rule.** The process-variable GUID goes on the left, always. Let
`form-set-element-event` resolve names - it fails before writing if one is unknown.

### The designer cannot render a mapping row you wrote via the API
**Cause.** The sides were written as bare strings.
**Rule.** Each side is an object: `{value, isList, path}`, with `path: {}` on the
process side and `path: null` on the form side.

### The process runs but the outputMap populates nothing
**Cause.** `syncRun: false` - the form fired and forgot.
**Rule.** `syncRun: true`. Verified to hold the line open across a multi-second
external call.
**Observed timing with `syncRun: false` (2026-10-22, FORM_LOAD and click chains):** the
renderer still launched with `runSynchronous=false`, waited for the completion notice, then
read `GET /api/formProcess/{form}/{process}/{instance}/variables`, and only then ran the next
event of the same chain. So a "hide the loader" script placed after the RUN_PROCESS runs once
the result is in, not right after the launch.

### A signature-pad value mapped to a File input fails at launch
**Symptom.** The click chain runs (publish, upload and launch all return 200), the form
unlocks, and nothing else happens. The instance shows 0 actions consumed and
`Error while building input model: Invalid variable value for the mandatory input file property.`
**Seen** once, on a duplicated form whose signature pad fed a `File` process input (the
upload itself succeeded; the stored value was `{id, elementId, name, file: {}, path, …}`).
Not yet checked on an original, non-duplicated form.
**Rule.** Before relying on a signature pad → File mapping, run the real chain once and check
the instance's actions. Give the form a visible failure path: a UI that only reacts to the
success output leaves the signer looking at a button that did nothing.

### The process launches twice per interaction
**Cause.** Two `RUN_PROCESS` events on the same trigger.
**Rule.** One event per trigger; rewire with `--replace`. Read their conditions first: two events
whose conditions exclude each other are one run per interaction, and they are a valid way to route
one trigger to two inputs.

### A Node action is rejected at save time
**Cause.** `Timeout` outside 60–300, or a superseded action (`Call API v3`).
**Rule.** `Timeout` 60–300; use `Call API` with `Response Status` / `Response Body`
/ `Time Out`. Remember `Node` returns raw while `Javascript` wraps as `{result: v}`.

### Fields come back empty but the call succeeded (status 200, valid body)
**Cause.** Extraction quality - the model returned mostly nulls for a partially
legible document. Not a wiring failure.
**Rule.** Carry a `warning_status` / `warning_message` pair out of the process so
the form can tell the two apart, and never throw inside a parse Node - return a
diagnosable object.

### A file variable is rejected
**Cause.** `file` is not a type.
**Rule.** Use the `FileDataModel` model.

### Removing an uploaded file starts the extraction again, on nothing
**Cause.** An upload's input chain also runs when the file is removed (the value becomes empty). A
`RUN_PROCESS` event in it without a condition then calls the extraction with no file: a paid call, a
loader for nothing, and outputs that may or may not clear what the last file produced.
**Rule.** Give every process call on an upload chain the condition `IS_NOT_EMPTY` on the upload's own
value (the same path an `IS_EMPTY` MAP of that chain already tests), as a sibling upload's chain
usually does already. Hide or clear what the old file produced (tables, a chart) in the `IS_EMPTY`
branch or from the page, so nothing chosen from a removed file stays on screen.

---

## CSS

### The page will not scroll; the bottom of the form is unreachable
**Cause.** `overflow: hidden` on `.form-builder--form`.
**Rule.** Never. Clip with a **background** instead - backgrounds honour
`border-radius` for free.

### The pinned footer lands on top of the content
**Cause.** A `transform` on `.form-builder--form` made the card the containing block
for `position: fixed` descendants.
**Rule.** Animate the card's `opacity` only. No `transform`, `filter`,
`perspective`, or `will-change: transform` on the card.

### An animated gradient bar vanishes after the first cycle
**Cause.** `background-repeat: no-repeat` while animating `background-position` - 
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
HTML parser cannot nest a `<div>` inside a `<p>` - the block is hoisted out and lands
as a SIBLING of an now-empty `<p>`. Selectors written against `p > .my-block` match
nothing, and the wrapper is `display: flex`, so the hoisted block becomes a flex ITEM
sized to its content: a centred block sits off to one side of the column it should fill.
**Rule.** Style the wrapper's children, not the `<p>`:
`.form-builder--paragraph { align-items: stretch } .form-builder--paragraph > * { flex: 1 1 auto; min-width: 0 }`.
DOMPurify's defaults keep `class`, `style` and `data-*`, so authored paragraph HTML can
carry real classes - do that instead of inline styles, which only `!important` can
override later.
**Where the block lands depends on how the HTML was parsed, so write CSS for both.** Measured
on a live form (2026-10-26): `v-html` sets `innerHTML` on the `<p>` itself, and fragment parsing
in that context keeps the `<div>` INSIDE the `<p>` (`block.parentElement.tagName === 'P'`). A
page parsed as a whole document, or a local replica that builds the body with one `innerHTML`
on a container, hoists it out as described above. So never select `p > .block` or
`.form-builder--paragraph > .block`; select the block's own class and give it its own layout.
The sanitizer is `DOMPurify.sanitize(html, { ADD_ATTR: ['target'] })`, so `target="_top"` on a
paragraph link survives. Inside a link keep the content inline (`<span>`s styled as blocks): on
the hoisting path a `<div>` inside an `<a>` inside a `<p>` is split by the parser.

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

### A hover lift does nothing on an element that animated in
**Cause.** The entrance animation used `animation-fill-mode: both`. Its last keyframe
(`transform: none`) stays applied after the animation ends, and animations beat
ordinary declarations, `:hover` included.
**Rule.** Entrances use `backwards`: the "from" state covers the delay, and the element
returns to its own styles at the end.

### Tiles in a grid overlap or overflow it
**Cause.** Authored `<a>` / `<button>` tiles with `width: 100%` and padding render with
`box-sizing: content-box` on this page, so every tile is wider than its grid track.
**Rule.** Set `box-sizing: border-box` on the component and its descendants. Also check
that a narrow-screen media query comes after the wider one in the file: a
`max-width: 480px` rule placed before a `max-width: 760px` rule loses to it on phones.

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
the real step elements - which happens the next time the form is saved.
**Rule.** If you draw your own rail, hide theirs explicitly:
`.form-builder--stepper--nav { display: none !important; }`.

### The step indicator jumps to a wrong position (e.g. straight to 100%)
**Cause.** Step detection failed and the code guessed.
**Rule.** Return `-1` for unknown and **leave the indicator untouched**. Wrong
information is worse than a stale frame.

### Step detection breaks after a redesign
**Cause.** Matching on a design-system wrapper class.
**Rule.** Match on the visible banner text - that text is the form's own content.

### Custom step labels drift from the form's
**Cause.** A second, hand-maintained list.
**Rule.** Copy the labels off the platform's nav items before hiding it, and fall
back to the hard-coded list only if the counts disagree.

### A gated "next" button lets a fast clicker straight through
**Cause.** Two independent leaks, both measured on a replica:
1. the gate was a **class on the button**, and the renderer destroys and recreates the
   nav buttons on every step change - the class is gone by the next click;
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
same change** - an always-visible control that opens the fields - not a timeout. A
toast promising "you can fill these in by hand" over fields that are still hidden is
worse than no promise.

### The recompute loop stops the moment nobody is looking
**Cause.** `requestAnimationFrame` does not fire in a **backgrounded or hidden tab**,
and the recompute loop hangs entirely off it. Harmless for a person (nothing to see),
but it makes the form look frozen to any automated check - the page renders once and
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
workspace API key with the form-code passphrase - both are short opaque tokens.

### A PUT starts failing for no visible reason
**Cause.** An unexpected extra field from the GET was echoed back, or camelCase was
sent where PascalCase is required.
**Rule.** Map the envelope explicitly (`_PUT_KEYS`), never spread the GET body.

### A fix on the process side breaks a branch that used to work
**Cause.** It was published straight to the live process.
**Rule.** Duplicate, change the copy, test the copy, promote. And when something
does break: revert fully and immediately, then re-approach.

### `form-set-code` succeeds and the form goes blank
**Cause.** The key stored for that environment is not the one the installation's
renderer uses. The write encrypts with it anyway; the renderer cannot open the blob, logs
`Malformed UTF-8 data` and never mounts the form. It is easy to read this as "the CLI
cannot write form CSS", which is the wrong conclusion. The tool no longer lends the
default environment's key to another installation, which closes the commonest way in,
but a wrong key stored under the right name still does this.
**Rule.** Before the first write on an installation, decrypt the code of a form whose CSS
was written in the designer there ([07](07-DEPLOY-WORKFLOW.md) §2). If that fails, the
key is wrong; do not write. `form-set-code --clear` repairs a form already blanked.

### A form answers "Form not found" after someone edited it in the designer
**Cause.** A designer **Save** without **Publish** turns a published form into a draft,
and a draft's page answers "Form not found". The draft is not closed, though: its data
stays reachable through the API, anonymous `rows/filter` included.
**Rule.** Publish after every designer save, and confirm the status through the API
(`status` 1 = published, 0 = draft). To take a form offline, make it private or disable
it. A draft takes the page down and leaves the data up.

### A form takes seconds to open, and much longer at busy times
**Cause.** The whole definition, scripts included, is sent on every open, uncompressed.
A 499 KB form took 4 s at good times and up to 20 s at bad ones. Minifying cut the
script by about a quarter but the form by only 9-15 %, because most of the weight is
elements and their data model (about 260 KB of them beside 100 KB of script, in one
case).
**Rule.** Few hidden helper fields: one request field and one result field per process,
holding JSON, rather than one field per value. Minify at build time and keep the
readable source in the repository. Check a form's size before it ships, the way you
check its contrast.

### The first open on a fresh browser takes most of a minute
**Cause.** Not the form. On a cold browser the forms site's own stylesheet, about 2 MB,
took 31-62 s to download in one measurement, while the form and its first process call
together took about 11 s.
**Rule.** Before a demo, open each form once on the presenting machine so the platform's
files are cached. Load the opening view with one process call, not several. Report
platform slowness with numbers: in the same measurement a neutral CDN served 1 MB in
about a second.

### Each process call from a form takes three to four seconds
**Cause.** Every `RUN_PROCESS` from a form went through a platform publish step
(1.8-3.0 s) before the launch itself (1.2-1.4 s). Calls made one after another add up:
a view that read three items with one call each spent 16.5 s on them, about half of its
31.7 s load.
**Rule.** Give each view one call that returns everything it needs. Whether the publish
step can be skipped for a process that has not changed is a question for the platform
team.

---

## Silent DTO acceptance (the server takes it and says nothing)

These are accepted with a 2xx and no error, then cost a debugging session because
nothing points at them. `form-update` now emits non-blocking **lint** warnings for
the first three (see `tools/procesio/formlint.py`); the doctrine is in
`agents/procesio/PROCESIO-API-RELIABILITY-DOCTRINE.md`.

### An element saves fine but renders on NO tab / pane
**Symptom.** The element exists in the DTO and the PUT succeeds, but it appears on
no tab - invisible in the rendered form.
**Cause.** Its `parentId` references no element on the form (a phantom parent). Tab
and container membership is by `parentId` = a container element's id (§01-ANATOMY);
a dangling id is silently placed nowhere.
**Rule.** Point `parentId` at a real container/tab element id, or `null` for a
top-level element. (Lint: "phantom parent - renders on NO pane".)

### A form-update patch changes nothing, silently
**Symptom.** `form-update` returns applied, but the form is unchanged.
**Cause.** The `--data` patch was wrapped as `{"Data": {...}}` (or a top-level key
was mistyped). The deep-merge adds it as a NEW key inside `Data` - inert junk - and
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
