"""PostgreSQL-authoritative degraded-mode operation journal.

PostgreSQL is always canonical. SQLite contains a certified non-authoritative
snapshot plus a durable journal of operations accepted while PostgreSQL is
unavailable. Recovery replays those journal entries exactly once through a
controlled reconciliation path. There is no generic bidirectional replication
and no last-write-wins conflict resolution.
"""
from __future__ import annotations

import base64
import json
import logging
from contextlib import contextmanager
from threading import RLock

from sqlalchemy import select, text, func, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Delete
from sqlalchemy.exc import OperationalError, DBAPIError

from .models import (
    Base, DegradedOperation, DegradedOperationReceipt, SyncControl, now, uid, Policy
)
from .security import canonical

JOURNAL_STATUSES={'PENDING','FAILED_RETRYABLE'}
BLOCKING_STATUSES={'CONFLICT','INVALID','FAILED_PERMANENT'}
EXCLUDED={
    'degraded_operations','degraded_operation_receipts','sync_batches','sync_receipts','sync_control'
}
log=logging.getLogger('ajo.reconciliation')


def encode(value):
    if isinstance(value,(bytes,memoryview)):
        return {'__binary__':base64.b64encode(bytes(value)).decode()}
    if isinstance(value,dict): return {k:encode(v) for k,v in value.items()}
    if isinstance(value,list): return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value,dict):
        if set(value)=={'__binary__'}: return base64.b64decode(value['__binary__'])
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list): return [decode(v) for v in value]
    return value


class SyncConflict(Exception): pass


class TrackedSession(Session):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.changes={}
        self.tracking=False

    def record(self,table,before,after):
        row=after or before
        key=(table.name,tuple(row[c.name] for c in table.primary_key))
        previous=self.changes.get(key)
        self.changes[key]={
            'table':table.name,
            'before':previous['before'] if previous else encode(before),
            'after':encode(after),
        }

    def execute(self,statement,*args,**kwargs):
        deleted=[]
        if self.tracking and isinstance(statement,Delete) and statement.table.name not in EXCLUDED:
            self.flush()
            deleted=list(self.connection().execute(
                select(statement.table).where(*([statement.whereclause] if statement.whereclause is not None else []))
            ).mappings())
        result=super().execute(statement,*args,**kwargs)
        for row in deleted: self.record(statement.table,dict(row),None)
        return result


@event.listens_for(TrackedSession,'before_flush')
def capture_before(db,context,instances):
    if not db.tracking: return
    captured=[]
    for obj in list(db.new)+list(db.dirty)+list(db.deleted):
        state=inspect(obj);table=state.mapper.local_table
        if table.name in EXCLUDED or (obj in db.dirty and not db.is_modified(obj,include_collections=False)):
            continue
        before=None
        if state.identity:
            clause=[c==v for c,v in zip(table.primary_key,state.identity)]
            old=db.connection().execute(select(table).where(*clause)).mappings().first()
            before=dict(old) if old else None
        if isinstance(obj,Policy) and obj in db.new and obj.id is None and db.info.get('sync_source')=='sqlite':
            maximum=max(db.scalar(select(func.max(Policy.id))) or 0,db.info.get('policy_id',0))
            obj.id=max(maximum+1,1_000_000_000)
            db.info['policy_id']=obj.id
        captured.append((obj,table,before,obj in db.deleted))
    db.info['captured']=captured


@event.listens_for(TrackedSession,'after_flush_postexec')
def capture_after(db,context):
    for obj,table,before,deleted in db.info.pop('captured',[]):
        after=None if deleted else {c.name:getattr(obj,c.name) for c in table.columns}
        db.record(table,before,after)


