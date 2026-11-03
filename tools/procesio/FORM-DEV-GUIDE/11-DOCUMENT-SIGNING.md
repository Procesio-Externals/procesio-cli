# 11 - Document signing: a form that collects signatures on a PDF

The `document-signing` element shows a PDF inside a form and runs a signing ceremony on it:
each signer places (or finds) their signature spot, signs by drawing, uploading an image or
typing, and the platform stamps the PDF and keeps an audit trail. Live in prod since
user-playground v1.116.0 and form-runtime v1.32.0 (2026-11-02). Every step below was run
against prod with this tool on 2026-11-03.

## How it fits together

- The element's **design** is plain configs saved in the form template: `document` (the
  PDF), `templateSigners` (who signs, in order), `templateSpots` (where each one signs, and
  the rows printed above the signature), plus toggles.
- The **ceremony** is server-side: a *signing envelope* (`api/form/signing/*`) seeded from
  the saved design when someone fills the form. The element's own `value` only references
  it: `{envelopeId, status, signedFileId}`.
- The host (the form runtime) does all REST calls. The element never sends the envelope;
  the runtime sends it at form submit. A submission made only over the API must send it
  itself (step 6).

## 1. Build the form with the element

```json
{"name": "Contract", "elements": [
  {"type": "input", "label": "Full name", "name": "fullName"},
  {"type": "document-signing", "label": "Sign the contract", "name": "ContractSigning",
   "configs": {
     "templateSigners": [{"id": "sig-filler", "kind": "FILLER", "userId": null, "label": "You"}],
     "templateSpots": [
       {"spotId": "s1", "partyId": "sig-filler", "page": 1, "x": 0.1, "y": 0.80, "w": 0.22, "h": 0.03, "type": "PRINTED_NAME", "required": false},
       {"spotId": "s2", "partyId": "sig-filler", "page": 1, "x": 0.1, "y": 0.83, "w": 0.22, "h": 0.08, "type": "SIGNATURE", "required": true}],
     "setupEditable": false, "required": true}},
  {"type": "button", "label": "Submit", "submit": true}]}
```

`procesio form-create --config-file contract.json`. Every other config comes from the golden
`dto/form/elements/document-signing.json` (generated from the FormBuilder mock).

## 2. Store the PDF and point the element at it

The template must be saved first (the upload is bound to its id):

```
procesio form-signing-upload-document --form-id <form id> --file contract.pdf --element ContractSigning
```

It answers `{fileId, name, pageCount}` and sets `document = {fileId, name}`. At most 10 MB
(the signing service's limit; the element's `maxFileSize` config, default 10, can only lower
it), PDF only, not encrypted. The two other `document` shapes work but are worse:
a URL string is fetched by the browser at fill time (it must allow CORS), and an inline
`{src: "data:application/pdf;base64,...", name}` puts the whole PDF in the form JSON (the
export shape; the lint flags it).

## 3. Signers: `templateSigners`

`[{id, kind, userId?, label?}]`, one step each, in list order.

- `FILLER` - whoever fills the form (the signed-in user, or the public signer, who types a
  first name, last name and e-mail). At most one.
- `MEMBER` - a workspace member, by `userId`. A MEMBER signer keeps the form private (the
  designer refuses "Make form public" while one is set); on a public form the slot is
  skipped.
- An entry without `kind` reads as MEMBER; an unknown kind is dropped by the designer.
- Order is the list order (each signer's `orderIndex` in the envelope; equal values would
  sign in parallel). There is no order-mode setting since v3.2.0. The design is always one
  signer per step; parallel steps exist only when the preparer sets them up while filling
  (`setupEditable` on: they add workspace members and drag them into steps).
- ⚠ A process cannot choose the signers. It can map values into the toggles and into
  `document`, but `templateSigners`, `templateSpots` and `blockFields` are not exposed to
  mapping (`exposed: false` in the golden). Signers are fixed in the design or picked by the
  preparer while filling.
- Apart from a public form's FILLER, every signer is a member of the form's workspace;
  inviting an outside signer by e-mail or link is not supported.

## 4. Spots: `templateSpots`

`[{spotId, partyId, page, x, y, w, h, type, required, label?, value?}]`

