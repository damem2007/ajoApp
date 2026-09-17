# FastAPI backend

The API implementation remains in the Python `backend/app/platform/` package to preserve migration, worker and deployment imports. The root `app` symlink keeps existing scripts and imports compatible. Start from the repository root:

    .venv/bin/uvicorn app.platform.application:app --host 127.0.0.1 --port 8000

The independently built Next.js client lives in `frontend/` and proxies `/api/*`, `/health` and `/ready` to this service. Financial rules, access controls and CMS publication remain in FastAPI. The historical HTML routes are compatibility entry points during rollout; their assets are owned by the frontend.
