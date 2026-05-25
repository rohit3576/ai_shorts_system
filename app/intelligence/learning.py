"""Self-improving local learning dataset builder."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import AnalyticsSnapshot, ChannelProfile, Clip, ClipIntelligence, LearningEvent, Upload, Video


class LearningEngine:
    """Convert clip outcomes into reusable local training examples."""

    async def sync_events(self, session: AsyncSession) -> int:
        result = await session.execute(select(Clip).order_by(desc(Clip.created_at)).limit(500))
        changed = 0
        for clip in result.scalars().all():
            existing = await session.scalar(select(LearningEvent).where(LearningEvent.clip_id == clip.id))
            intel = await session.scalar(select(ClipIntelligence).where(ClipIntelligence.clip_id == clip.id))
            latest = await session.scalar(
                select(AnalyticsSnapshot)
                .where(AnalyticsSnapshot.clip_id == clip.id)
                .order_by(desc(AnalyticsSnapshot.captured_at))
                .limit(1)
            )
            video = await session.get(Video, clip.video_id)
            profile = await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == video.channel_id)) if video else None
            upload = await session.scalar(select(Upload).where(Upload.clip_id == clip.id).order_by(desc(Upload.created_at)).limit(1))
            outcome = self._outcome_score(clip, intel, latest)
            event = existing or LearningEvent(channel_id=video.channel_id if video else None, clip_id=clip.id)
            event.event_type = "clip_outcome"
            event.outcome_score = outcome
            event.metrics_json = {
                "views": latest.views if latest else 0,
                "likes": latest.likes if latest else 0,
                "comments": latest.comments if latest else 0,
                "ctr": latest.ctr if latest else None,
                "retention_avg": latest.retention_avg if latest else None,
                "upload_status": upload.status if upload else None,
                "uploaded_at": upload.uploaded_at.isoformat() if upload and upload.uploaded_at else None,
                "scheduled_for": upload.scheduled_for.isoformat() if upload and upload.scheduled_for else None,
            }
            metadata = clip.metadata_json or {}
            event.features_json = {
                "hook_text": clip.hook_text,
                "title": clip.title,
                "hashtags": clip.hashtags or [],
                "duration": round((clip.end_time or 0) - (clip.start_time or 0), 1),
                "viral_score": clip.viral_score,
                "retention_score": intel.retention_score if intel else metadata.get("retention_score"),
                "viral_probability": intel.viral_probability if intel else metadata.get("viral_probability"),
                "emotional_score": intel.emotional_score if intel else metadata.get("emotional_score"),
                "hook_type": intel.hook_type if intel else metadata.get("hook_type"),
                "hook_variants": metadata.get("hook_variants", []),
                "selected_hook": metadata.get("selected_hook"),
                "subtitle_style": metadata.get("subtitle_style", "tiktok punch captions"),
                "persona": (intel.metadata_json or {}).get("persona") if intel else None,
                "pacing_style": profile.pacing_style if profile else None,
                "upload_schedule": (profile.schedule_json or {}).get("times", []) if profile else [],
                "dead_zone": metadata.get("dead_zone"),
                "dead_zone_score": metadata.get("dead_zone_score"),
                "watchability_score": metadata.get("watchability_score"),
                "transcript_excerpt": metadata.get("transcript_excerpt"),
                "render_settings": metadata.get("render_settings", {}),
                "human_review": metadata.get("human_review"),
                "clip_status": clip.status,
            }
            if not existing:
                session.add(event)
            changed += 1
        await session.flush()
        return changed

    async def export_dataset(self, session: AsyncSession) -> dict[str, Any]:
        await self.sync_events(session)
        settings.training_data_dir.mkdir(parents=True, exist_ok=True)
        result = await session.execute(select(LearningEvent).order_by(desc(LearningEvent.learned_at)).limit(1000))
        events = list(result.scalars().all())
        paths = {
            "all": settings.training_data_dir / "clip_outcomes.jsonl",
            "successful": settings.training_data_dir / "successful_clips.jsonl",
            "failed": settings.training_data_dir / "failed_clips.jsonl",
            "hooks": settings.training_data_dir / "hook_performance.jsonl",
            "dead_zones": settings.training_data_dir / "dead_zone_patterns.jsonl",
        }
        files = {key: path.open("w", encoding="utf-8") for key, path in paths.items()}
        try:
            for event in events:
                row = self._row(event)
                files["all"].write(json.dumps(row, ensure_ascii=True) + "\n")
                files["successful" if event.outcome_score >= 70 else "failed"].write(json.dumps(row, ensure_ascii=True) + "\n")
                if row["features"].get("hook_type") or row["features"].get("hook_variants"):
                    files["hooks"].write(json.dumps(row, ensure_ascii=True) + "\n")
                if row["features"].get("dead_zone"):
                    files["dead_zones"].write(json.dumps(row, ensure_ascii=True) + "\n")
        finally:
            for handle in files.values():
                handle.close()
        return {
            "total_examples": len(events),
            "successful_examples": sum(1 for event in events if event.outcome_score >= 70),
            "failed_examples": sum(1 for event in events if event.outcome_score < 70),
            "paths": {key: str(path) for key, path in paths.items()},
        }

    async def payload(self, session: AsyncSession) -> dict[str, Any]:
        export = await self.export_dataset(session)
        result = await session.execute(select(LearningEvent).order_by(desc(LearningEvent.outcome_score)).limit(200))
        events = list(result.scalars().all())
        return {
            "dataset": export,
            "learnings": self._learnings(events),
            "best_patterns": self._patterns(events, successful=True),
            "avoid_patterns": self._patterns(events, successful=False),
            "viral_patterns": self.viral_patterns(events),
            "hook_rankings": self.hook_rankings(events),
            "recent_examples": [self._row(event) for event in events[:10]],
        }

    def _outcome_score(
        self,
        clip: Clip,
        intel: ClipIntelligence | None,
        analytics: AnalyticsSnapshot | None,
    ) -> float:
        predicted = intel.retention_score if intel else float(clip.viral_score or 0) * 100
        if not analytics:
            return round(predicted * 0.72, 1)
        engagement = min(100.0, analytics.likes * 4 + analytics.comments * 10 + analytics.views / 100)
        retention = analytics.retention_avg if analytics.retention_avg is not None else predicted
        return round((retention * 0.56) + (engagement * 0.28) + (predicted * 0.16), 1)

    def _learnings(self, events: list[LearningEvent]) -> list[dict[str, Any]]:
        if not events:
            return [
                {"label": "Hooks", "insight": "Curiosity gap hooks are the current default until more outcomes arrive.", "confidence": 61},
                {"label": "Pacing", "insight": "Shorts in the 24-44 second range receive the strongest local prior.", "confidence": 67},
                {"label": "Subtitles", "insight": "TikTok punch captions remain the default style for early retention.", "confidence": 64},
            ]
        avg = sum(event.outcome_score for event in events) / len(events)
        return [
            {"label": "Outcome baseline", "insight": f"Current learned clip outcome baseline is {avg:.1f}/100.", "confidence": min(95, round(avg))},
            {"label": "Hook direction", "insight": self._top_feature(events, "hook_type", "Curiosity gap hooks are leading."), "confidence": 78},
            {"label": "Duration", "insight": self._duration_learning(events), "confidence": 74},
        ]

    def _patterns(self, events: list[LearningEvent], *, successful: bool) -> list[dict[str, Any]]:
        filtered = [event for event in events if (event.outcome_score >= 70) == successful]
        if not filtered:
            label = "fast curiosity clips" if successful else "slow context-heavy openings"
            return [{"pattern": label, "score": 72 if successful else 41, "count": 0}]
        buckets: dict[str, list[float]] = {}
        for event in filtered:
            features = event.features_json or {}
            key = str(features.get("hook_type") or features.get("subtitle_style") or "general")
            buckets.setdefault(key, []).append(event.outcome_score)
        return [
            {"pattern": key, "score": round(sum(values) / len(values), 1), "count": len(values)}
            for key, values in sorted(buckets.items(), key=lambda item: sum(item[1]) / len(item[1]), reverse=successful)
        ][:6]

    def viral_patterns(self, events: list[LearningEvent]) -> dict[str, Any]:
        winners = [event for event in events if event.outcome_score >= 70]
        source = winners or events
        durations = [float((event.features_json or {}).get("duration") or 0) for event in source if (event.features_json or {}).get("duration")]
        upload_hours = []
        for event in source:
            uploaded_at = (event.metrics_json or {}).get("uploaded_at") or (event.metrics_json or {}).get("scheduled_for")
            if uploaded_at:
                try:
                    upload_hours.append(uploaded_at[11:16])
                except IndexError:
                    pass
        return {
            "best_duration": round(sum(durations) / len(durations), 1) if durations else 38,
            "best_upload_times": sorted(set(upload_hours))[:5] or ["12:30", "18:30", "21:00"],
            "best_subtitle_styles": self._feature_counts(source, "subtitle_style"),
            "best_emotional_triggers": self._feature_counts(source, "hook_type"),
            "dead_zone_threshold": self._dead_zone_threshold(source),
        }

    def hook_rankings(self, events: list[LearningEvent]) -> list[dict[str, Any]]:
        buckets: dict[str, list[float]] = {}
        for event in events:
            hook_type = (event.features_json or {}).get("hook_type")
            if hook_type:
                buckets.setdefault(str(hook_type), []).append(event.outcome_score)
        return [
            {"hook_type": key, "score": round(sum(values) / len(values), 1), "count": len(values)}
            for key, values in sorted(buckets.items(), key=lambda item: sum(item[1]) / len(item[1]), reverse=True)
        ]

    def _feature_counts(self, events: list[LearningEvent], key: str) -> list[dict[str, Any]]:
        counts: dict[str, list[float]] = {}
        for event in events:
            value = (event.features_json or {}).get(key)
            if value:
                counts.setdefault(str(value), []).append(event.outcome_score)
        return [
            {"label": label, "score": round(sum(values) / len(values), 1), "count": len(values)}
            for label, values in sorted(counts.items(), key=lambda item: len(item[1]), reverse=True)[:6]
        ]

    def _dead_zone_threshold(self, events: list[LearningEvent]) -> float:
        scores = [
            float((event.features_json or {}).get("dead_zone_score") or 0)
            for event in events
            if (event.features_json or {}).get("dead_zone_score") is not None
        ]
        if not scores:
            return 34.0
        return round(max(18.0, min(58.0, sum(scores) / len(scores) + 8)), 1)

    def _top_feature(self, events: list[LearningEvent], key: str, fallback: str) -> str:
        counts: dict[str, int] = {}
        for event in events:
            value = (event.features_json or {}).get(key)
            if value:
                counts[str(value)] = counts.get(str(value), 0) + 1
        if not counts:
            return fallback
        top = max(counts.items(), key=lambda item: item[1])
        return f"{top[0]} appears most often in high-signal examples."

    def _duration_learning(self, events: list[LearningEvent]) -> str:
        durations = [float((event.features_json or {}).get("duration") or 0) for event in events if (event.features_json or {}).get("duration")]
        if not durations:
            return "No duration outcomes yet; defaulting to 24-44 seconds."
        avg = sum(durations) / len(durations)
        return f"Average learned clip duration is {avg:.1f}s; use this as the next render prior."

    def _row(self, event: LearningEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "channel_id": event.channel_id,
            "clip_id": event.clip_id,
            "event_type": event.event_type,
            "outcome_score": event.outcome_score,
            "metrics": event.metrics_json or {},
            "features": event.features_json or {},
            "learned_at": event.learned_at.isoformat() if event.learned_at else None,
        }
