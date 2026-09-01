# PROCESIO agent - knowledge base (staged)

**Status:** runtime built (v0.1.0). Registered agent, JSON in / JSON out, driven
by `python scripts/run-agent.py procesio <action>`. This folder is both the agent's
knowledge base (the docs below) and its code. It is the home for everything the
PROCESIO agent needs to create use cases, edit resources, improve implementations,
and handle formatting/styling in PROCESIO using the registered tools.

## Actions

| Action | What it does |
|---|---|
| `status` | Agent + driven-tool readiness. |
| `guidance` | Serve the playbook / best-practices / boundary docs from one place. `--topic`. |
| `checklist` | Emit the rigorous self-test checklist as structured steps. `--phase`, `--automatable-only`. |
| `verify` | The enforcement gate against a live process: validate, designer-vs-runtime parity audit, and (with `--run`) run + read the real instance status. Lists the manual checks it cannot run. `--process-id`, `--profile`, `--workspace-id`. |
| `audit` | Static best-practice + correctness audit of a process (action count, slow actions, error handling, inline secrets, parity). `--process-id`, `--profile`, `--workspace-id`. |

`verify` and `audit` are the executable side of the playbook: they turn the
prose discipline into a gate. `verify` exits with a `verdict` of pass/warn/fail
and always returns `manual_checks` (forms in a real browser, webhooks, E2E) so the
human/LLM steps cannot be silently skipped.

**Pass `--workspace-id` for any process outside the profile's default workspace.**
A session is scoped to one workspace, so without the flag the platform answers
`User is not authorized for the requested resource` even though the credential is
valid and the process id is right - it reads like a permission problem, not a
scoping one. Both actions forward the credential scope (profile + workspace) to
every inner tool call via `verifylib.scope_args`; any new inner call must splat
the same list, or it will fail on the second hop while the first one succeeded.

## The boundary - agent notes vs tool notes (read first)

Two kinds of knowledge, two homes. Keep them apart on purpose.

- **AGENT notes (here, `agents/procesio/`)** - how to BUILD WELL and how to BEHAVE:
  methodology, the build-and-test loop, best practices, which skills to use, the
  quality bar. Audience: the agent doing the work.
- **TOOL notes (stay in `tools/<tool>/`)** - how the tools work and WHY they work
  that way: API mechanics, DTO shapes, auth, builder internals, platform gotchas.
  Audience: whoever maintains or improves the tools. Keeping these with the tools
  means when we change a tool the reasoning is right there, so we do not repeat a
  mistake we already solved.

**Routing rule for any new learning (Hard rule 6, compounding):**
- About a TOOL, the PLATFORM API, a DTO quirk, or builder behavior -> the tool
  folder (`tools/procesio/*-NOTES.md`, or the relevant tool, e.g. `tools/web/`).
- About METHODOLOGY or how to build well -> here.
- A cross-cutting standing preference -> user memory (`memory/MEMORY.md` + a file).
- Never let a discovery live only in a chat.

## Contents

- **PROCESIO-BUILD-AND-TEST-PLAYBOOK.md** - the operating procedure. The loop the
  agent runs on every build/edit: frame -> design -> build -> rigorous self-test ->
  capture learnings -> fix bugs/inefficiency/UX -> re-verify -> document. Includes
  the self-test checklist (validate, run instances, forms render + behavior in a
  real browser, webhooks, end-to-end) and the skills-to-use map.
- **PROCESIO-BEST-PRACTICES.md** - distilled platform best practices (framing,
  design, integrations, robustness, observability, SQL actions, forms UX, optimize
  for speed). Source: the "Best practices for implementing with PROCESIO" doc.

## Tool notes this agent relies on (in `tools/procesio/`)

- `PHASE4-E2E-NOTES.md` - end-to-end build/test rounds; the verified mechanics for
  validating, running instances, form data-model + trigger behavior, document and
  webhook gotchas. The empirical backbone the playbook checklist points at.
- `PROCESIO-API-NOTES.md` - API behaviors not obvious from Swagger.
- `PROCESIO-AUTH-NOTES.md` - auth modes, workspace scoping.
- `DTO-SUBTOOLS-NOTE.md` - the resource-builder sub-tools contract.
- `PROCESIO-SEND-EMAIL-NOTES.md` - Send Email action node (attachment + recipient).

## Layout

```
agent.yaml            manifest (actions/args/tools/routing)
main.py               action dispatch (JSON in/out)
context.py            stateless tool-invoker context
knowledge.py          loads the KB docs for `guidance`
checklist.py          the self-test checklist (single source)
audit.py              static auditor (correctness + practice); ci() case helper
verifylib.py          the verify gate logic
handlers/             one file per action
tests/                manifest-sync guard + unit tests (31, all faked - no live calls)
```

## Next slices

- Wire `web` (real-browser form render + behavior) and `google-*` (deliverables)
  into actions, so the manual checklist steps become agent-driven where possible.
- A `build` / `edit` action surface over the procesio DTO sub-tools, with `verify`
  run automatically after every build.
