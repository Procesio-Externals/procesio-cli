"""Readable Markdown digest of PROCESIO flows — the CONTENT view, not the layout view.

`read-flow-graph` / `inspect-flow` answer "what is the shape of this flow". An audit needs
"what does it DO": the variable contract, every node in execution order, and each node's
runtime parameters — the Node.js script, the SQL statement, the HTTP call, the subprocess it
calls and how variables are mapped in and out. This module renders exactly that, offline.

Resolution it performs so the digest reads without the designer open:
  - `<%N%>` placeholders -> `{{variable_name}}` (via the parameter's own `variable[]` binding)
  - any variable GUID anywhere in a structured value -> `{{variable_name}}`
  - any flow GUID of a loaded flow -> `[[Flow title]]` (so a subprocess call names its target)
  - extra id -> name pairs from the caller (credentials, forms, data models) the same way

Noise it cuts: designer-only settings, canvas geometry, and huge literals (embedded document
templates / base64) which are elided with their size, never dumped.

Pure: dicts in, strings out. Accepts a flow DTO, the Web-API envelope
`{"result": {"flow": {...}}}`, or a .procesio bundle (every flow in it).
"""
from __future__ import annotations

import json
import re
from collections import deque

_PLACEHOLDER = re.compile(r"<%(\d+)%>")
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SQL = re.compile(r"\s*(select|insert|update|delete|exec|execute|with|declare|merge|create|alter)\b", re.I)
_B64 = re.compile(r"^[A-Za-z0-9+/=\s]+$")
_DIRECTION = {10: "input", 20: "process", 30: "output", 40: "system"}
_BUILTIN_TYPES = {
    "0317bfee-b2f5-4bde-bfe8-121212121210": "Boolean",
    "0317bfee-b2f5-4bde-bfe8-121212121211": "Integer",
    "0317bfee-b2f5-4bde-bfe8-121212121212": "Double",
    "0317bfee-b2f5-4bde-bfe8-121212121214": "String",
    "0317bfee-b2f5-4bde-bfe8-121212121218": "DateTime",
    "0317bfee-b2f5-4bde-bfe8-121212121220": "JSON",
    "10c6ac59-3929-49e6-99dc-121212121219": "File",
}
MAX_LITERAL = 150000         # chars of one literal kept verbatim (scripts are the knowledge; keep them whole)
MAX_B64 = 2000               # a base64-looking literal above this is elided


def _camel(x):
    """PascalCase export keys -> the camelCase the Web API returns (one code path for both)."""
    if isinstance(x, dict):
        return {(k[:1].lower() + k[1:] if isinstance(k, str) else k): _camel(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_camel(v) for v in x]
    return x


def unwrap(obj) -> list[dict]:
    """Every flow DTO in `obj`: a flow, the API envelope, or a bundle (either key casing)."""
    if isinstance(obj, str):
        obj = json.loads(obj)
    obj = _camel(obj)
    if not isinstance(obj, dict):
        return []
    if isinstance(obj.get("result"), dict):
        return unwrap(obj["result"])
    if isinstance(obj.get("flow"), dict):
        return [obj["flow"]]
    flows = obj.get("flows")
    if isinstance(flows, list):
        return [f for f in flows if isinstance(f, dict)]
    if "actions" in obj:
        return [obj]
    return []


def _title(flow: dict) -> str:
    return (flow.get("title") or "").strip() or "(untitled)"


class _Resolver:
    def __init__(self, flow: dict, names: dict[str, str]):
        self.vars = {v.get("id"): v.get("name") for v in flow.get("variables") or [] if v.get("id")}
        self.names = names

    def ids(self, s: str) -> str:
        def sub(m):
            g = m.group(0)
            if g in self.vars:
                return "{{" + str(self.vars[g]) + "}}"
            if g in self.names:
                return "[[" + self.names[g] + "]]"
            return g
        return _GUID.sub(sub, s)

    def literal(self, value: str, bindings: list | None) -> str:
        idx = {}
        for b in bindings or []:
            name = self.vars.get(b.get("variableId"), b.get("variableId"))
            attr = b.get("attribute")
            if isinstance(attr, dict) and attr.get("name"):
                name = f"{name}.{attr['name']}"
            idx[b.get("id")] = name
        out = _PLACEHOLDER.sub(lambda m: "{{" + str(idx.get(int(m.group(1)), "?" + m.group(1))) + "}}", value)
        return self.ids(out)


def _elide(s: str) -> str:
    if len(s) > MAX_B64 and _B64.match(s[:4000]):
        return f"[base64/binary literal, {len(s)} chars omitted]"
    if len(s) > MAX_LITERAL:
        return s[:MAX_LITERAL] + f"\n… [{len(s) - MAX_LITERAL} more chars omitted]"
    return s


def _structured(value, r: _Resolver) -> str:
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if v not in (None, "", [], {})}
        if isinstance(x, list):
            return [clean(v) for v in x]
        if isinstance(x, str):
            return _elide(x)
        return x
    return r.ids(json.dumps(clean(value), ensure_ascii=False, indent=1))


