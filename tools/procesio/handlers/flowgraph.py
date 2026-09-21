"""Offline structural reader actions over a .procesio export / live flow DTO.

`read-flow-graph` returns the canonical node/edge graph model (the substrate the canvas
layout tool and inspect-flow build on). No network; reads a file, '-' (stdin), or a raw
JSON string.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio import errors
from tools.procesio.flowmodel import read_bundle, read_flow
from tools.procesio.flowmodel.inspect import inspect as _inspect


def _load_in(value: str) -> str:
    """Resolve --in to a JSON string: '-' = stdin, an existing path = file, else literal."""
    if value == "-":
        return sys.stdin.read()
    try:
        p = Path(value)
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return value


def _in_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")
    p.add_argument("--resource-map", dest="resource_map", action="store_true",
                   help="emit every flow + the cross-process (process→process) edge list")


def read_flow_graph(args) -> dict:
    raw = _load_in(args.in_path)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise errors.UsageError(f"--in is not valid JSON: {e}")
    if args.resource_map:
        return {"result": read_bundle(obj)}
    return {"result": read_flow(obj, flow_id=args.flow_id).to_dict()}


def _inspect_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help=".procesio export or flow JSON: a path, '-' for stdin, or raw JSON")
    p.add_argument("--flow-id", dest="flow_id",
                   help="which flow when the bundle has more than one")


def inspect_flow(args) -> dict:
    raw = _load_in(args.in_path)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise errors.UsageError(f"--in is not valid JSON: {e}")
    return {"result": _inspect(obj, flow_id=args.flow_id)}


def _digest_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help="a flow JSON / API envelope / .procesio bundle file, OR a directory of them "
                        "(every *.json is read; subprocess targets resolve to titles across the set)")
    p.add_argument("--out", dest="out_dir",
                   help="write one <slug>.md per flow + INDEX.md here; omit to return the Markdown inline")
    p.add_argument("--names", dest="names",
                   help="optional JSON file {guid: display name} for ids outside the flows "
                        "(credentials, forms, data models)")


def _slug(title: str) -> str:
    import re as _re
    s = _re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return s[:80] or "untitled"


def flow_digest(args) -> dict:
    from tools.procesio.flowmodel import digest as _d
    src = Path(args.in_path)
    paths = sorted(src.glob("*.json")) if src.is_dir() else [src]
    if not paths:
        raise errors.UsageError(f"--in {args.in_path}: no .json files")
    flows = []
    for p in paths:
        try:
            flows += _d.unwrap(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            raise errors.UsageError(f"{p}: {e}")
    names = {f.get("id"): _d._title(f) for f in flows if f.get("id")}
    if args.names:
        try:
            names.update(json.loads(Path(args.names).read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            raise errors.UsageError(f"--names: {e}")
    if not args.out_dir:
        return {"result": {"count": len(flows),
                           "flows": [{"id": f.get("id"), "title": _d._title(f),
                                      "markdown": _d.render(f, names)} for f in flows]}}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = ["# Process index", "", "| process | nodes | calls |", "|---|---|---|"]
    written = []
    for f in sorted(flows, key=_d._title):
        slug = _slug(_d._title(f)) + "-" + str(f.get("id", ""))[:8]
        (out / f"{slug}.md").write_text(_d.render(f, names), encoding="utf-8")
        called = [names[g] for g in _d.calls(f) if g in names and g != f.get("id")
                  and g in {x.get("id") for x in flows}]
        index.append(f"| [{_d._title(f)}]({slug}.md) | {len(f.get('actions') or [])} | "
                     f"{'; '.join(sorted(set(called)))} |")
        written.append(f"{slug}.md")
    (out / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return {"result": {"count": len(flows), "out": str(out), "files": written + ["INDEX.md"]}}


def _form_digest_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help="a form template JSON (form-get output) or a directory of them; a sibling "
                        "<id>.code.json (form-get-code output) adds the global CSS/JS")
    p.add_argument("--processes", dest="processes",
                   help="directory of process JSON (API envelope / flow) to name RUN_PROCESS targets "
                        "and their variables")
    p.add_argument("--out", dest="out_dir",
                   help="write <slug>.md + <slug>/ (scripts, global form.js/form.css) per form and "
                        "FORM-PROCESS-MAP.md here; omit to return the Markdown inline")


def form_digest(args) -> dict:
    from tools.procesio.flowmodel import digest as _d
    from tools.procesio.flowmodel import formdigest as _fd
    src = Path(args.in_path)
    paths = ([p for p in sorted(src.glob("*.json")) if not p.name.endswith(".code.json")]
             if src.is_dir() else [src])
    if not paths:
        raise errors.UsageError(f"--in {args.in_path}: no form .json files")
    processes: dict = {}
    if args.processes:
        for p in sorted(Path(args.processes).glob("*.json")):
            try:
                for f in _d.unwrap(json.loads(p.read_text(encoding="utf-8"))):
                    if f.get("id"):
                        processes[f["id"]] = f
            except (json.JSONDecodeError, OSError):
                continue
    forms = []
    for p in paths:
        try:
            form = _fd.unwrap(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            raise errors.UsageError(f"{p}: {e}")
        code_path = p.with_name(p.stem + ".code.json")
        code = {}
        if code_path.exists():
            try:
                code = json.loads(code_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                code = {}
        forms.append((form, code))

    if not args.out_dir:
        return {"result": {"count": len(forms), "forms": [
            {"id": f.get("id"), "name": f.get("name"), "markdown": _fd.render(f, processes)[0]}
            for f, _ in forms]}}

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fmap = ["# Form → process map", "", "| form | element | trigger | process |", "|---|---|---|---|"]
    written = []
    for form, code in sorted(forms, key=lambda x: x[0].get("name") or ""):
        slug = _slug(form.get("name") or "form") + "-" + str(form.get("id", ""))[:8]
        md, scripts = _fd.render(form, processes)
        side = out / slug
        side.mkdir(exist_ok=True)
        for i, body in enumerate(scripts, 1):
            (side / f"script-{i:03d}.js").write_text(body, encoding="utf-8")
        if code.get("javascript"):
            (side / "form.js").write_text(code["javascript"], encoding="utf-8")
        if code.get("css"):
            (side / "form.css").write_text(code["css"], encoding="utf-8")
        extra = []
        if code.get("javascript") or code.get("css"):
            extra = ["", "## Global code", "",
                     f"- JavaScript: {len(code.get('javascript') or '')} chars → `{slug}/form.js`",
                     f"- CSS: {len(code.get('css') or '')} chars → `{slug}/form.css`"]
        (out / f"{slug}.md").write_text(md + "\n".join(extra) + f"\n\nScripts: `{slug}/script-NNN.js`\n",
                                        encoding="utf-8")
        written.append(f"{slug}.md")
        for link in _fd.process_links(form):
            pid = link["process_id"]
            title = (processes.get(pid) or {}).get("title") or pid
            fmap.append(f"| {form.get('name')} | {link['element']} | {link['trigger']} | {title} |")
    (out / "FORM-PROCESS-MAP.md").write_text("\n".join(fmap) + "\n", encoding="utf-8")
    return {"result": {"count": len(forms), "out": str(out), "files": written + ["FORM-PROCESS-MAP.md"]}}


ACTIONS = {
    "form-digest": ActionDef(
        func=form_digest, add_args=_form_digest_args, needs_client=False,
        description="Readable Markdown digest of forms (offline): structure tree, every element / "
                    "form-level event, RUN_PROCESS input/output maps with form paths and process "
                    "variables resolved to names, MAP_FORM_DATA conditions, scripts saved beside. "
                    "--out adds FORM-PROCESS-MAP.md.",
    ),
    "flow-digest": ActionDef(
        func=flow_digest, add_args=_digest_args, needs_client=False,
        description="Readable Markdown digest of flows (offline): variable contract, nodes in "
                    "execution order, each node's script/SQL/HTTP/subprocess parameters with "
                    "variable and flow ids resolved to names. --in a file or a directory; --out "
                    "writes one .md per flow + INDEX.md.",
    ),
    "read-flow-graph": ActionDef(
        func=read_flow_graph, add_args=_in_args, needs_client=False,
        description="Parse a .procesio export/flow into a node/edge graph model "
                    "(offline). --resource-map for the cross-process graph.",
    ),
    "inspect-flow": ActionDef(
        func=inspect_flow, add_args=_inspect_args, needs_client=False,
        description="Structural summary of a flow (offline): counts, action families, "
                    "branches, subprocess calls, resources, variables, advisory smells.",
    ),
}
