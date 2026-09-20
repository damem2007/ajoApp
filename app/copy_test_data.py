"""Copy the configured SQLite runtime dataset into PostgreSQL without deleting data.

Run: PYTHONPATH=backend backend/.venv/bin/python -m app.copy_test_data
An existing, different row causes a rollback; immutable evidence is never updated.
Generated initial CMS pointers may be replaced with source pointers. Policy versions
are deduplicated by data and appended, leaving destination history intact.
"""
import hashlib
import json
from sqlalchemy import create_engine, select, text
from .config import setting
from .database import selected_database_url
from .platform.models import Base


def fingerprint(rows):
    encoded = [json.dumps(row, sort_keys=True, default=lambda v: {'bytes':bytes(v).hex()} if isinstance(v,(bytes,memoryview)) else str(v)) for row in rows]
    return hashlib.sha256('\n'.join(sorted(encoded)).encode()).hexdigest()


def main():
    source = create_engine(setting('AJO_SQLITE_DATABASE_URL'))
    target = create_engine(selected_database_url())
    if source.dialect.name != 'sqlite' or target.dialect.name != 'postgresql':
        raise ValueError('Select PostgreSQL as destination and configure SQLite as source.')
    # SQLite read-only consistent snapshot; no credentials or private row values printed.
    with source.connect() as src, target.begin() as dst:
        src.exec_driver_sql('PRAGMA query_only=ON')
        src.exec_driver_sql('BEGIN')
        dst.execute(text('SELECT pg_advisory_xact_lock(714206)'))
        report = {}
        for table in Base.metadata.sorted_tables:
            source_rows = [dict(row) for row in src.execute(select(table)).mappings()]
            destination_rows = [dict(row) for row in dst.execute(select(table)).mappings()]
            key = lambda row: tuple(row[column.name] for column in table.primary_key)
            destination = {key(row): row for row in destination_rows}
            pending = []
            for row in source_rows:
                existing = destination.get(key(row))
                if table.name == 'policy_versions':
                    if not any(v['data'] == row['data'] and v['reason'] == row['reason'] for v in destination_rows):
                        pending.append({k:v for k,v in row.items() if k!='id'})
                elif table.name == 'content_pages' and existing:
                    predicate = [column == row[column.name] for column in table.primary_key]
                    dst.execute(table.update().where(*predicate).values(**row))
                elif existing:
                    if existing != row:
                        raise ValueError('Conflicting existing record in ' + table.name + '; transaction rolled back.')
                else:
                    pending.append(row)
            if pending:
                dst.execute(table.insert(), pending)
            if table.name not in {'policy_versions', 'content_pages'}:
                verified = {key(dict(row)):dict(row) for row in dst.execute(select(table)).mappings()}
                if fingerprint(source_rows) != fingerprint([verified[key(row)] for row in source_rows]):
                    raise ValueError('Verification mismatch in ' + table.name)
            inserted = len(pending)
            report[table.name] = {'source_rows':len(source_rows),'inserted':inserted,'verified':True}
        src.rollback()
    print(json.dumps(report, indent=2))
    source.dispose(); target.dispose()

if __name__ == '__main__':
    main()
