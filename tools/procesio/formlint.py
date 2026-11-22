"""Non-blocking safety lints for a form's Data DTO.

These encode form-build traps that the server ACCEPTS silently and that then cost
a debugging session to find (see PROCESIO-API-NOTES.md and FORM-DEV-GUIDE/08):

* **Phantom parentId** — an element whose `parentId` matches no element id renders
  on NO pane. Tab/container membership is by `parentId` = a container element's id;
  a dangling one is invisible, not an error (O6).
* **Duplicate id/name configs** — two elements sharing the designer `id` or `name`
  config collide for selectors and process mapping.
* **Patch wrapping mistake** — a form-update `--data` patch whose top-level key is
  not an existing Data field is merged in as an inert junk key; the classic case is
  wrapping the patch as `{"Data": {...}}` (O7).
* **Multiple-select without isList** — a select with `multiple=true` whose `value`
  config is not marked `isList` maps a list into a scalar.
* **IS_TRUE / IS_FALSE on a Boolean variable whose default is the text "false"** — the
  designer stores a Boolean form variable's default as a STRING ("False" / "false"), and a
  condition treats any non-empty string as true. Measured live: default "false" or "False"
  → IS_TRUE passes and IS_FALSE fails; default null → IS_TRUE fails and IS_FALSE passes.
  A gate like `isConfirmed IS_TRUE` on such a default is always open.
* **Field names a designer save renames** — a form built through the API keeps its field
  names as written, but one save in the designer re-keys `ProcesioForm.data.fields`: it
  splits each name on underscores, lowercases the parts and joins them in camelCase
  (`orderList` -> `orderlist`, `order_id` -> `orderId`; measured on two names, hyphens and
  spaces not tested). Form JS reading the original name then gets `undefined`. Only a
  single lowercase word survives unchanged. One warning per form, naming them all.
  That re-key happens only to a form whose `dataModelAttributeFormatVersion` is not "1": the
  designer reads a missing version as the legacy "0" format (user-playground
  Builder.component.vue; Form.model.ts::generateFormDataModel lower-cases under "0" and keeps
  the name under "1"). A form at "1" keeps its names through a designer save (measured
  2026-09-25 and 2026-10-05), so it draws no warning; form-create writes "1" since 2026-10-05.

* **Document-signing design** — a spot whose party is not a signer, a FILLER with no
  SIGNATURE spot on a locked setup, a MEMBER with no user, two FILLERs, a spot off the page,
  a PDF kept inline. The server stores all of these; they only fail when someone tries to sign.

* **Form JavaScript written for the wrong document** — form code and event scripts run in a
  hidden sandbox iframe, so a script that looks up or mounts elements through its own `document`
  and never through `window.parent.document` does nothing visible. Saved without a word.

Pure and side-effect-free: each returns a list of human-readable warning strings.
Warnings, never blockers — the caller attaches them to its result JSON.
"""
from __future__ import annotations

import re
from typing import Any


def _elements(data: Any) -> list:
    if isinstance(data, dict):
        els = data.get("elements")
        if isinstance(els, list):
            return els
    return []


def _cfg_value(element: dict, key: str):
    for c in element.get("configs") or []:
        if isinstance(c, dict) and c.get("key") == key:
            return c.get("value")
    return None


def _cfg(element: dict, key: str):
    for c in element.get("configs") or []:
        if isinstance(c, dict) and c.get("key") == key:
            return c
    return None


_EVENT_KEY = re.compile(r"^on[A-Z]\w*Events$")


def slot_events(key: Any, value: Any) -> list:
    """The events in an element's trigger slot (`onClickEvents`, `onInputEvents`, ...).

    The slot holds `{debounce, events: [...]}` on current forms and a bare list of events on
    older or hand-written ones; the runtime runs both. A reader that only knows the dict shape
    skips every event of such a form and reports nothing. A bare list counts only under an
    event key, because other configs (a select's options) are lists too."""
    if isinstance(value, dict):
        events = value.get("events")
        return [ev for ev in events if isinstance(ev, dict)] if isinstance(events, list) else []
    if isinstance(value, list) and isinstance(key, str) and _EVENT_KEY.match(key):
        return [ev for ev in value if isinstance(ev, dict)]
    return []


