# Field gate and remediation standard

Use this reference when an Agent Skill controls a real tool, platform, browser,
database, filesystem, or other externally observable system. It governs field
acceptance and remediation; it is not a substitute for the domain playbook.

## Contents

1. Freeze the field contract before mutation
2. Enforce the verdict outside the acting agent
3. Count the complete causal execution tree
4. Treat gaps as predeclared design choices
5. Remediate without rewriting history
6. Route each lesson to the correct reusable layer
7. Avoid case-specific overfitting
8. Minimum field release record

## 1. Freeze the field contract before mutation

A field trial needs the same discipline as a fixed jury. Before any mutation, lock:

- target, scope, stable resource identities, and expected end state;
- exact agent/model/tool settings and a fingerprint of the complete skill package,
  including `SKILL.md`, references, scripts, and assets—not only the entrypoint;
- ordered required check IDs with binary pass conditions;
- direct proof source for each check;
- explicitly permitted degraded modes, fallbacks, or gaps;
- resource, write, submission, launch, and execution budgets;
- safety containment, evidence preservation, and cleanup/rollback obligations as
  separate checks, including their ordering and authorization;
- unknown-outcome and retry policy;
- promotion rule and the host component that computes the verdict.

A prose goal plus an agent-authored report is not a fixed field contract. The acting
agent must not get to redefine success after seeing platform behavior.

### Safety closeout is independent of business acceptance

Distinguish reversible safety containment from evidence-destroying cleanup. After target
and effect reconciliation, perform containment within existing approval independently of
business-output decoding; then re-read the actual safety state. If authorization is absent,
request the exact bounded action and report the remaining risk—do not infer permission.
Preserve needed evidence before authorized deletion or other evidence-destroying cleanup.
If evidence preservation and immediate containment conflict, follow the predeclared safety
policy or escalate; neither silently discard evidence nor leave exposure unreported.
A safe end state does not pass the business gate, and failed business proof does not cancel
an independently authorized safety obligation. The owning runner/controller must enforce
this separation even when report parsing fails; skill prose alone cannot guarantee it.

## 2. Enforce the verdict outside the acting agent

The execution agent may collect evidence and return each fixed check, but a controller
or deterministic reviewer should validate:

- every required check ID is present exactly once and in the registered order;
- every required value is a real Boolean and is true for a pass;
- no unexpected check silently replaces a required one;
- no unknown mutation or run outcome remains;
- every allowed mutation and resource count stayed within scope;
- temporary resources were reconciled and cleaned up;
- the claimed evidence comes from the required observation boundary;
- the report's gap status is permitted by the frozen contract.

The host computes the aggregate verdict. An agent-written `passed` or
`passed_with_gap` field is evidence to validate, not authority.

Independence means a different causal observation path, not another success flag. A writer
and verifier can share the same erroneous intermediate and agree on the wrong value. Bind
storage checks to the original request, exact keys and field types; predeclare transition
cases whose before-states can actually falsify the claim. A value already null cannot
prove that a concrete value was cleared. Multiple offline assertions are not independent
native observations, and final loop snapshots need not describe all earlier iterations.

For confidentiality claims, identify the first persistence boundary before running the
experiment. Sensitive values may reach response variables or controller logs before later
sanitization. Use source evidence or explicitly approved isolated synthetic canaries, not
real secrets, to test that boundary. Inactive creation and runtime acceptance are separate.

## 3. Count the complete causal execution tree

Budget the real side effects, not only top-level commands. One form submission,
webhook launch, schedule occurrence, or parent-process run may create several process
instances through awaited subprocesses or nested normalizers.

Record separately:

- external submissions or trigger deliveries;
- top-level process instances;
- child and nested process instances;
- data writes and affected business keys;
- created, edited, enabled, disabled, and deleted resources;
- generated files, notifications, and external calls.

A budget that says “one run” while ignoring its child instances is ambiguous and
cannot support a reliable cost or safety claim.
Unknown counts remain unknown: null is not zero, and absence of a declared child path
is not direct evidence that no child executed.

## 4. Treat gaps as predeclared design choices

A required outcome that fails is not converted into a gap merely because adjacent
behavior worked or the platform limitation is understandable.

A field phase may pass with a gap only when all of the following were registered
before execution:

1. the specific degraded mode is permitted;
2. the permitted fallback is bounded;
3. the fallback proves the user-relevant outcome at the same observation boundary;
4. safety and cleanup constraints still pass;
5. the final report names the missing native capability without implying it worked.

Otherwise the phase is blocked or failed. Discovery of a platform limitation is
valuable evidence, but it is not completion of the missing acceptance criterion.

Keep phase-local and aggregate verdicts distinct. A phase verdict covers only that
phase's frozen obligations and newly observed outcomes. An approved gap from an earlier
phase remains in project lineage or the aggregate report; it does not force every later
phase to report `passed_with_gap`. Conversely, a new local failure cannot be hidden as
an inherited gap. Host code should compute and preserve both verdict scopes separately.

## 5. Remediate without rewriting history

