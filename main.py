"""Application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import settings
from app.dashboard.routes import router as dashboard_router
from app.importer.artifacts import ArtifactImporter
from app.logging_config import setup_logging
from app.scheduler.service import AppScheduler
from database.init_db import init_db

scheduler = AppScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize local runtime dependencies."""

    setup_logging(settings.log_level)
    settings.ensure_directories()
    await init_db()
    await ArtifactImporter().import_existing()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(dashboard_router)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "app" / "dashboard" / "static")),
    name="static",
)
app.mount(
    "/media",
    StaticFiles(directory=str(settings.resolve_path(settings.data_dir))),
    name="media",
)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
