# Provider, degraded-mode resilience and backoffice

## Provider boundary

Sandbox is a provider mode, never a database mode. Payment, identity and notification adapters are
resolved through the provider registry. The business/domain layer depends on normalized provider
contracts. Live/future adapters can be registered without changing circle, ledger or payout rules.

The payment orchestration layer owns external transfer initiation/status/cancellation semantics.
Ledger postings remain internal, balanced and auditable. Reusing a payment idempotency key with a
different request is rejected.

## PostgreSQL-authoritative resilience

PostgreSQL is the canonical source of truth. SQLite is a certified non-authoritative degraded-mode
snapshot plus an encrypted operation journal; it is not a peer database.

Normal mode:
```text
application -> PostgreSQL
                    |
                    +-> one-way refresh of certified SQLite snapshot
```

Outage:
```text
safe local mutation -> certified SQLite snapshot
                     +-> degraded_operations journal (same transaction)
```

Recovery:
```text
degraded_operations
        |
reconciliation worker
        |
validate -> idempotency receipt -> compare-before-write
        |
PostgreSQL
        |
SUCCESS / ALREADY_PROCESSED / CONFLICT / INVALID /
FAILED_RETRYABLE / FAILED_PERMANENT
```

Only successful/already-processed operations are marked synchronized. Conflicts and unsafe records
are quarantined; there is no force overwrite and no last-write-wins policy. Once the journal is
clean, SQLite is rebuilt/refreshed from PostgreSQL.

Commands:

```bash
python -m alembic upgrade head
python -m app.platform.cli sync-init
python -m app.platform.cli sync-status
python -m app.platform.cli sync-retry
python -m app.platform.cli reconciliation-worker
```

The fallback file and its process lock must be on a shared durable volume for API/workers on the
same host. This mechanism is not multi-host high availability.

## Backoffice/RBAC and bootstrap

Backoffice authorization resolves persisted StaffMembership -> StaffRole -> permissions. UI
visibility is not authorization. Super Admin can onboard staff and assign supported roles through
the application. Normal startup never seeds ordinary members or circles.

The optional initial Super Admin is configured with `SUPERADMIN_EMAIL`, `SUPERADMIN_PHONE`,
`SUPERADMIN_USERNAME` and `SUPERADMIN_PASSWORD`. Creation is idempotent and password-hashed.
After initial onboarding these variables can be removed from deployment configuration.

## Notifications

Notification creation writes a Notice and transactional outbox event in the same database
transaction. Delivery happens in the notification worker. A notification-provider failure therefore
does not roll back the successful domain/financial transaction that caused the notification.

## Test data

The old generic demo-seed command is not part of the target path. Development/test users and circles
are generated explicitly through `tests/cli`; records carry test metadata and a UUID run ID.
Production test-data generation/cleanup is refused.
