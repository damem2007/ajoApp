"""Periodic scheduler that writes durable work intents to the outbox."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from app.config import scheduler_interval_seconds
from .application import create_platform
from .outbox import enqueue


def schedule_once(ctx, *, now: datetime | None = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    # One bucket per minute prevents duplicate scheduling when the scheduler
    # restarts or multiple ticks happen close together.
    bucket = now.strftime("%Y%m%d%H%M")
    created = {}
    with ctx.session() as db:
        for event_type in (
            "payment.run_due",
            "notification.dispatch",
            "reconciliation.run",
        ):
            event = enqueue(
                db,
                event_type=event_type,
                aggregate_type="system",
                aggregate_id=None,
                payload={"scheduled_at": now.isoformat()},
                idempotency_key=f"scheduler:{event_type}:{bucket}",
            )
            created[event_type] = event.id
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    app = create_platform()
    ctx = app.state.ctx
    interval = scheduler_interval_seconds()

    while True:
        schedule_once(ctx)
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
