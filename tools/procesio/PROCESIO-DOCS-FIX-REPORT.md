# PROCESIO API docs — corrections needed

Audience: the PROCESIO docs/dev team.
Source of truth: a real login HAR from `procesio.app` + live calls against
`webapi.procesio.app` (2026-06-23). Target page:
`https://docs.procesio.com/developers-guide/procesio-api-documentation`.

The **username/password authentication** chapter is materially out of date — it
documents an OAuth/Bearer flow on a host that no longer serves it. The API-key /
run-a-process chapter is mostly correct. Details below.

---

## 1. Authentication host moved: `auth.procesio.app` → `webapi.procesio.app`

**Docs say:** *"Use the Proxy API `https://auth.procesio.app/swagger/index.html`
to reach the Authentication Service … POST `/api/Authentication`."*

**Reality:** login happens on the Web API host. `auth.procesio.app` now answers
with Kong's **default self-signed certificate** (`CN=localhost, O=Kong`) and
returns `{"message":"no Route matched"}` for `/api/Authentication` and
`/swagger/index.html`. Any integrator following the docs hits a TLS/404 wall.

**Fix:** point the auth chapter at `https://webapi.procesio.app`, and remove (or
repoint) the dead `auth.procesio.app/swagger/index.html` link.

## 2. Login request shape is wrong (JSON+OAuth → form + `x-requested-by`)

**Docs say:** `POST /api/Authentication` with a JSON body
`{realm:"procesio01", grant_type:"password", username, password,
client_id:"procesio-ui", client_secret:""}`.

**Reality (from the HAR):**

```http
POST https://webapi.procesio.app/api/authentication
Content-Type: application/x-www-form-urlencoded
x-requested-by: playground-v1

username=<user>&password=<pass>&client_id=procesio-ui
```

Differences to correct:
- **Content type is `application/x-www-form-urlencoded`**, not JSON.
- Body fields are only **`username`, `password`, `client_id`**. `realm`,
  `grant_type`, and `client_secret` are **not used** — drop them from the docs.
- A **`x-requested-by`** request header is **required**. Without it the gateway
  returns **`407`**. (The web app sends `x-requested-by: playground-v1`.) This
  header is currently undocumented and is the single most common reason an
  integration "mysteriously" fails to authenticate.
- Path casing in production is lowercase `/api/authentication` (ASP.NET is
  case-insensitive, so both resolve, but the docs/Swagger differ — align them).

## 3. Token delivery: Bearer JWT → HttpOnly cookie session

**Docs say:** *"you will receive an access token in the response which you will
be able to use to access the Web API"* and a **"Bearer Authentication"** section
(Authorize with `Bearer {token}`).

**Reality:** the `200` response body contains **no token** — it is literally
`{"message":"Authentication successful"}`. Authentication is delivered as **two
HttpOnly cookies**:

```
Set-Cookie: __Host-procesio.access   (HttpOnly, Secure, Path=/)
Set-Cookie: __Host-procesio.refresh  (HttpOnly, Secure, Path=/)
```

Subsequent Web-API calls authenticate by **sending those cookies** (the SPA uses
`fetch(..., {credentials:"include"})`; the server replies with
`Access-Control-Allow-Credentials: true`) plus the same `x-requested-by` header.
Lifetimes come from the cookies' own `Expires` attribute — observed
**~24 h for `.access`** and a longer window for `.refresh` (values were 961 and
733 bytes, i.e. JWTs). The `x-session-expires-at` header is declared in
`Access-Control-Expose-Headers` but was **empty** in the login response we
captured — either populate it consistently or remove it from the contract.

**Fix:** replace the "access token + Bearer {token}" narrative for the
username/password flow with a **cookie-session** description:
- list the two `__Host-procesio.*` cookies and that they are HttpOnly/Secure,
- state that callers must send cookies (`credentials: include`) + `x-requested-by`,
- document `x-session-expires-at` and the refresh mechanism (what calls the
  refresh cookie, and the refresh endpoint, if any),
- if `Authorization: Bearer` is still accepted by the Web API for
  machine-to-machine use, document **how to obtain that token now** (the login
  no longer returns one); otherwise remove the Bearer section for this flow.

## 4. API-key auth — mostly correct, two clarifications

The run-a-process chapter correctly lists the three headers `key` (key name),
`value` (key value), `workspaceid` (workspace GUID) on
`POST https://webapi.procesio.app/api/projects/{id}/run` with body
`{"payload":{}, "connectionid":null}`. Confirmed working live. Two additions:

- **State that `workspaceid` is required for workspace-scoped keys.** Live: a
  workspace-scoped key returns **`401`** with no `workspaceid`; supplying the
  correct workspace GUID returns `200`. (A master/personal key happens to work
  without one.) This isn't obvious and bites integrators.
- The Swagger security schemes name these headers `KeyName`→`key` and
  `KeyValue`→`value`. Make sure the prose and Swagger use the same names
  (`key`/`value`, not `api_key`).

## 5. Minor path/casing alignments

- Process **list** is `GET /api/Projects`; **run** is `POST /api/Projects/{id}/run`
  (capital `P`; the run endpoint also accepts `runSynchronous` &
  `secondsTimeOut` query params). The "ProcessTemplate" tag maps to the
  `/api/Projects` path — worth a note so readers don't look for `/api/ProcessTemplate`.
- Workspace **list** is `GET /api/Workspaces` (plural). `GET /api/Workspace`
  (singular) is not a route → 401/404. Align docs/examples to the plural form.
- The `webapi.procesio.app` v1.19 Swagger is accurate and reachable — keep it as
  the canonical Web-API reference; just fix the **auth chapter** that precedes it.

---

### TL;DR for the doc owner
1. Auth host: `auth.procesio.app` → `webapi.procesio.app`.
2. Login is **form-urlencoded** with **`username`+`password`+`client_id`** and a
   required **`x-requested-by`** header — not JSON/OAuth.
3. Auth is a **cookie session** (`__Host-procesio.access`/`.refresh`), not a
   Bearer token in the body.
4. Spell out that **`workspaceid` is required** for workspace-scoped API keys.
5. Fix the dead `auth.procesio.app/swagger` link and small path-casing mismatches.
