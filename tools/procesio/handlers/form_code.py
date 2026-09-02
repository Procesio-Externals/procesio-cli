"""Surgical read/write of a form's global CSS + JavaScript (`Data.code`).

Why this exists as its own pair of actions rather than going through `form-edit`:
`form-edit` is a DESIRED-STATE editor — it rebuilds the whole DTO from a config, so
using it to change one field on a large hand-authored form means re-declaring every
element or losing them. Restyling an existing form is the common case, so these two
actions do a read-modify-write on the LIVE DTO and touch ONLY `Data.code`, leaving
the element tree, theme, data model and events byte-identical.

`Data.code` is the designer's "Switch to code" editor and is stored AES-encrypted
(see dto/form/code_cipher.py + FORM-STYLING-NOTES.md); there is no plaintext field
on the DTO, so both directions need the `form-code-key` secret. The CSS is injected
by the renderer as a `<style>` prepended inside the form root; the JS is replayed as
a synthetic RUN_JAVASCRIPT event on mount and on every change, so it must be
idempotent — it runs more than once per page.

`form-set-code` always returns the PREVIOUS decrypted css/js under `previous`, so an
overwrite is recoverable from the tool output alone.

Concurrency (applies to EVERY surgical form/process action): each is a read-modify-write
of the WHOLE live DTO via PUT — there is no version/ETag check, so it is last-write-wins.
Two surgical writes racing each other, or one racing a designer "Save", silently clobber
whichever landed first. Safe for the intended single-editor CLI use; a concurrent editor
is the caller's responsibility. An optimistic-concurrency guard is tracked in
todo/procesio-surgical-optimistic-concurrency.md.
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged

# Top-level DTO keys PUT /api/FormTemplate expects (PascalCase), mapped from the
# camelCase keys GET /api/FormTemplate/{id} returns. Kept explicit so an unexpected
# extra field on the GET is never echoed back into the PUT.
_PUT_KEYS = {
    "Id": "id",
    "Name": "name",
    "IsPrivate": "isPrivate",
    "Type": "type",
    "Status": "status",
    "State": "state",
    "Assignees": "assignees",
    "CustomUrl": "customUrl",
}


def build_put_body(form: dict, *, data: dict | None = None, name: str | None = None,
                   status: int | None = None, state: bool | None = None,
                   is_private: bool | None = None) -> dict:
    """The single canonical GET-echo -> accepted-PUT-body transform for form surgery.

    `PUT /api/FormTemplate` binds top-level keys by PascalCase (`Id`/`Name`/`Data`);
    the camelCase GET echo (`id`/`name`/`data`) is rejected 403. Every surgical
    save (set-code, set-element-event/config, form-update) routes through here so
    no caller hand-rolls the camelCase PUT the server refuses.

    `Data` round-trips verbatim from the echo unless `data` is given (the caller
    already merged its change in). Top-level `name`/`status`/`state` are overridden
    only when passed. `IsPrivate` is the reachability switch: `false` + `Status: 1` is what makes a
    form answer to an anonymous visitor on its custom URL, and it is a PUBLISHING decision, so it is
    never changed unless the caller asks. `CustomUrl` is ECHOED from the GET (the PUT ignores it either
    way — a form's custom URL is a separate entity managed via /api/CustomUrl/*, so
    echo and null are equivalent; verified live), and server metadata that isn't in
    `_PUT_KEYS` is dropped.
    """
    for k in ("id", "name", "data"):
        if not form.get(k):
            raise UsageError(f"GET /api/FormTemplate echo is missing {k!r}; refusing to PUT")
    dto = {k: form.get(src) for k, src in _PUT_KEYS.items()}   # PascalCase echo incl. CustomUrl
    dto["Data"] = form.get("data") or {} if data is None else data
    if name is not None:
        dto["Name"] = name
    if status is not None:
        dto["Status"] = status
    if state is not None:
        dto["State"] = bool(state)
    if is_private is not None:
        dto["IsPrivate"] = bool(is_private)
    return dto


def _code_key() -> str:
    from tools._lib import creds  # lazy: avoid the keyring import unless needed
    try:
        return creds.get("procesio", "form-code-key")
    except KeyError as e:
        raise UsageError(
            "missing credential agents-and-tools:procesio:form-code-key — the AES "
            "passphrase for a form's Data.code blob. Store it with: "
            "python scripts/set-credential.py procesio form-code-key"
        ) from e


def _fetch(client, form_id: str) -> dict:
    body = client.get(f"/api/FormTemplate/{form_id}")
    if isinstance(body, dict) and "result" in body and isinstance(body["result"], dict):
        body = body["result"]
    if not isinstance(body, dict) or "data" not in body:
        raise UsageError(f"unexpected FormTemplate payload for {form_id!r}")
    return body


def _decode(blob: str, key: str) -> dict:
    """Decrypt a Data.code blob into {"CSS": str, "JAVASCRIPT": str}.

    Two shapes both mean "no form-level code" and must not be treated as errors:
    an empty/absent blob, and a blob that decrypts to explicit JSON nulls — the
    latter is the designer's INITIAL state (the frontend seeds both slots to null),
    so it is what every form that has never used "Switch to code" carries. Both are
    normalized to empty strings here so callers can rely on getting strings.
    """
    if not blob:
        return {"CSS": "", "JAVASCRIPT": ""}
    from tools.procesio.dto.form import code_cipher
    try:
        raw = code_cipher.decrypt_code(blob, key)
    except Exception as e:  # noqa: BLE001 — wrong key and corrupt blob look alike
        raise UsageError(
            f"could not decrypt Data.code ({e}); the stored form-code-key does not "
            f"match the blob this form was saved with"
        ) from e
    return {"CSS": raw.get("CSS") or "", "JAVASCRIPT": raw.get("JAVASCRIPT") or ""}


def _read_text(inline, path, label: str):
    if inline is not None and path:
        raise UsageError(f"pass either --{label} or --{label}-file, not both")
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read()
    return inline


# -- actions -----------------------------------------------------------------

def get_code(client, args) -> dict:
    form = _fetch(client, args.id)
    code = _decode(form["data"].get("code") or "", _code_key())
    css, js = code.get("CSS", ""), code.get("JAVASCRIPT", "")
    if args.css_out:
        with open(args.css_out, "w", encoding="utf-8") as f:
            f.write(css)
    if args.js_out:
        with open(args.js_out, "w", encoding="utf-8") as f:
            f.write(js)
    return {"id": args.id, "name": form.get("name"), "css": css, "javascript": js,
            "css_bytes": len(css), "javascript_bytes": len(js)}


def set_code(client, args) -> dict:
    css = _read_text(args.css, args.css_file, "css")
    js = _read_text(args.javascript, args.js_file, "js")
    if css is None and js is None:
        raise UsageError("nothing to set: pass --css/--css-file and/or --javascript/--js-file")

    key = _code_key()
    form = _fetch(client, args.id)
    previous = _decode(form["data"].get("code") or "", key)
    # Omitting one side PRESERVES it — restyling should never silently drop the JS.
    css = previous["CSS"] if css is None else css
    js = previous["JAVASCRIPT"] if js is None else js

    from tools.procesio.dto.form import code_cipher
    blob = code_cipher.encrypt_code(js, css, key) if (css or js) else ""

    result = {
        "id": args.id, "name": form.get("name"),
        "css_bytes": len(css), "javascript_bytes": len(js),
        "previous": {"css": previous["CSS"], "javascript": previous["JAVASCRIPT"]},
        "elements": len(form["data"].get("elements") or []),
    }
    if args.dry_run:
        return {"dry_run": True, **result}

    guard = guard_unchanged(lambda: _fetch(client, args.id), form, force=args.force)
    data = dict(form["data"])
    data["code"] = blob
    client.put("/api/FormTemplate", build_put_body(form, data=data))
    return {"updated": True, "concurrency": guard, **result}


def _get_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--css-out", dest="css_out", help="also write the CSS to this file")
    p.add_argument("--js-out", dest="js_out", help="also write the JavaScript to this file")


def _set_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--css", help="CSS source as an inline string")
    p.add_argument("--css-file", dest="css_file", help="path to a .css file")
    p.add_argument("--javascript", help="JavaScript source as an inline string")
    p.add_argument("--js-file", dest="js_file", help="path to a .js file")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="report the change (and the previous code) without writing")
    add_force_arg(p)


ACTIONS = {
    "form-get-code": ActionDef(
        func=get_code, add_args=_get_args, needs_client=True,
        description="Read a form's global CSS + JavaScript (decrypts Data.code).",
    ),
    "form-set-code": ActionDef(
        func=set_code, add_args=_set_args, needs_client=True,
        description="Set a form's global CSS + JavaScript in place (surgical: only "
                    "Data.code changes; omitted side is preserved; returns the previous code).",
    ),
}
