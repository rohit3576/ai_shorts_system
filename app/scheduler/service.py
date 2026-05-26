"""APScheduler integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import or_, select

from app.config import settings
from app.jobs.service import JobService
from database.models import Upload
from database.session import AsyncSessionLocal, commit_with_retry

logger = logging.getLogger(__name__)


class AppScheduler:
    """Background jobs for scanning, uploading, and analytics refreshes."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.jobs = JobService()

    def start(self) -> None:
        """Start scheduled automation jobs."""

        if not settings.scheduler_enabled:
            logger.info("Scheduler disabled by configuration")
            return
        write_job_defaults = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 300}
        self.scheduler.add_job(
            self.enqueue_scan_job,
            "interval",
            minutes=settings.scheduler_interval_minutes,
            id="scan_and_process",
            **write_job_defaults,
        )
        self.scheduler.add_job(
            self.enqueue_due_upload_jobs,
            "interval",
            minutes=15,
            id="upload_due_clips",
            **write_job_defaults,
        )
        self.scheduler.add_job(
            self.enqueue_analytics_job,
            "interval",
            minutes=settings.analytics_min_refresh_minutes,
            id="refresh_analytics",
            **write_job_defaults,
        )
        self.scheduler.add_job(
            self.jobs.process_due_jobs,
            "interval",
            minutes=settings.job_worker_interval_minutes,
            id="process_durable_jobs",
            **write_job_defaults,
        )
        if settings.cleanup_enabled:
            self.scheduler.add_job(
                self.enqueue_cleanup_job,
                "interval",
                hours=24,
                id="cleanup_storage",
                **write_job_defaults,
            )
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        """Stop scheduled jobs."""

        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def enqueue_scan_job(self) -> None:
        async with AsyncSessionLocal() as session:
            await self.jobs.enqueue(session, job_type="process_new_videos", priority=60)
            await commit_with_retry(session)

    async def enqueue_analytics_job(self) -> None:
        async with AsyncSessionLocal() as session:
            await self.jobs.enqueue(session, job_type="refresh_analytics", priority=20)
            await commit_with_retry(session)

    async def enqueue_cleanup_job(self) -> None:
        async with AsyncSessionLocal() as session:
            await self.jobs.enqueue(session, job_type="cleanup_storage", priority=90)
            await commit_with_retry(session)

    async def enqueue_due_upload_jobs(self) -> None:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Upload).where(
                    Upload.status == "queued",
                    or_(Upload.scheduled_for.is_(None), Upload.scheduled_for <= now),
                )
            )
            for upload in result.scalars().all():
                metadata = dict(upload.metadata_json or {})
                if metadata.get("upload_job_id"):
                    continue
                job = await self.jobs.enqueue(
                    session,
                    job_type="upload",
                    payload={"upload_id": upload.id},
                    priority=30,
                )
                metadata["upload_job_id"] = job.id
                upload.metadata_json = metadata
            await commit_with_retry(session)
