"""Redis-backed worker entrypoints for payment, notification and reconciliation work."""
from __future__ import annotations

import argparse
import time

from app.config import redis_url, worker_interval_seconds
from .application import create_platform
from .models import OutboxEvent
from .outbox import QUEUES, mark_completed, mark_retry
from .payments import run_due, dispatch_notices


def _event_type(ctx, event_id: str) -> str | None:
    with ctx.session() as db:
        event = db.get(OutboxEvent, event_id)
        if not event or event.status in {"completed", "failed"}:
            return None
        return event.event_type


def _run_reconciliation(ctx) -> dict:
    if not ctx.router:
        return {"enabled": False, "status": "not-configured"}
    with ctx.router.lock, ctx.router.process_lock():
        ctx.router.replay(ctx.router.secondary, ctx.router.engine if hasattr(ctx.router, "engine") else ctx.router.primary)
        ctx.router.replay(ctx.router.primary, ctx.router.secondary)
        ctx.router.verify_mirror()
        ctx.router.control("ready")
    return {"enabled": True, "status": "ready"}


def process_event(ctx, event_id: str) -> dict:
    event_type = _event_type(ctx, event_id)
    if event_type is None:
        return {"event_id": event_id, "status": "skipped"}

    try:
        if event_type == "reconciliation.run":
            result = _run_reconciliation(ctx)
            with ctx.session() as db:
                event = db.get(OutboxEvent, event_id)
                if event and event.status != "completed":
                    event.attempt_count += 1
                    mark_completed(db, event)
            return {"event_id": event_id, "status": "completed", "result": result}

        with ctx.session() as db:
            event = db.get(OutboxEvent, event_id)
            if not event or event.status == "completed":
                return {"event_id": event_id, "status": "skipped"}
            event.attempt_count += 1

            if event_type == "payment.run_due":
                result = run_due(db, ctx)
            elif event_type == "notification.dispatch":
                result = {"sent": dispatch_notices(db, ctx)}
            else:
                raise ValueError("Unsupported outbox event type")

            mark_completed(db, event)
            return {"event_id": event_id, "status": "completed", "result": result}
    except Exception as exc:
        mark_retry(ctx, event_id, exc)
        raise


def run_worker(kind: str, *, once: bool = False) -> None:
    from redis import Redis

    if kind not in QUEUES:
        raise ValueError("Unknown worker kind")
    app = create_platform()
    ctx = app.state.ctx
    if kind == "payment":
        ctx.ensure_configured("payments")
    elif kind == "notification":
        ctx.ensure_configured("notifications")

    client = Redis.from_url(redis_url(), decode_responses=True)
    queue = QUEUES[kind]
    timeout = max(1, min(worker_interval_seconds(), 30))

    while True:
        item = client.brpop(queue, timeout=1 if once else timeout)
        if item:
            _, event_id = item
            try:
                process_event(ctx, event_id)
            except Exception:
                # The durable outbox row now carries retry state. The dispatcher
                # republishes retryable events on a later pass.
                pass
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=sorted(QUEUES))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run_worker(args.kind, once=args.once)


if __name__ == "__main__":
    main()
