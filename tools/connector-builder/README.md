# connector-builder

Drive the **AI Connector Builder** ([connector-builder.procesio.app](https://connector-builder.procesio.app)) — the platform that turns API documentation into a compiled **PROCESIO Custom Action `.nupkg`** connector through an 8-stage LLM pipeline:

```
gather → clarify → plan → generate → validate → compile → fix → deliver
```

This tool is the **REST client** for that platform. It covers the whole build lifecycle, file read/write, artifact/zip download, logs & telemetry, and the admin knowledge base (the prompts/specs/examples that control how every build generates code).

> The compiled `.nupkg` is the bridge to PROCESIO: download it with `download-artifact`, then install it with `procesio customaction-upload --file <nupkg>` to test the connector live. See the **connector-builder agent** for the full build → upload → test → improve loop.

## Auth — two modes, one header

Both modes resolve to an `Authorization: Bearer <token>` header (verified against the backend's `permissions.py` — an API key is just a bearer token starting with `acb_`):

1. **API key** (default): the `acb_...` key, used verbatim.
2. **Username / password**: `POST /auth/login` → JWT access token. This is the "web-tool" login, done over the REST API (no browser needed — the app exposes the same backend under `/api/*`).

Selection: API key if stored, else username+password. Force with `CONNECTOR_BUILDER_AUTH=apikey|userpass`. Base URL overridable with `CONNECTOR_BUILDER_BASE_URL` (default `https://connector-builder.procesio.app/api`).

### Store credentials

```powershell
python scripts/set-credential.py connector-builder api-key      # acb_...
# and/or
python scripts/set-credential.py connector-builder username     # the platform login email
python scripts/set-credential.py connector-builder password
```

(Use `--from-file` on this terminal — interactive paste corrupts secrets.)

## Quick start

```bash
# Sanity / auth probe
python scripts/run-tool.py connector-builder check

# 1. Create a build from API docs
python scripts/run-tool.py connector-builder create-build \
    --api-url "https://api.example.com/docs" \
    --user-requirements "A connector that lists and creates orders."

# 2. Gather + clarify → returns clarification questions.
#    The sync LLM stages (gather/answer/revise-plan) 504 at the proxy but finish
#    server-side — pass --wait to swallow the 504 and poll to the settled state.
python scripts/run-tool.py connector-builder gather --build-id <ID> --wait

# 3. Answer the questions → triggers PLAN
python scripts/run-tool.py connector-builder answer --build-id <ID> \
    --answers '{"q1":"OAuth2 client credentials","q2":"JSON"}'

# 4. Approve the plan → GENERATE (pauses for review)
python scripts/run-tool.py connector-builder approve-plan --build-id <ID>

# 5. Accept generated files → VALIDATE → COMPILE → FIX → DELIVER
python scripts/run-tool.py connector-builder approve-generate --build-id <ID>

# 6. Download the compiled connector
python scripts/run-tool.py connector-builder download-artifact --build-id <ID> --out connector.nupkg
```

Prefer the **fully automatic** path? `start-build --build-id <ID>` runs every stage as one background task (no per-stage pauses); poll `get-build` for status.

## Actions

Run `python scripts/run-tool.py connector-builder --help` for the full list. Grouped:

**Auth / identity** — `check`, `whoami`, `list-api-keys`, `create-api-key`, `revoke-api-key`, `set-llm-key`, `delete-llm-key`

**Build lifecycle** — `list-builds`, `get-build`, `create-build`, `start-build`, `gather`, `answer`, `approve-plan`, `revise-plan`, `approve-generate`, `regenerate`, `regenerate-file`, `validate-autofix`, `validate-continue`, `validate-return-to-generate`, `retry`, `override-stage`, `stage-override-options`, `reset`, `set-version`, `archive`, `unarchive`, `wait-build`

> **Surviving the proxy 504:** the synchronous LLM stages (`gather`, `answer`, `revise-plan`) can exceed the gateway timeout and return a 504 while completing server-side. Pass `--wait` (with optional `--wait-timeout` / `--poll-interval`) to swallow that and poll to the settled state. After the background stages (`approve-generate`, `retry`, `start-build`), use `wait-build --build-id <ID>` (optionally `--until terminal`) to block until compile finishes.

**Diagnostics** — `logs`, `events`, `list-messages`, `post-message`, `telemetry`, `list-issues`, `get-issue`, `build-selftest`

**Files & artifact** — `list-file-versions`, `get-file-version`, `update-file`, `set-file-instructions`, `download-file`, `download-all`, `download-artifact`

**Admin / improve-the-builder** — `get-config`, `update-config`, `reload-config`, `knowledge-list`, `knowledge-get`, `knowledge-create`, `knowledge-update`, `knowledge-delete`, `list-users`

**Escape hatch** — `api --method --path --query --body [--out]` for any endpoint not first-classed.

## Feedback loops (how you improve a connector)

| Where it fails | Action |
|---|---|
| Plan is wrong | `revise-plan --feedback "..."` |
| Generated code is wrong | `regenerate-file --filename X --instructions "..."` or `regenerate` |
| Validation findings | `validate-autofix` / `validate-continue` / `validate-return-to-generate` |
| Compile failed | `retry --from-step 6` (skips straight to compile→fix→deliver) |
| Need to jump stages | `override-stage --target-step N --target-status running|waiting_user` |
| **Builder generates badly across all builds** | edit `knowledge-*` (prompts / spec_module / example / validation_rule / clarification) then `reload-config` |

## Contract

JSON in / JSON out. Success → one JSON object on stdout, exit 0. Failure → `{"error": {"code","message","details"}}`, non-zero exit. Error codes: `invalid_argument` (2), `auth_required`, `auth_failed`, `api_error`, `error`.

## Notes & internals

- `tool.yaml` is **generated** from the handlers by `gen_manifest.py` — edit handlers + the header consts, then rerun `.venv/Scripts/python tools/connector-builder/gen_manifest.py`. A manifest-sync test enforces this.
- Wire details, gotchas, and the PROCESIO interop are in **CONNECTOR-BUILDER-API-NOTES.md**.
