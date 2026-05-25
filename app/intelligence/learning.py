"""Self-improving local learning dataset builder."""

from __future__ import annotations

import json
import csv
import math
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import AnalyticsSnapshot, CalibrationReport, ChannelProfile, Clip, ClipIntelligence, LearningEvent, Upload, Video


class LearningEngine:
    """Convert clip outcomes into reusable local training examples."""

    async def sync_events(self, session: AsyncSession) -> int:
        result = await session.execute(select(Clip).order_by(desc(Clip.created_at)).limit(500))
        changed = 0
        for clip in result.scalars().all():
            existing = await session.scalar(
                select(LearningEvent).where(
                    LearningEvent.clip_id == clip.id,
                    LearningEvent.event_type == "clip_outcome",
                )
            )
            intel = await session.scalar(select(ClipIntelligence).where(ClipIntelligence.clip_id == clip.id))
            latest = await session.scalar(
                select(AnalyticsSnapshot)
                .where(
                    AnalyticsSnapshot.clip_id == clip.id,
                    AnalyticsSnapshot.metric_source == "REAL",
                )
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
                "metric_source": "REAL" if latest else "PREDICTED",
                "has_real_analytics": bool(latest),
                "views": latest.views if latest else 0,
                "likes": latest.likes if latest else 0,
                "comments": latest.comments if latest else 0,
                "ctr": latest.ctr if latest else None,
                "retention_avg": latest.retention_avg if latest else None,
                "average_view_duration_seconds": latest.average_view_duration_seconds if latest else None,
                "watch_time_minutes": latest.watch_time_minutes if latest else None,
                "subscriber_gain": latest.subscriber_gain if latest else None,
                "snapshot_window_hours": latest.snapshot_window_hours if latest else None,
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
            "summary_csv": settings.training_data_dir / "clip_outcomes.csv",
            "calibration_json": settings.training_data_dir / "calibration_report.json",
            "calibration_csv": settings.training_data_dir / "calibration_report.csv",
        }
        jsonl_paths = {key: path for key, path in paths.items() if path.suffix == ".jsonl"}
        files = {key: path.open("w", encoding="utf-8") for key, path in jsonl_paths.items()}
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
        self._write_summary_csv(paths["summary_csv"], events)
        calibration = await self.generate_calibration_report(session)
        paths["calibration_json"].write_text(json.dumps(calibration, indent=2, ensure_ascii=True), encoding="utf-8")
        self._write_calibration_csv(paths["calibration_csv"], calibration)
        return {
            "total_examples": len(events),
            "successful_examples": sum(1 for event in events if event.outcome_score >= 70),
            "failed_examples": sum(1 for event in events if event.outcome_score < 70),
            "real_analytics_examples": sum(1 for event in events if (event.metrics_json or {}).get("has_real_analytics")),
            "calibration": calibration,
            "paths": {key: str(path) for key, path in paths.items()},
        }

    async def payload(self, session: AsyncSession) -> dict[str, Any]:
        export = await self.export_dataset(session)
        result = await session.execute(select(LearningEvent).order_by(desc(LearningEvent.outcome_score)).limit(200))
        events = list(result.scalars().all())
        real_events = [event for event in events if (event.metrics_json or {}).get("has_real_analytics")]
        return {
            "dataset": export,
            "calibration": export["calibration"],
            "learnings": self._learnings(real_events),
            "best_patterns": self._patterns(real_events, successful=True),
            "avoid_patterns": self._patterns(events, successful=False),
            "viral_patterns": self.viral_patterns(real_events),
            "hook_rankings": self.hook_rankings(real_events),
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
            review = (clip.metadata_json or {}).get("human_review") or {}
            if review.get("action") == "rejected":
                return 0.0
            if review.get("action") == "approved":
                return 55.0
            return 0.0
        engagement = min(100.0, analytics.likes * 4 + analytics.comments * 10 + analytics.views / 100)
        retention = analytics.retention_avg if analytics.retention_avg is not None else predicted
        return round((retention * 0.56) + (engagement * 0.28) + (predicted * 0.16), 1)

    def _learnings(self, events: list[LearningEvent]) -> list[dict[str, Any]]:
        if not events:
            return [
                {"label": "No real analytics yet", "insight": "No real upload outcomes have been collected yet.", "confidence": 0},
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
            return [{"pattern": label, "score": 0, "count": 0}]
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
            "best_duration": round(sum(durations) / len(durations), 1) if durations else 0,
            "best_upload_times": sorted(set(upload_hours))[:5],
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
            return 0.0
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

    async def generate_calibration_report(self, session: AsyncSession) -> dict[str, Any]:
        """Compare predicted retention/virality/hook strength with real outcomes."""

        result = await session.execute(select(ClipIntelligence).order_by(desc(ClipIntelligence.updated_at)).limit(1000))
        rows: list[dict[str, Any]] = []
        retention_errors: list[float] = []
        virality_errors: list[float] = []
        hook_errors: list[float] = []
        for intel in result.scalars().all():
            snapshot = await session.scalar(
                select(AnalyticsSnapshot)
                .where(
                    AnalyticsSnapshot.clip_id == intel.clip_id,
                    AnalyticsSnapshot.metric_source == "REAL",
                )
                .order_by(desc(AnalyticsSnapshot.captured_at))
                .limit(1)
            )
            if not snapshot or snapshot.retention_avg is None:
                continue
            actual_retention = float(snapshot.retention_avg)
            actual_performance = self._actual_performance_score(snapshot)
            predicted_retention = float(intel.retention_score or 0)
            predicted_virality = float(intel.viral_probability or 0) * 100
            predicted_hook = float(intel.hook_strength_score or 0)
            hook_actual = min(100.0, (actual_retention * 0.72) + (actual_performance * 0.28))
            retention_error = abs(predicted_retention - actual_retention)
            virality_error = abs(predicted_virality - actual_performance)
            hook_error = abs(predicted_hook - hook_actual)
            retention_errors.append(retention_error)
            virality_errors.append(virality_error)
            hook_errors.append(hook_error)
            rows.append(
                {
                    "clip_id": intel.clip_id,
                    "predicted_retention": round(predicted_retention, 2),
                    "actual_retention": round(actual_retention, 2),
                    "predicted_virality": round(predicted_virality, 2),
                    "actual_performance_score": round(actual_performance, 2),
                    "predicted_hook_strength": round(predicted_hook, 2),
                    "actual_hook_proxy": round(hook_actual, 2),
                    "retention_error": round(retention_error, 2),
                    "virality_error": round(virality_error, 2),
                    "hook_error": round(hook_error, 2),
                    "metric_source": "REAL",
                    "actual_performance_score_source": "ESTIMATED_FROM_REAL_ANALYTICS",
                }
            )

        sample_count = len(rows)
        retention_mae = _mean(retention_errors)
        virality_mae = _mean(virality_errors)
        hook_mae = _mean(hook_errors)
        ci_low, ci_high = _confidence_interval(retention_errors)
        report = {
            "sample_count": sample_count,
            "retention_mae": retention_mae,
            "virality_mae": virality_mae,
            "hook_mae": hook_mae,
            "confidence_interval_95": {"low": ci_low, "high": ci_high},
            "status": "No real analytics collected yet." if sample_count == 0 else "calibrating",
            "rows": rows,
        }
        row = CalibrationReport(
            sample_count=sample_count,
            retention_mae=retention_mae,
            virality_mae=virality_mae,
            hook_mae=hook_mae,
            confidence_low=ci_low,
            confidence_high=ci_high,
            report_json=report,
        )
        session.add(row)
        await session.flush()
        return report

    def _actual_performance_score(self, snapshot: AnalyticsSnapshot) -> float:
        retention = float(snapshot.retention_avg or 0)
        engagement = min(100.0, (snapshot.likes * 4) + (snapshot.comments * 10) + (snapshot.views / 100))
        watch_time = min(100.0, float(snapshot.watch_time_minutes or 0) / 10)
        subscribers = min(100.0, float(snapshot.subscriber_gain or 0) * 20)
        return round((retention * 0.45) + (engagement * 0.35) + (watch_time * 0.12) + (subscribers * 0.08), 2)

    def _write_summary_csv(self, path, events: list[LearningEvent]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "id",
                    "clip_id",
                    "event_type",
                    "outcome_score",
                    "metric_source",
                    "has_real_analytics",
                    "views",
                    "retention_avg",
                    "ctr",
                    "hook_type",
                    "duration",
                    "labels",
                ],
            )
            writer.writeheader()
            for event in events:
                metrics = event.metrics_json or {}
                features = event.features_json or {}
                review = features.get("human_review") or {}
                writer.writerow(
                    {
                        "id": event.id,
                        "clip_id": event.clip_id,
                        "event_type": event.event_type,
                        "outcome_score": event.outcome_score,
                        "metric_source": metrics.get("metric_source"),
                        "has_real_analytics": metrics.get("has_real_analytics"),
                        "views": metrics.get("views"),
                        "retention_avg": metrics.get("retention_avg"),
                        "ctr": metrics.get("ctr"),
                        "hook_type": features.get("hook_type"),
                        "duration": features.get("duration"),
                        "labels": "|".join(review.get("labels", [])) if isinstance(review, dict) else "",
                    }
                )

    def _write_calibration_csv(self, path, calibration: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "clip_id",
                    "predicted_retention",
                    "actual_retention",
                    "predicted_virality",
                    "actual_performance_score",
                    "predicted_hook_strength",
                    "actual_hook_proxy",
                    "retention_error",
                    "virality_error",
                    "hook_error",
                    "metric_source",
                    "actual_performance_score_source",
                ],
            )
            writer.writeheader()
            writer.writerows(calibration.get("rows", []))

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


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _confidence_interval(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return round(mean, 3), round(mean, 3)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = 1.96 * math.sqrt(variance) / math.sqrt(len(values))
    return round(max(0.0, mean - margin), 3), round(mean + margin, 3)
