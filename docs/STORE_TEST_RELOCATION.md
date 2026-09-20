# Legacy store relocation

`backend/app/store.py` has been removed. Its five legacy ORM classes now live in
`tests/store.py`; they have no production imports or migrations. The shared
engine factory now lives in `backend/app/database.py`, alongside database
selection. API and Context imports use that module. SQLite connection settings
and configured database behavior are unchanged.

The retired prototype API moved from `sandbox/python_reference` to
`tests/legacy_reference/api.py`. Its fixture factory requires an explicit database
and demo flag and has no global app. Regression fixtures use temporary databases
so tests do not change real account or financial data.

Sandbox means provider simulation, not test storage: the canonical FastAPI API
resolves providers against the same account, circle, payment and notification
records in configured PostgreSQL or SQLite. No sandbox-only user store is
selected, and no runtime tables or records were migrated, copied or deleted.
The existing certified fallback and its synchronization remain unchanged.

The earlier STORE_MODELS_ANALYSIS.md records the investigation before relocation;
its paths describe that historical checkpoint. This approved cleanup supersedes
its recommendation to keep declarations in place pending approval.
