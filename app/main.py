"""Explicitly gated demo API. No authentication or payment provider is simulated as real."""
import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain import allocate
from app.store import Base, User, Scheme, Membership, LedgerEntry, AuditEvent, make_engine


class SchemeInput(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    currency: Literal["NGN", "CAD", "USD", "GBP"] = "NGN"
    target_minor: int = Field(gt=0, le=100_000_000_000, strict=True)
    planned_members: int = Field(ge=2, le=50, strict=True)
    contribution_frequency: Literal["daily", "weekly", "bi-weekly", "monthly", "bi-monthly", "quarterly", "semi-annual", "yearly"] = "monthly"
    collection_frequency: Literal["daily", "weekly", "bi-weekly", "monthly", "bi-monthly", "quarterly", "semi-annual", "yearly"] = "monthly"
    allow_overflow: bool = False

    @model_validator(mode="after")
    def supported_policy(self):
        if self.contribution_frequency != self.collection_frequency:
            raise ValueError("Mixed frequencies need an approved calendar-based allocation policy")
        if self.allow_overflow:
            raise ValueError("Overflow requires an approved strategy")
        if self.target_minor < self.planned_members:
            raise ValueError("Target must allow at least one minor unit per member")
        return self


class FinalizeInput(BaseModel):
    payout_order: list[str]


class SignInput(BaseModel):
    contract_hash: str


class SettleInput(BaseModel):
    period: int = Field(ge=0, strict=True)


def create_app(database_url=None, demo_mode=None):
    demo = os.getenv("AJO_DEMO_MODE", "false").lower() == "true" if demo_mode is None else demo_mode
    engine = make_engine(database_url)

    @asynccontextmanager
    async def lifespan(app):
        if demo:
            Base.metadata.create_all(engine)
            with Session(engine) as db, db.begin():
                for i, name in enumerate(["Amber Heron", "Cedar Finch", "Indigo Fox", "Silver Otter"]):
                    if not db.get(User, f"demo-{i + 1}"):
                        db.add(User(id=f"demo-{i + 1}", pseudonym=name, approved=i < 3))
        yield
        engine.dispose()

    app = FastAPI(title="Ajo — local sandbox", version="0.1.0", lifespan=lifespan)

    def session():
        if not demo:
            raise HTTPException(503, "Demo is disabled; production identity and provider adapters are not configured")
        with Session(engine) as db:
            # Serialize writes for SQLite; PostgreSQL uses a transaction advisory lock.
            # Coarse bootstrap lock protects user caps and scheme/ledger changes together.
            if engine.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            else:
                db.execute(text("SELECT pg_advisory_xact_lock(714205)"))
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def actor(db=Depends(session), x_demo_user: Optional[str] = Header(default=None)):
        user = db.get(User, x_demo_user) if x_demo_user else None
        if not user:
            raise HTTPException(401, "Select a sandbox identity using X-Demo-User")
        if not user.approved:
            raise HTTPException(403, "Approved KYC required (sandbox fixture)")
        return user

    def members(db, sid):
        return list(db.scalars(select(Membership).where(Membership.scheme_id == sid).order_by(Membership.rank)))

    def scheme_for(db, sid, user):
        scheme = db.get(Scheme, sid)
        if not scheme:
            raise HTTPException(404, "Scheme not found")
        if user.id not in [m.user_id for m in members(db, sid)]:
            raise HTTPException(403, "Scheme membership required")
        return scheme

    def check_cap(db, user):
        count = len(list(db.scalars(select(Membership).join(Scheme).where(
            Membership.user_id == user.id, Scheme.state.notin_(["Completed", "Cancelled"])))))
        if count >= user.scheme_cap:
            raise HTTPException(409, "Concurrent scheme cap reached; recruiting commitments also reserve a slot")

    def audit(db, scheme, user, action):
        db.add(AuditEvent(id=str(uuid4()), scheme_id=scheme.id, actor_id=user.id,
                          action=action, at=datetime.now(timezone.utc).isoformat()))

    def view(db, scheme):
        ms = members(db, scheme.id)
        entries = list(db.scalars(select(LedgerEntry).where(LedgerEntry.scheme_id == scheme.id)))
        shares = allocate(scheme.target_minor, len(ms), min(scheme.period, len(ms) - 1))
        people = []
        for i, m in enumerate(ms):
            contributed = sum(e.amount_minor for e in entries if e.user_id == m.user_id and e.direction == "contribution")
            collected = sum(e.amount_minor for e in entries if e.user_id == m.user_id and e.direction == "payout")
            people.append(dict(user_id=m.user_id, pseudonym=db.get(User, m.user_id).pseudonym,
                               rank=m.rank, signed=m.signed, next_contribution_minor=shares[i] if scheme.state != "Completed" else 0,
                               contributed_minor=contributed, collected_minor=collected,
                               net_position_minor=contributed-collected,
                               remaining_obligation_minor=scheme.target_minor-contributed))
        return dict(id=scheme.id, name=scheme.name, currency=scheme.currency,
                    target_minor=scheme.target_minor, planned_members=scheme.planned_members,
                    frequency=scheme.frequency, state=scheme.state, period=scheme.period,
                    members=people, contract_hash=scheme.contract_hash,
                    contract=json.loads(scheme.contract) if scheme.contract else None,
                    pool_minor=sum(e.amount_minor * (1 if e.direction == "contribution" else -1) for e in entries),
                    simulation=True)

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "demo" if demo else "unconfigured", "real_payments_enabled": False}

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/api/demo/users")
    def users(db=Depends(session)):
        return [dict(id=u.id, pseudonym=u.pseudonym, approved=u.approved) for u in db.scalars(select(User))]

    @app.get("/api/schemes")
    def listing(db=Depends(session), user=Depends(actor)):
        # All bootstrap schemes are public, pseudonym-only sandbox fixtures.
        return [view(db, s) for s in db.scalars(select(Scheme))]

    @app.post("/api/schemes", status_code=201)
    def create(body: SchemeInput, db=Depends(session), user=Depends(actor)):
        check_cap(db, user)
        scheme = Scheme(id=str(uuid4()), creator_id=user.id, name=body.name, currency=body.currency,
                        target_minor=body.target_minor, planned_members=body.planned_members,
                        frequency=body.contribution_frequency, state="Recruiting", period=0)
        db.add(scheme)
        db.flush()
        db.add(Membership(id=str(uuid4()), scheme_id=scheme.id, user_id=user.id, rank=0))
        audit(db, scheme, user, "Created and joined")
        db.flush()
        return view(db, scheme)

    @app.post("/api/schemes/{sid}/join")
    def join(sid: str, db=Depends(session), user=Depends(actor)):
        scheme = db.get(Scheme, sid)
        if not scheme:
            raise HTTPException(404, "Scheme not found")
        ms = members(db, sid)
        if user.id in [m.user_id for m in ms]:
            return view(db, scheme)
        if scheme.state != "Recruiting" or len(ms) >= scheme.planned_members:
            raise HTTPException(409, "Recruitment is closed")
        check_cap(db, user)
        db.add(Membership(id=str(uuid4()), scheme_id=sid, user_id=user.id, rank=len(ms)))
        if len(ms) + 1 == scheme.planned_members:
            scheme.state = "Finalizable"
        audit(db, scheme, user, "Joined; contribution reprorated")
        db.flush()
        return view(db, scheme)

    @app.post("/api/schemes/{sid}/finalize")
    def finalize(sid: str, body: FinalizeInput, db=Depends(session), user=Depends(actor)):
        scheme = scheme_for(db, sid, user)
        ms = members(db, sid)
        if scheme.state != "Finalizable":
            raise HTTPException(409, "Scheme must be finalizable")
        if len(body.payout_order) != len(ms) or set(body.payout_order) != {m.user_id for m in ms}:
            raise HTTPException(422, "Payout order must contain every member exactly once")
        # Vacate unique ranks before assigning the proposed permutation.
        for m in ms:
            m.rank = -m.rank - 1
        db.flush()
        for m in ms:
            m.rank = body.payout_order.index(m.user_id)
        contract = dict(version=1, scheme_id=sid, currency=scheme.currency, target_minor=scheme.target_minor,
                        frequency=scheme.frequency, payout_order=body.payout_order,
                        contributions=[allocate(scheme.target_minor, len(ms), p) for p in range(len(ms))],
                        terms="SANDBOX ONLY: simulated assent, no legal contract or bank mandate")
        scheme.contract = json.dumps(contract, sort_keys=True, separators=(",", ":"))
        scheme.contract_hash = hashlib.sha256(scheme.contract.encode()).hexdigest()
        scheme.state = "PendingSignatures"
        audit(db, scheme, user, "Frozen contract proposal")
        db.flush()
        return view(db, scheme)

    @app.post("/api/schemes/{sid}/sign")
    def sign(sid: str, body: SignInput, db=Depends(session), user=Depends(actor)):
        scheme = scheme_for(db, sid, user)
        if scheme.state != "PendingSignatures" or body.contract_hash != scheme.contract_hash:
            raise HTTPException(409, "Current pending contract hash required")
        ms = members(db, sid)
        member = next(m for m in ms if m.user_id == user.id)
        if not member.signed:
            member.signed = True
            audit(db, scheme, user, "Sandbox assent: " + scheme.contract_hash)
        if all(m.signed for m in ms):
            scheme.state = "Active"
            audit(db, scheme, user, "Activated after unanimous sandbox assent")
        db.flush()
        return view(db, scheme)

    @app.post("/api/schemes/{sid}/simulate-period")
    def settle(sid: str, body: SettleInput, db=Depends(session), user=Depends(actor)):
        scheme = scheme_for(db, sid, user)
        if body.period < scheme.period:
            return view(db, scheme)  # Natural idempotency key: scheme + period.
        if scheme.state not in ("Active", "Cycling") or body.period != scheme.period:
            raise HTTPException(409, "An active scheme and its next period are required")
        ms = members(db, sid)
        shares = allocate(scheme.target_minor, len(ms), body.period)
        for m, amount in zip(ms, shares):
            db.add(LedgerEntry(id=str(uuid4()), scheme_id=sid, user_id=m.user_id,
                              period=body.period, direction="contribution", amount_minor=amount))
        db.flush()
        if view(db, scheme)["pool_minor"] < scheme.target_minor:
            raise HTTPException(409, "Insufficient reconciled simulation pool")
        db.add(LedgerEntry(id=str(uuid4()), scheme_id=sid, user_id=ms[body.period].user_id,
                          period=body.period, direction="payout", amount_minor=scheme.target_minor))
        scheme.period += 1
        scheme.state = "Completed" if scheme.period == len(ms) else "Cycling"
        audit(db, scheme, user, f"Simulated settled period {body.period}; state={scheme.state}")
        db.flush()
        return view(db, scheme)

    @app.get("/api/schemes/{sid}/audit")
    def history(sid: str, db=Depends(session), user=Depends(actor)):
        scheme_for(db, sid, user)
        return [dict(actor_id=e.actor_id, action=e.action, at=e.at) for e in db.scalars(
            select(AuditEvent).where(AuditEvent.scheme_id == sid).order_by(AuditEvent.at))]

    return app


app = create_app()
