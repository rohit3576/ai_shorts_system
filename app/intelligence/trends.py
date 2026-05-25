"""Local-first trend mining from metadata and performance history."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AnalyticsSnapshot, ChannelProfile, Clip, LearningEvent, TrendSignal, Video

STOPWORDS = {
    "the", "and", "for", "you", "with", "this", "that", "from", "they", "have", "what", "when",
    "where", "your", "about", "shorts", "video", "full", "into", "after", "before", "there",
}


class TrendEngine:
    """Mine trends without paid APIs by weighting local content outcomes."""

    async def refresh(self, session: AsyncSession) -> list[TrendSignal]:
        weights: dict[str, Counter[str]] = defaultdict(Counter)
        video_result = await session.execute(select(Video).order_by(desc(Video.created_at)).limit(300))
        for video in video_result.scalars().all():
            niche = await self._niche_for_video(session, video)
            for token in self._tokens(f"{video.title} {video.description or ''}"):
                weights[niche][token] += 1

        clip_result = await session.execute(select(Clip).order_by(desc(Clip.created_at)).limit(300))
        clips = list(clip_result.scalars().all())
        analytics_by_clip = await self._views_by_clip(session)
        for clip in clips:
            video = await session.get(Video, clip.video_id)
            niche = await self._niche_for_video(session, video) if video else "general"
            view_weight = 1 + min(8, analytics_by_clip.get(clip.id, 0) / 1000)
            text = " ".join([clip.title or "", clip.hook_text or "", clip.reason or "", " ".join(clip.hashtags or [])])
            for token in self._tokens(text):
                weights[niche][token] += view_weight

        now = datetime.now(timezone.utc)
        signals: list[TrendSignal] = []
        for niche, counter in weights.items():
            for keyword, score in counter.most_common(30):
                existing = await session.scalar(
                    select(TrendSignal).where(
                        TrendSignal.niche_type == niche,
                        TrendSignal.keyword == keyword,
                        TrendSignal.source == "local_metadata",
                    )
                )
                signal = existing or TrendSignal(
                    niche_type=niche,
                    keyword=keyword,
                    source="local_metadata",
                    first_seen_at=now,
                )
                previous_score = signal.score or 0
                signal.score = round(float(score), 2)
                signal.velocity = round(float(score) - previous_score, 2)
                signal.evidence_count = int(max(1, score))
                signal.last_seen_at = now
                signal.metadata_json = {"engine": "local_trend_engine"}
                if not existing:
                    session.add(signal)
                signals.append(signal)
        await session.flush()
        return sorted(signals, key=lambda item: item.score, reverse=True)

    async def payload(self, session: AsyncSession) -> dict[str, Any]:
        signals = await self.refresh(session)
        by_niche: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in signals[:80]:
            by_niche[item.niche_type].append(self._serialize(item))
        return {
            "top_topics": [self._serialize(item) for item in signals[:12]],
            "by_niche": dict(by_niche),
            "heat": await self.heat_payload(session, signals),
            "trend_types": [
                {"name": "Curiosity hooks", "score": self._trend_score(signals, ["why", "secret", "truth"])},
                {"name": "Survival stakes", "score": self._trend_score(signals, ["survive", "danger", "risk"])},
                {"name": "Gaming reversals", "score": self._trend_score(signals, ["insane", "wild", "wrong"])},
                {"name": "Emotional reveals", "score": self._trend_score(signals, ["actually", "finally", "shock"])},
            ],
        }

    async def heat_payload(self, session: AsyncSession, signals: list[TrendSignal]) -> dict[str, Any]:
        """Return heat buckets for rising, saturated, and hook/emotion trends."""

        learning_result = await session.execute(select(LearningEvent).order_by(desc(LearningEvent.learned_at)).limit(300))
        events = list(learning_result.scalars().all())
        hooks = self._learning_heat(events, "hook_type")
        emotions = self._emotion_heat(events)
        return {
            "rising_topics": [
                self._serialize(item)
                for item in sorted(signals, key=lambda signal: signal.velocity, reverse=True)[:10]
                if item.velocity >= 0
            ],
            "overused_trends": [
                self._serialize(item)
                for item in sorted(signals, key=lambda signal: (signal.score, -signal.velocity), reverse=True)[:10]
                if item.score >= 6 and item.velocity <= 0
            ],
            "trending_games": [self._serialize(item) for item in signals if item.niche_type == "gaming"][:10],
            "trending_emotions": emotions,
            "trending_hooks": hooks,
        }

    def _learning_heat(self, events: list[LearningEvent], key: str) -> list[dict[str, Any]]:
        buckets: dict[str, list[float]] = defaultdict(list)
        for event in events:
            value = (event.features_json or {}).get(key)
            if value:
                buckets[str(value)].append(float(event.outcome_score or 0))
        return [
            {
                "label": label,
                "heat": round(sum(values) / len(values), 1),
                "count": len(values),
                "status": "rising" if sum(values) / len(values) >= 70 else "testing",
            }
            for label, values in sorted(buckets.items(), key=lambda item: sum(item[1]) / len(item[1]), reverse=True)[:10]
        ]

    def _emotion_heat(self, events: list[LearningEvent]) -> list[dict[str, Any]]:
        buckets: dict[str, list[float]] = defaultdict(list)
        for event in events:
            features = event.features_json or {}
            for key in ["emotional_score", "viral_probability", "watchability_score"]:
                value = features.get(key)
                if value is not None:
                    buckets[key.replace("_score", "").replace("_", " ")].append(float(value))
        return [
            {"label": label, "heat": round(sum(values) / len(values), 1), "count": len(values)}
            for label, values in sorted(buckets.items(), key=lambda item: sum(item[1]) / len(item[1]), reverse=True)
        ]

    async def _views_by_clip(self, session: AsyncSession) -> dict[int, int]:
        result = await session.execute(select(AnalyticsSnapshot))
        views: dict[int, int] = {}
        for snapshot in result.scalars().all():
            views[snapshot.clip_id] = max(views.get(snapshot.clip_id, 0), snapshot.views)
        return views

    async def _niche_for_video(self, session: AsyncSession, video: Video | None) -> str:
        if not video:
            return "general"
        profile = await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == video.channel_id))
        return profile.niche_type if profile else "general"

    def _tokens(self, text: str) -> list[str]:
        raw_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower())
        return [token for token in raw_tokens if token not in STOPWORDS and len(token) <= 24]

    def _trend_score(self, signals: list[TrendSignal], keywords: list[str]) -> int:
        score = sum(item.score for item in signals if item.keyword in keywords)
        return int(max(0, min(100, score * 6)))

    def _serialize(self, item: TrendSignal) -> dict[str, Any]:
        return {
            "keyword": item.keyword,
            "niche_type": item.niche_type,
            "score": round(item.score, 1),
            "velocity": round(item.velocity, 1),
            "evidence_count": item.evidence_count,
            "source": item.source,
            "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        }
