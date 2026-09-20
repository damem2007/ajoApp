# Ajo FastAPI backend

This repository is the backend Git root. Run commands from this directory.

## Local runtime

Create `.env` from `.env.example`, activate `.venv`, then:

```bash
python -m pip install -e '.[dev]'
python -m alembic upgrade head
python -m pytest
python -m app.serve
```

FastAPI owns authorization, financial rules, contracts, ledger state, jobs,
provider orchestration and versioned policies. PostgreSQL is the authoritative
normal-mode database. Optional SQLite resilience is a certified single-host
fallback/mutation journal; it is not an active-active peer.

Sandbox payments, identity and notifications are provider adapters selected
independently from database mode. `sandbox/legacy-ui` is archived UI reference
material only.

## Async runtime

Redis is transport only. Durable work is first committed to the database
`outbox_events` table and later published as event IDs. Run the same image/code
with separate process roles:

```bash
python -m app.platform.scheduler
python -m app.platform.dispatcher
python -m app.platform.workers payment
python -m app.platform.workers notification
python -m app.platform.workers reconciliation
```

`compose.yaml` defines PostgreSQL, Redis, API, migrations and these runtime
processes. Apply migrations before enabling database resilience. Initialize a
new SQLite fallback explicitly with:

```bash
python -m app.platform.cli sync-init
```

## API contracts

Export FastAPI OpenAPI without starting a server:

```bash
python scripts/export_openapi.py --output /tmp/ajo-openapi.json
```

The separate Next.js repository consumes this contract to generate TypeScript
API types while keeping its HTTP client handwritten.

See [architecture](docs/architecture.md), [configuration](docs/CONFIGURATION.md)
and [provider/resilience notes](docs/PROVIDER_RESILIENCE_BACKOFFICE.md).
