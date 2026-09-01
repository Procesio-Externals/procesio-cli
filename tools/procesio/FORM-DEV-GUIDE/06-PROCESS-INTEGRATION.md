# 06 — Wiring a form control to a process

How a control triggers a PROCESIO process, how data goes in, how results come back
into fields, and the design rule that saves a day of debugging: **one process
output variable per form field.**

---

## 1. The event

A `RUN_PROCESS` event on a control's trigger ([01](01-ANATOMY.md) §6):

```json
{
  "id": "<guid>",
  "type": "INPUT",
  "action": "RUN_PROCESS",
  "config": {
    "processId": "<process guid>",
    "syncRun": true,
    "inputMap":  [ … ],
    "outputMap": [ … ]
  }
}
```

**`syncRun: true` holds the line open** until the process finishes — verified live
across a multi-second external API call. With `syncRun: false` the form fires and
forgets, so an `outputMap` can never populate anything.

**One event per trigger.** Two `RUN_PROCESS` events on the same trigger launch the
process twice; the second result overwrites the first and the timing is not
deterministic. When rewiring, use `--replace` rather than appending.

## 2. The map rows — the shape that took three attempts to get right

```json
{
  "id": 0,
  "left":  {"value": "<PROCESS VARIABLE GUID>", "isList": false, "path": {}},
  "right": {"value": "<form value path>",       "isList": false, "path": null}
}
```

Four rules, each learned the hard way:

1. **The process-variable GUID goes on the LEFT** — in `inputMap` *and* in
   `outputMap`. A variable *name* on the left is accepted by the API, but the
   designer then renders raw guids and the launch 400s.
2. **Each side is an OBJECT, not a bare string.** Bare strings are accepted by the
   API and produce a row the designer cannot render.
3. **The two sides differ**: the process side carries `path: {}`, the form side
   `path: null`. Discovered by reading a mapping the designer itself had written.
4. **`path` carries the attribute chain** when a model-typed variable is mapped one
   attribute at a time. Rebuilding a row without carrying `path` over silently maps
   the whole object into a single text field — the classic `[object Object]`
   in every field.

The form side's value is the full field path from [01](01-ANATOMY.md) §5:

```
{dmRootId}.{FIELDS_NS}.{elementId}.{valueConfigId}
```

with `FIELDS_NS = 11223344-5566-7788-99aa-aabbccddeeff` (constant on every form).

## 3. Wire it with the tool, not by hand

`form-set-element-event` does a surgical read-modify-write: it touches **only** that
element's event config, resolves variable names to guids, and fails loudly *before
writing anything* if a name is unknown.

```bash
python scripts/run-tool.py procesio form-set-element-event \
  --id <form-id> --element <element-name-or-id> \
  --on input --action RUN_PROCESS --replace \
  --config-file event.json --dry-run
```

Drop `--dry-run` to write. Inspect what is currently wired with:

```bash
python scripts/run-tool.py procesio form-get-element-events --id <form-id> --element <name>
```

Because it resolves names, `event.json` can be written readably:

```json
{"processId": "<guid>",
 "inputMap":  [{"left": "input_file", "right": "<form value path>"}],
 "outputMap": [{"left": "o_first_name", "right": "<form value path>"}]}
```

It also defaults `syncRun` to `true`, so you cannot forget it.

## 4. Design rule: **one output variable per field, all primitives**

The tempting design is one structured output variable (a data model, or a JSON blob)
mapped attribute-by-attribute into the fields. Do not. The attribute-path shape on
the form side of a map row is typed `left: any` in the renderer, so it is **not
derivable** — you would be guessing, and a wrong guess writes `[object Object]`
into every field with no error anywhere.

The design that works:

```
File → Base64 → Decisional (branch by applicant type)
                 ├── Call API  (branch A)  → Node: parse → structured result
                 └── Call API  (branch B)  → Node: parse → structured result
                            ↓
                          Join
                            ↓
        one small "splitter" Node per field, each returning a plain string
                            ↓
        o_first_name, o_last_name, o_tax_code, …   (string outputs)
```

Each splitter is three lines:

```js
const o = <%0%>;                                  // the structured result
return (o && o.field_name != null) ? String(o.field_name) : '';
```

Then `outputMap` is a flat list of **primitive → field** rows. No paths, nothing to
guess, and every row is independently debuggable. The extra dozen Node actions cost
nothing at runtime and buy a wiring you can reason about.

**Do not add a hidden "carrier" field to the form** to receive the blob and then
distribute it in JavaScript. It puts a second copy of the data in the DOM, it needs
its own gating so it never shows, and the outputMap already populates fields
natively — which is also the honest completion signal (§6).

