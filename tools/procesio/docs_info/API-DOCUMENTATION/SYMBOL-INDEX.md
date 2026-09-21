# PROCESIO API reference — symbol index

**Generated** by `UC7/e87/verify/e87_pa_index.py`. **Do not hand-edit** — regenerate.

> ⚠ **WHY THIS EXISTS.** This directory documents 276 endpoints across 15 files and its own README says it is written *"so that another AI can generate applications that use PROCESIO as their backend, without reading the microservice source"*. **It was written for an agent to read, and three separate investigations measured behaviour to establish things defined here.** A definition is cheaper than a probe and it does not leave residue.

> ⚠ **GREP THIS FILE BEFORE DESIGNING A PROBE.** If a symbol is listed, the answer is already written down.

---

## Enums (7)

| enum | defined at | values |
|---|---|---|
| **`ActionStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:910` | — |
| **`DebuggerOperationType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:879` | `RESUME`=0 · `STEP`=1 |
| **`FlowDataRetentionType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:894` | — |
| **`FlowStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:860` | `STATUS_NONE`=1 · `INACTIVE`=5 · `STATUS_STOP_BY_USER`=6 · `STATUS_INITIALIZING`=15 · `STATUS_DISPATCHED_ACTIONS`=20 · `STATUS_RUNNING`=30 · `STATUS_RUNNING_WITH_ERRORS`=40 · `BREAK_POINT`=45 · `STATUS_FINISH`=50 · `STATUS_TEMPORARY_WAITING`=60 |
| **`ProcessTimeSpanFilterType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:875` | — |
| **`VariableOrientation`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:886` | `INPUT`=10 · `PROCESS`=20 · `OUTPUT`=30 |
| **`WebhookVariableType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:902` | — |

## DTOs (137)

| DTO | defined at |
|---|---|
| **`AccessTokenRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:479` |
| **`AcknowledgeUserNotificationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:467` |
| **`ActionAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:515` |
| **`ActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:521` |
| **`ActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:330` |
| **`ActionPrototypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:336` |
| **`ActionTabDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:389` |
| **`ApiKeyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:475` |
| **`AuthenticateUserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:559` |
| **`AuthenticationTokenResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:576` |
| **`BaseActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:432` |
| **`BaseActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:319` |
| **`BaseCredentialsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:361` |
| **`BaseCredentialsPropertyDetailsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:390` |
| **`BaseCredentialsPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:385` |
| **`BaseCredentialsTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:445` |
| **`BaseDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:764` |
| **`BaseDocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:829` |
| **`BaseFlowDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:610` |
| **`BaseScheduleDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:838` |
| **`BaseSubscriptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:398` |
| **`BaseTestActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:481` |
| **`BaseUserPermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:640` |
| **`BaseWebhookDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:426` |
| **`BasicFormTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:692` |
| **`BreakPointDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:554` |
| **`ConnectorActionRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:444` |
| **`ConnectorActionResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:454` |
| **`ConnectorControlValueDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:469` |
| **`CreateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:696` |
| **`CreateWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:661` |
| **`CredentialsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:373` |
| **`CredentialsPropertyConditionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:439` |
| **`CredentialsPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:408` |
| **`CredentialsPropertyOptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:419` |
| **`CredentialsTableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:504` |
| **`CredentialsTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:454` |
| **`CredentialsVerbDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:473` |
| **`CustomResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:769` |
| **`CustomUrlDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:271` |
| **`DataAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:735` |
| **`DataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:499` |
| **`DataRetentionPolicyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:784` |
| **`DataStoreColumnDefinitionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:574` |
| **`DataStoreCsvJobResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:689` |
| **`DataStoreFilterEntryDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:657` |
| **`DataStoreFromDataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:609` |
| **`DataStoreFromJsonDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:616` |
| **`DataStoreMetadataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:585` |
| **`DataStoreMetadataResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:593` |
| **`DataStoreModifyColumnDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:604` |
| **`DataStoreQueryRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:647` |
| **`DataStoreRowsAffectedDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:643` |
| **`DataStoreRowsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:630` |
| **`DataStoreRowsPrimaryKeysDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:639` |
| **`DataStoreSortEntryDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:664` |
| **`DataStoreUpdateRowRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:634` |
| **`DataStoreViewerResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:623` |
| **`DataTypeFileDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:729` |
| **`DataTypeTransferDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:710` |
| **`DataTypeUpdateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:715` |
| **`DebuggerOperationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:816` |
| **`DetailedActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:440` |
| **`DetailedActionTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:361` |
| **`DetailedScheduleDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:825` |
| **`DetailedTestActionRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:474` |
| **`DocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:812` |
| **`DocumentVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:850` |
| **`ExportEntitiesDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:485` |
| **`ExtendedCredentialsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:378` |
| **`ExtendedCredentialsPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:413` |
| **`ExtendedCredentialsPropertyOptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:424` |
| **`ExtendedCredentialsTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:459` |
| **`FlowRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:582` |
| **`FlowResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:595` |
| **`FormApplicationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:703` |
| **`FormApplicationImageDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:721` |
| **`FormAssigneeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:750` |
| **`FormFileDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:738` |
| **`FormNextStepDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:730` |
| **`FormSubmitterDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:767` |
| **`FormTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:313` |
| **`FormUserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:759` |
| **`GenerateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:723` |
| **`GetFormDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:638` |
| **`HandshakeConfigDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:458` |
| **`IdentifyRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:615` |
| **`InternalDataStoreGetRowsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:669` |
| **`InternalDataStoreRowsFilterDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:676` |
| **`InternalDataStoreRowsSortDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:683` |
| **`LayoutDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:435` |
| **`LimitsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:416` |
| **`NotificationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:794` |
| **`OwnershipAuditDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:779` |
| **`ParameterVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:506` |
| **`ParametersDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:500` |
| **`ParentFlowDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:776` |
| **`PermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:379` |
| **`PortDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:542` |
| **`PrivateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:703` |
| **`PropertyDependencyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:420` |
| **`PropertyEventDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:426` |
| **`RefreshTokenRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:568` |
| **`RefundReasonDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:391` |
| **`RestrictedDocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:839` |
| **`ScheduleVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:847` |
| **`SetFormDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:658` |
| **`SimpleActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:436` |
| **`SimpleActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:323` |
| **`SimpleActionTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:344` |
| **`SimpleEmailDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:635` |
| **`SimpleWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:654` |
| **`StoreCredentialsTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:464` |
| **`SubscriptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:421` |
| **`TabPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:395` |
| **`TableHeaderDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:509` |
| **`TestActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:484` |
| **`UPDefaultWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:651` |
| **`UpdatePasswordDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:629` |
| **`UpdateUserDetailsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:609` |
| **`UpdateWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:671` |
| **`UserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:591` |
| **`UserExtraDataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:604` |
| **`UserPasswordDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:621` |
| **`UserPermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:648` |
| **`UserPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:690` |
| **`ValidationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-credentials.md:430` |
| **`VariableAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:511` |
| **`VariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:488` |
| **`WebhookCustomResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:429` |
| **`WebhookDataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:437` |
| **`WebhookDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:407` |
| **`WebhookInstanceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:743` |
| **`WebhookListenDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:444` |
| **`WebhookRulesDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:760` |
| **`WebhookVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:753` |
| **`WorkspaceOptionsSettingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:682` |

## Endpoints (276)

| verbs | route | documented at |
|---|---|---|
| `POST` | `api/Authentication` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:32` |
| `GET` | `api/Authentication` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:45` |
| `GET` | `api/Authentication/oauth2/callback/{identityProvider}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:54` |
| `GET` | `api/Authentication/otp/callback` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:65` |
| `GET` | `api/Authentication/authorize/{identityProvider}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:74` |
| `POST` | `api/Authentication/refreshToken` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:84` |
| `POST` | `api/Authentication/logOut` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:96` |
| `DELETE` | `api/Authentication/logOut` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:105` |
| `GET` | `api/Users/me` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:121` |
| `POST` | `api/Users/otp/setup` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:128` |
| `POST` | `api/Users` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:136` |
| `PUT` | `api/Users/details` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:145` |
| `POST` | `api/Users/withActivation` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:154` |
| `POST` | `api/Users/resendToken` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:164` |
| `POST` | `api/Users/password/change` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:172` |
| `POST` | `api/Users/password/forgot` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:181` |
| `POST` | `api/Users/password/update` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:190` |
| `GET` | `api/UserPermissions/userTypes` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:204` |
| `GET` | `api/UserPermissions/roles` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:211` |
| `GET` | `api/UserPermissions/entities` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:218` |
| `PUT` | `api/UserPermissions/{userId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:225` |
| `GET` | `api/UserPermissions/{userId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:235` |
| `GET` | `api/UserPermissions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:243` |
| `GET` | `api/UserPermissions/workspace/{workspaceId}/default` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:250` |
| `GET` | `api/UserPreferences` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:264` |
| `POST` | `api/UserPreferences` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:271` |
| `DELETE` | `api/UserPreferences` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:279` |
| `GET` | `api/Workspaces` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:294` |
| `GET` | `api/Workspace/users` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:302` |
| `POST` | `api/Workspace/invite` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:313` |
| `DELETE` | `api/Workspace/invite/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:323` |
| `GET` | `api/Workspace/{parentId}/subworkspaces` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:338` |
| `GET` | `api/Workspace/{parentId}/subworkspaces/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:347` |
| `POST` | `api/Workspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:355` |
| `PUT` | `api/Workspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:363` |
| `DELETE` | `api/Workspace/{workspaceToDelete}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:371` |
| `POST` | `api/Workspace/transfer-ownership/{coOwnerId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:379` |
| `GET` | `api/Workspace/{parentId}/otp` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:387` |
| `PUT` | `api/Workspace/{parentId}/otp` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:395` |
| `GET` | `api/Workspace/settings/default` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:405` |
| `POST` | `api/Users/referral-code` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:420` |
| `DELETE` | `api/Users/otp` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:432` |
| `GET` | `api/Workspace/all` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:449` |
| `POST` | `api/Workspace/master` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:457` |
| `DELETE` | `api/Workspace/any/{workspaceToDelete}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:467` |
| `GET` | `api/UserProperty/all` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:482` |
| `GET` | `api/UserProperty/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:490` |
| `GET` | `api/UserProperty/user/{userId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:499` |
| `POST` | `api/UserProperty` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:508` |
| `PUT` | `api/UserProperty` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:517` |
| `DELETE` | `api/UserProperty/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:526` |
| `POST` | `api/Users/refer-friend` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:543` |
| `POST` | `api/Projects` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:55` |
| `PUT` | `api/Projects` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:66` |
| `POST` | `api/Projects/validate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:77` |
| `DELETE` | `api/Projects/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:88` |
| `GET` | `api/Projects` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:99` |
| `GET` | `api/Projects/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:113` |
| `GET` | `api/Projects/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:123` |
| `POST` | `api/Projects/{id}/duplicate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:134` |
| `GET` | `api/Projects/{id}/payload` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:145` |
| `GET` | `api/Projects/{id}/used` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:157` |
| `PATCH` | `api/Projects/{id}/toggle-activation` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:168` |
| `POST` | `api/Projects/notifications` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:180` |
| `GET` | `api/Projects/notifications/{flowId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:191` |
| `PATCH` | `api/Projects/{id}/dataRetention` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:202` |
| `GET` | `api/Projects/{id}/instances` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:220` |
| `GET` | `api/Projects/{id}/history` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:235` |
| `GET` | `api/Projects/{id}/archive` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:251` |
| `GET` | `api/Projects/{id}/instances/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:264` |
| `GET` | `api/Projects/instances/{id}/output` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:275` |
| `GET` | `api/Projects/instances/{id}/status` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:288` |
| `GET` | `api/Projects/{id}/instances/{instanceId}/customResponse` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:307` |
| `POST` | `api/Projects/{id}/instances/publish` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:321` |
| `POST` | `api/Projects/instances/{id}/launch` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:333` |
| `POST` | `api/Projects/instances/{id}/stop` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:351` |
| `POST` | `api/Projects/{id}/run` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:363` |
| `GET` | `api/Projects/{id}/restricted` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:380` |
| `DELETE` | `api/Projects/instances/{id}/dataRetention` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:391` |
| `GET` | `api/Projects/restricted/schedules` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:409` |
| `GET` | `api/Projects/{id}/restricted/schedules` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:422` |
| `POST` | `api/Debugger/instances/{id}/operation` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:439` |
| `PUT` | `api/Debugger/instances/{id}/variables` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:451` |
| `GET` | `api/Schedules` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:470` |
| `GET` | `api/Schedules/{scheduleId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:484` |
| `DELETE` | `api/Schedules/{scheduleId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:495` |
| `POST` | `api/Schedules` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:506` |
| `PUT` | `api/Schedules` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:517` |
| `PATCH` | `api/Schedules/{scheduleId}/status` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:528` |
| `POST` | `api/Schedules/notifications` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:540` |
| `GET` | `api/Schedules/notifications/{scheduleId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:551` |
| `GET` | `api/Actions/decisional/operators` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:29` |
| `GET` | `api/Actions/folders/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:44` |
| `GET` | `api/Actions/folders` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:54` |
| `POST` | `api/Actions/folders` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:62` |
| `PATCH` | `api/Actions/folders/rename` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:76` |
| `DELETE` | `api/Actions/folders/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:87` |
| `GET` | `api/Actions/templates/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:102` |
| `POST` | `api/Actions/templates` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:111` |
| `DELETE` | `api/Actions/templates/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:121` |
| `GET` | `api/Actions/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:136` |
| `GET` | `api/Actions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:144` |
| `GET` | `api/Actions/category/{category}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:156` |
| `GET` | `api/Actions/node` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:167` |
| `GET` | `api/Actions/restricted` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:185` |
| `POST` | `api/Actions/event` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:201` |
| `GET` | `api/Actions/event/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:218` |
| `POST` | `api/Actions/test` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:233` |
| `GET` | `api/Actions/test/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:248` |
| `POST` | `api/Actions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:263` |
| `DELETE` | `api/Actions/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:277` |
| `POST` | `api/PlatformAction` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:293` |
| `POST` | `api/File/upload/flow` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:45` |
| `GET` | `api/File/download` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:61` |
| `POST` | `api/File/upload/action-event` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:83` |
| `GET` | `api/File/download/action-event` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:99` |
| `POST` | `api/File/upload/schedule` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:117` |
| `GET` | `api/File/download/schedule` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:132` |
| `POST` | `api/File/upload/testAction` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:151` |
| `GET` | `api/File/download/testAction` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/06-files.md:167` |
| `GET` | `api/Form/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:31` |
| `GET` | `api/Form/{pid}/all` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:41` |
| `GET` | `api/Form/assigned` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:53` |
| `POST` | `api/Form` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:65` |
| `PUT` | `api/Form` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:75` |
| `DELETE` | `api/Form/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:85` |
| `DELETE` | `api/Form` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:94` |
| `GET` | `api/Form/{pid}/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:103` |
| `POST` | `api/FormTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:117` |
| `PUT` | `api/FormTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:126` |
| `PATCH` | `api/FormTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:135` |
| `DELETE` | `api/FormTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:145` |
| `GET` | `api/FormTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:154` |
| `GET` | `api/FormTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:163` |
| `GET` | `api/FormTemplate/all/basic` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:175` |
| `POST` | `api/FormTemplate/{id}/duplicate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:183` |
| `GET` | `api/FormTemplate/{workspaceId}/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:192` |
| `GET` | `api/FormTemplate/processTemplate/list` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:205` |
| `GET` | `api/FormTemplate/processTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:212` |
| `GET` | `api/FormApplication/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:226` |
| `GET` | `api/FormApplication/all` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:236` |
| `GET` | `api/FormApplication/all/{pid}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:247` |
| `GET` | `api/FormApplication/all/filter` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:256` |
| `POST` | `api/FormApplication` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:267` |
| `PUT` | `api/FormApplication` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:276` |
| `PATCH` | `api/FormApplication/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:285` |
| `DELETE` | `api/FormApplication/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:295` |
| `GET` | `api/Form/chain/{formTemplateId}/all` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:310` |
| `GET` | `api/Form/chain/{chainId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:322` |
| `PATCH` | `api/Form/chain/{chainId}/{formInstanceId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:331` |
| `GET` | `api/FormProcess/{formTemplateId}/{processTemplateId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:350` |
| `POST` | `api/FormProcess/{formTemplateId}/{processTemplateId}/publish` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:361` |
| `POST` | `api/FormProcess/{formTemplateId}/{processTemplateId}/launch` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:375` |
| `GET` | `api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:392` |
| `POST` | `api/Form/upload` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:412` |
| `GET` | `api/Form/download` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:425` |
| `POST` | `api/FormProcess/{formTemplateId}/{flowInstanceId}/upload` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:443` |
| `GET` | `api/FormProcess/download` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:461` |
| `GET` | `api/Form/dataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:484` |
| `POST` | `api/Form/dataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:499` |
| `PUT` | `api/Form/dataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:509` |
| `DELETE` | `api/Form/dataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:519` |
| `GET` | `api/DocumentTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:535` |
| `GET` | `api/DocumentTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:544` |
| `POST` | `api/DocumentTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:556` |
| `PUT` | `api/DocumentTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:565` |
| `DELETE` | `api/DocumentTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:574` |
| `GET` | `api/DocumentTemplate/{id}/restricted` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:589` |
| `GET` | `api/DocumentTemplate/restricted` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms-documents.md:604` |
| `POST` | `api/DataStore` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:32` |
| `PUT` | `api/DataStore` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:49` |
| `PATCH` | `api/DataStore/{dataStoreId}/column` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:61` |
| `DELETE` | `api/DataStore/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:76` |
| `GET` | `api/DataStore/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:87` |
| `GET` | `api/DataStore` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:98` |
| `POST` | `api/DataStore/from-data-model` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:112` |
| `POST` | `api/DataStore/from-json` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:127` |
| `GET` | `api/DataStore/{dataStoreId}/data-model` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:142` |
| `GET` | `api/DataStore/restricted` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:153` |
| `GET` | `api/DataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:174` |
| `POST` | `api/DataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:197` |
| `PUT` | `api/DataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:210` |
| `DELETE` | `api/DataStore/{dataStoreId}/rows` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:224` |
| `POST` | `api/DataStore/{dataStoreId}/export-start` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:252` |
| `GET` | `api/DataStore/{dataStoreId}/export-download/{jobId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:265` |
| `POST` | `api/DataStore/{dataStoreId}/import-start` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:278` |
| `GET` | `api/DataStore/{dataStoreId}/import-failures/{jobId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:293` |
| `POST` | `api/DataTypes` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:314` |
| `POST` | `api/DataTypes/private` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:329` |
| `POST` | `api/DataTypes/changeToPublic` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:344` |
| `POST` | `api/DataTypes/clone` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:357` |
| `DELETE` | `api/DataTypes/attribute/{rootDataTypeId}/{attributeId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:370` |
| `POST` | `api/DataTypes/attribute/{rootDataTypeId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:383` |
| `PUT` | `api/DataTypes/attribute/{rootDataTypeId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:395` |
| `PUT` | `api/DataTypes` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:407` |
| `GET` | `api/DataTypes/{id}/{type?}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:424` |
| `GET` | `api/DataTypes/{value}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:437` |
| `GET` | `api/DataTypes` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:448` |
| `GET` | `api/DataTypes/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:465` |
| `GET` | `api/DataTypes/primary` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:478` |
| `GET` | `api/DataTypes/procesio` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:490` |
| `GET` | `api/DataTypes/primary/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:502` |
| `GET` | `api/DataTypes/procesio/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:511` |
| `DELETE` | `api/DataTypes/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:520` |
| `POST` | `api/DataTypes/generate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:531` |
| `POST` | `api/DataTypes/generate/file` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:545` |
| `GET` | `api/DataTypes/restricted` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-datastore-datatypes.md:559` |
| `GET` | `api/CustomUrl/MasterWorkspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:29` |
| `POST` | `api/CustomUrl/MasterWorkspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:38` |
| `PUT` | `api/CustomUrl/MasterWorkspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:49` |
| `DELETE` | `api/CustomUrl/MasterWorkspace/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:60` |
| `GET` | `api/CustomUrl/Workspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:75` |
| `GET` | `api/CustomUrl/Workspace/master` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:83` |
| `POST` | `api/CustomUrl/Workspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:92` |
| `PUT` | `api/CustomUrl/Workspace` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:103` |
| `DELETE` | `api/CustomUrl/Workspace/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:113` |
| `GET` | `api/CustomUrl/FormTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:128` |
| `POST` | `api/CustomUrl/FormTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:138` |
| `PUT` | `api/CustomUrl/FormTemplate` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:148` |
| `DELETE` | `api/CustomUrl/FormTemplate/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:158` |
| `GET` | `api/CustomUrl/Webhook/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:173` |
| `POST` | `api/CustomUrl/Webhook` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:183` |
| `PUT` | `api/CustomUrl/Webhook` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:193` |
| `DELETE` | `api/CustomUrl/Webhook/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:203` |
| `GET|POST|PUT|PATCH|DELETE` | `/{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:218` |
| `GET|POST|PUT|PATCH|DELETE` | `/{tinyUrl}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-custom-urls.md:248` |
| `GET` | `api/Subscriptions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:28` |
| `GET` | `api/Subscriptions/{subscriptionId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:38` |
| `POST` | `api/Subscriptions/refund/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:49` |
| `POST` | `api/Subscriptions/renew/{id}/{state}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:63` |
| `POST` | `api/Subscriptions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:84` |
| `PUT` | `api/Subscriptions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:95` |
| `PUT` | `api/Subscriptions/{subscriptionId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:106` |
| `DELETE` | `api/Subscriptions` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:118` |
| `DELETE` | `api/Subscriptions/{subscriptionId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:129` |
| `GET` | `api/Subscriptions/reusable` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:140` |
| `GET` | `api/Subscriptions/externalReference/{externalRef}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:150` |
| `GET` | `api/Subscriptions/externalOrder/{refNo}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:162` |
| `PUT` | `api/Subscriptions/refund` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:173` |
| `GET` | `api/Resources/used` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:190` |
| `GET` | `api/Resources/used/subWorkspaces` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:203` |
| `GET` | `api/ResourceTrackingConfig` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:222` |
| `PUT` | `api/ResourceTrackingConfig/toggle/{enabled}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:232` |
| `GET` | `api/Resources/analytics/processes` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:249` |
| `GET` | `api/Resources/analytics/processes/{id}/details` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:264` |
| `GET` | `api/Resources/analytics/instances/{id}/details` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:284` |
| `GET` | `api/Analytics/user/usage/all` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:301` |
| `GET` | `api/Analytics/user/usage/update` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:313` |
| `GET` | `api/Analytics/user/all/activity` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:325` |
| `GET` | `api/Analytics/user/Segmentation` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:338` |
| `GET` | `api/analytics/executionEnvironment/concurrency` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:353` |
| `GET` | `api/analytics/executionEnvironment/topProcesses` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-subscriptions-resources-analytics.md:371` |
| `GET` | `api/Webhooks` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:32` |
| `GET` | `api/Webhooks/{webhookId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:46` |
| `POST` | `api/Webhooks` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:57` |
| `PUT` | `api/Webhooks` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:68` |
| `DELETE` | `api/Webhooks/{webhookId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:79` |
| `GET` | `api/Webhooks/datamodels/{webhookId}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:90` |
| `POST` | `api/Webhooks/generate-data` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:101` |
| `DELETE` | `api/Webhooks/{webhookId}/undo` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:112` |
| `GET` | `api/Webhooks/{webhookId}/used` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:124` |
| `POST` | `api/Webhooks/listen` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:135` |
| `GET|POST|PUT|PATCH|DELETE` | `api/Webhooks/launch/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:155` |
| `POST` | `api/Webhooks/launch/{id}/verifone` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:193` |
| `GET` | `api/Webhooks/launch/{id}/verifone` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:208` |
| `GET` | `api/WebhookEvents` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:229` |
| `GET` | `api/WebhookEvents/count` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:246` |
| `GET` | `api/Notifications` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:263` |
| `PATCH` | `api/Notifications` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:273` |
| `GET` | `api/ApiKey` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:293` |
| `POST` | `api/ApiKey` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:303` |
| `DELETE` | `api/ApiKey` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:315` |
| `DELETE` | `api/ApiKey/{id}` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:326` |
| `POST` | `api/Transport/import` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:344` |
| `GET` | `api/Transport/export` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:364` |
| `POST` | `api/Transport/export-entities` | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-webhooks-notifications-misc.md:377` |
