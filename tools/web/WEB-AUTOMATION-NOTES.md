# WEB — automation notes

Durable learnings for the `web` tool and everything built on it
(`whatsapp-personal`, `fgo-web`, `mirro` web actions). Hard rule 6.

## Headless stealth (why WhatsApp Web works headless)

Default headless Chromium advertises a `HeadlessChrome` User-Agent and
`navigator.webdriver = true`. WhatsApp Web's browser-support gate rejects this:
it renders "WhatsApp works with Google Chrome 85+ / update Chrome" and never
loads the app, so `whatsapp-personal send-message` used to time out waiting for
the composer (`#main footer div[contenteditable='true']...`).

`PlaywrightDriver.start()` now calls `_apply_stealth()` on **every** launch
(`driver.py`):

- adds `--disable-blink-features=AutomationControlled` to the launch args;
- shadows `navigator.webdriver` via an init script;
- if the live UA contains "Headless", rewrites it to plain "Chrome" through CDP
  `Network.setUserAgentOverride` (read from `navigator.userAgent`, so it tracks
  the installed Chromium version — nothing hard-coded).

This is best-effort and fully guarded (a stealth failure never breaks a launch),
and harmless when already headed (no "Headless" in the UA → UA override skipped).
Confirmed: headless `send-message` + `read-messages` against the saved
`whatsapp` persistent profile now succeed from a headless run, no visible window.

## Playwright browser install

- `python -m playwright install chromium` can print nothing and **not** actually
  download (leaving a partial `chrome.exe` that exists on disk but Playwright
  rejects as "Executable doesn't exist"). Use `--force` and watch for the
  ~182 MB download log.
- Headed launches (`save-session` for QR login) need the FULL build
  `chromium-<rev>/chrome-win64/chrome.exe`; headless can use
  `chromium_headless_shell-<rev>`.
- Always invoke via the venv: `.\.venv\Scripts\python.exe -m playwright install chromium`.

## WhatsApp session capture

`web save-session --name whatsapp --url https://web.whatsapp.com --persistent`
opens a HEADED window for the QR scan and stores a **persistent profile** at
`tools/web/sessions/whatsapp.profile` (IndexedDB-backed auth — a storageState
snapshot is not enough). The login persists across runs; the headless stealth
above is what lets later automated sends reuse it.

## `save-session` CANNOT be driven from an agent tool call (stdin EOF)

`save_session` blocks on `_block_on_enter()` -> `sys.stdin.readline()`. Inside a
Claude Code Bash/PowerShell tool call, stdin reports `isatty() == True` but
`readline()` returns `''` (immediate EOF). The wait therefore returns in
milliseconds, the headed browser is closed ~2s after launch, and a
HALF-AUTHENTICATED profile is written to disk.

Symptom (observed 2026-07-18, google session): three consecutive
`save-session --persistent --channel chrome` runs each returned
`cookies_saved: 54` — an identical, deterministic count, because 54 is simply
what Google sets on the pre-auth sign-in page. Every later
`web get-text --session google` then hit "Verify it's you". The profile dir
mtime updated each run, so the save *looked* successful.

**Rule:** an interactive `save-session` MUST be run by the human in their own
terminal. An agent can prepare/verify around it, but must not attempt to run it
and must not read `cookies_saved` as proof of a completed login.

**Verify a Google session correctly:** use a real target surface
(`https://drive.google.com/drive/my-drive`) and pass the SAME
`--channel chrome` the profile was saved with — bundled Chromium against a
real-Chrome profile is a fingerprint mismatch that triggers its own challenge.
`myaccount.google.com` always re-challenges and is a false negative.

### Fix (2026-07-18): `--wait-seconds` makes save-session agent-drivable

`save-session` now takes `--wait-seconds N` (+ optional
`--wait-until-url-excludes <host>`), which holds the headed browser open for up
to N seconds instead of touching stdin. An agent CAN now run the flow; the human
just logs in and it saves itself. Without `--wait-seconds` the legacy ENTER wait
still applies and is still unusable from a tool call.

Proven live restoring the `google` session after a password reset.

**`login_detected` is ADVISORY, not proof.** The URL poller returned
`login_detected: false` on the very run that produced a fully working session
(it reads one page's address bar; a login that completes in another tab, or
late, reads as a timeout). It is safe in the useful direction — a false negative
only costs waiting the full timeout. **The authoritative check is always a
post-save probe of the real target surface**, with the same `--channel` the
profile was saved with:

    web get-text --session google --channel chrome --url https://drive.google.com/drive/my-drive

**FIXED (2026-07-18):** `delete-session` used to only unlink the storageState
`<name>.json`, leaving `<name>.profile/` and `<name>.cookies.json` behind and
returning `{"deleted": false}` for a persistent session - a stale, possibly
half-authenticated profile that `open_session` then silently reused (it
auto-detects `<name>.profile`).

It now removes all THREE artifacts and reports them:
`{"deleted": true, "removed": ["state","profile","cookies"]}`.

**It previews by default.** Deleting a session destroys a login only a human at
a browser can re-establish, so nothing is removed without `--confirm`; the
unconfirmed call returns `would_remove` + `confirmation_required` and is the dry
run. An artifact that cannot be removed (Windows lock: a browser or serializing
broker still holds the profile) is reported under `failed` and does NOT count as
`deleted: true`. A preview never stops the owning broker - only a confirmed
delete does.


