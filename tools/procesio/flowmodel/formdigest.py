"""Readable Markdown digest of a PROCESIO form — its structure and its CONVERSATION with processes.

A form talks to processes through element events (`on<Trigger>Events`) and form-level events
(`Data.events`, e.g. FORM_LOAD). What an audit needs from each:
  - RUN_PROCESS   : which process, sync or not, and the two maps — inputMap (process input
                    variable <- form value) and outputMap (form value <- process output variable)
  - MAP_FORM_DATA : which form values it sets to what, under which conditions
  - RUN_JAVASCRIPT: the script (its header comment inline, the full body in a side file)
  - anything else : the config, ids resolved

Form values are addressed by dotted GUID paths into the form data model
(`<form>.<root>.<elementId>.<attributeId>`, or a bare form-variable id). Every GUID segment is
resolved to a name — elements by their designer `name`, attributes and variables by the data
model — so a mapping reads `Table_EE.value <- extracted_table_rows`.

Pure: dicts in, strings out. `processes` = {process_id: flow dict} to name process variables and
titles; without it they stay GUIDs.
"""
from __future__ import annotations

import json
import re

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_EVENT_KEY = re.compile(r"^on[A-Z]\w*Events$")
_ROOT = "11223344-5566-7788-99aa-aabbccddeeff"   # the synthetic root model under `form`


def unwrap(obj) -> dict:
    """The form template dict from the API envelope or a bare template."""
    if isinstance(obj, str):
        obj = json.loads(obj)
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        obj = obj["result"]
    return obj if isinstance(obj, dict) else {}


def _data(form: dict) -> dict:
    d = form.get("data") or form.get("Data") or {}
    return json.loads(d) if isinstance(d, str) else d


def _cfg(el: dict, key: str):
    for c in el.get("configs") or []:
        if c.get("key") == key:
            return c.get("value")
    return None


class _Names:
    def __init__(self, data: dict, processes: dict | None):
        self.map: dict[str, str] = {}
        self.process_vars: dict[str, dict[str, str]] = {}
        self.titles: dict[str, str] = {}

        def walk(node):
            if isinstance(node, dict):
                if node.get("id") and node.get("name"):
                    self.map.setdefault(node["id"], node["name"])
                for a in node.get("attributes") or []:
                    walk(a)
        walk(data.get("dataModel") or {})
        for v in data.get("variables") or []:
            if v.get("id"):
                self.map[v["id"]] = v.get("name")
        # element names win over their data-model node names (same GUID, clearer label)
        for el in data.get("elements") or []:
            n = _cfg(el, "name")
            if el.get("id") and n:
                self.map[el["id"]] = n
        for pid, flow in (processes or {}).items():
            self.titles[pid] = (flow.get("title") or "").strip()
            self.process_vars[pid] = {v.get("id"): v.get("name") for v in flow.get("variables") or []}

    def path(self, value) -> str:
        """A dotted GUID path -> dotted names (form/root segments dropped)."""
        if not isinstance(value, str) or not value:
            return "∅" if value in (None, "") else json.dumps(value, ensure_ascii=False)
        parts = value.split(".")
        # drop the implicit `form` variable and the synthetic root model segment
        while len(parts) > 1 and (self.map.get(parts[0]) == "form" or parts[0].startswith(_ROOT)):
            parts = parts[1:]
        return ".".join(self.map.get(p, p) for p in parts)

    def text(self, s: str, pid: str | None = None) -> str:
        pv = self.process_vars.get(pid or "", {})

        def sub(m):
            g = m.group(0)
            return pv.get(g) or self.map.get(g) or (("[[" + self.titles[g] + "]]") if g in self.titles else g)
        return _GUID.sub(sub, s)


def _code_header(code: str) -> str:
    """The script's leading comment block (how these scripts document themselves), else line 1."""
    lines = code.strip().splitlines()
    head = []
    for ln in lines:
        s = ln.strip()
        if s.startswith(("//", "/*", "*")):
            head.append(s.lstrip("/* ").rstrip())
            if len(head) >= 4:
                break
        elif head or s:
            break
    head = [h for h in head if h and not set(h) <= set("=-─ ")]
    return " / ".join(head)[:200] if head else (lines[0][:120] if lines else "")


def _side(x):
    """A map row / condition side is either `{"value": X}` or a bare `X`; real forms
    use both shapes (a RUN_PROCESS map row often carries the value inline as a string)."""
    return x.get("value") if isinstance(x, dict) else x


def _conditions(conds, names: _Names) -> list[str]:
    out = []
    for c in conds or []:
        left = _side(c.get("leftOperator"))
        right = _side(c.get("rightOperator"))
        join = {0: "", 1: "AND ", 2: "OR "}.get(c.get("logicOperator"), "")
        r = f" {names.path(right)}" if right not in (None, "") else ""
        out.append(f"{join}{names.path(left)} {c.get('operator')}{r}".strip())
    return out


