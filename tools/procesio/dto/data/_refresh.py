"""Refresh `action_catalog.json` from a live PROCESIO workspace.

The bundle is the process builder's OFFLINE default: `prepare_ctx` tries the live
workspace catalog first and falls back here when that fetch is slow or fails. A
stale bundle therefore does not fail loudly - it fails as
`unknown action '<name>' - not in the action catalog` for any action the platform
has gained since the bundle was taken, and only when the live fetch also misses
its deadline. That is a confusing pair of symptoms for one cause, which is why
this script exists rather than the bundle being hand-edited.

`action_catalog.json`'s own note has referred to this file since 24/06/2026; it
was not actually present until a build needed the `Data Store` action and found
the bundle 1 action behind.

    python _refresh.py --profile <name> --workspace-id <guid>          # report
    python _refresh.py --profile <name> --workspace-id <guid> --write  # apply

ADDITIVE BY DEFAULT. `--write` adds actions the bundle is missing and leaves
existing entries alone, because an in-place replacement of an action whose shape
has changed would silently alter every process the builder emits. Pass
`--replace-existing` to take the live definition for actions that are already
present, and diff the result before committing it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / "action_catalog.json"
AAT = HERE.parents[3]


def fetch_live(profile: str, workspace_id: str, timeout: int = 300) -> list:
    """`GET /api/Actions?getFullAction=true` through the registered tool.

    That endpoint serialises every action's full configuration tree and is
    occasionally very slow while the rest of the API stays sub-second, so this
    runs with a generous timeout - it is a maintenance script, not a hot path."""
    cmd = [sys.executable, str(AAT / "scripts" / "run-tool.py"), "procesio",
           "request", "--method", "GET", "--path", "/api/Actions?getFullAction=true",
           "--profile", profile, "--workspace-id", workspace_id]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          cwd=str(AAT), timeout=timeout)
    body = json.loads(proc.stdout.strip() or "{}")
    if "error" in body:
        raise SystemExit(f"fetch failed: {json.dumps(body['error'])}")
    res = body.get("result") or body
    acts = res.get("actions") if isinstance(res, dict) else res
    if not acts:
        raise SystemExit("live catalog returned no actions")
    return acts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--workspace-id", required=True)
    ap.add_argument("--write", action="store_true",
                    help="apply the change; without it, only report")
    ap.add_argument("--replace-existing", action="store_true",
                    help="also take the live definition for actions already "
                         "bundled (diff the result before committing)")
    ap.add_argument("--procesio-only", action="store_true",
                    help="keep only platform actions (isProcesioAction=true) "
                         "from the live catalog, so a workspace's own custom / "
                         "connector actions never leak into the offline bundle. "
                         "Use this whenever the refresh runs against a real "
                         "workspace, which the bundle is not meant to mirror.")
    a = ap.parse_args()

    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    live = fetch_live(a.profile, a.workspace_id)
    if a.procesio_only:
        live = [x for x in live if x.get("isProcesioAction")]

    # Project every live action to the bundle's canonical key set (the union of keys
    # already in the bundle) BEFORE comparing or storing. The live API attaches volatile,
    # workspace-specific fields (workspaceId, createdBy/updatedBy, *On timestamps, etc.)
    # that must never enter a portable, checked-in snapshot; stripping them also makes
    # `--replace-existing` flag only REAL config changes instead of timestamp churn.
    from collections import Counter
    _kc = Counter(k for x in bundle["actions"] for k in x.keys())
    _n = len(bundle["actions"])
    # Canonical keys appear in most actions; a volatile field (or one a few polluted
    # entries carry) appears in a minority, so a majority threshold keeps the portable
    # shape without hardcoding a blacklist that a new volatile field could slip past.
    keep = {k for k, c in _kc.items() if c > _n / 2} if _n else None

    def canon(act):
        return {k: v for k, v in act.items() if k in keep} if keep else act

    # First position per name — the bundle may carry duplicate names, so replace by
    # recorded index (identity-based .index() blew up on a duplicated action).
    pos = {}
    for i, x in enumerate(bundle["actions"]):
        nm = x.get("name")
        if nm and nm not in pos:
            pos[nm] = i
    name_counts = Counter(x.get("name") for x in bundle["actions"])
    by_name = {x.get("name"): x for x in bundle["actions"] if x.get("name")}
    added, replaced, skipped_ambiguous = [], [], []
    for act in live:
        name = act.get("name")
        if not name:
            continue
        act = canon(act)
        if name not in by_name:
            added.append(name)
            pos[name] = len(bundle["actions"])
            bundle["actions"].append(act)
            by_name[name] = act
        elif a.replace_existing and by_name[name] != act:
            # A name that occurs more than once (e.g. an action shipped in two versions
            # under one display name) cannot be targeted safely by name — replacing would
            # collapse both onto one live definition. Skip and report it; fix those by id.
            if name_counts[name] > 1:
                if name not in skipped_ambiguous:
                    skipped_ambiguous.append(name)
                continue
            replaced.append(name)
            bundle["actions"][pos[name]] = act
            by_name[name] = act

    missing_live = sorted(n for n in by_name if n not in {x.get("name") for x in live})

    report = {"bundled_before": len(by_name), "live": len(live),
              "added": sorted(added), "replaced": sorted(replaced),
              "skipped_ambiguous_names": sorted(skipped_ambiguous),
              "in_bundle_but_not_live": missing_live,
              "written": False}
    if a.write and (added or replaced):
        BUNDLE.write_text(json.dumps(bundle, indent=1, ensure_ascii=False),
                          encoding="utf-8")
        report["written"] = True
        report["bundled_after"] = len(bundle["actions"])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
