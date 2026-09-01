# PROCESIO "Send Email" action — attachment + dynamic recipient

How a PROCESIO **Send Email** action node sends an email with a **file
attachment** and a **dynamic (variable) recipient**. Verified against both the
offline `.procesio` export and the live `GET /api/Actions?getFullAction=true`
catalog for workspace `3fd85e9d-121e-415b-877f-f488cd685ce3`.

**Reference flow (real, working):**
`tools/procesio/docs_info/Exports/export_POSF_PROCESIO.procesio` ->
Flow **"Notification/Process Event with FILE"** -> action
`ActionName="notify"`, `ActionTemplateName="Send Email"`,
`TemplateId = c7673492-2912-4975-8cab-747fb9f4085d`, `Category = "cat1"`.

This is a node-building note (how to author the action's `Parameters[]` in a
flow DTO), complementing the API/auth notes — see
[PROCESIO-API-NOTES.md](PROCESIO-API-NOTES.md).

---

## 1. "Send Email" is the only send action (SMTP, NOT SendGrid)

The action catalog has four email-related actions:

| Action | Purpose |
|---|---|
| **Send Email** | **The ONLY email-send action.** SMTP-based. |
| Read Mailbox | Read incoming mail |
| Read Mailbox V2 | Read incoming mail (newer) |
| Word Mail Merge | Mail-merge a Word template |

There is **no SendGrid action** in PROCESIO — "Send Email" goes out over SMTP.
Its **first** configuration field is `type="credentials"`, label
**"Select SMTP credentials"**, with
`credentialsTemplateId = 20202020-0001-0000-0000-aaaaaaaaaaaa`. The bound
value is the GUID of a stored SMTP credential (in the example below,
`2aacf4f1-310c-469f-80ef-394d6ab9582f`).

## 2. Variable-binding pattern (applies to every field)

Every configurable field is one entry in the action's `Parameters[]` array:

```jsonc
{
  "TabPropertyId": "<field GUID>",          // which field (see map in section 3)
  "Variable": [                              // [] when the field is empty/literal
    { "id": 0, "variableId": "<flow var GUID>", "attribute": null }
  ],
  "Value": "<%0%>"                           // PROCESIO placeholder(s) + literal text
}
```

- **`Value`** holds PROCESIO placeholders of the form **`<%N%>`**, where `N` is
  the `id` of the matching entry in `Variable[]`. Placeholders are **mixable
  with literal text** — e.g. a Subject of `"Notificare mesaj: <%1%>"` injects
  flow variable `id:1` after the literal prefix.
- Each `<%N%>` in `Value` must have a `Variable[]` entry whose `id == N`; that
  entry's `variableId` is the flow variable's GUID. `attribute` is `null` for a
  whole-variable bind (set it to bind a sub-property of a complex variable).
- A field that is **empty or purely literal** has **`Variable: []`** and either a
  literal string `Value` (e.g. From display name `"POSF Notification"`) or
  `""`/`null`.

## 3. TabPropertyId map — Send Email fields

| TabPropertyId | Field | Type / notes |
|---|---|---|
| `f9d5da64-bbc0-4d53-a0ad-6f948cc3ff05` | **Select SMTP credentials** | `credentials` (credentialsTemplateId `20202020-0001-0000-0000-aaaaaaaaaaaa`) |
| `90d1ec9f-803c-42bc-bd8b-ca11e4ef116c` | **From (Display Name)** | string |
| `90d1ec9f-803c-42bc-bd8b-ca11e4ef11c6` | **From (Entity)** | string — WARNING: differs from Display Name only in the last 4 chars (`...11c6` vs `...116c`); easy to transpose |
| `1def19eb-ec69-4a21-a756-4abec8ae3171` | **To** | string (dynamic recipient — see section 5) |
| `30ba958f-0d83-4259-97b9-d64ce7282d83` | **Cc** | string |
| `1b6fbfac-183a-481b-9e0d-d4e7cf5543fe` | **Bcc** | string |
| `9eeaf788-c023-4848-afe7-2454840bd321` | **Subject** | string |
| `235aa4cf-d20f-4dbb-ad1d-d03e5ff5f13e` | **Body** | code-editor (HTML or plain text) |
| `5330da65-bd38-4419-88c7-93136bdb6dd9` | **Map attachment** | `file`, `isList=true`, dataTypeId `10c6ac59-3929-49e6-99dc-121212121219` (see section 4) |
| `3fdba8f7-75b5-4350-9d85-b542f8e5a73d` | **Body is Html** | check-box (`Value: null`/false = plain text; true = HTML) |

