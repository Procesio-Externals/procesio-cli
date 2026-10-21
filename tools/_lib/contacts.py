"""Pull published contact details out of free text or an HTML page.

Shared by the tools that read what a person publishes about themselves (a YouTube
channel description, a video description, a link-in-bio page, a personal site):
the email they list for business inquiries, their profiles on other platforms, and
any affiliate-shaped links (which say "this person already earns commission").

Pure functions, no I/O. Callers attach their own ``source`` to what comes back.

What is deliberately NOT done here: guessing addresses (first.last@domain),
resolving shortened links, or following redirects. Only what is literally on the
page counts, so every contact can be traced back to where it was published.
"""
from __future__ import annotations

import html as _html
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit

# --- emails -------------------------------------------------------------------

EMAIL_RE = re.compile(
    r"(?<![\w.+%-])([A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24})(?![\w-])"
)

# "name [at] domain [dot] com", "name (at) domain (dot) com", "name{at}domain{dot}com".
# A bare "name at domain dot com" is NOT matched: it is too common in normal prose.
_AT = r"\s*[\[\(\{<]\s*at\s*[\]\)\}>]\s*"
_DOT = r"\s*(?:[\[\(\{<]\s*dot\s*[\]\)\}>]|\.)\s*"
OBFUSCATED_EMAIL_RE = re.compile(
    rf"([A-Za-z0-9][A-Za-z0-9._%+-]*){_AT}([A-Za-z0-9-]+(?:{_DOT}[A-Za-z0-9-]+)+)",
    re.IGNORECASE,
)
_DOT_TOKEN_RE = re.compile(_DOT, re.IGNORECASE)

# File extensions that look like a TLD in retina asset names (an "@2x" suffix before ".png").
_NOT_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "ico", "mp4", "pdf"}
# Placeholder / infrastructure domains that are never a person's inbox.
_JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "email.example", "sentry.io", "wixpress.com", "sentry-next.wixpress.com",
}


def _clean_email(raw: str) -> str | None:
    email = raw.strip().strip(".").lower()
    if email.count("@") != 1:
        return None
    local, domain = email.split("@")
    if not local or not domain or ".." in email:
        return None
    if domain.rsplit(".", 1)[-1] in _NOT_TLDS:
        return None
    if domain in _JUNK_EMAIL_DOMAINS or domain.endswith(".example"):
        return None
    return email


def find_emails(text: str) -> list[str]:
    """Every distinct email in ``text``, in order of appearance (lowercased)."""
    found: list[str] = []
    for m in EMAIL_RE.finditer(text or ""):
        e = _clean_email(m.group(1))
        if e and e not in found:
            found.append(e)
    for m in OBFUSCATED_EMAIL_RE.finditer(text or ""):
        domain = _DOT_TOKEN_RE.sub(".", m.group(2))
        e = _clean_email(f"{m.group(1)}@{domain}")
        if e and "." in domain and e not in found:
            found.append(e)
    return found


# --- links --------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s<>\"'`\]\[|]+", re.IGNORECASE)
# Profile links people often write without a scheme.
BARE_PROFILE_RE = re.compile(
    r"(?<![\w./-])((?:www\.)?(?:linkedin\.com/(?:in|company)/|x\.com/|twitter\.com/)[\w%./-]+)",
    re.IGNORECASE,
)
_TRAILING = ".,;:!?)]}'\"*"

