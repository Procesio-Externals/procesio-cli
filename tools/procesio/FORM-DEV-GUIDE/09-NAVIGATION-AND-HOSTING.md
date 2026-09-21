# 09 — Navigation between forms, public URLs, and what the host shell always shows

Verified in a live browser against the deployed runtime, 2026-09-03. This is the chapter to
read before designing a multi-form product (a control panel, a wizard, a "app made of forms").

## 1. A form has NO URL until one is minted — and only the server's tiny URL resolves

There is no id-based public URL. `GET <gateway>/<formId>` is a 404. A form is unreachable
until a CustomUrl record exists, and what then resolves is the **server-minted `tinyUrl`**,
not the human slug you supplied.

```
POST /api/CustomUrl/FormTemplate
  {"workspaceId": "...", "entityId": "<formId>", "entityType": 1, "type": 3, "url": "my-slug"}
→ {"id": "...", "url": "my-slug", "tinyUrl": "q0aQ3f_zmC"}
```

| tried | result |
|---|---|
| `<host>/q0aQ3f_zmC` (server tinyUrl) | **200** |
| `<host>/my-slug` (your slug) | 404 |
| `<host>/<formId>` | 404 |

The SPA route table has exactly two public shapes:

```
/:entityUrl                                        ← the tinyUrl route
/:masterWorkspaceUrl/:subWorkspaceUrl/:entityUrl   ← vanity, needs BOTH other segments minted
```

Your slug is only ever the **third** segment. The readable 3-segment address therefore needs
`CustomUrl/MasterWorkspace` and `CustomUrl/Workspace` records minted first (bare JSON-string
bodies, reserved words rejected) — an installation-wide act, not a per-form one.

**CustomUrl changes a PATH, never a hostname.** The host is fixed per installation.

## 2. Navigating from one form to another — the proven recipe

A button can navigate. Use an element-event, never form-level code:

```bash
python scripts/run-tool.py procesio form-set-element-event \
  --id <form> --element <buttonName> --on click --action RUN_JAVASCRIPT --config-file nav.json
```

```json
{"code": "var W = (window.parent && window.parent !== window) ? window.parent : window;\nW.location.assign('https://<forms-host>/<tinyUrl>');"}
```

**Why it is allowed:** the trigger sandbox is a same-origin `srcdoc` iframe carrying **no
`sandbox` attribute**, so assigning `window.parent.location` is permitted.

**The event config is PLAINTEXT** — verified by reading it back from a fresh GET, and again in
the anonymous payload served to any browser. This is a different surface from `Data.code`
(which is AES-encrypted); element-event JS does not depend on the form-code key.

### Adding an event without destroying the one already there

| flag | effect |
|---|---|
| none (append) | adds; existing events survive (`event_count` 1 → 2) |
| `--replace` | **discards ALL events on that trigger**, with a warning that does not block |
| `--replace-action <ACTION>` | swaps that one action in place; others untouched; slot order kept, event id is new |

Never use bare `--replace` on a trigger you did not just create.

`TRIGGER_FORM` is a different mechanism — the assignee / task-dispatch path, executed by the
host app — and is **not** established as browser navigation. Use `RUN_JAVASCRIPT`.

## 3. What the host shell shows no matter what you configure

`hideBranding: true` removes **exactly one thing**: the bottom "Built with PROCESIO" banner
and its click-through. Confirmed against the renderer source and side by side in a browser.

Everything else in the topbar is unconditional: the platform logo linking to the main app, the
form's **name** (not `browserTitle`), a theme toggle, and a hard-coded ` - PROCESIO` suffix on
the tab title. For a **signed-in** visitor it additionally renders `Workspace: <name>` and a
user-avatar menu — platform chrome inside what you may have promised as a plain app.

There is also an anti-hiding guard in the deployed bundle: form-level CSS is scrubbed of the
branding class name before injection. (It uses a string `replace`, so it removes only the
first occurrence — but do not build on that.)

**Consequence for product promises:** "the user never sees the platform" is not achievable
through form configuration on a shared host. It is a property of the installation, not of the
form DTO. Establish which host a customer will be on before promising a white-labelled app.

## 4. Private forms and anonymous visitors

A private form opened without a session returns 401 and renders a dead end — *"Form not
found — the link may be outdated, the form may have been removed, or you may not have
access."* **There is no sign-in prompt and no redirect to a login.** A runner handed a link
who is not already signed in simply cannot get in from there.

A public form renders immediately with no login, as a bare form card.

Also: opening a **private** form over a tinyUrl calls `setActiveWorkspace(form.workspaceId)` —
it **switches the signed-in user's active workspace**. Worth knowing before a control panel
links across workspaces.

## 5. Reading and writing field values from event JS

`ProcesioForm.data.fields.<elementName>.value` works for read and write (also `.visible`,
`.required`, `.readonly`); `ProcesioForm.variables.<name>` for form variables. The field key is
the element **name**, lowercased by the runtime.

