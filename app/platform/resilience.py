"""Single-writer routing with transactional, encrypted mutation batches.

Fallback is admitted only for a certified mirror. Recovery replays whole
transactions in sequence using compare-before-write and idempotent receipts.
Never retry a provider call or switch databases after a transaction has started.
"""
import base64
import logging
from contextlib import contextmanager
from threading import RLock
from sqlalchemy import select, text, func, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Delete
from sqlalchemy.exc import OperationalError, DBAPIError
from .models import Base, SyncBatch, SyncReceipt, SyncControl, now, uid, Policy
from .security import canonical

EXCLUDED = {'sync_batches','sync_receipts','sync_control','outbox_events','worker_receipts'}
log=logging.getLogger('ajo.sync')


def encode(value):
    if isinstance(value,(bytes,memoryview)): return {'__binary__':base64.b64encode(bytes(value)).decode()}
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
        super().__init__(*args,**kwargs);self.changes={};self.tracking=False

    def record(self,table,before,after):
        row=after or before
        key=(table.name,tuple(row[c.name] for c in table.primary_key))
        previous=self.changes.get(key)
        self.changes[key]={'table':table.name,'before':previous['before'] if previous else encode(before),'after':encode(after)}

    def execute(self,statement,*args,**kwargs):
        deleted=[]
        if self.tracking and isinstance(statement,Delete) and statement.table.name not in EXCLUDED:
            self.flush()
            deleted=list(self.connection().execute(select(statement.table).where(*([statement.whereclause] if statement.whereclause is not None else []))).mappings())
        result=super().execute(statement,*args,**kwargs)
        for row in deleted: self.record(statement.table,dict(row),None)
        return result


