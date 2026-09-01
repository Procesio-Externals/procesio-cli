# connector-builder agent

Orchestrates the **AI Connector Builder** ([connector-builder.procesio.app](https://connector-builder.procesio.app)) and **PROCESIO** to run one loop end to end:

```
API docs → [connector-builder] build a Custom Action → download .nupkg
        → [procesio] install + test it live → capture failures
        → [connector-builder] improve (revise plan / regenerate / tune knowledge)
        → recompile → re-upload → repeat until it passes
```

It is the **executable doctrine** for that loop. Tool mechanics live in `tools/connector-builder/` and `tools/procesio/`; this agent decides *what to run next* and *how the two tools hand off*.

## Tool-vs-agent boundary

- **`connector-builder` tool** — the REST client. One subprocess call per API action (create-build, gather, answer, approve-*, download-artifact, knowledge-*, …). No methodology, just the wire.
- **`procesio` tool** — installs/uninstalls the produced `.nupkg` (`customaction-upload` / `customaction-delete` / `customaction-list`) and runs processes.
- **this agent** — sequences those calls. It never imports a tool's internals; it drives them through the registry via `agents/_lib/toolrunner`.
- **`procesio` agent** — owns the PROCESIO-side *testing* methodology (the build-and-test playbook: validate/run/forms/webhooks/E2E). This agent hands off to it at the "test" step.

## Actions

```bash
# Readiness (this agent + connector-builder + procesio tools)
python scripts/run-agent.py connector-builder status

# The whole loop as a checklist (optionally for a goal)
python scripts/run-agent.py connector-builder checklist --goal "Stripe refunds connector"

# What do I run next? — live, from the build's real state
python scripts/run-agent.py connector-builder next-step --build-id <ID>
# …or classify a known state pair without a live call
python scripts/run-agent.py connector-builder next-step --status generating --step-status waiting_user

# Load the methodology
python scripts/run-agent.py connector-builder guidance --topic playbook
python scripts/run-agent.py connector-builder guidance --topic interop
```

`next-step` turns the 8-stage pipeline state machine into a single "what now?" answer, including the PROCESIO hand-off once the connector compiles. `checklist` is the same loop as an ordered, executable list.

## Knowledge base (served by `guidance`)

- **CONNECTOR-BUILDER-PLAYBOOK.md** — the operating procedure for the build→test→improve loop.
- **CONNECTOR-BUILDER-PROCESIO-INTEROP.md** — the precise hand-off between the connector-builder and procesio tools/agent (the `.nupkg` bridge, upload/test/cleanup, where each improvement type goes).
- **README.md** — this file (overview + boundary).

## Design notes

- The agent dir name is hyphenated, so its modules are imported by BARE name with the agent root on sys.path (like the hyphenated tools); shared agent libs come from `agents._lib`.
- Stateless: no state backend, no own secret. Readiness comes from the tools it drives.
