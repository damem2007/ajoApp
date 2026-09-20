# AJo target architecture

AJo remains a **FastAPI modular monolith**. The web client is a separate Next.js/TypeScript
repository and a future Flutter client can consume the same REST/OpenAPI contract. No Kubernetes,
microservices, GraphQL, service mesh, Kafka, distributed transactions or generated HTTP SDK are
part of this architecture.

## Runtime topology

```text
Next.js / future Flutter
          |
       REST/JSON
          |
      FastAPI API
          |
       PostgreSQL  <---- canonical source of truth
          |
   transactional outbox
          |
        Redis
      /   |    \
 payment notification reconciliation
 worker     worker       worker
             ^
             |
          scheduler (enqueues durable work)
```

The API, dispatcher, workers and scheduler use the same Python source and Docker image with
different commands. They are process roles, not network microservices.

## Domain ownership

FastAPI is authoritative for authentication/authorization, circles and membership, contribution
and payout rules, payment orchestration, ledger postings, reconciliation, provider selection,
financial state transitions, audit and backoffice/RBAC. The Next.js client owns presentation,
forms, browser/session concerns and compile-time API usage. Do not duplicate financial/domain rules
in Next.js or a future Dart client.

Existing modules are migrated incrementally rather than moved merely to match an aspirational
folder tree. Dedicated `ledger.py`, `payment_orchestration.py`, provider contracts, outbox,
workers and resilience boundaries provide the important separation without breaking stable imports.

## Providers and payment orchestration

`PaymentProvider`, `IdentityProvider` and `NotificationProvider` are normalized contracts.
Configuration selects registered adapters independently of database mode:

```dotenv
AJO_PAYMENTS_PROVIDER=sandbox
AJO_IDENTITY_PROVIDER=sandbox
AJO_NOTIFICATIONS_PROVIDER=sandbox
```

`PaymentOrchestrationService` sits above payment providers. External financial calls use provider
idempotency keys; reusing a key with a different request is rejected. Provider timeouts normalize to
Pending so reconciliation can determine the terminal state before another financial attempt.
External provider actions are not executed from degraded SQLite mode.

Ledger postings are append-oriented, balanced and idempotent by originating event key. Provider
responses do not directly become balances.

## Transactional outbox and workers

Domain changes and their `OutboxEvent` are committed in the same transaction. Redis transports
event IDs only; the database record is authoritative. Dispatch is at-least-once and
`WorkerReceipt` makes worker handling idempotent.

Runtime roles:

```text
api
outbox-dispatcher
payment-worker
notification-worker
reconciliation-worker
scheduler
postgres
redis
```

The scheduler enqueues payment and reconciliation scans. It does not execute long-running provider
work itself. Payment/notification workers do not consume work while PostgreSQL is unavailable.

## PostgreSQL and SQLite degraded mode

PostgreSQL is canonical. SQLite is **not** an equal database and there is no generic PostgreSQL <->
SQLite active-active replication.

`sync-init` creates a certified, non-authoritative SQLite snapshot. While PostgreSQL is healthy,
normal reads/writes use PostgreSQL; successful primary changes may refresh that certified snapshot
one-way so it is usable during an outage.

When PostgreSQL is unavailable, safe application mutations may run against the certified snapshot
only to preserve the local transaction. The same SQLite transaction writes an encrypted
`DegradedOperation` journal record containing an event ID, operation/aggregate information,
idempotency key, sequence, status, retry metadata and the deterministic before/after mutation
payload. Risky external-provider actions are paused.

When PostgreSQL returns, normal routed writes remain blocked until the reconciliation worker replays
the SQLite journal **toward PostgreSQL only**. Reconciliation uses compare-before-write and a
PostgreSQL `DegradedOperationReceipt` for exactly-once application. Results are classified as:

```text
SUCCESS
ALREADY_PROCESSED
CONFLICT
INVALID
FAILED_RETRYABLE
FAILED_PERMANENT
```

CONFLICT/INVALID/FAILED_PERMANENT remain quarantined for review. There is no last-write-wins
resolution. After a clean replay, SQLite is refreshed from PostgreSQL and becomes a certified
non-authoritative snapshot again.

Legacy `sync_batches` / `sync_receipts` tables remain only for non-destructive migration
compatibility; the target degraded-mode path uses `degraded_operations` and
`degraded_operation_receipts`.

## API contract synchronization

FastAPI/Pydantic is the API-contract source of truth. `scripts/export_openapi.py` exports
`app.openapi()` deterministically. The separate frontend repository uses `openapi-typescript` to
generate committed type-only definitions in `src/generated/api-types.ts`.

The frontend keeps its handwritten `src/lib/api/*` HTTP functions. Stable generated contracts such
as `CircleSetupResponse` and `PlanPreview` are imported from the generated file rather than
duplicated manually.

Frontend commands:

```bash
npm run api:types
npm run api:types:check
npm run typecheck
npm run build
```

The drift check regenerates into a temporary file and fails when committed types differ. CI never
silently updates the contract.

## Bootstrap and test data

Normal startup creates required system/reference/RBAC configuration and, when all
`SUPERADMIN_*` settings are supplied, exactly one idempotent Super Admin. It does not create
ordinary demo members, circles or sample transactions.

Explicit test users are created through `tests/cli` using normal HTTP registration,
verification, KYC, bank and circle workflows. They are tagged with `source=test_cli`,
`is_test_account`/`is_test_data` and a UUID `test_run_id`. The CLI refuses production.
Cleanup selects only those explicit tags and never deletes an administrator.

```bash
APP_ENV=test python -m tests.cli.create_test_clients --count 10
APP_ENV=test python -m tests.cli.create_test_scenario --clients 10 --circles 3 --members-per-circle 5
APP_ENV=test python -m tests.cli.cleanup_test_data --run-id <uuid>
```

## Local/container workflow

```bash
cp .env.example .env
python -m alembic upgrade head
python -m app.platform.cli sync-init   # once, only when resilience is enabled
docker compose up --build
```

`compose.yaml` runs PostgreSQL, Redis, migrations, API, outbox dispatcher, payment worker,
notification worker, reconciliation worker and scheduler. Apply migrations before enabling a new
fallback file.
