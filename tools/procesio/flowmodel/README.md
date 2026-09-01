# flowmodel — offline flow graph reader

Parses a PROCESIO flow (a `.procesio` export bundle or a live flow DTO) into a canonical,
JSON-ready node/edge graph model. Pure, offline, case-insensitive (handles PascalCase
exports and camelCase live DTOs). Never mutates its input.

This is the substrate the canvas layout tool, `inspect-flow`, and audit build on — parse
once, reuse. The model it produces is documented in `../PROCESIO-RESOURCE-MODEL-NOTES.md` §1.

## Use

```python
from tools.procesio.flowmodel import read_flow, read_bundle

g = read_flow(bundle_or_flow, flow_id=None)   # -> FlowGraph (nodes, edges, containers,
                                               #    variables, subprocess_calls, resources,
                                               #    start_id, stop_ids); g.to_dict() for JSON
rm = read_bundle(bundle)                       # -> {"flows": {...}, "process_edges": [...]}
```

CLI (offline, no profile needed):

```
python -m tools.procesio.main read-flow-graph --in <export.procesio|->  [--flow-id <id>]
python -m tools.procesio.main read-flow-graph --in <export.procesio> --resource-map
```

- `--in` accepts a file path, `-` (stdin), or a raw JSON string.
- `--flow-id` disambiguates a multi-flow bundle.
- `--resource-map` emits every flow plus the cross-process (process→process) edge list,
  built from each flow's `Call/Trigger Subprocess` targets.

## Files

- `model.py` — dataclasses: `FlowGraph`, `Node`, `Edge`, `Container`, `VarRef`, `SubprocessCall`.
- `reader.py` — `read_flow` / `read_bundle` + the case-insensitive getter `_g`.
- Tests: `../tests/test_flowmodel.py` (synthetic + real exports).
