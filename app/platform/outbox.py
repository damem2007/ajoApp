"""Transactional outbox primitives.

Domain transactions persist OutboxEvent rows in the same database transaction as
business state. A separate dispatcher publishes only event IDs to Redis. Workers
then reload the authoritative event from the database and process it idempotently.

Redis is transport, never the source of truth.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select

from .models import OutboxEvent, now

QUEUE_NAME = "ajo:outbox"
RETRYABLE_STATUSES = ("pending", "retry")


def enqueue(
    db,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str,
) -> OutboxEvent:
    """Insert an outbox event once for the supplied business idempotency key."""
    existing = db.scalar(
        select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        idempotency_key=idempotency_key,
        status="pending",
    )
    db.add(event)
    db.flush()
    return event


def publish_pending(ctx, *, redis_client=None, limit: int = 100) -> dict[str, int]:
    """Publish durable event IDs to Redis.

    Publishing happens before the database row is marked published. A crash in
    between may enqueue the same ID twice; workers intentionally tolerate that.
    """
    if redis_client is None:
        from redis import Redis
        from app.config import redis_url

        redis_client = Redis.from_url(redis_url(), decode_responses=True)

    published = 0
    failed = 0
    with ctx.session() as db:
        events = list(
            db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.status.in_(RETRYABLE_STATUSES))
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(limit)
            )
        )
        for event in events:
            try:
                redis_client.rpush(QUEUE_NAME, event.id)
                event.status = "published"
                event.published_at = now()
                event.last_error = None
                published += 1
            except Exception as exc:
                event.status = "retry"
                event.last_error = type(exc).__name__
                failed += 1
    return {"published": published, "failed": failed}


def mark_retry(ctx, event_id: str, error: Exception, *, max_attempts: int = 5) -> None:
    """Record a safe retry state without persisting exception messages/secrets."""
    with ctx.session() as db:
        event = db.get(OutboxEvent, event_id)
        if not event or event.status == "completed":
            return
        event.attempt_count += 1
        event.last_error = type(error).__name__
        event.status = "retry" if event.attempt_count < max_attempts else "failed"


def mark_completed(db, event: OutboxEvent) -> None:
    event.status = "completed"
    event.completed_at = now()
    event.last_error = None
