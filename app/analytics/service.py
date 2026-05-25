"""YouTube analytics collection."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.uploader.auth import YouTubeAuth
from database.models import AnalyticsSnapshot, Clip, Upload
from database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Collect and summarize YouTube Shorts analytics."""

    def __init__(self, auth: YouTubeAuth | None = None) -> None:
        self.auth = auth or YouTubeAuth()

    async def refresh_all(self) -> int:
        """Refresh analytics for all uploaded clips now."""

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

    async def refresh_due_snapshots(self) -> int:
        """Capture scheduled 1h/6h/24h/72h/7d snapshots when due."""

        captured = 0
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Upload).where(
                    Upload.status == "uploaded",
                    Upload.youtube_video_id.is_not(None),
                    Upload.uploaded_at.is_not(None),
                )
            )
            for upload in result.scalars().all():
                if not upload.uploaded_at:
                    continue
                uploaded_at = _as_aware_utc(upload.uploaded_at)
                age_hours = (now - uploaded_at).total_seconds() / 3600
                for window in settings.analytics_windows:
                    if age_hours < window:
                        continue
                    existing = await session.scalar(
                        select(AnalyticsSnapshot).where(
                            AnalyticsSnapshot.upload_id == upload.id,
                            AnalyticsSnapshot.snapshot_window_hours == window,
                            AnalyticsSnapshot.metric_source == "REAL",
                        )
                    )
                    if existing:
                        continue
                    await self.refresh_upload(session, upload, snapshot_window_hours=window)
                    captured += 1
            await session.commit()
        return captured

    async def refresh_upload(
        self,
        session: AsyncSession,
        upload: Upload,
        *,
        snapshot_window_hours: int | None = None,
    ) -> AnalyticsSnapshot:
        """Create a fresh analytics snapshot for one uploaded Short."""

        if not upload.youtube_video_id:
            raise ValueError(f"Upload {upload.id} has no YouTube video ID")
        stats = await asyncio.to_thread(
            self._fetch_stats_sync,
            upload.youtube_video_id,
            upload.uploaded_at,
        )
        uploaded_at = _as_aware_utc(upload.uploaded_at) if upload.uploaded_at else None
        upload_age_hours = (
            (datetime.now(timezone.utc) - uploaded_at).total_seconds() / 3600
            if uploaded_at
            else None
        )
        snapshot = AnalyticsSnapshot(
            clip_id=upload.clip_id,
            upload_id=upload.id,
            views=int(stats.get("views") or 0),
            likes=int(stats.get("likes") or 0),
            comments=int(stats.get("comments") or 0),
            ctr=stats.get("ctr"),
            retention_avg=stats.get("average_view_percentage"),
            average_view_duration_seconds=stats.get("average_view_duration_seconds"),
            average_view_percentage=stats.get("average_view_percentage"),
            watch_time_minutes=stats.get("watch_time_minutes"),
            watch_percentage=stats.get("average_view_percentage"),
            subscriber_gain=stats.get("subscriber_gain"),
            shares=stats.get("shares"),
            impressions=stats.get("impressions"),
            rewatch_rate=stats.get("rewatch_rate"),
            snapshot_window_hours=snapshot_window_hours,
            upload_age_hours=round(upload_age_hours, 2) if upload_age_hours is not None else None,
            metric_source="REAL",
            capture_status="captured" if not stats.get("unavailable_metrics") else "partial",
            unavailable_metrics=stats.get("unavailable_metrics") or [],
            raw_json=stats.get("raw_json") or {},
        )
        session.add(snapshot)
        await session.flush()
        logger.info("Captured analytics for upload %s", upload.id)
        return snapshot

    async def latest_summary(self, session: AsyncSession) -> dict[str, Any]:
        """Return dashboard/API analytics summary."""

        result = await session.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.metric_source == "REAL")
            .order_by(desc(AnalyticsSnapshot.captured_at))
            .limit(100)
        )
        snapshots = list(result.scalars().all())
        top_result = await session.execute(
            select(Clip)
            .join(AnalyticsSnapshot, AnalyticsSnapshot.clip_id == Clip.id)
            .where(AnalyticsSnapshot.metric_source == "REAL")
            .order_by(desc(AnalyticsSnapshot.views))
            .limit(10)
        )
        return {
            "snapshots": snapshots,
            "top_clips": list(top_result.scalars().all()),
        }

    def _fetch_stats_sync(self, youtube_video_id: str, uploaded_at: datetime | None) -> dict[str, Any]:
        youtube = self.auth.build("youtube", "v3")
        response = youtube.videos().list(part="statistics,snippet", id=youtube_video_id).execute()
        items = response.get("items", [])
        statistics = items[0].get("statistics", {}) if items else {}
        snippet = items[0].get("snippet", {}) if items else {}
        unavailable: list[str] = ["rewatch_rate"]
        stats: dict[str, Any] = {
            "views": int(statistics.get("viewCount", 0)),
            "likes": int(statistics.get("likeCount", 0)),
            "comments": int(statistics.get("commentCount", 0)),
            "ctr": None,
            "average_view_duration_seconds": None,
            "average_view_percentage": None,
            "watch_time_minutes": None,
            "subscriber_gain": None,
            "shares": None,
            "impressions": None,
            "rewatch_rate": None,
            "unavailable_metrics": unavailable,
            "raw_json": {"data_api": {"statistics": statistics, "snippet": snippet}},
        }

        try:
            analytics = self.auth.build("youtubeAnalytics", "v2")
            today = date.today()
            start = _analytics_start_date(uploaded_at, today)
            core = self._query_analytics(
                analytics,
                youtube_video_id=youtube_video_id,
                start_date=start,
                end_date=today,
                metrics=[
                    "views",
                    "likes",
                    "comments",
                    "shares",
                    "subscribersGained",
                    "estimatedMinutesWatched",
                    "averageViewDuration",
                    "averageViewPercentage",
                ],
            )
            stats["raw_json"]["analytics_core"] = core.get("raw")
            if core.get("row"):
                row = core["row"]
                stats["views"] = int(row.get("views") or stats["views"])
                stats["likes"] = int(row.get("likes") or stats["likes"])
                stats["comments"] = int(row.get("comments") or stats["comments"])
                stats["shares"] = _optional_int(row.get("shares"))
                stats["subscriber_gain"] = _optional_int(row.get("subscribersGained"))
                stats["watch_time_minutes"] = _optional_float(row.get("estimatedMinutesWatched"))
                stats["average_view_duration_seconds"] = _optional_float(row.get("averageViewDuration"))
                stats["average_view_percentage"] = _optional_float(row.get("averageViewPercentage"))
            else:
                unavailable.extend(
                    [
                        "shares",
                        "subscribersGained",
                        "estimatedMinutesWatched",
                        "averageViewDuration",
                        "averageViewPercentage",
                    ]
                )

            ctr = self._query_analytics(
                analytics,
                youtube_video_id=youtube_video_id,
                start_date=start,
                end_date=today,
                metrics=["impressions", "impressionsClickThroughRate"],
            )
            stats["raw_json"]["analytics_ctr"] = ctr.get("raw")
            if ctr.get("row"):
                row = ctr["row"]
                stats["impressions"] = _optional_int(row.get("impressions"))
                stats["ctr"] = _optional_float(row.get("impressionsClickThroughRate"))
            else:
                unavailable.extend(["impressions", "impressionsClickThroughRate"])
        except Exception as exc:
            logger.debug("Advanced YouTube Analytics metrics unavailable: %s", exc)
            unavailable.extend(
                [
                    "shares",
                    "subscribersGained",
                    "estimatedMinutesWatched",
                    "averageViewDuration",
                    "averageViewPercentage",
                    "impressions",
                    "impressionsClickThroughRate",
                    "rewatch_rate",
                ]
            )

        return stats

    def _query_analytics(
        self,
        analytics: Any,
        *,
        youtube_video_id: str,
        start_date: date,
        end_date: date,
        metrics: list[str],
    ) -> dict[str, Any]:
        report = (
            analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=start_date.isoformat(),
                endDate=end_date.isoformat(),
                metrics=",".join(metrics),
                filters=f"video=={youtube_video_id}",
            )
            .execute()
        )
        rows = report.get("rows") or []
        if not rows:
            return {"raw": report, "row": None}
        return {"raw": report, "row": dict(zip(metrics, rows[0], strict=False))}


def _analytics_start_date(uploaded_at: datetime | None, today: date) -> date:
    if not uploaded_at:
        return today - timedelta(days=90)
    return max(_as_aware_utc(uploaded_at).date(), today - timedelta(days=90))


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
