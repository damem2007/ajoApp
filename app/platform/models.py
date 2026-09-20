"""Versioned platform schema; legacy demo tables are left untouched."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, ForeignKey, JSON, Text, LargeBinary, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()
def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).isoformat()

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False)
    kyc_status = Column(String, default='NotSubmitted', nullable=False)
    pseudonym = Column(String, unique=True)
    role = Column(String, default='member', nullable=False)
    suspended = Column(Boolean, default=False, nullable=False)
    score = Column(Integer, default=0, nullable=False)
    mfa_secret = Column(Text)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_counter = Column(BigInteger, default=-1, nullable=False)
    preferences = Column(JSON, default=dict, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class SessionToken(Base):
    __tablename__ = 'session_tokens'
    token_hash = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False, index=True)
    refresh_hash = Column(String, unique=True, nullable=False)
    expires = Column(BigInteger, nullable=False)
    refresh_expires = Column(BigInteger, nullable=False)

class Challenge(Base):
    __tablename__ = 'verification_challenges'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    channel = Column(String, nullable=False)
    code_hash = Column(String, nullable=False)
    expires = Column(BigInteger, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created = Column(BigInteger, nullable=False)

class RateLimit(Base):
    __tablename__ = 'rate_limits'
    key = Column(String, primary_key=True)
    count = Column(Integer, default=0, nullable=False)
    until = Column(BigInteger, nullable=False)

class IdentityCase(Base):
    __tablename__ = 'identity_cases'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False, index=True)
    status = Column(String, default='Pending', nullable=False)
    encrypted_data = Column(Text, nullable=False)
    id_fingerprint = Column(String, nullable=False, index=True)
    biometric_fingerprint = Column(String, index=True)
    device_fingerprint = Column(String, index=True)
    signals = Column(JSON, default=list, nullable=False)
    provider_ref = Column(String)
    reason = Column(Text)
    created_at = Column(String, default=now, nullable=False)

class Document(Base):
    __tablename__ = 'secure_documents'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    kind = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    ciphertext = Column(LargeBinary, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Bank(Base):
    __tablename__ = 'bank_links'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    encrypted_token = Column(Text, nullable=False)
    masked = Column(String, nullable=False)
    status = Column(String, default='Pending', nullable=False)
    mandate = Column(Boolean, default=False, nullable=False)

class Policy(Base):
    __tablename__ = 'policy_versions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(JSON, nullable=False)
    actor_id = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Circle(Base):
    __tablename__ = 'circles'
    id = Column(String, primary_key=True, default=uid)
    creator_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    name = Column(String, nullable=False)
    state = Column(String, default='Draft', nullable=False, index=True)
    config = Column(JSON, nullable=False)
    featured = Column(Boolean, default=False, nullable=False)
    removed = Column(Boolean, default=False, nullable=False)
    seed = Column(Text, nullable=False)
    commitment = Column(String, nullable=False)
    contract_id = Column(String)
    created_at = Column(String, default=now, nullable=False)

class Participant(Base):
    __tablename__ = 'participants'
    __table_args__ = (UniqueConstraint('circle_id', 'user_id'),)
    id = Column(String, primary_key=True, default=uid)
    circle_id = Column(String, ForeignKey('circles.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False, index=True)
    inviter_id = Column(String, ForeignKey('accounts.id'))
    rank = Column(Integer)
    status = Column(String, default='Joined', nullable=False)
    joined_at = Column(String, default=now, nullable=False)

class Invitation(Base):
    __tablename__ = 'invitations'
    id = Column(String, primary_key=True, default=uid)
    circle_id = Column(String, ForeignKey('circles.id'), nullable=False)
    generator_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    code_hash = Column(String, unique=True, nullable=False)
    recipient_hash = Column(String)
    max_uses = Column(Integer, nullable=False)
    uses = Column(Integer, default=0, nullable=False)
    expires = Column(BigInteger, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)

class Contract(Base):
    __tablename__ = 'circle_contracts'
    __table_args__ = (UniqueConstraint('circle_id', 'version'),)
    id = Column(String, primary_key=True, default=uid)
    circle_id = Column(String, ForeignKey('circles.id'), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    digest = Column(String, nullable=False)
    pdf = Column(LargeBinary, nullable=False)
    pdf_hash = Column(String, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Signature(Base):
    __tablename__ = 'contract_signatures'
    __table_args__ = (UniqueConstraint('contract_id','user_id'),)
    id = Column(String, primary_key=True, default=uid)
    contract_id = Column(String, ForeignKey('circle_contracts.id'), nullable=False)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    typed_name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    device = Column(String, nullable=False)
    signed_at = Column(String, default=now, nullable=False)

class Due(Base):
    __tablename__ = 'scheduled_payments'
    __table_args__ = (UniqueConstraint('circle_id','business_key'), CheckConstraint('amount_minor >= 0'))
    id = Column(String, primary_key=True, default=uid)
    circle_id = Column(String, ForeignKey('circles.id'), nullable=False, index=True)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    business_key = Column(String, nullable=False)
    window = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)
    date = Column(String, nullable=False, index=True)
    amount_minor = Column(BigInteger, nullable=False)
    status = Column(String, default='Scheduled', nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt = Column(String)
    provider_ref = Column(String)

class PaymentEvent(Base):
    __tablename__ = 'payment_events'
    id = Column(String, primary_key=True, default=uid)
    due_id = Column(String, ForeignKey('scheduled_payments.id'), nullable=False)
    key = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Posting(Base):
    __tablename__ = 'ledger_postings'
    __table_args__ = (UniqueConstraint('event_key', 'account'),)
    id = Column(String, primary_key=True, default=uid)
    circle_id = Column(String, ForeignKey('circles.id'), nullable=False, index=True)
    due_id = Column(String, ForeignKey('scheduled_payments.id'), nullable=False)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    event_key = Column(String, nullable=False)
    account = Column(String, nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class TrustEvent(Base):
    __tablename__ = 'trust_events'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    circle_id = Column(String, ForeignKey('circles.id'))
    key = Column(String, unique=True, nullable=False)
    delta = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Notice(Base):
    __tablename__ = 'notification_outbox'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    key = Column(String, unique=True, nullable=False)
    channel = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, default='Queued', nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    read = Column(Boolean, default=False, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class Complaint(Base):
    __tablename__ = 'complaints'
    id = Column(String, primary_key=True, default=uid)
    circle_id = Column(String, ForeignKey('circles.id'), nullable=False)
    filer_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    target_id = Column(String, ForeignKey('accounts.id'))
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, default='Submitted', nullable=False)
    assignee = Column(String, ForeignKey('accounts.id'))
    resolution = Column(Text)
    created_at = Column(String, default=now, nullable=False)
    updated_at = Column(String, default=now, nullable=False)

class Audit(Base):
    __tablename__ = 'platform_audit'
    id = Column(String, primary_key=True, default=uid)
    actor_id = Column(String, nullable=False)
    resource = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    created_at = Column(String, default=now, nullable=False)

class DataRequest(Base):
    __tablename__ = 'data_requests'
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    kind = Column(String, nullable=False)
    status = Column(String, default='Submitted', nullable=False)
    reason = Column(Text)
    created_at = Column(String, default=now, nullable=False)

class ContentPage(Base):
    __tablename__ = 'content_pages'
    slug = Column(String, primary_key=True)
    draft_id = Column(String, nullable=False)
    published_id = Column(String, nullable=False)

class ContentRevision(Base):
    __tablename__ = 'content_revisions'
    id = Column(String, primary_key=True, default=uid)
    page_slug = Column(String, ForeignKey('content_pages.slug'), nullable=False, index=True)
    content = Column(JSON, nullable=False)
    author_id = Column(String, ForeignKey('accounts.id'))
    reason = Column(String, nullable=False)
    created_at = Column(String, default=now, nullable=False)


class NotificationChannel(Base):
    __tablename__ = 'notification_channels'
    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(String, nullable=False, default=now)
    updated_at = Column(String, nullable=False, default=now)

class StaffRole(Base):
    __tablename__ = 'staff_roles'
    id = Column(String, primary_key=True)
    permissions = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False, default=now)

class StaffMembership(Base):
    __tablename__ = 'staff_memberships'
    user_id = Column(String, ForeignKey('accounts.id'), primary_key=True)
    role_id = Column(String, ForeignKey('staff_roles.id'), nullable=False)
    status = Column(String, nullable=False, default='active')
    created_by = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=now)
    updated_at = Column(String, nullable=False, default=now)

class StaffInvitation(Base):
    __tablename__ = 'staff_invitations'
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, nullable=False)
    role_id = Column(String, ForeignKey('staff_roles.id'), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires = Column(BigInteger, nullable=False)
    status = Column(String, nullable=False, default='invited')
    created_by = Column(String, ForeignKey('accounts.id'), nullable=False)
    accepted_by = Column(String, ForeignKey('accounts.id'))
    created_at = Column(String, nullable=False, default=now)

class SyncBatch(Base):
    __tablename__ = 'sync_batches'
    id = Column(String, primary_key=True, default=uid)
    sequence = Column(Integer, nullable=False)
    source = Column(String, nullable=False)
    changes = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    error_code = Column(String)
    created_at = Column(String, nullable=False, default=now)
    synced_at = Column(String)

class SyncReceipt(Base):
    __tablename__ = 'sync_receipts'
    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    applied_at = Column(String, nullable=False, default=now)

class SyncControl(Base):
    __tablename__ = 'sync_control'
    id = Column(String, primary_key=True)
    state = Column(String, nullable=False)
    detail = Column(String)
    updated_at = Column(String, nullable=False, default=now)