- `partyId` is a `templateSigners` id. `page` is 1-based. `x, y, w, h` are fractions of the
  page, top-left origin (0..1); the server converts to PDF points.
- `type`: `SIGNATURE` (required), `PRINTED_NAME`, `DATE_SIGNED`, `TEXT` (its printed text in
  `value`, max 256 characters; labels max 128). The API also takes `FIRST_NAME`/`LAST_NAME`.
- A **block** is rows stacked exactly above a SIGNATURE of the same party: same page, `x`
  and `w`, and `row.y + row.h == next.y`. Default geometry: width 0.22, row height 0.03,
  signature height 0.08. `blockFields` sets the rows a newly placed block starts with.
- ⚠ Give every signer a SIGNATURE spot. The Web API accepts a signer without one (their
  session's `placesOwnSignature`; their sign then carries `signatureSpot`), and upstream's
  element reference says such a signer clicks where to sign on their turn. That is the
  ui-builder 0.x line, which no longer fills forms in prod: user-playground v1.116.0 sends every
  fill route (public, assignments, submissions) to form-runtime, whose 1.x line (1.46.0 in
  prod and on its main as of 2026-11-03) has no own-signature placement. There the preparer's
  submit is refused with "Every signer needs a signature on the document", and a signer sent
  without a spot over the API has no way to sign in the form.
- Limits per envelope: 50 signers, 1000 spots, 10 rows per block, a draft of at most 1 MB.

## 5. Toggles

`setupEditable` (default on): off sends the document exactly as designed, and the filler only
signs. `fieldsEditable`: whether the preparer may rename, add or remove block rows.
`allowDecline` (default on) only hides **Decline**: the Web API does not check it, so an API
caller can still decline. `required`: a document must be attached before submit.
`maxHeight` (e.g. `600px`) scrolls the PDF inside the element instead of showing it whole.

## 6. The envelope lifecycle (what the runtime does, and what an API-only flow must do)

1. `POST api/form/signing/envelope/from-template {formTemplateId, elementId, formId?}` seeds a
   DRAFT from the saved design: one party per signer, the spots with fresh ids. (Public form:
   `POST api/form/signing/public/envelope/from-template` with `workspaceId`, `firstName`,
   `lastName`, `email`; it returns `{envelope, accessToken}` once, and every later public call
   sends `x-signing-token: <accessToken>`.)
2. The form is submitted; the runtime then sends the envelope:
   `POST api/form/signing/envelope/{id}/send?formId=<form instance id>&rowVersion=<n>`.
   **An API-only submission must make this call**, or nobody is ever asked to sign. A draft
   with no signers completes at once.
3. Each signer: `GET .../my-session`, then `POST .../my-session/sign {signaturePngBase64,
   timeZone, signatureSpot?}` (`signatureSpot {page,x,y,w,h}` only when `placesOwnSignature`),
   or `POST .../my-session/decline {reason}` (signed-in signers only; there is no public
   decline). The reason shows on the party as `declineReason`.
4. `GET .../document?version=current|signed|source|my-step` streams a rendition; any other
   value is refused (400, code 502).

Statuses: envelope DRAFT, SENT, IN_PROGRESS, COMPLETED (everyone signed, or there was no
signer), DECLINED (a decline stops the signing and e-mails the envelope's creator), VOIDED
(the form instance or template was deleted), EXPIRED (not finished within 14 days of the
send, the default `ExpiresOn`). Party PENDING (not e-mailed a sign request: a later step's
signer, the sender in the first step, or a public form's signer), NOTIFIED, VIEWED, SIGNED,
DECLINED. An unsent DRAFT is deleted after 30 days without changes. While envelopes are live,
the submission's next step has `FormAssigneeType.SIGNER = 3` assignees (only the Web API
writes those).

## 7. Reacting in the form and in the process

- Element events `onSignedEvents`, `onDeclinedEvents`, `onCompletedEvents`, with `$event =
  {envelopeId, status, party, signedPartyCount, totalPartyCount, completed, reason?}`.
  `onCompleted` fires right after the `onSigned` that completed the document, and also when a
  document with no signers is sent. Only the current user's own act fires a trigger: another
  signer's signature or decline fires nothing in this form and shows as a status the next
  time it loads.
- Wire them with `form-set-element-event --on signed | declined | completed` (event types
  `SIGNING_SIGNED` / `SIGNING_DECLINED` / `SIGNING_COMPLETED`). Example, launching a process when the document is completed:
  `form-set-element-event --id <form> --element <signing element name> --on completed
  --action RUN_PROCESS --config-file cfg.json` with `cfg.json` = `{"processId": ...,
  "inputMap": [{"left": "<process variable>", "right": "<form field name>"}], "outputMap": []}`;
  both sides take names and are resolved. Run it with `--dry-run` first. An element saved
  without the slot gets it back-filled from the template. `form-get-element-events` lists the
  three slots; it also reads a slot written by hand as a bare list of events (the runtime
  accepts that shape and `{debounce, events}` alike). Measured 2026-11-03: a public fill
  launched the process once, after the signature, with the form's field values mapped in.
- ⚠ Mapping the signing element ITSELF into a process at `onCompleted` hands over its value as it
  was before the signature: `{envelopeId, status: "DRAFT", signedFileId: null, ...}`. The
  envelope id is right; do not count on `signedFileId` or the status there.
- A process mapping the element's `document` attribute receives the file NAME for a stored or
  inline file, and null for a data: URL. The signed PDF is the envelope's `signedFileId`.
- In the app, the form's **Submissions** list shows a download icon in the signing element's
  column: it downloads the signed rendition (the same bytes as `document?version=signed`).
  Show details lists the stage (`completed`).

## 7b. What the designer and the fill page do (measured 2026-11-03)

- **Designer:** a new element starts with NO signers. Under Signers, "+ The person filling the
  form" adds the FILLER (labelled "Form filler"); "Add a workspace member" is refused on a
  public form ("Members cannot be added as signers unless this option in Form settings is
  removed"). Pick the signer's chip above the PDF, then click the page: the block is CENTRED on
  the click, rows from "Signature block fields configuration" (default Full name, Date) above
  the signature. The settings also hold the PDF (upload zone or URL, "Max document size (MB)"
  10), "Signers can decline", "Preparer can set up signing" (`setupEditable`) and the three
  events.
- **Fill page, signed in:** a public form still runs the PUBLIC envelope even when the person
  filling it is signed in; the signer's first name, last name and e-mail come prefilled from
  the account and stay editable, and the envelope party gets what is typed. The Sign dialog
  offers Draw / Upload image / Type; after it the element shows "Signed - sent with the form"
  and the signature on its block. The calls run in this order: from-template (at Sign), form
  submit, envelope PUT, send, my-session/sign, then the element's triggers.
- **No e-mail** reaches a public filler who signs on the spot.

## 8. Errors you will meet

The Web API answers with its coded list; the tool shows `message (code N) [target]`:

| code | when |
|---|---|
| 502 | a `document?version=` other than current, signed, source or my-step |
| 710 | envelope not found (also after delete) |
| 711 | the envelope's state refuses it: an edit of a non-DRAFT, a send of a declined or voided envelope or one without `formId`, a sign or decline when the envelope is not SENT / IN_PROGRESS or the caller already acted |
| 712 | try again: a stale `rowVersion`, the envelope changed meanwhile, or the document or signature could not be stored |
| 713 | not the caller's turn |
| 714 | a signer is not valid (a MEMBER who is not in the workspace), sign without a required `signatureSpot`, or a send that dropped a signer the design named |
| 715 | spot configuration invalid: unknown signer, page out of range, off the page, or a signer placing a spot when one was placed for them (was 409/711 before v3.2.0) |
| 716 | the document cannot be rendered (the envelope stays DRAFT) |
| 719 | the signature image is missing, not base64, not a PNG, or over the size or pixel cap |
| 1013 | the installation has Forms switched off (`procesio features`) |

## 9. Verify

`form-get-element --element ContractSigning --key document --key templateSigners` shows the
design; the form lint (run on every form write) reports a spot for an unknown signer, a
signer without a SIGNATURE spot (the prod form runtime refuses it, see step 4), a MEMBER without a user, two FILLERs, geometry off the page
and an inline PDF. To see it rendered, publish (`form-update --is-private false --status 1`,
FILLER-only designs) and open `https://forms.procesio.app/forms/<form id>#<workspace id>`: the
PDF shows with the placed blocks and a Sign button.
