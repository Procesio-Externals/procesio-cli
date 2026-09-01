"""Parse a PROCESIO flow (export or live DTO) into a `FlowGraph`.

Pure + offline + case-insensitive: exports are PascalCase (`Actions`, `Ports`,
`CustomData`), the live Web-API is camelCase (`actions`, `ports`, `customData`). Same
DTOs, different case — so every field access goes through `_g` (case-insensitive get).
Never mutates the input.

The model it produces is documented in tools/procesio/PROCESIO-RESOURCE-MODEL-NOTES.md §1.
"""
from __future__ import annotations

import json
from typing import Any

from tools.procesio.flowmodel.model import (
    Container, Edge, FlowGraph, Node, SubprocessCall, VarRef,
)


def _g(obj: Any, *names: str, default=None):
    """Case-insensitive get: try each name, matched against lowercased keys."""
    if not isinstance(obj, dict):
        return default
    low = {str(k).lower(): v for k, v in obj.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return default


def _is_bundle(obj: dict) -> bool:
    return _g(obj, "Flows") is not None and _g(obj, "Actions") is None


def _walk_settings(custom_data: dict):
    """Yield every setting dict in an action's CustomData.configuration, recursing into
    side-panel settings whose `value` is itself a list of settings."""
    for tab in _g(custom_data, "configuration", default=[]) or []:
        for s in _g(tab, "settings", default=[]) or []:
            if isinstance(s, dict):
                yield s
                val = _g(s, "value")
                if isinstance(val, list):
                    for sub in val:
                        if isinstance(sub, dict) and (_g(sub, "label") or _g(sub, "type")):
                            yield sub


def _template_name(action: dict) -> str | None:
    return _g(action, "ActionTemplateName", "actionTemplateName") \
        or _g(action, "ActionName", "actionName")


def _read_flow(flow: dict) -> FlowGraph:
    flow_id = _g(flow, "Id")
    fg = FlowGraph(flow_id=flow_id, title=_g(flow, "Title", "Name"))

    actions = _g(flow, "Actions", default=[]) or []
    area_ids: dict[str, dict] = {}     # area node id -> its CustomData
    for a in actions:
        cd = _g(a, "CustomData", default={}) or {}
        aid = _g(a, "Id")
        tmpl = _template_name(a)
        shape = _g(cd, "type")
        pos = _g(cd, "position", default={}) or {}
        asz = _g(cd, "areaSize", default={}) or {}
        node = Node(
            id=aid, template=tmpl, shape=shape, icon=_g(cd, "icon"),
            position={"x": _g(pos, "x", default=0), "y": _g(pos, "y", default=0)},
            size={"w": _g(asz, "width", default=48), "h": _g(asz, "height", default=48)},
            parent_id=_g(a, "ParentId"),
            input_ports=_g(cd, "inputPorts"), output_ports=_g(cd, "outputPorts"),
            disabled=bool(_g(a, "IsDisabled", default=False)),
        )
        fg.nodes.append(node)
        if shape == "area":
            area_ids[aid] = cd
        if tmpl == "Start":
            fg.start_id = aid
        elif tmpl == "Stop":
            fg.stop_ids.append(aid)

        # edges (stored on the source action)
        for p in _g(a, "Ports", default=[]) or []:
            src = _g(p, "SourceId")
            dst = _g(p, "DestinationId")
            if src and dst:
                pdata = _g(p, "Data", default={}) or {}
                fg.edges.append(Edge(
                    source=src, dest=dst, type=int(_g(p, "Type", default=0) or 0),
                    is_default=(_g(pdata, "isDefault") == "default")))

        # subprocess + credential references via the action's settings
        if tmpl in ("Call Subprocess", "Trigger Subprocess"):
            target = None
            for s in _walk_settings(cd):
                if _g(s, "type") == "flow-list":
                    target = _g(s, "value")
                    break
            fg.subprocess_calls.append(SubprocessCall(
                action_id=aid, target_flow_id=target,
                kind="call" if tmpl == "Call Subprocess" else "trigger"))
        for s in _walk_settings(cd):
            if _g(s, "type") == "credentials":
                gid = _g(s, "value")
                if gid and gid not in fg.resources["credentials"]:
                    fg.resources["credentials"].append(gid)

    # containers: For-Each areas with their parented children
    children_by_parent: dict[str, list[str]] = {}
    for n in fg.nodes:
        if n.parent_id:
            children_by_parent.setdefault(n.parent_id, []).append(n.id)
    for aid, cd in area_ids.items():
        is_foreach = (_g(cd, "name") == "For Each")
        fg.containers.append(Container(
            id=aid, kind="foreach" if is_foreach else "area",
            children=sorted(children_by_parent.get(aid, [])),
            size={"w": _g(_g(cd, "areaSize", default={}) or {}, "width", default=0),
                  "h": _g(_g(cd, "areaSize", default={}) or {}, "height", default=0)}))

    # variables (the flow's contract)
    for v in _g(flow, "Variables", default=[]) or []:
        fg.variables.append(VarRef(
            id=_g(v, "Id"), name=_g(v, "Name"), type=_g(v, "Type"),
            data_type=_g(v, "DataType"),
            is_list=bool(_g(v, "IsList", default=False)),
            is_required=bool(_g(v, "IsRequired", default=False)),
            is_error=bool(_g(v, "IsError", default=False))))

    # webhooks embedded on the flow
    for w in _g(flow, "Webhooks", default=[]) or []:
        wid = _g(w, "WebhookId", "Id")
        if wid:
            fg.resources["webhooks"].append(wid)

    # deterministic ordering
    fg.nodes.sort(key=lambda n: n.id or "")
    fg.edges.sort(key=lambda e: (e.source or "", e.dest or "", e.type))
    fg.containers.sort(key=lambda c: c.id or "")
    fg.subprocess_calls.sort(key=lambda s: s.action_id or "")
    return fg


def _coerce(source) -> dict:
    if isinstance(source, dict):
        return source
    if isinstance(source, str):
        return json.loads(source)
    raise TypeError(f"unsupported source type: {type(source).__name__}")


def read_flow(source, flow_id: str | None = None) -> FlowGraph:
    """Read one flow into a FlowGraph. `source` may be a flow dict, a bundle dict, or a
    JSON string of either. `flow_id` is required only to disambiguate a multi-flow bundle.
    """
    obj = _coerce(source)
    if _is_bundle(obj):
        flows = _g(obj, "Flows", default=[]) or []
        if not flows:
            raise ValueError("bundle has no flows")
        if flow_id:
            match = next((f for f in flows if _g(f, "Id") == flow_id), None)
            if match is None:
                raise ValueError(f"flow_id {flow_id} not found in bundle")
            return _read_flow(match)
        if len(flows) > 1:
            ids = [_g(f, "Id") for f in flows]
            raise ValueError(f"bundle has {len(flows)} flows; pass flow_id (one of {ids[:8]}…)")
        return _read_flow(flows[0])
    return _read_flow(obj)


def read_bundle(source) -> dict:
    """Read every flow in a bundle plus the cross-process (process→process) edge list.

    Returns {"flows": {flow_id: FlowGraph.to_dict()}, "process_edges": [...]}.
    """
    obj = _coerce(source)
    flows = _g(obj, "Flows", default=[]) or ([obj] if _g(obj, "Actions") is not None else [])
    graphs: dict[str, FlowGraph] = {}
    for f in flows:
        fg = _read_flow(f)
        graphs[fg.flow_id] = fg
    process_edges = []
    for fid, fg in graphs.items():
        for sc in fg.subprocess_calls:
            if sc.target_flow_id:
                process_edges.append({"source": fid, "target": sc.target_flow_id, "kind": sc.kind})
    process_edges.sort(key=lambda e: (e["source"] or "", e["target"] or "", e["kind"]))
    return {"flows": {k: v.to_dict() for k, v in graphs.items()}, "process_edges": process_edges}
