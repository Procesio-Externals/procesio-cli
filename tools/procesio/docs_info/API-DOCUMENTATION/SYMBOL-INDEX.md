# PROCESIO API reference - symbol index

**Generated** from `endpoints/*.md` by `procesio-release api-docs-sync` (ai-ready c0648c8 2026-11-02). **Do not hand-edit** - regenerate.

> **Why this exists.** This directory documents 301 endpoints and was written for an agent to read, yet behaviour defined here has been re-measured with live probes more than once. A definition is cheaper than a probe and leaves no residue.

> **Grep this file before designing a probe.** If a symbol is listed, the answer is already written down.

## Enums (7)

| enum | defined at | values |
|---|---|---|
| **`ActionStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:935` | `NONE`=1 · `STARTING`=10 · `INPUT_DONE`=15 · `EXECUTED`=20 · `FOREACH_ITERATION_DONE`=30 · `CALL_SUBPROCESS_CHILD_STARTED`=35 · `CALL_SUBPROCESS_CHILD_FINISHED`=36 · `OUTPUT_DONE`=40 · `ERROR`=90 |
| **`DebuggerOperationType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:903` | `RESUME`=0 · `STEP`=1 |
| **`FlowDataRetentionType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:919` | `Never`=0 · `AtEndOfRuntime`=1 · `AtMoveToHistory`=2 |
| **`FlowStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:884` | `STATUS_NONE`=1 · `INACTIVE`=5 · `STATUS_STOP_BY_USER`=6 · `STATUS_INITIALIZING`=15 · `STATUS_DISPATCHED_ACTIONS`=20 · `STATUS_RUNNING`=30 · `STATUS_RUNNING_WITH_ERRORS`=40 · `BREAK_POINT`=45 · `STATUS_FINISH`=50 · `STATUS_TEMPORARY_WAITING`=60 |
| **`ProcessTimeSpanFilterType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:899` | `LastHour`=1 · `Last24Hours`=2 · `Last3Days`=3 · `Last7Days`=4 · `Last30Days`=5 · `ThisMonth`=6 · `ThisQuarter`=7 · `ThisYear`=8 · `LastMonth`=9 · `LastQuarter`=10 · `Last3Months`=11 · `Last6Months`=12 · `LastYear`=13 · `CertainMonth`=14 |
| **`VariableOrientation`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:910` | `INPUT`=10 · `PROCESS`=20 · `OUTPUT`=30 · `AUTO`=50 |
| **`WebhookVariableType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:927` | `Header`=1 · `Query`=2 · `Body`=3 |

## DTOs (171)

| DTO | defined at |
|---|---|
| **`AccessTokenErrorResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:498` |
| **`AccessTokenRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:479` |
| **`AccessTokenResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:489` |
| **`AcknowledgeUserNotificationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/15-notifications-apikeys-transport.md:196` |
| **`ActionAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:515` |
| **`ActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:684` |
| **`ActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:330` |
| **`ActionPrototypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:336` |
| **`ActionTabDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:389` |
| **`ApiErrorResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1234` |
| **`ApiKeyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/15-notifications-apikeys-transport.md:204` |
| **`AuthenticateUserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:622` |
| **`AuthenticationTokenResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:639` |
| **`AuthorizationConnection`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:484` |
| **`BaseActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:432` |
| **`BaseActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:319` |
| **`BaseDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:482` |
| **`BaseDocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:122` |
| **`BaseFlowDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:634` |
| **`BaseScheduleDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:862` |
| **`BaseSubscriptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:398` |
| **`BaseTestActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:481` |
| **`BaseUserPermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:703` |
| **`BaseWebhookDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:272` |
| **`BasicFormTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:922` |
| **`BreakPointDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:750` |
| **`ConnectorActionRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:444` |
| **`ConnectorActionResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:454` |
| **`ConnectorControlValueDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:469` |
| **`CreateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:285` |
| **`CreatePublicSigningEnvelopeFromTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1157` |
| **`CreateSigningEnvelopeFromTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1149` |
| **`CreateWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:724` |
| **`CredentialsPropertyConditionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:439` |
| **`CredentialsPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:408` |
| **`CredentialsPropertyOptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:419` |
| **`CredentialsTableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:504` |
| **`CredentialsVerbDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:473` |
| **`CustomResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:793` |
| **`CustomUrlDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1191` |
| **`CustomUrlEntityType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1306` |
| **`CustomUrlType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1299` |
| **`DataAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:453` |
| **`DataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:474` |
| **`DataRetentionPolicyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:808` |
| **`DataStoreColumnDefinitionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:323` |
| **`DataStoreCsvJobResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:446` |
| **`DataStoreDeleteRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1036` |
| **`DataStoreFromDataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:366` |
| **`DataStoreFromJsonDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:373` |
| **`DataStoreGetRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:406` |
| **`DataStoreInsertRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1023` |
| **`DataStoreMetadataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:335` |
| **`DataStoreMetadataResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:343` |
| **`DataStoreModifyColumnDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:354` |
| **`DataStoreRowsAffectedDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:402` |
| **`DataStoreUpdateRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1029` |
| **`DataStoreViewerResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:380` |
| **`DataTypeFileDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:318` |
| **`DataTypeTransferDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:299` |
| **`DataTypeUpdateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:304` |
| **`DebuggerOperationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:840` |
| **`DecisionDataType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:566` |
| **`DecisionMatrixRule`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:557` |
| **`DetailedActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:440` |
| **`DetailedActionTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:361` |
| **`DetailedScheduleDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:849` |
| **`DetailedTestActionRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:474` |
| **`DocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:105` |
| **`DocumentVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:143` |
| **`EEAnalyticsStatsType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:445` |
| **`ErrorPayload`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:527` |
| **`ExportEntitiesDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/15-notifications-apikeys-transport.md:219` |
| **`ExtendedCredentialsPropertyOptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:424` |
| **`FlowRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:606` |
| **`FlowResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:619` |
| **`FormApplicationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:933` |
| **`FormApplicationImageDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:951` |
| **`FormApplicationImageSource`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1292` |
| **`FormApplicationState`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1285` |
| **`FormApplicationType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1278` |
| **`FormAssigneeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:980` |
| **`FormAssigneeType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1272` |
| **`FormChain`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1253` |
| **`FormChainDataModel`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1004` |
| **`FormFileDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:968` |
| **`FormNextStepDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:960` |
| **`FormStage`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1246` |
| **`FormStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1266` |
| **`FormSubmitterDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:997` |
| **`FormTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:904` |
| **`FormType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1260` |
| **`FormUserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:989` |
| **`GenerateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:312` |
| **`GetConnectionId`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/16-realtime-signalr.md:48` |
| **`GetFormDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:868` |
| **`GetSigningEnvelopeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1042` |
| **`HandshakeConfigDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:304` |
| **`ICustomUrlModel`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-custom-urls.md:317` |
| **`IdentifyRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:678` |
| **`LaunchFlowPayload`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:588` |
| **`LayoutDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:435` |
| **`LimitsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:416` |
| **`NotificationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:818` |
| **`OwnershipAuditDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:652` |
| **`Pagination`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:520` |
| **`ParametersDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:723` |
| **`ParameterVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:731` |
| **`ParentFlowDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:800` |
| **`PayloadVariable`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:830` |
| **`PermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:379` |
| **`PortDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:709` |
| **`PrivateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:292` |
| **`PropertyDependencyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:420` |
| **`PropertyEventDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:756` |
| **`PublicSigningEnvelopeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1167` |
| **`RefreshTokenRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:631` |
| **`RefundReasonDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:391` |
| **`RestrictedDataStoreMetadataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:359` |
| **`RestrictedDocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:132` |
| **`RunFlowPayload`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:789` |
| **`ScheduleVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:871` |
| **`SetFormDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:888` |
| **`SetSigningEnvelopeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1110` |
| **`SigningConflictResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1184` |
| **`SigningDeclineDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1143` |
| **`SigningDocumentDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1065` |
| **`SigningEffectiveStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1315` |
| **`SigningOrderMode`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1335` |
| **`SigningPartyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1094` |
| **`SigningPartyStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1326` |
| **`SigningSessionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1120` |
| **`SigningSpotDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1077` |
| **`SigningSpotType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1344` |
| **`SigningTemplateDocumentDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1174` |
| **`SimpleActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:436` |
| **`SimpleActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:323` |
| **`SimpleActionTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:344` |
| **`SimpleEmailDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:698` |
| **`SimpleWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:717` |
| **`SubmitSignatureDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1136` |
| **`SubscriptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:421` |
| **`SubscriptionOptions`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:430` |
| **`SubWorkspaceNameChangeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:763` |
| **`TableHeaderDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:509` |
| **`TabPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:395` |
| **`TestActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:484` |
| **`UpdatePasswordDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:692` |
| **`UpdateUserDetailsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:672` |
| **`UpdateWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:734` |
| **`UPDefaultWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:714` |
| **`UserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:654` |
| **`UserExtraDataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:667` |
| **`UserGuideDTO`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:385` |
| **`UserPasswordDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:684` |
| **`UserPermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:711` |
| **`UserPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:778` |
| **`ValidationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:430` |
| **`VariableAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:741` |
| **`VariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:668` |
| **`WebhookCustomResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:275` |
| **`WebhookDataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:283` |
| **`WebhookDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:253` |
| **`WebhookInstanceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:767` |
| **`WebhookListenDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:290` |
| **`WebhookPayloadModel`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:332` |
| **`WebhookRulesDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:784` |
| **`WebhookVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:777` |
| **`WorkspaceNameChangeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:757` |
| **`WorkspaceNameSyncReportDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:745` |
| **`WorkspaceOptionsSettingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:770` |
