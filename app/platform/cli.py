"""Local administration. Never creates a predictable production credential."""
import argparse
import getpass
import os
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
    parser.add_argument('command',choices=['init-admin','seed-demo','worker'])
    parser.add_argument('--email')
    parser.add_argument('--phone')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    app=create_platform();ctx=app.state.ctx
    if not ctx.vault: parser.error('Configure AJO_KEY_FILE first')
    if ctx.sandbox: Base.metadata.create_all(ctx.engine)
    with Session(ctx.engine) as db,db.begin(): seed_policy(db,ctx.sandbox)
    if args.command=='worker':
        ctx.require_sandbox()
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
            time.sleep(30)
        return
    if args.command=='seed-demo':
        ctx.require_sandbox();password=secret()
        with Session(ctx.engine) as db,db.begin():
            for i,(name,role) in enumerate([('Amber Heron','member'),('Cedar Finch','member'),('Indigo Fox','member'),('Platform Admin','admin')]):
                email=f'{["amber","cedar","indigo","admin"][i]}@ajo.test'
                if db.scalar(select(Account.id).where(Account.email==email)): continue
                u=Account(email=email,phone=f'+1555555000{i}',password=password_hash(password),email_verified=True,
                          phone_verified=True,kyc_status='Approved',pseudonym=name,role=role)
                db.add(u);db.flush();token='sandbox-ok-'+u.id
                db.add(Bank(user_id=u.id,token_hash=ctx.vault.fingerprint(token),encrypted_token=ctx.vault.seal(token),
                            masked='•••• 000'+str(i),status='Verified',mandate=True))
                audit(db,'local-cli',u.id,'sandbox_fixture_created')
                print('Created:',email)
        print('Password for newly created sandbox accounts:',password)
        return
    if not args.email or not args.phone: parser.error('--email and --phone are required')
    password=getpass.getpass('New administrator password (12+ characters): ')
    if len(password)<12: parser.error('Password must be at least 12 characters')
    with Session(ctx.engine) as db,db.begin():
        if db.scalar(select(Account.id).where(Account.email==args.email.lower())): parser.error('Account already exists')
        u=Account(email=args.email.lower(),phone=args.phone,password=password_hash(password),role='admin')
        db.add(u);db.flush();audit(db,'local-cli',u.id,'administrator_created')
    print('Administrator created. Complete channel verification and MFA before live staff access.')

if __name__=='__main__': main()
