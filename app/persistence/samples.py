"""Canonical records for generated Shorts and learning samples."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AnalyticsSnapshot, Clip, ClipIntelligence, LearningEvent, MediaAsset, Video


async def ensure_generated_clip_records(
    session: AsyncSession,
    clip: Clip,
    *,
    event_type: str = "generated_clip",
    source: str = "pipeline",
) -> None:
    """Ensure every rendered/imported Short is trainable and measurable.

    The initial analytics row is explicitly marked PREDICTED. It is a placeholder
    for calibration and UI truth mode, not a real YouTube performance snapshot.
    """

    video = await session.get(Video, clip.video_id)
    metadata = clip.metadata_json or {}
    intelligence = await session.scalar(select(ClipIntelligence).where(ClipIntelligence.clip_id == clip.id))
    if not intelligence:
        intelligence = ClipIntelligence(
            clip_id=clip.id,
            retention_score=float(metadata.get("retention_score") or float(clip.viral_score or 0) * 100),
            viral_probability=float(metadata.get("viral_probability") or float(clip.viral_score or 0)),
            curiosity_score=float(metadata.get("curiosity_score") or 0),
            emotional_score=float(metadata.get("emotional_score") or 0),
            pacing_score=float(metadata.get("pacing_score") or 0),
            hook_strength_score=float(metadata.get("hook_strength_score") or 0),
            quality_score=float(metadata.get("watchability_score") or metadata.get("retention_score") or 0),
            decision="review",
            metadata_json={"source": source, "note": "Backfilled because no scorer record existed."},
        )
        session.add(intelligence)
        await session.flush()

    existing_event = await session.scalar(
        select(LearningEvent).where(
            LearningEvent.clip_id == clip.id,
            LearningEvent.event_type == event_type,
        )
    )
    if not existing_event:
        session.add(
            LearningEvent(
                channel_id=video.channel_id if video else None,
                clip_id=clip.id,
                event_type=event_type,
                outcome_score=0.0,
                metrics_json={
                    "metric_source": "PREDICTED",
                    "status": "awaiting_real_upload_outcome",
                },
                features_json=_clip_features(clip, intelligence, metadata),
            )
        )

    existing_predicted_snapshot = await session.scalar(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.clip_id == clip.id,
            AnalyticsSnapshot.metric_source == "PREDICTED",
        )
    )
    if not existing_predicted_snapshot:
        session.add(
            AnalyticsSnapshot(
                clip_id=clip.id,
                views=0,
                likes=0,
                comments=0,
                ctr=None,
                retention_avg=float(intelligence.retention_score or 0),
                average_view_percentage=float(intelligence.retention_score or 0),
                metric_source="PREDICTED",
                capture_status="awaiting_upload",
                unavailable_metrics=["real_views", "real_retention", "real_ctr", "real_revenue"],
                raw_json={
                    "source": source,
                    "prediction_only": True,
                    "retention_score": intelligence.retention_score,
                    "viral_probability": intelligence.viral_probability,
                },
            )
        )

    await upsert_clip_media_assets(session, clip)
    await session.flush()


async def upsert_clip_media_assets(session: AsyncSession, clip: Clip) -> None:
    """Track rendered clip and subtitle files for lifecycle cleanup."""

    for asset_type, path_value in [("rendered_clip", clip.clip_path), ("subtitle", clip.subtitle_path)]:
        if not path_value:
            continue
        await upsert_media_asset(
            session,
            asset_type=asset_type,
            file_path=path_value,
            owner_table="clips",
            owner_id=clip.id,
        )


async def upsert_video_media_assets(session: AsyncSession, video: Video) -> None:
    """Track source, audio, transcript, and thumbnail files for cleanup."""

    for asset_type, path_value in [
        ("source_video", video.downloaded_path),
        ("audio", video.audio_path),
        ("transcript", video.transcript_path),
        ("thumbnail", video.thumbnail_path),
    ]:
        if not path_value:
            continue
        await upsert_media_asset(
            session,
            asset_type=asset_type,
            file_path=path_value,
            owner_table="videos",
            owner_id=video.id,
        )


async def upsert_media_asset(
    session: AsyncSession,
    *,
    asset_type: str,
    file_path: str,
    owner_table: str | None = None,
    owner_id: int | None = None,
) -> MediaAsset:
    """Insert or update a tracked media asset row."""

    path = Path(file_path)
    resolved = str(path.resolve()) if path.exists() else str(path)
    existing = await session.scalar(select(MediaAsset).where(MediaAsset.file_path == resolved))
    asset = existing or MediaAsset(file_path=resolved, asset_type=asset_type)
    asset.asset_type = asset_type
    asset.owner_table = owner_table
    asset.owner_id = owner_id
    asset.size_bytes = path.stat().st_size if path.exists() else 0
    asset.retention_state = "active"
    asset.last_seen_at = datetime.now(timezone.utc)
    if not existing:
        session.add(asset)
    await session.flush()
    return asset


def _clip_features(clip: Clip, intelligence: ClipIntelligence, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "hook_text": clip.hook_text,
        "title": clip.title,
        "hashtags": clip.hashtags or [],
        "duration": round((clip.end_time or 0) - (clip.start_time or 0), 1),
        "viral_score": clip.viral_score,
        "predicted_retention": intelligence.retention_score,
        "predicted_virality": intelligence.viral_probability,
        "predicted_hook_strength": intelligence.hook_strength_score,
        "hook_type": intelligence.hook_type,
        "subtitle_style": metadata.get("subtitle_style", "tiktok punch captions"),
        "pacing_score": intelligence.pacing_score,
        "emotional_score": intelligence.emotional_score,
        "dead_zone": metadata.get("dead_zone"),
        "dead_zone_score": metadata.get("dead_zone_score"),
        "review_labels": (metadata.get("human_review") or {}).get("labels", []),
        "transcript_snippet": metadata.get("transcript_excerpt"),
    }