LINK_IN_BIO_HOSTS = {
    "linktr.ee", "beacons.ai", "stan.store", "bio.link", "lnk.bio", "linkin.bio",
    "taplink.cc", "campsite.bio", "solo.to", "hoo.be", "msha.ke", "linkpop.com",
    "koji.to", "withkoji.com", "bento.me", "allmylinks.com", "linkr.bio", "contactin.bio",
}
_PLATFORM_HOSTS = {
    "linkedin": ("linkedin.com", "lnkd.in"),
    "x": ("x.com", "twitter.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "facebook": ("facebook.com", "fb.com", "fb.me"),
    "github": ("github.com",),
    "booking": ("calendly.com", "cal.com", "tidycal.com", "savvycal.com", "zcal.co"),
    "newsletter": ("substack.com", "beehiiv.com", "convertkit.com", "kit.com"),
}
# Shorteners and stores: a link, but neither the person's site nor a profile.
_OTHER_HOSTS = (
    "bit.ly", "tinyurl.com", "geni.us", "amzn.to", "amazon.com", "t.co", "goo.gl",
    "ow.ly", "rebrand.ly", "shorturl.at", "buff.ly", "discord.gg", "discord.com",
    "patreon.com", "buymeacoffee.com", "ko-fi.com", "gumroad.com", "udemy.com",
    "apple.com", "spotify.com", "google.com", "goo.gl", "forms.gle",
)
LINK_KINDS = ("linkedin", "x", "youtube", "instagram", "tiktok", "facebook", "github",
              "booking", "newsletter", "link_in_bio", "website", "other")


def _host(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def normalize_url(raw: str) -> str:
    url = raw.strip().rstrip(_TRAILING)
    if not re.match(r"https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


# Static files: never a profile, a site or a contact route.
_ASSET_RE = re.compile(
    r"\.(?:js|mjs|css|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|json|webmanifest|map|mp4|webm)$",
    re.IGNORECASE)


def is_asset(url: str) -> bool:
    try:
        return bool(_ASSET_RE.search(urlsplit(url).path))
    except ValueError:
        return False


def find_urls(text: str) -> list[str]:
    """Distinct http(s) URLs plus scheme-less LinkedIn / X profile links.
    Static assets (scripts, styles, images, fonts) are skipped."""
    text = (text or "").replace("\\/", "/")
    out: list[str] = []
    for m in URL_RE.finditer(text):
        u = normalize_url(m.group(0))
        if _host(u) and not is_asset(u) and u not in out:
            out.append(u)
    for m in BARE_PROFILE_RE.finditer(text):
        u = normalize_url(m.group(1))
        if u not in out:
            out.append(u)
    return out


def classify_url(url: str) -> str:
    """Which kind of link this is (one of LINK_KINDS)."""
    host = _host(url)
    if not host:
        return "other"
    if _host_matches(host, LINK_IN_BIO_HOSTS) or host.endswith(".carrd.co"):
        return "link_in_bio"
    for kind, domains in _PLATFORM_HOSTS.items():
        if _host_matches(host, domains):
            return kind
    if _host_matches(host, _OTHER_HOSTS):
        return "other"
    return "website"


# --- affiliate-shaped links ---------------------------------------------------

# Query parameters affiliate / referral programs put on a link, and the network
# that uses each (None = generic referral parameter used by many programs).
AFFILIATE_PARAMS = {
    "via": "rewardful",
    "fpr": "firstpromoter",
    "fp_ref": "firstpromoter",
    "tap_a": "tapfiliate",
    "irclickid": "impact",
    "aff": None, "affiliate": None, "aff_id": None, "affid": None, "affiliate_id": None,
    "ref": None, "referral": None, "referral_code": None, "ref_id": None,
    "pc": None, "partner": None, "partner_id": None, "promo": None,
    "tag": "amazon",
}
# Hosts that only exist to track affiliate clicks.
AFFILIATE_HOSTS = {
    "partnerlinks.io": "partnerstack",
    "sjv.io": "impact",
    "pxf.io": "impact",
    "ojrq.net": "impact",
    "7eer.net": "impact",
    "shareasale.com": "shareasale",
    "awin1.com": "awin",
    "dpbolvw.net": "cj",
    "anrdoezrs.net": "cj",
    "kqzyfj.com": "cj",
    "tkqlhce.com": "cj",
    "jdoqocy.com": "cj",
}


def _program_from_host(host: str) -> str:
    labels = [x for x in host.split(".") if x]
    if len(labels) >= 2:
        return labels[-2]
    return host


def affiliate_info(url: str) -> dict | None:
    """Describe ``url`` as an affiliate link, or None when it does not look like one.

    ``program`` is the product the link promotes: the subdomain on a tracking host
    (``acme.partnerlinks.io`` -> ``acme``), else the site's own name
    (``www.acme.com/?via=x`` -> ``acme``).
    """
    host = _host(url)
    if not host:
        return None
    for tracker, network in AFFILIATE_HOSTS.items():
        if host == tracker or host.endswith("." + tracker):
            sub = host[: -len(tracker)].rstrip(".")
            program = sub.split(".")[-1] if sub else tracker
            return {"url": url, "host": host, "network": network, "program": program, "param": None}
    try:
        params = parse_qsl(urlsplit(url).query, keep_blank_values=False)
    except ValueError:
        params = []
    for key, value in params:
        k = key.lower()
        if k in AFFILIATE_PARAMS and value.strip():
            network = AFFILIATE_PARAMS[k]
            if k == "tag" and "amazon." not in host:
                continue
            return {"url": url, "host": host, "network": network,
                    "program": _program_from_host(host), "param": k}
    return None


# --- one-shot extraction ------------------------------------------------------

def empty_result() -> dict:
    return {"emails": [], "links": {k: [] for k in LINK_KINDS}, "affiliate_links": []}


def extract(text: str) -> dict:
    """Emails, links grouped by kind, and affiliate-shaped links found in ``text``."""
    out = empty_result()
    out["emails"] = find_emails(text)
    for url in find_urls(text):
        kind = classify_url(url)
        aff = affiliate_info(url)
        if aff:
            out["affiliate_links"].append(aff)
            # An affiliate link points at someone else's product, not the
            # person's own site: never let it pose as their website.
            if kind == "website":
                kind = "other"
        out["links"][kind].append(url)
    return out


def merge(*results: dict) -> dict:
    """Union of several ``extract`` results, order-preserving and de-duplicated."""
    out = empty_result()
    for r in results:
        for e in r.get("emails", []):
            if e not in out["emails"]:
                out["emails"].append(e)
        for kind, urls in (r.get("links") or {}).items():
            bucket = out["links"].setdefault(kind, [])
            for u in urls:
                if u not in bucket:
                    bucket.append(u)
        seen = {a["url"] for a in out["affiliate_links"]}
        for a in r.get("affiliate_links", []):
            if a["url"] not in seen:
                out["affiliate_links"].append(a)
                seen.add(a["url"])
    return out


# --- HTML pages ---------------------------------------------------------------

class _PageParser(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.text: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.hrefs.append(value.strip())

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.text.append(data)


# Kinds safe to take from anywhere in a page's source: a profile URL is a profile
# whether it sits in an anchor or in a JSON blob. Plain sites, link-in-bio pages and
# affiliate links are NOT taken from raw source: link-in-bio services embed their
# own assets and sponsored offers there, and those are not the creator's.
_RAW_SAFE_KINDS = ("linkedin", "x", "youtube", "instagram", "tiktok", "facebook",
                   "github", "booking", "newsletter")

_NEXT_DATA_RE = re.compile(
    r"""<script[^>]*id=["']__NEXT_DATA__["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL)


def _site(host: str) -> str:
    labels = [x for x in (host or "").split(".") if x]
    return ".".join(labels[-2:])


def next_data_links(page: str) -> tuple[list[str], list[str]]:
    """Links a creator chose, from a Next.js page's ``__NEXT_DATA__`` JSON.

    Link-in-bio services built on Next.js (Linktree among them) render no anchors
    server-side: the creator's buttons live in ``props.pageProps.links[].url``, the
    social icons in ``socialLinks[].url`` (``pinnedLinks`` too) and the bio in
    ``pageProps.description``. Returns ``(urls, texts)``, empty when the page has no
    such blob. Sponsored offers the platform injects sit elsewhere in the same JSON
    and are deliberately not read.
    """
    m = _NEXT_DATA_RE.search(page or "")
    if not m:
        return [], []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return [], []
    props = data.get("props") if isinstance(data, dict) else None
    pp = props.get("pageProps") if isinstance(props, dict) else None
    if not isinstance(pp, dict):
        return [], []
    urls: list[str] = []
    for k in ("links", "socialLinks", "pinnedLinks"):
        items = pp.get(k)
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                urls.append(item["url"].strip())
    texts = [pp["description"]] if isinstance(pp.get("description"), str) else []
    return urls, texts


def _split_hrefs(hrefs: list[str], base_url: str) -> tuple[list[str], list[str]]:
    """(emails from mailto: links, absolute http(s) URLs)."""
    mailto: list[str] = []
    urls: list[str] = []
    for h in hrefs:
        h = _html.unescape(h).strip()
        low = h.lower()
        if low.startswith("mailto:"):
            mailto.extend(find_emails(h[7:].split("?", 1)[0]))
        elif low.startswith(("http://", "https://")):
            urls.append(h)
        elif h.startswith("/") and base_url:
            urls.append(urljoin(base_url, h))
    return mailto, urls


def extract_html(page: str, base_url: str = "") -> dict:
    """Contacts on an HTML page, from three places:

    1. ``mailto:`` links, anchor hrefs and visible text (what a visitor sees);
    2. the links a creator chose on a Next.js link-in-bio page (``next_data_links``);
    3. profile URLs (LinkedIn, X, Instagram, ...) anywhere in the raw source.

    Links back to the page's own site are dropped from the link-in-bio / website /
    other buckets: on a link-in-bio page they are navigation and assets, not the
    creator's destinations.
    """
    parser = _PageParser()
    try:
        parser.feed(page or "")
        parser.close()
    except Exception:  # noqa: BLE001 - a malformed page still yields what was parsed
        pass

    mailto, hrefs = _split_hrefs(parser.hrefs, base_url)
    visible = " ".join(t.strip() for t in parser.text if t.strip())
    shown = merge({"emails": mailto, "links": {}, "affiliate_links": []},
                  extract(visible + "\n" + "\n".join(hrefs)))

    nd_urls, nd_texts = next_data_links(page)
    nd_mailto, nd_hrefs = _split_hrefs(nd_urls, base_url)
    chosen = merge({"emails": nd_mailto, "links": {}, "affiliate_links": []},
                   extract("\n".join(nd_texts + nd_hrefs)))

    raw_all = extract(_html.unescape(page or ""))
    raw = {"emails": [], "affiliate_links": [],
           "links": {k: (v if k in _RAW_SAFE_KINDS else []) for k, v in raw_all["links"].items()}}

    result = merge(shown, chosen, raw)
    site = _site(_host(base_url)) if base_url else ""
    if site:
        for kind in ("link_in_bio", "website", "other"):
            result["links"][kind] = [u for u in result["links"].get(kind, [])
                                     if _site(_host(u)) != site]
    result["title"] = " ".join(parser.title.split())
    return result


def collect(sources: list[tuple[str, str]]) -> dict:
    """Extract from several labelled texts, keeping where each find came from.

    ``sources`` is ``[(source_label, text), ...]`` (e.g. ``("video:abc", desc)``).
    Returns emails as ``[{"email", "sources": [...]}]``, links grouped by kind, and
    affiliate links each carrying the ``source`` it was first seen in.
    """
    emails: dict[str, list[str]] = {}
    merged = empty_result()
    affiliates: list[dict] = []
    seen: set[str] = set()
    for source, text in sources:
        r = extract(text or "")
        for e in r["emails"]:
            emails.setdefault(e, [])
            if source not in emails[e]:
                emails[e].append(source)
        merged = merge(merged, {"emails": [], "links": r["links"], "affiliate_links": []})
        for a in r["affiliate_links"]:
            if a["url"] not in seen:
                affiliates.append({**a, "source": source})
                seen.add(a["url"])
    return {
        "emails": [{"email": e, "sources": s} for e, s in emails.items()],
        "links": merged["links"],
        "affiliate_links": affiliates,
        "sources_scanned": len(sources),
    }