## 4. Attachment — bind a File-typed variable

Bind TabPropertyId **`5330da65-bd38-4419-88c7-93136bdb6dd9`** (Map attachment)
to a **File** flow variable.

- File DataType id = **`10c6ac59-3929-49e6-99dc-121212121219`**.
- The field is a **list** (`isList=true`), so a **`List<File>`** fits naturally;
  a **single `File`** variable also works.
- In the reference flow it is bound to variable **`mailList`** (a `List<File>`,
  `IsList=True`, DataType `10c6ac59-...121219`).
- **No inline / base64 content.** Files travel as **PROCESIO File variable
  references** — you build/obtain a File (e.g. via *Object To File*, *Export To
  CSV*, a download action) earlier in the flow and pass that variable here. The
  binding is `Variable:[{id:N, variableId:<file var>, attribute:null}]`,
  `Value:"<%N%>"`.

## 5. Dynamic recipient — bind a String variable

Bind TabPropertyId **`1def19eb-ec69-4a21-a756-4abec8ae3171`** (To) to a
**String** flow variable (DataType `0317bfee-b2f5-4bde-bfe8-121212121214`).

- **One recipient:** point the String variable at a single address.
- **Multiple recipients:** use **one String variable holding comma-joined
  addresses** (NOT a List). In the reference flow the To field binds variable
  **`emailsConcatenated`**, which is built upstream by a **For-Each** over the
  recipient list feeding a **Concatenate** action (`concatEmails` +
  `concatCrtEmail` in the same flow).

## 6. Built-in dataTypeIds (for typing flow variables)

| Type | dataTypeId |
|---|---|
| String | `0317bfee-b2f5-4bde-bfe8-121212121214` |
| Text (rich) | `0317bfee-b2f5-4bde-bfe8-121212121221` |
| Boolean | `0317bfee-b2f5-4bde-bfe8-121212121210` |
| Integer / Guid | `0317bfee-b2f5-4bde-bfe8-121212121211` |
| File | `10c6ac59-3929-49e6-99dc-121212121219` |

---

## Reference — verbatim `Parameters[]` from the `notify` action

Taken as-is from the reference flow. Note the byte between `Notificare mesaj:`
and `<%1%>` in the Subject is **U+00A0 (non-breaking space)**, not a normal
space — preserved verbatim below.

