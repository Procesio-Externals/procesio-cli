"""page-contacts - the contact details a public page publishes, without a browser.

For link-in-bio pages (Linktree, Beacons, Stan, ...) and personal sites: one plain
HTTP GET with a browser User-Agent, then the shared extractor
(tools._lib.contacts) over mailto links, anchors, visible text and the profile
links that link-in-bio services embed as JSON. No session, no login, nothing is
clicked or submitted, and no address is guessed - only what the page shows.

A page that answers 4xx/5xx is a normal outcome when scanning many creators, so it
comes back as ``reachable: false`` rather than an error. A network failure (DNS,
timeout, TLS) is an error.
"""
from __future__ import annotations

import argparse

from tools._lib import contacts as extractor
from tools.web.actiondef import ActionDef
from tools.web.errors import UsageError
from tools.web.handlers.archive import _HEADERS

MAX_BYTES = 2_000_000


def _fetch(url: str, timeout: int) -> tuple[str, int, str, str]:
    """GET url. Returns (text, status, content_type, final_url)."""
    import requests
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    except Exception as exc:  # noqa: BLE001 - network shape varies by failure
        raise UsageError(f"fetch failed for {url!r}: {exc}")
    body = resp.content[:MAX_BYTES]
    encoding = resp.encoding or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return text, resp.status_code, resp.headers.get("Content-Type", ""), resp.url


def page_contacts(args) -> dict:
    url = (args.url or "").strip()
    if not url:
        raise UsageError("--url is required")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    text, status, content_type, final_url = _fetch(url, args.timeout)
    out = {"url": url, "final_url": final_url, "status": status,
           "content_type": content_type, "reachable": 200 <= status < 400}
    if not out["reachable"]:
        out.update(extractor.empty_result())
        out["title"] = ""
        return out
    ctype = content_type.lower()
    if "html" in ctype or "<html" in text[:2000].lower():
        out.update(extractor.extract_html(text, base_url=final_url))
    else:
        out.update(extractor.extract(text))
        out["title"] = ""
    return out


def _args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--url", required=True, help="Public page to read (link-in-bio, personal site)")
    p.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds (default 20)")


ACTIONS = {
    "page-contacts": ActionDef(
        page_contacts, _args, needs_driver=False,
        description=("Emails, profile links and affiliate links a public page "
                     "publishes (one plain GET; no browser, no session)."),
    ),
}
