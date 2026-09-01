# Connector Builder ⇄ PROCESIO interop

How this agent hands off between the `connector-builder` and `procesio` tools/agents. The whole point of building a connector is to run it in PROCESIO, so this hand-off is the spine of the loop.

## The bridge artifact: the `.nupkg`

The AI Connector Builder produces a compiled **PROCESIO Custom Action package** (`.nupkg`, built with the Custom Actions SDK). That single file is the contract between the two systems:

```
connector-builder download-artifact --build-id <ID> --out connector.nupkg
        │  (a real PROCESIO Custom Action package)
        ▼
procesio customaction-upload --file connector.nupkg     # POST /api/actions, multipart "package" → {id}
```

`customaction-upload` returns the new **actionId**. Keep it — you need it to uninstall before re-uploading an improved build.

## Install → verify → cleanup (the procesio side)

```bash
# 1. Install
python scripts/run-tool.py procesio customaction-upload --file connector.nupkg     # → {"id": "<actionId>"}

# 2. Confirm it registered
python scripts/run-tool.py procesio customaction-list                              # the workspace's custom actions

# 3. Test it for real — hand off to the procesio AGENT (owns the test methodology)
python scripts/run-agent.py procesio verify --process-id <ID>
#    (build/import a process that uses the action; run it; check inputs/outputs/errors)

# 4. Before re-uploading a NEW build of the same connector, uninstall the old one
python scripts/run-tool.py procesio customaction-delete --id <actionId>
```

`customaction-upload` is `CustomActions.Write`; `customaction-delete` is `CustomActions.Delete`. Re-uploading without deleting can leave duplicate/stale actions in the workspace — always `customaction-delete` the prior actionId first.

## Division of labour

| Concern | Owner |
|---|---|
| Generate/compile the connector | `connector-builder` tool |
| Sequence the build pipeline, recommend next step | `connector-builder` **agent** (this one) |
| Install/uninstall/list the `.nupkg` | `procesio` tool (`customaction-*`) |
| Test the action inside PROCESIO (processes, forms, webhooks, E2E) | `procesio` **agent** (build-and-test playbook) |

This agent does **not** re-implement PROCESIO testing — it calls the procesio agent's `verify` and reads the procesio agent's playbook (`run-agent.py procesio guidance --topic playbook`). Conversely the procesio agent does not know how to build a connector — it receives a finished `.nupkg`.

## Turning PROCESIO feedback into a better connector

What PROCESIO tells you maps back to a specific connector-builder action:

| PROCESIO observation | Feed back via |
|---|---|
| Action's input/output ports are wrong or missing | `connector-builder revise-plan --feedback "..."` → re-approve → re-generate |
| The action throws / returns wrong data at runtime | `connector-builder regenerate-file --filename <impl>.cs --instructions "<the PROCESIO error>"` |
| Action metadata/decorators wrong (won't load, bad category) | `regenerate-file` on the decorated class; if recurring, fix the `spec_module` knowledge |
| The model keeps making the same SDK mistake across connectors | `connector-builder knowledge-update --module-type spec_module|example|prompt ...` then `reload-config` |

Rule of thumb: **per-connector** problems → `revise-plan` / `regenerate*`; **systemic** problems (every connector hits them) → edit the builder's `knowledge`. The procesio-custom-actions skill is the authority on what *correct* SDK usage looks like — cite it when writing knowledge corrections.

## One full pass (concrete)

```bash
B=<build-id>
python scripts/run-agent.py connector-builder next-step --build-id $B          # follow until status=completed
python scripts/run-tool.py  connector-builder download-artifact --build-id $B --out c.nupkg
ID=$(python scripts/run-tool.py procesio customaction-upload --file c.nupkg | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
python scripts/run-agent.py procesio verify --process-id <proc-using-the-action>
# if it failed:
python scripts/run-tool.py  connector-builder regenerate-file --build-id $B --filename Impl.cs --instructions "<error>"
python scripts/run-tool.py  connector-builder approve-generate --build-id $B
python scripts/run-tool.py  connector-builder download-artifact --build-id $B --out c.nupkg
python scripts/run-tool.py  procesio customaction-delete --id $ID
python scripts/run-tool.py  procesio customaction-upload --file c.nupkg
# re-verify … repeat until green
```
