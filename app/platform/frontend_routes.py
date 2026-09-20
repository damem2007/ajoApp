"""Compatibility URLs redirect to Next.js; the backend never renders UI."""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from app.config import frontend_origin


def routes():
    router = APIRouter(include_in_schema=False)

    @router.get('/')
    @router.get('/app')
    @router.get('/app/{path:path}')
    @router.get('/backoffice')
    @router.get('/backoffice/{path:path}')
    @router.get('/marketplace')
    @router.get('/terms')
    @router.get('/privacy')
    @router.get('/sign-in')
    @router.get('/register')
    @router.get('/verify')
    def frontend(request: Request):
        query = '?' + request.url.query if request.url.query else ''
        return RedirectResponse(frontend_origin() + request.url.path + query, status_code=307)

    return router
