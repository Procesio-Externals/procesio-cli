# layout — deterministic canvas auto-layout

Graph in, tidy positions out. A Sugiyama-style layered layout adapted to a PROCESIO
action DAG: layer left→right by longest-path depth, order within a layer by the median of
predecessor positions (crossing reduction), pack vertically with a min gap, drop error-port
targets to a low lane, and lay out For-Each container bodies inside their frame. Pure and
deterministic — same input → same output. Rationale in
`../../agents/procesio/PROCESIO-VISUAL-ORGANIZATION.md`; data model in
`../PROCESIO-RESOURCE-MODEL-NOTES.md` §1.

## Use

```python
from tools.procesio.layout import engine, adapter

res = engine.layout(nodes, edges, opts=None)            # full layout: {positions, areas, bbox}
res = engine.layout(nodes, edges, subset=["id1", ...])  # partial: reposition only these
res = adapter.layout_flow(bundle_or_flow, flow_id=None) # read→engine→write-back; res["bundle"]
res = adapter.layout_flow(bundle, flow_id=fid, only=["actId"])  # re-tidy only these actions
rm  = adapter.layout_resource_map(bundle)               # process→process graph positioned
```

CLI (offline, no profile):

```
python -m tools.procesio.main layout-flow --in <export.procesio> [--flow-id <id>] [--out <file>] [--dry-run]
python -m tools.procesio.main layout-flow --in <export.procesio> --only <actId[,actId...]>   # partial
python -m tools.procesio.main layout-flow --in <export.procesio> --cluster                   # serpentine long chains
python -m tools.procesio.main layout-flow --in <export.procesio> --min-crossings             # reduce edge crossings
python -m tools.procesio.main layout-resource-map --in <export.procesio> [--root-flow-id <id>]
```

Two OPTIONAL final layers (composable; both off by default):

**Minimize crossings (`--min-crossings` / `minimize_crossings=True`).** Best-effort edge-
crossing reduction in **two phases**:

- **Phase A — region re-placement.** Each off-spine sub-region (the error region, dead-end
  folds) is offered several candidate placements; the fewest-crossings one wins, replacing the
  base **only if strictly better**:
  - **compact flush** — region re-laid compactly (a linear chain collapses to one row), hung
    just above OR just below the main body;
  - **loop-curl** — when the region is a **retry/error loop** (an entry edge *from* the main
    flow AND a return edge *back* to it: error → decisional → retry-to-Join), it's laid as two
    vertical columns aligned to its anchors — the loop tail rises above its **return target**,
    the decisional + fail path rise above the **entry source**. Both boundary edges become
    vertical (no crossing) and the decisional reads in-flow (fans left to the loop, up to the
    fail path), the way a human draws a retry loop.
  Compact/aligned ⇒ no far teleport, no empty gap; never overlaps other nodes/frames.
- **Phase B — bounded, distance-penalized per-node local search.** Each movable top-level node
  is nudged within a small grid neighbourhood, keeping the move that most lowers
  `crossings + MINCROSS_MOVE_PENALTY * grid-steps-from-start`. Distance being a **real cost**
  keeps every move LOCAL (e.g. sliding a skip-edge endpoint one row); a node is never teleported
  far into empty space to shave a marginal crossing. Phase B **excludes region-internal nodes**:
  Phase A owns each region's compact, readable layout, so Phase B can't drag a decisional (e.g. a
  `retry?`) downstream of its own successors just to shave one boundary crossing. (There is also
  an optional `MINCROSS_LEN_PENALTY` edge-length term, default 0.)

