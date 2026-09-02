---
name: framework-map
description: Regenerate the interactive, bilingual (EN default / RO) framework map - a single self-contained HTML file that visualises every tool, agent, skill and action from the live registry (drillable to the argument level), plus the orchestration loop, the who-triggers-what diagram, schedules, the context/state/knowledge store and worked use cases. Built for presenting the Agents-and-Tools framework to a…
---

# framework-map

Regenerate the interactive, bilingual (EN default / RO) framework map - a single self-contained HTML file that visualises every tool, agent, skill and action from the live registry (drillable to the argument level), plus the orchestration loop, the who-triggers-what diagram, schedules, the context/state/knowledge store and worked use cases. Built for presenting the Agents-and-Tools framework to a team.

## How to call it

```bash
python scripts/run-tool.py framework-map <action> [--args]
# e.g. framework-map build   (dry-run counts + untranslated: framework-map check)
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

**Start with `build`.**

## Actions

| action | required args | what it does |
|---|---|---|
| `build` | — | Extract the live registry, compress it, apply the RO catalog translations (falling back to English where a translation is missing), assemble the single-file… |
| `check` | — | Report current counts, the category breakdown, any uncategorized tools, and any catalog strings (tool/agent/skill descriptions, triggers, categories) still… |

---

Generated from `tools/framework-map/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
