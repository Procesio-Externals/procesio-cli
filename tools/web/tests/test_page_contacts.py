"""page-contacts: one plain GET -> published emails, profile and affiliate links."""
from __future__ import annotations

import pytest

from tools.web import main as web_main
from tools.web.errors import UsageError
from tools.web.handlers import contacts as page

LINKTREE = """<!DOCTYPE html><html><head><title>@jane | Linktree</title></head><body>
<a href="https://www.linkedin.com/in/jane-doe">LinkedIn</a>
<a href="https://acme.partnerlinks.io/jane">The tool I use</a>
<a href="mailto:jane@studio.io">Email</a>
<script id="__NEXT_DATA__">{"socials":[{"url":"https:\\/\\/x.com\\/janedoe"}]}</script>
</body></html>"""


def _fake(text="", status=200, ctype="text/html; charset=utf-8", final=None, calls=None):
    def fetch(url, timeout):
        if calls is not None:
            calls.append((url, timeout))
        return text, status, ctype, final or url
    return fetch


def test_registered_without_a_browser():
    assert web_main.ACTIONS["page-contacts"].needs_driver is False


def test_link_in_bio_page(monkeypatch):
    calls = []
    monkeypatch.setattr(page, "_fetch", _fake(LINKTREE, calls=calls))
    r = web_main.dispatch("page-contacts", ["--url", "linktr.ee/jane", "--timeout", "7"])
    assert calls == [("https://linktr.ee/jane", 7)]
    assert r["reachable"] is True
    assert r["title"] == "@jane | Linktree"
    assert r["emails"] == ["jane@studio.io"]
    assert r["links"]["linkedin"] == ["https://www.linkedin.com/in/jane-doe"]
    assert r["links"]["x"] == ["https://x.com/janedoe"]
    assert r["affiliate_links"][0]["network"] == "partnerstack"


def test_error_status_is_unreachable_not_an_error(monkeypatch):
    monkeypatch.setattr(page, "_fetch", _fake("gone", status=404))
    r = web_main.dispatch("page-contacts", ["--url", "https://jane.dev"])
    assert r["reachable"] is False
    assert r["status"] == 404
    assert r["emails"] == []


def test_plain_text_body(monkeypatch):
    monkeypatch.setattr(page, "_fetch", _fake("contact: biz@jane.dev", ctype="text/plain"))
    r = web_main.dispatch("page-contacts", ["--url", "https://jane.dev/contact.txt"])
    assert r["emails"] == ["biz@jane.dev"]


def test_redirect_target_used_as_base_and_own_site_links_dropped(monkeypatch):
    html = ('<html><body><a href="/about">About</a>'
            '<a href="https://partner.io/x">Partner</a></body></html>')
    monkeypatch.setattr(page, "_fetch", _fake(html, final="https://www.jane.dev/home"))
    r = web_main.dispatch("page-contacts", ["--url", "https://jane.dev"])
    assert r["final_url"] == "https://www.jane.dev/home"
    assert r["links"]["website"] == ["https://partner.io/x"]


def test_url_required():
    with pytest.raises(UsageError):
        web_main.dispatch("page-contacts", [])