Crossings are counted **render-faithfully** — an area (For-Each) node is attached at its frame
**top-left** (where the designer draws its edges), not the node centre `positions` holds; using
the centre miscounts every container-boundary edge (this was a real bug: the optimiser was
improving a wrong model). Counts all drawn edges (normal + error). Strictly-better-only moves +
a monotone bounded score ⇒ the result is **never worse** than the input, and it terminates.
Containers/children stay fixed; never overlaps. Tunables `MINCROSS_ITERS`, `MINCROSS_RANGE`,
`MINCROSS_MOVE_PENALTY` (0.25; higher = more conservative). Verified: reaches **0 crossings** on
the ANAF/Query production process (matching the reference hand-arrangement's intent), from a base of 3.
Not zero-guaranteed in general — a structural crossing no compact/local move can remove is left
as-is.

**Cluster consecutive horizontal actions (`--cluster` / `cluster=True`) — opt-in.** A long
run of consecutive `1-in/1-out` actions (top-level, NOT inside a For-Each), `>= CLUSTER_MIN`
(5) nodes, is folded from one long horizontal row into a compact **serpentine grid** — down
one column, up the next, wrapping every `CLUSTER_WRAP` (4) rows — to conserve horizontal
space and improve readability. Off by default; the run otherwise stays a single straight row.
Tunables `CLUSTER_MIN` / `CLUSTER_WRAP` in `engine.DEFAULTS`. **Guarded by the final result:**
the fold is kept only if the FINISHED layout (after min-crossings + de-overlap) is no worse in
`(overlaps, crossings)` than not folding — on a branchy flow a serpentine can shove folded
nodes into overlaps/crossings, so `layout()` computes both outcomes and keeps the better. On a
clean linear run it folds for free (equal crossings, less width).

**De-overlap safety net (always on).** As the final step, `layout()` runs `_resolve_overlaps`:
if any two nodes' boxes overlap (independent off-spine lanes — an error region + a dead-end
chain — can otherwise be dropped into the same lane), the lower one is nudged down a grid row
until clear. It is a **no-op when nothing overlaps**, so clean layouts stay byte-identical.
Guarantees the "no node overlaps" invariant (`verify-layout` issue_count 0). Note: resolving a
base-layout overlap this way can convert it into a crossing — an overlap is the worse of the two.

Full `layout-flow` changes ONLY each action's `CustomData.position` and a For-Each area's
`areaSize` — topology (ids, ports, parameters) is byte-identical, so the bundle re-imports
cleanly. It **never touches `CanvasData`** (the designer viewport pan/zoom): moving the
viewport would jump the user's view away from the content. Fit-to-screen in the designer to
frame a re-laid-out process. `--dry-run` emits the computed positions without writing.

**Partial mode (`--only` / `subset=`)** repositions just the named actions among their
fixed neighbours (x between predecessors and successors, y at the neighbours' median,
nudged clear of overlaps) and leaves every other action, the area frames, and `CanvasData`
**byte-identical**. This is the "I changed one action's config, re-tidy only it" path — it
operates on the real flow's action ids, so there's no identity ambiguity.

## Alternative engine: ELK `layered` (opt-in, off by default)

A second, independent layout engine (`elk_engine.py`) maps the same graph onto the Eclipse
Layout Kernel's `layered` (Sugiyama) algorithm via **elkjs**, run through a synchronous local
Node subprocess (`elk/elk_runner.mjs`, offline — no network). It has the **exact same I/O
contract** as `engine.layout` (positions = absolute node centres, areas = absolute container
frames, bbox), so it is a drop-in alternative. The hand-written `engine.py` is untouched and
remains the default.

**Selection is a config flag, not user-facing:** the `LAYOUT_ENGINE` environment variable,
resolved by `dispatch.layout` (the single dispatch point `adapter.layout_flow` calls):

```
LAYOUT_ENGINE=legacy   # (default) hand-written engine.py
LAYOUT_ENGINE=elk      # ELK 'layered' via elkjs
# unset / blank / anything else → legacy
```

```powershell
$env:LAYOUT_ENGINE = "elk"                                   # this shell
python -m tools.procesio.main layout-flow --in <export.procesio> --out out.procesio
```

What the ELK engine does with the graph: each action → an ELK node (real width/height);
each connection → an ELK edge (direction preserved; **back/cycle edges passed through** —
layered resolves them); For-Each containers → **compound nodes** (children laid out inside
the frame, one hierarchical pass via `hierarchyHandling=INCLUDE_CHILDREN`). Ports are **not**
modelled — the PROCESIO JSON carries no per-connector attachment points. It **degrades
gracefully**: a missing Node/elkjs, an ELK error, an empty graph, or a `subset` (partial
re-tidy — legacy-only) all fall back to the legacy engine, so callers always get a valid
layout.

