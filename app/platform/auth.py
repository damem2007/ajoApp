import base64
import json
import secrets
import time
from datetime import date
from typing import Optional
from app.config import setting, app_environment
from fastapi import APIRouter, Depends, Request, UploadFile, File, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, delete
from .models import Account, SessionToken, Challenge, RateLimit, IdentityCase, Document, Bank, Notice, DataRequest
from .schemas import Register, Login, Verify, KYCInput, BankInput, Preferences, Input
from .security import secret, digest, password_hash, password_ok, verify_totp, canonical
from .services import get, rows, fail, audit, notify, account_view, policy, eligible


defaultThrottleLimit = int(setting('THROTTLE_LIMIT', required=False) or '5')
defaultThrottleWindow = int(setting('THROTTLE_WINDOW', required=False) or '300')

def routes(ctx):
    router=APIRouter(prefix='/api/v1',tags=['Identity'])
    dbdep=ctx.session
    #print(f"throttleLimit: {defaultThrottleLimit}")
    #print(f"throttleWindow: {defaultThrottleWindow}")

    def token_pair(db,user):
        access,refresh=secret(),secret()
        db.add(SessionToken(token_hash=digest(access),refresh_hash=digest(refresh),user_id=user.id,
                            expires=int(time.time())+900,refresh_expires=int(time.time())+86400*7))
        return dict(access_token=access,refresh_token=refresh,token_type='bearer',expires_in=900,user=account_view(db,user))

    def throttle(db,key,limit=defaultThrottleLimit,seconds=defaultThrottleWindow):
        k=digest(key); row=db.get(RateLimit,k); now=int(time.time())
        if not row:
            row=RateLimit(key=k,count=0,until=now+seconds);db.add(row)
        if row.until<=now: row.count=0;row.until=now+seconds
        row.count+=1;db.flush()
        return row.count<=limit

    def challenge(db,user,channel):
        for old in rows(db,Challenge,Challenge.user_id==user.id,Challenge.channel==channel,Challenge.used==False): old.used=True
        code=str(secrets.randbelow(1000000)).zfill(6)
        item=Challenge(user_id=user.id,channel=channel,code_hash=ctx.vault.fingerprint(code+user.id+channel),
                       expires=int(time.time())+600,created=int(time.time()))
        db.add(item);db.flush()
        # OTP is encrypted even in the delivery outbox. Sandbox inbox decrypts only for its owner.
        notify(db,user.id,'otp:'+item.id,'Verification code',ctx.vault.seal(code),channels=[channel])

    @router.post('/auth/register',status_code=201)
    def register(body:Register,request:Request,db=Depends(dbdep)):
        if not throttle(db,'register:'+request.client.host,20,3600):
            return JSONResponse({'detail':'Registration rate limit exceeded'},status_code=429)
        if db.scalar(select(Account).where((Account.email==body.email.lower())|(Account.phone==body.phone))):
            return JSONResponse({'detail':'Account already exists'},status_code=409)
        test_run_id=request.headers.get('x-ajo-test-run-id','').strip() or None
        if test_run_id:
            from uuid import UUID
            try: UUID(test_run_id)
            except ValueError: fail('X-Ajo-Test-Run-Id must be a UUID',422)
            if app_environment() not in {'development','test'}: fail('Test-data tagging is disabled in production',403)
        user=Account(email=body.email.lower(),phone=body.phone,password=password_hash(body.password),
                     source='test_cli' if test_run_id else 'app',
                     is_test_account=bool(test_run_id),test_run_id=test_run_id)
        db.add(user);db.flush()
        for channel in ['email','sms']: challenge(db,user,channel)
        audit(db,user,user.id,'registered')
        return token_pair(db,user)

    @router.post('/auth/login')
    def login(body:Login,request:Request,db=Depends(dbdep)):
        if not throttle(db,'login:'+request.client.host+':'+body.email.lower()):
            return JSONResponse({'detail':'Too many attempts; wait five minutes'},status_code=429)
        user=db.scalar(select(Account).where(Account.email==body.email.lower()))
        # A fixed dummy hash exercises the same password work for nonexistent accounts.
        encoded=user.password if user else ctx.dummy_password
        if not password_ok(body.password,encoded) or not user or user.suspended:
            return JSONResponse({'detail':'Invalid credentials or suspended account'},status_code=401)
        if user.mfa_enabled:
            counter=verify_totp(ctx.vault.open(user.mfa_secret),body.totp,user.mfa_counter)
            if counter is None: return JSONResponse({'detail':'Valid unused MFA code required'},status_code=401)
            user.mfa_counter=counter
        audit(db,user,user.id,'login')
        return token_pair(db,user)

    class Refresh(Input): refresh_token:str
    @router.post('/auth/refresh')
    def refresh(body:Refresh,db=Depends(dbdep)):
        row=db.scalar(select(SessionToken).where(SessionToken.refresh_hash==digest(body.refresh_token)))
        if not row or row.refresh_expires<=time.time(): fail('Expired refresh token',401)
        user=get(db,Account,row.user_id)
        if user.suspended: fail('Account suspended',403)
        db.delete(row);db.flush()
        return token_pair(db,user)

    @router.post('/auth/logout',status_code=204)
    def logout(request:Request,db=Depends(dbdep),user=Depends(ctx.actor)):
        token=request.headers.get('authorization','').removeprefix('Bearer ')
        row=db.get(SessionToken,digest(token))
        if row: db.delete(row)
        return Response(status_code=204)

    @router.post('/auth/verify')
    def verify(body:Verify,db=Depends(dbdep),user=Depends(ctx.actor)):
        item=db.scalar(select(Challenge).where(Challenge.user_id==user.id,Challenge.channel==body.channel,
                                              Challenge.used==False).order_by(Challenge.created.desc()))
        if not item or item.expires<time.time() or item.attempts>=5:
            return JSONResponse({'detail':'Request a new verification code'},status_code=409)
        item.attempts+=1
        import hmac
        if not hmac.compare_digest(item.code_hash,ctx.vault.fingerprint(body.code+user.id+body.channel)):
            return JSONResponse({'detail':'Incorrect code'},status_code=400)
        item.used=True
        if body.channel=='email': user.email_verified=True
        else: user.phone_verified=True
        audit(db,user,user.id,'channel_verified',channel=body.channel)
        return account_view(db,user)

    @router.post('/auth/resend/{channel}')
    def resend(channel:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        if channel not in ['email','sms']: fail('Unknown channel',422)
        if not throttle(db,'resend:'+user.id+channel,3,600):
            return JSONResponse({'detail':'Resend limit reached'},status_code=429)
        challenge(db,user,channel)
        return {'status':'Queued'}

    @router.get('/auth/sandbox-inbox')
    def inbox(db=Depends(dbdep),user=Depends(ctx.actor)):
        ctx.require_sandbox("notifications")
        return [dict(id=n.id,channel=n.channel,code=ctx.vault.open(n.body),created_at=n.created_at)
                for n in rows(db,Notice,Notice.user_id==user.id,Notice.title=='Verification code')][-10:]

    @router.post('/auth/mfa/setup')
    def mfa_setup(db=Depends(dbdep),user=Depends(ctx.actor)):
        if user.mfa_enabled: fail('MFA is already enabled')
        value=ctx.vault.open(user.mfa_secret) if user.mfa_secret else base64.b32encode(secrets.token_bytes(20)).decode()
        user.mfa_secret=ctx.vault.seal(value)
        from urllib.parse import quote, urlencode
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderSVG
        uri='otpauth://totp/'+quote('Ajo:'+user.email,safe='')+'?'+urlencode({'secret':value,'issuer':'Ajo'})
        widget=QrCodeWidget(uri); x0,y0,x1,y1=widget.getBounds()
        drawing=Drawing(240,240,transform=[240/(x1-x0),0,0,240/(y1-y0),0,0]);drawing.add(widget)
        svg=renderSVG.drawToString(drawing)
        if isinstance(svg,str): svg=svg.encode()
        return {'secret':value,'issuer':'Ajo','account':user.email,'qr_data_url':'data:image/svg+xml;base64,'+base64.b64encode(svg).decode()}

    class MFACode(Input): code:str
    @router.post('/auth/mfa/enable')
    def mfa_enable(body:MFACode,db=Depends(dbdep),user=Depends(ctx.actor)):
        if not throttle(db,'mfa:'+user.id): return JSONResponse({'detail':'MFA attempt limit reached'},status_code=429)
        counter=verify_totp(ctx.vault.open(user.mfa_secret),body.code,user.mfa_counter) if user.mfa_secret else None
        if counter is None: return JSONResponse({'detail':'Invalid MFA code'},status_code=400)
        user.mfa_enabled=True;user.mfa_counter=counter
        # Existing sessions are revoked; the next login must prove MFA.
        db.execute(delete(SessionToken).where(SessionToken.user_id==user.id))
        audit(db,user,user.id,'mfa_enabled')
        return {'status':'Enabled; sign in again'}

    @router.get('/me')
    def me(db=Depends(dbdep),user=Depends(ctx.actor)): return account_view(db,user)

    @router.put('/me/preferences')
    def preferences(body:Preferences,db=Depends(dbdep),user=Depends(ctx.actor)):
        data=body.model_dump()
        if data.get('push_token'): data['push_token']=ctx.vault.seal(data['push_token'])
        user.preferences=data
        return {'status':'Saved'}

    @router.post('/documents',status_code=201)
    def upload(kind:str=Query(pattern='^(identity|selfie)$'),file:UploadFile=File(...),db=Depends(dbdep),user=Depends(ctx.actor)):
        if not user.email_verified or not user.phone_verified: fail('Verify both channels before uploading',403)
        data=file.file.read(5*1024*1024+1)
        if len(data)>5*1024*1024: fail('Maximum file size is 5 MB',413)
        signatures={'image/jpeg':b'\xff\xd8\xff','image/png':b'\x89PNG\r\n\x1a\n','application/pdf':b'%PDF-'}
        if file.content_type not in signatures or not data.startswith(signatures[file.content_type]): fail('Upload a valid JPEG, PNG or PDF',422)
        if kind=='selfie' and file.content_type=='application/pdf': fail('Selfie must be an image',422)
        doc=Document(user_id=user.id,kind=kind,mime=file.content_type,
                     ciphertext=ctx.vault.seal(base64.b64encode(data).decode()).encode())
        db.add(doc);db.flush();audit(db,user,doc.id,'document_uploaded',kind=kind)
        return {'id':doc.id,'kind':kind}

    @router.post('/kyc',status_code=201)
    def kyc(body:KYCInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        if not user.email_verified or not user.phone_verified: fail('Verify both channels first',403)
        if user.kyc_status in ['Approved','Pending','UnderReview']: fail('KYC already submitted or approved')
        p=policy(db).data
        if body.country not in p['launch_countries'] or body.id_type not in p['id_types'].get(body.country,[]): fail('Country or document type is not configured',422)
        if body.expiry<=date.today() or body.dob>=date.today(): fail('Invalid birth or expiry date',422)
        docs=[get(db,Document,i) for i in [body.document_id,body.selfie_id]]
        if any(d.user_id!=user.id for d in docs) or [d.kind for d in docs]!=['identity','selfie']: fail('Use your own identity document and selfie',403)
        identity=body.model_dump(mode='json')
        fingerprint=ctx.vault.fingerprint(body.country+':'+body.id_number.strip().upper())
        signals=[]
        if db.scalar(select(IdentityCase.id).where(IdentityCase.user_id!=user.id,IdentityCase.id_fingerprint==fingerprint)):
            signals.append('Duplicate document identity; manual review required')
        device=ctx.vault.fingerprint(body.device_fingerprint)
        if db.scalar(select(IdentityCase.id).where(IdentityCase.user_id!=user.id,IdentityCase.device_fingerprint==device)):
            signals.append('Shared device signal; not proof of duplicate identity')
        # Do not create an external identity-provider side effect from the degraded
        # SQLite journal. The user can safely retry once PostgreSQL is canonical.
        ctx.require_canonical()
        item=IdentityCase(user_id=user.id,encrypted_data=ctx.vault.seal(canonical(identity)),
                          id_fingerprint=fingerprint,device_fingerprint=device,signals=signals)
        db.add(item);db.flush()
        result=ctx.identity.submit(key=item.id,identity=identity,
            document=base64.b64decode(ctx.vault.open(docs[0].ciphertext.decode())),
            selfie=base64.b64decode(ctx.vault.open(docs[1].ciphertext.decode())))
        item.provider_ref=result['reference'];item.signals=signals+result.get('signals',[])
        item.status='UnderReview' if signals else 'Pending';user.kyc_status=item.status
        notify(db,user.id,'kyc:'+item.id,'Identity verification submitted',item.status)
        audit(db,user,item.id,'kyc_submitted')
        return {'id':item.id,'status':item.status}

    @router.get('/kyc')
    def kyc_status(db=Depends(dbdep),user=Depends(ctx.actor)):
        return [dict(id=k.id,status=k.status,reason=k.reason,created_at=k.created_at) for k in rows(db,IdentityCase,IdentityCase.user_id==user.id)]

    @router.post('/banks',status_code=201)
    def bank(body:BankInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        eligible(user)
        ctx.ensure_configured('payments')
        ctx.require_canonical()
        try: linked=ctx.payments.link_bank(bank_token=body.provider_token)
        except ValueError as error: fail(str(error),422)
        b=Bank(user_id=user.id,token_hash=ctx.vault.fingerprint(body.provider_token),encrypted_token=ctx.vault.seal(body.provider_token),masked=linked['masked'],status=linked['status'],mandate=body.mandate_accepted)
        db.add(b);db.flush();audit(db,user,b.id,'provider_bank_linked')
        return {'id':b.id,'masked':b.masked,'status':b.status,'sandbox':ctx.provider_names['payments']=='sandbox'}

    @router.get('/banks')
    def banks(db=Depends(dbdep),user=Depends(ctx.actor)):
        return [dict(id=b.id,masked=b.masked,status=b.status,mandate=b.mandate) for b in rows(db,Bank,Bank.user_id==user.id)]

    @router.post('/data-requests/{kind}',status_code=201)
    def data_request(kind:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        if kind not in ['export','deletion']: fail('Choose export or deletion',422)
        item=DataRequest(user_id=user.id,kind=kind)
        db.add(item);db.flush();audit(db,user,item.id,'data_request',kind=kind)
        return {'id':item.id,'status':item.status}

    return router
