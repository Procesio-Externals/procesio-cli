"""Curated structural summary of a flow, built on the graph reader + family map.

Pure: parse → summarize. Reports counts, action families, branch map, subprocess calls,
resources, the variable contract, and advisory smells (it reports; it does not fix).
"""
from __future__ import annotations

import collections

from tools.procesio.flowmodel import families, read_flow

_LARGE_FLOW = 40                       # actions; above this, suggest splitting
_DIRECTION = {10: "inputs", 20: "process", 30: "outputs"}


def inspect(source, flow_id: str | None = None) -> dict:
    fg = read_flow(source, flow_id)

    fam = collections.Counter(families.classify(n.template) for n in fg.nodes)
    out0 = collections.Counter()
    err_sources: set[str] = set()
    for e in fg.edges:
        if e.type == 1:
            err_sources.add(e.source)
        else:
            out0[e.source] += 1

    branches = []
    for n in fg.nodes:
        if n.shape == "diamond":
            targets = sorted(e.dest for e in fg.edges if e.source == n.id and e.type == 0)
            branches.append({"decisional_id": n.id, "cases": len(targets), "targets": targets})

    counts = {
        "actions": len(fg.nodes), "edges": len(fg.edges),
        "decisionals": sum(1 for n in fg.nodes if n.shape == "diamond"),
        "stops": len(fg.stop_ids),
        "subprocess_calls": len(fg.subprocess_calls),
        "foreach": sum(1 for c in fg.containers if c.kind == "foreach"),
    }

    variables = {"inputs": [], "process": [], "outputs": [], "required": []}
    for v in fg.variables:
        bucket = _DIRECTION.get(v.type)
        if bucket:
            variables[bucket].append(v.name)
        if v.is_required:
            variables["required"].append(v.name)

    smells = []
    loop_kids = {kid for c in fg.containers for kid in c.children}
    for n in fg.nodes:
        family = families.classify(n.template)
        if family == "integration" and n.id not in err_sources:
            smells.append({"code": "no_error_port",
                           "message": f"{n.template} (integration) has no error port wired",
                           "action_id": n.id})
        if n.id in loop_kids and family == "integration":
            smells.append({"code": "slow_in_loop",
                           "message": f"{n.template} runs inside a loop — cost multiplies per item",
                           "action_id": n.id})
    if len(fg.nodes) > _LARGE_FLOW:
        smells.append({"code": "large_flow",
                       "message": f"{len(fg.nodes)} actions — consider splitting into subprocesses"})
    if variables["required"]:
        smells.append({"code": "required_inputs",
                       "message": "verify the trigger supplies the required inputs: "
                                  + ", ".join(variables["required"])})

    return {
        "flow_id": fg.flow_id, "title": fg.title,
        "counts": counts, "action_families": dict(fam),
        "branches": branches,
        "subprocess_calls": [{"action_id": s.action_id, "target_flow_id": s.target_flow_id,
                              "kind": s.kind} for s in fg.subprocess_calls],
        "resources": fg.resources, "variables": variables, "smells": smells,
    }
