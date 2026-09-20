# Ajo FastAPI backend

This repository is the backend Git root. Run backend commands from this directory.

## Local setup

Create `.env` from `.env.example`, activate the backend virtual environment, then run:

```bash
python -m pip install -e '.[dev]'
python -m alembic upgrade head
python -m pytest
python -m app.serve
```

FastAPI owns authorization, circle and contract rules, financial state, provider orchestration,
backoffice/RBAC, transactional outbox processing, and the PostgreSQL/SQLite resilience layer.

PostgreSQL is the authoritative normal-mode database. SQLite resilience is an explicitly enabled
certified fallback/replay mechanism; it is not selected by sandbox provider mode and is not an
active-active peer.

Sandbox payments, identity and notifications are provider adapters selected independently from the
database mode.

## Async runtime

Redis transports durable outbox event IDs. PostgreSQL/SQLite database records remain authoritative.
The repository runs the API, outbox dispatcher, payment worker, notification worker, and scheduler
as separate process roles from the same codebase/image. See `compose.yaml`.

## Bootstrap

Normal startup creates required system configuration only. An initial administrator may be created
from the optional `SUPERADMIN_*` environment variables. Ordinary members, circles, and payment
fixtures are not created by bootstrap.

## API contract

Export the FastAPI contract without starting a web server:

```bash
python scripts/export_openapi.py --output /tmp/ajo-openapi.json
```

The separate Next.js repository consumes this contract for TypeScript API type synchronization.

See [architecture](docs/architecture.md), [configuration](docs/CONFIGURATION.md), and
[provider/resilience notes](docs/PROVIDER_RESILIENCE_BACKOFFICE.md).