A verifier/parser error does not by itself establish that the action failed; a valid
observation of a missing required effect can. First ask whether existing attributable evidence
can answer the missing check without another execution. Reuse it
only when identity, input/version, observation boundary and freshness fit that claim.
A historical runtime result cannot prove current configuration or safety state after drift.
If evidence is insufficient, name the missing observation boundary; additional execution
still needs a separately approved budget. An observation-contract repair produces a new
attributable result, not an overwritten failure or silent relaxation of frozen checks.

When a field gate misses a required outcome:

1. preserve the original report, logs, IDs, screenshots, and before/after evidence;
2. classify the cause: domain assumption, skill instruction, source-owned reference,
   tool/runtime, platform capability, observation method, or field-contract defect;
3. write a separately approved versioned remediation contract with a narrower mutation
   and execution budget;
4. generate stable non-secret business keys before any retryable operation;
5. re-read current state and save pre-edit snapshots;
6. repair the smallest responsible layer;
7. rerun only the missing acceptance claim, never a successful destructive claim for
   cosmetic extra evidence;
8. reconcile unknown outcomes before another submit, launch, write, or run;
9. let deterministic host code validate remediation reports and promote the original
   phase only after all required checks pass;
10. archive the pre-remediation report and disclose the additional cost and mutations.

Credential exposure is monotonic for the exposed credential. Deleting a file, masking
a screenshot, or redacting a transcript copy does not make a completed
`no_secret_exposure` check true. Preserve the incident, revoke or rotate the credential
under a separately approved remediation, prove the old value is rejected and the new
value is distributed only through approved boundaries, invalidate stale exports or
reports, and then compute a new attributable promotion result.

Never edit the old report in place to pretend the first attempt passed. Promotion is a
new, attributable result built on preserved evidence.

Separate approval recording, checkpoint eligibility and execution receipts. A controller
must bind one approval to the exact phase, payload and reconciled before-state; recording
approval before discovering an ineligible checkpoint does not establish a completed action
or permission to replay another phase. Repeated manual archive/resume recipes belong in a
source-owned state machine with adversarial tests, not ever-longer skill instructions.

## 6. Route each lesson to the correct reusable layer

Do not turn every field incident into more top-level skill prose.

| Signal | Durable home |
|---|---|
| Stable platform/API semantic | Source-owned tool description or domain reference |
| Repeated deterministic construction error | Builder, schema, validator, lint, or script |
| General operational decision | Domain skill core or progressive reference |
| Evaluation/field-gate integrity defect | Meta-skill standard and controller test |
| Project-specific ID, title, payload, or workaround | Versioned field contract/evidence only |
| One unexplained observation | Preserve as provisional evidence; do not generalize yet |

Prefer a source-owned correction over duplication. Link to it from the skill when the
agent must change a decision, but do not copy volatile schemas into several places.

Separate repaired artifact proof from causal skill improvement. A successful typed-null
workaround after simultaneous script/mapping/instruction edits demonstrates that bounded
artifact outcome, not which skill edit caused it. Freeze sanitized incident cases in a
separate development corpus; preserve formal holdouts and historical failures. A changed
reference changes the skill package and needs fresh fingerprint-bound evaluation before
new release or superiority claims. Do not relabel old field passes as evidence for new bytes.

## 7. Avoid case-specific overfitting

Before changing a reusable skill, ask:

- Is the observation supported by a live schema, source, repeated trajectory, or a
  controlled counterexample?
- Does the proposed instruction change a recurring decision rather than narrate one
  project's history?
- Is this actually a skill issue, or can a tool/schema/controller enforce it better?
- Can the rule be stated without workspace IDs, project titles, one-off evidence keys,
  or exact remediation filenames?
- Which baseline success could the new rule break?
- What targeted regression case will prove the rule without making the full skill more
  specific to this incident?

A useful field lesson should become a small invariant, validator, or source-owned
reference. The detailed incident remains in evidence, not in the always-loaded skill.

Express the candidate rule as trigger → decision → limit. Add a structurally similar case
in a different domain and a counterexample where it must not apply, alongside a preserved
baseline success. If transfer requires the original field names or workaround, keep it
local or provisional. These are development cases, not transfer-performance evidence;
measured generalization still requires fresh held-out observations. Reject a new paragraph
when an existing rule already covers the decision; repair routing or enforcement instead.

## 8. Minimum field release record

Record:

- frozen contract/version and required check IDs;
- complete skill-package fingerprint plus model/tool settings;
- target and stable IDs, with secrets removed;
- model/client/tool versions when they affect execution;
- permitted gaps and actual gaps;
- phase-local verdicts and the separately computed aggregate/project verdict;
- exact mutation and full causal execution counts;
- direct proof per required check;
- unknown outcomes and reconciliation evidence;
- temporary-resource cleanup;
- credential exposures, revocation/rotation evidence, and stale-artifact invalidation;
- original and remediated reports when remediation occurred;
- source-owned documentation or code changes derived from the field evidence;
- residual limits and claims deliberately not made.
