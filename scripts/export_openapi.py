"""Export FastAPI OpenAPI deterministically without starting a server or external services."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


def configure_schema_environment() -> None:
    root = Path(tempfile.gettempdir()) / "ajo-openapi"
    os.environ.setdefault("AJO_PLATFORM_DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("AJO_PROVIDER_MODE", "simulated")
    os.environ.setdefault("AJO_PAYMENTS_PROVIDER", "sandbox")
    os.environ.setdefault("AJO_IDENTITY_PROVIDER", "sandbox")
    os.environ.setdefault("AJO_NOTIFICATIONS_PROVIDER", "sandbox")
    os.environ.setdefault("AJO_DATA_DIR", str(root))
    os.environ.setdefault("AJO_DATABASE_RESILIENCE", "false")
    os.environ.setdefault("FRONTEND_URL", "http://localhost:9520")
    os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:9520")
    os.environ.setdefault("AJO_API_HOST", "127.0.0.1")
    os.environ.setdefault("AJO_API_PORT", "9020")
    os.environ.setdefault("AJO_WORKER_INTERVAL_SECONDS", "30")
    os.environ.setdefault("THROTTLE_LIMIT", "5")
    os.environ.setdefault("THROTTLE_WINDOW", "300")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    configure_schema_environment()
    from app.platform.application import create_platform

    schema = create_platform(database_url="sqlite:///:memory:", sandbox=True).openapi()
    encoded = json.dumps(schema, indent=2, sort_keys=True) + "
"
    if args.output == "-":
        print(encoded, end="")
    else:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
