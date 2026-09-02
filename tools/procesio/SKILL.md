---
name: procesio
description: PROCESIO low-code automation platform (procesio.app/.com). Full 1:1 coverage of the Web API: every endpoint is an action (<method>-<path> names) plus ergonomic shortcuts, a generic `request`, and an `export` (.procesio Transport). Dual auth (API key per-workspace, or username/password cookie session) with a multi-credential profile store; --profile picks the account/key, --workspace-id sets the…
---

# procesio

PROCESIO low-code automation platform (procesio.app/.com). Full 1:1 coverage of the Web API: every endpoint is an action (<method>-<path> names) plus ergonomic shortcuts, a generic `request`, and an `export` (.procesio Transport). Dual auth (API key per-workspace, or username/password cookie session) with a multi-credential profile store; --profile picks the account/key, --workspace-id sets the active workspace. Multi-environment: named <Client>-<ENV> environments (Internal-PROD/QA/DEV built in, client envs added at runtime) each carry their own host URLs and bound credentials; switch the default with set-environment or per-call with --environment (unbound credentials stay on Internal-PROD).

## How to call it

```bash
python scripts/run-tool.py procesio <action> [--args]
# e.g. procesio list-processes   (run: procesio run-process --id <id> --payload '{...}')
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

**Start with `run-process`.**

## Credentials

Stored in the OS credential store, never in files. Missing ones are reported by `python scripts/list-tools.py`.

- `agents-and-tools:procesio:credentials` — JSON index of stored credential profiles. Profiles live under agents-and-tools:procesio:cred-<name> (API keys and username/password accounts). Manage with…
- `agents-and-tools:procesio:form-code-key` — AES passphrase used to encrypt a form's Data.code blob (the designer's 'Switch to code' CSS + JavaScript). Required only to build forms WITH form-level CSS/JS;…

## Actions

### add

| action | required args | what it does |
|---|---|---|
| `add-credential` | `--name`, `--type` | Store a new credential profile (apikey or userpass) in Credential Manager. |
| `add-environment` | `--name`, `--web-base`, `--app-base`, `--forms-base` | Add a client environment (<Client>-<ENV> + its host URLs) to the registry. |

### check

| action | required args | what it does |
|---|---|---|
| `check-auth` | — | Hit a live read endpoint to verify the profile authenticates. |

### create

| action | required args | what it does |
|---|---|---|
| `create-schedule` | `--payload` | Create a schedule (POST /api/Schedules) from a JSON --payload; --cron/--timezone sets a crontab recurrence. |

### credential

| action | required args | what it does |
|---|---|---|
| `credential-create` | — | Create a PROCESIO credential from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO. |
| `credential-delete` | `--id` | Delete a resource by id (DELETE /api/Credentials/{id}). |
| `credential-edit` | `--id` | Edit a PROCESIO credential to a desired-state config (--id required). --dry-run to preview the DTO. |
| `credential-get` | `--id` | Get one resource by id (GET /api/Credentials/{id}). |
| `credential-test` | — | Live-test a credential config without saving it (POST /api/Credentials/test). |

### customaction

| action | required args | what it does |
|---|---|---|
| `customaction-delete` | `--id` | Uninstall a custom action (DELETE /api/actions/{id}). |
| `customaction-list` | — | List the workspace's custom actions (--all for the full catalog). |
| `customaction-test` | — | Test a custom action (POST /api/Actions/test). |
| `customaction-upload` | `--file` | Install a custom action from a .nupkg package (POST /api/actions multipart). |

### datastore

| action | required args | what it does |
|---|---|---|
| `datastore-add-rows` | `--id`, `--rows` | Insert rows (POST /api/DataStore/{id}/rows) from a JSON --rows array. |
| `datastore-create` | `--payload` | Create a data store (POST /api/DataStore) from a JSON --payload. |
| `datastore-delete` | `--id` | Delete a data store (DELETE /api/DataStore/{id}). |
| `datastore-delete-rows` | `--id` | Delete rows (DELETE /api/DataStore/{id}/rows) a --filter/--filters selects (filter mandatory). |
| `datastore-export-download` | `--id`, `--job-id`, `--out` | Download a finished CSV export (GET /api/DataStore/{id}/export-download/{jobId}) to --out. |
| `datastore-export-start` | `--id` | Start a CSV export job (POST /api/DataStore/{id}/export-start). |
| `datastore-from-data-model` | `--payload` | Create a data store from an existing data model (POST /api/DataStore/from-data-model). |
| `datastore-from-json` | `--payload` | Create a data store from raw JSON / a JSON URL (POST /api/DataStore/from-json). |
| `datastore-get` | `--id` | Get a data store's metadata (GET /api/DataStore/{id}). |
| `datastore-get-data-model` | `--id` | Get the data model backing a data store (GET /api/DataStore/{id}/data-model). |
| `datastore-get-rows` | `--id` | Read rows (POST /api/DataStore/{id}/rows/filter): paging on the query string, filter tree + sort in the body (--filters/--filter/--sort). |
| `datastore-import-failures` | `--id`, `--job-id` | Get a CSV import job's failures (GET /api/DataStore/{id}/import-failures/{jobId}). |
| `datastore-import-start` | `--id`, `--file` | Start a CSV import job (POST /api/DataStore/{id}/import-start) from a --file. |
| `datastore-list` | — | List data stores (GET /api/DataStore). |
| `datastore-list-restricted` | — | List data stores the caller is restricted to (GET /api/DataStore/restricted). |
| `datastore-modify-column` | `--id`, `--payload` | Modify one column (PATCH /api/DataStore/{id}/column) from --payload. |
| `datastore-update` | `--payload` | Update a data store's metadata (PUT /api/DataStore) from --payload (include id). |
| `datastore-update-row` | `--id` | Update rows (PUT /api/DataStore/{id}/rows) — set --values on rows a --filter/--filters selects (filter mandatory). |

### datatype

| action | required args | what it does |
|---|---|---|
| `datatype-add-attribute` | `--id`, `--name`, `--data-type` | Add one attribute to a model — compiles it; a model-typed attr inlines the child + keeps it reusable. |
| `datatype-change-to-public` | `--root-id`, `--id` | Promote a private inner model (from fromJson) to public so it's reusable (POST /api/DataTypes/changeToPublic). |
| `datatype-clone` | `--root-id`, `--id` | Clone an inner data model (POST /api/DataTypes/clone). |
| `datatype-create` | — | Create a PROCESIO datatype from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO. |
| `datatype-delete` | `--id` | Delete a data model (DELETE /api/DataTypes/{id}). |
| `datatype-delete-attribute` | `--id`, `--attribute` | Delete one attribute (DELETE /api/dataTypes/attribute/{id}/{attrId}). |
| `datatype-edit` | `--id` | Edit a PROCESIO datatype to a desired-state config (--id required). --dry-run to preview the DTO. |
| `datatype-edit-attribute` | `--id`, `--attribute` | Edit one attribute (PUT /api/dataTypes/attribute/{id}). |
| `datatype-get` | `--id` | Get a data model with its attributes (GET /api/DataTypes/{id}). |

### delete

| action | required args | what it does |
|---|---|---|
| `delete-actions-by-id` | `--id` | DELETE /api/Actions/{id} [Actions] - Permission required: CustomActions.Delete |
| `delete-actions-folders-by-id` | `--id` | DELETE /api/Actions/folders/{id} [Actions] - Permission required: ProcessDesigner.Delete |
| `delete-actions-templates-by-id` | `--id` | DELETE /api/Actions/templates/{id} [Actions] - Permission required: ProcessDesigner.Delete |
| `delete-apikey` | — | DELETE /api/ApiKey [ApiKey] - Permission required: ApiKey.Delete |
| `delete-apikey-by-id` | `--id` | DELETE /api/ApiKey/{id} [ApiKey] - Permission required: ApiKey.Delete |
| `delete-authentication-logout` | — | DELETE /api/Authentication/logOut [Authentication] - Permission required: None |
| `delete-by-masterworkspaceurl-by-workspaceurl-by-entityurl` | `--masterWorkspaceUrl`, `--workspaceUrl`, `--entityUrl` | DELETE /{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl} [CustomUrlLaunch] |
| `delete-by-tinyurl` | `--tinyUrl` | DELETE /{tinyUrl} [TinyUrlLaunch] |
| `delete-credentials-by-id` | `--id` | DELETE /api/Credentials/{id} [Credentials] - Permission required: Credentials.Delete |
| `delete-customurl-formtemplate-by-id` | `--id` | DELETE /api/CustomUrl/FormTemplate/{id} [CustomUrlForm] - Permission required: FormTemplate.Delete |
| `delete-customurl-masterworkspace-by-id` | `--id` | DELETE /api/CustomUrl/MasterWorkspace/{id} [CustomUrlMaster] - Permission required: MasterWorkspace.Update |
| `delete-customurl-webhook-by-id` | `--id` | DELETE /api/CustomUrl/Webhook/{id} [CustomUrlWebhook] - Permission required: Webhook.Delete |
| `delete-customurl-workspace-by-id` | `--id` | DELETE /api/CustomUrl/Workspace/{id} [CustomUrlWorkspace] - Permission required: Workspace.Delete |
| `delete-datatypes-attribute-by-rootdatatypeid-by-attributeid` | `--rootDataTypeId`, `--attributeId` | DELETE /api/DataTypes/attribute/{rootDataTypeId}/{attributeId} [DataTypes] - Permission required: DataModels.Update |
| `delete-datatypes-by-id` | `--id` | DELETE /api/DataTypes/{id} [DataTypes] - Permission required: DataModels.Delete |
| `delete-documenttemplate-by-id` | `--id` | DELETE /api/DocumentTemplate/{id} [DocumentTemplate] - Permission required: DocumentDesigner.Delete |
| `delete-form` | — | DELETE /api/Form [Form] - Permission required: FormInstance.Delete |
| `delete-form-by-id` | `--id` | DELETE /api/Form/{id} [Form] - Permission required: FormInstance.Delete |
| `delete-formapplication-by-id` | `--id` | DELETE /api/FormApplication/{id} [FormApplication] - Permission required: FormTemplate.Delete |
| `delete-formtemplate-by-id` | `--id` | DELETE /api/FormTemplate/{id} [FormTemplate] - Permission required: FormTemplate.Delete |
| `delete-projects-by-id` | `--id` | DELETE /api/Projects/{id} [ProcessTemplate] - Permission required: ProcessDesigner.Delete |
| `delete-projects-instances-by-id-dataretention` | `--id` | DELETE /api/Projects/instances/{id}/dataRetention [ProcessInstance] - Permission required: ProcessInstance.Delete |
| `delete-schedule` | `--id` | Delete a schedule (DELETE /api/Schedules/{id}). |
| `delete-schedules-by-scheduleid` | `--scheduleId` | DELETE /api/Schedules/{scheduleId} [Schedules] - Permission required: Schedule.Delete |
| `delete-userpreferences` | — | DELETE /api/UserPreferences [UserPreferences] - Permission required: None |
| `delete-webhooks-by-webhookid` | `--webhookId` | DELETE /api/Webhooks/{webhookId} [Webhooks] - Permission required: Webhook.Delete |
| `delete-webhooks-by-webhookid-undo` | `--webhookId` | DELETE /api/Webhooks/{webhookId}/undo [Webhooks] - Permission required: Webhook.Update |
| `delete-webhooks-launch-by-id` | `--id` | DELETE /api/Webhooks/launch/{id} [WebhookLaunch] - Permission required: None |
| `delete-workspace-by-workspacetodelete` | `--workspaceToDelete` | DELETE /api/Workspace/{workspaceToDelete} [Workspace] - Permission required: MasterWorkspace.Delete |
| `delete-workspace-invite-by-id` | `--id` | DELETE /api/Workspace/invite/{id} [Workspace] - Permission required: Workspace.Update |

### document

| action | required args | what it does |
|---|---|---|
| `document-create` | — | Create a PROCESIO document from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO. |
| `document-delete` | `--id` | Delete a resource by id (DELETE /api/DocumentTemplate/{id}). |
| `document-edit` | `--id` | Edit a PROCESIO document to a desired-state config (--id required). --dry-run to preview the DTO. |
| `document-get` | `--id` | Get one resource by id (GET /api/DocumentTemplate/{id}). |
| `document-list` | — | List documents (GET /api/DocumentTemplate). |

### duplicate

| action | required args | what it does |
|---|---|---|
| `duplicate-process` | `--id` | Duplicate a process (POST /api/Projects/{id}/duplicate) and return the copy's id + designer URL (found by diffing the workspace's project list).… |

### export

| action | required args | what it does |
|---|---|---|
| `export` | — | Export components to a .procesio file (Transport). Accepts names/ids/all per type; credentials excluded by default; --dry-run to preview the selection. |

### file

| action | required args | what it does |
|---|---|---|
| `file-download` | — | Download a flow-instance file (Generate-Document output etc.) via the header-based GET /api/File/download. |

### flow

| action | required args | what it does |
|---|---|---|
| `flow-lint` | `--id` | Designer-layer 'Process Errors' lint on a live flow (the check that blocks designer SAVE, which POST /Projects/validate does NOT catch): stale subprocess… |

### form

| action | required args | what it does |
|---|---|---|
| `form-add-element` | `--id` | Add one or more controls to a LIVE form (authoring-config elements), splicing them into Data.elements AND the data model without regenerating what is already… |
| `form-create` | — | Create a PROCESIO form from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO. |
| `form-delete` | `--id` | Delete a resource by id (DELETE /api/FormTemplate/{id}). |
| `form-duplicate` | `--id` | POST /api/FormTemplate/{id}/duplicate. |
| `form-edit` | `--id` | Edit a PROCESIO form to a desired-state config (--id required). --dry-run to preview the DTO. |
| `form-get` | `--id` | Get one resource by id (GET /api/FormTemplate/{id}). |
| `form-get-code` | `--id` | Read a form's global CSS + JavaScript (decrypts Data.code). |
| `form-get-element` | `--id`, `--element` | Read one element's configs from a live form (id or name). |
| `form-get-element-events` | `--id`, `--element` | List one element's event handlers, by trigger. |
| `form-list` | — | List forms (GET /api/FormTemplate/all/basic). |
| `form-set-code` | `--id` | Set a form's global CSS + JavaScript in place (surgical: only Data.code changes; omitted side is preserved; returns the previous code). |
| `form-set-element-config` | `--id`, `--element` | Set one element's plain configs in place (surgical: only that element's config values change, ids preserved; returns the previous values). Event configs go… |
| `form-set-element-event` | `--id`, `--element`, `--on`, `--action` | Wire one element's trigger to RUN_PROCESS / RUN_JAVASCRIPT / RUN_DATA_STORE_OPERATION in place (surgical: only that element's event config changes;… |
| `form-update` | `--id` | Safely save an arbitrary change to a LIVE form: GET it, deep-merge a --data patch into its Data (and/or override --name/--status/--state/--is-private), then… |

### get

| action | required args | what it does |
|---|---|---|
| `get-actions` | — | GET /api/Actions [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-by-id` | `--id` | GET /api/Actions/{id} [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-category-by-category` | `--category` | GET /api/Actions/category/{category} [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-event-by-id` | `--id` | GET /api/Actions/event/{id} [Actions] - Permission required: ProcessDesigner.Update |
| `get-actions-folders` | — | GET /api/Actions/folders [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-folders-by-id` | `--id` | GET /api/Actions/folders/{id} [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-node` | — | GET /api/Actions/node [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-restricted` | — | GET /api/Actions/restricted [Actions] - Permission required: ProcessInstance.Read |
| `get-actions-templates-by-id` | `--id` | GET /api/Actions/templates/{id} [Actions] - Permission required: ProcessDesigner.Read |
| `get-actions-test-by-id` | `--id` | GET /api/Actions/test/{id} [Actions] - Permission required: ProcessDesigner.Update |
| `get-analytics-executionenvironment-concurrency` | — | GET /api/analytics/executionEnvironment/concurrency [Resources] - Permission required: MasterWorkspace.Read |
| `get-analytics-executionenvironment-topprocesses` | — | GET /api/analytics/executionEnvironment/topProcesses [Resources] - Permission required: MasterWorkspace.Read |
| `get-apikey` | — | GET /api/ApiKey [ApiKey] - Permission required: ApiKey.Read |
| `get-by-masterworkspaceurl-by-workspaceurl-by-entityurl` | `--masterWorkspaceUrl`, `--workspaceUrl`, `--entityUrl` | GET /{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl} [CustomUrlLaunch] |
| `get-by-tinyurl` | `--tinyUrl` | GET /{tinyUrl} [TinyUrlLaunch] |
| `get-credentials` | — | GET /api/Credentials [Credentials] - Permission required: Credentials.Read |
| `get-credentials-authorize-by-id` | `--id` | GET /api/Credentials/authorize/{id} [Credentials] - Permission required: Credentials.Update |
| `get-credentials-by-id` | `--id` | GET /api/Credentials/{id} [Credentials] - Permission required: Credentials.Read |
| `get-credentials-by-id-restricted` | `--id` | GET /api/Credentials/{id}/restricted [Credentials] - Permission required: ProcessInstance.Read |
| `get-credentials-count` | — | GET /api/Credentials/count [Credentials] - Permission required: Credentials.Read |
| `get-credentials-list-by-typeid` | `--typeId` | GET /api/Credentials/list/{typeId} [Credentials] - Permission required: Credentials.Read |
| `get-credentials-list-by-typeid-count` | `--typeId` | GET /api/Credentials/list/{typeId}/count [Credentials] - Permission required: Credentials.Read |
| `get-credentials-list-by-typeid-restricted` | `--typeId` | GET /api/Credentials/list/{typeId}/restricted [Credentials] - Permission required: ProcessDesigner.Read |
| `get-credentials-types` | — | GET /api/Credentials/types [Credentials] - Permission required: Credentials.Read |
| `get-credentials-types-by-id` | `--id` | GET /api/Credentials/types/{id} [Credentials] - Permission required: Credentials.Read |
| `get-credentials-verbs-by-templateid` | `--templateId` | GET /api/Credentials/verbs/{templateId} [Credentials] - Permission required: None |
| `get-customurl-formtemplate-by-id` | `--id` | GET /api/CustomUrl/FormTemplate/{id} [CustomUrlForm] - Permission required: FormTemplate.Read |
| `get-customurl-masterworkspace` | — | GET /api/CustomUrl/MasterWorkspace [CustomUrlMaster] - Permission required: MasterWorkspace.Read |
| `get-customurl-webhook-by-id` | `--id` | GET /api/CustomUrl/Webhook/{id} [CustomUrlWebhook] - Permission required: Webhook.Read |
| `get-customurl-workspace` | — | GET /api/CustomUrl/Workspace [CustomUrlWorkspace] - Permission required: Workspace.Read |
| `get-customurl-workspace-master` | — | GET /api/CustomUrl/Workspace/master [CustomUrlWorkspace] - Permission required: Workspace.Read |
| `get-datatypes` | — | GET /api/DataTypes [DataTypes] - Permission required: DataModels.Read |
| `get-datatypes-by-id-by-type` | `--id`, `--type` | GET /api/DataTypes/{id}/{type} [DataTypes] - Permission required: DataModels.Read |
| `get-datatypes-by-value` | `--value` | GET /api/DataTypes/{value} [DataTypes] - Permission required: DataModels.Read |
| `get-datatypes-count` | — | GET /api/DataTypes/count [DataTypes] - Permission required: DataModels.Read |
| `get-datatypes-primary` | — | GET /api/DataTypes/primary [DataTypes] - Permission required: None |
| `get-datatypes-primary-count` | — | GET /api/DataTypes/primary/count [DataTypes] - Permission required: None |
| `get-datatypes-procesio` | — | GET /api/DataTypes/procesio [DataTypes] - Permission required: None |
| `get-datatypes-procesio-count` | — | GET /api/DataTypes/procesio/count [DataTypes] - Permission required: None |
| `get-datatypes-restricted` | — | GET /api/DataTypes/restricted [DataTypes] - Permission required: None |
| `get-documenttemplate` | — | GET /api/DocumentTemplate [DocumentTemplate] - Permission required: DocumentDesigner.Read |
| `get-documenttemplate-by-id` | `--id` | GET /api/DocumentTemplate/{id} [DocumentTemplate] - Permission required: DocumentDesigner.Read |
| `get-documenttemplate-by-id-restricted` | `--id` | GET /api/DocumentTemplate/{id}/restricted [DocumentTemplate] - Permission required: ProcessInstance.Read |
| `get-documenttemplate-restricted` | — | GET /api/DocumentTemplate/restricted [DocumentTemplate] - Permission required: ProcessDesigner.Read |
| `get-file-download` | — | GET /api/File/download [File] - Permission required: ProcessInstance.Read |
| `get-file-download-action-event` | — | GET /api/File/download/action-event [File] - Permission required: ProcessDesigner.Read |
| `get-file-download-schedule` | — | GET /api/File/download/schedule [File] - Permission required: Schedule.Read |
| `get-file-download-testaction` | — | GET /api/File/download/testAction [File] - Permission required: ProcessDesigner.Read |
| `get-form-assigned` | — | GET /api/Form/assigned [Form] - Permission required: FormInstance.Read |
| `get-form-by-id` | `--id` | GET /api/Form/{id} [Form] - Permission required: FormInstance.Read |
| `get-form-by-pid-all` | `--pid` | GET /api/Form/{pid}/all [Form] - Permission required: FormInstance.Read |
| `get-form-by-pid-count` | `--pid` | GET /api/Form/{pid}/count [Form] - Permission required: FormInstance.Read |
| `get-form-chain-by-chainid` | `--chainId` | GET /api/Form/chain/{chainId} [FormChain] - Permission required: FormInstance.Read |
| `get-form-chain-by-formtemplateid-all` | `--formTemplateId` | GET /api/Form/chain/{formTemplateId}/all [FormChain] - Permission required: FormInstance.Read |
| `get-form-download` | — | GET /api/Form/download [FileForm] - Permission required: FormInstance.Read |
| `get-formapplication-all` | — | GET /api/FormApplication/all [FormApplication] - Permission required: FormTemplate.None |
| `get-formapplication-all-by-pid` | `--pid` | GET /api/FormApplication/all/{pid} [FormApplication] - Permission required: FormTemplate.None |
| `get-formapplication-all-filter` | — | GET /api/FormApplication/all/filter [FormApplication] - Permission required: FormTemplate.None |
| `get-formapplication-by-id` | `--id` | GET /api/FormApplication/{id} [FormApplication] - Permission required: FormTemplate.None |
| `get-formprocess-by-formtemplateid-by-processtemplateid` | `--formTemplateId`, `--processTemplateId` | GET /api/FormProcess/{formTemplateId}/{processTemplateId} [FormProcess] - Permission required: None |
| `get-formprocess-by-formtemplateid-by-processtemplateid-by-processinstanceid-variables` | `--formTemplateId`, `--processTemplateId`, `--processInstanceId` | GET /api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables [FormProcess] - Permission required: None |
| `get-formprocess-download` | — | GET /api/FormProcess/download [FileFormProcess] - Permission required: None |
| `get-formtemplate` | — | GET /api/FormTemplate [FormTemplate] - Permission required: FormTemplate.Read |
| `get-formtemplate-all-basic` | — | GET /api/FormTemplate/all/basic [FormTemplate] - Permission required: FormTemplate.None |
| `get-formtemplate-by-id` | `--id` | GET /api/FormTemplate/{id} [FormTemplate] - Permission required: FormTemplate.Read |
| `get-formtemplate-by-workspaceid-by-id` | `--workspaceId`, `--id` | GET /api/FormTemplate/{workspaceId}/{id} [FormTemplate] - Permission required: None |
| `get-formtemplate-processtemplate-by-id` | `--id` | GET /api/FormTemplate/processTemplate/{id} [FormTemplate] - Permission required: FormTemplate.Read |
| `get-formtemplate-processtemplate-list` | — | GET /api/FormTemplate/processTemplate/list [FormTemplate] - Permission required: FormTemplate.Read |
| `get-instance-output` | `--id` | Get an instance's output (GET /api/Projects/instances/{id}/output). |
| `get-instance-status` | `--id` | Get an instance's status/variables (GET /api/Projects/instances/{id}/status). |
| `get-notifications` | — | GET /api/Notifications [Notifications] - Permission required: None |
| `get-process` | `--id` | Get one process by id (GET /api/Projects/{id}). |
| `get-process-payload` | `--id` | Get a process's input-variable payload shape for run-process. |
| `get-projects` | — | GET /api/Projects [ProcessTemplate] - Permission required: ProcessDesigner.Read |
| `get-projects-by-id` | `--id` | GET /api/Projects/{id} [ProcessTemplate] - Permission required: ProcessDesigner.Read |
| `get-projects-by-id-history` | `--id` | GET /api/Projects/{id}/history [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-by-id-instances` | `--id` | GET /api/Projects/{id}/instances [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-by-id-instances-by-instanceid-customresponse` | `--id`, `--instanceId` | GET /api/Projects/{id}/instances/{instanceId}/customResponse [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-by-id-instances-count` | `--id` | GET /api/Projects/{id}/instances/count [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-by-id-payload` | `--id` | GET /api/Projects/{id}/payload [ProcessTemplate] - Permission required: ProcessDesigner.Read |
| `get-projects-by-id-restricted` | `--id` | GET /api/Projects/{id}/restricted [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-by-id-restricted-schedules` | `--id` | GET /api/Projects/{id}/restricted/schedules [ProcessTemplate] - Permission required: Schedule.Read |
| `get-projects-by-id-used` | `--id` | GET /api/Projects/{id}/used [ProcessTemplate] - Permission required: ProcessDesigner.Read |
| `get-projects-count` | — | GET /api/Projects/count [ProcessTemplate] - Permission required: ProcessDesigner.Read |
| `get-projects-instances-by-id-output` | `--id` | GET /api/Projects/instances/{id}/output [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-instances-by-id-status` | `--id` | GET /api/Projects/instances/{id}/status [ProcessInstance] - Permission required: ProcessInstance.Read |
| `get-projects-notifications-by-flowid` | `--flowId` | GET /api/Projects/notifications/{flowId} [ProcessTemplate] - Permission required: ProcessDesigner.Read |
| `get-projects-restricted-schedules` | — | GET /api/Projects/restricted/schedules [ProcessTemplate] - Permission required: Schedule.Read |
| `get-resources-analytics-instances-by-id-details` | `--id` | GET /api/Resources/analytics/instances/{id}/details [Resources] - Permission required: ProcessInstance.Read |
| `get-resources-analytics-processes` | — | GET /api/Resources/analytics/processes [Resources] - Permission required: ProcessDesigner.Read |
| `get-resources-analytics-processes-by-id-details` | `--id` | GET /api/Resources/analytics/processes/{id}/details [Resources] - Permission required: ProcessDesigner.Read |
| `get-resources-used` | — | GET /api/Resources/used [Resources] - Permission required: Workspace.Read |
| `get-resources-used-subworkspaces` | — | GET /api/Resources/used/subWorkspaces [Resources] - Permission required: Workspace.Read |
| `get-resourcetrackingconfig` | — | GET /api/ResourceTrackingConfig [ResourceTrackingConfig] - Permission required: Workspace.Read |
| `get-schedule` | `--id` | Get one schedule by id (GET /api/Schedules/{id}). |
| `get-schedule-notifications` | `--id` | Get a schedule's notifications (GET /api/Schedules/notifications/{id}). |
| `get-schedules` | — | GET /api/Schedules [Schedules] - Permission required: Schedule.Read |
| `get-schedules-by-scheduleid` | `--scheduleId` | GET /api/Schedules/{scheduleId} [Schedules] - Permission required: Schedule.Read |
| `get-schedules-notifications-by-scheduleid` | `--scheduleId` | GET /api/Schedules/notifications/{scheduleId} [Schedules] - Permission required: Schedule.Read |
| `get-subscriptions` | — | GET /api/Subscriptions [Subscriptions] - Permission required: MasterWorkspace.Read |
| `get-subscriptions-by-subscriptionid` | `--subscriptionId` | GET /api/Subscriptions/{subscriptionId} [Subscriptions] - Permission required: MasterWorkspace.Read |
| `get-transport-export` | — | GET /api/Transport/export [Transport] - Permission required: Workspace.Admin |
| `get-userpermissions` | — | GET /api/UserPermissions [UserPermissions] - Permission required: None |
| `get-userpermissions-by-userid` | `--userId` | GET /api/UserPermissions/{userId} [UserPermissions] - Permission required: Workspace.Admin |
| `get-userpermissions-entities` | — | GET /api/UserPermissions/entities [UserPermissions] - Permission required: None |
| `get-userpermissions-roles` | — | GET /api/UserPermissions/roles [UserPermissions] - Permission required: None |
| `get-userpermissions-usertypes` | — | GET /api/UserPermissions/userTypes [UserPermissions] - Permission required: None |
| `get-userpermissions-workspace-by-workspaceid-default` | `--workspaceId` | GET /api/UserPermissions/workspace/{workspaceId}/default [UserPermissions] - Permission required: Workspace.Admin |
| `get-userpreferences` | — | GET /api/UserPreferences [UserPreferences] - Permission required: None |
| `get-users-me` | — | GET /api/Users/me [Users] - Permission required: None |
| `get-webhooks` | — | GET /api/Webhooks [Webhooks] - Permission required: Webhook.Read |
| `get-webhooks-by-webhookid` | `--webhookId` | GET /api/Webhooks/{webhookId} [Webhooks] - Permission required: Webhook.Read |
| `get-webhooks-by-webhookid-used` | `--webhookId` | GET /api/Webhooks/{webhookId}/used [Webhooks] - Permission required: Webhook.Read |
| `get-webhooks-datamodels-by-webhookid` | `--webhookId` | GET /api/Webhooks/datamodels/{webhookId} [Webhooks] - Permission required: Webhook.Read |
| `get-webhooks-launch-by-id` | `--id` | GET /api/Webhooks/launch/{id} [WebhookLaunch] - Permission required: None |
| `get-workspace-by-parentid-otp` | `--parentId` | GET /api/Workspace/{parentId}/otp [Workspace] - Permission required: MasterWorkspace.Read |
| `get-workspace-by-parentid-subworkspaces` | `--parentId` | GET /api/Workspace/{parentId}/subworkspaces [Workspace] - Permission required: MasterWorkspace.Read |
| `get-workspace-by-parentid-subworkspaces-by-id` | `--parentId`, `--id` | GET /api/Workspace/{parentId}/subworkspaces/{id} [Workspace] - Permission required: MasterWorkspace.Read |
| `get-workspace-settings-default` | — | GET /api/Workspace/settings/default [Workspace] - Permission required: MasterWorkspace.Read |
| `get-workspace-users` | — | GET /api/Workspace/users [Workspace] - Permission required: Workspace.Write |
| `get-workspaces` | — | GET /api/Workspaces [Workspace] - Permission required: None |

### import

| action | required args | what it does |
|---|---|---|
| `import` | `--file` | Import components from a .procesio bundle (POST /api/Transport/import); mirrors export. |

### inspect

| action | required args | what it does |
|---|---|---|
| `inspect-flow` | `--in` | Structural summary of a flow (offline): counts, action families, branches, subprocess calls, resources, variables, advisory smells. |

### layout

| action | required args | what it does |
|---|---|---|
| `layout-flow` | `--in` | Recompute tidy canvas positions for a flow (deterministic, offline). Writes positions back into a re-importable bundle (--out) or prints it. |
| `layout-report` | — | Engine-agnostic layout verification: readability report for a laid-out flow (hard issues + crossings, edge lengths, vertical rows, For-Each padding/size).… |
| `layout-resource-map` | `--in` | Position the cross-process (process→process) call graph from a bundle (offline). |

### list

| action | required args | what it does |
|---|---|---|
| `list-actions-catalog` | — | List the action/connector catalog (GET /api/Actions). |
| `list-api-keys` | — | List API keys in the workspace (GET /api/ApiKey). |
| `list-connection-types` | — | List supported connection types (GET /api/Credentials/types). |
| `list-connections` | — | List stored connection credentials (GET /api/Credentials). |
| `list-credentials` | — | List stored credential profiles (names/types/workspaces only - no secrets). |
| `list-datatypes` | — | List data types (GET /api/DataTypes). |
| `list-endpoints` | — | Browse the bundled Swagger index of all PROCESIO endpoints. |
| `list-environments` | — | List known PROCESIO environments (URLs, default, bound credentials). |
| `list-instances` | `--id` | List a process's run instances (GET /api/Projects/{id}/instances). |
| `list-processes` | — | List processes (GET /api/Projects). |
| `list-project-schedules` | `--id` | List a project's schedules (GET /api/Projects/{id}/restricted/schedules). |
| `list-schedules` | — | List schedules (GET /api/Schedules). |
| `list-subworkspaces` | `--parent-id` | List a master's sub-workspaces, active-only by default (--include-removed for soft-deleted). |
| `list-workspace-users` | — | List users in a workspace (GET /api/Workspace/users). |
| `list-workspaces` | — | List the caller's workspaces (GET /api/Workspaces, active-only). |

### login

| action | required args | what it does |
|---|---|---|
| `login` | — | Acquire (userpass) or confirm (apikey) authentication; caches the token. |

### logout

| action | required args | what it does |
|---|---|---|
| `logout` | — | Clear the cached Bearer token for a userpass profile. |

### node

| action | required args | what it does |
|---|---|---|
| `node-delete` | `--id`, `--node` | Delete ONE action from a live process and heal the graph: every port that pointed at it is re-pointed at its successor (or dropped when it has none) ->… |
| `node-params` | `--id` | List a live process's nodes with each runtime parameter's designer label, current value, editability and bound variables (read-only). |
| `node-replace-text` | `--id`, `--node`, `--find`, `--replace` | Replace an EXACT literal in every string leaf of a node's runtime parameters AND designer settings on a live process - the safe way to reach a value nested… |
| `node-set-param` | `--id`, `--node`, `--property`, `--value` | Surgically set ONE node parameter's literal text on a live process (an endpoint, timeout, SQL or script body) -> regenerate the designer layer from the runtime… |

### patch

| action | required args | what it does |
|---|---|---|
| `patch-actions-folders-rename` | — | PATCH /api/Actions/folders/rename [Actions] - Permission required: ProcessDesigner.Update |
| `patch-by-masterworkspaceurl-by-workspaceurl-by-entityurl` | `--masterWorkspaceUrl`, `--workspaceUrl`, `--entityUrl` | PATCH /{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl} [CustomUrlLaunch] |
| `patch-by-tinyurl` | `--tinyUrl` | PATCH /{tinyUrl} [TinyUrlLaunch] |
| `patch-form-chain-by-chainid-by-forminstanceid` | `--chainId`, `--formInstanceId` | PATCH /api/Form/chain/{chainId}/{formInstanceId} [FormChain] - Permission required: FormInstance.Update |
| `patch-formapplication-by-id` | `--id` | PATCH /api/FormApplication/{id} [FormApplication] - Permission required: FormTemplate.Update |
| `patch-formtemplate-by-id` | `--id` | PATCH /api/FormTemplate/{id} [FormTemplate] - Permission required: FormTemplate.Update |
| `patch-notifications` | — | PATCH /api/Notifications [Notifications] - Permission required: None |
| `patch-projects-by-id-dataretention` | `--id` | PATCH /api/Projects/{id}/dataRetention [ProcessTemplate] - Permission required: ProcessDesigner.Update |
| `patch-projects-by-id-toggle-activation` | `--id` | PATCH /api/Projects/{id}/toggle-activation [ProcessTemplate] - Permission required: ProcessDesigner.Update |
| `patch-schedules-by-scheduleid-status` | `--scheduleId` | PATCH /api/Schedules/{scheduleId}/status [Schedules] - Permission required: Schedule.Update |
| `patch-webhooks-launch-by-id` | `--id` | PATCH /api/Webhooks/launch/{id} [WebhookLaunch] - Permission required: None |

### post

| action | required args | what it does |
|---|---|---|
| `post-actions` | — | POST /api/Actions [Actions] - Permission required: CustomActions.Write |
| `post-actions-event` | — | POST /api/Actions/event [Actions] - Permission required: ProcessDesigner.Update |
| `post-actions-folders` | — | POST /api/Actions/folders [Actions] - Permission required: ProcessDesigner.Write |
| `post-actions-test` | — | POST /api/Actions/test [Actions] - Permission required: ProcessDesigner.Update |
| `post-apikey` | — | POST /api/ApiKey [ApiKey] - Permission required: ApiKey.Write |
| `post-authentication` | — | POST /api/Authentication [Authentication] - Permission required: None |
| `post-authentication-logout` | — | POST /api/Authentication/logOut [Authentication] - Permission required: None |
| `post-authentication-refreshtoken` | — | POST /api/Authentication/refreshToken [Authentication] - Permission required: None |
| `post-by-masterworkspaceurl-by-workspaceurl-by-entityurl` | `--masterWorkspaceUrl`, `--workspaceUrl`, `--entityUrl` | POST /{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl} [CustomUrlLaunch] |
| `post-by-tinyurl` | `--tinyUrl` | POST /{tinyUrl} [TinyUrlLaunch] |
| `post-credentials` | — | POST /api/Credentials [Credentials] - Permission required: Credentials.Write |
| `post-credentials-accesstoken-by-id` | `--id` | POST /api/Credentials/accessToken/{id} [Credentials] - Permission required: Credentials.Update |
| `post-credentials-test` | — | POST /api/Credentials/test [Credentials] - Permission required: Credentials.Update |
| `post-credentials-upload-by-credentialsid` | `--credentialsId` | POST /api/Credentials/upload/{credentialsId} [Credentials] - Permission required: Credentials.Update |
| `post-credentials-upload-test` | — | POST /api/Credentials/upload/test [Credentials] - Permission required: Credentials.Update |
| `post-customurl-formtemplate` | — | POST /api/CustomUrl/FormTemplate [CustomUrlForm] - Permission required: FormTemplate.Write |
| `post-customurl-masterworkspace` | — | POST /api/CustomUrl/MasterWorkspace [CustomUrlMaster] - Permission required: MasterWorkspace.Write |
| `post-customurl-webhook` | — | POST /api/CustomUrl/Webhook [CustomUrlWebhook] - Permission required: Webhook.Write |
| `post-customurl-workspace` | — | POST /api/CustomUrl/Workspace [CustomUrlWorkspace] - Permission required: Workspace.Write |
| `post-datatypes` | — | POST /api/DataTypes [DataTypes] - Permission required: DataModels.Write |
| `post-datatypes-attribute-by-rootdatatypeid` | `--rootDataTypeId` | POST /api/DataTypes/attribute/{rootDataTypeId} [DataTypes] - Permission required: DataModels.Update |
| `post-datatypes-changetopublic` | — | POST /api/DataTypes/changeToPublic [DataTypes] - Permission required: DataModels.Write |
| `post-datatypes-clone` | — | POST /api/DataTypes/clone [DataTypes] - Permission required: DataModels.Write |
| `post-datatypes-generate` | — | POST /api/DataTypes/generate [DataTypes] - Permission required: DataModels.Write |
| `post-datatypes-generate-file` | — | POST /api/DataTypes/generate/file [DataTypes] - Permission required: DataModels.Write |
| `post-datatypes-private` | — | POST /api/DataTypes/private [DataTypes] - Permission required: DataModels.Write |
| `post-debugger-instances-by-id-operation` | `--id` | POST /api/Debugger/instances/{id}/operation [Debugger] - Permission required: ProcessInstance.Write |
| `post-documenttemplate` | — | POST /api/DocumentTemplate [DocumentTemplate] - Permission required: DocumentDesigner.Write |
| `post-file-upload-action-event` | — | POST /api/File/upload/action-event [File] - Permission required: ProcessDesigner.Update |
| `post-file-upload-flow` | — | POST /api/File/upload/flow [File] - Permission required: ProcessInstance.Write |
| `post-file-upload-schedule` | — | POST /api/File/upload/schedule [File] - Permission required: Schedule.Write |
| `post-file-upload-testaction` | — | POST /api/File/upload/testAction [File] - Permission required: ProcessDesigner.Update |
| `post-form` | — | POST /api/Form [Form] - Permission required: None |
| `post-form-upload` | — | POST /api/Form/upload [FileForm] - Permission required: None |
| `post-formapplication` | — | POST /api/FormApplication [FormApplication] - Permission required: FormTemplate.Write |
| `post-formprocess-by-formtemplateid-by-flowinstanceid-upload` | `--formTemplateId`, `--flowInstanceId` | POST /api/FormProcess/{formTemplateId}/{flowInstanceId}/upload [FileFormProcess] - Permission required: None |
| `post-formprocess-by-formtemplateid-by-processtemplateid-launch` | `--formTemplateId`, `--processTemplateId` | POST /api/FormProcess/{formTemplateId}/{processTemplateId}/launch [FormProcess] - Permission required: None |
| `post-formprocess-by-formtemplateid-by-processtemplateid-publish` | `--formTemplateId`, `--processTemplateId` | POST /api/FormProcess/{formTemplateId}/{processTemplateId}/publish [FormProcess] - Permission required: None |
| `post-formtemplate` | — | POST /api/FormTemplate [FormTemplate] - Permission required: FormTemplate.Write |
| `post-formtemplate-by-id-duplicate` | `--id` | POST /api/FormTemplate/{id}/duplicate [FormTemplate] - Permission required: FormTemplate.Write |
| `post-projects` | — | POST /api/Projects [ProcessTemplate] - Permission required: ProcessDesigner.Write |
| `post-projects-by-id-duplicate` | `--id` | POST /api/Projects/{id}/duplicate [ProcessTemplate] - Permission required: ProcessDesigner.Write |
| `post-projects-by-id-instances-publish` | `--id` | POST /api/Projects/{id}/instances/publish [ProcessInstance] - Permission required: ProcessInstance.Write |
| `post-projects-by-id-run` | `--id` | POST /api/Projects/{id}/run [ProcessInstance] - Permission required: ProcessInstance.Write |
| `post-projects-instances-by-id-launch` | `--id` | POST /api/Projects/instances/{id}/launch [ProcessInstance] - Permission required: ProcessInstance.Write |
| `post-projects-instances-by-id-stop` | `--id` | POST /api/Projects/instances/{id}/stop [ProcessInstance] - Permission required: ProcessInstance.Update |
| `post-projects-notifications` | — | POST /api/Projects/notifications [ProcessTemplate] - Permission required: ProcessDesigner.Update |
| `post-projects-validate` | — | POST /api/Projects/validate [ProcessTemplate] - Permission required: ProcessDesigner.Update |
| `post-schedules` | — | POST /api/Schedules [Schedules] - Permission required: Schedule.Write |
| `post-schedules-notifications` | — | POST /api/Schedules/notifications [Schedules] - Permission required: Schedule.Update |
| `post-subscriptions-refund-by-id` | `--id` | POST /api/Subscriptions/refund/{id} [Subscriptions] - Permission required: MasterWorkspace.Admin |
| `post-subscriptions-renew-by-id-by-state` | `--id`, `--state` | POST /api/Subscriptions/renew/{id}/{state} [Subscriptions] - Permission required: MasterWorkspace.Admin |
| `post-transport-export-entities` | — | POST /api/Transport/export-entities [Transport] - Permission required: Workspace.Admin |
| `post-transport-import` | — | POST /api/Transport/import [Transport] - Permission required: Workspace.Admin |
| `post-userpreferences` | — | POST /api/UserPreferences [UserPreferences] - Permission required: None |
| `post-users` | — | POST /api/Users [Users] - Permission required: None |
| `post-users-otp-setup` | — | POST /api/Users/otp/setup [Users] - Permission required: None |
| `post-users-password-change` | — | POST /api/Users/password/change [Users] - Permission required: None |
| `post-users-password-forgot` | — | POST /api/Users/password/forgot [Users] - Permission required: None |
| `post-users-password-update` | — | POST /api/Users/password/update [Users] - Permission required: None |
| `post-users-refer-friend` | — | POST /api/Users/refer-friend [Users] - Permission required: None |
| `post-users-resendtoken` | — | POST /api/Users/resendToken [Users] - Permission required: None |
| `post-webhooks` | — | POST /api/Webhooks [Webhooks] - Permission required: Webhook.Write |
| `post-webhooks-generate-data` | — | POST /api/Webhooks/generate-data [Webhooks] - Permission required: Webhook.Write |
| `post-webhooks-launch-by-id` | `--id` | POST /api/Webhooks/launch/{id} [WebhookLaunch] - Permission required: None |
| `post-webhooks-listen` | — | POST /api/Webhooks/listen [Webhooks] - Permission required: Webhook.Update |
| `post-workspace` | — | POST /api/Workspace [Workspace] - Permission required: MasterWorkspace.Write |
| `post-workspace-invite` | — | POST /api/Workspace/invite [Workspace] - Permission required: Workspace.Write |
| `post-workspace-transfer-ownership-by-coownerid` | `--coOwnerId` | POST /api/Workspace/transfer-ownership/{coOwnerId} [Workspace] - Permission required: MasterWorkspace.Update |

### process

| action | required args | what it does |
|---|---|---|
| `process-create` | — | Create a PROCESIO process from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO. |
| `process-delete` | `--id` | Delete a resource by id (DELETE /api/Projects/{id}). |
| `process-edit` | `--id` | Edit a PROCESIO process to a desired-state config (--id required). --dry-run to preview the DTO. |
| `process-fe-validate` | `--id` | Front-end (designer-layer) 'Process Errors' validation on a live process — the client-side check that BLOCKS designer Save but which POST… |
| `process-toggle-activation` | `--id` | DEACTIVATE a process (PATCH /api/Projects/{id}/toggle-activation). Despite the name it is not a toggle: measured, it only ever sets `active` to FALSE, and… |
| `process-validate` | `--id` | Validate a process with PROCESIO's own validator (POST /api/Projects/validate). |

### put

| action | required args | what it does |
|---|---|---|
| `put-by-masterworkspaceurl-by-workspaceurl-by-entityurl` | `--masterWorkspaceUrl`, `--workspaceUrl`, `--entityUrl` | PUT /{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl} [CustomUrlLaunch] |
| `put-by-tinyurl` | `--tinyUrl` | PUT /{tinyUrl} [TinyUrlLaunch] |
| `put-credentials` | — | PUT /api/Credentials [Credentials] - Permission required: Credentials.Update |
| `put-customurl-formtemplate` | — | PUT /api/CustomUrl/FormTemplate [CustomUrlForm] - Permission required: FormTemplate.Update |
| `put-customurl-masterworkspace` | — | PUT /api/CustomUrl/MasterWorkspace [CustomUrlMaster] - Permission required: MasterWorkspace.Update |
| `put-customurl-webhook` | — | PUT /api/CustomUrl/Webhook [CustomUrlWebhook] - Permission required: Webhook.Update |
| `put-customurl-workspace` | — | PUT /api/CustomUrl/Workspace [CustomUrlWorkspace] - Permission required: Workspace.Update |
| `put-datatypes` | — | PUT /api/DataTypes [DataTypes] - Permission required: DataModels.Update |
| `put-datatypes-attribute-by-rootdatatypeid` | `--rootDataTypeId` | PUT /api/DataTypes/attribute/{rootDataTypeId} [DataTypes] - Permission required: DataModels.Update |
| `put-debugger-instances-by-id-variables` | `--id` | PUT /api/Debugger/instances/{id}/variables [Debugger] - Permission required: ProcessInstance.Write |
| `put-documenttemplate` | — | PUT /api/DocumentTemplate [DocumentTemplate] - Permission required: DocumentDesigner.Update |
| `put-form` | — | PUT /api/Form [Form] - Permission required: None |
| `put-formapplication` | — | PUT /api/FormApplication [FormApplication] - Permission required: FormTemplate.Update |
| `put-formtemplate` | — | PUT /api/FormTemplate [FormTemplate] - Permission required: FormTemplate.Update |
| `put-projects` | — | Update a process (PUT /api/Projects). Reports HTTP status/elapsed and WARNS on an empty-body success (which can silently not persist). |
| `put-projects-put` | — | PUT /api/Projects [ProcessTemplate] - Permission required: ProcessDesigner.Update |
| `put-resourcetrackingconfig-toggle-by-enabled` | `--enabled` | PUT /api/ResourceTrackingConfig/toggle/{enabled} [ResourceTrackingConfig] - Permission required: Workspace.Admin |
| `put-schedules` | — | PUT /api/Schedules [Schedules] - Permission required: Schedule.Update |
| `put-userpermissions-by-userid` | `--userId` | PUT /api/UserPermissions/{userId} [UserPermissions] - Permission required: Workspace.Admin |
| `put-users-details` | — | PUT /api/Users/details [Users] - Permission required: None |
| `put-webhooks` | — | PUT /api/Webhooks [Webhooks] - Permission required: Webhook.Update |
| `put-webhooks-launch-by-id` | `--id` | PUT /api/Webhooks/launch/{id} [WebhookLaunch] - Permission required: None |
| `put-workspace` | — | PUT /api/Workspace [Workspace] - Permission required: MasterWorkspace.Update |
| `put-workspace-by-parentid-otp` | `--parentId` | PUT /api/Workspace/{parentId}/otp [Workspace] - Permission required: MasterWorkspace.Update |

### read

| action | required args | what it does |
|---|---|---|
| `read-flow-graph` | `--in` | Parse a .procesio export/flow into a node/edge graph model (offline). --resource-map for the cross-process graph. |

### relayout

| action | required args | what it does |
|---|---|---|
| `relayout-process` | `--id` | Re-lay-out a LIVE process in place: read the flow, run the auto-layout engine (LAYOUT_ENGINE env: legacy default / elk), validate, and save back (PUT… |

### remove

| action | required args | what it does |
|---|---|---|
| `remove-credential` | `--name` | Delete a credential profile and its cached token. |
| `remove-environment` | `--name` | Remove a user-defined environment (built-in Internal-* cannot be removed). |

### rename

| action | required args | what it does |
|---|---|---|
| `rename-actions` | `--id` | Rename a LIVE process's canvas actions in bulk from an id → name map (--map JSON or --map-file), setting BOTH ActionName and CustomData.name; validates, then… |

### repair

| action | required args | what it does |
|---|---|---|
| `repair-datastore-mapper` | `--in` | Repair a .procesio pack whose Data Store mapper the export re-spelled into the refused `document`/`process` form (offline). An imported process carrying the… |

### request

| action | required args | what it does |
|---|---|---|
| `request` | `--path` | Call ANY Web-API endpoint: --method --path [--query JSON] [--body JSON]. |

### run

| action | required args | what it does |
|---|---|---|
| `run-form-with-files` | `--form-id`, `--process-id` | Submit a form the way a browser does: publish -> upload files -> launch -> read variables, through the public FormProcess endpoints. Proves the form's own… |
| `run-process` | `--id` | Run a process (POST /api/Projects/{id}/run). Supports --dry-run. |
| `run-process-with-file` | `--id` | Run a process that takes File input variable(s): publish -> upload bytes -> launch -> poll -> output. --file VARNAME=PATH (repeatable). |

### set

| action | required args | what it does |
|---|---|---|
| `set-default` | `--name` | Set the default profile used when --profile is omitted. |
| `set-environment` | `--name` | Switch the default environment (e.g. to Internal-QA); persists the choice. |
| `set-schedule-notifications` | `--payload` | Set a schedule's notifications (POST /api/Schedules/notifications) from a JSON --payload. |
| `set-schedule-status` | `--id`, `--active` | Enable/disable a schedule (PATCH /api/Schedules/{id}/status --active true|false). |

### show

| action | required args | what it does |
|---|---|---|
| `show-credential` | `--name` | Show one profile's non-secret fields (secrets shown only as has_*). |
| `show-environment` | `--name` | Show one environment's URLs, default flag, and bound credentials. |

### sql

| action | required args | what it does |
|---|---|---|
| `sql-convert` | `--id`, `--node`, `--to` | Move one SQL node between the Execute Command and Execute Query families (--to) and optionally rebind its Output (--output-variable); validate + flow-lint then… |
| `sql-parameterize` | `--id` | Convert inline N'<%N%>' SQL nodes to safe named-@param binding (--node or --all); validate then PUT (--dry-run to preview). |
| `sql-scan` | `--id` | List a process's SQL Server actions (Execute Query/Command) with inline-vs-parameterized status. |

### stop

| action | required args | what it does |
|---|---|---|
| `stop-instance` | `--id` | Stop a running instance (POST /api/Projects/instances/{id}/stop). |

### update

| action | required args | what it does |
|---|---|---|
| `update-schedule` | `--payload` | Update a schedule (PUT /api/Schedules) from a JSON --payload; --cron/--timezone sets a crontab recurrence. |

### usage

| action | required args | what it does |
|---|---|---|
| `usage-guide` | — | Regenerate PROCESIO-USAGE-GUIDE.md from the rules the notes in this folder mark with a warning sign (offline, deterministic). The guide carries the rule and a… |

### validate

| action | required args | what it does |
|---|---|---|
| `validate-crontab` | `--cron` | Preview a crontab expression's next occurrences (POST /api/Schedules/validate-crontab). |

### variable

| action | required args | what it does |
|---|---|---|
| `variable-set-type` | `--id`, `--variable`, `--data-type` | Retype one variable of a live process (dataType, optionally isList) -> validate + flow-lint -> PUT. Refuses an input/output variable without… |

### verify

| action | required args | what it does |
|---|---|---|
| `verify-layout` | `--in` | Simulate the designer's rendering of a flow's positions and report problems (container children outside their frame, node overlaps). |

### webhook

| action | required args | what it does |
|---|---|---|
| `webhook-create` | — | Create a PROCESIO webhook from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO. |
| `webhook-delete` | `--id` | Delete a resource by id (DELETE /api/Webhooks/{id}). |
| `webhook-edit` | `--id` | Edit a PROCESIO webhook to a desired-state config (--id required). --dry-run to preview the DTO. |
| `webhook-get` | `--id` | Get one resource by id (GET /api/Webhooks/{id}). |
| `webhook-launch` | `--id` | Fire a webhook-triggered process with a payload (POST /api/Webhooks/launch/{id}). |

---

Generated from `tools/procesio/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
