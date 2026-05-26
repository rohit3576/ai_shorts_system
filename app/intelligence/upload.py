"""Upload timing and packaging intelligence."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ChannelProfile, Clip, ClipIntelligence, UploadRecommendation, Video


class UploadIntelligenceService:
    """Recommend when and how to publish generated Shorts."""

    async def build_recommendations(self, session: AsyncSession) -> list[UploadRecommendation]:
        result = await session.execute(select(Clip).where(Clip.status.in_(["detected", "generated"])).order_by(desc(Clip.created_at)).limit(60))
        clips = list(result.scalars().all())
        recommendations: list[UploadRecommendation] = []
        for clip in clips:
            existing = await session.scalar(
                select(UploadRecommendation).where(
                    UploadRecommendation.clip_id == clip.id,
                    UploadRecommendation.status.in_(["recommended", "scheduled"]),
                )
            )
            if existing:
                recommendations.append(existing)
                continue
            video = await session.get(Video, clip.video_id)
            profile = await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == video.channel_id)) if video else None
            intel = await session.scalar(select(ClipIntelligence).where(ClipIntelligence.clip_id == clip.id))
            recommended_for = self.next_slot(profile)
            confidence = self.confidence(clip, intel)
            rec = UploadRecommendation(
                channel_id=video.channel_id if video else None,
                clip_id=clip.id,
                recommended_for=recommended_for,
                confidence_score=confidence,
                rationale=self.rationale(profile, intel),
                title=clip.title,
                hashtags=clip.hashtags or ["#shorts"],
                thumbnail_prompt=self.thumbnail_prompt(clip, intel),
                status="recommended",
                metadata_json={"source": "local_upload_intelligence"},
            )
            session.add(rec)
            recommendations.append(rec)
        await session.flush()
        return recommendations

    async def payload(self, session: AsyncSession) -> dict[str, Any]:
        result = await session.execute(
            select(UploadRecommendation).order_by(desc(UploadRecommendation.confidence_score)).limit(80)
        )
        recommendations = list(result.scalars().all())
        ordered = sorted(recommendations, key=lambda item: item.confidence_score, reverse=True)
        return {
            "recommended_today": [self._serialize(item) for item in ordered[:8]],
            "suggested_times": await self.suggested_times(session),
            "schedule_patterns": [
                {"label": "Morning test", "time": "08:30", "score": 72, "metric_source": "PREDICTED"},
                {"label": "Lunch scroll", "time": "12:30", "score": 81, "metric_source": "PREDICTED"},
                {"label": "Evening prime", "time": "18:30", "score": 88, "metric_source": "PREDICTED"},
                {"label": "Late-night binge", "time": "22:00", "score": 79, "metric_source": "PREDICTED"},
            ],
            "auto_upload_ready": [self._serialize(item) for item in ordered if item.confidence_score >= 0.84][:5],
        }

    async def suggested_times(self, session: AsyncSession) -> list[dict[str, Any]]:
        result = await session.execute(select(ChannelProfile).where(ChannelProfile.active.is_(True)))
        profiles = list(result.scalars().all())
        if not profiles:
            return [
                {"channel": "Network default", "time": "12:30", "score": 81, "metric_source": "PREDICTED"},
                {"channel": "Network default", "time": "18:30", "score": 88, "metric_source": "PREDICTED"},
                {"channel": "Network default", "time": "22:00", "score": 79, "metric_source": "PREDICTED"},
            ]
        rows: list[dict[str, Any]] = []
        for profile in profiles:
            for index, slot in enumerate((profile.schedule_json or {}).get("times", ["12:30", "18:30"])):
                rows.append(
                    {
                        "channel_id": profile.channel_id,
                        "niche": profile.niche_type,
                        "time": slot,
                        "score": 88 - (index * 5),
                        "metric_source": "PREDICTED",
                    }
                )
        return rows

    def next_slot(self, profile: ChannelProfile | None) -> datetime:
        now = datetime.now().astimezone()
        slots = (profile.schedule_json or {}).get("times", ["12:30", "18:30", "21:00"]) if profile else ["12:30", "18:30", "21:00"]
        candidates = []
        for day_offset in range(0, 3):
            target_day = now.date() + timedelta(days=day_offset)
            for slot in slots:
                hour, minute = [int(part) for part in slot.split(":", 1)]
                candidates.append(datetime.combine(target_day, time(hour, minute), tzinfo=now.tzinfo))
        return next((item for item in sorted(candidates) if item > now + timedelta(minutes=10)), sorted(candidates)[-1])

    def confidence(self, clip: Clip, intel: ClipIntelligence | None) -> float:
        if intel:
            return round(max(0.05, min(0.98, (intel.retention_score / 100 * 0.68) + (intel.viral_probability * 0.32))), 3)
        return round(max(0.05, min(0.95, float(clip.viral_score or 0))), 3)

    def rationale(self, profile: ChannelProfile | None, intel: ClipIntelligence | None) -> str:
        niche = profile.niche_type if profile else "network"
        if intel:
            reasons = ", ".join((intel.reasons_json or [])[:3])
            return f"{niche} slot matched to {intel.retention_score:.1f}% retention score: {reasons or 'strong local signals'}."
        return f"{niche} slot selected from default posting cadence and clip score."

    def thumbnail_prompt(self, clip: Clip, intel: ClipIntelligence | None) -> str:
        hook = clip.hook_text or clip.title or "viral moment"
        mood = intel.hook_type if intel else "curiosity"
        return f"High-contrast vertical thumbnail, close-up emotion, bold 3-word hook '{hook}', {mood} mood"

    def _serialize(self, item: UploadRecommendation) -> dict[str, Any]:
        return {
            "id": item.id,
            "channel_id": item.channel_id,
            "clip_id": item.clip_id,
            "recommended_for": item.recommended_for.isoformat() if item.recommended_for else None,
            "confidence_score": round(item.confidence_score * 100, 1),
            "rationale": item.rationale,
            "title": item.title,
            "hashtags": item.hashtags or [],
            "thumbnail_prompt": item.thumbnail_prompt,
            "status": item.status,
            "metric_source": "PREDICTED",
        }