def _label(element: dict) -> str:
    """Best identifier for a message: the designer name, else the element id."""
    name = _cfg_value(element, "name")
    if isinstance(name, str) and name.strip():
        return f"{name.strip()!r}"
    return f"id {element.get('id')!r}"


def lint_phantom_parent(data: Any) -> list[str]:
    els = _elements(data)
    ids = {e.get("id") for e in els if isinstance(e, dict)}
    out = []
    for e in els:
        if not isinstance(e, dict):
            continue
        pid = e.get("parentId")
        if pid not in (None, "") and pid not in ids:
            out.append(
                f"element {_label(e)} has parentId {pid!r} matching no element on the "
                f"form — it renders on NO pane (dangling container reference). Point it "
                f"at a real container/tab element id, or set parentId to null for a "
                f"top-level element.")
    return out


def lint_duplicate_configs(data: Any) -> list[str]:
    els = _elements(data)
    out = []
    for cfg_key in ("id", "name"):
        seen: dict[str, int] = {}
        for e in els:
            if not isinstance(e, dict):
                continue
            val = _cfg_value(e, cfg_key)
            if isinstance(val, str) and val.strip():
                seen[val.strip()] = seen.get(val.strip(), 0) + 1
        for val, n in seen.items():
            if n > 1:
                out.append(
                    f"{n} elements share the same {cfg_key} config {val!r}; a duplicate "
                    f"{cfg_key} collides for CSS/JS selectors and process mapping — make "
                    f"each element's {cfg_key} unique.")
    return out


def lint_multiple_select_islist(data: Any) -> list[str]:
    els = _elements(data)
    out = []
    for e in els:
        if not isinstance(e, dict):
            continue
        multiple = _cfg_value(e, "multiple")
        if multiple is True or (isinstance(multiple, str) and multiple.lower() == "true"):
            value_cfg = _cfg(e, "value") or {}
            is_list = value_cfg.get("isList") if isinstance(value_cfg, dict) else None
            if not is_list:
                out.append(
                    f"element {_label(e)} is a multiple-select (multiple=true) but its "
                    f"value config is not marked isList — a multi-value selection maps "
                    f"into a scalar. Set isList on the value config / the mapped "
                    f"data-model attribute.")
    return out


def lint_patch_keys(existing_data: Any, patch: Any) -> list[str]:
    """A form-update --data patch whose top-level key is not an existing Data field
    is added as a (probably inert) junk key. Flags the classic `{"Data": {...}}`
    wrapping mistake explicitly."""
    if not isinstance(patch, dict) or not isinstance(existing_data, dict):
        return []
    known = set(existing_data.keys())
    out = []
    for k in patch:
        if k in known:
            continue
        if k.lower() == "data":
            out.append(
                f"patch top-level key {k!r} is not a Data field — this is almost "
                f"certainly the wrapping mistake: pass the INNER fields directly (e.g. "
                f'--data \'{{"hideBranding": true}}\'), not wrapped as {{{k!r}: {{...}}}}. '
                f"As written it creates an inert junk key that changes nothing.")
        else:
            sample = ", ".join(sorted(known)[:8]) or "(none)"
            out.append(
                f"patch top-level key {k!r} is not an existing Data field — it will be "
                f"ADDED as a new key (no existing value is changed). Existing fields "
                f"include: {sample}. Check for a typo/casing mismatch.")
    return out


_BOOLEAN_TESTS = ("IS_TRUE", "IS_FALSE")


def string_boolean_conditions(events: Any, variables: Any, where: str) -> list[str]:
    """Warnings for IS_TRUE / IS_FALSE conditions, in `events`, on a form variable whose
    default is the TEXT "false" (any case): the condition reads it as true. Shared by the
    whole-form lint and by form-set-element-chains, which checks only the chains it writes.
    A "true" text default is left alone - it evaluates the way it reads."""
    defaults = {v.get("id"): v for v in variables or [] if isinstance(v, dict)}
    out = []
    for ev in events or []:
        conds = ((ev or {}).get("config") or {}).get("conditions") or []
        for c in conds:
            op = str(c.get("operator") or "")
            var = defaults.get((c.get("leftOperator") or {}).get("value"))
            if op not in _BOOLEAN_TESTS or var is None:
                continue
            default = var.get("defaultValue")
            if not (isinstance(default, str) and default.strip().lower() == "false"):
                continue
            effect = ("PASSES although it reads false" if op == "IS_TRUE"
                      else "never passes although it reads false")
            out.append(
                f"{where}: condition `{var.get('name')} {op}` reads a form variable whose "
                f"default is the TEXT {default!r}; a condition treats any non-empty text as "
                f"true, so {op} {effect}, until something writes a real boolean (measured "
                f"live). Set the default to null, or branch with EQUALS on a value that really "
                f"is text (a select's value, or a field your own flow writes).")
    return out


