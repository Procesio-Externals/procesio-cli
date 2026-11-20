# 12 - Embedding a form in another web page (the PROCESIO form SDK)

A PROCESIO form can run inside any web page, a customer portal, a landing page or an internal
tool, with the form SDK `@procesio/form-sdk` (repository `PROCESIO/procesio-form-sdk`). The SDK
puts an `<iframe>` in an element of the page and talks to the form over `postMessage`. The page
hears what happens in the form, and can ask the form to act. The form keeps running on the
PROCESIO origin, so its CSS and the page's never meet, and it always follows the deployed
runtime, whatever SDK version the page loads.

Verified on production on 2026-11-20 with the SDK built from its repository: embedding, prefill,
the form's own onLoad Data Store reads, `ready`, `resize`, `submit` and `error`.

**Start here:** `procesio form-embed --id <form id>` checks everything below for one form and
returns a ready snippet; `--out page.html` writes a complete test page.

## What has to be true

| Condition | Otherwise |
|---|---|
| The form is **public** (`isPrivate: false`) | a private form, a submission or an assignment needs a signed-in PROCESIO session, which a page on another domain does not have: the page gets `not-found` |
| The form is **published** (`status: 1`) | a designer Save leaves a draft (`status: 0`), which nobody can open: `not-found` |
| The form is **enabled** (`state: true`) | `not-found` |
| The page is served over **http(s)** | opened from disk, the page hears no event and can ask nothing |
| The runtime at `baseUrl` has the embed bridge | the form shows but reports nothing; after 5 s the SDK raises `embed-unsupported` |

`not-found` arrives about 120 ms after mount, with the message "The form could not be loaded.
The link may be outdated, the form may have been removed, or it may not be accessible."

## What each runtime supports

The runtime is the form front end at the environment's forms host. A build can carry the embed
bridge (events) before it carries the page's requests:

| Runtime | Embed + events (`ready`, `resize`, `submit`, `error`) | Page requests (`setValues`, `validate`, `focus`, `submit`, `runTrigger`) |
|---|---|---|
| `forms.procesio.app` (production) | yes | **not yet** (checked 2026-11-20): a request is never answered, the promise waits |
| `forms-qa.procesio.app` | yes | not yet (the same build as production) |
| `forms-dev.procesio.app` | yes | yes |

`form-embed` reads this live from the runtime's bundle (the bridge's `embedOrigin` parameter and
the request names `set-values`, `run-trigger`), so it stays right after a deployment. Until a
runtime answers requests, prefill with `values` at mount: it works everywhere.

## Getting the SDK

