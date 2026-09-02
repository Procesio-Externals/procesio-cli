# Submitting a PROCESIO form programmatically, and why you must

How to run a process **through its form** rather than through the process API, using the
public `FormProcess` endpoints, and the class of defect that only this catches.

## Why the process API is not enough

A form and the process behind it are assembled separately, and **nothing in the platform
asserts that the two agree**. Two failure modes follow, both of which pass every
process-side assertion ever written:

1. **A submit button wired to nothing.** The form validates, publishes, renders, collects
   every field, and discards all of it. Process-side tests never touch the form, so they
   stay green.
2. **An input that is collected, mapped, and never consumed.** The variable exists, the
   form sends it, the engine receives it, and no action reads it. The feature it appears to
   offer silently does nothing, and the value shown to the user is whatever the code
   hardcoded.

Both are invisible to an API-only test suite and to a green run. Treat a form-surface
submission as part of acceptance, not as an extra.

## The call sequence (mirrors the process side, different routes and headers)

Every `FormProcess` route is **anonymous** and scoped entirely by the
`formTemplateWorkspaceId` **header**. Omit it and the API answers
`Invalid request due to missing or incorrect resource parameters. target: form template`.

| Step | Call | Notes |
|---|---|---|
| 1 publish | `POST /api/FormProcess/{formTemplateId}/{processTemplateId}/publish` | body = the input payload keyed by **process variable name**; files are staged as **metadata only** `{path:"",size,mimeType,name,id:<client uuid>,hash:""}` |
| 2 upload | `POST /api/FormProcess/{formTemplateId}/{flowInstanceId}/upload` | `multipart/form-data`, field name **`package`**, headers `flowTemplateId`, `variableName`, `fileId`, `formTemplateWorkspaceId` |
| 3 launch | `POST /api/FormProcess/{formTemplateId}/{instanceId}/launch?runSynchronous=true&secondsTimeOut=N` | body `{connectionId, flowTemplateId}` |
| 4 read | `GET /api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables` | |

**The launch route's second path segment is the INSTANCE, not the process template**, even
though the API reference names it `processTemplateId`. The give-away is that the body
already carries `flowTemplateId`, which would be redundant otherwise; the process-side
equivalent (`/api/Projects/instances/{instanceId}/launch`) has the same shape. Verified
live: launching with the instance in that slot succeeds.

**The variables response carries runtime values in `defaultValue`, not `value`.** The
endpoint returns variable *definitions*. Reading `value` yields `None` for every output and
looks exactly like "the form produced nothing", which is the same false negative this
whole exercise exists to prevent. Flatten to `{name: defaultValue}` before asserting.

Implemented as the curated action `run-form-with-files` (the generated `<method>-<path>`
actions cannot reach it: they send JSON only, with no custom headers and no multipart).

## The contract check, as a standard

Run this for every card that ships a form. It is three layers, and the third is the one
that cannot be faked:

1. **Every form input reaches the engine.** Each `inputMap` row's process side resolves to a
   real input variable, and its form side resolves to a **4-segment value path**. A row left
   holding a raw field *name* is accepted by the API, renders blank in the designer, and
   never carries a value.
2. **Every engine output reaches a pane.** Any output with no `outputMap` row is either a
   missing pane or a machine-only channel. See the exemption rule below.
3. **Every input is consumed by the logic.** Cross-reference each input variable against every
   action's parameter bindings. An input bound by nothing is a **defect, not a spare**. Then
   prove it end to end: submit through the form surface and assert that a value entered on the
   form is visible in the rendered output. A tolerance, a threshold or a label is ideal,
   because a wrong one is invisible in a green run.

Layers 1 and 2 read the live DTOs and cost nothing. Layer 3 needs one real submission.

## The named machine channel: how to have an exception without losing the rule

A strict rule with no exit becomes a rule people switch off. A rule with a silent exit stops
being a rule. The way to keep both is a **declared exemption**: a machine-only output is
listed by name in the checker, so it passes and the pass is visible.

```python
# Outputs that exist for assertions and API callers, not for a pane.
# Named explicitly so the exemption shows up rather than being assumed.
MACHINE_ONLY = {"recon"}
```

The check then reports `output 'recon' is a declared machine channel, no pane expected`
instead of either failing a legitimate design or silently skipping it. Three properties make
this honest, and they generalise to any strict gate:

- **It is enumerated, not inferred.** No pattern match on names, no "outputs starting with an
  underscore are internal". Someone had to type the name.
