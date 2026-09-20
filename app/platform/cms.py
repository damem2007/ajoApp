"""Small first-party CMS: immutable revisions, explicit publishing and optimistic editing."""
import copy
from typing import Optional
from fastapi import APIRouter, Depends
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




def routes(ctx):
    router=APIRouter();dbdep=ctx.session;editor=ctx.require_permission('content.edit');publisher=ctx.require_permission('content.publish')
    @router.get('/api/v1/content/home')
    def public_content(db=Depends(dbdep)):
        page=ensure_page(db);revision=get(db,ContentRevision,page.published_id)
        return {'revision_id':revision.id,'content':revision.content}
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
    @router.get('/api/v1/admin/content/home/preview')
    @router.get('/api/v1/admin/content/home/preview-data')
    def preview_data(db=Depends(dbdep),user=Depends(editor)):
        page=ensure_page(db);draft=get(db,ContentRevision,page.draft_id)
        return {'revision_id':draft.id,'content':draft.content}
    return router
