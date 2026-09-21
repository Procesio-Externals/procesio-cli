# PROCESIO — the ANONYMOUS surface, enumerated

**Generated** from `API-DOCUMENTATION/endpoints/*.md`. **Do not hand-edit** — regenerate.

> ⚠ **WHY THIS EXISTS.** Three anonymous endpoints were met one incident at a time: `api/Webhooks/launch/{id}` (a bearer id that travels in packs), `api/FormProcess/.../launch`, and `api/Form/dataStore/{id}/rows` (full CRUD, including DELETE, on any store the path names). **All three were documented and none was read before it mattered.**

> ⚠ **THE GENERAL FORM: on every endpoint below the access control is AN ID.** An id is a bearer credential — it travels in process definitions, in exported packs, in shared links, in logs and in browser history. **Treat every `{id}` in this table as a secret, or decide deliberately that it is not.**

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
| `POST` | `api/Users/otp/setup` | `OtpSetup` | `{(none in route)}` | `03-auth-users-workspaces.md:128` |
| `POST` | `api/Users` | `CreateUser` | `{(none in route)}` | `03-auth-users-workspaces.md:136` |
| `PUT` | `api/Users/details` | `UpdateUserDetails` | `{(none in route)}` | `03-auth-users-workspaces.md:145` |
| `POST` | `api/Users/withActivation` | `CreateUserWithActivationResponse` | `{(none in route)}` | `03-auth-users-workspaces.md:154` |
| `POST` | `api/Users/resendToken` | `RefreshCreateUserToken` | `{(none in route)}` | `03-auth-users-workspaces.md:164` |
| `POST` | `api/Users/password/change` | `ChangePassword` | `{(none in route)}` | `03-auth-users-workspaces.md:172` |
| `POST` | `api/Users/password/forgot` | `ForgotPassword` | `{(none in route)}` | `03-auth-users-workspaces.md:181` |
| `POST` | `api/Users/password/update` | `UpdatePassword` | `{(none in route)}` | `03-auth-users-workspaces.md:190` |
| `POST` | `api/Form` | `SaveForm` | `{(none in route)}` | `07-forms-documents.md:65` |
| `POST` | `api/FormTemplate/{id}/duplicate` | `DuplicateForm` | `{id}` | `07-forms-documents.md:183` |
| `GET` | `api/FormTemplate/{workspaceId}/{id}` | `GetAnonymousForm` | `{workspaceId}` · `{id}` | `07-forms-documents.md:192` |
| `GET` | `api/FormProcess/{formTemplateId}/{processTemplateId}` | `GetProcessTemplate` | `{formTemplateId}` · `{processTemplateId}` | `07-forms-documents.md:350` |
| `POST` | `api/FormProcess/{formTemplateId}/{processTemplateId}/publish` | `PublishFlow` | `{formTemplateId}` · `{processTemplateId}` | `07-forms-documents.md:361` |
| `POST` | `api/FormProcess/{formTemplateId}/{processTemplateId}/launch` | `LaunchFlowInstance` | `{formTemplateId}` · `{processTemplateId}` | `07-forms-documents.md:375` |
| `GET` | `api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables` | `GetFlowInstanceVariables` | `{formTemplateId}` · `{processTemplateId}` · `{processInstanceId}` | `07-forms-documents.md:392` |
| `POST` | `api/Form/upload` | `UploadFormFile` | `{(none in route)}` | `07-forms-documents.md:412` |
| `POST` | `api/FormProcess/{formTemplateId}/{flowInstanceId}/upload` | `Upload` | `{formTemplateId}` · `{flowInstanceId}` | `07-forms-documents.md:443` |
| `GET` | `api/FormProcess/download` | `Download` | `{(none in route)}` | `07-forms-documents.md:461` |
| `GET` | `api/Form/dataStore/{dataStoreId}/rows` | `GetRows` | `{dataStoreId}` | `07-forms-documents.md:484` |
| `POST` | `api/Form/dataStore/{dataStoreId}/rows` | `AddRows` | `{dataStoreId}` | `07-forms-documents.md:499` |
| `PUT` | `api/Form/dataStore/{dataStoreId}/rows` | `UpdateRow` | `{dataStoreId}` | `07-forms-documents.md:509` |
| `DELETE` | `api/Form/dataStore/{dataStoreId}/rows` | `DeleteRows` | `{dataStoreId}` | `07-forms-documents.md:519` |
| `GET` | `api/DataTypes/primary` | `GetPrimaryTypes` | `{(none in route)}` | `09-datastore-datatypes.md:478` |
| `GET` | `api/DataTypes/procesio` | `GetProcesioTypes` | `{(none in route)}` | `09-datastore-datatypes.md:490` |
| `GET` | `api/DataTypes/primary/count` | `CountPrimaryDataTypes` | `{(none in route)}` | `09-datastore-datatypes.md:502` |
| `GET|POST|PUT|PATCH|DELETE` | `/{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl}` | `Launch` | `{masterWorkspaceUrl}` · `{workspaceUrl}` · `{entityUrl}` | `10-custom-urls.md:218` |
| `GET|POST|PUT|PATCH|DELETE` | `/{tinyUrl}` | `Launch` | `{tinyUrl}` | `10-custom-urls.md:248` |
| `GET|POST|PUT|PATCH|DELETE` | `api/Webhooks/launch/{id}` | `LaunchWebhook` | `{id}` | `12-webhooks-notifications-misc.md:155` |
| `POST` | `api/Webhooks/launch/{id}/verifone` | `LaunchFormData` | `{id}` | `12-webhooks-notifications-misc.md:193` |
| `GET` | `api/Webhooks/launch/{id}/verifone` | `LaunchGetFormData` | `{id}` | `12-webhooks-notifications-misc.md:208` |

**Total anonymous endpoints: 38**