- **It appears in the output.** The exemption is a line in the report, so a reviewer sees the
  exception was taken and can challenge it.
- **It is per-artefact and small.** A growing allowlist is itself the signal that the design
  drifted, which a blanket `--skip-outputs` flag would hide.

Never widen this to a category ("all Json outputs are machine channels"). The moment the
exemption is a class rather than a list, a genuinely missing pane joins it unnoticed, and the
gate goes back to passing the defect it was built to catch.

## A RUN_PROCESS event that never reads its result

Two separate settings decide whether a form learns anything from the process it launched, and a
form can be missing both while looking completely wired in the designer:

- **`syncRun: false`** — the event fires and the form moves on. Nothing downstream can see a result.
- **`outputMap: []`** — even a synchronous run maps nothing back, so the process's output variables
  stay inside the process.

With both, the form falls through to its generic `SUBMIT_SUCCESS` message whatever happened, so a
refusal ("that slot is taken", "invalid email", a rate-limit) is indistinguishable from a booking
that was written. This is the form-side twin of the `Execute Command` result-set defect
(PROCESIO-SQL-ACTIONS-NOTES.md): at every layer the failure mode is *the outcome is discarded and
success is assumed*, and at every layer it is invisible to validation and to a green run.

**The shape that works** — three events on one button, in this order:
1. `RUN_JAVASCRIPT` — validate, then write the process inputs into `ProcesioForm.variables`.
2. `RUN_PROCESS` — `syncRun: true`, `inputMap` from those variables, `outputMap` from the
   process's output variable into a FORM variable.
3. `RUN_JAVASCRIPT` — read that form variable and render the real outcome.

`form-set-element-event --replace-action RUN_PROCESS` swaps step 2 in place, preserving the other
events and their order; a plain call appends, which is how step 3 lands last.

**A result-set output arrives as a LIST even when it is one row**, so step 3 must take `[0]` (and
tolerate a non-array). Guard the success test on both `true` and `1` — the same field comes back
as a SQL bit and as a JSON boolean depending on the path.

**Do not hand-escape values in the form's JavaScript.** A `.replace(/'/g, "''")` in a submit
handler is a sign the process is string-interpolating SQL rather than binding parameters. Fix the
process (`sql-parameterize`), then delete the escaping: it is not a control (the process endpoint
is callable directly, without the form) and it corrupts legitimate input.

### Map rows: `isList` is not cosmetic
Each side of an `inputMap` / `outputMap` row is an object, `{value, isList, path}`. Binding a
list-valued variable with `isList: false` puts the whole result set into a scalar slot: the form
receives nothing, and both the API and the designer accept the row without complaint. `path` is
`{}` on the process side; on the form side it is `{}` for a form VARIABLE and `null` for a form
FIELD target.

## A `paragraph` renders its `label`. Writing `.value` paints nothing.

The single highest-yield form gotcha found so far, because it fails in the direction that looks
fine: `ProcesioForm.data.fields.SomeParagraph.value = '…'` is accepted, throws nothing, logs
nothing — and the page keeps its original placeholder text. A handler written that way reports
nothing at all to the visitor, whatever happened underneath.

```js
function say(text) {                      // set BOTH: a field control does read .value
  const m = ProcesioForm.data.fields.BookingMessage;
  m.label = text; m.value = text; m.visible = true;
}
```

Verified live both ways on a published form: with only `.value` the DOM text was unchanged after a
successful run; with `.label` the new text appeared. Assume the same for any control whose text is
authored as a label (heading, paragraph) rather than typed into by the user.

**Test it by reading the DOM, not the handler.** The handler running is not evidence the reader saw
anything — `document.body.innerText` before and after the click is.

## Driving a published form headlessly, without a compositing browser pane

Two facts make a real end-to-end click-through possible even when no pane is displayed and trusted
mouse events are unavailable:

1. **`element.click()` works on a PROCESIO form button.** The whole event chain fires — the JS
   handlers, the RUN_PROCESS, the result handler. Confirmed by the process instance appearing in
   `list-instances` attributed to the form, and by the row changing in the database.
2. **Every control pre-fills from a URL query parameter named after the control** — including
   `visible: false` controls, whose values reach the process even though they are not in the DOM at
   all. That is what makes a hidden-token page (a cancel link) work, and it also lets a test skip
   custom pickers (dropdown, date, slot list) that need trusted events: pass their values on the
   query string instead.

So: navigate with the fields on the query string, `.click()` the button, then read
`document.body.innerText`. That is a genuine test of the deployed form, not a stub.
