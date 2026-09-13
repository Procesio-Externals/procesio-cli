# Capability change contract

## Tool or agent addition

Define before implementation:

- unique shell-friendly name;
- user jobs and routing triggers;
- action names and typed arguments;
- read versus mutation classification;
- credential and machine requirements;
- stable success and error JSON;
- idempotency or unknown-outcome behavior;
- cheapest health check;
- direct verification method.

Update the manifest in the same change as the implementation. Regenerate derived manuals/router output and fail CI on drift.

## Tests

Cover:

- argument parsing and required fields;
- success envelope and exit code;
- normalized failure envelope;
- structured JSON passed as one argv element;
- no secret echo, including secret-bearing reads (saved input/default values, not only credentials endpoints);
- dry-run or preview for dangerous writes where possible;
- reversibility gate behavior;
- one client-level invocation path.

Use fakes for unit tests and a separately gated live test for external systems.

A read-only action can still disclose a credential. For secret-bearing DTOs, test a redacted projection with a synthetic sentinel in every supported literal position, including nested/list values, and verify non-sensitive structure survives. Keep raw compatibility behavior explicit; examples and evidence collectors must choose the safe projection. Do not infer secrecy from a field name or from the absence of mutation.
