# Schedules and webhooks

## Goal

Create or change a time/event trigger and prove that its saved configuration launches the intended process exactly as designed.

## Preconditions

- Identify workspace, target process ID, trigger ID for edits, payload mapping, timezone, recurrence/event contract, activation state, concurrency/idempotency policy, and test window.
- Confirm the target process validates and can run with a controlled payload before attaching an automatic trigger.
- Determine whether any schedule process input is sensitive. Literal `processInputs` values may be persisted and returned unmasked by schedule reads; prefer a named credential, secret-store reference, or runtime lookup when the architecture supports it. Before any potentially sensitive schedule read (including the initial fetch), verify in the installed local help/schema that `get-schedule --redact-process-inputs` is available. If absent, stop and request an approved safe projection before acquisition; never silently fall back to raw output.
- For a webhook, determine the live payload-binding granularity before designing the target process. A generated webhook body is a typed model object; do not assume the platform can fan its fields directly into several primitive process inputs.

## Inspect

1. After the pre-acquisition checks above, fetch existing schedule/webhook, target process, notifications, activation, timezone/recurrence, and recent related instances.
2. Check duplicate or overlapping triggers and downstream rate/concurrency limits.
3. For a schedule with non-empty process inputs, use `get-schedule --redact-process-inputs` for ordinary inspection and evidence. Use the raw mode only when exact values are strictly needed, the observation boundary is protected, and the exact sensitive acquisition is explicitly approved; treat that result as secret-bearing. Raw mode is not a compatibility fallback for missing redaction support.
4. For webhooks, inspect authentication/signature expectations, sample body, generated body model and attribute IDs, response behavior, replay handling, secret exposure, and the exact `WebhookVariableDto`/attachment shape.
5. Inspect the complete process tree the trigger can create. One delivery may create a trigger-target instance plus awaited child and nested instances.

## Preview and approval

- Prefer creating schedules disabled and webhooks unattached/unshared until configuration review.
- Show next run times in an absolute timezone, target process, redacted payload shape, notification recipients, and public endpoint exposure.
- Enabling, sharing, invoking, updating, or deleting a trigger is a mutation requiring the exact target to be approved.
- Predeclare one stable event/business key, one launch window, the maximum trigger deliveries, and the full parent/child instance budget.

## Execute

- Save the trigger once and re-fetch it through the redacted mode when process inputs are present.
- For a schedule, enable only for an agreed controlled occurrence or invoke the underlying process separately before enablement.
- Do not place a long-lived or broad credential in literal schedule inputs when a reference-based design is available. When a literal secret is temporarily unavoidable, use a dedicated least-privilege rotatable value, stage the payload through a protected `@file`, restrict schedule readers, and never echo the raw read DTO.
- For a webhook, launch with a signed/controlled sample using the intended content type and headers.
- Bind a webhook's generated body to one compatible model-typed process input. When the retained target exposes primitive inputs, use a bounded adapter process that accepts the whole body, extracts attributes deterministically, and calls the retained target through plain variables. Do not repeat a failed per-field primitive mapping.
- Keep a test adapter temporary unless it is part of the reviewed architecture. Bind scripting Error outputs, use nonzero timeouts, and preserve the retained target's public variable IDs.
- Do not blind-retry a webhook request after an unknown response; reconcile by event/business ID and time window.

## Verify

- Saved recurrence/timezone or webhook schema/auth settings match intent.
- Exactly one expected delivery is associated with the controlled event/window.
- The complete trigger-target/child instance tree is reconciled; inputs, final statuses, outputs, notifications, and external side effects are correct.
- For a schedule-secret claim, account for both the protected source and the platform-side schedule copy. A clean local-file sweep does not prove the schedule definition or an external transcript is clean.
- For a webhook, prove the model object reached the intended model-typed input or adapter, the extracted primitive values are correct, and the final business-key side effect exists exactly once. An attached DTO plus a never-started instance is not a passing mapping test.
- Duplicate delivery, missed run, clock/DST, overlap, and disabled-state behavior are covered where material.

## Recovery and cleanup

On unexpected firing, duplication, or payload mismatch, reconcile target/effects and promptly perform the exact approved containment (disable trigger or revoke test access), then re-read its state. If not covered, request separate approval and report the active risk. Containment must not wait for successful output decoding. Preserve event IDs and instance evidence before authorized fixture deletion; never treat shared production triggers as test cleanup. Apply the containment/evidence separation in `references/process-lifecycle.md`.

After a schedule input appears in a transcript, log, screenshot, or retained artifact, treat it as disclosed rather than merely redacting the local copy. Rotate it and reconcile every dependent process hash, schedule input, and protected source before claiming recovery.

For a temporary webhook adapter, detach the webhook first, revalidate retained processes, delete the webhook and adapter, then prove zero matching public endpoints, adapter processes, and live references to the generated webhook model remain.

## Evidence

Return trigger/process IDs, generated webhook model and relevant attribute IDs, absolute test time or event ID, saved configuration summary, activation state, delivery count, full parent/child instance tree, side-effect proof by stable business key, adapter cleanup, and recurrence/replay scenarios not yet exercised. Redact every literal schedule input value; record only variable identifiers, value presence/type, and the separate protected source or credential reference.
