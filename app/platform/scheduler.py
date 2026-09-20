"""Periodic scheduler that creates durable work rather than executing providers inline."""
from datetime import date, datetime, timezone
from sqlalchemy import select
from .models import Due
from .outbox import emit


def enqueue_due_scan(db, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    exists = db.scalar(
        select(Due.id).where(
            Due.date <= as_of.isoformat(),
            Due.status.in_(['Scheduled', 'Failed']),
        ).limit(1)
    )
    if not exists:
        return 0
    # Hour bucket prevents a tight scheduler loop from flooding the outbox while
    # still allowing recovery/retry later the same day if a worker was offline.
    bucket = datetime.now(timezone.utc).strftime('%Y%m%d%H')
    emit(
        db,
        event_type='payment.scan',
        aggregate_type='payment_schedule',
        aggregate_id=as_of.isoformat(),
        idempotency_key=f'payment-scan:{as_of.isoformat()}:{bucket}',
        payload={'as_of': as_of.isoformat()},
    )
    return 1
