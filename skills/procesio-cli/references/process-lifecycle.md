# Process lifecycle

## Goal

Create or change one PROCESIO process and prove both its saved design and representative runtime behavior.

## Preconditions

- Identify environment, workspace ID, credential profile, process ID for edits, representative input, and expected outputs/side effects.
- Run readiness/auth checks and resolve the process by stable ID.
- Use the `procesio` agent for a full build-and-test outcome. Use a narrow `procesio` tool action only for one explicit read or edit.

## Inspect

1. Read agent guidance for the current build/test doctrine.
2. Fetch the existing process and input payload shape when editing or running.
3. Inspect dependencies: data models, credentials, child processes, documents, webhooks, schedules, forms, and custom actions.
4. Record activation state and a compact before-state.
5. Before editing a process used by a form, webhook, schedule, or child process, snapshot its public variable IDs, types/directions, custom-response contract, and every dependent mapping. A seemingly additive output or response change can orphan callers.

## Preview and approval

- Build or edit through the structured process DTO path; use dry-run/validation before save when available.
- Inspect the generated action graph, mappings, branches, error ports, and output variables.
- Treat create, edit, activation, run, duplicate, import, and delete as mutations. Cross the MCP confirmation boundary only after the target and blast radius are explicit.
- If the create DTO is active by default, state that explicitly. Confirm whether any attached webhook, schedule, form event, or other trigger could launch it autonomously. An active process with no trigger still requires approval to run, but it has no autonomous launch path.
- State whether a representative top-level run can create child or nested instances and include those in the execution budget.

Check catalog input-port/output-port declarations against every convergence, backward edge
and error path **before freezing** a graph. Use supported Join semantics where appropriate;
a Join is not a universal loop repair. Validate the composed DTO and later prove actual
execution. A frozen incompatible graph requires an explicit versioned amendment, not a
silent redesign. Preserve runtime/designer bindings, including nested attribute paths.

### Sensitive API responses: gate before acquisition

For scanners, exports or integrations, locate the **first persistence boundary**: API response
variables, action/instance diagnostics, child-agent stdout and coordinator logs may retain
values before downstream hashing or redaction. Read-only access does not make a saved
configuration non-sensitive. Retention deletion after execution cannot prove non-exposure.

Before retrieving potentially sensitive configurations, require implementation evidence of
pre-persistence suppression/redaction or a separately approved isolated synthetic canary
experiment covering success, error and diagnostic paths. Never use real secrets as probes.
If that boundary is unproved, keep runtime acquisition blocked. An inactive creation preview
may still be reviewed separately, but does not authorize activation or a scan; ensure the
creation path cannot auto-execute. Offline checks/non-saving validation do not clear this gate.

## Execute

- Save one coherent process version.
- Validate it at the source platform.
- Apply layout or action-name cleanup only when it does not change behavior.
- Preserve existing public input/output IDs and direct-caller response semantics when the process has dependents. When a new envelope is needed for one caller type, add it compatibly rather than replacing an established output contract.
- Execute the representative payload **exactly once**. Prefer the `procesio` agent verification path with `--run` because it validates, audits parity, runs, and reads instance status in one operation.
- Do not also call `run-process` before or after `verify --run` merely to obtain the same proof. If a representative run was already launched, inspect that instance directly and run non-executing validation/audit checks instead.
- Do not blind-retry a timed-out run; reconcile instances first.

## Verify

Minimum proof:

1. Re-fetch the process and compare the saved design with the intended DTO/graph.
2. Re-fetch every dependent form/process/trigger mapping after a public-interface edit and prove no variable ID or response contract was orphaned.
3. Use one execution path only:
   - preferred: `procesio` agent `verify --run`, then use the returned instance ID for output inspection; or
   - direct `run-process` once, followed by explicit instance-status/output reads and a non-running audit.
4. After a successful `verify --run`, call `get-instance-output` directly with the returned instance ID and process ID. Do not add `list-instances` as routine confirmation when the instance ID is already known; reserve it for a missing ID, timeout/unknown outcome, or reconciliation.
5. Read the real instance status, inputs, outputs, and error details. Status alone is not proof of the expected output value.
6. When the process calls subprocesses, capture the complete parent/child tree needed for the claim. Distinguish one external submit/run from the number of process instances it created.
7. Verify external effects at their boundary: database row, generated file, API result, email sink, or child instance.
8. Run the static audit for secrets, missing error handling, inefficient patterns, and designer/runtime mismatch.

Validation alone does not pass this playbook. Two successful executions are not stronger evidence when one representative execution and direct output inspection prove the same claim.

## Recovery and cleanup

- Validation failure: correct the DTO or mappings before another save.
- Unknown run outcome: list/reconcile instances by process and time before rerunning.
- Failed required field outcome: preserve the original report and successful evidence. Use a separately approved bounded remediation for only the missing path; do not rerun successful side-effecting claims for cosmetic proof.
- Failed test mutation: reconcile actual effects and obtain approval for any restoration or follow-up corrective edit; do not delete evidence before recording the failure.
- Treat approved safety containment separately from fixture deletion: after target/effect reconciliation, disabling temporary execution paths and verifying their state does not depend on successful output decoding. If not already authorized, preview the exact action and obtain separate approval; report any active-state risk while waiting.
- Preserve needed evidence before evidence-destroying cleanup. Do not delete a process, instance history or fixture merely to hide a failed check. Safety state and business-output acceptance are separate results; verify and report both.
- For a disposable smoke test, delete the process only after its process ID, instance ID, validation result, runtime status, and expected output have been captured. Re-list the workspace to prove cleanup.

## Evidence

Return environment/workspace/process/instance IDs, parent/child execution counts, validation result, runtime status, relevant outputs or side-effect proof, dependent-caller compatibility, audit findings, cleanup result, and any manual production check still open.
