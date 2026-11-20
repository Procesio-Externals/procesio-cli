"""form-embed: everything a web page needs to embed a PROCESIO form with the form SDK.

The form SDK (`@procesio/form-sdk`, repository PROCESIO/procesio-form-sdk) puts an `<iframe>` on
any web page and talks to the form over `postMessage`: the page hears `ready`, `submit`,
`resize` and `error`, and can ask the form to `setValues`, `validate`, `focus`, `submit` or
`runTrigger`. This action reads one form and the environment's form runtime and answers what a
developer needs before writing a line:

- whether the form can be embedded (public, published, enabled) and why not;
- what the runtime at the environment's forms host supports (the embed bridge, and the page's
  requests into the form, which a runtime build can lack while still embedding);
- the field names `values` / `setValues` take and the trigger ids `runTrigger` takes;
- where the SDK comes from today (public npm or not), and a ready snippet (HTML, JS module or
  React), or with `--out` a complete page to open over http(s).

Read-only: it changes nothing on the form or the environment.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from tools.procesio import config, formlint
from tools.procesio.actiondef import ActionDef
from tools.procesio.dto.form import fieldpath
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg

SDK_PACKAGE = "@procesio/form-sdk"
SDK_REPO = "https://github.com/PROCESIO/procesio-form-sdk"
NPM_REGISTRY = "https://registry.npmjs.org/@procesio%2fform-sdk"
CDN_UMD = "https://cdn.jsdelivr.net/npm/@procesio/form-sdk@1/dist/procesio-form-sdk.umd.js"
# What the runtime bundle carries: the embed bridge's origin parameter, and the names of the
# requests a page sends (form-runtime src/embed/protocol.ts). A build can have the bridge
# without the requests: it embeds and reports events, and leaves every request unanswered.
_BRIDGE_MARK = "embedOrigin"
_REQUEST_MARKS = ("set-values", "run-trigger")
# Elements that hold no value a page could fill in.
_NO_VALUE = {"button", "heading", "paragraph", "divider", "image", "table", "dynamic-table-row",
             "static-table-row", "section", "columns", "column", "tabs", "tab", "side-panel",
             "chart", "file-viewer", "list", "list-item", "stepper", "step", "carousel"}
_FORM_TRIGGER = {"FORM_LOAD": "form onLoad", "FORM_BEFORE_SUBMIT": "form onBeforeSubmit",
                 "FORM_AFTER_SUBMIT": "form onAfterSubmit"}


def _name(el: dict) -> str | None:
    return next((c.get("value") for c in el.get("configs") or [] if c.get("key") == "name"), None)


def embeddability(form: dict) -> list[str]:
    """Why a page cannot show this form, empty when it can."""
    out = []
    if form.get("isPrivate"):
        out.append("the form is private: only a public form can be embedded today (a private "
                   "form needs a signed-in PROCESIO session, which another site does not have)")
    if form.get("status") == 0:
        out.append("the form is a draft (a designer Save leaves status 0): publish it, or the "
                   "page gets `not-found`")
    if form.get("state") is False:
        out.append("the form is disabled (state false)")
    return out


def fields(form: dict) -> list[dict]:
    """The fields a page can fill by name (`values`, `setValues`, `focus`)."""
    out = []
    elements = (form.get("data") or {}).get("elements") or []
    # a table row's cells repeat per row: a page cannot fill one by name
    rows = {e.get("id") for e in elements if e.get("type") in ("dynamic-table-row", "static-table-row")}
    for el in elements:
        kind = el.get("type")
        if el.get("parentId") in rows or kind in _NO_VALUE or not any(c.get("key") == fieldpath.value_key(kind)
                                        for c in el.get("configs") or []):
            continue
        name = _name(el)
        if name:
            label = next((c.get("value") for c in el.get("configs") or [] if c.get("key") == "label"), None)
            out.append({"name": name, "type": kind, "label": label})
    return out


def triggers(form: dict) -> list[dict]:
    """Every trigger `runTrigger` can run: element events and the form's own events."""
    out = []
    data = form.get("data") or {}
    for el in data.get("elements") or []:
        for cfg in el.get("configs") or []:
            for ev in formlint.slot_events(cfg.get("key"), cfg.get("value")):
                out.append(_trigger_row(ev, _name(el), cfg.get("key")))
    for ev in data.get("events") or []:
        if isinstance(ev, dict):
            out.append(_trigger_row(ev, None, _FORM_TRIGGER.get(ev.get("type"), ev.get("type"))))
    return [t for t in out if t["id"]]


