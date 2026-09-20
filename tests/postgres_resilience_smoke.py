import tempfile,uuid
from pathlib import Path
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.platform.application import create_platform
from app.platform.models import Base,Account,SyncBatch,SyncReceipt
from app.platform.resilience import DatabaseRouter
from app.platform.rbac import bootstrap
from app.platform.services import seed_policy
ctx=create_platform().state.ctx
schema='ajo_sync_test_'+uuid.uuid4().hex
with ctx.engine.begin() as db: db.execute(text('CREATE SCHEMA '+schema))
primary=create_engine(ctx.engine.url,connect_args={'options':'-csearch_path='+schema})
try:
    with tempfile.TemporaryDirectory() as tmp:
        secondary=create_engine('sqlite:///'+str(Path(tmp)/'fallback.db'))
        Base.metadata.create_all(primary);Base.metadata.create_all(secondary)
        with Session(primary) as db,db.begin(): seed_policy(db,True);bootstrap(db)
        router=DatabaseRouter(primary,secondary,ctx.vault);router.bootstrap()
        with router.session() as db: db.add(Account(id='pg-fixture',email='test@example.invalid',phone='+15555550199',password='test-only'))
        original=primary.connect
        def outage(*args,**kwargs): raise OperationalError('probe',None,Exception('simulated outage'))
        primary.connect=outage
        with router.session() as db: db.get(Account,'pg-fixture').pseudonym='Fallback fixture'
        with Session(secondary) as db: batch_id=db.scalar(select(SyncBatch.id))
        primary.connect=original
        with router.session() as db: assert db.get(Account,'pg-fixture').pseudonym=='Fallback fixture'
        with Session(secondary) as db,db.begin(): db.get(SyncBatch,batch_id).status='pending'
        router.replay(secondary,primary);router.verify_mirror()
        with Session(primary) as db: assert db.get(SyncReceipt,batch_id)
        secondary.dispose()
    print('Isolated real PostgreSQL schema: primary mirror, outage write, recovery, duplicate replay and equality passed')
finally:
    primary.dispose()
    with ctx.engine.begin() as db: db.execute(text('DROP SCHEMA '+schema+' CASCADE'))
