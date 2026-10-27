---
name: procesio-cli
description: >-
  Operate and troubleshoot PROCESIO resources through this repository's CLI or MCP.
  Use when inspecting, creating, editing, running, validating, auditing, exporting,
  importing, scheduling, triggering, testing, or verifying a PROCESIO process, form,
  document, webhook, credential, data model, custom action, workspace, or execution instance.
version: 1.0.4
owner: procesio-cli maintainers
last_verified: 2026-09-09
baseline_version: da12de643c8a2355d019f40515766abf80a819df
eval_suite: evals/evals.json
source_policy: generated
routing:
  triggers:
    - operate or troubleshoot a PROCESIO workspace through the CLI or MCP
    - create, edit, run, validate, audit, export, import, schedule, trigger, test, or verify a PROCESIO resource
    - inspect a PROCESIO process instance, form, document, webhook, credential, data model, or custom action
  primary_action: capabilities
  example: get-skill.py procesio-cli --content
---

# Operate the PROCESIO CLI

Use this skill to **do work against a PROCESIO installation**. It chooses and sequences the repository's tools and executable agents; it does not replace their manifests or duplicate their action catalog.

## Boundary

- Product fit, pricing, sizing, comparisons, compliance, or automation strategy without a requested platform change: use `procesio-platform-advisor`.
- Optimize T-SQL itself: use `sql-server-optimizer`. Return here to verify the surrounding process.
- Author, refactor, or evaluate an Agent Skill: use `agent-skill-engineer`. Repository code, manifests, MCP, CI, and skill integration belong to `procesio-cli-maintainer`.

## Operating workflow

1. **Name the outcome and target.** Identify the environment, workspace, resource type, stable ID, expected end state, and whether the request permits a mutation. Resolve names to IDs with read actions before changing anything.
2. **Discover, do not guess.** Use bounded MCP capability search when supported by the installed schema, or inspect the exact registered capability through local CLI help/manifests. Do not invent an action or argument from memory.
3. **Check readiness, then obey the result.** Run the tool inventory and the cheapest read-only authentication or health check. If `check-auth` returns `authenticated: false`, stop all remote platform calls. `mode: apikey` or `mode: userpass` names the stored profile type; it is not evidence of successful authentication. Use only local non-secret metadata commands until the credential is corrected and `check-auth` explicitly returns `authenticated: true`.
4. **Choose the narrowest executor.** Use an agent for a complete methodology and a tool for one explicit operation. Prefer curated actions over generated endpoint wrappers; use raw request only as a documented escape hatch.
5. **Read current state.** Fetch the resource and any dependency that constrains the change. Save IDs and relevant before-state in the working record.
6. **Preview the mutation locally.** Inspect the exact payload and intended effect without dispatching it; explain the expected blast radius. A dry-run or validation call is safe only if its installed contract proves no side effects. Creating a draft/disabled resource is still a mutation requiring approval.
7. **Cross the approval boundary once.** A user request to design or investigate is not permission to mutate. Obtain explicit operator approval of the exact action, target, payload and side-effect budget BEFORE either CLI or MCP execution endpoint. Do not call the unconfirmed MCP path as a preview: inherited argument-insensitive gating can execute a mutation there. The confirmed variant is not the sole gate; both paths require prior approval. Never split one hidden broad mutation across several apparently narrow calls.
8. **Execute once, then observe.** Do not retry a write until you know whether the first request committed. Treat timeout and transport loss as unknown outcomes and re-read state.
9. **Prove the real result.** Re-read the saved resource, run the process, inspect the instance, exercise the browser, query the database, or download the produced file—whichever observes the user's actual outcome.
10. **Report evidence.** Return the target IDs, action taken, before/after facts, proof performed, and checks that remain manual. A successful HTTP response alone is not completion.

Read `references/operation-contract.md` for executor selection, inventory coverage, approval/checkpoint resumption, comparison boundaries, and scoped delivery when proof is blocked.

Verification is not additional execution permission. The matrix and commands below describe proof paths, not authorization to run them. Obtain explicit approval for any run, test, submission, trigger or other side effect outside the approved scope; otherwise report configuration-only verification and the missing runtime proof. Reuse the approved run's instance ID instead of running again for evidence.

## Playbook router

Load only the playbook that matches the requested outcome:

