"""Revenue estimation for a local-first Shorts network."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AnalyticsSnapshot, Channel, ChannelProfile, Clip, RevenueSnapshot, Upload, Video


class RevenueEstimator:
    """Estimate revenue from Shorts analytics without paid finance tools."""

    async def refresh(self, session: AsyncSession) -> list[RevenueSnapshot]:
        latest = await self._latest_snapshots(session)
        rows: list[RevenueSnapshot] = []
        now = datetime.now(timezone.utc)
        for snapshot in latest.values():
            clip = await session.get(Clip, snapshot.clip_id)
            video = await session.get(Video, clip.video_id) if clip else None
            profile = await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == video.channel_id)) if video else None
            rpm = profile.estimated_shorts_rpm if profile else 0.06
            retention = float(snapshot.retention_avg or 55)
            estimated_watch_hours = snapshot.views * ((clip.end_time - clip.start_time) if clip else 30) * (retention / 100) / 3600
            revenue = (snapshot.views / 1000) * rpm
            existing = await session.scalar(
                select(RevenueSnapshot).where(
                    RevenueSnapshot.clip_id == snapshot.clip_id,
                    RevenueSnapshot.upload_id == snapshot.upload_id,
                    RevenueSnapshot.period_end == snapshot.captured_at,
                )
            )
            row = existing or RevenueSnapshot(
                channel_id=video.channel_id if video else None,
                clip_id=snapshot.clip_id,
                upload_id=snapshot.upload_id,
                period_start=snapshot.captured_at - timedelta(days=1),
                period_end=snapshot.captured_at,
            )
            row.views = snapshot.views
            row.watch_time_hours = round(estimated_watch_hours, 2)
            row.estimated_rpm = rpm
            row.estimated_revenue = round(revenue, 4)
            row.projected_monthly_revenue = round(revenue * 30, 2)
            row.metadata_json = {"source": "local_revenue_estimator", "retention_avg": snapshot.retention_avg}
            if not existing:
                session.add(row)
            rows.append(row)
        await session.flush()
        return rows

    async def payload(self, session: AsyncSession) -> dict[str, Any]:
        rows = await self.refresh(session)
        if not rows:
            rows = self._demo_rows()
        total_revenue = sum(item.estimated_revenue for item in rows)
        projected = sum(item.projected_monthly_revenue for item in rows)
        views = sum(item.views for item in rows)
        watch_time = sum(item.watch_time_hours for item in rows)
        by_channel = await self._channel_breakdown(session, rows)
        return {
            "summary": {
                "estimated_revenue": round(total_revenue, 2),
                "projected_monthly": round(projected, 2),
                "views": views,
                "watch_time_hours": round(watch_time, 1),
                "average_rpm": round(sum(item.estimated_rpm for item in rows) / max(1, len(rows)), 3),
                "monthly_growth": self._growth(rows),
            },
            "top_channels": by_channel,
            "top_shorts": [self._serialize(item) for item in sorted(rows, key=lambda row: row.estimated_revenue, reverse=True)[:8]],
            "forecast": self._forecast(projected),
        }

    async def _latest_snapshots(self, session: AsyncSession) -> dict[int, AnalyticsSnapshot]:
        result = await session.execute(select(AnalyticsSnapshot).order_by(desc(AnalyticsSnapshot.captured_at)))
        latest: dict[int, AnalyticsSnapshot] = {}
        for snapshot in result.scalars().all():
            latest.setdefault(snapshot.clip_id, snapshot)
        return latest

    async def _channel_breakdown(self, session: AsyncSession, rows: list[RevenueSnapshot]) -> list[dict[str, Any]]:
        totals: dict[int | None, dict[str, Any]] = defaultdict(lambda: {"views": 0, "revenue": 0.0, "clips": 0})
        for row in rows:
            bucket = totals[row.channel_id]
            bucket["views"] += row.views
            bucket["revenue"] += row.estimated_revenue
            bucket["clips"] += 1
        output = []
        for channel_id, values in totals.items():
            channel = await session.get(Channel, channel_id) if channel_id else None
            output.append(
                {
                    "channel_id": channel_id,
                    "name": channel.name if channel else "Network demo",
                    "views": values["views"],
                    "estimated_revenue": round(values["revenue"], 2),
                    "clips": values["clips"],
                }
            )
        return sorted(output, key=lambda item: item["estimated_revenue"], reverse=True)

    def _growth(self, rows: list[RevenueSnapshot]) -> float:
        if len(rows) < 2:
            return 0.0
        ordered = sorted(rows, key=lambda row: row.period_end or row.created_at)
        midpoint = max(1, len(ordered) // 2)
        early = sum(row.estimated_revenue for row in ordered[:midpoint])
        late = sum(row.estimated_revenue for row in ordered[midpoint:])
        return round(((late - early) / max(0.01, early)) * 100, 1)

    def _forecast(self, projected: float) -> list[dict[str, Any]]:
        return [
            {"label": "30 days", "value": round(projected, 2)},
            {"label": "90 days", "value": round(projected * 3.2, 2)},
            {"label": "180 days", "value": round(projected * 7.1, 2)},
        ]

    def _serialize(self, item: RevenueSnapshot) -> dict[str, Any]:
        return {
            "clip_id": item.clip_id,
            "views": item.views,
            "watch_time_hours": item.watch_time_hours,
            "estimated_rpm": item.estimated_rpm,
            "estimated_revenue": item.estimated_revenue,
            "projected_monthly_revenue": item.projected_monthly_revenue,
        }

    def _demo_rows(self) -> list[RevenueSnapshot]:
        now = datetime.now(timezone.utc)
        return [
            RevenueSnapshot(
                views=1200,
                watch_time_hours=8.4,
                estimated_rpm=0.06,
                estimated_revenue=0.07,
                projected_monthly_revenue=2.1,
                period_end=now,
            )
        ]
