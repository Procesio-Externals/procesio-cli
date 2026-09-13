# Schedule process-input security

This note records a live-observed security property of the PROCESIO schedule API.
It belongs beside the curated schedule handler because it describes the wire and
storage behavior of `/api/Schedules`, not one project's workflow.

## Observed contract

Observed in a bounded deployment trace on 2026-09-05; deployment identifiers and
private receipts are intentionally not published. These observations are not a
platform-wide retention guarantee or fresh runtime verification:

- values supplied in a schedule's `processInputs` are persisted as part of the
  schedule definition;
- `GET /api/Schedules/{scheduleId}` returns those values without masking them;
- saving a schedule GET response, debug dump, transcript, screenshot, or report can
  therefore disclose any token, password, API key, or other secret placed there;
- redacting a local artifact after the read does not undo disclosure to an already
  captured transcript or external log;
- a claim that the clear value exists “only in a local protected file” is false while
  the same value remains in a readable schedule definition.

The curated `get-schedule` action preserves the raw API DTO by default for backward-
compatible round-tripping. Use `get-schedule --redact-process-inputs` for ordinary
inspection and evidence; it copies the DTO while replacing each non-null returned
`processInputs[].value` with `[REDACTED]` and preserving null. This projection only
covers those fields, not arbitrary secrets elsewhere in the response. Generic
requests and raw get mode retain clear values; classify those reads before use.

## Required handling

1. Prefer a target process that resolves authentication through a named credential,
   secret store, or other runtime reference instead of receiving a long-lived secret
   as a literal schedule input.
2. When a literal secret is temporarily unavoidable, use a dedicated least-privilege,
   rotatable value. Do not reuse a personal or broad administrative credential.
3. Pass a secret-bearing create/update payload through a protected `@file`, not inline
   JSON that may enter shell history, process listings, or logs. Delete the temporary
   file only after the write outcome is reconciled.
4. Restrict `Schedule.Read` and artifact access to principals that may read the secret.
5. Use `get-schedule --redact-process-inputs` for diagnostics and ordinary evidence.
   Record permitted structural metadata, not literal values. Non-null values become
   a marker, so their original types are not preserved by this projection.
6. After any accidental transcript, log, screenshot, or artifact exposure, treat the
   value as disclosed and rotate it. Update every dependent hash, schedule input, and
   protected local source as one reconciled change.
7. Under separate approval, verify that the old value is rejected and the new value
   succeeds. A redacted structural read cannot prove which value was saved: use an
   approved protected comparison for that claim without emitting either clear value.
   Review retained evidence separately for possible exposure.

## Evidence boundary

A safe schedule-security claim needs all relevant storage boundaries:

- protected local source and its permissions;
- process definition or credential reference;
- schedule `processInputs` as a redacted structural summary;
- transcripts, logs, screenshots, exports, deployment manifests, and saved API reads;
- rotation or revocation proof after exposure.

A clean local-file sweep alone does not prove that the platform-side schedule copy or
an external transcript is clean.