def lint_string_boolean_conditions(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    variables = data.get("variables") or []
    out = string_boolean_conditions(data.get("events") or [], variables, "form-level event")
    for e in _elements(data):
        if not isinstance(e, dict):
            continue
        for c in e.get("configs") or []:
            if isinstance(c, dict) and str(c.get("key", "")).startswith("on"):
                events = slot_events(c.get("key"), c.get("value"))
                if events:
                    out += string_boolean_conditions(events, variables,
                                                     f"element {_label(e)} {c.get('key')}")
    return out


_SINGLE_WORD = re.compile(r"[a-z0-9]+")
_UNDERSCORED = re.compile(r"[A-Za-z0-9_]+")


def designer_key(name: str) -> str | None:
    """The key a designer save gives a field name, or None where that rule was not
    measured (a name with hyphens, spaces or other characters)."""
    if not _UNDERSCORED.fullmatch(name or ""):
        return None
    parts = [p.lower() for p in name.split("_") if p]
    if not parts:
        return None
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def lint_field_names(data: Any) -> list[str]:
    """One warning naming every element whose name a designer save would re-key.

    None for a form at dataModelAttributeFormatVersion "1": the designer keeps its names."""
    if isinstance(data, dict) and str(data.get("dataModelAttributeFormatVersion") or "") == "1":
        return []
    renamed = []
    for el in _elements(data):
        name = _cfg_value(el, "name")
        if not isinstance(name, str) or not name or _SINGLE_WORD.fullmatch(name):
            continue
        key = designer_key(name)
        renamed.append(f"{name} -> {key}" if key else f"{name} -> (renamed; rule not measured)")
    if not renamed:
        return []
    shown = ", ".join(renamed[:8])
    if len(renamed) > 8:
        shown += f", and {len(renamed) - 8} more"
    return [f"{len(renamed)} field name(s) are not a single lowercase word, and a save in the "
            f"designer re-keys them in ProcesioForm.data.fields: {shown}. Form JS that reads "
            f"the original name then gets undefined. Read fields through a lookup that ignores "
            f"case and underscores, or name them as single lowercase words "
            f"(FORM-DEV-GUIDE/08-PITFALLS.md)."]


# Form custom CSS is scoped to the form container: every selector's last compound gets
# `:where([data-form-css-scope=<id>], [data-form-css-scope=<id>] *)` appended. UI the JS mounts
# on document.body, and `:root` / `html` / `body` rules, sit outside that scope and get no style
# unless the JS copies the attribute onto <html>. See FORM-DEV-GUIDE/02-CODE-INJECTION.md §2.
_SCOPE_ATTR = "data-form-css-scope"
_BODY_MOUNT = re.compile(
    r"document\.body\s*\.\s*(?:appendChild|append|prepend|insertBefore|insertAdjacentHTML|"
    r"insertAdjacentElement|replaceChildren)\b"
    r"|document\.body\s*\.\s*innerHTML\s*\+?="
    r"|\.mount\(\s*(?:document\.body\b|['\"]body['\"])")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_PRELUDE = re.compile(r"([^{}]+)\{")
_PAGE_SELECTOR = re.compile(r"(:root|html|body)(?![\w-])", re.I)


def lint_form_code_scope(css: str | None, js: str | None) -> list[str]:
    """One warning when the form code relies on styling outside the form's CSS scope.

    Fires when the JS mounts UI on document.body, or the CSS styles :root / html / body, and the
    JS never mentions the scope attribute (the known fix copies it onto <html>). A form whose UI
    stays inside the form container triggers neither and gets no warning."""
    css, js = css or "", js or ""
    if _SCOPE_ATTR in js:
        return []
    reasons = []
    if _BODY_MOUNT.search(js):
        reasons.append("the JS renders UI onto document.body")
    heads = set()
    for prelude in _CSS_PRELUDE.findall(_CSS_COMMENT.sub("", css)):
        prelude = prelude.strip()
        if prelude.startswith("@"):
            continue
        for sel in prelude.split(","):
            m = _PAGE_SELECTOR.match(sel.strip())
            if m:
                heads.add(m.group(1).lower())
    if heads:
        reasons.append("the CSS styles " + " / ".join(sorted(heads)))
    if not reasons:
        return []
    return [f"form code: {' and '.join(reasons)}, but the form's custom CSS is scoped to the form "
            f"container ([{_SCOPE_ATTR}]), so those styles will not apply. Before mounting, copy the "
            f"container's {_SCOPE_ATTR} value onto <html> (FORM-DEV-GUIDE/02-CODE-INJECTION.md §2)."]


# Document-signing element limits and vocabulary (Web-Api signing manager + ui-builder
# documentSigning.ts). The designer places SIGNATURE / PRINTED_NAME / DATE_SIGNED / TEXT;
# the API also takes FIRST_NAME / LAST_NAME.
_SIGNER_KINDS = {"MEMBER", "FILLER"}
_SPOT_TYPES = {"SIGNATURE", "PRINTED_NAME", "DATE_SIGNED", "TEXT", "FIRST_NAME", "LAST_NAME"}
_MAX_SIGNERS, _MAX_SPOTS, _MAX_TEXT, _MAX_LABEL = 50, 1000, 256, 128


def _spot_geometry_problem(s: dict) -> str | None:
    try:
        page = s.get("page")
        x, y, w, h = (float(s.get(k)) for k in ("x", "y", "w", "h"))
    except (TypeError, ValueError):
        return "needs numeric x, y, w, h"
    if not isinstance(page, int) or page < 1:
        return f"page {page!r} must be a 1-based integer"
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1.0001 or y + h > 1.0001:
        return "x, y, w, h are fractions of the page (0..1, top-left origin) and must fit on it"
    return None


def lint_document_signing(data: Any) -> list[str]:
    """Traps in a document-signing element's design that the server stores without a word
    and that only show when someone tries to sign: a spot whose party is not a signer, a
    FILLER with no SIGNATURE spot while setupEditable is off (a signer without a spot may
    place their own since form-runtime v1.33.0, but on a public form this filler gets no way
    to, and the submit stays blocked), a MEMBER with no user, more than one FILLER, geometry
    off the page, and a PDF stored inline."""
    out = []
    for el in _elements(data):
        if not isinstance(el, dict) or el.get("type") != "document-signing":
            continue
        who = _label(el)
        signers = _cfg_value(el, "templateSigners") or []
        spots = _cfg_value(el, "templateSpots") or []
        if not isinstance(signers, list) or not isinstance(spots, list):
            out.append(f"document-signing {who}: templateSigners and templateSpots must be lists")
            continue
        ids = [s.get("id") for s in signers if isinstance(s, dict)]
        kinds = [str(s.get("kind") or "MEMBER").upper() for s in signers if isinstance(s, dict)]
        for s in signers:
            if not isinstance(s, dict) or not s.get("id"):
                out.append(f"document-signing {who}: a signer without an id is ignored")
                continue
            kind = str(s.get("kind") or "MEMBER").upper()
            if kind not in _SIGNER_KINDS:
                out.append(f"document-signing {who}: signer {s['id']!r} kind {kind!r} is "
                           f"dropped by the designer (MEMBER or FILLER)")
            elif kind == "MEMBER" and not s.get("userId"):
                out.append(f"document-signing {who}: MEMBER signer {s['id']!r} needs the "
                           f"userId of a workspace member")
        if kinds.count("FILLER") > 1:
            out.append(f"document-signing {who}: at most one FILLER signer (the person "
                       f"filling the form); found {kinds.count('FILLER')}")
        if "MEMBER" in kinds:
            out.append(f"document-signing {who}: a MEMBER signer keeps the form private "
                       f"(the designer refuses Make form public while one is set)")
        if len(signers) > _MAX_SIGNERS or len(spots) > _MAX_SPOTS:
            out.append(f"document-signing {who}: at most {_MAX_SIGNERS} signers and "
                       f"{_MAX_SPOTS} spots per envelope")
        signed = set()
        for sp in spots:
            if not isinstance(sp, dict):
                continue
            sid = sp.get("spotId") or "?"
            if sp.get("partyId") not in ids:
                out.append(f"document-signing {who}: spot {sid!r} names party "
                           f"{sp.get('partyId')!r}, which is not a templateSigners id")
            stype = str(sp.get("type") or "")
            if stype not in _SPOT_TYPES:
                out.append(f"document-signing {who}: spot {sid!r} type {stype!r} is not one of "
                           f"{sorted(_SPOT_TYPES)}")
            if stype == "SIGNATURE":
                signed.add(sp.get("partyId"))
            if len(str(sp.get("value") or "")) > _MAX_TEXT or len(str(sp.get("label") or "")) > _MAX_LABEL:
                out.append(f"document-signing {who}: spot {sid!r} text is limited to "
                           f"{_MAX_TEXT} characters and its label to {_MAX_LABEL}")
            problem = _spot_geometry_problem(sp)
            if problem:
                out.append(f"document-signing {who}: spot {sid!r} {problem}")
        stuck = [s.get("id") for s in signers if isinstance(s, dict)
                 and str(s.get("kind") or "MEMBER").upper() == "FILLER"
                 and s.get("id") and s.get("id") not in signed]
        if stuck and _cfg_value(el, "setupEditable") in (False, "false"):
            out.append(f"document-signing {who}: FILLER signer {stuck} has no SIGNATURE spot and "
                       f"setupEditable is off; on a public form that filler gets no way to sign "
                       f"and the submit stays blocked, so place a spot or turn setupEditable on")
        doc = _cfg_value(el, "document")
        if isinstance(doc, dict) and str(doc.get("src") or "").startswith("data:"):
            out.append(f"document-signing {who}: the PDF is inline in the form (a data: URL); "
                       f"store it with form-signing-upload-document and set "
                       f"document={{fileId, name}} instead")
    return out


# The form's number field is no native number input (ui-builder 0.184 / 1.41, design-system
# ADR 0001): it renders <input type="text" inputmode="decimal">, so a selector on
# type=number matches nothing.
_NUMBER_TYPE_SELECTOR = re.compile(r"""type\s*=\s*\\?["']?number\b|\.type\s*===?\s*["']number["']""", re.I)
# Since form-runtime 1.30 / designer 1.115, `deserialze(x)` is replaced with the value as JSON
# (a string variable that holds JSON goes in parsed, any other string as a quoted literal).
# Wrapped in quotes, the call now yields text that carries the quotes of the literal.
_QUOTED_DESERIALZE = re.compile(r"""(["'`])\s*deserialze\(""")


def lint_form_code_runtime(css: str | None, js: str | None, where: str = "form code") -> list[str]:
    """Code written for runtime behaviour that changed in the 2026-10 front ends."""
    out = []
    text = f"{css or ''}\n{js or ''}"
    if _NUMBER_TYPE_SELECTOR.search(text):
        out.append(f"{where} selects a number input by type=number, but a form's number field "
                   f"renders <input type=\"text\" inputmode=\"decimal\">: the selector matches "
                   f"nothing. Select it by the element's class or name instead.")
    if _QUOTED_DESERIALZE.search(js or ""):
        out.append(f"{where} wraps deserialze(...) in quotes. The runtime now inserts the value "
                   f"as JSON (a string as a quoted literal), so the quotes end up inside the "
                   f"value. Write deserialze(name) without quotes around it.")
    return out


# Form JavaScript (the form-level code and every RUN_JAVASCRIPT event) runs in a hidden sandbox
# iframe that the runtime builds for the run and removes afterwards (form-runtime
# services/triggers/javascript/Sandbox.ts). `document` there is the iframe's own page, which holds
# nothing but the script: a lookup finds no form element, and what the script mounts is never on
# screen. The server stores such code without a word and the form shows no error, so the only
# symptom is "nothing happens". See FORM-DEV-GUIDE/02-CODE-INJECTION.md §3-§4.
_JS_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\\\w\"'`])//[^\n]*", re.S)
_OWN_DOCUMENT = re.compile(
    r"(?<![.\w$])(?:(?:window|self|globalThis)\s*\.\s*)?document\s*\.\s*"
    r"(?:getElementById|getElementsBy\w+|querySelector(?:All)?|body|documentElement|head|forms|"
    r"activeElement|addEventListener)\b")