**The snapshot lags by one interaction.** A field typed into immediately before the click can
read back empty on that click and correct on the next. Do not assume the keystroke preceding a
click is visible to it — and do not conclude "there are no values" from a single probe.

## 6. Which elements have a value at all

Only value-bearing controls get a `value` config, and therefore a `value` attribute in the data
model. A **button** and a **paragraph** correctly have none. The invariant that holds for every
type is the §5 rule: *every data-model attribute id equals the element's config id for that key*.
Asserting "a new element has a `value`" is the wrong check for a button, and will read as a
failure when authoring is correct.

## 7. `Data.events` — the form-level trigger surface (plaintext, and the ONLY on-load hook)

There is a **third** event surface beside element events and the encrypted `Data.code`: a
flat array at `Data.events`, the designer's *onLoad / onBeforeSubmit / onAfterSubmit*. It is
**plaintext**, so it does not depend on the form-code key that `form-set-code` needs.

```json
[{"id": "<guid>", "type": "FORM_LOAD", "action": "RUN_JAVASCRIPT", "config": {"code": "…"}}]
```

Types: `FORM_LOAD`, `FORM_BEFORE_SUBMIT`, `FORM_AFTER_SUBMIT`. Note the shape: a **flat list of
event objects**, NOT the `{debounce, events:[…]}` wrapper an element config uses.

Write it with `form-update --data-file '{"events": […]}'` — the merge replaces arrays wholesale,
and it touches nothing else (`code`, `theme`, `elements` survive). Read it back from a fresh
`form-get`.

**Why it matters: no ordinary control has a load trigger.** Of every element golden, only `chat`
carries `onReadyEvents`. So anything that must happen *before the first click* — greeting the
viewer, hiding a branch, seeding a label — has exactly one place to live, and it is not the
encrypted code blob.

It runs in the **same sandbox** as an element event, so `ProcesioForm` is available.

### The viewer's identity, addressable from any trigger

The renderer generates an `instance` node into the data model and fills it from the signed-in
session, so JS can read who is looking:

```js
ProcesioForm.data.instance.currentUser.id     // user id ("" / null when anonymous)
ProcesioForm.data.instance.currentUser.name   // full name
ProcesioForm.data.instance.currentUser.email
```

`instance.submitter` (id / name) and `instance.ID` (the instance id) sit beside it. The attribute
ids are **constants baked into the renderer**, not per-form guids, so the node works on any form.

**This is orientation, never authorization.** Anything a browser can read, a viewer can edit, and
the event config is served to them in plaintext — so an allow-list held in form JS is a UI hint
wearing a lock's clothing. It also puts a roster of real addresses into a document every viewer
can read. Let the platform's permission profile refuse server-side, and use identity to tell a
viewer *which account they are on* before they choose a route.

### Writing a config other than `value`

`ProcesioForm.data.fields.<name>.<attr> = …` reaches **any exposed config**, not just `value` —
`label`, `visible`, `readonly`, `required`. That is how a paragraph or a heading gets rewritten at
runtime. Two rules decide the key:

- only configs marked `exposed: true` get a data-model attribute (`style` has none, so it is
  unreachable from JS);
- the attribute name is the **camelCase of the config's designer label**, not its `key` — the
  config `{key: "info-text", label: "Info text"}` is addressed as `.infoText`.

A write that lands on a readonly attribute is not an error: the sandbox logs *"Readonly property
… can not be set!"* and moves on.

### Two rules for any form-load script

1. **Wrap the whole body in `try`/`catch`.** An unhandled top-level throw stops the sandbox
   reporting completion, and the trigger is only released after a **60-second** timeout — the
   console says so, but the form has been sitting there the whole time.
2. **Write the static copy so it is already correct, and let the script only improve it.** The
   script is one cached bundle, one renaming, one absent identity away from not running.
   `"Welcome."` → `"Welcome, <name>."` degrades invisibly; `"Welcome, "` does not.

## 8. A public front door with delegated sign-in (the safe way past §4's dead end)

§4's dead end has exactly one fix that keeps every private form private: **one public
signpost form** whose only job is to name the thing and hand sign-in off to PROCESIO.

**Publishing is per-template, not per-workspace.** Flip one form public with
`form-update --id <form> --is-private false`. Proven on a live workspace: with one form
public, an anonymous `GET /api/FormTemplate/{workspaceId}/{id}` returned **200 for that
form and 401 for every other form in the same workspace**, and the workspace's
form-backed data stores stayed **401** (`GET /api/Form/dataStore/{id}/rows` with the
`formTemplateWorkspaceId` header). So making a signpost public does **not** widen the
anonymous surface to the private forms or their stores beside it — the earlier worry that
"publishing any form exposes every store in the workspace" is wrong. Keep the signpost
safe by construction: **no input fields, no backing flow, no data-store binding** — a form
that collects nothing and launches nothing has nothing to leak, whoever opens it.

