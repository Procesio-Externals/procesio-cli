# Appendix — Internal & inter-service surface (NOT for external clients)

> This appendix exists so the picture is complete. **None of the endpoints here are part of the public API contract.** Do not call them from an application — they are service-to-service only and will reject external callers.

---

## 1. Web-Api `internal/*` endpoints

These controllers live in `BE/Web-Api/WebApi/Application/Controllers/Internal/` and are marked `[SecureInternalController]`. They are reachable only with the `prc-service` + `prc-code` header pair (from `ServiceCodesConfig`); any other caller gets **404** (intentional — avoids leaking endpoint existence). Other PROCESIO microservices use them for cross-service lookups.

| Route prefix | Controller | Purpose (internal) |
| --- | --- | --- |
| `internal/ActionTemplate` | `Internal/ActionTemplateController` | Action-template lookups for other services |
| `internal/Credentials` | `Internal/CredentialsController` | Credential resolution at execution time |
| `internal/DataStore` | `Internal/DataStoreController` | Data-store metadata reads for the execution engine (cache-populating), per-workspace DB-user get-or-create for the Data-Store service (`POST user`), admin metadata-cache invalidation |
| `internal/DataTypes` | `Internal/DataTypesController` | Data-type metadata |
| `internal/DocumentTemplate` | `Internal/DocumentTemplateController` | Document-template fetch |
| `internal/Form` | `Internal/FormController` | Form instance access |
| `internal/FormTemplate` | `Internal/FormTemplateController` | Form-template fetch |
| `internal/FormApplication` | `Internal/FormApplicationController` | Form-application access |
| `internal/Notifications` | `Internal/NotificationsController` | Notification fan-in |
| `internal/PredefinedItems` | `Internal/PredefinedItemsController` | Seed/predefined data |
| `internal/Projects` | `Internal/ProcessController` | Process/template lookups for the engine |
| `internal/SecureData` | `Internal/SecureDataController` | Secret material exchange |
| `internal/Subscriptions` | `Internal/SubscriptionsController` | Subscription checks |
| `internal/Sync` | `Internal/SyncController` | Cross-service sync |

---

## 2. The other Back-End repositories

For an external integrator, **only Web-Api is callable**. The remaining repositories either have no HTTP surface at all, or have one that is internal (guarded by `SecureInternalRequests`) or reached only through Web-Api. They are listed here for architectural context. The canonical list is [BE/REPOSITORIES.md](../../BE/REPOSITORIES.md) — if a repo there is missing from this table, this table is stale.

| Service | Default branch | Role | Externally callable? |
| --- | --- | --- | --- |
| **Web-Api** | `main` | Public HTTP gateway + owner of files/credentials/forms/custom-actions/subscriptions/analytics | **Yes — the public API** |
| Authentication-Proxy | `main` | Users, workspaces, permissions, JWT issuance (fronts Keycloak) | No — via Web-Api `api/Authentication`, `api/Users`, `api/Workspace` |
| Process-Monitor | `main` | Launches processes (HTTP→AMQP) + live monitoring | No — via Web-Api `api/Projects` |
| Process-Execution | `main` | Core workflow engine (built-in actions, dispatcher) | No — driven by RabbitMQ |
| Process-History | `main` | Archived flow-instance data | No — via Web-Api `api/Projects` (archived reads) |
| Action-Execution | `main` | Runs user-uploaded custom NuGet actions (legacy) | No — driven by RabbitMQ |
| Scheduler | `main` | Cron triggers + delay-action resume | No — via Web-Api `api/Schedules` / `api/Projects` |
| Webhook-Service | `main` | Inbound webhook gateway + condition evaluator | No — external systems hit Web-Api `api/Webhooks/launch/{id}`; Web-Api forwards |
| System-Notifications | `main` | SignalR push + notification inbox | **Hub yes** (`/hub/notification`); REST is internal — see `16-realtime-signalr.md` |
| Resource-Tracking | `main` | Quota/limits, usage analytics, runtime subscription enforcement | No — via Web-Api `api/Resources`, `api/Analytics` |
| Data-Store | `main` | User-defined dynamic data tables (CRUD + CSV) | No — via Web-Api `api/DataStore`. At runtime it also calls back into Web-Api (`POST internal/DataStore/user`) to pull its per-workspace DB user |
| Test-Action | `main` | Designer-time single-action test harness | No — via Web-Api `api/Actions/test` |
| Action-Core | `main` | NuGet contract package (`IAction`, decorators) | No — library, no HTTP |
| External-Adapters | `main` | NuGet storage-abstraction library | No — library, no HTTP |
| DataBase-Update | `main` | Hand-applied SQL migration scripts | No — no runtime |
| bdamserver | `main` | Bitdefender anti-malware scanning engine (third-party container image, not a PROCESIO service) | No — unauthenticated in-cluster REST on port 1344, reachable only by pods labelled `bdamserver-client: "true"`. Never expose it |

**Takeaway:** build your application against the Web-Api routes documented in this folder (`03`–`13`). For realtime delivery, connect to the System-Notifications SignalR hub. Everything else is internal plumbing.
