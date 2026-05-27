"""Durable job queue runner."""

from __future__ import annotations

import logging
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import asc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import ProcessingJob
from database.session import AsyncSessionLocal, commit_with_retry

logger = logging.getLogger(__name__)
_JOB_RUNNER_LOCK = asyncio.Lock()


class JobService:
    """Create and process persisted jobs so work survives restarts."""

    async def enqueue(
        self,
        session: AsyncSession,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        run_at: datetime | None = None,
        max_attempts: int | None = None,
    ) -> ProcessingJob:
        job = ProcessingJob(
            job_type=job_type,
            status="queued",
            priority=priority,
            payload_json=payload or {},
            max_attempts=max_attempts or settings.job_max_attempts,
            next_run_at=run_at,
        )
        session.add(job)
        await session.flush()
        return job

    async def process_due_jobs(self, *, limit: int = 1) -> int:
        """Run queued/retry jobs that are due now."""

        if _JOB_RUNNER_LOCK.locked():
            logger.info("Durable job runner already active; skipping overlapping tick")
            return 0
        async with _JOB_RUNNER_LOCK:
            return await self._process_due_jobs(limit=limit)

    async def _process_due_jobs(self, *, limit: int = 1) -> int:
        now = datetime.now(timezone.utc)
        processed = 0
        async with AsyncSessionLocal() as session:
            await self.recover_interrupted_jobs(session)
            result = await session.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status.in_(["queued", "retry"]),
                    or_(ProcessingJob.next_run_at.is_(None), ProcessingJob.next_run_at <= now),
                )
                .order_by(asc(ProcessingJob.priority), asc(ProcessingJob.created_at))
                .limit(limit)
            )
            jobs = list(result.scalars().all())
            for job in jobs:
                job.status = "running"
                job.locked_at = now
                job.started_at = now
                job.finished_at = None
                job.error = None
                job.attempts = int(job.attempts or 0) + 1
            await commit_with_retry(session)

        for job in jobs:
            await self.run_job(job.id)
            processed += 1
        return processed

    async def run_job(self, job_id: int) -> ProcessingJob:
        """Run one job by ID using fresh service instances."""

        started = time.perf_counter()
        async with AsyncSessionLocal() as session:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")
            if job.status not in {"running", "queued", "retry"}:
                return job
            if job.status in {"queued", "retry"}:
                job.attempts = int(job.attempts or 0) + 1
            job.status = "running"
            job.locked_at = datetime.now(timezone.utc)
            job.started_at = job.started_at or datetime.now(timezone.utc)
            await commit_with_retry(session)

        try:
            result = await self._dispatch(job_id)
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                job = await session.get(ProcessingJob, job_id)
                if not job:
                    raise
                job.error = str(exc)
                job.stderr_tail = str(exc)[-4000:]
                job.finished_at = datetime.now(timezone.utc)
                job.duration_seconds = round(time.perf_counter() - started, 3)
                attempts = int(job.attempts or 0)
                max_attempts = int(job.max_attempts or settings.job_max_attempts)
                if attempts < max_attempts and not _is_non_retryable(exc):
                    job.status = "retry"
                    job.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=min(60, 2**attempts))
                else:
                    job.status = "failed"
                    job.next_run_at = None
                await commit_with_retry(session)
                return job

        async with AsyncSessionLocal() as session:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                raise ValueError(f"Job {job_id} disappeared")
            job.status = "completed"
            job.result_json = result if isinstance(result, dict) else {"result": result}
            job.finished_at = datetime.now(timezone.utc)
            job.duration_seconds = round(time.perf_counter() - started, 3)
            job.next_run_at = None
            await commit_with_retry(session)
            await session.refresh(job)
            return job

    async def recover_interrupted_jobs(self, session: AsyncSession) -> int:
        """Return stale running jobs to retry after a restart/crash."""

        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        result = await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.status == "running",
                or_(ProcessingJob.locked_at.is_(None), ProcessingJob.locked_at < cutoff),
            )
        )
        count = 0
        for job in result.scalars().all():
            attempts = int(job.attempts or 0)
            max_attempts = int(job.max_attempts or settings.job_max_attempts)
            job.status = "retry" if attempts < max_attempts else "failed"
            job.next_run_at = datetime.now(timezone.utc)
            job.error = job.error or "Recovered stale running job after restart."
            count += 1
        return count

    async def _dispatch(self, job_id: int) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")
            job_type = job.job_type
            payload = job.payload_json or {}

        if job_type == "process_new_videos":
            from app.pipeline import ShortsPipeline

            return await ShortsPipeline().process_new_videos(job_id=job_id)
        if job_type == "process_video":
            from app.pipeline import ShortsPipeline

            return await ShortsPipeline().process_video(int(payload["video_id"]), job_id=job_id)
        if job_type == "upload":
            from app.uploader.service import YouTubeUploader

            await YouTubeUploader().upload_by_id(int(payload["upload_id"]))
            async with AsyncSessionLocal() as session:
                from database.models import Upload

                upload = await session.get(Upload, int(payload["upload_id"]))
                if upload and upload.status in {"failed", "blocked"}:
                    raise RuntimeError(upload.error or f"Upload {upload.id} {upload.status}")
                return {"upload_id": payload["upload_id"], "status": upload.status if upload else "processed"}
        if job_type == "refresh_analytics":
            from app.analytics.service import AnalyticsService

            count = await AnalyticsService().refresh_due_snapshots()
            return {"snapshots": count}
        if job_type == "refresh_intelligence":
            from app.intelligence.learning import LearningEngine
            from app.intelligence.revenue import RevenueEstimator
            from app.intelligence.trends import TrendEngine
            from app.intelligence.upload import UploadIntelligenceService

            async with AsyncSessionLocal() as session:
                await TrendEngine().refresh(session)
                await UploadIntelligenceService().build_recommendations(session)
                await RevenueEstimator().refresh(session)
                await LearningEngine().sync_events(session)
                await commit_with_retry(session)
            return {"status": "refreshed"}
        if job_type == "import_existing_clips":
            from app.importer.artifacts import ArtifactImporter

            return await ArtifactImporter().import_existing()
        if job_type == "cleanup_storage":
            from app.storage.lifecycle import StorageLifecycleService

            return await StorageLifecycleService().run_cleanup()
        if job_type == "export_training_dataset":
            from app.intelligence.learning import LearningEngine

            async with AsyncSessionLocal() as session:
                result = await LearningEngine().export_dataset(session)
                await commit_with_retry(session)
                return result

        raise ValueError(f"Unknown job type: {job_type}")


def _is_non_retryable(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"UploadGateError"}
