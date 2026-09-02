# Connector Builder — build → test → improve playbook

The operating procedure for producing a working PROCESIO Custom Action with the AI Connector Builder. The agent's `next-step` and `checklist` actions are the executable form of this document.

> **Running it for real?** Read `guidance --topic troubleshooting` alongside this — it has the tool/skill inventory, the live-run realities (sync stages 504 at the proxy but keep running → poll; the clarification-questions shape; the MSYS path gotcha), and the compile failure triage (NU1301 = platform NuGet, not your code, vs NU1102 = a bad version pin you fix in the .csproj). `next-step --build-id` attaches that triage automatically on a failed compile.

## The loop

```
1 scope     → create-build (API docs + clear requirements)
2 gather    → gather (GATHER+CLARIFY) → read api_profile + questions
3 clarify   → answer (every question; keys are the question ids) → PLAN
4 plan      → revise-plan* then approve-plan → GENERATE (pauses)
5 generate  → review files; regenerate-file* then approve-generate
6 validate  → validate-continue / validate-autofix / validate-return-to-generate
   compile  → (automatic) on failure: retry --from-step 6
7 deliver   → download-artifact → connector.nupkg
8 install   → procesio customaction-upload --file connector.nupkg
9 test      → exercise it in PROCESIO (hand off to the procesio agent)
10 improve  → feed failures back (see "Where feedback goes")
11 cleanup  → procesio customaction-delete before re-uploading a new build
            → recompile, re-upload, repeat 8-11 until green
```

`*` = repeat as needed before the approve.

## Two ways to drive stages 2-6

- **Manual (default for a first build):** call each stage yourself so you can read and steer every output. Use `next-step --build-id <ID>` after each call.
- **Automatic:** `start-build --build-id <ID>` runs the entire pipeline as one background task. Poll `get-build`. Use this only once the requirements + clarifications are trusted (it won't pause for review).

## Stage discipline

- **Scope (1).** Requirements are the highest-leverage input. State the operations the connector must expose, the auth scheme, and the data shapes. A vague requirement produces a vague plan and a weak connector. The docs URL is scraped; if the docs are poor, paste the relevant section via `--api-docs-text`.
- **Clarify (3).** Answer *all* questions — unanswered ones fall back to defaults that may not match intent. The answer keys are the question **ids** returned by `gather` (or `get-build`).
- **Plan (4).** This is the cheapest place to fix structure (files, classes, methods, NuGet deps, input/output controls). Prefer `revise-plan` here over fixing generated code later. `set-version` is only valid at this stage.
- **Generate (5).** Review before approving. Fix a single file with `regenerate-file`; use `regenerate` for cross-file/general guidance. Approving moves you into validate→compile→fix→deliver (a background task).
- **Validate/Compile (6).** Read findings before continuing. On a compile failure, `retry --from-step 6` skips straight to compile→fix→deliver (no regeneration); use `--from-step 4` to regenerate first.
- **Deliver (7).** The artifact is a real PROCESIO Custom Action `.nupkg`. It is not "done" until it has been **installed and exercised in PROCESIO** — compiling is necessary, not sufficient.

## Where feedback goes (improve, stage 10)

| Symptom seen in PROCESIO | Fix in the builder |
|---|---|
| Wrong inputs/outputs, missing operation | `revise-plan` (re-shape) → re-approve |
| One file's logic wrong | `regenerate-file --filename X --instructions "..."` |
| Compiles but misbehaves at runtime | `regenerate` with the PROCESIO error text as `--step-instructions` |
| Validation too weak/strong | edit `validation_rule` knowledge module |
| **Every connector makes the same mistake** | edit `prompt` / `spec_module` / `example` knowledge, then `reload-config` — this fixes generation for ALL future builds |

The knowledge edits are the deepest loop: they improve the *builder*, not just one connector. Reach for them when you see a systemic pattern (e.g. the model keeps mis-using a PROCESIO SDK decorator) — encode the correction once as a spec module or few-shot example.

## Diagnostics

- `get-build` — current status/step_status + all JSONB state.
- `logs --success false` — the failing stage's LLM logs (model/cost/tokens, prompt via the admin prompt endpoint).
- `list-issues --build-id <ID>` / `get-issue` — recorded failure cases with code snapshots (before/after a fix).
- `build-selftest` — is the compiler service itself healthy? (trivial 2-file C#, no LLM spend.)

## Definition of done

A connector is done when: it compiled, **installed into PROCESIO** (`customaction-list` shows it), and ran correctly inside a real PROCESIO process with expected inputs/outputs — verified per the procesio agent's build-and-test playbook. Anything short of a live PROCESIO run is "compiles", not "works".
