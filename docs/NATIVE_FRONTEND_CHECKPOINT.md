# Native frontend and environment checkpoint

The user-approved StockData-style architecture uses native App Router TSX screens, named typed API resources and shared session/toast providers. CMS is a backoffice submodule. The legacy HTML/static handlers have now been retired after functional verification. Exact old rendering/controller source is preserved in sandbox/legacy-ui, outside public serving and deployment builds. There is no remaining approval block for this cleanup.

Database, API origin, server bindings and display preferences use validated environment configuration. User credentials remain unchanged in ignored backend/.env and frontend/.env.local. API, worker and migrations share database selection. PostgreSQL is reachable with the complete 23-table Ajo schema at migration 7bb13c20a6f9. The configured API runs on its environment-selected port; the original SQLite sandbox remains independent.

Verification: 43 Python tests passed with isolated databases; frontend configuration and TypeScript checks passed. Production build and all four browser suites passed after the final frontend changes, including checks against legacy asset-script loads and escaped CMS preview text. Browser mutations use intercepted fixtures. No historical signed agreements were rewritten. Docker definitions are environment-driven but Docker execution remains unverified on this host.

See ARCHITECTURE.md and CONFIGURATION.md for supported ownership and settings.

Active runtime: one configured frontend/API at ports 9520/9020. The redundant 3000/8000 listeners are stopped. `AJO_DATABASE_MODE` selects PostgreSQL or the retained SQLite database after restart, independently of simulated provider mode. All SQLite runtime users and related records were copied transactionally to PostgreSQL and verified. The original SQLite database and encryption key are retained. See DATABASE_SWITCH.md.

## September 18 database/setup checkpoint

Root `app` compatibility symlink retained at user request; canonical source is backend/app. Historical prototype API moved to sandbox/python_reference for isolated tests. Read-only SQLite workbench: ajo-data/query_sqlite.py. Structured circle setup is in backoffice/policies, with shared preview/create/edit enforcement. Verification: 46 backend tests; production frontend build; four existing browser suites plus expanded setup-editor coverage.

## Provider/resilience/backoffice continuation

Provider selection is now independent of database selection. The PostgreSQL runtime has a new dedicated SQLite mirror and transactional synchronization; original local test records are preserved. Staff invitations, persisted RBAC memberships/grants and notification channel setup are integrated into the native client. See [implementation report](PROVIDER_RESILIENCE_BACKOFFICE.md) and [legacy store analysis](STORE_MODELS_ANALYSIS.md) for configuration, migration, correctness boundaries and tests. Earlier statements that synchronization is absent describe the previous checkpoint.
