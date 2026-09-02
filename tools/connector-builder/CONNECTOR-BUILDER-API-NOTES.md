# Connector Builder — API notes (durable)

Hard-won facts about the AI Connector Builder backend so future sessions don't re-derive them. Source repo (the app itself): the AI Connector Builder checkout — see its `documentation/03-API-REFERENCE.md`, `04-PIPELINE-ENGINE.md`, and `deploy/Caddyfile.example`.

## What the platform is

A FastAPI + Postgres app that generates **.NET/C# PROCESIO Custom Action connectors** from API docs via an 8-stage LLM pipeline (LiteLLM, vendor-agnostic). A standalone compiler service runs `dotnet restore/build/pack` and returns a `.nupkg`. Frontend is Next.js. Admin-configurable: prompts, spec modules, examples, validation rules all editable through the API (the "knowledge" endpoints).

## Base URL & routing (verified live 2026-06-30)

- Production host: `https://connector-builder.procesio.app`. Caddy reverse-proxies **`/api/*` → backend** (the `/api` prefix is stripped before reaching FastAPI). So the REST surface documented without a prefix in `03-API-REFERENCE.md` lives under **`/api`** in production.
  - `GET https://connector-builder.procesio.app/api/auth/me` → works.
  - The bare host root serves the Next.js frontend (so `GET /health` at the root returns the SPA 404, not the backend health — health is a backend route under `/api` semantics in prod).
- Dev: backend at `:8000`, frontend at `:3001`. Swagger at `/docs`, OpenAPI at `/openapi.json`.
- Tool default base = `https://connector-builder.procesio.app/api`; override with env `CONNECTOR_BUILDER_BASE_URL`.

## Auth — BOTH modes are just a bearer token

`backend/app/core/permissions.py::get_current_user` requires `Authorization: Bearer <token>`. If the token **starts with `acb_`** it's looked up as an API key (sha256 hash match in the `api_keys` table); otherwise it's verified as a JWT access token.