def _trigger_row(ev: dict, element, slot) -> dict:
    cfg = ev.get("config") or {}
    what = ev.get("action")
    if what == "RUN_DATA_STORE_OPERATION":
        what = f"data store {cfg.get('operation')}"
    elif what == "RUN_PROCESS":
        what = f"process {cfg.get('processId')}"
    return {"id": ev.get("id"), "element": element, "on": slot, "type": ev.get("type"), "does": what}


def runtime_support(forms_base: str, http_get) -> dict:
    """What the runtime deployed at `forms_base` supports, read from its JS bundle."""
    try:
        html = http_get(f"{forms_base}/")
        scripts = re.findall(r'(/assets/index-[^"\']+\.js)', html or "")
        if not scripts:
            return {"embed": None, "requests": None, "checked": "no runtime bundle found"}
        bundle = http_get(f"{forms_base}{scripts[0]}") or ""
    except Exception as e:  # noqa: BLE001 - a support check never fails the action
        return {"embed": None, "requests": None, "checked": f"could not read the runtime: {e}"}
    return {"embed": _BRIDGE_MARK in bundle,
            "requests": all(m in bundle for m in _REQUEST_MARKS),
            "checked": f"{forms_base}{scripts[0]}"}


def npm_version(http_get) -> str | None:
    try:
        body = json.loads(http_get(NPM_REGISTRY) or "{}")
    except Exception:  # noqa: BLE001
        return None
    return ((body.get("dist-tags") or {}).get("latest")) if isinstance(body, dict) else None


def snippet(kind: str, opts: dict, sdk_url: str) -> str:
    """Ready-to-paste code. `opts` are the SDK `create` options."""
    js_opts = json.dumps(opts, indent=2).replace("\n", "\n  ")
    if kind == "html":
        return (f'<div id="procesio-form"></div>\n'
                f'<script src="{sdk_url}"></script>\n'
                f"<script>\n"
                f"  const form = ProcesioForm.create('#procesio-form', {js_opts});\n"
                f"  form.on('submit', ({{ success, submissionId }}) => {{\n"
                f"    if (success) console.log('Saved as', submissionId);\n"
                f"  }});\n"
                f"  form.on('error', ({{ code, message }}) => console.error(code, message));\n"
                f"</script>\n")
    if kind == "module":
        return (f"import {{ create }} from '{SDK_PACKAGE}';\n\n"
                f"const form = create('#procesio-form', {js_opts});\n"
                f"form.on('submit', ({{ success, submissionId }}) => {{\n"
                f"  if (success) console.log('Saved as', submissionId);\n"
                f"}});\n"
                f"await form.ready;\n")
    if kind == "react":
        return (f"import {{ useEffect, useRef }} from 'react';\n"
                f"import {{ create }} from '{SDK_PACKAGE}';\n\n"
                f"export function ProcesioForm({{ onSubmit }}) {{\n"
                f"  const box = useRef(null);\n"
                f"  useEffect(() => {{\n"
                f"    const form = create(box.current, {js_opts.replace(chr(10), chr(10) + '  ')});\n"
                f"    const off = form.on('submit', (e) => onSubmit && onSubmit(e));\n"
                f"    return () => {{ off(); form.destroy(); }};\n"
                f"  }}, [onSubmit]);\n"
                f"  return <div ref={{box}} />;\n"
                f"}}\n")
    raise UsageError(f"unknown --framework {kind!r}; use html, module or react")


def page(opts: dict, sdk_url: str, form_name: str) -> str:
    """A complete test page: the form, its events in a log, and the page-side calls."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{form_name} - embedded</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px}}#log{{background:#111;color:#9f9;
padding:12px;font-size:12px;white-space:pre-wrap;max-height:40vh;overflow:auto}}</style>
</head><body>
<div id="procesio-form"></div>
<pre id="log"></pre>
<script src="{sdk_url}"></script>
<script>
  const log = (...a) => document.getElementById('log').textContent +=
    a.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' ') + '\\n';
  const form = ProcesioForm.create('#procesio-form', {json.dumps(opts)});
  ['ready', 'submit', 'resize', 'error'].forEach(e => form.on(e, p => log(e, p)));
  window.form = form;  // try form.setValues({{...}}), form.validate(), form.runTrigger(id)
</script>
<!-- Open this page over http(s): opened from disk it hears no events. -->
</body></html>
"""


