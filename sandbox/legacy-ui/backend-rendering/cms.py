"""Small first-party CMS: immutable revisions, explicit publishing and optimistic editing."""
import os
import copy
import html
import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import Field, model_validator
from sqlalchemy import select
from .models import ContentPage, ContentRevision, uid
from .schemas import Input
from .services import audit, fail, get
from .cms_defaults import DEFAULT_CONTENT


def validate_content(value,template,path='content'):
    if isinstance(template,dict):
        if not isinstance(value,dict) or set(value)!=set(template): raise ValueError('Content structure must match the editor fields')
        for key in template: validate_content(value[key],template[key],path+'.'+key)
    elif isinstance(template,list):
        if not isinstance(value,list) or not 1<=len(value)<=20: raise ValueError('Lists require between 1 and 20 entries')
        if path.endswith('hero.lines') and len(value)!=3: raise ValueError('The hero requires three lines')
        for entry in value: validate_content(entry,template[0],path)
    elif not isinstance(value,str) or not 1<=len(value.strip())<=5000:
        raise ValueError('Text fields require between 1 and 5000 characters')

class DraftInput(Input):
    content: dict
    expected_draft: str
    reason: str = Field(min_length=3,max_length=500)
    @model_validator(mode='after')
    def valid(self): validate_content(self.content,DEFAULT_CONTENT); return self

class PublishInput(Input):
    revision_id: str
    expected_published: str
    reason: str = Field(min_length=3,max_length=500)


def ensure_page(db):
    page=db.get(ContentPage,'home')
    if page: return page
    rid=uid();page=ContentPage(slug='home',draft_id=rid,published_id=rid)
    db.add(page);db.flush()
    db.add(ContentRevision(id=rid,page_slug='home',content=copy.deepcopy(DEFAULT_CONTENT),reason='Initial content from landing-page reference'))
    db.flush();return page


def page_state(db,page):
    draft=get(db,ContentRevision,page.draft_id);published=get(db,ContentRevision,page.published_id)
    return {'slug':page.slug,'draft':{'id':draft.id,'content':draft.content},'published':{'id':published.id,'content':published.content}}


def render_home(content):
    template=(Path(os.getenv('AJO_FRONTEND_ASSETS',str(Path(__file__).resolve().parents[3]/'frontend'/'public'/'assets')))/'home.html').read_text()
    def token(match):
        value=content
        for key in match.group(1).split('.'): value=value[int(key)] if isinstance(value,list) else value[key]
        return html.escape(str(value),quote=True)
    template=re.sub(r'\{\{cms:([\w.]+)\}\}',token,template)
    esc=lambda value:html.escape(value,quote=True)
    steps=''.join('<article><span class="step-number">'+str(i+1)+'</span><h3>'+esc(item['title'])+'</h3><p>'+esc(item['body'])+'</p></article>' for i,item in enumerate(content['how']['steps']))
    icons=['shield','calendar','record','info']
    paths={'shield':'M12 2 4 5v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5l-8-3Z M9 12l2 2 4-4','calendar':'M4 5h16v16H4Z M4 9h16 M8 2v5 M16 2v5','record':'M5 2h9l5 5v15H5Z M14 2v6h5 M8 12h8 M8 16h6','info':'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M12 8v5 M12 17h.01'}
    guards=''.join('<article><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="'+paths[icons[i%4]]+'"/></svg><div><h3>'+esc(item['title'])+'</h3><p>'+esc(item['body'])+'</p></div></article>' for i,item in enumerate(content['safeguards']['items']))
    faq=''.join('<details'+(' open' if i==0 else '')+'><summary>'+esc(item['question'])+'</summary><p>'+esc(item['answer'])+'</p></details>' for i,item in enumerate(content['faq']['items']))
    return template.replace('{{steps}}',steps).replace('{{guards}}',guards).replace('{{faq}}',faq)