_PARENT_DOCUMENT = re.compile(r"(?<![\w$])(?:parent|top)\s*\.\s*document\b|\bframeElement\b")
# `var W = window.parent && window.parent !== window ? window.parent : window;` - the name the
# parent window is kept under, so that `W.document` counts as reaching the page.
_PARENT_ALIAS = re.compile(
    r"([A-Za-z_$][\w$]*)\s*=(?!=)[^;\n]*?(?<![.\w$])(?:window\s*\.\s*)?(?:parent|top)\b")


def uses_only_sandbox_document(js: str | None) -> bool:
    """True when the script works on the DOM through its own `document` and never reaches the
    document of the page that shows the form.

    A script that keeps the parent window only to hang a value on it (`P.__state = ...`) still
    counts: the DOM calls are what must reach the page. A script that reaches the parent document
    anywhere is left alone, because the documented pattern injects a runtime into the parent and
    that runtime's own `document` is the right one."""
    code = _JS_COMMENT.sub("", js or "")
    if not _OWN_DOCUMENT.search(code):
        return False
    if _PARENT_DOCUMENT.search(code):
        return False
    for alias in set(_PARENT_ALIAS.findall(code)):
        if re.search(rf"(?<![.\w$]){re.escape(alias)}\s*\.\s*document\b", code):
            return False
    return True


