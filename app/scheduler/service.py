"""APScheduler integration."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.analytics.service import AnalyticsService
from app.config import settings
from app.pipeline import ShortsPipeline
from app.uploader.service import YouTubeUploader

logger = logging.getLogger(__name__)


class AppScheduler:
    """Background jobs for scanning, uploading, and analytics refreshes."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.pipeline = ShortsPipeline()
        self.uploader = YouTubeUploader()
        self.analytics = AnalyticsService()

    def start(self) -> None:
        """Start scheduled automation jobs."""

        if not settings.scheduler_enabled:
            logger.info("Scheduler disabled by configuration")
            return
        self.scheduler.add_job(
            self.pipeline.process_new_videos,
            "interval",
            minutes=settings.scheduler_interval_minutes,
            id="scan_and_process",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self.uploader.process_due_uploads,
            "interval",
            minutes=15,
            id="upload_due_clips",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self.analytics.refresh_all,
            "interval",
            hours=settings.analytics_refresh_hours,
            id="refresh_analytics",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        """Stop scheduled jobs."""

        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

