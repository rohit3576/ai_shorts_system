"""Database initialization helpers."""

from __future__ import annotations

import database.models  # noqa: F401 - import models so metadata is populated
from database.base import Base
from database.migrations import run_migrations
from database.session import engine


async def init_db() -> None:
    """Create all configured database tables."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_migrations)