def _http_get(url: str) -> str:
    import requests   # lazy: only this action fetches outside the API
    r = requests.get(url, timeout=20)
    return r.text if r.status_code == 200 else ""


def form_embed(client, args, http_get=_http_get) -> dict:
    try:
        form = client.get(f"/api/FormTemplate/{args.id}")
    except ProcesioAPIError as e:
        raise UsageError(f"could not read form {args.id}: {e}") from e
    if isinstance(form, dict) and isinstance(form.get("result"), dict):
        form = form["result"]
    if not isinstance(form, dict) or "data" not in form:
        raise UsageError(f"form {args.id}: unexpected read shape")
    ws = form.get("workspaceId") or client.workspace_id or (client.profile or {}).get("workspace_id")
    tiny = None
    try:
        url = client.get(f"/api/CustomUrl/FormTemplate/{args.id}")
        url = url.get("result", url) if isinstance(url, dict) else None
        tiny = (url or {}).get("tinyUrl")
    except ProcesioAPIError:
        pass   # a form with no link yet; it embeds by id

    base = config.forms_base(client.profile)
    opts: dict = {"formId": args.id, "workspaceId": ws}
    if base != config.DEFAULT_FORMS_BASE:
        opts["baseUrl"] = base
    if args.values:
        values = json.loads(args.values)
        if not isinstance(values, dict):
            raise UsageError("--values must be a JSON object of {field name: value}")
        opts["values"] = values

    support = runtime_support(base, http_get)
    published = npm_version(http_get)
    sdk_url = args.sdk_url or CDN_UMD
    blockers = embeddability(form)
    names = fields(form)
    warnings = list(blockers)
    if args.values:
        unknown = sorted(set(opts["values"]) - {f["name"] for f in names})
        if unknown:
            warnings.append(f"values for {unknown}: the form has no field of that name, and the "
                            f"form skips them")
    if support["embed"] is False:
        warnings.append(f"the runtime at {base} has no embed bridge: the form shows but reports "
                        f"nothing, and the SDK raises `embed-unsupported` after 5 s")
    elif support["requests"] is False:
        warnings.append(f"the runtime at {base} embeds and reports events (ready, submit, "
                        f"resize, error) but does not answer the page's requests yet: "
                        f"setValues, validate, focus, submit and runTrigger wait with no answer. "
                        f"Prefill with `values` instead")
    if not published and not args.sdk_url:
        warnings.append(f"{SDK_PACKAGE} is not on the public npm registry yet, so the CDN URL in "
                        f"the snippet does not serve it. Build it from {SDK_REPO} (npm run build) "
                        f"and host dist/procesio-form-sdk.umd.js yourself (--sdk-url), or install "
                        f"it from GitHub Packages (@procesio:registry=https://npm.pkg.github.com)")
    out = {
        "form_id": args.id, "form_name": form.get("name"), "workspace_id": ws,
        "embeddable": not blockers, "path": tiny,
        "base_url": base, "runtime": support,
        "sdk": {"package": SDK_PACKAGE, "npm_latest": published, "repository": SDK_REPO,
                "script_url": sdk_url},
        "create_options": opts,
        "fields": names, "triggers": triggers(form),
        "snippet": snippet(args.framework, opts, sdk_url),
        "warnings": warnings,
    }
    if args.out:
        Path(args.out).write_text(page(opts, sdk_url, form.get("name") or "PROCESIO form"),
                                  encoding="utf-8", newline="\n")
        out["page"] = str(Path(args.out).resolve())
    return out


def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--framework", default="html", choices=("html", "module", "react"),
                   help="snippet flavour: a <script> page (default), an ES module, or a React component")
    p.add_argument("--values", help="JSON {field name: value} to prefill, checked against the form's fields")
    p.add_argument("--sdk-url", dest="sdk_url",
                   help="where the page loads the SDK's UMD build from (default: the npm CDN)")
    p.add_argument("--out", help="also write a complete test page here (open it over http(s))")


ACTIONS = {
    "form-embed": ActionDef(
        func=form_embed, add_args=_args, needs_client=True,
        description=("Embed a form in another web page with the PROCESIO form SDK: checks the "
                     "form can be embedded (public, published, enabled) and what the "
                     "environment's form runtime supports (the embed bridge; the page's "
                     "requests), lists the field names for values/setValues and the trigger ids "
                     "for runTrigger, and returns a ready snippet (html, module, react) or, "
                     "with --out, a complete test page. Read-only.")),
}
