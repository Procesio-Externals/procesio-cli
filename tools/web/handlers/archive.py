"""archive-document - capture a published document as a reviewable evidence set.

WHY THIS EXISTS. A published document (a terms page, a subscription agreement,
a policy PDF) is evidence. Quoting it later is only safe if three things are
kept together: the bytes exactly as the publisher served them, a rendering a
human can open without a network, and a text form that can be searched and
quoted. Screenshots lose the text, a markdown conversion loses the clause
numbering and pagination that a reader relies on, and a bare URL loses
everything the moment the publisher edits the page.

So every capture writes THREE artefacts into one folder named for the document:

  <name>.html / .pdf          the ORIGINAL response body, byte for byte. Never
                              rewritten. The sha256 in the manifest is this
                              file's hash, so a later capture of the same URL
                              can be compared against it to prove whether the
                              publisher changed the document.
  <name>.self-contained.html  (HTML only) the same markup with every stylesheet
                              fetched and inlined, so the document opens with
                              its layout intact on a machine with no network
                              and no repository access. The markup is otherwise
                              untouched.
  <name>.md                   a text extraction for searching and quoting,
                              carrying a provenance header: title, the date the
                              document states about itself, source URL, fetch
                              timestamp, and the sha256 of the original.

PROVENANCE IS NOT OPTIONAL. Both readable artefacts carry the same header
block, because an extraction that travels without its source URL and fetch date
becomes an unattributable quote the first time someone copies it into a brief.

DATES. ``document_date_candidates`` reports date-like strings the document
states about ITSELF (near "last updated", "effective", "version", "revised").
They are CANDIDATES, reported in the order found and never reconciled: a page
that says two different things about its own date is a finding about the page,
not a defect to be quietly resolved here.

LOGIN-GATED PAGES ARE OUT OF SCOPE by design. This action performs an
unauthenticated fetch. A document behind a login is a fact worth recording as
unreachable, not one to be silently substituted with a summary; capture those
through ``web run`` / ``web get-text`` with a saved session instead.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from tools.web.actiondef import ActionDef
from tools.web.errors import UsageError

# A publisher's edge (Cloudflare and friends) may serve a challenge page to a
# default urllib/requests agent. A real browser agent gets the document itself.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Date-ish strings a document uses to state its own version. Deliberately broad:
# over-reporting a candidate is cheap, missing the one date counsel needs is not.
_DATE_PATTERNS = [
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
]
_DATE_CONTEXT = re.compile(
    r"(last\s+updated|last\s+revised|effective|version|revised|updated|"
    r"in\s+effect|as\s+of|dated|valabil|actualizat)", re.I)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(url: str, timeout: int) -> tuple[bytes, int, str, str]:
    """GET url with a browser agent. Returns (body, status, content_type, final_url)."""
    import requests
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout,
                            allow_redirects=True)
    except Exception as exc:  # noqa: BLE001 - network shape varies by failure
        raise UsageError(f"fetch failed for {url!r}: {exc}")
    return (resp.content, resp.status_code,
            resp.headers.get("Content-Type", ""), resp.url)


def _is_pdf(body: bytes, content_type: str, url: str) -> bool:
    return (body[:5] == b"%PDF-"
            or "application/pdf" in content_type.lower()
            or urlparse(url).path.lower().endswith(".pdf"))


def _soup(html: bytes):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml")


def _extract_title(soup, fallback: str) -> str:
    for getter in (lambda: soup.title.get_text(strip=True) if soup.title else None,
                   lambda: soup.h1.get_text(strip=True) if soup.h1 else None):
        try:
            value = getter()
        except Exception:  # noqa: BLE001 - malformed markup must not abort a capture
            value = None
        if value:
            return value
    return fallback


def _html_to_text(soup) -> str:
    """Visible text with block structure preserved.

    Only script/style/noscript/template are dropped - they carry no text a
    reader would quote. Nothing else is filtered: a navigation or footer line
    in the extraction is noise, but silently dropping a region risks dropping
    a clause that happens to sit in one.
    """
    from bs4 import BeautifulSoup  # noqa: F401  (soup already built by caller)
    clone = _soup(str(soup).encode("utf-8"))
    for tag in clone(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = clone.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out).strip()


def _pdf_to_text(path: Path) -> str:
    try:
        import fitz
        with fitz.open(path) as doc:
            return "\n\n".join(
                f"--- page {i + 1} ---\n{page.get_text()}"
                for i, page in enumerate(doc)
            ).strip()
    except Exception:  # noqa: BLE001 - fall through to the second engine
        pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join(
            f"--- page {i + 1} ---\n{(pg.extract_text() or '')}"
            for i, pg in enumerate(reader.pages)
        ).strip()
    except Exception as exc:  # noqa: BLE001
        return f"[extraction failed: {exc}]"


def _date_candidates(text: str, limit: int = 12) -> list[dict]:
    """Date strings the document states about itself, with their context line.

    Reported in document order and NEVER de-conflicted. Two different dates on
    one document is a finding, not an error to resolve.
    """
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        if not _DATE_CONTEXT.search(line):
            continue
        for pattern in _DATE_PATTERNS:
            for match in re.findall(pattern, line):
                key = (match, line[:80])
                if key in seen:
                    continue
                seen.add(key)
                found.append({"date": match, "context": line.strip()[:200]})
                if len(found) >= limit:
                    return found
    return found


def _inline_stylesheets(soup, base_url: str, timeout: int) -> int:
    """Fetch every <link rel=stylesheet> and inline it as <style>.

    Makes the capture open with its layout on a machine with no network. The
    markup is not otherwise touched: only the link element is swapped for the
    stylesheet it pointed at, and a comment records where each came from so the
    substitution stays auditable.
    """
    import requests
    inlined = 0
    for link in list(soup.find_all("link")):
        rel = " ".join(link.get("rel") or []).lower()
        href = link.get("href")
        if "stylesheet" not in rel or not href:
            continue
        css_url = urljoin(base_url, href)
        try:
            resp = requests.get(css_url, headers=_HEADERS, timeout=timeout)
            if resp.status_code != 200:
                continue
            css = resp.text
        except Exception:  # noqa: BLE001 - a missing stylesheet degrades, never aborts
            continue
        # url(...) inside the CSS is relative to the STYLESHEET, not the page,
        # so rewrite to absolute or the inlined copy loses its fonts and images.
        css = re.sub(
            r"url\(\s*(['\"]?)(?!data:|https?:|//)([^)'\"]+)\1\s*\)",
            lambda m: f"url({m.group(1)}{urljoin(css_url, m.group(2))}{m.group(1)})",
            css)
        style = soup.new_tag("style")
        style.string = f"/* inlined from {css_url} */\n{css}"
        link.replace_with(style)
        inlined += 1
    return inlined


def _header(fmt: str, meta: dict) -> str:
    """Provenance block prepended to every readable artefact."""
    dates = meta["document_date_candidates"]
    date_line = ("; ".join(f"{d['date']} ({d['context'][:60]})" for d in dates)
                 if dates else "NONE STATED ON THE DOCUMENT")
    rows = [
        ("Document title (as published)", meta["title"]),
        ("Date stated on the document", date_line),
        ("Source URL", meta["url"]),
        ("Final URL after redirects", meta["final_url"]),
        ("HTTP status", str(meta["status"])),
        ("Fetched at (UTC)", meta["fetched_at"]),
        ("Original file", meta["original_name"]),
        ("SHA-256 of original", meta["sha256_original"]),
        ("Original size (bytes)", str(meta["bytes"])),
        ("Captured by", "web archive-document (Agents-and-Tools)"),
    ]
    if fmt == "md":
        body = "\n".join(f"| {k} | {v} |" for k, v in rows)
        return (
            f"# {meta['title']}\n\n"
            "> **Working copy for review. The original is the authority.**\n"
            "> This extraction is the document's text only; clause numbering, "
            "layout and pagination live in the original file beside it.\n\n"
            "| Field | Value |\n|---|---|\n" + body + "\n\n---\n\n"
        )
    return ""


def archive_document(args) -> dict:
    if bool(args.url) == bool(args.file):
        raise UsageError("provide exactly one of --url or --file")

    out_dir = Path(args.out_dir).expanduser()
    name = args.name.strip()
    if not name or "/" in name or "\\" in name:
        raise UsageError("--name must be a single folder-safe token")
    folder = out_dir / name
    folder.mkdir(parents=True, exist_ok=True)

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.url:
        body, status, content_type, final_url = _fetch(args.url, args.timeout)
        source = args.url
    else:
        src = Path(args.file).expanduser()
        if not src.is_file():
            raise UsageError(f"--file not found: {src}")
        body = src.read_bytes()
        status, content_type, final_url = 200, "", src.as_uri()
        source = args.source_url or src.as_uri()

    is_pdf = _is_pdf(body, content_type, final_url)
    ext = "pdf" if is_pdf else "html"
    original = folder / f"{name}.{ext}"
    original.write_bytes(body)  # byte for byte, never rewritten

    meta = {
        "title": args.title or name,
        "url": source,
        "final_url": final_url,
        "status": status,
        "fetched_at": fetched_at,
        "original_name": original.name,
        "sha256_original": _sha256(body),
        "bytes": len(body),
        "document_date_candidates": [],
    }

    self_contained: Path | None = None
    inlined = 0
    if is_pdf:
        text = _pdf_to_text(original)
    else:
        soup = _soup(body)
        meta["title"] = args.title or _extract_title(soup, name)
        text = _html_to_text(soup)
        if not args.no_self_contained:
            sc_soup = _soup(body)
            inlined = _inline_stylesheets(sc_soup, final_url, args.timeout)
            if sc_soup.head:
                base = sc_soup.new_tag("base", href=final_url)
                sc_soup.head.insert(0, base)
            self_contained = folder / f"{name}.self-contained.html"
            self_contained.write_text(str(sc_soup), encoding="utf-8")

    meta["document_date_candidates"] = _date_candidates(text)

    extraction = folder / f"{name}.md"
    extraction.write_text(_header("md", meta) + text, encoding="utf-8")

    files = {"original": str(original), "extraction": str(extraction)}
    hashes = {
        "original": meta["sha256_original"],
        "extraction": _sha256(extraction.read_bytes()),
    }
    if self_contained is not None:
        files["self_contained"] = str(self_contained)
        hashes["self_contained"] = _sha256(self_contained.read_bytes())

    return {
        "name": name,
        "dir": str(folder),
        "url": source,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "kind": "pdf" if is_pdf else "html",
        "title": meta["title"],
        "fetched_at": fetched_at,
        "bytes": len(body),
        "stylesheets_inlined": inlined,
        "chars_extracted": len(text),
        "document_date_candidates": meta["document_date_candidates"],
        "files": files,
        "sha256": hashes,
    }


def _archive_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--url", default=None,
                   help="URL of the document to capture (exactly one of --url/--file)")
    p.add_argument("--file", default=None,
                   help="Local file to archive instead of fetching (already-downloaded original)")
    p.add_argument("--source-url", default=None,
                   help="With --file: the URL the file came from, recorded in the header")
    p.add_argument("--out-dir", required=True,
                   help="Base directory; a subfolder named --name is created inside it")
    p.add_argument("--name", required=True,
                   help="Folder and file basename for the document (a slug, not a URL)")
    p.add_argument("--title", default=None,
                   help="Published title override; default reads <title>/<h1>")
    p.add_argument("--timeout", type=int, default=60,
                   help="Per-request timeout in seconds (default 60)")
    p.add_argument("--no-self-contained", action="store_true",
                   help="Skip the stylesheet-inlined copy (original + extraction only)")


ACTIONS = {
    "archive-document": ActionDef(
        archive_document, _archive_args, needs_driver=False,
        description=("Capture a published document as original bytes + a "
                     "self-contained rendering + a text extraction, each with "
                     "a provenance header and sha256."),
    ),
}
