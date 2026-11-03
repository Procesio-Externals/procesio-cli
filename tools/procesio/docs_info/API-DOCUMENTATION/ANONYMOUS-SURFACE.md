# PROCESIO - the ANONYMOUS surface, enumerated

**Generated** from `endpoints/*.md` by `procesio-release api-docs-sync` (ai-ready 3b58134 2026-11-03). **Do not hand-edit** - regenerate.

> **Why this exists.** Anonymous endpoints used to be met one incident at a time: a webhook launch id that travels in exported packs, a public form's process launch, and a form data-store route that reads and writes any store its path names. All were documented; none was read before it mattered.

> **The general rule: on every endpoint below the access control is AN ID.** An id is a bearer credential - it travels in process definitions, exported packs, shared links, logs and browser history. Treat every `{id}` in this table as a secret, or decide deliberately that it is not.

43 anonymous endpoints.

| verbs | route | operation | the id that IS the control | documented at |
|---|---|---|---|---|
| `POST` | `api/Authentication` | `Authenticate` | `{(none in route)}` | `03-auth-users-workspaces.md:32` |
| `GET` | `api/Authentication` | `AuthenticationForm` | `{(none in route)}` | `03-auth-users-workspaces.md:45` |
| `GET` | `api/Authentication/oauth2/callback/{identityProvider}` | `AuthenticateByBroker` | `{identityProvider}` | `03-auth-users-workspaces.md:54` |
| `GET` | `api/Authentication/otp/callback` | `AuthenticateOTPCallback` | `{(none in route)}` | `03-auth-users-workspaces.md:65` |
| `GET` | `api/Authentication/authorize/{identityProvider}` | `GetAuthorization` | `{identityProvider}` | `03-auth-users-workspaces.md:74` |
| `POST` | `api/Authentication/refreshToken` | `RefreshToken` | `{(none in route)}` | `03-auth-users-workspaces.md:84` |
| `POST` | `api/Authentication/logOut` | `Logout` | `{(none in route)}` | `03-auth-users-workspaces.md:96` |
| `DELETE` | `api/Authentication/logOut` | `DeleteAllSessions` | `{(none in route)}` | `03-auth-users-workspaces.md:105` |
| `POST` | `api/Users` | `CreateUser` | `{(none in route)}` | `03-auth-users-workspaces.md:136` |
| `POST` | `api/Users/withActivation` | `CreateUserWithActivationResponse` | `{(none in route)}` | `03-auth-users-workspaces.md:154` |
| `POST` | `api/Users/resendToken` | `RefreshCreateUserToken` | `{(none in route)}` | `03-auth-users-workspaces.md:164` |
| `POST` | `api/Users/password/change` | `ChangePassword` | `{(none in route)}` | `03-auth-users-workspaces.md:172` |
| `POST` | `api/Users/password/forgot` | `ForgotPassword` | `{(none in route)}` | `03-auth-users-workspaces.md:181` |
| `POST` | `api/Users/password/update` | `UpdatePassword` | `{(none in route)}` | `03-auth-users-workspaces.md:190` |
| `POST` | `api/Form` | `SaveForm` | `{(none in route)}` | `07-forms.md:67` |
| `GET` | `api/FormTemplate/{workspaceId}/{id}` | `GetAnonymousForm` | `{workspaceId}` · `{id}` | `07-forms.md:194` |
| `GET` | `api/FormProcess/{formTemplateId}/{processTemplateId}` | `GetProcessTemplate` | `{formTemplateId}` · `{processTemplateId}` | `07-forms.md:352` |
| `POST` | `api/FormProcess/{formTemplateId}/{processTemplateId}/publish` | `PublishFlow` | `{formTemplateId}` · `{processTemplateId}` | `07-forms.md:363` |
| `POST` | `api/FormProcess/{formTemplateId}/{processTemplateId}/launch` | `LaunchFlowInstance` | `{formTemplateId}` · `{processTemplateId}` | `07-forms.md:377` |
| `GET` | `api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables` | `GetFlowInstanceVariables` | `{formTemplateId}` · `{processTemplateId}` · `{processInstanceId}` | `07-forms.md:394` |
| `POST` | `api/Form/upload` | `UploadFormFile` | `{(none in route)}` | `07-forms.md:414` |
| `POST` | `api/FormProcess/{formTemplateId}/{flowInstanceId}/upload` | `Upload` | `{formTemplateId}` · `{flowInstanceId}` | `07-forms.md:445` |
| `GET` | `api/FormProcess/download` | `Download` | `{(none in route)}` | `07-forms.md:463` |
| `POST` | `api/Form/dataStore/{dataStoreId}/rows/filter` | `GetRows` | `{dataStoreId}` | `07-forms.md:486` |
| `POST` | `api/Form/dataStore/{dataStoreId}/rows` | `AddRows` | `{dataStoreId}` | `07-forms.md:504` |
| `PUT` | `api/Form/dataStore/{dataStoreId}/rows` | `UpdateRows` | `{dataStoreId}` | `07-forms.md:514` |
| `DELETE` | `api/Form/dataStore/{dataStoreId}/rows` | `DeleteRows` | `{dataStoreId}` | `07-forms.md:524` |
| `POST` | `api/form/signing/public/envelope` | `CreateEnvelope` | `{(none in route)}` | `07-forms.md:694` |
| `POST` | `api/form/signing/public/envelope/from-template` | `CreateEnvelopeFromTemplate` | `{(none in route)}` | `07-forms.md:713` |
| `GET` | `api/form/signing/public/envelope/{id}` | `GetEnvelope` | `{id}` | `07-forms.md:725` |
| `PUT` | `api/form/signing/public/envelope/{id}` | `UpdateDraft` | `{id}` | `07-forms.md:735` |
| `POST` | `api/form/signing/public/envelope/{id}/send` | `Send` | `{id}` | `07-forms.md:748` |
| `DELETE` | `api/form/signing/public/envelope/{id}` | `DiscardDraft` | `{id}` | `07-forms.md:760` |
| `GET` | `api/form/signing/public/envelope/{id}/document` | `Download` | `{id}` | `07-forms.md:771` |
| `GET` | `api/form/signing/public/envelope/{id}/my-session` | `GetMySession` | `{id}` | `07-forms.md:784` |
| `POST` | `api/form/signing/public/envelope/{id}/my-session/sign` | `Sign` | `{id}` | `07-forms.md:794` |
| `GET` | `api/form/signing/public/template-document/{workspaceId}/{formTemplateId}/{fileId}` | `DownloadTemplateDocument` | `{workspaceId}` · `{formTemplateId}` · `{fileId}` | `07-forms.md:807` |
| `GET` | `api/DataStore/restricted` | `GetRestrictedDataStores` | `{(none in route)}` | `10-datastore.md:147` |
| `GET` | `api/DataTypes/primary` | `GetPrimaryTypes` | `{(none in route)}` | `11-datatypes.md:189` |
| `GET` | `api/DataTypes/procesio` | `GetProcesioTypes` | `{(none in route)}` | `11-datatypes.md:201` |
| `GET` | `api/DataTypes/primary/count` | `CountPrimaryDataTypes` | `{(none in route)}` | `11-datatypes.md:213` |
| `POST` | `api/Webhooks/launch/{id}/verifone` | `LaunchFormData` | `{id}` | `14-webhooks.md:187` |
| `GET` | `api/Webhooks/launch/{id}/verifone` | `LaunchGetFormData` | `{id}` | `14-webhooks.md:202` |