def _labels(node: dict) -> dict:
    out: dict = {}

    def walk(settings):
        for s in settings or []:
            if isinstance(s, dict):
                if s.get("id") and s.get("label"):
                    out[s["id"]] = s["label"]
                if isinstance(s.get("value"), list):
                    walk(s["value"])
    for tab in (node.get("customData") or {}).get("configuration") or []:
        walk(tab.get("settings") or [])
    return out


def _order(flow: dict) -> tuple[list[dict], dict]:
    """Nodes in execution order (BFS from Start; unreachable ones last) + outgoing edges."""
    actions = [a for a in flow.get("actions") or [] if isinstance(a, dict)]
    byid = {a.get("id"): a for a in actions}
    out: dict = {a.get("id"): [] for a in actions}
    for a in actions:
        for p in a.get("ports") or []:
            if p.get("destinationId"):
                kind = "error" if p.get("type") == 1 else "next"
                data = p.get("data") or {}
                if data.get("isDefault") == "default":
                    kind = "default"
                out[a["id"]].append((kind, p["destinationId"]))
    starts = [a for a in actions if (a.get("actionTemplateName") or "") == "Start"]
    seen, ordered = set(), []
    q = deque(a.get("id") for a in starts)
    while q:
        i = q.popleft()
        if i in seen or i not in byid:
            continue
        seen.add(i)
        ordered.append(byid[i])
        for _, d in out.get(i, []):
            q.append(d)
    ordered += [a for a in actions if a.get("id") not in seen]
    return ordered, out


def render(flow: dict, names: dict[str, str] | None = None) -> str:
    """Markdown digest of ONE flow. `names` = extra GUID -> display name (flows, credentials…)."""
    names = dict(names or {})
    ordered, edges = _order(flow)
    num = {a.get("id"): n for n, a in enumerate(ordered, 1)}
    # a node GUID inside a parameter (decisional branch targets) reads as "#N label"
    for a in ordered:
        names.setdefault(a.get("id"), f"#{num[a.get('id')]} {a.get('actionName') or ''}".strip())
    r = _Resolver(flow, names)

    lines = [f"# {_title(flow)}", "", f"- id: `{flow.get('id')}`"]
    if flow.get("description"):
        lines.append(f"- description: {flow['description']}")
    lines.append(f"- nodes: {len(ordered)}")
    lines += ["", "## Variables", "", "| name | direction | type | list | default |", "|---|---|---|---|---|"]
    for v in flow.get("variables") or []:
        dt = v.get("dataType") or ""
        tname = _BUILTIN_TYPES.get(dt) or names.get(dt) or dt[-12:]
        d = v.get("defaultValue")
        d = "" if d in (None, "") else str(d).replace("|", "\\|").replace("\n", " ")[:60]
        lines.append(f"| {v.get('name')} | {_DIRECTION.get(v.get('type'), v.get('type'))} | {tname} | "
                     f"{'yes' if v.get('isList') else ''} | {d} |")

    lines += ["", "## Nodes (execution order)", ""]
    for a in ordered:
        n = num[a.get("id")]
        tpl = a.get("actionTemplateName") or "?"
        label = a.get("actionName") or ""
        flag = " — DISABLED" if a.get("isDisabled") else ""
        lines.append(f"### {n}. {tpl}: {label}{flag}")
        nxt = [f"{k} → {num.get(d, '?')}" for k, d in edges.get(a.get("id"), [])]
        if nxt:
            lines.append("next: " + ", ".join(nxt))
        labels = _labels(a)
        for p in a.get("parameters") or []:
            v = p.get("value")
            if v in (None, "", [], {}, "00000000-0000-0000-0000-000000000000"):
                continue
            lbl = labels.get(p.get("tabPropertyId")) or (p.get("tabPropertyId") or "")[:8]
            if isinstance(v, str):
                text = _elide(r.literal(v, p.get("variable")))
                is_sql = bool(_SQL.match(text))
                if is_sql or "\n" in text or len(text) > 100:
                    lines += [f"- **{lbl}**:", "```sql" if is_sql else "```", text, "```"]
                else:
                    lines.append(f"- **{lbl}**: `{text}`")
            else:
                lines += [f"- **{lbl}**:", "```json", _structured(v, r), "```"]
        lines.append("")
    return "\n".join(lines)


def calls(flow: dict) -> list[str]:
    """Flow GUIDs this flow references in any node parameter (subprocess targets et al.)."""
    found = set()
    for a in flow.get("actions") or []:
        found.update(_GUID.findall(json.dumps(a.get("parameters") or [])))
    return sorted(found)
