# PROCESIO visual organization & build patterns (agent guidance)

How to lay out a process so a human can read it, and the build patterns that recur in
production. Agent-scoped: these are standards a build should meet, not tool mechanics.
The DTO shapes behind every claim are in `tools/procesio/PROCESIO-RESOURCE-MODEL-NOTES.md`;
the deterministic re-layout tool is specced in `todo/procesio-canvas-layout-tool.md`.
Additive to [PROCESIO-BEST-PRACTICES.md](PROCESIO-BEST-PRACTICES.md) (§2 modularize,
§10 speed) — it does not replace anything there.

---

## 1. Why layout matters

A process is read far more often than it is built — by the next builder, by QA, by the
person debugging a 2am failure. A tangled canvas hides the logic; a tidy one shows it.
Layout is not cosmetic, it is part of "document & handover" (best-practices §7). The
target: someone with no prior context can follow the flow left-to-right and see where it
branches, loops, and stops.

## 2. Layout rules (what "tidy" means on a PROCESIO canvas)

The canvas model: a node's shape is set by its action (inherited, never changed when you
place it); edges are `Ports` (`Type 0` normal, `Type 1` error); a `Decisional` fans out
any number of branches that need not re-merge; the only container is the `For Each` loop
frame, whose children sit *inside* it via `ParentId`. Given that, the rules:

1. **Flow left-to-right.** `Start` on the left, `Stop`(s) on the right. Depth from Start
   sets the column. Time reads as horizontal distance.
2. **One column per dependency level.** All actions at the same distance from Start share
   a vertical axis. Never stack unrelated actions in the same column.
3. **Center children on their parent.** A node with several successors sits at the
   vertical center of that group (tidy-tree rule). Branches of a Decisional spread
   symmetrically around the diamond.
4. **No overlaps, consistent gaps.** Equal horizontal gap between columns; minimum
   vertical gap between siblings. When a deeper level grows, push siblings apart — never
   let boxes collide.
5. **Lay out the For Each frame recursively.** Place a `For Each`'s children first, size
   the frame to fit them, then place the frame as one node at its level.
6. **Error ports go down-and-out.** `Type 1` (error) edges route to a handler placed
   below the main lane, so the happy path stays a clean horizontal line.
7. **Re-converge only where paths should reunite.** A Decisional's branches may end at
   their own `Stop` or merge at a `Join` — don't force a Join where branches are genuinely
   independent. Where they do reunite, make the `Join` visible so the reader sees it.
8. **Deterministic order.** Same graph → same layout. Order siblings by descendant-count
   then id, so re-running layout doesn't reshuffle the diagram.

This is the Reingold-Tilford "tidy tree with contours" idea applied to a DAG: layer by
depth, pack each column without overlap using subtree contours, center on the parent.
The same algorithm, run on the **process→process** graph (`Call Subprocess` /
`Trigger Subprocess` targets) instead of the in-flow graph, produces the **Resource Map**
(left = who calls this process, right = what it calls). The layout tool will do both.

## 3. The For Each container

