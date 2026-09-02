# Form-control goldens: generated from the FormBuilder mock (DO NOT hand-edit)

`elements/<type>.json` (the per-control "goldens" the builder clones) are **generated**
from the FormBuilder source of truth `docs_info/FormBuilder mock.ts` by
`sync_from_mock.py`. Do not edit them by hand — your change will be overwritten on the
next sync. Change the mock (or `enum_map.json`) and re-run instead.

## The sync mechanism — `sync_from_mock.py`
```
python tools/procesio/dto/form/sync_from_mock.py            # dry-run: what would change + unverified enums
python tools/procesio/dto/form/sync_from_mock.py --write    # regenerate all elements/*.json
python tools/procesio/dto/form/sync_from_mock.py --check    # exit 1 if goldens != mock (CI guard)
```
**When a new mock.ts arrives** (new control, changed control, new feature): drop it in
`docs_info/FormBuilder mock.ts`, run `--write`, eyeball the change list + the
"UNVERIFIED enum members" section, run the tests. That's the whole loop.

What it guarantees:
- **complete** — one golden per control the FormBuilder ships (33), incl. ones that
  could never be harvested (chart, chat, assignee, signature-pad, stepper, step).
- **exact** — config keys, **render order** (= designer properties-panel order),
  `type`/`category`/`subCategory`/`exposed`/`events` all come straight from the mock.
- **deterministic / repeatable** — same mock in → byte-identical files out (ids are
  `uuid5`; the builder reassigns ids at build time so their values are cosmetic).
- **sound** — before writing it re-checks every regenerated golden against the previous
  on-disk one and ABORTS if any *resolved enum value* of a shared config changed
  (catches a wrong enum mapping). Adding keys a stale golden lacked is allowed.

## Enum resolution — authoritative, no guessing
The mock references config metadata via enums imported from `../config`. Resolution
precedence (highest first):
1. `docs_info/form-config-enums.ts` — the frontend's actual enum definitions (provided
   verbatim by the team 2026-06-25). Parsed directly → every member is authoritative.
2. `enum_map.json` — committed fallback / manual override (used only for a member not
   in the TS file).
3. rule `MEMBER → lower, '_'→'-'` — last resort, flagged **UNVERIFIED**.

`ElementType` and `ElementCategory` are defined **inside** the mock → parsed from it.

With the TS file present, **0 members are unverified**. Confirmed oddities the rule
alone would get wrong (now in the TS file): `READONLY_OR_DISABLED_TOGGLE →
"readonly-or-disabled"` (suffix dropped) and the misspelled `CONTOLS → "controls"`.

**When the frontend changes a config enum:** paste the updated enum into
`docs_info/form-config-enums.ts` and re-run `--write`. That's the whole enum-upkeep
story — no manual map editing.

## TEMPLATE_ONLY configs are intentionally excluded  (DECISION — confirmed 2026-06-25)
Configs typed `TEMPLATE_ONLY` (templateLabel, variation, palette-only duplicates) live
only in the builder palette, never in an instantiated/saved control — so the generator
drops them. The golden mirrors **what the toolbar produces**, which is what the builder
must send. Their absence is correct, not drift. Do NOT re-add them: a real saved control
has none, and shipping them risks the platform's on-save compiler mishandling the element
and creates phantom data-model attributes. (To override anyway, the only change is to stop
skipping `type == "template-only"` in `sync_from_mock.py`.)

## Builder coupling (don't break these)
`builder._set_config` overrides a key **only if it already exists** in the golden — a
missing key = silent no-op. That's why golden completeness matters and why we generate
from the mock. Builder-critical keys verified present: `childrenIdPerColumn`, `rows`,
`columns`, `tabs`, `tableColumnsSourceType/Value`, canonical `value`
(`exposed:true` + `events:["EMIT_INPUT"]`).

## Files
- `sync_from_mock.py` — the generator (this mechanism).
- `../../docs_info/form-config-enums.ts` — AUTHORITATIVE frontend enum definitions
  (parsed directly). Update this when the frontend changes a config enum.
- `enum_map.json` — committed fallback used only if the TS file is absent.
- `capture_goldens.py` — OLD harvest-from-exports approach, superseded by the above
  (kept for reference / cross-checking against real saved forms).
- `elements.bak.premock/` — backup of the pre-sync harvested goldens (safe to delete
  once you're happy: `rm -r elements.bak.premock`).
