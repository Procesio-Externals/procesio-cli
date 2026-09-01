# Connector Builder — operations & troubleshooting

Everything a session needs to actually RUN the build → test-in-PROCESIO → find-gaps → reiterate loop, including the realities learned from live runs. Read this together with the playbook (the method) and the interop doc (the PROCESIO hand-off). Load all three: `run-agent.py connector-builder guidance --topic all`.

## Tool & skill inventory — what to use for each part of the loop

| Job | Use | How |
|---|---|---|
| Build the connector (whole pipeline) | **`connector-builder` tool** | `run-tool.py connector-builder <action>` — create-build, gather, answer, approve-plan/revise-plan, approve-generate/regenerate-file, validate-*, retry, override-stage, download-artifact, logs, get-issue, knowledge-* |
| Know what to run next | **this agent** | `run-agent.py connector-builder next-step --build-id <ID>` (reads live state, incl. compile-failure triage) |
| Review generated C# for SDK correctness | **`procesio-custom-actions` skill** | it is the authority on decorators/IAction/credentials/limits — read it before judging generated code or writing knowledge corrections |
| Install the `.nupkg` into PROCESIO | **`procesio` tool** | `run-tool.py procesio customaction-upload --file <nupkg>` → actionId; `customaction-list`; `customaction-delete --id <actionId>` |
| Test the action inside PROCESIO | **`procesio` agent** | `run-agent.py procesio verify --process-id <ID>` and its build-and-test playbook (`run-agent.py procesio guidance`) — it owns the PROCESIO-side testing method |
| Tune the builder itself (systemic) | **`connector-builder` tool** knowledge-* | edit `prompt` / `spec_module` / `example` / `validation_rule` / `clarification`, then `reload-config` |

The agent never re-implements PROCESIO testing — it hands off to the procesio agent. The procesio agent never builds a connector — it receives a finished `.nupkg`.

## Operating reality (from live runs — do not be surprised by these)

- **Synchronous LLM stages 504 at the proxy but keep running server-side.** `gather`, `answer` (PLAN), and `revise-plan` routinely exceed the gateway timeout → without `--wait` the tool returns a clean `api_error` with `status_code: 504`. **This is NOT a failure** — the stage completes server-side. **Preferred:** pass `--wait` to these three (`gather --wait`, `answer --wait`, `revise-plan --wait`) — the tool swallows the 504 and polls `get-build` to the settled state, returning the full build detail (`waited: true`, `settled: true`). Tune with `--wait-timeout` (default 600s) / `--poll-interval` (default 8s). Without `--wait`, poll manually via `get-build` (or `next-step --build-id`) until `status`/`step_status` advance. `approve-plan` / `approve-generate` / `retry` / `start-build` return fast (background tasks) but then run through compile — use **`wait-build --build-id <ID>`** (optionally `--until terminal`) to block until they finish. NOTE: when the *agent* drives a `--wait`/`wait-build` call via toolrunner, pass a subprocess timeout longer than `--wait-timeout` (toolrunner defaults to 120s).
- **`clarification_questions` is `{"questions": [ {id, question, default, options, context, category, required}, … ]}`** — a dict with a `questions` list, not a bare list. Each question has a sensible PROCESIO-aware `default`. Answering `{id: default}` for all is a solid baseline; override only where the connector needs something specific. Keys in `--answers` are the question **ids** (`q1`, `q2`, …).
- **Review before every approve.** The plan (step 3) is the cheapest place to fix structure — prefer `revise-plan` over fixing generated code later. At generate (step 5), read the files (`get-build` → `generated_files`, or `list-file-versions`) and `regenerate-file` anything wrong before `approve-generate`.
- **Windows/Git-Bash gotcha:** the `api --path /admin/...` escape hatch has its leading-slash path rewritten by MSYS (`C:/Program Files/Git/admin/...` → 404). Run those with `MSYS_NO_PATHCONV=1` or from PowerShell. First-class actions are unaffected.

## Failure triage (compile is where it usually bites)

`next-step --build-id <ID>` attaches a `diagnosis` when a build failed at compile. The logic:

- **NU1301 / "failed to retrieve information about '<pkg>'" / can't reach the source index** → **PLATFORM problem, not your code.** The compiler can't pull the PROCESIO SDK (`Ringhel.Procesio.Action.Core`) from GitHub Packages. Regenerating is useless. Check `get-config --which compilation` (nuget_sources) and `POST /admin/platform-settings/test-nuget` — but note test-nuget only validates the ORG index, and `build-selftest` passes without the SDK, so neither proves the SDK package is restorable. Fix is server-side (grant the GitHub Packages PAT read access to the SDK package, or mirror it to a reachable feed), then `retry --from-step 6`. *No code change needed — the generated code stays parked at step 6 and completes once restore works.* (This is exactly what happened on the first real build.)
- **NU1102 / "unable to find package … version" → CODE problem.** The `.csproj` pinned a non-existent version. Read it (`get-file-version --filename *.csproj`), fix the version (`update-file`), then `retry --from-step 6`.
- **Real C# errors → CODE problem.** Let the FIX loop try (`retry --from-step 6`); if it can't, `override-stage` back to generate and `regenerate-file` the offending file with the compiler error as instructions.

Distinguish **transient vs deterministic**: retry once; if the same restore error repeats, it's deterministic → platform, escalate rather than loop. Every failure also writes a `stage_logs` row (`logs --stage compile --success false`) and often an issue case (`list-issues --build-id` / `get-issue`) with a before/after code snapshot.

## Turning PROCESIO feedback into a better connector (reiterate)

After `customaction-upload` + a `procesio verify` run, map what you see back to an action:

| PROCESIO observation | Feed back via |
|---|---|
| Wrong/missing input or output ports | `revise-plan` → re-approve → regenerate |
| Action throws / returns wrong data at runtime | `regenerate-file --filename <impl>.cs --instructions "<the PROCESIO error>"` |
| Won't load / bad metadata / wrong category | `regenerate-file` on the decorated class; if recurring, fix the `spec_module` knowledge |
| Every connector repeats the same SDK mistake | `knowledge-update --module-type spec_module|example|prompt …` then `reload-config` (improves ALL future builds) |

Per-connector problems → `revise-plan` / `regenerate*`. Systemic problems → edit `knowledge`. Cite the `procesio-custom-actions` skill for what *correct* SDK usage is when writing a knowledge correction. Before re-uploading a fixed build, `procesio customaction-delete --id <old actionId>` so you don't leave stale duplicates.

## Definition of done — "as expected"

A connector is done ONLY when all of these hold:
1. It **compiled** (`status: completed`, a `.nupkg` downloads).
2. It **installed** into PROCESIO (`customaction-list` shows it, `isCustom: true`).
3. It **ran correctly inside a real PROCESIO process** — expected inputs produce expected outputs, and the designed error path behaves (e.g. an API that returns HTTP 200 with `ok:false` sets the error output and does not throw), verified per the procesio agent's build-and-test playbook.

Compiling and installing are necessary, not sufficient. Keep iterating (test → diagnose → improve → recompile → re-upload) until step 3 passes. If step 3 needs a live credential (e.g. a Slack bot token) and none is available, the runtime test is the one open item — say so explicitly rather than declaring done.