The only container the Process Designer supports today is the `For Each` loop frame (an
`area`). Keep its body small and self-contained — everything inside runs once per item,
so cost multiplies (best-practices §10). **A `For Each` cannot contain another `For
Each`.** To nest a loop, put a `Call Subprocess` (or `Trigger Subprocess`) inside the
`For Each` and place the inner loop in that subprocess — that also keeps each loop body
flat and independently testable. (Free-form grouping areas are not yet supported by the
designer; don't rely on them.)

## 4. Build patterns to reach for

The actions that carry most real systems, and the shapes they form:

- **Modular by subprocess.** Real systems are a thin main process orchestrating small
  reusable subprocesses (auth, paging, upsert, notify), exactly as best-practices §2/§3
  prescribe. Synchronous `Call Subprocess` when you need the result; async
  `Trigger Subprocess` to fire-and-forget.
- **Branch then (maybe) join.** `Decisional` + `Join` is the standard control shape:
  decide, run the branch-specific work, optionally re-merge. Keep decisionals single where
  you can — five chained decisionals (~2s) collapse to one (<200ms) (best-practices §10).
- **Model JSON, don't chain extractors.** `Extract Objects/List/Object/Text` exist, but
  the fast path is a typed Data Model read directly (best-practices §10). Reserve the
  extract family for genuinely dynamic shapes.
- **Script to do more per node.** A `Node` script often replaces a chain of primitives
  (and `Node` returns raw, typed output; `Javascript` wraps `{result}` — see API notes).
  Fewer nodes = faster + more readable.
- **Throw on purpose.** `Throw` raises a controlled error into the error port — use it to
  fail loudly on a business-rule violation instead of letting bad data flow on.
- **Centralize SQL through credentials.** `Execute Query`/`Execute Command` bind a
  credential by gid (never inline secrets). Apply the `sql-server-optimizer` skill.

## 5. Forms: design for the user, route approvals cleanly

(DTO detail in the resource-model note; here the standards.)

- **Calls to processes are the expensive part of a form.** A control's `RUN_PROCESS`
  event should call a process of 1-3 actions, optimized for speed (best-practices §9).
  Prefer `syncRun:false` + a scoped loader for anything that might exceed 1s; fill the
  result back via `outputMap`. Drive option lists from a static `sourceType:JSON` where
  the data is fixed — don't call a process to fetch constants.
- **Approval = assign + show + capture + branch.** Put an `approval` control with a named
  `approver` (and `approverReplacement` fallbacks) on a task form (`Assignees` set). Show
  approver-only fields with `visibility:{type:"task-assignees"}`. The control captures
  `approved` + `comment` + `responseUser` + `responseDate`; branch the downstream process
  on `approved`. For sequential sign-offs use multi-step `approvalSteps`. Keep the
  approver's screen minimal — they decide, they don't re-enter data.
- **Compose apps with `chainConfig`.** Several forms tied into one columnar dashboard is
  the "App" pattern — use it for an operator landing page that links to sub-forms, rather
  than one giant form.
- **Style via theme variables, not hacks.** Set the `--c-*` theme variables; reserve
  `Data.code` (encrypted) for genuine custom CSS/JS, and run form JS against
  `window.parent.document` inside the sandbox iframe.
- **Dark theme + per-mode palettes.** A form now carries a light AND a dark palette
  (the 16-var `DARK_PALETTE`), swapped at runtime by `themeMode`. Opt in via the form
  config (`themeMode` / `themeDark` overrides); don't fake dark mode with custom CSS.
- **Element alignment.** Container elements (section, list-item, column, step, tab,
  side-panel) accept three flex vars in their per-control style — `--fd-<scope>`
  (direction), `--jc-<scope>` (main axis), `--ai-<scope>` (cross axis). Use them to lay
  out contents instead of custom CSS.
- **Trigger a Data Store operation like a process.** Besides `RUN_PROCESS`, a control can
  raise `RUN_DATA_STORE_OPERATION` (READ/ADD/UPDATE/DELETE) straight against a data store,
  with input/output maps and (for every op except ADD) filters. Reach for it when the
  form just needs to read or write a tenant table without authoring a process. See the
  `datastore` topic.

## 6. Shapes in the Process Designer (decorative, execution-irrelevant)

Cuore's **Shapes** (rectangle / ellipse / diamond, PRC-4391) are annotation objects on
the canvas — they group and label a region and never affect execution. They persist
under the flow's opaque `canvasData.shapes` blob (not a top-level field) and sit in a
z-order band **below** the connectors. Two rules for the agent: **never reason about a
shape as a node** (it has no ports, no config, no run behavior), and **never let an edit
or a re-layout drop `canvasData`** — the tool's `process-edit` carries the live canvas
through, and the layout engine leaves `canvasData` byte-identical; preserve that when
touching a flow by hand.

## 6. When you build or re-organize a process

- After building programmatically, the node positions the builder emits are functional
  but not tidy. Run the layout tool to make the diagram readable before handover —
  deterministic, so it won't fight a future edit:
  `python scripts/run-tool.py procesio layout-flow --in <export.procesio> --out <tidy.procesio>`
  (changes only positions; re-imports cleanly). `inspect-flow` gives a structural summary
  (counts, families, branches, smells); `read-flow-graph` gives the raw node/edge model.
- Until then, if you place nodes by hand, follow §2: left-to-right by level, center
  children, error ports below, and a `Join` only where branches truly reunite.
- Verify the diagram communicates: open it and check a stranger could narrate the flow.
  That check is part of "done" (playbook §C/§E spirit — verified behavior + handover).


## Layout engine upgrade 2026-07-05 (brief: "fix the tool so it layouts right")

Four engine changes in `tools/procesio/layout/engine.py` (all covered by the existing test suite):
1. **Error-region detection stops AT error targets**: main-flow reach may point INTO an error-port
   target (e.g. a script-gate's normal case edge into the shared error Join) but never THROUGH it.
   Before, one normal edge into the sink pulled the whole notify subtree into the main graph.
2. **ALAP layer pull with branch-head anchoring**: single-successor chains get pulled RIGHT adjacent
   to their join (kills 8-layer join edges), but a branch HEAD (predecessor fans out) keeps its ASAP
   layer so it stays next to its decisional.
3. **Error components anchor independently, laid VERTICALLY**: each weakly-connected component of the
   error region becomes a vertical rail below the canvas, anchored at the median x of ITS OWN feeders.
   Vertical rails cannot cross the horizontal main flow.
4. **MINIMIZE_CROSSINGS defaults ON** (strictly better in every measurement).

FLOW-side pattern that finishes the job: with feeders spread across a wide canvas, a SINGLE shared
error Join forces ~feeder-span-length edges (geometry, not layout). Split into ONE ERROR RAIL PER
CANVAS REGION (Networky v2: rails A/left/right - Join+Compose+notice+Stop each, cloned). Result on
the 78-node v2: crossings 10 -> 0 (proper-intersection; report's endpoint-touch counter: 2),
max edge 3729 -> ~1500, all four Networky flows re-laid clean.
LEGACY engine remains the default (ELK is opt-in backup via LAYOUT_ENGINE=elk).


### Layout round 2 (same day, after the designer re-review)
5. **At most ONE folded dead-end chain per branch node** (`_deadend_chains` cap): several chains
   folding onto the same column stacked into overlapping piles (the AI Router 5-way fan). The
   shortest chain folds; the rest lay out normally. Result incl. label-aware collision check:
   v2 = 0 crossings, 0 label collisions; ALL FOUR flows 0/0 by layout-report.
6. **Designer code sync for authored Nodes**: when creating a Node via API, the customData Code
   setting must hold the GUID-reference form (variableId[.attributeId]), NOT the runtime `<%N%>`
   form — the designer renders `<%N%>` literally and the variable picker breaks. Convert with
   the param's variable map (flowpatch `_config_value_from_param` pattern). Synced on 9 authored
   Nodes across v2/HCT/SendExport/PEC.
