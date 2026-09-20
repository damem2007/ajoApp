"""Export FastAPI OpenAPI deterministically without starting a server."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="openapi/openapi.json")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="ajo-openapi-") as data_dir:
        os.environ.setdefault("AJO_PLATFORM_DATABASE_URL", "sqlite:///:memory:")
        os.environ.setdefault("AJO_FRONTEND_ORIGIN", "http://frontend.test")
        os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://frontend.test")
        os.environ.setdefault("AJO_DATA_DIR", data_dir)
        os.environ.setdefault("AJO_DATABASE_RESILIENCE", "false")
        os.environ.setdefault("AJO_PROVIDER_MODE", "simulated")
        os.environ.setdefault("AJO_PAYMENTS_PROVIDER", "sandbox")
        os.environ.setdefault("AJO_IDENTITY_PROVIDER", "sandbox")
        os.environ.setdefault("AJO_NOTIFICATIONS_PROVIDER", "sandbox")

        from app.platform.application import create_platform

        schema = create_platform(database_url="sqlite:///:memory:", sandbox=True).openapi()

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
