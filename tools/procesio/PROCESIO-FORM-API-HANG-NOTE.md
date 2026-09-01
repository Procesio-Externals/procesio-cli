# PROCESIO forms over the API — what works, and the one call that hangs

Live-probed while shipping a form for a marketplace template. The folklore is "form
creation hangs over the API". That is **wrong, and the imprecision costs a build**: creation
is fine. The call that hangs is the **read**.

| Call | Endpoint | Result |
|---|---|---|
| `form-create` | `POST /api/FormTemplate` | ✅ **works** — returns the new form id; the form renders with all its controls |
| `form-list` | `GET /api/FormTemplate/all/basic` | ✅ works (fast) |
| `get-customurl-formtemplate-by-id` | `GET /api/CustomUrl/FormTemplate/{id}` | ✅ returns (empty until a CustomUrl is minted) |
| **`form-get`** | **`GET /api/FormTemplate/{id}`** | ❌ **HANGS** — no response, no error; killed at 90s |

## The consequence: nothing that must READ a form first can run

Every surgical/read-modify-write form action reads the form before writing, so they all
inherit the hang: `form-set-element-event` (wiring a control to `RUN_PROCESS`),
`form-set-element-config`, `form-get-element`, `form-get-element-events`, `form-set-code`,
`form-update`, `form-edit`. A wiring dry-run never even reaches its write.

**Practical rule:** everything a form needs must be expressed in the **single `form-create`
call**, because you may not get a second bite at it over the API. Build the complete element
tree, theme, and (where the builder supports it) events in that one create. If a form must
be adjusted afterwards, expect to do it in the designer UI.

**Do not** try to work around the hang by re-creating the form on every change: each
`form-create` mints a NEW form id (and any URL you minted points at the old one). Prefer one
correct create, then the UI.

## Wiring a form's submit to a process, in the UI (the fallback recipe)

1. Open the form in the designer, select the submit button, add an event on **click**:
   **Run process** → pick the process.
2. Turn **syncRun ON** ("wait for the process to finish"). With it off, the form fires and
   forgets and no output can ever populate.
3. Map **inputs**: each form field → the matching process input variable (file upload →
   the `FileDataModel` input; a file control already holds a *list*, which is what a
   file-typed process input expects).
4. Map **outputs** the same way if results are shown back on the form. Design rule: one
   output variable per field, all primitives — mapping one structured object
   attribute-by-attribute is what produces `[object Object]` in every field.
5. Publish, then mint the public URL (CustomUrl) if the form should be reachable
   without a login.

## Wire the process INSIDE the create — it works, and it is the only way here

Because `form-set-element-event` cannot run (it reads first), declare the trigger in the
`form-create` config itself. The builder resolves names on both sides, so the config stays
readable and no GUIDs are hand-written:

```json
{"type":"button","name":"btn_run","label":"Run","submit":true,
 "events":[{"on":"click","do":"process","processId":"<pid>","syncRun":true,
   "inputs":  [{"to":"<process input var>", "from":"<form field name>"}],
   "outputs": [{"to":"<form field name>",   "from":"<process output var>"}]}]}
```

Verify the built DTO before trusting it: every map row's form side must be a 4-segment
value path (`formId.FIELDS_NS.elementId.valueConfigId`). A row still holding the raw field
**name** is silently broken - the API accepts it, the designer renders it blank, and the
field never populates.

### Two builder defects this exposed (both fixed in `dto/form/builder.py`)

1. **Field paths resolved in declaration order.** `ctx['field_paths']` is filled as
   elements are built, so a trigger declared *above* its target fields could not resolve
   them. That is the normal layout for any form that shows results (the submit button sits
   above the results panel), so every output map silently kept raw names. Fixed with a
   second pass (`_resolve_late_field_refs`) that re-resolves event map rows once every path
   is known; declaration order no longer changes the wiring.
2. **Controls whose value config is not called `value` never registered a path.** A
   `file-viewer` holds its file in **`src`** (its own empty state reads "Field source not
   set"), while `_VALUE_TYPE` already types it as File. So it received a data-model
   attribute but no field path, and could not be targeted by an output map. Fixed with
   `_VALUE_CONFIG_KEY` / `_value_key()`, used for both path registration and the
   data-model attribute typing, so `src` is typed File rather than String.

**Design rule that still applies:** one output variable per field, all primitives. Add a
small splitter action per display field that returns a plain string, rather than mapping
one structured object attribute by attribute (which writes `[object Object]` everywhere).

## Building the form in one create — shape that worked

`form-create --config-file` with a flat `elements` list; each control is
`{type,label,name,required,...}` and the submit is `{"type":"button","submit":true}`.
Types used successfully: `heading`, `paragraph`, `file-upload`, `datetime-input`, `input`,
`number-input`, `button`. `isPrivate:false` + `publish:true` makes it public and published.
A control's `name` is also the **URL query-param key** for pre-filling, so pick stable,
URL-safe names.
