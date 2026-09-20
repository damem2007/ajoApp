# store.py investigation — analysis only

## Finding and evidence

`backend/app/store.py` defines a separate declarative `Base` and five SQLAlchemy ORM mapped classes using Column declarations. These are not standalone SQLAlchemy Core Table definitions. They are legacy reference-test infrastructure, not active production persistence. They are not the active platform models. Neither the configured PostgreSQL database nor the original `ajo-platform.db` contains these five tables (read-only inspection during this checkpoint). Their absence is consistent with the current migration target, rather than proof of missing production migrations.

| Prototype table / model | Prototype responsibility | Active replacement |
|---|---|---|
| users / User | pseudonym, approval, static scheme cap | accounts; policy_versions and score-derived participant limits |
| schemes / Scheme | rotating scheme state, amount, contract and period | circles; scheduled_payments, circle_contracts and contract_signatures |
| memberships / Membership | scheme membership, rank and signature flag | participants and contract_signatures |
| ledger_entries / LedgerEntry | simulated contribution/payout accounting | ledger_postings, scheduled_payments and payment_events |
| audit_events / AuditEvent | scheme event history | platform_audit |

These are conceptual mappings, not an approved field-level migration specification. The active tables have different identity, authorization, encryption and financial semantics.

`store.py:6` creates prototype metadata; `platform/models.py:7` creates independent platform metadata. `migrations/env.py` targets platform metadata. The only application imports of store.py are `make_engine` in `platform/application.py` and `platform/runtime.py`. They do not activate its prototype models.

`sandbox/python_reference/api.py:17` imports the five prototype models. Its explicit demo lifespan (`:59`) creates prototype tables for legacy reference tests. `tests/test_platform.py` uses this isolated reference implementation; active native-client features call the canonical platform API. `platform/application.py:28` creates **platform** tables only for explicit test-fixture construction, not default deployment startup. Production migrations do not create store.Base tables.

## Behavior and risks

The retired prototype API uses these ORM tables for its own users, schemes, signatures, simulated ledger and audit events. They are not fallback representations of current accounts or circles. Importing a mapped class alone does not create a table. Calling a prototype query against a platform-only database would produce a database missing-table error; using its fixture initializer there could create a second, incompatible identity domain. This would be an architectural mistake, not a repair.

The prototype has fewer constraints and fields than the active system. Its static `scheme_cap`, signature boolean and simulation ledger cannot safely substitute for current score policy, signed evidence or payment state. There is no active JSON financial persistence replacing these five tables. The encryption-key file is a secret-management artifact, not a users/circles database.

The shared engine factory residing alongside retired models makes the boundary less clear to maintainers. Legacy reference tests also continue to depend on this import path. Removing or moving the models without inspecting those imports would break those tests.

## Recommended future options — not implemented

1. Keep the prototype explicitly isolated and document that its schema is reference-test-only.
2. In a separately approved cleanup, move the engine factory into a neutral database module and move prototype mappings beside the reference API, with compatibility imports if necessary.
3. Only design a data migration if an actual legacy database with required business records is discovered. First inventory records and map identities, monetary semantics, contracts and immutable history; do not infer equivalence from similar table names.
4. Never add these tables to active Alembic metadata or call store.Base.create_all to hide a missing-table error.

**Scope confirmation:** this task made no changes to store.py and no migrations or schema remediation for its five tables. Git already showed changes to store.py from earlier checkpoints; those pre-existing changes were retained.
