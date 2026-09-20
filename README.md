# FastAPI backend

Start from the repository root with `backend/.venv/bin/python -m app.serve`. The launcher reads its database, host, port and frontend origin from `backend/.env` through `backend/app/config.py`. Alembic and workers use the same database settings; migrations run explicitly with `backend/.venv/bin/alembic upgrade head`.

Python domain modules stay in `backend/app/platform`. The root `app` symlink retains stable imports for scripts/tests. FastAPI returns API data and domain documents. Public UI URLs redirect to the configured Next.js frontend. There are no backend HTML renderers or frontend static mounts.

Run sandbox mode with an explicit separate database if required. Existing signed agreements and encrypted evidence need their original encryption key. Regression tests isolate databases before importing application modules.

See [architecture](../docs/ARCHITECTURE.md) and [configuration reference](../docs/CONFIGURATION.md).
