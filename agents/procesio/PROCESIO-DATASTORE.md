# PROCESIO Data Store — build & use

**Data Store** is PROCESIO's user-defined dynamic-table feature: a tenant defines a
typed table (columns backed by a data model) and reads/writes its rows. It is
API-first, it surfaces as a **Process Designer action**, and it can be triggered from a
**form** — the same operation reachable three ways over one service.

## The model (know this before building)

- A data store = **metadata** (name + typed columns) + **rows**. Rows are JSON objects
  keyed by **column display name**, never the internal alias. Values are arbitrary JSON.
- **Primary-key columns** identify a row for update/delete. Four system columns are
  read-only and managed by the platform (`CREATED_ON`, `UPDATED_ON`, and the created/
  updated user ids).
- Two **permission entities** gate it: `DataStoreSchema` (create/alter/drop the table)
  and `DataStoreRows` (read/write rows + CSV). A user may hold one without the other.

**When to use it.** Reach for a Data Store when a process needs a small, tenant-owned,
queryable table it can also read/write from a form (a lookup list, a queue, a
submissions log). Prefer a **data model** (data type) for the *shape* of a variable, and
an **external DB action** (Execute Query/Command over a DB credential) when the data
already lives in a real database you own.

## Tool actions (`procesio datastore-*`)

Metadata: `datastore-create` / `-update` / `-modify-column` / `-delete` / `-get` /
`-list` / `-list-restricted` / `-from-data-model` / `-from-json` / `-get-data-model`.
Rows: `datastore-get-rows` (paged read with filters/sort), `-add-rows`, `-update-row`,
`-delete-rows`. CSV jobs: `datastore-export-start` / `-export-download` /
`-import-start` / `-import-failures`.

- **Reads: `POST …/rows/filter`** — **pagination on the query string**
  (`?pageNumber=&pageItemCount=`), body a RECURSIVE filter tree + sort:
  `{filter:{id,logic(0/1/2),items:[{id,type(1 condition|2 group),logic,condition:{id,column,
  operator,value,auxValue?}}]}, sort:[{column,direction(1 asc|2 desc)}]}` (no body = read
  all). `datastore-get-rows` builds this from `--filters '[{column,operator,value}]'`
  (+`--logic and|or`) or takes a raw `--filter`/`--body`. Operators are `QueryOperators`
  (0–20); pass a name (`Equals`,`Contains`,`Between`,`In`,`IsNull`,…) or number.
- **Update = `{values:{…}, filter:<tree>}`; delete = `{filter:<tree>}`** — a **non-empty
  filter is mandatory** on both (there is no key-array form). `datastore-update-row`
  takes `--values` + `--filter/--filters`; `datastore-delete-rows` takes `--filter/--filters`.
- Row dicts are keyed by **display name** everywhere (add/update/delete).

## Process Designer — the "Data Store" action

A native **`Data Store`** node runs one operation against a store. Operation is
`DataStoreOperationType` shown as **SELECT / INSERT / UPDATE / DELETE**
(SelectRows=1 / InsertRows=2 / UpdateRows=3 / DeleteRows=4). Its inputs use a dedicated
FE mapper component (`Data_Store_Mapper`) to bind the store id, the operation, and the
Set-Values / Match-Where maps. It is a platform (native) action dispatched by
`IsProcesio`, so there is **no code-visible action GUID** — resolve it by name from the
live action catalog (`procesio list-actions-catalog`) when authoring a flow, and refresh
the tool's bundled catalog from `/api/Actions` after a platform release.

## Forms — the Data Store trigger

A form element can trigger a Data Store operation the same way it triggers a process
(RUN_PROCESS). The event action is **`RUN_DATA_STORE_OPERATION`**; wire it surgically
with `procesio form-set-element-event --action RUN_DATA_STORE_OPERATION --data-store-id
<id> --operation READ|ADD|UPDATE|DELETE` (or in a full form rebuild via a control event
`do: datastore`). Config shape: `{dataStoreId, operation, inputMap, outputMap, filters?,
areFiltersConfigured?}`. **Filters apply to every operation except ADD.** The form
runtime calls the anonymous `api/Form/dataStore/{id}/rows(/filter)` endpoints with the
form context in headers — the form does not need the tenant's DataStore permissions.

## Verify (never call it done on compile)

Round-trip a store end to end: create (from-json is quickest), add rows, read them back
with a filter, update one by its PK, delete it — asserting `affectedRows` each step and
that the filtered read returns exactly the rows you expect. Then build a process with a
Data Store SELECT node and run it, and (if a form is in scope) render the form and fire
the trigger. See the build-and-test playbook, forms section.
