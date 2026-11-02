# PROCESIO integration actions: SQL, SFTP, Call API, CURL, email (measured live 2026-10-29)

Learned while building a demo process that chains Execute Query, Call API, CURL, the SFTP
actions and Send Email, every step against a public test service. Each point below was
checked with a real run unless it says otherwise.

## Credentials

- **SQL credential (MySQL too) requires Protocol Type and Authentication Type.** The notes
  elsewhere call Protocol Type conditional on Server Type = MSSQL; the BE still refuses a
  MySQL credential without both (400, statusCode 113 "Required credentials fields should not
  be empty.", targets `Protocol Type` and `Authentication Type`). Send `Protocol Type: TCP`
  and `Authentication Type: Credentials Authentication`.
- **Password is required.** A public database whose login has NO password (many read-only
  science databases) cannot be reached: the credential refuses an empty Password (113), and a
  placeholder password fails the login. Pick a public server with a published password.
- **SFTP credential requires `Directory path`** (113 without it); `/` is fine.
- The credential test (`credential-create --dry-run`) opens a real connection from PROCESIO's
  cloud, so it is the quickest way to check a host is reachable from there. Outbound port 25
  timed out to a public test SMTP host; do not plan a demo on a port-25 relay.

## Public test services that work from PROCESIO's cloud

| Service | Use | Notes |
|---|---|---|
| `relational.fel.cvut.cz:3306` (MariaDB 10.6), user `guest`, password `ctu-relational` (published by the CTU relational dataset repository) | Execute Query on MySQL | Read-only: Execute Command gets "Access denied for user 'guest'". Sample databases such as `classicmodels` (orders, customers, products). |
| `test.rebex.net:22`, published demo login | SFTP list and download | Read-only. `/pub/example` holds small PNGs and a readme.txt. |
| `demo.wftpserver.com:2222`, published demo login | SFTP upload | Upload into `/upload` works; Create Folder, Rename and Delete File return false there. The folder is shared with the public, so do not list it on camera. |
| `https://httpbin.org/post` | Call API / CURL | Echoes body and headers. The response shows the caller's public IP (`origin`); mask it in a film. |

## Execute Query / Execute Command

- **Time Out is bounded 60 to 1800 seconds.** 30 is refused by FE (LIMIT_RANGE) and BE
  (151 "Value of Timeout: 30, is not within the allowed limits: [60, 1800]"). The tooltip
  only says "Minimum is 60".
- Binding a named parameter after the fact (the builder seeds the Parameters config tab
  empty): set the runtime parameter `73416282-…` (Execute Query) to
  `[{id: N, source: {value: "<%N%>", variable: [{id: N, variableId: <var>, attribute: null}]},
  destination: {value: "<name>", variable: []}}]` and the designer setting to
  `[{id: N, destination: "<name>", source: <var id>}]`, with N a slot no other parameter of
  the action uses (the Output already owns `<%0%>`). Checked: the run filters by the bound
  value.
- **Guid in a binary(16) column:** comparing it with the text form in quotes returns no rows
  and no error; comparing with the hex literal (`0x…`, no quotes) matches (measured on
  MariaDB with `UNHEX(REPLACE(guid,'-',''))`). GUID Converter gives both byte orders: `Hex` is
  the .NET order (`3f1a7c52-9b1d-…` -> `0x527C1A3F1D9B…`), `Hex (big-endian)` is text order
  (`0x3F1A7C529B1D…`). Use the big-endian form for bytes stored in text order (MySQL
  `UNHEX`, `UUID_TO_BIN` without swap), `Hex` for bytes written by .NET / SQL Server.

## SFTP actions

- **A refused operation returns Result false and the run goes on** (status 50, no action
  error) for Create Folder, Rename File/Folder and Delete File on a server that does not allow
  them. Upload File returns false when the target folder is missing. Check Result in the flow.
- Get File List: use the current template `c96e6905-…` (it has MaxFileNumber); the older
  `a56553a4-…0502` has the same name. Leave "Is it Recursive?" unset when building over the
  API: the builder does not resolve its `True`/`False` options and the FE flags
  VALUE_INTEGER. Output items are `{size, name, type, path}`; `size` is in KB (a 24 KB PNG
  lists as 24, the downloaded file says 24029 bytes).
- Download Bulk takes Get File List's output as is and returns a list of Files; its
  **Errors** output must be bound or the FE refuses the save (REQUIRED). SFTP Connections =
  parallel connections, 1 by default, 20 at most (tooltip).
- Moving a file between two servers = Download File on one credential, Upload File on the
  other. (Move File / Move Bulk take a "To SFTP credentials" field too; not run, both public
  servers refuse moves.)

## Call API, CURL, Send Email

- Call API with a raw JSON body `{"orders": <%1%>}` bound to an Execute Query output (list of
  objects) sends the list as a JSON array. Response Headers (json) holds the server's
  response headers. The runtime's User-Agent is `ProcesioRuntime/<version>`.
- CURL runs a curl command line (`curl -X POST … -H … -d '…'`, variables allowed in the
  text); Status gets the HTTP status (200), Result the parsed JSON body. The runtime's curl
  identifies as `curl/7.68.0`.
- Send Email with Map attachment bound to Download Bulk's list of Files delivered the files as
  attachments (checked in the receiving mailbox).
- Opening Call API's Configure Request side panel marks the process changed:
  Run greys out until Save + Validate. A film that opens panels must save and validate before
  it runs.
