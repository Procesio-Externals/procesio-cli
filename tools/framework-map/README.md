# framework-map

Regenerates the **interactive, bilingual (EN default / RO) framework map** — a
single self-contained HTML file that shows the whole Agents-and-Tools framework
on one page: every tool, agent, skill and action from the live registry (drillable
down to arguments), plus the orchestration loop, the who-triggers-what diagram,
schedules, the context/state/knowledge store, and worked use cases. Built for
presenting the framework to a team.

The page is generated **from the registry**, so it never drifts: add a tool, run
`build`, and it appears. Names, commands and per-action technical text stay in
English (they mirror the CLI); the *catalog* layer (categories, tool/agent/skill
descriptions, triggers) is translated to Romanian.

## Usage

```bash
# regenerate framework-map.html at the repo root
python scripts/run-tool.py framework-map build

# write somewhere else
python scripts/run-tool.py framework-map build --out outputs/map.html

# dry-run: counts, categories, and what still needs an RO translation (writes nothing)
python scripts/run-tool.py framework-map check
```

Open the resulting `.html` in any browser — it is fully offline and self-contained
(no external scripts, fonts, or images), so it works from any laptop with no
network, and toggles EN/RO in the top bar.

## Output

`build` emits, e.g.:

```json
{ "path": ".../framework-map.html", "bytes": 1280000,
  "tools": 44, "agents": 8, "skills": 12, "actions": 1500,
  "tool_actions": 1398, "agent_actions": 102,
  "categories": { "PROCESIO & automation": 5, "Data & databases": 4, ... },
  "uncategorized": [],
  "ro_untranslated": {} }
```

- `ro_untranslated` lists any catalog strings (tool/agent/skill descriptions,
  triggers, categories) with no Romanian translation yet — those fall back to
  English in the RO view. Empty means the catalog is fully translated.
- `uncategorized` lists tools missing from the category map (they land in "Other").

## Keeping it current

When you add a tool or agent:

1. `framework-map check` — see if it needs a category or an RO translation.
2. Add a category in `fm_builder.CAT` if it landed in "Other".
3. Add the RO translation in `fm_ro_catalog.py` (tool/agent/skill desc + triggers;
   a new category goes in `CATS`).
4. `framework-map build`.

The test suite enforces both: `test_every_tool_is_categorized` and
`test_catalog_fully_translated_to_ro` fail until the new entry is covered.

## What is generated vs hand-authored

Most narrative sections (the pieces, the loop, use cases, etc.) are static strings
in `fm_strings.py`. Two are generated at build time from live data, so do **not**
hand-edit them — the generated value overrides the string:

- **The "Live today" schedule note** — built from `schedule.yaml` by
  `fm_builder._schedule_note` (real enabled jobs, cadence, target agent, mode).
  Falls back to a generic line on a fresh/wiped install.
- **The context-state-knowledge tree** — built from the real top-level folders by
  `fm_builder._store_tree`, so a new subfolder never goes missing. store.db's
  record types stay conceptual.

Two structural guards run in the suite: `test_section_and_div_tags_balanced` (a
dropped closing tag orphaned every later section once — this catches it) and
`test_narrative_references_resolve` (every `data-ujump` chip must point at a real
registered tool/agent). `test_nav_links_resolve_to_sections` keeps the nav honest.

## Layout

```
tools/framework-map/
  tool.yaml          manifest (source of truth: build + check)
  main.py            entrypoint - action dispatch, JSON in/out
  fm_builder.py      pipeline: extract registry -> compress -> translate RO -> assemble
  fm_strings.py      narrative + UI strings (EN + RO), humanized
  fm_ro_catalog.py   RO catalog translations (categories, descriptions, triggers)
  styles.css         page styles (inlined into the HTML at build)
  app.js             explorer + language toggle (inlined into the HTML at build)
  tests/             manifest-sync guard + build/structure invariants
```

No secrets. The generated HTML is a build artifact; it reflects current
credential *presence* (the green/grey readiness dots — booleans only, never
values), so treat it like anything under `outputs/`, not as versioned framework
source.
