"""Maintenance utility — (re)capture canonical form-control goldens from real forms.

The element goldens in `elements/*.json` MUST match exactly what the PROCESIO FormBuilder
toolbar produces when you drag a control onto a form. If they drift (stale/hand-trimmed),
the platform's on-save data-model compiler drops properties (notably the `value` attribute,
whose element config must be canonical: `exposed:true` + `events:["EMIT_INPUT"]`), and the
process-trigger "Map data" picker shows the form variable as "Unknown".

This script harvests canonical controls from real toolbar-built forms — the project's
exports (`docs_info/Exports/*.procesio`, each a JSON with `Forms[].Data` whose `elements`
are real controls) — and writes one neutralized golden per control `type`.

Selection: per type, pick the export instance with the MOST `exposed:true` configs (the
canonical marker). Neutralize: blank event/option/style/table values (the builder fills
label/name/value/placeholder/etc. per spec; ids are regenerated at build time).

Usage:
    python tools/procesio/dto/form/capture_goldens.py            # dry-run: report only
    python tools/procesio/dto/form/capture_goldens.py --write    # overwrite elements/*.json

Re-run whenever the FormBuilder updates a control. Verify a freshly-added control in the
designer matches the captured golden (the user can add one and save; diff the saved form).
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
ELEMENTS = DIR / "elements"
EXPORTS = DIR.parent.parent / "docs_info" / "Exports"

_NEUTRAL_LIST = {"sourceValue", "tableColumnsSourceValue", "rows", "columns", "tabs", "style",
                 "options"}


def _form_data(form: dict):
    v = form.get("Data")
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return None
    return v if isinstance(v, dict) else None


def _exposed_score(el: dict) -> tuple[int, int]:
    cfgs = el.get("configs", []) or []
    return (sum(1 for c in cfgs if c.get("exposed") is True), len(cfgs))


def _neutralize(el: dict) -> dict:
    el = json.loads(json.dumps(el))
    el["parentId"] = None
    for c in el.get("configs", []) or []:
        k = c.get("key", "")
        if isinstance(k, str) and k.endswith("Events"):
            c["value"] = None
        elif k == "childrenIdPerColumn":
            c["value"] = {}
        elif k in _NEUTRAL_LIST:
            c["value"] = []
    return el


def harvest() -> dict[str, dict]:
    cands: dict[str, list] = collections.defaultdict(list)
    for p in sorted(EXPORTS.glob("*.procesio")):
        try:
            dd = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for fm in dd.get("Forms") or []:
            data = _form_data(fm)
            if not isinstance(data, dict):
                continue
            for el in data.get("elements") or []:
                if el.get("type"):
                    cands[el["type"]].append(el)
    return {t: _neutralize(max(insts, key=_exposed_score))
            for t, insts in cands.items()}


def main(argv: list[str]) -> int:
    write = "--write" in argv
    goldens = harvest()
    existing = {p.stem for p in ELEMENTS.glob("*.json")}
    for t in sorted(goldens):
        el = goldens[t]
        keys = [c.get("key") for c in el.get("configs", [])]
        valcfg = next((c for c in el["configs"] if c.get("key") == "value"), None)
        ok = bool(valcfg and valcfg.get("exposed") and valcfg.get("events") == ["EMIT_INPUT"])
        flag = "field+value" if ok else ("field" if valcfg else "no-value")
        print(f"{t:18s} {len(keys):2d} cfgs  {flag}")
        if write:
            (ELEMENTS / f"{t}.json").write_text(
                json.dumps(el, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{'WROTE' if write else 'DRY-RUN'} {len(goldens)} goldens. "
          f"missing-from-disk: {sorted(set(goldens) - existing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
