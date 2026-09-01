# PROCESIO API — live-validated auth & coverage notes

Recorded 2026-06-23 against the production Web API. No secrets in this file.

## Hosts & infrastructure

| Host | Resolves to | TLS | Role | Reachable from here |
|------|-------------|-----|------|---------------------|
| `webapi.procesio.app` | 86.105.154.113 (Kong) | valid `*.procesio.app` | **Web API** (v1.19 Swagger, 247 ops) | ✅ yes |
| `auth.procesio.app` | 86.105.154.113 (Kong) | **self-signed Kong default** (`CN=localhost,O=Kong`) | Proxy/Auth API (login) | ❌ Kong "no route" / cert fail |
| `procesio.app` | nginx | valid | the Vue SPA (`VUE_APP_*` build env) | SPA only, `/api` = 405 |
| `procesio.com` | Cloudflare | valid | Next.js marketing site | n/a |

All `*.procesio.app` names (auth, app, identity, login, sso, …) resolve to the
same Kong node; only `webapi` has a configured cert+route. So the documented
auth host `auth.procesio.app` currently serves Kong's default cert and 404s its
own `/api/Authentication` and `/swagger` from the public edge.

## Auth mode 1 — API key  ✅ WORKING

Three request headers on every Web-API call:

```
key:         <api key name>
value:       <api key value>
workspaceid: <workspace GUID>     # required for workspace-scoped keys
```

The Swagger security schemes define `key` (KeyName) and `value` (KeyValue); the
developer docs add `workspaceid`. Live results for the two showcase keys:

| Profile | key/value | workspaceid | `GET /api/Workspaces` |
|---------|-----------|-------------|------------------------|
| `personal` | valid | (none) | **200** — 146 workspaces |
| `ws-scoped` | valid | (none) | 401 Unauthorized |
| `ws-scoped` | valid | its own workspace GUID | **200** |
| `ws-scoped` | valid | a DIFFERENT workspace GUID | 401 |

**Conclusion:** a personal/master key authenticates without `workspaceid`; a
workspace-scoped key **requires** the exact workspace GUID. Such a profile must be stored WITH its `workspace_id` to authenticate at all. Find any workspace's GUID with `list-workspaces` (`id`).

### Endpoints exercised live with the `personal` key (all 200)
- `GET /api/Workspaces` → 146 workspaces
- `GET /api/Projects` → `{totalItemCount, pageNumber, pageItemCount, pageItems}`
- `GET /api/DataTypes` → same paginated envelope
- `GET /api/Actions` → `{actions, grouping, prototypes}`
- `GET /api/Credentials/types` → 33 connection types

`GET /api/ApiKey` returns 401 even for the personal key — that endpoint needs a
`workspaceid`-scoped context (use a workspace profile).

## Auth mode 2 — username / password  ✅ WORKING (cookie session)

