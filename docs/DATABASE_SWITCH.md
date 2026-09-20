# One application, two database choices

All active server code lives in `backend/app`. The historical prototype API is retained only under `tests/legacy_reference` for isolated regression tests. The root `app` entry is only a compatibility
symlink to that folder. The same Next.js and FastAPI applications work with either
SQLite or PostgreSQL; no separate sandbox application source is maintained.

Change **backend/.env**, then restart the API and any worker:

```dotenv
AJO_DATABASE_MODE=postgres
# DATABASE_URL already contains the PostgreSQL credentials.
AJO_SQLITE_DATABASE_URL=sqlite:////absolute/path/to/ajo-platform.db
AJO_PROVIDER_MODE=simulated
```

Set `AJO_DATABASE_MODE=sqlite` when PostgreSQL is paused. Set it back to `postgres`
when available. Database selection is in `backend/app/database.py`; secrets stay
in environment files. Without AJO_DATABASE_RESILIENCE, explicit database switching has no automatic
synchronization. Changes made in one independently selected database are
not silently written to the other. API URL and frontend configuration stay the
same when the API is restarted on its usual port.

`AJO_PROVIDER_MODE` independently selects simulated or unconfigured integrations.
PostgreSQL can run simulated providers, and SQLite can use unconfigured providers.
This setting does not enable live payment adapters. `AJO_DEMO_MODE` remains a
compatibility alias only when the explicit provider setting is absent.
`AJO_PLATFORM_DATABASE_URL` remains an explicit process override for tests/tools.
The encryption key must remain the same to read the copied MFA/bank/identity data.

## Copy runtime test data

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.copy_test_data
```

Select PostgreSQL before copying. The copy reads a consistent SQLite snapshot,
uses one PostgreSQL transaction, preserves IDs/password hashes/encrypted fields,
and verifies all matching runtime rows. Different existing records cause a
rollback. Initial CMS pointers are switched to the copied revisions; existing
revisions remain. Policy versions are deduplicated and appended; immutable
contracts, signatures and ledger rows are never updated or deleted.
This is an explicit initial test-data copy, not a continuous replication service.

## Backoffice configuration

Backoffice → Policies contains the structured **Circle configuration** editor.
Admins control currency choices/default, name lengths, monetary limits, member
limits, enabled contribution/payout frequencies and their defaults. A save creates
an audited policy version. The circle wizard loads these settings from the API;
preview, create and edit validate the same settings on the server. Existing signed
contracts retain their frozen rules. Overflow remains disabled under the agreed
rule that a cycle cannot exceed its planned membership.

Generous transport bounds still protect request sizes and integer storage. They
are safety ceilings, not the business limits edited in backoffice.

Backoffice → Policies also provides **Circle-participant config** for trust-score thresholds and concurrent circle commitment caps. Admin-only saves create an audited policy version and preserve other settings. A score-zero tier is required. Lowered limits govern new commitments; existing memberships are not removed.

## Certified PostgreSQL fallback

Opt-in `AJO_DATABASE_RESILIENCE=true` adds a dedicated SQLite mirror while
`AJO_DATABASE_MODE=postgres` remains authoritative. This mirror is distinct from
the original independently selected SQLite test database. Configure
`AJO_FALLBACK_DATABASE_URL`, migrate the primary and run `sync-init` once against
a new fallback file. API and worker must share its durable volume and process
lock. Recovery uses transactional encrypted batches, idempotent receipts and
compare-before-write conflict detection. See
[provider and resilience report](PROVIDER_RESILIENCE_BACKOFFICE.md) for commands,
deployment boundaries and operator reconciliation.
