"""YouTube analytics collection."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.uploader.auth import YouTubeAuth
from database.models import AnalyticsSnapshot, Clip, Upload
from database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Collect and summarize YouTube Shorts analytics."""

    def __init__(self, auth: YouTubeAuth | None = None) -> None:
        self.auth = auth or YouTubeAuth()

    async def refresh_all(self) -> int:
        """Refresh analytics for all uploaded clips."""

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Upload).where(
                    Upload.status == "uploaded",
                    Upload.youtube_video_id.is_not(None),
                )
            )
            uploads = list(result.scalars().all())
            for upload in uploads:
                await self.refresh_upload(session, upload)
            await session.commit()
            return len(uploads)

    async def refresh_upload(self, session: AsyncSession, upload: Upload) -> AnalyticsSnapshot:
        """Create a fresh analytics snapshot for one uploaded Short."""

        if not upload.youtube_video_id:
            raise ValueError(f"Upload {upload.id} has no YouTube video ID")
        stats = await asyncio.to_thread(self._fetch_stats_sync, upload.youtube_video_id)
        snapshot = AnalyticsSnapshot(
            clip_id=upload.clip_id,
            upload_id=upload.id,
            views=int(stats.get("views") or 0),
            likes=int(stats.get("likes") or 0),
            comments=int(stats.get("comments") or 0),
            ctr=stats.get("ctr"),
            retention_avg=stats.get("retention_avg"),
        )
        session.add(snapshot)
        await session.flush()
        logger.info("Captured analytics for upload %s", upload.id)
        return snapshot

    async def latest_summary(self, session: AsyncSession) -> dict[str, Any]:
        """Return dashboard/API analytics summary."""

        result = await session.execute(
            select(AnalyticsSnapshot)
            .order_by(desc(AnalyticsSnapshot.captured_at))
            .limit(100)
        )
        snapshots = list(result.scalars().all())
        top_result = await session.execute(
            select(Clip)
            .join(AnalyticsSnapshot, AnalyticsSnapshot.clip_id == Clip.id)
            .order_by(desc(AnalyticsSnapshot.views))
            .limit(10)
        )
        return {
            "snapshots": snapshots,
            "top_clips": list(top_result.scalars().all()),
        }

    def _fetch_stats_sync(self, youtube_video_id: str) -> dict[str, Any]:
        youtube = self.auth.build("youtube", "v3")
        response = youtube.videos().list(part="statistics", id=youtube_video_id).execute()
        items = response.get("items", [])
        statistics = items[0].get("statistics", {}) if items else {}
        stats: dict[str, Any] = {
            "views": int(statistics.get("viewCount", 0)),
            "likes": int(statistics.get("likeCount", 0)),
            "comments": int(statistics.get("commentCount", 0)),
            "ctr": None,
            "retention_avg": None,
        }

        try:
            analytics = self.auth.build("youtubeAnalytics", "v2")
            today = date.today()
            report = (
                analytics.reports()
                .query(
                    ids="channel==MINE",
                    startDate=(today - timedelta(days=90)).isoformat(),
                    endDate=today.isoformat(),
                    metrics="averageViewPercentage,impressionsClickThroughRate",
                    filters=f"video=={youtube_video_id}",
                )
                .execute()
            )
            rows = report.get("rows") or []
            if rows:
                stats["retention_avg"] = float(rows[0][0])
                stats["ctr"] = float(rows[0][1])
        except Exception as exc:
            logger.debug("Advanced YouTube Analytics metrics unavailable: %s", exc)

        return stats

