---
name: connector-builder
description: AI Connector Builder (connector-builder.procesio.app): turn API documentation into a compiled PROCESIO Custom Action .nupkg connector via an 8-stage LLM pipeline (gather -> clarify -> plan -> generate -> validate -> compile -> fix -> deliver). Drive the whole build lifecycle, read/write generated files, download the .nupkg artifact (to upload to PROCESIO for live testing), inspect logs/telemetry,…
---

# connector-builder

AI Connector Builder (connector-builder.procesio.app): turn API documentation into a compiled PROCESIO Custom Action .nupkg connector via an 8-stage LLM pipeline (gather -> clarify -> plan -> generate -> validate -> compile -> fix -> deliver). Drive the whole build lifecycle, read/write generated files, download the .nupkg artifact (to upload to PROCESIO for live testing), inspect logs/telemetry, and edit the builder's own knowledge base (prompts, spec modules, examples, validation rules). Two auth modes, both -> Bearer token: an acb_ API key, or username/password via /auth/login.

## How to call it

```bash
python scripts/run-tool.py connector-builder <action> [--args]
# e.g. connector-builder create-build --api-url <docs-url> --user-requirements '...'   (then gather / answer / approve-plan / approve-generate / download-artifact)
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

**Start with `create-build`.**

## Credentials

Stored in the OS credential store, never in files. Missing ones are reported by `python scripts/list-tools.py`.

- `agents-and-tools:connector-builder:api-key` — Connector Builder API key (acb_...). Used verbatim as the bearer token.
- `agents-and-tools:connector-builder:username` — Login email for username/password auth mode (e.g. user@example.com).
- `agents-and-tools:connector-builder:password` — Login password for username/password auth mode (-> POST /auth/login -> JWT).

## Actions

### answer

| action | required args | what it does |
|---|---|---|
| `answer` | `--build-id`, `--answers` | Submit clarification answers; triggers PLAN. |

### api

| action | required args | what it does |
|---|---|---|
| `api` | `--path` | Call any endpoint (method/path/query/body); --out streams binary. |

### approve

| action | required args | what it does |
|---|---|---|
| `approve-generate` | `--build-id` | Accept generated files; runs VALIDATE->COMPILE->FIX->DELIVER. |
| `approve-plan` | `--build-id` | Approve plan; triggers GENERATE (then pauses). |

### archive

| action | required args | what it does |
|---|---|---|
| `archive` | `--build-id` | Archive a build (admin). |

### build

| action | required args | what it does |
|---|---|---|
| `build-selftest` | — | Compiler health self-test (trivial C#). |

### check

| action | required args | what it does |
|---|---|---|
| `check` | — | Connectivity + auth probe (GET /auth/me). |

### create

| action | required args | what it does |
|---|---|---|
| `create-api-key` | `--name` | Create an API key (full_key shown only once). |
| `create-build` | — | Create a build from URL(s) / pasted docs. |

### delete

| action | required args | what it does |
|---|---|---|
| `delete-llm-key` | — | Remove the stored LLM provider key. |

### download

| action | required args | what it does |
|---|---|---|
| `download-all` | `--build-id`, `--out` | Download all generated files as a zip to --out. |
| `download-artifact` | `--build-id`, `--out` | Download the compiled .nupkg to --out (upload to PROCESIO). |
| `download-file` | `--build-id`, `--filename`, `--out` | Download one generated file to --out. |

### events

| action | required args | what it does |
|---|---|---|
| `events` | `--build-id` | Per-build pipeline events. |

### gather

| action | required args | what it does |
|---|---|---|
| `gather` | `--build-id` | Run GATHER+CLARIFY (profile+questions); --wait survives the 504. |

### get

| action | required args | what it does |
|---|---|---|
| `get-build` | `--build-id` | Full build detail (all JSONB fields). |
| `get-config` | `--which` | Read a config block (pipeline/providers/...). |
| `get-file-version` | `--build-id`, `--filename`, `--version` | Full content of one file at a specific version. |
| `get-issue` | `--id` | Full issue-case detail incl. snapshots. |

### knowledge

| action | required args | what it does |
|---|---|---|
| `knowledge-create` | `--module-type`, `--name` | Create a new knowledge module. |
| `knowledge-delete` | `--module-type`, `--name` | Delete a knowledge module. |
| `knowledge-get` | `--module-type`, `--name` | Get one knowledge module's content. |
| `knowledge-list` | `--module-type` | List knowledge modules of a type. |
| `knowledge-update` | `--module-type`, `--name` | Update an existing knowledge module. |

### list

| action | required args | what it does |
|---|---|---|
| `list-api-keys` | — | List your API keys. |
| `list-builds` | — | List builds (paginated, filterable). |
| `list-file-versions` | `--build-id` | Version metadata for every file in a build (no content). |
| `list-issues` | — | List issue cases (failures), filterable. |
| `list-messages` | `--build-id` | Chat/system messages for a build. |
| `list-users` | — | List all users (admin). |

### logs

| action | required args | what it does |
|---|---|---|
| `logs` | `--build-id` | Per-build stage logs (model/cost/token breakdown). |

### override

| action | required args | what it does |
|---|---|---|
| `override-stage` | `--build-id`, `--target-step`, `--target-status` | Jump the build to a target step/status. |

### post

| action | required args | what it does |
|---|---|---|
| `post-message` | `--build-id`, `--step`, `--content` | Post a chat message to a build/step. |

### regenerate

| action | required args | what it does |
|---|---|---|
| `regenerate` | `--build-id` | Regenerate files with per-file/general instructions. |
| `regenerate-file` | `--build-id`, `--filename`, `--instructions` | Regenerate a single file with instructions. |

### reload

| action | required args | what it does |
|---|---|---|
| `reload-config` | — | Reload all YAML config + knowledge cache. |

### reset

| action | required args | what it does |
|---|---|---|
| `reset` | `--build-id` | Reset a failed/clarifying/planning build to pending. |

### retry

| action | required args | what it does |
|---|---|---|
| `retry` | `--build-id` | Retry the pipeline from a step (or last failed). |

### revise

| action | required args | what it does |
|---|---|---|
| `revise-plan` | `--build-id`, `--feedback` | Revise the plan with free-text feedback. |

### revoke

| action | required args | what it does |
|---|---|---|
| `revoke-api-key` | `--id` | Revoke an API key by id. |

### set

| action | required args | what it does |
|---|---|---|
| `set-file-instructions` | `--build-id`, `--filename`, `--instructions` | Save per-file regeneration instructions. |
| `set-llm-key` | `--api-key`, `--provider` | Set the LLM provider key that powers builds. |
| `set-version` | `--build-id`, `--major`, `--minor`, `--patch` | Set Major.Minor.Patch (at Plan/waiting_user). |

### stage

| action | required args | what it does |
|---|---|---|
| `stage-override-options` | — | Valid stage-override targets for override-stage. |

### start

| action | required args | what it does |
|---|---|---|
| `start-build` | `--build-id` | Run the FULL pipeline as a background task. |

### telemetry

| action | required args | what it does |
|---|---|---|
| `telemetry` | — | Cross-build LLM telemetry (cost/tokens/latency), filterable. |

### unarchive

| action | required args | what it does |
|---|---|---|
| `unarchive` | `--build-id` | Unarchive a build (admin). |

### update

| action | required args | what it does |
|---|---|---|
| `update-config` | `--which` | Update a config block from JSON. |
| `update-file` | `--build-id`, `--filename` | Overwrite a file's content (inline or from --content-file). |

### validate

| action | required args | what it does |
|---|---|---|
| `validate-autofix` | `--build-id` | Auto-fix validation findings. |
| `validate-continue` | `--build-id` | Continue past validation to COMPILE. |
| `validate-return-to-generate` | `--build-id` | Return from VALIDATE back to GENERATE. |

### wait

| action | required args | what it does |
|---|---|---|
| `wait-build` | `--build-id` | Poll get-build until settled/terminal (use after approve-generate/retry). |

### whoami

| action | required args | what it does |
|---|---|---|
| `whoami` | — | Full current-user record (GET /auth/me). |

---

Generated from `tools/connector-builder/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
