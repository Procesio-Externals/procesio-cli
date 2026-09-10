# Form `RUN_PROCESS` synchronous result notes

These notes cover native form output mapping after a synchronous process event. They
are based on the form builder contract plus a live browser/process/ledger field trace
on 2026-09-05. The trace is historical and not a public proof packet; publication
of these notes does not reverify the deployed browser/runtime. Confirm compatibility
with the target runtime before relying on this response shape.

## Mapping direction

The form builder resolves both input and output mappings with the process variable on
the left and the form field value path on the right:

- input spec `{to: processVariable, from: formField}`;
- output spec `{to: formField, from: processVariable}`.

The process side must resolve to the stable process-variable GUID. Re-fetch and compare
mappings after any process edit that could replace variable IDs.

## Native synchronous writer contract

A successful synchronous process execution is not sufficient for visible output-map
updates. The form runtime's native writer consumes a process-variable collection from
the launch response's `content.variable` path. When the process custom response is an
arbitrary business object without a compatible `variable` member, the process can:

- finish successfully;
- write its database/data-store side effect;
- return a useful object to an API caller;
- yet leave the form's mapped result fields unchanged.

For a process shared by form, CLI, and subprocess callers, use a compatibility envelope
rather than replacing the established response:

```json
{
  "decision": "<existing top-level field>",
  "summary": "<existing top-level field>",
  "next_action": "<existing top-level field>",
  "duplicate": false,
  "response": {"<optional complete original response>": "..."},
  "variable": ["<exact live process-variable instance objects>"]
}
```

The example is structural, not a DTO to copy literally. Through an approved protected
inspection, establish the exact entry shape, IDs, value encoding, list flags and types
expected by the deployed runtime. Do not return the entire instance variable array:
only expose outputs the form caller is authorized to see, never credentials or internal
state. Keep existing permitted business fields at their established top-level paths.

Point the process custom response at the compatibility envelope and keep the ordinary
process outputs present. Bind any Node/Javascript Error output and set a nonzero timeout.

## Proof standard

A native output-mapping claim passes only when one real form interaction:

1. opens the published form in a clean browser context;
2. submits or clicks exactly once with a stable business key;
3. observes the real launch response;
4. updates the mapped fields automatically through the platform event path;
5. shows the expected decision and non-empty next action;
6. reconciles the exact process instance and storage side effect;
7. has no unexplained console, page, network, or response errors.

Do not call the SPA writer manually, patch result fields in the DOM, replay the request,
or feed an older instance into the writer as proof. Those techniques may diagnose the
expected shape, but they do not verify the native form path.

## Secret and compatibility rules

- Never store an access token as a form default or in plaintext form code.
- Exclude secrets before screenshot, log or response capture; masking afterward cannot
  undo an earlier disclosure.
- Snapshot process variable IDs and the old custom-response shape before editing.
- Re-fetch dependent forms and subprocess mappings after the edit.
- Preserve direct CLI/subprocess response semantics; additive envelopes are safer than
  replacing an established response object.
- Count the form-triggered process and every awaited/nested child in execution budgets.
