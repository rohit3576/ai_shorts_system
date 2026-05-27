"""Stage tracking helpers for durable jobs."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import JobStage


@asynccontextmanager
async def job_stage(
    session: AsyncSession,
    job_id: int | None,
    name: str,
    *,
    stage_order: int = 0,
) -> AsyncIterator[JobStage | None]:
    """Mark a job stage as running, then completed or failed."""

    if job_id is None:
        yield None
        return

    stage = await start_stage(session, job_id, name, stage_order=stage_order)
    started = time.perf_counter()
    try:
        yield stage
    except Exception as exc:
        await fail_stage(session, stage, exc, started)
        raise
    else:
        await finish_stage(session, stage, started)


async def start_stage(session: AsyncSession, job_id: int, name: str, *, stage_order: int = 0) -> JobStage:
    stage = await session.scalar(select(JobStage).where(JobStage.job_id == job_id, JobStage.name == name))
    if not stage:
        stage = JobStage(job_id=job_id, name=name, stage_order=stage_order)
        session.add(stage)
    stage.status = "running"
    stage.attempts = int(stage.attempts or 0) + 1
    stage.started_at = datetime.now(timezone.utc)
    stage.finished_at = None
    stage.error = None
    await session.flush()
    return stage


async def finish_stage(session: AsyncSession, stage: JobStage, started: float) -> None:
    stage.status = "completed"
    stage.finished_at = datetime.now(timezone.utc)
    stage.duration_seconds = round(time.perf_counter() - started, 3)
    stage.error = None
    await session.flush()


async def fail_stage(session: AsyncSession, stage: JobStage, exc: Exception, started: float) -> None:
    stage.status = "failed"
    stage.finished_at = datetime.now(timezone.utc)
    stage.duration_seconds = round(time.perf_counter() - started, 3)
    stage.error = str(exc)
    stage.stderr_tail = str(exc)[-4000:]
    await session.flush()