```json
[
  {
    "TabPropertyId": "f9d5da64-bbc0-4d53-a0ad-6f948cc3ff05",
    "Variable": [],
    "Value": "2aacf4f1-310c-469f-80ef-394d6ab9582f"
  },
  {
    "TabPropertyId": "90d1ec9f-803c-42bc-bd8b-ca11e4ef116c",
    "Variable": [],
    "Value": "POSF Notification"
  },
  {
    "TabPropertyId": "1def19eb-ec69-4a21-a756-4abec8ae3171",
    "Variable": [
      {
        "id": 0,
        "variableId": "82957998-8f7f-46d6-819e-e370d9bc913d",
        "attribute": null
      }
    ],
    "Value": "<%0%>"
  },
  {
    "TabPropertyId": "30ba958f-0d83-4259-97b9-d64ce7282d83",
    "Variable": [],
    "Value": ""
  },
  {
    "TabPropertyId": "1b6fbfac-183a-481b-9e0d-d4e7cf5543fe",
    "Variable": [],
    "Value": ""
  },
  {
    "TabPropertyId": "9eeaf788-c023-4848-afe7-2454840bd321",
    "Variable": [
      {
        "id": 1,
        "variableId": "50f8dbbe-ccc6-477b-9492-1544bb011d2d",
        "attribute": null
      }
    ],
    "Value": "Notificare mesaj: <%1%>"
  },
  {
    "TabPropertyId": "235aa4cf-d20f-4dbb-ad1d-d03e5ff5f13e",
    "Variable": [],
    "Value": "Hello,

The message body goes here. Line breaks in a plain-text body are literal \r\n sequences inside the JSON string, not real newlines.

Regards,
The team"
  },
  {
    "TabPropertyId": "5330da65-bd38-4419-88c7-93136bdb6dd9",
    "Variable": [
      {
        "id": 2,
        "variableId": "3b45476e-b634-4e05-9fb5-c7ac521615ed",
        "attribute": null
      }
    ],
    "Value": "<%2%>"
  },
  {
    "TabPropertyId": "3fdba8f7-75b5-4350-9d85-b542f8e5a73d",
    "Variable": [],
    "Value": null
  }
]
```

How the example binds each field (resolved against the flow's `Variables[]`):

| TabPropertyId | Field | Binding |
|---|---|---|
| `f9d5da64-...ff05` | SMTP credentials | literal credential GUID `2aacf4f1-310c-469f-80ef-394d6ab9582f` |
| `90d1ec9f-...116c` | From (Display Name) | literal `"POSF Notification"` |
| `1def19eb-...3171` | **To** | `<%0%>` -> var `emailsConcatenated` (String, comma-joined) |
| `30ba958f-...2d83` | Cc | empty |
| `1b6fbfac-...543fe` | Bcc | empty |
| `9eeaf788-...d321` | Subject | `"Notificare mesaj: <%1%>"` -> var `messageType` (String) |
| `235aa4cf-...5f13e` | Body | literal multi-line plain-text body |
| `5330da65-...6dd9` | **Map attachment** | `<%2%>` -> var `mailList` (List<File>) |
| `3fdba8f7-...a73d` | Body is Html | `null` (unchecked -> plain-text body) |

---

## Corroborating flows (also use Send Email + Map attachment)

Same pattern verified across other production exports under
`tools/procesio/docs_info/Exports/`:

- **RINGHEL_RINGHEL 1** -> `HR_UC/Add CtrAndAnnex`
- **RINGHEL_RINGHEL 1** -> `PRC/Generate Contract`
- **OMS_v2_dev** -> `notification/lateDeliveryNote`
- **OMS_v2_dev** -> `utilitary/extractFile`
- **RINGHEL_Demo** -> `Party Invite/Send email to all attendees`

---

## Map attachment requires `list<File>` (verified live 2026-06-25)

The **"Map attachment"** field (`TabPropertyId 5330da65-bd38-4419-88c7-93136bdb6dd9`,
`type="file"`) is a **LIST of files** at runtime. Binding a **single** `File` variable
(model `10c6ac59-3929-49e6-99dc-121212121219`, `isList:false`) makes the designer show
**"Error: data type mismatch"** on the Send Email node and the email sends with **NO
attachment** — and the run STILL returns **status 50** (the mismatch does not fail the run,
so a green run is NOT proof the file attached). The designer's "+ Add Variable" tooltip on
that field literally reads **"Add Variable type=list <File>"**.

**Fix:** the bound variable must be **`isList:true`** (a `list<File>`). So:
- Declare the process input as `{model: "10c6ac59-…", isList: true}`.
- When running directly, pass the file DTO **inside a list**: `"briefFile": [ <fileDTO> ]`.
- A form file-upload control already holds a list, so a form→process attachment binds cleanly.

A **dynamic recipient** is a normal variable bind: `To` Value `<%0%>` + `Variable:[{id:0,
variableId: <recipientEmail var>}]` — verified delivering live to the entered address, with
the `list<File>` PDF attached (form → Process 2 brief → Process 3 email, AAT_ use case).