@event.listens_for(TrackedSession,'before_flush')
def capture_before(db,context,instances):
    if not db.tracking: return
    captured=[]
    for obj in list(db.new)+list(db.dirty)+list(db.deleted):
        state=inspect(obj);table=state.mapper.local_table
        if table.name in EXCLUDED or (obj in db.dirty and not db.is_modified(obj,include_collections=False)): continue
        before=None
        if state.identity:
            clause=[c==v for c,v in zip(table.primary_key,state.identity)]
            old=db.connection().execute(select(table).where(*clause)).mappings().first()
            before=dict(old) if old else None
        # Stable, disjoint fallback IDs for the existing integer policy PK.
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
        self.primary=primary;self.secondary=secondary;self.vault=vault;self.lock=RLock();self.mode='postgres';self.verified=False

    @contextmanager
    def process_lock(self):
        # API and worker on this host share the same fallback volume. Hold a
        # process-wide fence through primary commit AND mirror certification.
        import fcntl
        import os
        from pathlib import Path
        filename=self.secondary.url.database
        if not filename or filename==':memory:': raise ValueError('Fallback requires a durable SQLite file')
        lockfile=Path(filename).resolve().with_suffix('.sync.lock')
        lockfile.parent.mkdir(parents=True,exist_ok=True)
        with os.fdopen(os.open(str(lockfile),os.O_CREAT|os.O_RDWR,0o600),'a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(handle,fcntl.LOCK_UN)

    def control(self,state,detail=None):
        with Session(self.secondary) as db,db.begin():
            row=db.get(SyncControl,'mirror')
            if row: row.state=state;row.detail=detail;row.updated_at=now()
            else: db.add(SyncControl(id='mirror',state=state,detail=detail))

    def bootstrap(self):
        """Initialize only an empty fallback database, under the primary writer lock."""
        tables=[t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED]
        with self.primary.connect() as src, self.secondary.begin() as dst:
            transaction=src.begin()
            if self.primary.dialect.name=='postgresql': src.execute(text('SELECT pg_advisory_xact_lock(714206)'))
            if dst.execute(select(SyncControl).where(SyncControl.id=='mirror')).first(): raise ValueError('Fallback is already initialized')
            if any(dst.execute(select(func.count()).select_from(t)).scalar() for t in tables if t.name not in {'notification_channels','staff_roles'}): raise ValueError('Initialize a new empty fallback database; existing records are never overwritten')
            for table in tables:
                rows=[dict(row) for row in src.execute(select(table)).mappings()]
                if rows:
                    if table.name in {'notification_channels','staff_roles'}:
                        dst.execute(table.delete())
                    dst.execute(table.insert(),rows)
            dst.execute(SyncControl.__table__.insert().values(id='mirror',state='ready',updated_at=now()))
            transaction.commit()

    def verify_mirror(self):
        """Detect independent writers or an ambiguous primary commit; never overwrite."""
        with self.primary.connect() as primary, self.secondary.connect() as secondary:
            for table in Base.metadata.sorted_tables:
                if table.name in EXCLUDED: continue
                query=select(table).order_by(*table.primary_key.columns)
                left=[encode(dict(row)) for row in primary.execute(query).mappings()]
                right=[encode(dict(row)) for row in secondary.execute(query).mappings()]
                if left!=right:
                    self.control('unsafe','mirror_diverged')
                    raise SyncConflict('mirror_diverged')
        self.verified=True

    def replay(self,source,target):
        with Session(source) as src:
            batches=list(src.scalars(select(SyncBatch).where(SyncBatch.status.in_(['pending','failed','conflict'])).order_by(SyncBatch.sequence,SyncBatch.created_at,SyncBatch.id)))
        for batch in batches:
            try:
                import json
                changes=json.loads(self.vault.open(batch.changes['payload']))
                with target.begin() as dst:
                    if target.dialect.name=='postgresql': dst.execute(text('SELECT pg_advisory_xact_lock(714206)'))
                    receipt=dst.execute(select(SyncReceipt.__table__).where(SyncReceipt.id==batch.id)).first()
                    if not receipt:
                        for change in changes:
                            table=Base.metadata.tables[change['table']]
                            before=decode(change['before']);after=decode(change['after']);row=after or before
                            clause=[c==row[c.name] for c in table.primary_key]
                            existing=dst.execute(select(table).where(*clause)).mappings().first()
                            current=dict(existing) if existing else None
                            if current==after: continue
                            if current!=before: raise SyncConflict('row_changed')
                            if after is None: dst.execute(table.delete().where(*clause))
                            elif current is None: dst.execute(table.insert().values(**after))
                            else: dst.execute(table.update().where(*clause).values(**after))
                        dst.execute(SyncReceipt.__table__.insert().values(id=batch.id,source=batch.source,applied_at=now()))
                        if target.dialect.name=='postgresql':
                            dst.execute(text("SELECT setval(pg_get_serial_sequence('policy_versions','id'), GREATEST((SELECT COALESCE(MAX(id),1) FROM policy_versions WHERE id < 1000000000),1), true)"))
                with Session(source) as src,src.begin():
                    row=src.get(SyncBatch,batch.id);row.status='synced';row.synced_at=now();row.attempts+=1;row.error_code=None
            except Exception as error:
                with Session(source) as src,src.begin():
                    row=src.get(SyncBatch,batch.id);row.status='conflict' if isinstance(error,SyncConflict) else 'failed';row.attempts+=1;row.error_code='row_changed' if isinstance(error,SyncConflict) else 'replay_failed'
                log.warning('sync batch=%s status=%s',batch.id,'conflict' if isinstance(error,SyncConflict) else 'failed')
                raise

    @contextmanager
    def session(self):
        from .services import fail
        with self.lock,self.process_lock():
            try:
                with self.primary.connect() as probe: probe.execute(text('SELECT 1'))
            except OperationalError:
                with Session(self.secondary) as local:
                    mirror=local.get(SyncControl,'mirror')
                    if not mirror or mirror.state!='ready': fail('Database fallback is not synchronized; writes are paused',503)
                engine=self.secondary;source='sqlite';self.mode='sqlite'
            else:
                try:
                    self.replay(self.secondary,self.primary)
                    self.replay(self.primary,self.secondary)
                    with Session(self.secondary) as local:
                        control=local.get(SyncControl,'mirror')
                        unsafe=control is None or control.state!='ready'
                    if not self.verified or self.mode=='sqlite' or unsafe: self.verify_mirror()
                except Exception: fail('Database synchronization requires reconciliation; writes are paused',503)
                self.control('ready');engine=self.primary;source='postgres';self.mode='postgres'
            # A failed PostgreSQL commit/replication leaves the mirror uncertified.
            if source=='postgres': self.control('unsafe','primary_transaction_in_progress')
            with TrackedSession(engine) as db:
                if engine.dialect.name=='sqlite': db.execute(text('BEGIN IMMEDIATE'))
                else: db.execute(text('SELECT pg_advisory_xact_lock(714206)'))
                db.info['sync_source']=source;db.tracking=True
                try:
                    yield db
                    db.flush()
                    changes=[v for v in db.changes.values() if v['before']!=v['after']]
                    order={table.name:i for i,table in enumerate(Base.metadata.sorted_tables)}
                    changes.sort(key=lambda change: (change['after'] is None, -order[change['table']] if change['after'] is None else order[change['table']]))
                    if changes:
                        sequence=(db.scalar(select(func.max(SyncBatch.sequence))) or 0)+1
                        db.add(SyncBatch(id=uid(),sequence=sequence,source=source,changes={'payload':self.vault.seal(canonical(changes))},status='pending'))
                    db.tracking=False;db.commit()
                except Exception:
                    db.rollback()
                    # A confirmed rollback is safe; ambiguous connection failures are not.
                    import sys
                    error=sys.exc_info()[1]
                    if source=='postgres' and not isinstance(error,DBAPIError): self.control('ready')
                    raise
            if source=='postgres':
                try: self.replay(self.primary,self.secondary);self.control('ready')
                except Exception:
                    # Primary commit has succeeded. Do not report a failure that invites
                    # repeating a money operation. Fallback stays blocked until replay.
                    log.warning('mirror refresh pending; fallback blocked')
