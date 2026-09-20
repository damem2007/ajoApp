"""Platform application, independent from the historical demo API."""
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config import database_url as configured_database_url, simulated_providers, cors_origins
from app.database import make_engine
from .models import Base
from .runtime import Context
from .services import seed_policy
from .integrity import install_guards
from . import auth,circles,operations,cms,frontend_routes,administration
from .rbac import bootstrap as bootstrap_rbac
from .bootstrap import bootstrap_superadmin

def create_platform(database_url=None,sandbox=None):
    initialize_test_fixture = sandbox is not None
    engine=make_engine(database_url or configured_database_url())
    ctx=Context(engine,sandbox)
    @asynccontextmanager
    async def lifespan(app):
        if initialize_test_fixture:
            Base.metadata.create_all(engine)
            with engine.begin() as connection: install_guards(connection)
            with Session(engine) as db,db.begin():
                seed_policy(db,bool(sandbox));bootstrap_rbac(db);bootstrap_superadmin(db)
        else:
            # Production/local deployments are migrated explicitly, then startup
            # ensures only required system data and the optional Super Admin.
            with Session(engine) as db,db.begin():
                seed_policy(db,ctx.sandbox);bootstrap_rbac(db);bootstrap_superadmin(db)
        yield
        engine.dispose()
    app=FastAPI(title='Ajo platform',version='0.2.0',lifespan=lifespan)
    app.state.ctx=ctx
    app.add_middleware(CORSMiddleware,allow_origins=cors_origins(),allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type'])
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
        response=await call_next(request)
        response.headers['X-Request-ID']=rid
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" if not request.url.path.endswith('/docs') else "frame-ancestors 'none'"
        logging.getLogger('ajo').info('request id=%s method=%s status=%s elapsed_ms=%.1f',rid,request.method,response.status_code,(time.monotonic()-start)*1000)
        return response
    app.include_router(frontend_routes.routes())
    app.include_router(auth.routes(ctx));app.include_router(circles.routes(ctx));app.include_router(operations.routes(ctx));app.include_router(cms.routes(ctx));app.include_router(administration.routes(ctx))
    @app.get('/health')
    def health(): return {'status':'ok','sandbox':ctx.sandbox,'providers':ctx.provider_names,'database_mode':ctx.router.mode if ctx.router else engine.dialect.name,'live_payments':ctx.provider_names['payments'] not in {'sandbox','unconfigured'},'version':'0.2.0'}
    @app.get('/ready')
    def ready():
        if ctx.router:
            with ctx.router.session() as db: db.execute(text('SELECT 1'))
        else:
            with engine.connect() as connection: connection.execute(text('SELECT 1'))
        return {'database':'reachable','production_ready':False,'missing':['live provider adapters','approved jurisdiction and policies']}
    return app

app=create_platform()
