# Application ownership and maintenance

The supported client is Next.js React, under `frontend/src`. Every application screen is TSX, reached through App Router pages. FastAPI owns data, authorization, financial rules, contracts, jobs and versioned policies. It returns JSON, uploaded evidence, PDFs or exports. Website URLs on the API redirect to the configured frontend. FastAPI has no frontend static mount and no HTML template renderer.

## Adding a feature

1. Define its request/response shape in `frontend/src/lib/types.ts`, or the domain's dedicated type file.
2. Add a named resource function in `frontend/src/lib/api/<domain>.ts`. The shared transport owns bearer tokens, coordinated refresh, field errors, multipart uploads and document downloads. React components do not assemble deployment addresses.
3. Implement its feature component under `frontend/src/components/<domain>/` and a small route page under `frontend/src/app/`. Member and staff layouts share session, notification and toast providers. The CMS belongs to `/backoffice/cms`.
4. Add authoritative validation and authorization in the relevant `backend/app/platform` API/domain module. Keep money in integer minor units; freeze signed schedules and policy versions.
5. Verify behavior in isolated sandbox API/browser fixtures. Do not use local database credentials in tests.

The public and member marketplaces share one catalogue component and API resource. Independent debit and payout calendars use contribution-first input and funding validation. Immutable historical contracts are never rewritten to match new defaults.

## Assets and legacy references

`frontend/public/assets` contains styles, fonts, icons and the install manifest; it contains no handwritten UI JavaScript or HTML templates. Next.js compiles TS/TSX into browser JavaScript under `_next`. The browser service worker is generated from `frontend/src/workers/service-worker.ts` before dev/build and registered by `PwaRegistration.tsx`. It does not cache financial or identity data.

`sandbox/legacy-ui` preserves the retired controllers, templates and old rendering source as reference only. They are excluded from production serving and container builds. The supported sandbox is the same native React UI against FastAPI synthetic providers. Original Python domain regression tests remain available.

## Configuration

`backend/app/config.py` loads `backend/.env` from a stable path, validates deployment settings and preserves process-variable precedence. API, worker, persistence and Alembic all use it. There is no embedded database address. Missing required settings raise actionable errors without printing credentials. Paths for encryption keys resolve relative to that environment file.

`frontend/src/lib/backend-origin.ts` validates the configured upstream for both the proxy and server-rendered CMS content. Browser API calls stay same-origin. `client-config.ts` reads the public polling interval and page size. The frontend launcher loads `.env.local` before selecting its host/port. There is no embedded API origin or listening port in application source.

Only non-secret public preferences may have the `NEXT_PUBLIC_` prefix. Next.js embeds these values at build time; rebuild when they change. Server-only environment changes require restarting the server. Route paths, formatting rules and security/domain constraints are code contracts, not deployment addresses. Open business questions belong to versioned backoffice policies rather than unvalidated environment switches.

See [configuration reference](CONFIGURATION.md). `compose.yaml` is the single deployment definition. Runtime and public build settings come from environment files. Docker execution has not been verified on this host.