| Outcome | Playbook |
|---|---|
| Create, change, validate, run, or audit a process; gate sensitive response acquisition | `references/process-lifecycle.md` |
| Diagnose a failed, silent, or incorrect process run | `references/process-debugging.md` |
| Build or change a form and verify it as a user | `references/form-e2e.md` |
| Generate, install, test, and improve a custom-action connector | `references/connector-lifecycle.md` |
| Move resources across workspaces or installations | `references/transport-environments.md` |
| Create or change schedules and webhook triggers | `references/schedules-webhooks.md` |
| Create documents, run generation, and inspect produced files | `references/documents-files.md` |
| Change data models or prove native datastore/database/workbook effects, including nullable mappings | `references/data-verification.md` |
| Configure profiles, workspace scope, credentials, users, or API keys | `references/credentials-admin.md` |

## Discovery and setup

Run repository-root CLI commands from the configured source checkout, not from an installed skill directory. Before any operation, enforce the approved profile, environment, workspace and action scope; examples omit installation-specific selectors, which must be supplied explicitly. Local discovery is not permission for remote reads or execution.

```bash
python scripts/list-tools.py
python scripts/run-tool.py procesio check-auth
python scripts/run-tool.py procesio list-processes
```

MCP is optional. Inspect the installed schema first: use a narrow `query` and optional `name` on `capabilities` only when supported; otherwise use local CLI help/manifests. Likewise, use `get_skill` with a `resource` field only when that feature exists. Coding agents can read referenced files natively, relative to this skill root; no MCP resource extension or CLI resource flag is required. Load only the needed file.

## Choose agent or tool

### Process lifecycle

Use the `procesio` agent when the work includes building, validating, executing, or auditing a process as one outcome:

```bash
python scripts/run-agent.py procesio guidance
python scripts/run-agent.py procesio verify --process-id <id> --run --payload '{}'
python scripts/run-agent.py procesio audit --process-id <id>
```

Validation is a prerequisite, not proof of runtime behavior. For a change, verify against the target workspace and a representative input.

### Connector lifecycle

Use the `connector-builder` agent for the complete docs → plan → generate → compile → upload → live-test loop:

```bash
python scripts/run-agent.py connector-builder next-step --build-id <id>
```

Do not call a downloaded package complete until PROCESIO accepts it and its intended action passes a live or controlled test.

### One narrow operation

Use a registered tool action when the requested outcome is one read or one explicit mutation. Check its exact schema first. Curated resource actions beat raw endpoint actions because they encode DTO and platform rules.

## Verification matrix

| Outcome | Minimum direct proof |
|---|---|
| Process changed | Re-fetch configuration, validate, run representative payload, inspect final instance status and outputs |
| Form changed | Re-fetch, publish or open intended URL, exercise relevant controls in a real browser, inspect page/console/network diagnostics |
| Webhook or schedule changed | Re-fetch saved trigger, invoke or wait in a controlled case, inspect the resulting process instance |
| Document changed | Run generation and inspect or download the produced artifact, not only the template DTO |
| Data model or SQL behavior changed | Re-fetch schema and inspect the actual database/result side effect |
| Connector changed | Upload, test the custom action, inspect response mapping and failure behavior |
| Export/import completed | Inventory the destination resources and verify dependencies, names, IDs, and activation state |

## Failure recovery

- `check-auth` returns `authenticated: false`: **hard stop**. Do not probe another PROCESIO endpoint or infer success from `mode` or from a `403`. Inspect only local non-secret profile/environment metadata, correct or rotate the credential, then retry `check-auth`.
- `not_found`: re-resolve the resource in the intended workspace; do not substitute a similarly named object silently.
- `permission_denied` after a successful auth check: inspect workspace scope and role. Do not retry unchanged permissions.
- timeout or dropped connection after a write: classify as **unknown outcome**, re-read by stable ID or idempotency key, then decide whether a retry is safe.
- process says finished but outcome is absent: inspect instance variables, outputs, platform-specific usage rules, and external side effects.
- browser screenshot looks correct but diagnostics fail: the form is not verified.

## Completion response

State:

1. Environment, workspace, resource, and stable IDs.
2. Exact capability used and whether it mutated state.
3. Direct verification performed and observable result.
4. Any assumption, unverified external side effect, or manual check still open.
