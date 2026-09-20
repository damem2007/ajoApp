# Provider, resilience and backoffice checkpoint

## Result

One FastAPI application remains in `backend/app`; the root `app` entry remains a compatibility symlink. Next.js components use typed API modules. Sandbox providers are independent of database selection. PostgreSQL remains authoritative when resilience is enabled, with a dedicated SQLite mirror for certified fallback writes. Staff onboarding, permission enforcement and supported notification channels are database-backed.

The configured local backend uses PostgreSQL and three simulated providers. A new `.ajo-data/fallback.db` was initialized from PostgreSQL. The original `ajo-platform.db` was not modified by this task. Default deployment startup no longer uses provider mode to trigger table creation. Explicit test fixture construction retains isolated platform schema setup.

## Architecture inspected

BA Artifacts' `backend/app/models.py` persists role grants and TeamMembership. Its `services/auth.py:274` enforces permissions, and `routes/management.py:251` persists owner membership during team creation. Ajo adopts that persisted identity → membership → role → grants pattern without introducing a second staff identity store or unrelated team/tenant features.

Ajo authorization resolves the authenticated account and its active StaffMembership on the server. StaffRole holds permission identifiers in a persisted JSON grant list, matching the existing BA pattern. Account.role remains a compatibility display value; it does not independently authorize requests. Navigation uses account permissions, but hiding navigation is not authorization.

## Providers and configuration

Existing PaymentProvider, IdentityProvider and NotificationProvider protocols remain the entrypoints. `platform/providers.py` adds a registry and `register_provider(kind, name, factory)` / `resolve_provider`. Context resolves each provider independently:

```dotenv
AJO_PAYMENTS_PROVIDER=sandbox
AJO_IDENTITY_PROVIDER=sandbox
AJO_NOTIFICATIONS_PROVIDER=sandbox
AJO_DATABASE_MODE=postgres
AJO_DATABASE_RESILIENCE=true
AJO_FALLBACK_DATABASE_URL=sqlite:////absolute/path/to/.ajo-data/fallback.db
AJO_WORKER_INTERVAL_SECONDS=30
```

Database modes remain only `postgres` and `sqlite`; their existing URL settings are preserved. There is no sandbox database mode. Legacy AJO_PROVIDER_MODE / AJO_DEMO_MODE remain compatibility defaults when a per-provider setting is omitted. Unknown provider names fail with a safe configuration error; `unconfigured` explicitly reports that the integration adapter is not implemented.

A future adapter implements its protocol and registers a name before application construction. Its credentials remain in deployment environment/secret storage. Business routes call the protocol rather than testing a concrete adapter class. No live banking, identity or email integration has been invented in this checkpoint.

Sandbox bank-link tokens support success, failure and pending simulations; raw bank credentials are rejected. Stored provider tokens are encrypted, masked in account views and used by simulated payment execution. No transfer reaches a bank. Synthetic reconciliation, test inboxes and time overrides remain explicitly testing capabilities. The all-simulated flag retains historical test MFA behavior; live staff use MFA requirements.

## Synchronization and recovery

`platform/resilience.py` centrally routes Context sessions. API routes, worker and CLI business writes use this boundary. Provider/database decisions do not live in page components or each business route.

1. Initialize a **new** SQLite mirror through migrations and a locked primary snapshot. Existing business rows in a prospective mirror are rejected rather than overwritten.
2. While PostgreSQL is reachable, commit each mutation with an encrypted SyncBatch in the same primary transaction. Mirror it before certifying fallback as ready.
3. If the initial primary probe raises a connection error, admit SQLite only when its mirror is certified. Write local mutations and encrypted outbox batch atomically.
4. On reconnection, replay local batches into PostgreSQL in sequence, then primary batches into SQLite. The next API/worker transaction triggers recovery; no hidden second application is running.
5. Replay a whole batch atomically. Stable UUID identities and idempotent receipt IDs prevent duplicate application. Compare each row against its recorded before-state; an already-matching after-state is harmless. Concurrent differences become conflicts, never last-write-wins overwrites.
6. Deletes are recorded as tombstones. Foreign-key dependency ordering is respected. The existing integer policy PK uses a separate fallback allocation range; primary sequence maintenance prevents primary collisions.
7. After startup, fallback recovery or uncertified primary state, compare runtime tables before certifying the mirror. An independent writer or ambiguous commit that escaped the outbox is detected as mirror divergence.

Do not retry a provider call or switch databases after a transaction begins. An ambiguous primary connection/commit failure leaves fallback unsafe. If the primary committed but mirror replication failed, keep the primary result successful and block fallback until replay, avoiding an API error that invites repeating a financial action.

SyncBatch exposes status, sequence, attempts, timestamps and safe error codes. SyncReceipt is committed with the destination mutation. Encrypted changes are not returned by the admin status endpoint. SyncControl exposes readiness and divergence. Logs identify batches and safe failure categories without dumping rows or credentials.

```bash
backend/.venv/bin/alembic upgrade head
backend/.venv/bin/python -m app.platform.cli sync-init
backend/.venv/bin/python -m app.platform.cli sync-status
backend/.venv/bin/python -m app.platform.cli sync-retry
```

Run sync-init once, with the API/worker stopped, using a new fallback file. sync-retry retries ordered replay and verifies equality; it does **not** force conflict resolution. A conflicted batch stays blocked until an operator investigates authoritative records and performs an explicitly reviewed reconciliation. There is no destructive overwrite button or automatic conflict winner.