_SANDBOX_ADVICE = ("Form JavaScript runs in a hidden sandbox iframe, and `document` there is the "
                   "iframe's own page: a lookup finds no form element and what the script mounts "
                   "is never on screen. Reach the form through window.parent.document, and put "
                   "code that must outlive the run in a runtime installed in the parent page "
                   "(FORM-DEV-GUIDE/02-CODE-INJECTION.md §3-§4).")


# Carried by the answers that READ form JavaScript (form-get-code, form-get-element-events). A
# rule stated only in the guidance reaches a caller that loads the guidance; the read is the one
# step every edit of a script starts with, so the rule is repeated there, in a few lines.
SANDBOX_NOTE = ("Form JavaScript runs in a hidden sandbox iframe that the runtime removes after the "
                "run: `document` is the iframe's own page, not the form. Reach the form through "
                "window.parent.document, and put code that must outlive the run (listeners, timers, "
                "a game loop) in a runtime installed once in the parent page. Guide: "
                "FORM-DEV-GUIDE/02-CODE-INJECTION.md (guidance topic forms-code).")


def lint_form_code_sandbox(js: str | None, where: str = "form code") -> list[str]:
    """One warning when the script reads or changes the DOM only through the sandbox's document."""
    if not uses_only_sandbox_document(js):
        return []
    return [f"{where} works on the page through `document` and never through "
            f"window.parent.document. {_SANDBOX_ADVICE}"]