- **npm**: `npm install @procesio/form-sdk`, then `import { create } from '@procesio/form-sdk'`.
  As of 2026-11-20 the package is not on the public registry yet (a publish-from-tag workflow is
  on the SDK's `task/publish-to-npm` branch); until then it installs from GitHub Packages
  (`@procesio:registry=https://npm.pkg.github.com` with a token).
- **A `<script>` tag**: the UMD build defines `window.ProcesioForm`. Once the package is on npm,
  a CDN serves it: `https://cdn.jsdelivr.net/npm/@procesio/form-sdk@1/dist/procesio-form-sdk.umd.js`
  (name the major version so a later one cannot change the page). Before that, build it
  (`npm install && npm run build` in the SDK repository; the build reads the message contract
  from a `form-runtime` checkout next to it on `main`) and host `dist/procesio-form-sdk.umd.js`
  yourself.
- Sizes: about 5 kB gzipped on the page.

## The code

```html
<div id="contact-form"></div>
<script src="https://cdn.jsdelivr.net/npm/@procesio/form-sdk@1/dist/procesio-form-sdk.umd.js"></script>
<script>
  const form = ProcesioForm.create('#contact-form', {
    formId: '<form template id>',
    workspaceId: '<workspace id>',
    values: { email: 'ana@example.com' },        // prefill, by field NAME
  });
  form.on('submit', ({ success, submissionId }) => { if (success) showThanks(submissionId); });
  form.on('error', ({ code, message }) => console.error(code, message));
</script>
```

Which form, exactly one of: `formId` (a template), `path` (its tiny URL or custom URL, e.g.
`p2FrgbxLzq`), `formId` + `submissionId`, `assignmentId` (the last two need a signed-in session).
`baseUrl` defaults to production; pass the environment's forms host for any other
(`https://forms-dev.procesio.app`, or a client installation's).

Other options: `theme` (`light` | `dark` | `system`), `showHeader` (default off), `autoHeight`
(default on, the page scrolls) or a fixed `height`, `initialHeight`, `className`, `iframe`
(`title`, `allow`, `sandbox`, `loading`, `referrerPolicy`), `on` (listeners before load),
`autoMount`. Leave `iframe.sandbox` unset unless you need it; the form needs at least
`allow-scripts allow-same-origin allow-forms allow-popups allow-downloads`.

## Events (all verified on production)

| Event | Payload | When |
|---|---|---|
| `ready` | `{ formName }` | the form is on screen, once per mount (also `await form.ready`); 230-520 ms |
| `resize` | `{ height, width }` | the content height changed (with `autoHeight`) |
| `submit` | `{ success, submissionId, formId, messageType }` | after every submit, failed ones too; `messageType` `SUBMIT_SUCCESS` on success. The iframe then shrinks to the form's thank-you message |
| `error` | `{ code, message }` | loading failed: `not-found`, `frame-unreachable` (45 s), `embed-unsupported` (5 s), `form-timeout` (20 s), `mount-failed` |

`submissionId` is the saved form instance: the page's reference to what was submitted.

## Prefill and the form's own logic

- `values` (and `setValues`) go by the field's **name** (its `name` config, what the designer
  shows as Name), never its id. A name the form does not have is skipped silently;
  `form-embed --values` checks them against the form.
- **`values` is applied before the form's onLoad events.** A form that reads a Data Store on
  load with a filter on a field reads with the value the page passed: a page can open the
  same form on a different record, category or customer with no extra call (verified: a READ
  filtered on the prefilled field returned the prefilled category's rows).
- Everything the form does by itself runs embedded as it does standalone: onLoad and element
  Data Store events, saved queries, processes, dropdowns filled from rows, form JavaScript.

## Asking the form (where the runtime supports requests)

```js
await form.setValues({ email: 'ana@example.com' });   // names the form lacks are skipped
if (!(await form.validate())) await form.focus('email');
await form.submit();                                   // ends as a `submit` event
await form.runTrigger('<trigger id>', { orderId: 'NW-1' });   // `data` is $event in form JS
```

A trigger id is the id of an event: an element's event or one of the form's own (onLoad,
before / after submit). The designer has a copy button on each; `form-embed` lists them all with
the element and what each does. A refused request rejects with a `FormError` whose `code` is
`not-found`, `busy`, `not-allowed`, `failed`, `unsupported`, `no-origin` or `destroyed`.

## Methods

`form.destroy()`, `await form.reload({ ...newOptions })`, `await form.mount()` (with
`autoMount: false`), `form.setTheme('dark')`, `form.resize()`, and `form.element`,
`form.iframe`, `form.options`, `form.isMounted`. `configure({ baseUrl })` sets defaults for every
form on the page.

## Build the form for embedding

- Make it public and publish it, and give it a short link if the page should not carry ids
  (`POST /api/CustomUrl/FormTemplate`, see chapter 09); `form-embed` reports the tiny URL.
- Name the fields the page will fill: the name is the API between the page and the form.
- Load what the form shows with Data Store events on the form's onLoad, not with a process
  (see `../PROCESIO-FORM-QUERIES-NOTES.md`); the page's prefill drives their filters.
- Give the form a submit button if the page waits for `submit`.
- Hide nothing the page needs to see: `showHeader` is off by default, and the form's own
  thank-you message is what shows after a submit unless the page replaces the embed.

## Testing an embed

`form-embed --id <form> --out page.html --sdk-url <where the UMD build is served>` writes a page
that logs every event. Serve it over http(s) (a local static server is enough) and open it; the
log shows `ready` with the form's name, `resize`, and `submit` with the submission id. Check
`error` with a form that is private, a draft or does not exist: `not-found`.
