"""Negative sample storage for learning from failures and rejections."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Clip, LearningEvent, NegativeSample, Video

NEGATIVE_REVIEW_LABELS = {
    "boring",
    "weak hook",
    "no payoff",
    "repetitive",
    "confusing",
    "low energy",
    "policy risk",
}


class NegativeSampleService:
    """Record examples the system should avoid repeating."""

    async def record(
        self,
        session: AsyncSession,
        *,
        category: str,
        clip: Clip | None = None,
        video: Video | None = None,
        reason: str | None = None,
        labels: list[str] | None = None,
        severity: float = 50.0,
        features: dict[str, Any] | None = None,
        source: str = "system",
    ) -> NegativeSample:
        """Create one negative sample and matching learning event if missing."""

        existing = None
        if clip:
            existing = await session.scalar(
                select(NegativeSample).where(
                    NegativeSample.clip_id == clip.id,
                    NegativeSample.category == category,
                    NegativeSample.source == source,
                )
            )
        sample = existing or NegativeSample(category=category, source=source)
        sample.clip_id = clip.id if clip else None
        sample.video_id = video.id if video else clip.video_id if clip else None
        sample.reason = reason
        sample.labels_json = labels or []
        sample.severity = max(0.0, min(100.0, severity))
        sample.features_json = features or self._clip_features(clip)
        if not existing:
            session.add(sample)
            await session.flush()
            session.add(
                LearningEvent(
                    channel_id=(await self._channel_id(session, clip, video)),
                    clip_id=clip.id if clip else None,
                    event_type=f"negative_{category}",
                    outcome_score=max(0.0, 100.0 - sample.severity),
                    metrics_json={
                        "metric_source": "REAL" if source == "human_review" else "PREDICTED",
                        "negative_sample_id": sample.id,
                        "labels": sample.labels_json,
                    },
                    features_json=sample.features_json,
                )
            )
        await session.flush()
        return sample

    async def record_review(
        self,
        session: AsyncSession,
        *,
        clip: Clip,
        action: str,
        labels: list[str],
        reason: str | None,
    ) -> list[NegativeSample]:
        """Turn human review labels into durable training negatives."""

        samples: list[NegativeSample] = []
        normalized = [label.strip().lower() for label in labels if label.strip()]
        if action == "rejected" and not normalized:
            normalized = ["rejected"]
        for label in normalized:
            if action == "rejected" or label in NEGATIVE_REVIEW_LABELS:
                samples.append(
                    await self.record(
                        session,
                        category=label.replace(" ", "_"),
                        clip=clip,
                        reason=reason or label,
                        labels=normalized,
                        severity=82.0 if action == "rejected" else 65.0,
                        source="human_review",
                    )
                )
        return samples

    def _clip_features(self, clip: Clip | None) -> dict[str, Any]:
        if not clip:
            return {}
        metadata = clip.metadata_json or {}
        return {
            "hook_text": clip.hook_text,
            "title": clip.title,
            "duration": round((clip.end_time or 0) - (clip.start_time or 0), 1),
            "viral_score": clip.viral_score,
            "dead_zone_score": metadata.get("dead_zone_score"),
            "watchability_score": metadata.get("watchability_score"),
            "transcript_snippet": metadata.get("transcript_excerpt"),
        }

    async def _channel_id(self, session: AsyncSession, clip: Clip | None, video: Video | None) -> int | None:
        if video:
            return video.channel_id
        if clip:
            source_video = await session.get(Video, clip.video_id)
            return source_video.channel_id if source_video else None
        return None