**Delegated sign-in — never collect the password.** The signpost's primary button
navigates the top window to the platform's own login (`https://<app-host>`, e.g.
`procesio.app`), which signed-out shows the real email + SSO login. That is the whole
"pass the credentials to PROCESIO encrypted" story: the user types them on PROCESIO's own
origin, TLS-encrypted to its auth service, and PROCESIO sets the HTTP-only session cookie.
Do **not** build a login form that collects the password into its own fields, even to
"encrypt and forward" it: (a) it trains users to type their platform password into a
non-login page — the phishing pattern; and (b) it cannot work anyway — event JS runs in a
sandboxed same-origin `srcdoc` iframe and HTTP-only auth cookies are unreadable/unsettable
from page script, so the form could capture the password but never establish the session.

**Two things the login handoff cannot do — design around them, don't fight them:**
- **No return-to-form.** The login UI drops any `redirect_uri` that points at a form (the
  URL reverts to the bare app host); after sign-in the user lands on the dashboard, not
  back on your form. So the round trip is: signpost → login → dashboard → the user opens
  the form link (bookmark). You cannot auto-forward them onto the form after login.
- **No role from the client.** `GET /api/Users/me` returns only `userId / username /
  firstName / lastName / email` — **no role, no userType, no per-workspace permissions** —
  and `ProcesioForm.data.instance.currentUser` exposes only id/name/email (empty when
  anonymous). So a form cannot branch "runner vs admin" client-side. Offer both
  destinations as buttons and let the **permission profile refuse server-side** (a runner
  clicking an admin door hits §4's 401); role-based *auto*-routing would need a backing
  flow that reads the permission catalog with a bound credential, which forfeits the
  export/import-clean, credential-free property that makes a pack marketplace-ready.

**Adding the button (`form-add-element`) takes a MINIMAL spec, not a cloned element.**
Pass `{"type":"button","label":"…","name":"…"}` and the tool synthesises the element and
its data-model sub-model. Passing a full element you read back (with a `configs` list, a
dict `onClickEvents`, a `style: []`) throws `'list' object has no attribute 'items'`. To
give the new button its navigation, add it minimal, then set the click JS separately with
`form-set-element-event --on click --action RUN_JAVASCRIPT` (see §2's recipe).

## 9. App tiles (`FormApplication`) — the only tenant-portable navigation

§2's recipe (a button whose JS assigns `location` to `https://forms.procesio.app/<tinyUrl>`) is
correct **inside one installation and nowhere else**. A tinyUrl is minted per workspace, so every
absolute inter-form URL you bake into a form is a pointer at *your* tenant. Export a pack built that
way and every importer's buttons lead back to the author's forms — a broken app, the author's form
and process ids shipped inside a "clean" bundle, and a live cross-tenant redirect the moment the
author publishes any of those forms. Runtime repair is not available either: from a form's origin,
`GET /api/FormTemplate/{ws}/{id}` on a private sibling returns **401**, so a form cannot look its
neighbours up and self-heal.

**Use `FormApplication` instead.** It registers a form as an **app tile** on the workspace dashboard
(the same mechanism the built-in apps use), and it is bound to the form by **`pid` = the form
template id**, never by URL. Ids survive import, so a tile resolves to whichever tenant it is
installed in. This is what makes a multi-form pack portable, and it removes bookmark-passing: a user
signs in, lands on the dashboard, and the apps are there.

```
POST /api/FormApplication
{ "pid": "<form template id>", "name": "…", "description": "…",
  "image": { "url": "", "name": "icon.png", "value": "data:image/png;base64,…", "source": 2 },
  "type": 2, "enabled": true, "isProcesio": false }
```

- **`image.source` is REQUIRED and is the trap.** Omit it and the create fails with HTTP 500
  `Data truncated for column 'ImageSource'` — an error that reads like a length problem and is not.
  `source: 2` goes with a base64 `value`.
- **Tiles are NOT carried by a `.procesio` export.** Verified: a bundle containing forms, flows and
  a store carries no `FormApplications`. They are created at install — one POST per tile, which is
  far cheaper than minting a URL per form *and* hand-editing navigation JS.
- The tile opens the form in a **new tab**, so a scripted click on the dashboard will not move the
  original page.

**What still belongs in a form.** Two navigation targets are tenant-independent and safe to hardcode:
the platform root (`https://<app-host>`, for sign-in or platform admin), and **going back** — use
`W.history.back()` (with the same top-window `W` as §2), never a hardcoded "back to X" URL. Between
tiles for forward navigation and `history.back()` for return, a portable pack needs no per-tenant
URL anywhere. Before shipping, grep the exported forms for `forms.<host>/` and for any
`admin/process/designer/<guid>` deep-link: both should be zero.