def routes(ctx):
    router=APIRouter();dbdep=ctx.session;editor=ctx.staff('admin','ops');publisher=ctx.staff('admin')
    @router.get('/api/v1/content/home')
    def public_content(db=Depends(dbdep)):
        page=ensure_page(db);revision=get(db,ContentRevision,page.published_id)
        return {'revision_id':revision.id,'content':revision.content}
    @router.get('/',include_in_schema=False,response_class=HTMLResponse)
    def home(db=Depends(dbdep)):
        page=ensure_page(db);return render_home(get(db,ContentRevision,page.published_id).content)
    @router.get('/api/v1/admin/content/home')
    def edit_state(db=Depends(dbdep),user=Depends(editor)):
        return page_state(db,ensure_page(db))
    @router.put('/api/v1/admin/content/home/draft')
    def save_draft(body:DraftInput,db=Depends(dbdep),user=Depends(editor)):
        page=ensure_page(db)
        if page.draft_id!=body.expected_draft: fail('Another editor saved a revision. Reload before saving your changes.')
        revision=ContentRevision(page_slug='home',content=body.content,author_id=user.id,reason=body.reason)
        db.add(revision);db.flush();page.draft_id=revision.id
        audit(db,user,'content:home','content_draft_saved',revision_id=revision.id,reason=body.reason)
        return page_state(db,page)
    @router.post('/api/v1/admin/content/home/publish')
    def publish(body:PublishInput,db=Depends(dbdep),user=Depends(publisher)):
        page=ensure_page(db)
        if page.published_id!=body.expected_published: fail('Published content changed. Reload before publishing.')
        if body.revision_id!=page.draft_id: fail('Only the current saved draft can be published')
        page.published_id=page.draft_id
        audit(db,user,'content:home','content_published',revision_id=page.published_id,reason=body.reason)
        return page_state(db,page)
    @router.get('/api/v1/admin/content/home/revisions')
    def history(db=Depends(dbdep),user=Depends(editor)):
        ensure_page(db)
        return [{'id':r.id,'created_at':r.created_at,'author_id':r.author_id,'reason':r.reason} for r in db.scalars(select(ContentRevision).where(ContentRevision.page_slug=='home').order_by(ContentRevision.created_at.desc()).limit(100))]
    @router.get('/api/v1/admin/content/home/revisions/{rid}')
    def revision(rid:str,db=Depends(dbdep),user=Depends(editor)):
        r=get(db,ContentRevision,rid)
        if r.page_slug!='home': fail('Revision unavailable',404)
        return {'id':r.id,'content':r.content}
    @router.post('/api/v1/admin/content/home/restore')
    def restore(body:PublishInput,db=Depends(dbdep),user=Depends(publisher)):
        page=ensure_page(db)
        if body.expected_published!=page.published_id: fail('Published content changed. Reload before restoring.')
        original=get(db,ContentRevision,body.revision_id)
        if original.page_slug!='home': fail('Revision unavailable',404)
        new=ContentRevision(page_slug='home',content=copy.deepcopy(original.content),author_id=user.id,reason=body.reason)
        db.add(new);db.flush();page.draft_id=new.id;page.published_id=new.id
        audit(db,user,'content:home','content_restored',revision_id=new.id,source_revision=original.id,reason=body.reason)
        return page_state(db,page)
    @router.get('/api/v1/admin/content/home/preview-data')
    def preview_data(db=Depends(dbdep),user=Depends(editor)):
        page=ensure_page(db);draft=get(db,ContentRevision,page.draft_id)
        return {'revision_id':draft.id,'content':draft.content}
    @router.get('/api/v1/admin/content/home/preview',response_class=HTMLResponse)
    def preview(db=Depends(dbdep),user=Depends(editor)):
        page=ensure_page(db);return render_home(get(db,ContentRevision,page.draft_id).content)
    @router.get('/terms',include_in_schema=False,response_class=HTMLResponse)
    @router.get('/privacy',include_in_schema=False,response_class=HTMLResponse)
    def legal(request:Request,db=Depends(dbdep)):
        page=ensure_page(db);content=get(db,ContentRevision,page.published_id).content
        key='terms' if request.url.path=='/terms' else 'privacy'
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(content['legal'][key+'_title'])+'</title><link rel="stylesheet" href="/assets/marketplace-fonts.css"><link rel="stylesheet" href="/assets/marketplace-theme.css"><link rel="stylesheet" href="/assets/home.css"></head><body><main class="legal wrap"><a href="/">ajo·</a><h1>'+html.escape(content['legal'][key+'_title'])+'</h1><p>'+html.escape(content['legal'][key+'_body'])+'</p><a href="/">Back to Ajo</a></main></body></html>'
    return router
