"""Local administration. Never creates a predictable production credential."""
import argparse
import getpass
from contextlib import contextmanager
from app.config import worker_interval_seconds
import time
from sqlalchemy.orm import Session
from sqlalchemy import select
from .models import Base,Account,Bank
from .security import password_hash,secret
from .services import seed_policy,audit
from .application import create_platform
from .payments import run_due,dispatch_notices

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init-admin','seed-demo','worker','sync-init','sync-status','sync-retry'])
    parser.add_argument('--email')
    parser.add_argument('--phone')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    app=create_platform();ctx=app.state.ctx
    if not ctx.vault: parser.error('Configure AJO_KEY_FILE first')
    if args.command in {'init-admin','seed-demo'}:
        with contextmanager(ctx.session)() as db: seed_policy(db,False)
    if args.command=='sync-status':
        if not ctx.router: parser.error('Database resilience is not enabled')
        from .models import SyncBatch, SyncControl
        for name,engine in [('postgres',ctx.engine),('sqlite',ctx.router.secondary)]:
            try:
                with Session(engine) as db:
                    mirror=db.get(SyncControl,'mirror')
                    print(name,'mirror:',mirror.state if mirror else 'authoritative_primary' if name=='postgres' else 'not_initialized')
                    for batch in db.scalars(select(SyncBatch).where(SyncBatch.status!='synced').order_by(SyncBatch.sequence)):
                        print(batch.id,batch.sequence,batch.status,batch.attempts,batch.error_code)
            except Exception: print(name,'unavailable')
        return
    if args.command=='sync-retry':
        if not ctx.router: parser.error('Database resilience is not enabled')
        with ctx.router.lock,ctx.router.process_lock():
            ctx.router.replay(ctx.router.secondary,ctx.engine)
            ctx.router.replay(ctx.engine,ctx.router.secondary)
            ctx.router.verify_mirror()
            ctx.router.control('ready')
        print('Pending synchronization replayed')
        return
    if args.command=='sync-init':
        if not ctx.router: parser.error('Enable AJO_DATABASE_RESILIENCE with PostgreSQL and a configured fallback URL first')
        from alembic.config import Config
        from alembic import command
        cfg=Config('alembic.ini')
        with ctx.router.secondary.begin() as connection:
            cfg.attributes['connection']=connection
            command.upgrade(cfg,'head')
        ctx.router.bootstrap()
        print('SQLite fallback initialized and certified')
        return
    if args.command=='worker':
        ctx.ensure_configured('payments');ctx.ensure_configured('notifications')
        interval = worker_interval_seconds() if not args.once else None
        while True:
            gen=ctx.session();db=next(gen)
            try:
                result=run_due(db,ctx);result['notices']=dispatch_notices(db,ctx)
                try: next(gen)
                except StopIteration: pass
                print(result,flush=True)
            except Exception:
                gen.close();raise
            if args.once: break
            time.sleep(interval)
        return
    if args.command=='seed-demo':
        ctx.require_sandbox();password=secret()
        with contextmanager(ctx.session)() as db:
            for i,(name,role) in enumerate([('Amber Heron','member'),('Cedar Finch','member'),('Indigo Fox','member'),('Platform Admin','admin')]):
                email=f'{["amber","cedar","indigo","admin"][i]}@ajo.test'
                if db.scalar(select(Account.id).where(Account.email==email)): continue
                u=Account(email=email,phone=f'+1555555000{i}',password=password_hash(password),email_verified=True,
                          phone_verified=True,kyc_status='Approved',pseudonym=name,role=role)
                db.add(u);db.flush();token='sandbox-ok-'+u.id
                db.add(Bank(user_id=u.id,token_hash=ctx.vault.fingerprint(token),encrypted_token=ctx.vault.seal(token),
                            masked='•••• 000'+str(i),status='Verified',mandate=True))
                if role!='member':
                    from .rbac import assign
                    assign(db,u,role,u)
                audit(db,'local-cli',u.id,'sandbox_fixture_created')
                print('Created:',email)
        print('Password for newly created sandbox accounts:',password)
        return
    if not args.email or not args.phone: parser.error('--email and --phone are required')
    password=getpass.getpass('New administrator password (12+ characters): ')
    if len(password)<12: parser.error('Password must be at least 12 characters')
    with contextmanager(ctx.session)() as db:
        if db.scalar(select(Account.id).where(Account.email==args.email.lower())): parser.error('Account already exists')
        u=Account(email=args.email.lower(),phone=args.phone,password=password_hash(password),role='admin')
        db.add(u);db.flush()
        from .rbac import assign
        assign(db,u,'admin',u)
        audit(db,'local-cli',u.id,'administrator_created')
    print('Administrator created. Complete channel verification and MFA before live staff access.')

if __name__=='__main__': main()
