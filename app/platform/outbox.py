"""Transactional outbox primitives.

Domain code writes OutboxEvent rows in the same database transaction as the
business change. A dispatcher publishes event IDs to Redis after commit.
Consumers are idempotent through WorkerReceipt and the domain's own business keys.
"""
from __future__ import annotations

from typing import Callable
from sqlalchemy import select
from .models import OutboxEvent, now


QUEUE_BY_PREFIX = {
    'payment.': 'ajo:payments',
    'notification.': 'ajo:notifications',
    'reconciliation.': 'ajo:reconciliation',
}


def queue_for(event_type: str) -> str:
    for prefix, queue in QUEUE_BY_PREFIX.items():
        if event_type.startswith(prefix):
            return queue
    return 'ajo:operations'


def emit(
    db,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    payload: dict | None = None,
) -> OutboxEvent:
    """Insert once inside the caller's existing transaction."""
    existing = db.scalar(select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key))
    if existing:
        return existing
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        payload=payload or {},
    )
    db.add(event)
    db.flush()
    return event


class RedisPublisher:
    def __init__(self, url: str):
        from redis import Redis
        self.client = Redis.from_url(url, decode_responses=True)

    def publish(self, event: OutboxEvent) -> None:
        self.client.rpush(queue_for(event.event_type), event.id)

    def close(self) -> None:
        self.client.close()


def dispatch_pending(db, publish: Callable[[OutboxEvent], None], limit: int = 100) -> int:
    """Publish incomplete rows at-least-once; consumers deduplicate by event ID."""
    events = list(
        db.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status.in_(['pending', 'failed', 'published']))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
        )
    )
    published = 0
    for event in events:
        event.attempt_count += 1
        try:
            publish(event)
            event.status = 'published'
            event.published_at = now()
            event.last_error = None
            published += 1
        except Exception as exc:
            event.status = 'failed'
            event.last_error = type(exc).__name__
    return published
