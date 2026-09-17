import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, UniqueConstraint, Text

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    pseudonym = Column(String, nullable=False, unique=True)
    approved = Column(Boolean, nullable=False, default=False)
    scheme_cap = Column(Integer, nullable=False, default=1)


class Scheme(Base):
    __tablename__ = "schemes"
    id = Column(String, primary_key=True)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    target_minor = Column(Integer, nullable=False)
    planned_members = Column(Integer, nullable=False)
    frequency = Column(String, nullable=False)
    state = Column(String, nullable=False, default="Recruiting")
    contract = Column(Text)
    contract_hash = Column(String)
    period = Column(Integer, nullable=False, default=0)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("scheme_id", "user_id"), UniqueConstraint("scheme_id", "rank"))
    id = Column(String, primary_key=True)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    rank = Column(Integer, nullable=False)
    signed = Column(Boolean, nullable=False, default=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("scheme_id", "period", "user_id", "direction"),)
    id = Column(String, primary_key=True)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    period = Column(Integer, nullable=False)
    direction = Column(String, nullable=False)
    amount_minor = Column(Integer, nullable=False)
    source = Column(String, nullable=False, default="simulation")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String, primary_key=True)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    actor_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    at = Column(String, nullable=False)


def make_engine(url=None):
    url = url or os.getenv("DATABASE_URL", "sqlite:///./ajo.db")
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
    return engine
