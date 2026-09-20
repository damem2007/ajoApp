# Configuration reference

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env.local`, then supply the real database and API addresses. These local files are ignored by Git and container build contexts. Existing files and credentials are preserved. Exported variables override local file values.

| Setting | Consumer | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | API, worker, Alembic | Required PostgreSQL or SQLite URL; PostgreSQL uses psycopg. |
| `AJO_PLATFORM_DATABASE_URL` | Same | Optional explicit override, useful for isolated sandbox storage. |
| `FRONTEND_URL` | FastAPI | Required frontend origin; website URLs redirect here. |
| `AJO_FRONTEND_ORIGIN` | FastAPI | Optional override of `FRONTEND_URL`. |
| `CORS_ALLOWED_ORIGINS` | FastAPI | Optional comma-separated additional origins; the configured frontend is included. |
| `AJO_DEMO_MODE` | FastAPI/worker | Required true/false; true selects synthetic providers. |
| `AJO_DATA_DIR` | Sandbox encryption | Required when sandbox mode has no mounted key; relative to backend/.env. |
| `AJO_KEY_FILE` | Document/token encryption | Optional mounted key, required for encrypted account workflows outside sandbox. |
| `AJO_API_HOST`, `AJO_API_PORT` | `python -m app.serve` | Required listening host and port. |
| `REFRESH_INTERVAL_SECONDS` | Sandbox worker | Worker interval. `AJO_WORKER_INTERVAL_SECONDS` overrides it. |
| `NEXT_PUBLIC_API_BASE_URL` | Next.js proxy/CMS reads | Required upstream origin, optionally ending in /api/v1. |
| `AJO_API_ORIGIN` | Next.js server | Optional server-only override of the API base URL. |
| `NEXT_PUBLIC_REFRESH_INTERVAL_SECONDS` | Notification bell | Required positive polling interval; polling is cleaned up when unmounted. |
| `NEXT_PUBLIC_DEFAULT_PAGE_SIZE` | Notification dropdown | Required positive item limit; unread count covers all notifications. |
| `FRONTEND_HOST`, `FRONTEND_PORT` | `npm run dev/start` | Required frontend listening address, loaded before startup. |
| `AJO_NEXT_DIST_DIR` | Next.js | Optional isolated build directory. |
| `AJO_CONTAINER_DATA_DIR` | Compose | Writable shared encryption-key directory in API/worker containers. |
| `AJO_CONTAINER_BIND_HOST` | Compose | Container listening interface; host port bindings still use AJO_API_HOST/FRONTEND_HOST. |

Unrelated StockData JWT, local-root and SMTP fields present in copied environment files do not enable Ajo authentication or live delivery adapters. Ajo currently uses its own revocable sessions, explicit administrator initialization and synthetic sandbox delivery. No automatic account or provider change is inferred from those fields.

## Run

From the repository root:

```sh
backend/.venv/bin/alembic upgrade head
backend/.venv/bin/python -m app.serve
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
# Production:
npm run build
npm run start
```

Use the configured frontend URL. Database/host changes require restart; public frontend settings require rebuild. For sandbox testing, set `AJO_DEMO_MODE=true` and select a separate database with `AJO_PLATFORM_DATABASE_URL`. `pytest` overrides deployment credentials before application imports and uses isolated databases.

## Verify

```sh
backend/.venv/bin/python -m pytest -q
cd frontend
npm run test:config
npm run typecheck
npm run build
# Choose the frontend under test; browser writes are intercepted fixtures.
AJO_UI_ORIGIN=http://localhost:9520 npm run test:ui
```

Install the Playwright browser with `npx playwright install chromium`, or provide `AJO_BROWSER_EXECUTABLE`. `AJO_PLAYWRIGHT_MODULE` optionally selects a host-provided Playwright runtime. No machine-specific browser path is embedded in tests.

## Containers

One canonical Compose file reads both files explicitly:

```sh
docker compose --env-file backend/.env --env-file frontend/.env.local run --rm api alembic upgrade head
docker compose --env-file backend/.env --env-file frontend/.env.local up --build
# Optional sandbox worker:
docker compose --env-file backend/.env --env-file frontend/.env.local --profile scheduler up --build
```

Docker execution remains unverified on this host. Both API and worker must retain access to the same encryption key when switching environments or databases containing existing encrypted evidence.

## Database selection checkpoint

See [DATABASE_SWITCH.md](DATABASE_SWITCH.md) for `AJO_DATABASE_MODE` and independent `AJO_PROVIDER_MODE`. This explicit selection supersedes older instructions that pair SQLite with demo mode. The configured PostgreSQL database now contains the copied SQLite runtime test accounts and their related records.

### Next.js development origins

`AJO_ALLOWED_DEV_ORIGINS` in `frontend/.env.local` supplies comma-separated hostnames/IP addresses to Next.js `allowedDevOrigins`, matching the configuration approach in StockData and BA Artifacts. Use hostnames without schemes, ports or paths. Restart the development server after changes. This is separate from FastAPI CORS and does not enable cross-origin API requests.