def _event(ev: dict, names: _Names, scripts: list) -> list[str]:
    act = ev.get("action")
    cfg = ev.get("config") or {}
    if act == "RUN_PROCESS":
        pid = cfg.get("processId")
        title = names.titles.get(pid) or pid
        pv = names.process_vars.get(pid, {})
        lines = [f"RUN_PROCESS → **{title}** ({'sync' if cfg.get('syncRun') else 'async'})"]
        for m in cfg.get("inputMap") or []:
            left = _side(m.get("left"))
            lines.append(f"  - in: `{pv.get(left, left)}` ← `{names.path(_side(m.get('right')))}`")
        for m in cfg.get("outputMap") or []:
            left = _side(m.get("left"))
            lines.append(f"  - out: `{names.path(_side(m.get('right')))}` ← `{pv.get(left, left)}`")
        return lines
    if act == "MAP_FORM_DATA":
        lines = ["MAP_FORM_DATA"]
        conds = _conditions(cfg.get("conditions"), names) if cfg.get("areConditionsConfigured") else []
        if conds:
            lines.append("  - when: " + " ".join(conds))
        for m in cfg.get("mapping") or []:
            lines.append(f"  - set `{names.path(m.get('left'))}` = `{names.path(m.get('right')) if _GUID.match(str(m.get('right') or '')) else m.get('right')}`")
        return lines
    if act == "RUN_JAVASCRIPT":
        code = cfg.get("code") or ""
        scripts.append(code)
        return [f"RUN_JAVASCRIPT ({len(code)} chars, script #{len(scripts)}): {_code_header(code)}"]
    return [f"{act}: `{names.text(json.dumps(cfg, ensure_ascii=False))[:400]}`"]


def render(form: dict, processes: dict | None = None) -> tuple[str, list[str]]:
    """(Markdown digest, [script bodies referenced as script #N])."""
    data = _data(form)
    names = _Names(data, processes)
    els = data.get("elements") or []
    kids: dict = {}
    for e in els:
        kids.setdefault(e.get("parentId"), []).append(e)
    scripts: list[str] = []

    lines = [f"# {form.get('name')}", "", f"- id: `{form.get('id')}`",
             f"- status: {'published' if form.get('status') == 1 else 'draft'}, "
             f"{'private' if form.get('isPrivate') else 'public'}",
             f"- elements: {len(els)}"]
    fvars = data.get("variables") or []
    if fvars:
        lines += ["", "## Form variables", ""]
        for v in fvars:
            if v.get("name") != "form":
                lines.append(f"- `{v.get('name')}`{' (list)' if v.get('isList') else ''}"
                             f"{' default=' + str(v.get('defaultValue')) if v.get('defaultValue') not in (None, '') else ''}")

    fevents = data.get("events") or []
    if fevents:
        lines += ["", "## Form-level events", ""]
        for ev in fevents:
            body = _event(ev, names, scripts)
            lines.append(f"- **{ev.get('type')}** → {body[0]}")
            lines += ["  " + b for b in body[1:]]

    lines += ["", "## Structure and element events", ""]

    def walk(parent, depth):
        for e in kids.get(parent, []):
            name = _cfg(e, "name") or ""
            dom = _cfg(e, "id")
            label = _cfg(e, "label")
            vis = _cfg(e, "visible")
            bits = [f"{'  ' * depth}- **{e.get('type')}** `{name}`"]
            if dom and dom != name:
                bits.append(f"#{dom}")
            if isinstance(label, str) and label and "<" not in label:
                bits.append(f"“{label[:60]}”")
            if vis is False:
                bits.append("(hidden by default)")
            lines.append(" ".join(bits))
            for c in e.get("configs") or []:
                v = c.get("value")
                if _EVENT_KEY.match(c.get("key") or "") and isinstance(v, dict) and v.get("events"):
                    trig = c["key"][2:-6]
                    for ev in v["events"]:
                        body = _event(ev, names, scripts)
                        lines.append(f"{'  ' * (depth + 1)}- on {trig}: {body[0]}")
                        lines.extend(f"{'  ' * (depth + 1)}{b}" for b in body[1:])
            walk(e.get("id"), depth + 1)
    walk(None, 0)
    return "\n".join(lines) + "\n", scripts


def process_links(form: dict) -> list[dict]:
    """[{process_id, trigger, element}] for every RUN_PROCESS the form fires."""
    data = _data(form)
    out = []
    for ev in data.get("events") or []:
        if ev.get("action") == "RUN_PROCESS":
            out.append({"process_id": (ev.get("config") or {}).get("processId"),
                        "trigger": ev.get("type"), "element": "(form)"})
    for e in data.get("elements") or []:
        for c in e.get("configs") or []:
            v = c.get("value")
            if _EVENT_KEY.match(c.get("key") or "") and isinstance(v, dict):
                for ev in v.get("events") or []:
                    if ev.get("action") == "RUN_PROCESS":
                        out.append({"process_id": (ev.get("config") or {}).get("processId"),
                                    "trigger": c["key"][2:-6], "element": _cfg(e, "name")})
    return out