## Agent fills the form, human submits it (`run --hold-seconds`)

The agent stages the work, the human clicks the irreversible control. This is
what the permission rules require for anything outward-facing (Submit, Confirm,
Send), and `run` supports it directly:

    web run --session <s> --headed --hold-seconds 900 \
            --hold-until-selector "text=Thank" --actions-file steps.json

After the last step the headed browser stays open up to `--hold-seconds`, so the
human can review what was filled and act. `--hold-until-selector` (or
`--hold-until-url-excludes <host>`) ends the hold the moment they do. The result
gains:

    "hold": {"held_seconds": 412.0, "completed": true, "reason": "selector"}

`reason` is `selector` | `url` | `timeout`.

**An expired hold is SUCCESS, not failure.** The steps ran; the human is allowed
to walk away. A timeout returns exit 0 with `completed: false`, so the caller can
still tell "the fill broke" from "nobody was at the desk". `--hold-seconds`
without `--headed` is a usage error (exit 2) - holding a headless browser open
helps nobody.

**`completed` is ADVISORY, not proof** - same caveat as `save-session`'s
`login_detected`. **Confirm from `final_url`, not from a screenshot.** A
screenshot proves only that the fields were populated: it is captured before the
human acts and looks identical whether or not anything was submitted. The
evidence is `final_url` landing on the site's submit/post-submit host. Check
`diagnostics` too - empty `page_errors` / `bad_responses` means the page was
actually healthy, which a screenshot also cannot show.

Before `--hold-seconds` existed the workaround was a long trailing
`wait_for` step. It worked, but a human who did not act in time made the whole
run raise `browser_error` - a successful fill reported as a failure. Don't
reintroduce it.

## Discover selectors from the HTML, before starting a browser

Fetch the page server-side (`urllib`/`requests`) and scan the
`<input|textarea|select>` tags: one call yields every `id` and `name` on the
form. Cheaper and far more reliable than round-tripping a live page for
structure, and it surfaces fields the rendered view hides - which is exactly
where the next two traps live.

## Form traps that cost a run

**Hidden sub-inputs behind a "lite mode" field.** Date widgets commonly render
`day_<qid>` / `month_<qid>` / `year_<qid>` inside a `<div style="display:none">`
and expose ONE visible text input, `lite_mode_<qid>`. Filling the sub-inputs
times out - Playwright will not type into a hidden element. Fill the lite-mode
input, using the format the element itself declares
(`data-format="ddmmyyyy"` + `data-seperator="-"` -> `01-04-2026`), then
`press Tab` on it so the widget propagates the value into the hidden fields.
Generally: when a fill times out on a field that plainly exists in the HTML,
check whether an ancestor is `display:none` and look for the visible proxy.

**Honeypot fields.** A form may carry an input with a plausible name and NO
`id` (seen: `name="website"`). It is an anti-spam trap - a filled value marks
the submission as a bot. Always fill by explicit id; never iterate "every input
on the page".

**A DNS failure inside the browser can be transient.** `net::ERR_NAME_NOT_RESOLVED`
on `goto` while the same URL fetches fine from Python is not proof of a blocked
host or a broken session. Retry once before diagnosing.

## Archiving a published document as evidence (`archive-document`)

Added 16/09/2026. Captures a web page or PDF as three artefacts in one folder: the response bytes
untouched, a stylesheet-inlined copy that renders offline, and a text extraction. Every readable file
carries a provenance header with the sha256 of the original, so a later capture of the same URL can be
diffed against it to prove whether the publisher edited the document.

**Fetch is plain HTTP with a browser User-Agent, no Playwright.** A CDN edge will serve a challenge
page to a default urllib/requests agent and the document itself to a browser agent, so the agent
string is load-bearing, not cosmetic. Server-rendered pages (Next.js and similar) come back complete;
verify by grepping the extraction for a string only the rendered page would carry before trusting it.
A client-rendered page needs `web run` / `get-text` with a session instead.

**Why three files and not a markdown conversion.** Clause numbering, layout and pagination are part of
what a reader of a legal or contractual document relies on, and a markdown conversion destroys all
three. The original is kept byte for byte and is the only artefact treated as evidence; the other two
are derived conveniences.

**Date candidates are reported, never reconciled.** The extractor reports date-like strings that sit
near version wording ("last updated", "effective", "revised"). Two of them on one document is a finding
about the document. Expect false positives where a document quotes a date for another reason: a policy
citing a court judgment will surface the judgment's date as a candidate, so read the context line
before treating a candidate as the document's own date.

**A bucket that returns 403 for an unknown key cannot be used to prove absence.** Object stores
configured to deny listing commonly answer 403 rather than 404 for a key that does not exist, which
makes "absent" and "present but private" indistinguishable from outside. Probing for sibling filenames
is therefore evidence of nothing in either direction; enumerate from the pages that link the objects
instead, and say so when reporting coverage.

**A published estate can be split across surfaces that do not link to each other.** The documents an
application presents at sign-up and sign-in can live on a different host from the ones a marketing site
links in its footer, with no path between them. Crawling the website alone will miss the operative
contract. Read the sign-up and sign-in screens as first-class sources, and record whether acceptance is
a ticked box or acceptance by conduct, because the absence of a checkbox is itself a finding.
