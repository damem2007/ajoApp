"""Database-enforced append-only evidence. Production DB roles must not own tables."""
from sqlalchemy import text
IMMUTABLE=['circle_contracts','contract_signatures','ledger_postings','payment_events','trust_events','platform_audit','policy_versions']
def install_guards(connection):
    if connection.dialect.name=='sqlite':
        for table in IMMUTABLE:
            for operation in ['UPDATE','DELETE']:
                connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only evidence'); END"))
    elif connection.dialect.name=='postgresql':
        connection.execute(text("CREATE OR REPLACE FUNCTION ajo_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only evidence'; END; $$"))
        for table in IMMUTABLE:
            connection.execute(text(f'DROP TRIGGER IF EXISTS immutable_{table} ON {table}'))
            connection.execute(text(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ajo_immutable()'))
