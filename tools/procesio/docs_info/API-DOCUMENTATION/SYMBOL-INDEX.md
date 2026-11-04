# PROCESIO API reference - symbol index

**Generated** from `endpoints/*.md` by `procesio-release api-docs-sync` (ai-ready d2554c3 2026-11-04). **Do not hand-edit** - regenerate.

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
| **`AccessTokenErrorResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:504` |
| **`AccessTokenRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:485` |
| **`AccessTokenResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:495` |
| **`AcknowledgeUserNotificationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/15-notifications-apikeys-transport.md:196` |
| **`ActionAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:516` |
| **`ActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:684` |
| **`ActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:330` |
| **`ActionPrototypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:336` |
| **`ActionTabDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:389` |
| **`ApiErrorResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1251` |
| **`ApiKeyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/15-notifications-apikeys-transport.md:204` |
| **`AuthenticateUserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:622` |
| **`AuthenticationTokenResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:639` |
| **`AuthorizationConnection`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:490` |
| **`BaseActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:433` |
| **`BaseActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:319` |
| **`BaseDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:482` |
| **`BaseDocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:122` |
| **`BaseFlowDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:634` |
| **`BaseScheduleDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:862` |
| **`BaseSubscriptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:398` |
| **`BaseTestActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:482` |
| **`BaseUserPermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:703` |
| **`BaseWebhookDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:272` |
| **`BasicFormTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:929` |
| **`BreakPointDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:750` |
| **`ConnectorActionRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:445` |
| **`ConnectorActionResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:455` |
| **`ConnectorControlValueDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:470` |
| **`CreateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:285` |
| **`CreatePublicSigningEnvelopeFromTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1174` |
| **`CreateSigningEnvelopeFromTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1166` |
| **`CreateWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:724` |
| **`CredentialsPropertyConditionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:445` |
| **`CredentialsPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:412` |
| **`CredentialsPropertyOptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:424` |
| **`CredentialsTableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:510` |
| **`CredentialsVerbDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:479` |
| **`CustomResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:793` |
| **`CustomUrlDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1208` |
| **`CustomUrlEntityType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1326` |
| **`CustomUrlType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1319` |
| **`DataAttributeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:453` |
| **`DataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:474` |
| **`DataRetentionPolicyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:808` |
| **`DataStoreColumnDefinitionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:323` |
| **`DataStoreCsvJobResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:446` |
| **`DataStoreDeleteRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1043` |
| **`DataStoreFromDataModelDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:366` |
| **`DataStoreFromJsonDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:373` |
| **`DataStoreGetRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:406` |
| **`DataStoreInsertRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1030` |
| **`DataStoreMetadataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:335` |
| **`DataStoreMetadataResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:343` |
| **`DataStoreModifyColumnDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:354` |
| **`DataStoreRowsAffectedDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:402` |
| **`DataStoreUpdateRowsRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1036` |
| **`DataStoreViewerResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:380` |
| **`DataTypeFileDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:318` |
| **`DataTypeTransferDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:299` |
| **`DataTypeUpdateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:304` |
| **`DebuggerOperationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:840` |
| **`DecisionDataType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:567` |
| **`DecisionMatrixRule`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:558` |
| **`DetailedActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:441` |
| **`DetailedActionTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:361` |
| **`DetailedScheduleDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:849` |
| **`DetailedTestActionRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:475` |
| **`DocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:105` |
| **`DocumentVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:143` |
| **`EEAnalyticsStatsType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:445` |
| **`ErrorPayload`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:533` |
| **`ExportEntitiesDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/15-notifications-apikeys-transport.md:219` |
| **`ExtendedCredentialsPropertyOptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:430` |
| **`FlowRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:606` |
| **`FlowResponseDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:619` |
| **`FormApplicationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:940` |
| **`FormApplicationImageDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:958` |
| **`FormApplicationImageSource`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1312` |
| **`FormApplicationState`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1305` |
| **`FormApplicationType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1298` |
| **`FormAssigneeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:987` |
| **`FormAssigneeType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1289` |
| **`FormChain`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1270` |
| **`FormChainDataModel`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1011` |
| **`FormFileDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:975` |
| **`FormNextStepDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:967` |
| **`FormStage`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1263` |
| **`FormStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1283` |
| **`FormSubmitterDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1004` |
| **`FormTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:911` |
| **`FormType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1277` |
| **`FormUserDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:996` |
| **`GenerateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:312` |
| **`GetConnectionId`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/16-realtime-signalr.md:48` |
| **`GetFormDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:875` |
| **`GetSigningEnvelopeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1049` |
| **`HandshakeConfigDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/14-webhooks.md:304` |
| **`ICustomUrlModel`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/12-custom-urls.md:317` |
| **`IdentifyRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:678` |
| **`LaunchFlowPayload`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:588` |
| **`LayoutDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:441` |
| **`LimitsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:417` |
| **`NotificationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:818` |
| **`OwnershipAuditDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:652` |
| **`Pagination`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:526` |
| **`ParametersDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:723` |
| **`ParameterVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:731` |
| **`ParentFlowDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:800` |
| **`PayloadVariable`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:830` |
| **`PermissionsDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:379` |
| **`PortDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:709` |
| **`PrivateDataTypeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/11-datatypes.md:292` |
| **`PropertyDependencyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:421` |
| **`PropertyEventDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:756` |
| **`PublicSigningEnvelopeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1184` |
| **`RefreshTokenRequestDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:631` |
| **`RefundReasonDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:391` |
| **`RestrictedDataStoreMetadataDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/10-datastore.md:359` |
| **`RestrictedDocumentTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/08-documents.md:132` |
| **`RunFlowPayload`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:789` |
| **`ScheduleVariableDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/04-processes.md:871` |
| **`SetFormDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:895` |
| **`SetSigningEnvelopeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1116` |
| **`SigningConflictResponse`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1201` |
| **`SigningDeclineDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1160` |
| **`SigningDocumentDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1071` |
| **`SigningEffectiveStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1335` |
| **`SigningPartyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1100` |
| **`SigningPartyStatus`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1346` |
| **`SigningSessionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1125` |
| **`SigningSpotDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1083` |
| **`SigningSpotPlacementDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1150` |
| **`SigningSpotType`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1355` |
| **`SigningTemplateDocumentDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1191` |
| **`SimpleActionGroupingDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:437` |
| **`SimpleActionNodeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:323` |
| **`SimpleActionTemplateDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:344` |
| **`SimpleEmailDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:698` |
| **`SimpleWorkspaceDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:717` |
| **`SubmitSignatureDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/07-forms.md:1142` |
| **`SubscriptionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:421` |
| **`SubscriptionOptions`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/13-subscriptions-resources-analytics.md:430` |
| **`SubWorkspaceNameChangeDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/03-auth-users-workspaces.md:763` |
| **`TableHeaderDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:515` |
| **`TabPropertyDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:395` |
| **`TestActionDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/05-actions.md:485` |
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
| **`ValidationDto`** | `tools/procesio/docs_info/API-DOCUMENTATION/endpoints/09-credentials.md:436` |
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
