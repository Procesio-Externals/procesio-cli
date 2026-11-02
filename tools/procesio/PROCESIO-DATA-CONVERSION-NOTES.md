# JSON, XML, HTML, encoding, hashing, encryption and generators: measured behaviour

Live runs, 2026-10 (production), every statement below checked with a real process run. The public docs pages for most of
these actions say "Coming soon", so this is the reference. Names: the action list shows the template names (`String To
JSON`, `Mapper`, `Sanitizer`, `Object To String`), not the older labels some docs and the palette tree use (`Parse Json`,
`XML Mapper`, `Html Sanitize`, `ToString`).

## Where they live in the action list

- **JSON**: Extract Objects, File To JSON, Key Value, String To JSON, Is Valid.
- **XML**: Mapper, Update, Processor, Builder, Is Valid.
- **HTML**: Is Valid, Sanitizer, HTML Manipulation.
- **Converters**: JSON To XML, XML To JSON, HTML To JSON, JSON To HTML, HTML To PDF, Object To String; sub-folder
  **Cryptographic**: Encrypt To AES256, Decrypt From AES256, Hash, Hash Mac.
- **Base64**: File To Base64, Base64 To File, Base64 To String, String To Base64.
- **Utilitary**: Generate GUID, GUID Converter, Generate Integer, Generate String.

## JSON

- **String To JSON** (`Text` -> `Json` / `Json List`): a text holding an object fills `Json` and leaves `Json List` null;
  a text holding an array fills `Json List` and leaves `Json` null.
- **Key Value** (`JSON list to process`, `Key attribute`, `Value attribute`, `Pivot data`, `Output JSON`): input
  `[{"name":"channel","value":"web"},{"name":"priority","value":"high"}]` with key `name`, value `value`:
  - Pivot data off: the same list with the fields renamed, `[{"key":"channel","value":"web"},{"key":"priority","value":"high"}]`.
  - Pivot data on: one object, `{"channel":"web","priority":"high"}`.
- A `{var, path}` binding into an untyped `json` variable is refused by the back end (`Error converting value "<field>" to
  type 'System.Guid'` on `attribute.attributeId`): paths work only into a data model's attributes. Use Extract Objects, a
  model, or separate variables.

## XML

- **JSON To XML** wraps the object in `<root>`; each field becomes a tag; each item of a list becomes a repeated tag with
  the list's name (`items: [..2..]` -> two `<items>`). The output is indented over several lines. A top-level array goes to
  `List of Xml` instead of `Xml`. HTML inside a value is escaped (`&lt;p&gt;`).
- **XML To JSON** keeps the root (`{"root": {...}}`) and returns every value as a string (`"total": "149.9"`, `"qty": "2"`):
  XML has no number type.
- **Mapper** (`Input XML` or `Input XML file`, `XPath Expression`): one match -> `The resulting value` (typed: `149.9`
  came back as a number), `Is List` false; several matches -> `The resulting list of values`, `Is List` true.
  `Is List` is a REQUIRED output in the designer (a save without it is refused).
- **Update** (`XPath expression` = the PARENT, `XML tag`, `New value`): updates the tag under that parent, or adds it when
  missing. `/root` + `status` + `sent` appended `<status>sent</status>`. Its string output is compact (one line).
- **Processor** (`Input Template XML` = any XML, `Input JSON` = a list of `{xpath, xmlTag, newValue}`, `Input Prefix` =
  namespace map) and **Builder** (`Template XML`, `Builder Specs` = the same list, `Prefixes`):
  - Processor UPDATES a tag that already exists with a value (`<Number>1</Number>` -> `A-1042`); Builder always ADDS a new
    tag (the same spec gave `<Number>1</Number><Number>A-1042</Number>`). With `newValue: ""` both add, which is how
    repeating lines are built: `{"/Lines","Line",""}` then `{"/Lines/Line[last()]","Sku","BK-01"}`, twice, gives two
    `<Line><Sku>..</Sku></Line>`.
  - An xpath that matches nothing (a missing parent, a wrong root) finishes the run as SUCCESS with a null output. No error.
  - Namespaces: template `<Invoice xmlns:cbc="urn:cbc">`, prefixes `{"cbc":"urn:cbc"}`, tag `cbc:ID` -> `<cbc:ID>` works
    in both. With no namespaces pass `{}`: an empty prefix field fails Builder with
    `Error reading JToken from JsonReader. Path '', line 0, position 0.`
  - Specs must be a JSON array (`Error reading JArray from JsonReader...` on an object). Extra keys tried for attributes
    (`attributes`, `attribute`/`attributeValue`) are ignored: no attribute support found.
  - The docs' XPath overview says Builder "helps you construct XPath expressions": it does not, it builds XML.
