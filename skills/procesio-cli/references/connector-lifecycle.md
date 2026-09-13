# Connector lifecycle

## Goal

Turn external API documentation into a compiled PROCESIO custom action, install it in a controlled workspace, and verify its intended operations and failure behavior.

## Preconditions

- Define the API source, required operations, authentication mechanism, pagination, rate limits, error shapes, file flows, and target workspace.
- Confirm connector-builder and PROCESIO credential readiness without exposing secrets.
- Decide which live calls are safe; prepare a sandbox or read-only endpoint and non-sensitive fixtures.

## Inspect

1. Use the `connector-builder` agent guidance/checklist and read the live build state.
2. Review the generated plan for operation names, inputs/outputs, authentication fields, retries, pagination, and PROCESIO type mappings.
3. Inspect any previous compile/test feedback before regenerating.

## Preview and approval

- Approve the build plan separately from code generation and separately from installing/testing in PROCESIO.
- Inspect package identity/version and target workspace before upload.
- Do not run write/delete/payment/email operations merely because they were generated; select explicit safe tests.

## Execute

1. Drive gather → plan → generate → compile through the `connector-builder` agent.
2. Download the resulting `.nupkg` and retain its digest/build ID.
3. Upload/install it in the target test workspace.
4. Run the custom-action test or a minimal process using controlled credentials and inputs.

## Verify

- Package installs and appears under the expected identity/version.
- Each required operation maps inputs, outputs, nulls, collections/files, and errors correctly.
- Authentication secrets are credential fields, not source, logs, package metadata, or outputs.
- Pagination/rate-limit/retry behavior is demonstrated where in scope.
- At least one expected provider error becomes a useful stable connector error.
- A PROCESIO process can consume the returned data shape.

## Recovery and cleanup

On test failure, feed concrete compile/runtime evidence back into the same build and change the smallest responsible layer. Remove the failed package only when safe and preserve the prior working version for rollback. Revoke disposable API credentials after testing.

## Evidence

Return build ID, artifact name/digest, installed custom-action ID/version, operations tested, sanitized input/output/error evidence, target workspace, rollback version, and untested destructive/provider paths.