So:
1. **API key**: `Authorization: Bearer acb_...` — verbatim, no login call. Simplest. The key belongs to a specific user (and inherits that user's role).
2. **Username/password**: `POST /api/auth/login {"email","password"}` → `{"access_token","refresh_token","token_type":"bearer"}`; use the `access_token` as the bearer. (The login field is **`email`**, not `username`.)

The provided account (a platform login email) and the provided API key `acb_...091` both resolve to the **same admin user** (`role: admin`), so the tool can reach every `/admin/*` endpoint. There is no functional difference between the two modes for this account beyond JWT expiry vs. a long-lived key.

Roles: `viewer` / `builder` / `admin`. Most build endpoints need `builder` or `admin`; knowledge/config/users/issues need `admin`.

## Pipeline state machine (drives the agent's `next-step`)

`status` (overall) × `step_status` decide what to call next:

- `pending` → `start-build` (full auto) OR `gather` (manual, synchronous GATHER+CLARIFY).
- `clarifying` (after gather) → `answer --answers '{...}'` (keys are the question ids) → moves to `planning`.
- `planning` (plan present) → `approve-plan` (→ generate) or `revise-plan --feedback`.
- `generating` + `step_status=waiting_user` → review files, then `approve-generate` (→ validate/compile/fix/deliver) or `regenerate` / `regenerate-file`.
- `validating` + `waiting_user` → `validate-autofix` | `validate-continue` | `validate-return-to-generate`.
- `failed` → `retry [--from-step N]` (1-3 single stage; 4-5 generate→deliver; ≥6 compile→deliver) or `reset` (only from failed/clarifying/planning).
- `completed` → `download-artifact`.
- Jump anywhere with `override-stage --target-step N --target-status running|waiting_user`. **Semantics matter**: `running` clears the target step's own data and re-runs it; `waiting_user` PRESERVES the target step's data and just re-opens its review screen (use this to revisit a plan without wiping it — otherwise `revise-plan` returns "no plan to revise").

## Endpoints worth knowing

- `GET /builds` paginates (`per_page` max 500) with `status` / `archive_status` / `created_by` filters. Each build carries `version_prefix`/`version_build`/`package_version`.
- `PATCH /builds/{id}/version` only works at **step 3 (Plan) + waiting_user**, and only allows non-decreasing semver.
- Binary endpoints (stream, not JSON): `GET /builds/{id}/artifact` (the `.nupkg`), `…/files/{file}/download`, `…/files/download-all` (zip). The tool's `download` helper streams these to `--out` and reads the real filename from `Content-Disposition`.
- `POST /admin/build-selftest` compiles a trivial 2-file C# project end-to-end — a fast health check of the compiler service without burning LLM tokens.
- **Knowledge** = how the builder itself is tuned. `GET/POST/PUT/DELETE /admin/knowledge/{module_type}/{name}` where `module_type ∈ {prompt, spec_module, example, validation_rule, clarification}`. After editing, `POST /admin/config/reload` to refresh the in-memory cache. Editing `spec_module`/`example`/`prompt` changes generation quality for **all future builds** — this is the deepest improvement loop.

## Errors

Backend returns `{"detail": "..."}` on error (FastAPI default). The compiler internal API returns `{"detail","error_code"}`. The tool maps non-2xx → `ApiError` (`auth_failed` for 401/403, else `api_error`) and surfaces the server `detail` in the message.

## PROCESIO interop (the whole point)

The connector this platform builds is a PROCESIO Custom Action package. The `procesio` tool already installs one:

```
procesio customaction-upload --file <connector.nupkg>   # POST /api/actions multipart field "package" → {id}
procesio customaction-list                              # confirm it installed
procesio customaction-delete --id <actionId>           # uninstall before re-upload
```

End-to-end loop: `connector-builder download-artifact` → `procesio customaction-upload` → exercise it in a PROCESIO process (run-process / forms / webhooks) → capture failures → feed them back via `connector-builder revise-plan` / `regenerate-file` / (for systemic issues) `knowledge-update` → recompile → re-upload. The **connector-builder agent** encodes this loop; the procesio agent's build-and-test playbook governs the PROCESIO-side testing.

## Tool internals

- Dir name is hyphenated → modules imported by BARE name (`import client`, `from handlers import builds`) with the tool root on sys.path (see `main.py`); tests use an importlib-alias conftest (`cb_*`), NO `tests/__init__.py`, unique `test_cb_*` basenames.
- `tool.yaml` is GENERATED by `gen_manifest.py` from the live `ACTIONS` dict; never hand-edit actions/args.

## Live-run learnings (first real E2E build, 2026-06-30)

Built a "Send Slack Message" custom action (Slack `chat.postMessage`) end-to-end to exercise the tool+agent. The pipeline ran correctly through create → gather → clarify (10 PROCESIO-aware questions) → plan → generate (6 files, idiomatic SDK code) → compile. Operational facts learned:

- **Synchronous LLM endpoints return 504 at the proxy but COMPLETE server-side.** `gather`, `answers` (PLAN), and `revise-plan` each took longer than Caddy's upstream timeout → without `--wait` the tool got a clean `api_error` 504. The backend kept working. **Handled since v0.2:** pass `--wait` to `gather` / `answer` / `revise-plan` and the tool swallows a 502/503/504 (or client-side timeout) and polls `get-build` to the settled state (`--wait-timeout` default 600s, `--poll-interval` 8s), returning the full build detail with `waited`/`settled` markers. A standalone `wait-build --build-id [--until settled|terminal]` blocks after the fast background stages (`approve-generate`/`retry`/`start-build`) until compile finishes. Robustness detail: the wait guards on `updated_at` advancing past a pre-trigger baseline so a fast poll can't return the stale pre-stage `waiting_user` state. `approve-plan` / `approve-generate` / `retry` return fast (background tasks), so no 504 there.
- **clarification_questions shape:** `{"questions": [ {id, question, default, options, context, category, required}, ... ]}` — a dict with a `questions` list, NOT a bare list. Each question carries a sensible `default`; answering `{id: default}` for all is a good baseline. The CLARIFY stage is PROCESIO-aware (asks about Credentials_Rest vs secret text, tab structure, FeComponentType, HTTP-200-but-ok=false handling, namespace/class naming).
- **Generated code quality is high:** correct `Ringhel.Procesio.Action.Core` decorators (`ClassDecorator`, `FETabDecorator`, `FEDecorator` Type=`Credentials_Rest`, `BEDecorator`, `Validator`), `IAction`, `APICredentialsManager`. Matches the procesio-custom-actions skill conventions.
- **COMPILE blocker — NU1301 restoring the PROCESIO SDK from GitHub Packages.** `compile attempt_1` fails: "Failed to retrieve information about 'Ringhel.Procesio.Action.Core' from remote source 'https://nuget.pkg.github.com/PROCESIO/download/ringhel.procesio.action.core/index.json'." This is **NU1301 (source/package-index access)**, not NU1102 (missing version) — so the pinned version (`1.41.0`) is NOT the cause. `GET /admin/platform-settings` shows `github_packages_pat_set: true` and `POST /admin/platform-settings/test-nuget` returns "PAT is valid" — but test-nuget only checks the ORG index (`/PROCESIO/index.json`), not the package-level download index, so it passing does not prove the SDK package is restorable. `POST /admin/build-selftest` returns "pass" because its trivial 2-file project does NOT reference the SDK, so it never exercises the GitHub Packages restore. **Net: the connector-builder compiler cannot download the PROCESIO SDK package** — a server-side PAT package-scope / egress issue. Fix is platform-side (grant the GitHub Packages PAT read access to the `Ringhel.Procesio.Action.Core` package, or mirror the SDK to a reachable feed), then `retry --from-step 6`. The generated code is already correct and waiting; once restore works, compile→deliver→`download-artifact`→`procesio customaction-upload` completes unchanged.
- **MSYS path-conversion gotcha (Git Bash on Windows):** the `api --path /admin/...` escape hatch gets its leading-slash path rewritten to `C:/Program Files/Git/admin/...` by MSYS, causing a 404. Run those calls with `MSYS_NO_PATHCONV=1` (or from PowerShell). First-class actions are unaffected (they build the path internally).