def lint_event_scripts(data: Any) -> list[str]:
    """The script lints over every RUN_JAVASCRIPT event of the form's elements. The sandbox lint
    is reported once for the form, naming the scripts, so a form with many handlers written the
    same way does not repeat the advice for each."""
    out: list[str] = []
    sandboxed: list[str] = []
    for el in _elements(data):
        for c in el.get("configs") or []:
            for ev in slot_events(c.get("key"), c.get("value")):
                if ev.get("action") == "RUN_JAVASCRIPT":
                    code = (ev.get("config") or {}).get("code")
                    where = f"the {c.get('key')} script of {_label(el)}"
                    for w in lint_form_code_runtime(None, code, where):
                        if w not in out:
                            out.append(w)
                    if uses_only_sandbox_document(code) and where not in sandboxed:
                        sandboxed.append(where)
    if sandboxed:
        shown = ", ".join(sandboxed[:8])
        if len(sandboxed) > 8:
            shown += f", and {len(sandboxed) - 8} more"
        verb = "works" if len(sandboxed) == 1 else "work"
        out.append(f"{shown} {verb} on the page through `document` and never through "
                   f"window.parent.document. {_SANDBOX_ADVICE}")
    return out


def lint_form_data(data: Any) -> list[str]:
    """All structural (element-level) lints for a form's Data."""
    return (lint_phantom_parent(data)
            + lint_duplicate_configs(data)
            + lint_multiple_select_islist(data)
            + lint_string_boolean_conditions(data)
            + lint_field_names(data)
            + lint_document_signing(data)
            + lint_event_scripts(data))
