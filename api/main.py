"""Top-level `api/` entrypoint exposing `app` for FastAPI/Uvicorn (`uvicorn api.main:app --reload`) and CLI."""

from __future__ import annotations

from youtube_studio.api.app import create_api_app, create_fastapi_app
from youtube_studio.api.cli import main

app = create_fastapi_app(run_mode="desktop_local")
local_api = create_api_app(run_mode="desktop_local")

__all__ = ["app", "local_api", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
