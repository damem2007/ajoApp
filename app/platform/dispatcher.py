"""Outbox dispatcher process.

The dispatcher is intentionally separate from API request handling. It reads
committed outbox rows and publishes event IDs to Redis.
"""
from __future__ import annotations

import argparse
import time

from app.config import worker_interval_seconds
from .application import create_platform
from .outbox import publish_pending


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    app = create_platform()
    ctx = app.state.ctx
    interval = worker_interval_seconds()

    while True:
        publish_pending(ctx)
        if args.once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