class DatabaseRouter:
    def __init__(self,primary,secondary,vault):
        self.primary=primary
        self.secondary=secondary
        self.vault=vault
        self.lock=RLock()
        self.mode='postgres'

    @contextmanager
    def process_lock(self):
        import fcntl, os
        from pathlib import Path
        filename=self.secondary.url.database
        if not filename or filename==':memory:':
            raise ValueError('Fallback requires a durable SQLite file')
        lockfile=Path(filename).resolve().with_suffix('.reconciliation.lock')
        lockfile.parent.mkdir(parents=True,exist_ok=True)
        with os.fdopen(os.open(str(lockfile),os.O_CREAT|os.O_RDWR,0o600),'a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(handle,fcntl.LOCK_UN)

    def control(self,state,detail=None):
        with Session(self.secondary) as db,db.begin():
            row=db.get(SyncControl,'snapshot')
            if row:
                row.state=state;row.detail=detail;row.updated_at=now()
            else:
                db.add(SyncControl(id='snapshot',state=state,detail=detail))

    def primary_available(self):
        try:
            with self.primary.connect() as connection:
                connection.execute(text('SELECT 1'))
            return True
        except (OperationalError,DBAPIError):
            return False

    def _tables(self):
        return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED]

    def _pending(self):
        with Session(self.secondary) as db:
            return list(db.scalars(
                select(DegradedOperation)
                .where(DegradedOperation.sync_status.in_(JOURNAL_STATUSES|BLOCKING_STATUSES))
                .order_by(DegradedOperation.sequence,DegradedOperation.created_at,DegradedOperation.id)
            ))

    def bootstrap(self):
        """Create a certified non-authoritative SQLite snapshot from PostgreSQL."""
        with self.lock,self.process_lock():
            self._replace_snapshot()
            self.control('ready','postgres_snapshot')

    def _replace_snapshot(self):
        with self.primary.connect() as src, self.secondary.begin() as dst:
            if self.primary.dialect.name=='postgresql':
                src.execute(text('SELECT pg_advisory_xact_lock(714206)'))
            pending=dst.execute(
                select(func.count()).select_from(DegradedOperation).where(
                    DegradedOperation.sync_status.in_(JOURNAL_STATUSES|BLOCKING_STATUSES)
                )
            ).scalar() or 0
            if pending:
                raise SyncConflict('journal_not_empty')
            tables=self._tables()
            for table in reversed(tables):
                dst.execute(table.delete())
            for table in tables:
                rows=[dict(row) for row in src.execute(select(table)).mappings()]
                if rows: dst.execute(table.insert(),rows)

    def _validate_changes(self,changes):
        if not isinstance(changes,list) or not changes:
            raise ValueError('empty_operation')
        for change in changes:
            if not isinstance(change,dict) or set(change)!={'table','before','after'}:
                raise ValueError('invalid_change_shape')
            if change['table'] not in Base.metadata.tables or change['table'] in EXCLUDED:
                raise ValueError('invalid_table')
            if change['before'] is None and change['after'] is None:
                raise ValueError('empty_change')

    def _apply_changes(self,connection,changes):
        self._validate_changes(changes)
        for change in changes:
            table=Base.metadata.tables[change['table']]
            before=change['before'];after=change['after'];row=after or before
            row=decode(row)
            clause=[c==row[c.name] for c in table.primary_key]
            existing=connection.execute(select(table).where(*clause)).mappings().first()
            current=encode(dict(existing)) if existing else None
            if current==after:
                continue
            if current!=before:
                raise SyncConflict('row_changed')
            if after is None:
                connection.execute(table.delete().where(*clause))
            elif current is None:
                connection.execute(table.insert().values(**decode(after)))
            else:
                connection.execute(table.update().where(*clause).values(**decode(after)))

    def _refresh_snapshot_changes(self,changes):
        # Incremental refresh is permitted only for a snapshot that was explicitly
        # initialized/certified from PostgreSQL. Never turn a partial SQLite file
        # into a certified fallback merely because a primary write succeeded.
        with Session(self.secondary) as db:
            control=db.get(SyncControl,'snapshot')
            if not control or control.state!='ready':
                return False
        with self.secondary.begin() as dst:
            self._apply_changes(dst,changes)
        self.control('ready','primary_refresh')
        return True

    def _record_operation(self,db,changes):
        first=changes[0]
        row=first['after'] or first['before'] or {}
        table=Base.metadata.tables[first['table']]
        decoded=decode(row)
        aggregate_id=':'.join(str(decoded.get(c.name,'')) for c in table.primary_key)
        event_id=uid()
        sequence=(db.scalar(select(func.max(DegradedOperation.sequence))) or 0)+1
        operation=DegradedOperation(
            id=event_id,
            operation_type=first['table']+'.transaction',
            aggregate_type=first['table'],
            aggregate_id=aggregate_id or None,
            payload={'sealed':self.vault.seal(canonical(changes))},
            idempotency_key='degraded:'+event_id,
            sequence=sequence,
            sync_status='PENDING',
        )
        db.add(operation)
        return operation

    def reconcile_pending(self,limit=100):
        """Replay SQLite journal operations to PostgreSQL and classify every result."""
        results=[]
        with self.lock,self.process_lock():
            with Session(self.secondary) as db:
                ids=list(db.scalars(
                    select(DegradedOperation.id)
                    .where(DegradedOperation.sync_status.in_(JOURNAL_STATUSES))
                    .order_by(DegradedOperation.sequence,DegradedOperation.created_at,DegradedOperation.id)
                    .limit(limit)
                ))
            if not ids:
                with Session(self.secondary) as db:
                    blocking=db.scalar(select(func.count()).select_from(DegradedOperation).where(
                        DegradedOperation.sync_status.in_(BLOCKING_STATUSES)
                    )) or 0
                if blocking:
                    self.control('quarantined','conflicting_operations_require_review')
                return results

            for event_id in ids:
                with Session(self.secondary) as local:
                    operation=local.get(DegradedOperation,event_id)
                    if not operation: continue
                    key=operation.idempotency_key
                    sealed=operation.payload.get('sealed') if isinstance(operation.payload,dict) else None
                result='SUCCESS';error_code=None
                try:
                    if not sealed: raise ValueError('missing_payload')
                    changes=json.loads(self.vault.open(sealed))
                    self._validate_changes(changes)
                    with self.primary.begin() as dst:
                        if self.primary.dialect.name=='postgresql':
                            dst.execute(text('SELECT pg_advisory_xact_lock(714206)'))
                        receipt=dst.execute(
                            select(DegradedOperationReceipt.__table__).where(
                                DegradedOperationReceipt.idempotency_key==key
                            )
                        ).first()
                        if receipt:
                            result='ALREADY_PROCESSED'
                        else:
                            self._apply_changes(dst,changes)
                            dst.execute(DegradedOperationReceipt.__table__.insert().values(
                                idempotency_key=key,event_id=event_id,applied_at=now()
                            ))
                except SyncConflict:
                    result='CONFLICT';error_code='row_changed'
                except (OperationalError,DBAPIError):
                    result='FAILED_RETRYABLE';error_code='database_unavailable'
                except ValueError as exc:
                    result='INVALID';error_code=str(exc)[:120]
                except Exception as exc:
                    result='FAILED_PERMANENT';error_code=type(exc).__name__
                with Session(self.secondary) as local,local.begin():
                    operation=local.get(DegradedOperation,event_id)
                    operation.retry_count+=1
                    operation.result=result
                    operation.last_error=error_code
                    operation.sync_status=result
                    if result in {'SUCCESS','ALREADY_PROCESSED'}:
                        operation.synced_at=now()
                log.info('reconciliation event_id=%s result=%s',event_id,result)
                results.append({'event_id':event_id,'result':result})

            with Session(self.secondary) as db:
                blocking=db.scalar(select(func.count()).select_from(DegradedOperation).where(
                    DegradedOperation.sync_status.in_(JOURNAL_STATUSES|BLOCKING_STATUSES)
                )) or 0
            if blocking:
                self.control('quarantined','pending_or_conflicting_operations')
            else:
                self._replace_snapshot()
                self.control('ready','reconciled')
                self.mode='postgres'
        return results

    def status(self):
        with Session(self.secondary) as db:
            control=db.get(SyncControl,'snapshot')
            counts={}
            for status,count in db.execute(
                select(DegradedOperation.sync_status,func.count()).group_by(DegradedOperation.sync_status)
            ):
                counts[status]=count
            return {'mode':self.mode,'snapshot':control.state if control else 'not_initialized','operations':counts}

    @contextmanager
    def session(self):
        from .services import fail
        with self.lock,self.process_lock():
            try:
                with self.primary.connect() as probe: probe.execute(text('SELECT 1'))
            except (OperationalError,DBAPIError):
                with Session(self.secondary) as local:
                    snapshot=local.get(SyncControl,'snapshot')
                    if not snapshot or snapshot.state!='ready':
                        fail('Database fallback snapshot is not certified; writes are paused',503)
                engine=self.secondary;source='sqlite';self.mode='sqlite'
            else:
                with Session(self.secondary) as local:
                    pending=local.scalar(select(func.count()).select_from(DegradedOperation).where(
                        DegradedOperation.sync_status.in_(JOURNAL_STATUSES|BLOCKING_STATUSES)
                    )) or 0
                if pending:
                    fail('Database recovery is pending reconciliation; writes are paused',503)
                engine=self.primary;source='postgres';self.mode='postgres'

            with TrackedSession(engine) as db:
                if engine.dialect.name=='sqlite': db.execute(text('BEGIN IMMEDIATE'))
                else: db.execute(text('SELECT pg_advisory_xact_lock(714206)'))
                db.info['sync_source']=source;db.tracking=True
                try:
                    yield db
                    db.flush()
                    changes=[v for v in db.changes.values() if v['before']!=v['after']]
                    order={table.name:i for i,table in enumerate(Base.metadata.sorted_tables)}
                    changes.sort(key=lambda change:(change['after'] is None,
                        -order[change['table']] if change['after'] is None else order[change['table']]))
                    if source=='sqlite' and changes:
                        self._record_operation(db,changes)
                    db.tracking=False
                    db.commit()
                except Exception:
                    db.rollback();raise

            if source=='postgres' and changes:
                try:
                    self._refresh_snapshot_changes(changes)
                except Exception:
                    self.control('unsafe','snapshot_refresh_failed')
                    log.warning('SQLite degraded snapshot refresh failed; degraded mode blocked until sync-init')