**Tuned for readability** (validated on real production flows by rendering them and
inspecting) — all ELK knobs are named constants at the top of `elk_engine.py`, each
commented. The config optimises for a clean, untangled left-to-right process flow:
`LAYERING_STRATEGY = NETWORK_SIMPLEX` **aligns parallel branches** (longest-path staggered
them); `NODE_PLACEMENT_STRATEGY = BRANDES_KOEPF` + `BK_ALIGNMENT = BALANCED` **straightens
chains**; `WRAPPING_STRATEGY = OFF` keeps the flow uninterrupted (a wide, scrollable flow
reads better than stacked bands); `SEPARATE_COMPONENTS` + `COMPONENT_SPACING` **pack
disconnected sub-flows close** instead of scattering them; `POST_COMPACTION = LEFT` shortens
long edges; `CONTAINER_BETWEEN_LAYERS` / `CONTAINER_NODE_NODE` give For-Each bodies room so
inner labels don't cram; `CROSSING_MIN_STRATEGY = LAYER_SWEEP`; `NODE_NODE_SPACING` /
`NODE_NODE_BETWEEN_LAYERS` for top-level spacing; `DIRECTION = RIGHT`. `RANDOM_SEED` fixes
output → deterministic. The cost is width (long flows are wide but scrollable); to bound
width instead, set `WRAPPING_STRATEGY = "SINGLE_EDGE"` and re-add an aspect ratio — at the
cost of fragmenting the read. Measured on 6 production flows: crossings dropped (e.g. 8→3,
4→1, 2→0) and long/diagonal edges were largely eliminated vs the first-cut config.

**PROCESIO branch conventions** (post-ELK, `_apply_branch_conventions`): an action's **error**
port target and a decisional's **DEFAULT** stop-branch drop **perpendicular** to the flow —
directly above/below the source (same x), the private chain continuing right along that lane.
Default→**Join** and a default that is the **main path** (long chain, > `SHORT_DEADEND`) stay
in-flow; error ports always drop (any length). Needs the port's `data.isDefault` flag, plumbed
through `flowmodel.Edge.is_default`. Loop-backs / For-Each members are left alone;
collision-checked (no overlaps). Toggle `BRANCH_CONVENTIONS`; offset `PERP_LANE_GAP`.

The `elk/` folder vendors the dependency: `elk/package.json` (`elkjs`) + installed
`elk/node_modules`. Reinstall with `npm install` inside `elk/` if it's missing.

## Files

- `engine.py` — pure layered layout core (no PROCESIO imports, no I/O). **Default.**
- `elk_engine.py` — opt-in ELK `layered` engine (elkjs via a Node subprocess); same contract.
- `dispatch.py` — reads `LAYOUT_ENGINE`, calls the legacy or ELK engine (same signature).
- `elk/` — `elk_runner.mjs` (Node runner) + `package.json` + `node_modules` (elkjs).
- `adapter.py` — bridges the chosen engine to a `.procesio` bundle via the flow graph reader.
- Tests: `../tests/test_layout.py` (legacy: determinism, no-overlap, containment, round-trip,
  idempotency) and `../tests/test_elk_layout.py` (ELK: flat/branching/compound all-positioned +
  no-NaN, determinism, graceful fallback, dispatch-flag selection).

## Note

The process builder (`../dto/process/builder.py`) uses THIS engine as its single build-time
layout step (`_engine_layout` → `engine.layout(...)`). The legacy provisional `_layout()` pass
was removed on 2026-07-07 (`todo/done/procesio-retire-builder-layout.md`): it computed seed
positions that the engine then overwrote, so deleting it left the built DTOs byte-identical
(the `greet.dto.json` golden and the full layout suite pass unchanged). The engine is now the
sole source of canvas positions at build time.
