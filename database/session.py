"""Async SQLAlchemy engine and session helpers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    future=True,
    connect_args={"timeout": 5} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Tune per-connection SQLite settings for local concurrent reads."""

    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""

    async with AsyncSessionLocal() as session:
        yield session


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for read-only request handlers."""

    async with AsyncSessionLocal() as session:
        session.info["read_only"] = True
        yield session


def is_sqlite_locked_error(exc: BaseException) -> bool:
    """Return true for SQLite lock errors raised through SQLAlchemy."""

    if not isinstance(exc, OperationalError):
        return False
    return "database is locked" in str(exc).lower()


async def commit_with_retry(
    session: AsyncSession,
    *,
    max_attempts: int = 3,
    base_delay: float = 0.1,
) -> None:
    """Commit with exponential backoff for transient SQLite lock pressure."""

    for attempt in range(max_attempts):
        try:
            await session.commit()
            return
        except OperationalError as exc:
            if not is_sqlite_locked_error(exc) or attempt >= max_attempts - 1:
                await session.rollback()
                raise
            await asyncio.sleep(base_delay * (2**attempt))
