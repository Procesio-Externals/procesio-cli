"""Document-signing forms: store the PDF a document-signing element asks people to sign.

A `document-signing` form element names its PDF in the `document` config. Three shapes
work: `{fileId, name}` (the designer's own: the file is stored server-side), a URL string
(fetched by the browser at fill time), or an inline `{src: "data:...", name}` (kept in the
form JSON itself, the legacy and export shape). Only the first keeps the form small and the
file under the platform's control, and the generic endpoint actions cannot produce it: the
upload is multipart.

    form-signing-upload-document   POST /api/form/signing/template-document
                                    multipart {package: <pdf>, formTemplateId}
                                    -> {fileId, name, pageCount}

With `--element` the same call points that element's `document` at the stored file, as a
surgical write (same invariants as form-set-element-config: existing config only, ids kept,
previous value returned, optimistic-concurrency guard). The form template must already be
saved: the upload is bound to its id.

Signers and signature spots are plain configs (`templateSigners`, `templateSpots`); set
them with form-set-element-config. FORM-DEV-GUIDE/11-DOCUMENT-SIGNING.md has the recipe.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.handlers.form_code import _fetch, build_put_body
from tools.procesio.handlers.form_events import _cfg, _find_element

UPLOAD_PATH = "/api/form/signing/template-document"
# ui-builder MAX_SIGNING_DOCUMENT_MB: the signing service's own limit
MAX_SIGNING_DOCUMENT_MB = 10


def _read_pdf(path: str) -> tuple[str, bytes]:
    p = Path(path)
    if not p.is_file():
        raise UsageError(f"--file {path!r} is not a file")
    data = p.read_bytes()
    if not data.startswith(b"%PDF"):
        raise UsageError(f"--file {p.name!r} is not a PDF (a signing document must be a PDF)")
    if len(data) > MAX_SIGNING_DOCUMENT_MB * 1024 * 1024:
        raise UsageError(f"--file {p.name!r} is {len(data) / 1048576:.1f} MB; the signing "
                         f"service takes at most {MAX_SIGNING_DOCUMENT_MB} MB")
    return p.name, data


def upload_document(client, args) -> dict:
    name, data = _read_pdf(args.file)
    form = el = None
    if args.element:
        form = _fetch(client, args.form_id)
        el = _find_element(form["data"].get("elements") or [], args.element)
        if el.get("type") != "document-signing":
            raise UsageError(f"element {args.element!r} is a {el.get('type')!r}, not a "
                             f"document-signing element")
        if _cfg(el, "document") is None:
            raise UsageError(f"element {args.element!r} has no `document` config")
    if args.dry_run:
        return {"dry_run": True, "would_upload": {"path": UPLOAD_PATH, "name": name,
                                                  "bytes": len(data),
                                                  "formTemplateId": args.form_id},
                "element": el.get("id") if el else None}

    stored = client.request_multipart(UPLOAD_PATH, files={
        "package": (name, data, "application/pdf"),
        "formTemplateId": (None, args.form_id),
    })
    result = {"uploaded": True, "form_id": args.form_id, "document": stored}
    if el is None:
        return result

    value = {"fileId": stored.get("fileId"), "name": stored.get("name") or name}
    c = _cfg(el, "document")
    previous = copy.deepcopy(c.get("value"))
    c["value"] = value                      # the config's own id is preserved
    guard = guard_unchanged(lambda: _fetch(client, args.form_id), form, force=args.force)
    client.put("/api/FormTemplate", build_put_body(form, data=form["data"]))
    result.update({"element_id": el.get("id"), "set": {"document": value},
                   "previous": {"document": previous}, "concurrency": guard})
    return result


def _upload_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--form-id", dest="form_id", required=True,
                   help="the SAVED form template the document belongs to")
    p.add_argument("--file", required=True,
                   help=f"local PDF to store (at most {MAX_SIGNING_DOCUMENT_MB} MB)")
    p.add_argument("--element",
                   help="document-signing element id or `name` config; when given, its "
                        "`document` config is set to the stored file {fileId, name}")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="check the PDF and the element, upload nothing")
    add_force_arg(p)


ACTIONS = {
    "form-signing-upload-document": ActionDef(
        func=upload_document, add_args=_upload_args, needs_client=True,
        description="Store the PDF a document-signing form element asks people to sign "
                    "(POST /api/form/signing/template-document, multipart) -> {fileId, name, "
                    "pageCount}. With --element, also set that element's `document` config to "
                    "the stored file, surgically (previous value returned). Signers and "
                    "signature spots are configs: set templateSigners / templateSpots with "
                    "form-set-element-config.",
    ),
}