## 5. Notes on the process side

- **A file input's variable is `FileDataModel`**, not a primitive type. `file` is
  not a type.
- **`Call API v3` is superseded** — use `Call API`, with `Response Status`,
  `Response Body`, and `Time Out`. The framework's `process-create` refuses
  superseded actions outright.
- **A `Node` action's `Timeout` must be 60–300.** `30` is rejected by the validation
  gate. `Node` returns its value raw; a `Javascript` action wraps it as
  `{result: v}` — a difference that silently changes every downstream reference.
- **`Decisional` is a diamond** and fans out any number of branches; they do not
  have to re-converge, but a `Join` is the explicit merge point when they should.
- Parse defensively at the boundary and return a *diagnosable* object rather than
  throwing:

  ```js
  const r = <%0%>;
  try {
    const a = r.choices[0].message.tool_calls[0].function.arguments;
    return (typeof a === 'string') ? JSON.parse(a) : a;
  } catch (e) {
    return ({ warning_status: true,
              warning_message: 'Could not read the extraction service response.',
              _err: String(e && e.message) });
  }
  ```

  A thrown error inside a Node stops the flow and tells the form nothing. A returned
  warning object flows on and can be surfaced to the user.

- Carry a **`warning_status` / `warning_message` pair** through to the form. When an
  external model returns mostly nulls (a partially legible document), that is an
  *extraction quality* result, not a wiring failure — and the two are indistinguishable
  from the form unless the process says which it was.

## 6. The form side: detect arrival from the fields themselves

```js
/* The extraction is done when the platform has written into the fields — the
   outputMap populates them natively, so there is no carrier to read. Detecting the
   values themselves is also the honest signal: it is true exactly when there is
   something worth showing. */
function extractionArrived() {
  var found = false;
  fields().forEach(function (el) {
    if (found) { return; }
    if (!fieldKey(el)) { return; }
    var f = q('input, textarea', el);
    if (f && String(f.value || '').trim()) { found = true; }
  });
  return found;
}
```

## 7. The full pattern: upload → veil → reveal only what applies

```js
/* 1. The upload starts the work: raise a HELD veil (the network is silent, so the
      quiet-timer heuristic would lift it immediately). */
D.addEventListener('change', function (e) {
  var input = e.target;
  if (!input || input.type !== 'file' || !input.files || !input.files.length) { return; }
  if (!input.closest || !input.closest('.form-builder--file-upload')) { return; }
  if (currentStep() !== IDENTITY_STEP) { return; }     // other steps just collect documents
  window.__uxExtracting = true;
  showVeil('Reading the document…', true);
}, true);

/* 2. Every refresh pass decides what the step shows. */
function identityStep(active) {
  if (active !== IDENTITY_STEP) { return; }
  var arrived = extractionArrived();

  if (arrived && window.__uxExtracting) {              // 3. dismiss the held veil
    window.__uxExtracting = false;
    hideVeil();
  }

  var ready = true;
  fields().forEach(function (el) {
    if (q('input[type=file]', el) || el.querySelector('.form-builder--file-upload')) {
      return;                                          // the upload always stays
    }
    var key = fieldKey(el);
    if (!key) { return; }

    var group = FIELD_GROUP[key];                      // 'a' | 'b' | undefined
    var mine  = !group || group === currentApplicantKind();

    // Hidden until the document has been read, and then only the half that
    // belongs to the chosen applicant type.
    el.classList.toggle('ux-gated', !arrived || !mine);
    if (!arrived) { ready = false; return; }
    if (!mine) { return; }

    var ok = validate(el, key);
    if (el.offsetParent !== null && !ok) { ready = false; }   // only VISIBLE fields gate
  });

  gateNext(ready);                                     // 4. → appears only when complete
}
```

Three details that matter:

- **`el.offsetParent !== null`** is the real "is this visible" test. Counting a
  hidden field against readiness makes the next button unreachable forever, with no
  visible cause.
- **`FIELD_GROUP` decides visibility here as well** as in the form's own logic. The
  form's logic keys off its own state and runs on its own schedule; deciding here
  too means the step never shows the wrong half, not even for the frame between the
  results landing and that logic running.
- **The upload is exempt from every gate.** It is the only thing on the step before
  the results arrive, and it must stay reachable afterwards so a wrong document can
  be replaced.

## 8. Offer a manual escape

Extraction from a photographed document fails sometimes. When the veil's ceiling
fires, say so and let the person continue by hand — a form that can only be
completed when a model cooperates is not a form.

```js
window.UXToast('This is taking longer than usual. You can fill the fields in manually.', 'err');
```