Confirmed from a real login HAR (`procesio.app.har`) + live replay. The actual
flow is a **cookie session on the Web API**, NOT the OAuth/Bearer flow the docs
describe and NOT on `auth.procesio.app` (that host is obsolete — "auth moved to
webapi"):

```
POST https://webapi.procesio.app/api/authentication      # lowercase path
Content-Type: application/x-www-form-urlencoded
x-requested-by: playground-v1                            # REQUIRED (omitting it = 407)
body: username=<>&password=<>&client_id=procesio-ui      # form, no realm/grant_type/client_secret

200 -> {"message":"Authentication successful"}
Set-Cookie: __Host-procesio.access  (HttpOnly, Secure, Path=/)
Set-Cookie: __Host-procesio.refresh (HttpOnly, Secure, Path=/)
Response header: x-session-expires-at  (exposed via Access-Control-Expose-Headers)
```

Every subsequent Web-API call carries those two cookies plus
`x-requested-by: playground-v1` (browser uses `credentials: include`;
`Access-Control-Allow-Credentials: true`). Live-verified end to end:
`POST /api/authentication` → 200, then `GET /api/users/me` → 200 (real user
`facaf267-…`), `GET /api/workspaces` → 200.

The tool implements exactly this: `login` form-posts and caches the cookies in
Credential Manager (`token-<profile>`), `auth_headers` sends `Cookie` +
`x-requested-by`, and a 401 transparently re-logs-in. The `client_id` is
overridable per profile; the gateway id defaults to `playground-v1`
(`requested_by` profile field to override). No Bearer token, no `auth_base` is
involved any more for login.

> Earlier 407/401 dead-ends were because the documented flow (JSON body,
> realm/grant_type, `auth.procesio.app`) is obsolete: the gateway needs the
> form body **and** the `x-requested-by` header on **webapi**.

### Session caching (Windows Credential Manager blob limit)

Windows Credential Manager rejects a blob over **2560 bytes** — `CredWrite` fails
with `WinError 1783 "stub received bad data"`. The trap: keyring stores the value
as **UTF-16LE**, so the real ceiling is **1280 CHARACTERS**, not 2560. Measured by
binary search on this machine: 1280 chars writes, 1281 fails. Budget in
characters and halve the byte figure, or you will conclude a payload fits when it
does not — the two cookies are ~1700 chars, which "fits" 2560 bytes on paper and
is rejected in practice.

### The login 401 is GENERIC — it never tells you which half is wrong

A rejected form login answers:

```
401  "Authentication token is null!"
```

Verified by probing the endpoint with an account that does not exist: the body is
byte-identical to a real account with a wrong password. So the string proves only
that the gateway accepted the REQUEST shape (path, form body, `x-requested-by`)
and refused the CREDENTIALS. It does not distinguish, and must not be read as, a
missing/expired token despite what it says — nothing about a cached session is
involved on a login call.

Diagnose by elimination, in this order (cheapest first):
1. **Wrong environment.** A profile is bound to one environment; an account that
   lives on QA/DEV (or a client installation) simply does not exist on PROD and is
   rejected exactly like a bad password. Match the profile's environment to the
   host the user actually logs into in the browser.
2. **Typo at the hidden prompt.** getpass echoes nothing, and `Ctrl+V` does not
   paste in a Windows console — a truncated paste looks like a wrong password.
3. **SSO account.** An account that reaches the platform through an external IdP
   has no platform-side password to submit; the redirect-based SSO flow is not
   implemented here, so use an api-key profile instead.

Rule of thumb for any gateway that returns one opaque message for every auth
failure: probe it once with a knowingly invalid identity. If the response matches
what the user is getting, the message carries no information and the fault must be
located by varying one input at a time.

### Storing a credential needs the runner bypassed

`add-credential` deliberately prompts for the secret instead of taking it on the
command line (flags leak into shell history and process listings). But run-tool
routes tools through the persistent runner by default, so the tool runs in a
daemon worker with no TTY, `sys.stdin.isatty()` is False, and the prompt is
unreachable — even though the human IS at a console. Bypass it for that one call:

```powershell
$env:AAT_RUNNER_DIRECT = "1"
python scripts/run-tool.py procesio add-credential --name <profile> --type userpass --username <you> --make-default
Remove-Item Env:AAT_RUNNER_DIRECT
```

Generalizes to every framework action that prompts for a secret. See
`tools/_lib/toolrunner/TOOLRUNNER-NOTES.md` ("Limitations").

### The dashboard's secret list is not where a profile is added

A tool that keeps its OWN multi-profile store shows only its bookkeeping secrets
in the dashboard's generic per-tool secret list — here `credentials` (the
non-secret JSON index of profile names) and `form-code-key` (unrelated to login).
Neither is the credential a user is hunting for, and hand-writing the index
desyncs it from the real `cred-<name>` entries. Profiles are added through the
tool's own action only; the dashboard panel manages environments and
set-default/remove for profiles that already exist.

The two JWTs therefore cannot share one entry, and both must survive (the access
cookie authenticates; the refresh cookie is what renews the session without the
password). They get **one entry each** — `token-<name>` for the access cookie
plus its expiry, `refresh-<name>` for the refresh cookie. At ~961 and ~733 chars
each fits comfortably.

So the tool: (1) keeps an **in-process** cookie cache (always works, avoids
re-login within one CLI invocation), and (2) best-effort persists both entries
independently — a failed refresh write only costs the next process a full login,
it does not break the access cache. If a write fails it logs to stderr and
re-logs-in next invocation. Never let a token cache write crash a request.

### Renewing a session — refresh, don't re-login

The access cookie is a **~30-minute JWT**; the refresh cookie outlives it. A
browser never notices, because for cookie/BFF clients the gateway refreshes
behind a `307` redirect. A programmatic cookie client gets no such help and must
ask explicitly:

```
POST {web_base}/api/Authentication/refreshToken
Content-Type: application/x-www-form-urlencoded
x-requested-by: playground-v1
body: refresh_token=<value of __Host-procesio.refresh>&client_id=procesio-ui
```

→ `200 {"message":"Token refreshed successfully"}` plus a fresh **pair** of
Set-Cookie headers. Verified live: the refreshed access cookie authenticates an
ordinary Web-API call. This is why the refresh cookie must be cached — without
it the only way to renew is to re-send the account password every half hour.

Resolution order is therefore: in-process cache → persistent cache → **refresh**
→ full login. A refresh token that is dead by its own `exp` is skipped rather
than spending a round-trip proving it.

### Which status means "your session is stale"

Measured against the prod gateway with a bad access cookie:

| Cookie sent | Status |
| --- | --- |
| valid | `200` |
| present but rejected (bad/expired token) | **`403`** |
| present but unparseable | `401` |
| absent entirely | `401` |

The trap: a **rejected session comes back 403, not 401**. A client that
re-authenticates only on 401 surfaces a stale session as a permission error the
user cannot act on. Treat both as re-authable; make it one-shot so a genuine
permission denial still terminates. The cost of including 403 is one cheap
refresh round-trip when the denial was real.

### Bearer (token-in-body) is also available

Omitting `x-requested-by` on the login POST switches the gateway out of cookie/BFF
mode: the 200 body then carries `access_token` / `refresh_token` / `expires_in`
(1800) instead of setting cookies, and `Authorization: Bearer <access_token>`
authenticates Web-API calls normally (verified live). PROCESIO's own API
documentation recommends this style for integrations and reserves the cookie path
for the official SPA. This tool still uses the cookie flow — switching is a
migration to make deliberately, not a bug fix — but the option is real and
carries no extra dependency.

