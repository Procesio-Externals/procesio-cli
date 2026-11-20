# Embed a form in another web application

## Goal

Put a PROCESIO form inside a web page or application that is not PROCESIO (a portal, a landing page, an internal tool) with the PROCESIO form SDK, and prove the page receives what the form does.

## Preconditions

- Identify the form, its environment and workspace, the page or application that will host it, and what the page must know (a submit, a submission id, the form's height) or set (prefilled values).
- Only a public, published, enabled form can be embedded today. A private form, a submission or an assignment needs a signed-in PROCESIO session, which a page on another domain does not have.
- The host page must be served over http(s); opened from disk it hears nothing.

## Inspect

1. Run `procesio form-embed --id <form id>` for the form's environment. It reports whether the form can be embedded and why not, what the environment's form runtime supports, the field names the page can prefill, the trigger ids the page can run, where the SDK comes from today, and a ready snippet (`--framework html | module | react`).
2. Read the runtime support it reports. A runtime can embed and report events while not yet answering the page's requests (`setValues`, `validate`, `focus`, `submit`, `runTrigger`): on such a runtime, prefill with `values` at mount and do not depend on requests.
3. Read the SDK source it reports. While the package is not on the public npm registry, build its browser bundle from the SDK repository and host it with the page, or install it from the organisation's package registry.

## Prepare the form

- Make it public and publish it; a save in the designer leaves a draft, which nobody can open. Give it a short link if the page should not carry ids.
- Name the fields the page will fill: prefill and page requests address fields by name, never by id.
- Load what the form shows with Data Store events on the form's own load event, not with a process; the page's prefill is applied before those events, so it can drive their filters.
- Give the form a submit button when the page waits for the submit event.

## Execute

- Paste the snippet into the host page, or write a test page with `form-embed --out <file>` and serve it over http(s).
- Pass the environment's forms host as `baseUrl` for any environment other than production; the snippet does it.
- Keep the iframe sandbox unset unless the host requires one; the form needs scripts, same-origin, forms, popups and downloads.

## Verify

1. The page logs `ready` with the form's name within a second, then `resize`.
2. Prefilled fields show the page's values, and anything the form loads on open reflects them.
3. A submit from inside the form reaches the page as `submit` with `success` and a `submissionId`.
4. A form that is private, a draft or missing reaches the page as `error` with code `not-found`.
5. Where the runtime supports requests, each page call resolves (or rejects with a `FormError` code); where it does not, the report says so and no page logic depends on them.

The procesio tool's form development guide, chapter 12, has the options, events, methods, error codes and the runtime support table.
