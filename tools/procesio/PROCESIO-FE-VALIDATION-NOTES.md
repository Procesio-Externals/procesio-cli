# PROCESIO front-end (designer-layer) validation — notes

Born 2026-07-06. Ports the Process Designer's client-side **"Process Errors"** checks
(the ones that BLOCK designer *Save*) into an offline validator, and auto-runs it before
every process save. Source of truth for the rules: `docs_info/process-validation-reference-1.md`
(the FE team's verbatim dump of `Validation.ts` + `ControlValidators/*`).

## Why this exists (the core insight)

`POST /api/Projects/validate` validates only the **runtime** layer (parameters) and
returns EMPTY even when the designer would REFUSE to save. The designer's "Process
Errors" panel is a **separate client-side check of the DESIGNER layer (`customData`)**
with **no server endpoint**. So a tool-driven save was held to a *lower* bar than a human
clicking Save. This closes that gap: FE (designer) checks run first, then BE, then save.

## Pieces

- `flowmodel/fevalidation.py` — **pure**, offline, case-insensitive validator over a flow
  DTO. `validate_flow(flow, *, datatypes=None, target_vars_of=None, include_types=True)`
  → `list[warning]`. `split_severity()` → `(errors, warnings)`.
- `handlers/fevalidate.py` — impure layer: gathers the datatype catalog + subprocess-var
  resolver from the live API, exposes the **`process-fe-validate`** action, and provides
  the **`pre_save_validate(client, dto, *, force)`** gate (FE → BE, raises
  `ValidationBlocked` on blocking errors unless `force`).
- Wiring: `dto/framework.py` gained a `save_gate` field on `Component`;
  `dto/process/builder.py` defines `_save_gate` and calls it inside `_edit` before the PUT
  and registers it on `COMPONENT`; `handlers/dto_actions.py` runs the gate in
  `_make_create` before POST and threads `--force` / `--no-types` into `ctx`.
- `errors.py` gained `ValidationBlocked` → classified as `validation_failed`, exit 2,
  with the full `{fe, be, blocked, forced}` report as `details`.

## Severity model (deliberate)

- **error** (blocks save): the deterministic, high-signal checks — connectivity, exactly
  1 Start / ≥1 Stop, node names, unique/primitive-named variables, numeric limits,
  required-empty fields, leftover placeholders, number/integer value-format, and
  subprocess required-input mapping.
- **warning** (never blocks): the **data-type MISMATCH** layer. The FE helper
  `getValueDataTypes` (which resolves a value's variable refs to their datatypes) is NOT
  in the reference file, so it was reconstructed best-effort. Kept non-blocking so an
  imperfect reconstruction can never wrongly block a legit save. Ported for the default
  validator + column-definition; the other composite type-checks (TabsPayload,
  MapProcessData, Conditional) are left for a later tuned pass. `--no-types` skips it.

## DTO ↔ FE-model mapping — quirks discovered the hard way

The reference describes the FE's **in-memory** model; the persisted/live DTO differs.
These bit me during live verification — get them right or you get false positives:

1. **Node name = `customData.name`, NOT `actionName`.** The FE's `node.name` (the canvas
   label, defaults from the template, e.g. "Start"/"Call API") is stored in
   `customData.name`. On many live DTOs `actionName` is `None`. Reading `actionName`
   flagged `NODE_NAME` on 9/25 valid processes. `_action_name` reads `customData.name`
   first (sentinel `_ABSENT` when the key is truly absent → falls back to `actionName`
   for older/fixture DTOs).
2. **`actionTemplateId` / `actionTemplateName` can BOTH be `None`** on legacy DTOs (e.g.
   "Github API", "Old/*"). Template-family detection (`_kind`) keys off the GUID first,
   then the template name, then falls back to `customData.name` for the structural
   templates (Start/Stop/For Each/(Trigger) Subprocess). A renamed non-structural node
   just reads as "other" (safe false-negative, never a false block).
3. **Settings carry the FULL FE `Setting` shape** in `customData.configuration[].settings[]`:
   `id, type (SettingType), label, value, dataTypeId, isList, isRequired, limits`. So the
   FE field-level checks CAN run offline — no need to enrich from `/api/Actions`.
4. **Empty ≠ format error.** The FE's `isValidNumber`/`isValidInteger` treat `""` as
   valid; emptiness is the *required* check's job. An optional numeric field left blank
   (e.g. a Delay's unused "Runtime Amount", `type=number dataTypeId=INTEGER value=""`)
   must NOT be flagged. `_default_value_check` and `_check_limits` skip empty values.
   This was a real false positive on "AI Decisional Test" (BE-valid).
5. **`lineArray` is reconstructed from `Ports`.** Edges live on the *source* action's
   `Ports` (`sourceId`/`destinationId`/`type`/`data.isDefault`). Each line touches BOTH
   endpoints. **Error path** = `Type == 1` OR `data.isDefault == "error"` (the reference
   keys on `isDefault === "error"`; the DTO also uses `Type == 1`).
6. **`flow-list` (subprocess target) setting has NO `id`.** Locate it via a loose walk
   (`_walk_settings_loose`) that recurses one level into side-panel values; the id-based
   `getAllSettings` flatten skips it.
7. Case: exports are PascalCase (`Actions`, `CustomData`), live API is camelCase. Every
   field access goes through `_g` (case-insensitive). Live flow is under `resp["flow"]`.

## Live verification (2026-07-06)

Swept 25 real processes in the default workspace: **24 FE-clean, 0 false positives**; the
only FE-flagged one ("AI Connector Builder Result") is genuinely `isValid=False` (an
`UNCONNECTED` action). FE errors correctly line up with BE invalidity where they overlap.

## Relationship to `flow-lint`

`flow-lint` (handlers/flowlint.py) predates this and covers a few designer checks NOT in
the reference file: stale subprocess **side-pannel id**, Execute-Query **Output** null /
scalar-typed, and Node **code binding error-scope/undeclared vars**. Those are
complementary. **As of 2026-07-06 those three unique flow-lint checks are FOLDED INTO the
gate**: `run_fe_validation` calls `flowlint.lint_flow_dto` and merges its unique findings
(SIDEPANEL_ID, EXECQUERY_*, CODE_*, missing_error_variable) as blocking errors — the
overlapping subprocess-mapping ones are excluded to avoid double-reporting. It's
best-effort (wrapped in try/except): a flow-lint infra hiccup never blocks a legit save.
So a stale-sidepanel / bad-Execute-Query / error-scope-code flow is now blocked on save too.

## Gotchas / do-nots

- The gate is process-only (via `Component.save_gate`); other components (form/document)
  are unaffected — their existing `validate` oracle still runs.
- `--force` bypasses BOTH FE and BE and saves anyway. `--dry-run` runs the gate in
  report-only mode (forced open) so you see the validation without saving.
- The type (warning) layer needs the datatype catalog (`GET /api/DataTypes`,
  `pageItemCount=1000`); it's fetched best-effort and silently skipped if that call fails.
- After changing any action's arg/description surface, regenerate the manifest:
  `python -m tools.procesio.gen_manifest` (never hand-edit tool.yaml; ~236 KB, capped
  Write). `tests/test_manifest_sync.py` guards it.