- The process builder refuses a code-editor value (`Input JSON`, `Builder Specs`) written on one long line: lay the JSON
  out over lines (`json.dumps(..., indent=2)`).

## HTML

- **Sanitizer**: `<p onclick="track()">Please gift wrap it</p><script>alert('hi')</script>` -> `<p>Please gift wrap it</p>`
  (event attribute and script removed). `Encode the result ?` ticked -> the cleaned HTML escaped, `&lt;p&gt;...&lt;/p&gt;`.
- **HTML Manipulation** (`HTML Input`, `XPath Expression`, `HTML Attribute`, `New Value`): `//a` + `href` + a URL set the
  link's href.
- **HTML To JSON** returns a node tree: `{"NodeType":"Document","Tag":null,"Text":null,"Attributes":{},"Children":[{"NodeType":
  "Element","Tag":"p","Text":"...","Children":[{"NodeType":"Text","Tag":"#text",...}]}]}`.
- **JSON To HTML** accepts ONLY that tree (round trip is exact). Any other JSON, object or array, fails the run with
  `Couldn't convert JSON to HTML. Make sure JSON is in the expected format.` It does not build a table from data.

## Converters, Base64, hashing, encryption

- **Object To String**: a json object -> its compact JSON text.
- **String To Base64** / **Base64 To String**: UTF-8, round trip exact.
- **Hash** (`Input String` or `Input File`, file wins; algorithms MD5, SHA1, SHA256, SHA3_256/384/512, SHA384, SHA512):
  lowercase hex, identical to Python `hashlib`.
- **Hash Mac** needs a credential of template **HashMac Key** (`70707070-0001-0000-0000-aaaaaaaaaaaa`, one password field
  "HashMac Key"); `credential-create` stores it, and its connection test answers `CREDENTIALS_TYPE_NOT_SUPPORTED` (normal,
  the type has no test). Settings sit in the "Configure Hash" side panel (HMACMD5 ... HMACSHA512). Output: lowercase hex,
  identical to Python `hmac.new(key, msg, sha256)`.
- **Encrypt To AES256** / **Decrypt From AES256**: AES-256-CBC with PKCS7 padding, key and IV taken as UTF-8 text
  (identical to the `cryptography` package). The key must be exactly 32 characters (`Input Error: Secret Key must be 32
  characters long!`) and the IV exactly 16 (`Input Error: IV must be 16 characters long!`). Encrypt outputs Hex
  (uppercase) and Base64; BOTH outputs are required bindings in the designer. Decrypt's `Format` (base64/hex) names the
  input's encoding. There is no credential option: key and IV are text or variables.

## Generators

- **Generate GUID** -> a v4 GUID. **Generate String** (`Length` + Lowercase / Uppercase / Numeric / Special check boxes)
  -> e.g. 8 characters with Uppercase + Numeric: `AA1NS2RQ`. **Generate Integer** (`Lower Limit`, `Upper Limit`) -> a
  random integer in the range (inclusiveness of the upper limit not measured).

## Designer findings around these actions

- The Run dialog cannot show a default of a JSON LIST input variable: it renders `[object Object],[object Object]` and
  then refuses it with "Not a valid JSON". Keep such defaults in an internal variable, or type the JSON in the dialog.
- After a save with every required setting filled, Run is enabled directly; a process saved invalid shows "Please validate
  the process" on the Run button.
- Connection routing follows the nodes' relative positions (ports are not stored per side): a "snake" layout (rows
  alternating direction, a short vertical drop at each row end) draws cleanly, while rows that all run left to right draw
  each row change as a line crossing back through the row.