**Deployment boundary:** this is a single-host, single-writer architecture. API and worker must share the same durable SQLite volume and `.sync.lock` file. A process file lock covers routing, primary commit and mirror certification; PostgreSQL advisory locks also serialize participating primary transactions. Compose now shares `/data` and a container fallback URL. This is not multi-host high availability. Independent database writers must be avoided; detected divergence pauses writes. Full verification loads tables into memory at recovery boundaries, so large datasets will need paginated/fingerprint verification. Outbox/receipt retention is intentionally not automatically pruned.

## Staff onboarding

Backoffice → Users → Backoffice onboarding invites a verified email to one of admin, ops, compliance or support. The invitation persists an expiry, hashed token, invited role and creator. Duplicate active invitations are rejected. The one-time token is delivered in an encrypted email-queue payload, not the invitation API response or audit text.

The recipient registers or signs in through the existing account flow, verifies the matching email and accepts from Account. Acceptance validates token/expiry/status, recipient identity and the inviter's current permission; creates or updates persisted staff membership; records acceptance and audit; and revokes prior sessions so grants refresh on sign-in. Suspension disables staff membership and revokes sessions; reactivation follows existing account management. Role assignments validate the seeded role set.

The simulated invitation inbox is available only to the verified recipient with a sandbox notification provider. Ordinary members cannot invite staff or assign roles. `init-admin` remains an explicit bootstrap-only administration command, not the normal onboarding path. In simulated environments email verification and delivery are simulated; real adapters must implement those integrations before live use.

## Role permission matrix

All four staff roles can view members, circles and metrics. Persisted memberships must be active, the account unsuspended, and live staff MFA enabled.

| Capability | admin | ops | compliance | support |
|---|---|---|---|---|
| View payments | Yes | Yes | Yes | Yes |
| Manage payments, jobs and circle operations | Yes | Yes | No | No |
| Review KYC/compliance | Yes | No | Yes | No |
| Manage complaints/support requests | Yes | No | Yes | Yes |
| Edit CMS | Yes | Yes | No | No |
| Publish CMS | Yes | No | No | No |
| View delivery operations | Yes | Yes | No | Yes |
| View audit | Yes | No | Yes | No |
| Manage users/roles/invitations | Yes | No | No | No |
| Manage setup, channels and participant policy | Yes | No | No | No |
| View synchronization | Yes | Yes | No | No |

Exact grants are in `platform/rbac.py` and frozen migration seed data. Routes enforce named permission dependencies. This checkpoint does not add arbitrary-role creation or a grant-editing UI. Existing role/status workflows persist membership updates rather than relying on a hardcoded account role check.

## Notification channels

Migration seeds in-app, email, SMS and push as enabled NotificationChannel rows. Backoffice → System setup & policies → Notification channels configures display labels and enabled state with an audit reason. Authentication is required and management is administrator-only.

Notification creation consults enabled supported channels and member preferences. Disabled channels are skipped for implicit delivery; an explicit request to an unsupported/disabled channel is rejected. Dispatch checks enabled state again, leaving historical and queued records intact. Re-enabling permits retained pending delivery to proceed. No channel/history delete is introduced. Adapter credentials remain deployment secrets, not editable CMS content.

## Migration and changed files

`67444298b84c` is a retained checkpoint marker. Forward revision `938fa45d0182` creates/seeds the seven new platform tables: notification_channels, staff_roles, staff_memberships, staff_invitations, sync_batches, sync_receipts and sync_control. It backfills membership for existing staff accounts. Guards accommodate local tables previously initialized dynamically. The complete chain works on an empty SQLite database. No revision was stamped and no legacy store tables were added.

Main backend changes: config.py; platform/models.py, providers.py, runtime.py, resilience.py, rbac.py, administration.py, application.py, services.py, auth.py, operations.py, cms.py, circles.py, payments.py and cli.py; migrations/env.py and the two revisions. Deployment changes: backend/.env.example and compose.yaml, plus ignored local environment settings.

Frontend changes: typed admin API and Account permissions; StaffOnboarding, StaffAccept and ChannelSetup TSX components; their account/backoffice pages and permission-filtered navigation. All use existing form, resource, toast and session infrastructure.

Tests: test_resilience.py, test_provider_admin_channels.py, test_backoffice_migration.py, postgres_resilience_smoke.py; existing fixture bootstrap updated in full-platform/CMS tests and resilience disabled in test configuration. Separate legacy table findings are in STORE_MODELS_ANALYSIS.md; store.py was not changed by this task.

## Validation and limitations

Complete backend suite: **62 passed**. Additional divergence and empty-migration cases are included. Isolated tests cover primary routing, outage writes, restart with pending changes, recovery, duplicate receipts, retry metadata, conflicts, deletes and bulk session revocation. Provider/channel/onboarding tests cover invalid tokens/roles and representative allowed/denied permissions.

A temporary real PostgreSQL schema independently passed primary mirroring, simulated probe outage with SQLite writes, recovery, duplicate replay and equality verification, then was dropped. Reproduce explicitly with `PYTHONPATH=backend backend/.venv/bin/python tests/postgres_resilience_smoke.py`. The actual PostgreSQL and dedicated SQLite runtime tables compared equal; legacy prototype tables were absent in PostgreSQL and original SQLite. Supabase itself was not paused during testing.

Next.js production build passed. All **five browser suites passed**, covering landing/CMS, catalogue, account/sandbox workspace, backoffice and password components with intercepted writes. An extended backoffice check also passed native invitation creation and notification-channel updates. Actual user and financial data were preserved.

Live providers remain unimplemented, manual synthetic reconciliation remains sandbox-only, and jurisdiction/policy approvals remain outstanding. Do not represent this simulated setup as production banking. Immutable existing ledger/contract/audit evidence was not rewritten during bootstrap or synchronization setup. Future PostgreSQL recovery conflicts require deliberate operator reconciliation; automatic force resolution is intentionally absent.
