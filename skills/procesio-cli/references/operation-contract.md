# PROCESIO operation contract

## Contents

- Executor selection and inventory evidence
- Safety boundary and field acceptance
- Retry classification and coordinator resumption
- Proof standard and comparison boundaries

## Executor selection

| Work shape | Executor |
|---|---|
| Multi-step process build, verification, or audit | `procesio` agent |
| Connector generation through live PROCESIO testing | `connector-builder` agent |
| One known platform operation | Registered tool action |
| User-visible form behavior | `web` tool after platform creation/edit |
| Database side effect | `sqlserver` or `mysql` after the process run |
| Workbook content | `xlsx` after file creation/download |
| Capability unknown | Bounded capability search, then inspect one schema |

## Inventory evidence

Inspect the actual response envelope and resource-specific ID field before projecting it;
missing projected fields are not evidence that resources are absent. Keep output allowlisted
and metadata-only. Permission denied is not not-found. Reconcile returned page metadata,
unique stable IDs and reported totals; a requested next page returning the same page/IDs is
not traversal proof. State observed coverage and use a registered paged read where available,
never assume an unpaged or truncated listing is exhaustive.

## Safety boundary

Before a read, export or diagnostic fetch, classify whether its response can contain
sensitive values and where those values first persist or appear in output. Read-only is
not confidentiality-safe by definition. For such data, apply the pre-acquisition gate in
`references/process-lifecycle.md` before fetching it, regardless of the selected playbook.

A read result may authorize another read; it never authorizes a write. Before a mutation, establish:

- exact environment and workspace;
- stable target ID;
- expected before and after state;
- whether the operation is reversible;
- preview or validation result when available;
- explicit operator approval of the exact action and side-effect budget, for CLI and MCP alike.

Run, test, submit, enable, and trigger operations may cause writes or external effects even when labeled verification. Approval for configuration changes does not automatically include these operations or cleanup. Preview the full causal scope and obtain separate approval for any additional action; when withheld, preserve a configuration-only verdict.

Never place credentials in command arguments unless the repository action explicitly performs secure credential capture and no safer prompt/store path exists. Never echo a secret into evidence.

## Field acceptance and remediation

For a staged or multi-resource field project, freeze before the first mutation:

- ordered required check IDs and their direct proof boundary;
- explicitly permitted degraded modes and equivalent fallbacks;
- resource, write, submission, trigger, and execution budgets;
- cleanup and rollback obligations;
- unknown-outcome policy;
- the deterministic controller that validates reports and computes promotion.

The execution agent may collect evidence, but its own `passed` or `passed_with_gap` label is not authority. A required outcome that fails remains blocked unless the frozen contract already permitted a fallback that proves the same user-visible result. Preserve the original report and use a separately approved, versioned, narrower remediation; do not relabel history after discovering a platform limitation.

Scope each phase verdict to that phase's own obligations. A previously approved gap remains in project or aggregate lineage; it does not make every downstream audit phase `passed_with_gap`. Preserve both scopes explicitly: the current phase may be `passed` while the overall project remains `passed_with_gap`. A new local failure may not be disguised as inherited.

Count the complete causal tree. A form submit, webhook launch, schedule occurrence, or parent-process run may create child and nested process instances. Report top-level deliveries, parent/child instance IDs, data writes, and generated artifacts separately so cost and side-effect budgets are real.

## Retry classification

| Result | Retry rule |
|---|---|
| Explicit validation failure before send | Correct input; safe to retry |
| Read-only request failed before response | Retry with bounded backoff if transient |
| Write returned a stable error proving no commit | Correct cause; retry once appropriate |
| Write timed out, connection reset, or response was lost | Unknown outcome: re-read first; never blind retry |
| Write succeeded but verification failed | Investigate state; do not repeat mutation as a repair guess |

A remediation is not permission to replay a successful claim. Re-run only the missing acceptance path, with a stable business key chosen before execution, after current-state and concurrency checks.

### Coordinator resumption and operator interaction

Approval recording, checkpoint eligibility and actual execution are separate states.
Before giving a resume command, inspect the saved report, approved bytes and committed
receipts. If a blocked checkpoint prevents entry, adding an approval flag is not a resume
mechanism. Use the owner's supported history-preserving path; if none exists, route the
state-machine defect to the runtime maintainer. Do not silently delete reports or reuse
an old approval after changing payloads, before-state or phase scope.

Recover already supplied metadata and successful evidence instead of restarting discovery.
Offer one bounded next step, explain precisely what it authorizes, and keep bookkeeping
inside a reviewed helper where possible. A transport interruption requires checking whether
work started or committed, not automatically relaunching it. Keep selected-phase success
separate from aggregate project acceptance; a banner, exit zero or artifact existence is
not proof that pending phases completed. Do not promise a one-command finish across unknown
platform boundaries or turn operator frustration into blanket execution permission.

Before another diagnostic step, name the unresolved claim, the smallest observation that
could change the decision, the responsible owner and a stop condition. When available
reads cannot close the proof gap, stop the chain and hand off that gap. Offer an authorized,
clearly scoped artifact from existing evidence when useful, with demonstrated outcomes,
unknowns and the next decision visible. A synthetic/component walkthrough is not retroactive
acceptance of a blocked integration; packaging evidence creates neither new runtime proof
nor permission to publish. Honor the operator's chosen execution interface without making
them repeat already captured evidence or bookkeeping.

## Proof standard

Select evidence at the same boundary the user cares about:

- API/DTO state for configuration outcomes;
- runtime instance for process outcomes;
- native browser interaction plus diagnostics for form outcomes;
- database query for persisted data outcomes;
- downloaded file inspection for document outcomes;
- installed package plus action invocation for connector outcomes.

Do not substitute a manual DOM patch, direct internal writer call, old instance, or API-only simulation for proof that a form's native event path rendered the result. Do not substitute an attached webhook DTO for proof that its real payload mapping launched and completed the intended instance.

Keep the evidence small: IDs, status, relevant fields, output digest/path, and diagnostics. Avoid dumping secrets or entire payloads when a few fields prove the result.

### Comparison boundaries

Classify identity, authored semantics and representation separately. Bind environment,
workspace/resource/instance IDs and required parent relationships before using labels or
normalization. Compare only projections whose equivalence is established by a versioned
source contract; a saved definition and a runtime projection need not expose the same fields.

For a documented non-semantic difference, use a copied comparison view, retain the untouched
original evidence, and disclose exact field paths and the normalization rule. Do not silently
strip unknown fields, error bindings, control flags or authored values to get a pass. Preserve
missing/null and Boolean/integer distinctions unless the source contract explicitly defines
their equivalence for this check. Happy-path output does not prove error-path semantics.

Prefer predeclared comparison rules. A mismatch discovered after execution needs bounded
read-only diagnosis and, if warranted, a reviewed versioned verifier/contract correction at
its owning layer with negative controls for meaningful changes. Preserve the original failed
report; any revised interpretation is a new attributable result, not silent acceptance or
permission to replay the action. If semantics remain unproved, retain the affected gap.
