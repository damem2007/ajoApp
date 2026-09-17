"""Platform application, independent from the historical demo API."""
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.store import make_engine
from .models import Base
from .runtime import Context
from .services import seed_policy
from .integrity import install_guards
from . import auth,circles,operations,cms

def create_platform(database_url=None,sandbox=None):
    sandbox=os.getenv('AJO_DEMO_MODE','false').lower()=='true' if sandbox is None else sandbox
    engine=make_engine(database_url or os.getenv('AJO_PLATFORM_DATABASE_URL','sqlite:///./ajo-platform.db'))
    ctx=Context(engine,sandbox)
    @asynccontextmanager
    async def lifespan(app):
        if sandbox:
            Base.metadata.create_all(engine)
            with engine.begin() as connection: install_guards(connection)
            with Session(engine) as db,db.begin(): seed_policy(db,True)
        yield
        engine.dispose()
    app=FastAPI(title='Ajo platform',version='0.2.0',lifespan=lifespan)
    app.state.ctx=ctx
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        errors=[]
        for error in exc.errors():
            field=str(error.get('loc', ['request'])[-1]);kind=error.get('type','')
            if field=='phone': message='Enter your phone number with country code, for example +14165551234.'
            elif field=='password': message='Use a password with at least 12 characters.'
            elif kind=='missing': message='This field is required.'
            else: message='Check this value and try again.'
            errors.append({'field':field,'message':message})
        return JSONResponse({'detail':'Please check the highlighted information.','errors':errors},status_code=422)

    @app.middleware('http')
    async def headers(request,call_next):
        rid=str(uuid4());start=time.monotonic()
        frontend_origin=os.getenv('AJO_FRONTEND_ORIGIN','').rstrip('/')
        if frontend_origin and request.url.path in ['/', '/app', '/marketplace', '/terms', '/privacy']:
            response=RedirectResponse(frontend_origin+request.url.path+('?' + request.url.query if request.url.query else ''),status_code=307)
        else:
            response=await call_next(request)
        response.headers['X-Request-ID']=rid
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" if not request.url.path.endswith('/docs') else "frame-ancestors 'none'"
        logging.getLogger('ajo').info('request id=%s method=%s status=%s elapsed_ms=%.1f',rid,request.method,response.status_code,(time.monotonic()-start)*1000)
        return response
    app.include_router(auth.routes(ctx));app.include_router(circles.routes(ctx));app.include_router(operations.routes(ctx));app.include_router(cms.routes(ctx))
    @app.get('/health')
    def health(): return {'status':'ok','sandbox':sandbox,'live_payments':False,'version':'0.2.0'}
    @app.get('/ready')
    def ready():
        with engine.connect() as connection: connection.execute(text('SELECT 1'))
        return {'database':'reachable','production_ready':False,'missing':['live provider adapters','approved jurisdiction and policies']}
    static=Path(os.getenv('AJO_FRONTEND_ASSETS',str(Path(__file__).resolve().parents[3]/'frontend'/'public'/'assets')))
    app.mount('/assets',StaticFiles(directory=static),name='assets')
    @app.get('/sw.js',include_in_schema=False)
    def service_worker(): return FileResponse(static/'sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/'})
    @app.get('/marketplace',include_in_schema=False)
    def marketplace(): return FileResponse(static/'landing.html')
    @app.get('/app',include_in_schema=False)
    def workspace(): return FileResponse(static/'platform.html')
    return app

app=create_platform()
