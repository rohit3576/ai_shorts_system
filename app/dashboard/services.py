"""Dashboard data services.

These helpers keep dashboard aggregation separate from the media pipeline. They
only read existing database state and expose UI-friendly dictionaries.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.learning import LearningEngine
from app.intelligence.profiles import ChannelProfileService
from app.intelligence.revenue import RevenueEstimator
from app.intelligence.trends import TrendEngine
from app.intelligence.upload import UploadIntelligenceService
from app.storage.lifecycle import StorageLifecycleService
from database.models import (
    AnalyticsSnapshot,
    Channel,
    ChannelProfile,
    Clip,
    ClipIntelligence,
    SourceFeed,
    Upload,
    UploadRecommendation,
    Video,
)

profile_service = ChannelProfileService()
trend_engine = TrendEngine()
upload_intelligence = UploadIntelligenceService()
revenue_estimator = RevenueEstimator()
learning_engine = LearningEngine()
storage_lifecycle = StorageLifecycleService()


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _file_url(path: str | None) -> str | None:
    if not path:
        return None
    source = Path(path)
    try:
        relative = source.resolve().relative_to(settings.resolve_path(settings.data_dir))
    except ValueError:
        return None
    return f"/media/{relative.as_posix()}"


def _clip_duration(clip: Clip) -> float:
    return max(0.0, float(clip.end_time or 0) - float(clip.start_time or 0))


def serialize_clip(
    clip: Clip,
    upload_status: str | None = None,
    intelligence: ClipIntelligence | None = None,
) -> dict[str, Any]:
    metadata = clip.metadata_json or {}
    retention_score = (
        intelligence.retention_score
        if intelligence
        else metadata.get("retention_score", round(float(clip.viral_score or 0) * 100, 1))
    )
    intelligence_metadata = intelligence.metadata_json if intelligence and intelligence.metadata_json else {}
    dead_zone_payload = metadata.get("dead_zone") or intelligence_metadata.get("dead_zone") or {}
    dead_zone_score = metadata.get("dead_zone_score", dead_zone_payload.get("dead_zone_score", 0))
    watchability_score = metadata.get("watchability_score", intelligence_metadata.get("watchability_score", retention_score))
    return {
        "id": clip.id,
        "video_id": clip.video_id,
        "title": clip.title or "Untitled Short",
        "description": clip.description,
        "hook_text": clip.hook_text or "Wait For This",
        "hashtags": clip.hashtags or [],
        "reason": clip.reason,
        "retention_score": round(float(retention_score or 0), 1),
        "retention_score_source": "PREDICTED",
        "viral_score": float(clip.viral_score or 0),
        "viral_score_source": "PREDICTED",
        "metric_sources": {
            "retention_score": "PREDICTED",
            "viral_score": "PREDICTED",
            "insights": "PREDICTED",
        },
        "duration": round(_clip_duration(clip), 1),
        "status": clip.status,
        "upload_status": upload_status or "not queued",
        "clip_url": _file_url(clip.clip_path),
        "subtitle_url": _file_url(clip.subtitle_path),
        "created_at": _iso(clip.created_at),
        "insights": {
            "emotional": round(float(intelligence.emotional_score if intelligence else metadata.get("emotional_score", round(float(clip.viral_score or 0) * 86)))),
            "curiosity": round(float(intelligence.curiosity_score if intelligence else metadata.get("curiosity_score", round(float(clip.viral_score or 0) * 92)))),
            "pacing": round(float(intelligence.pacing_score if intelligence else metadata.get("pacing_score", round(float(clip.viral_score or 0) * 88)))),
            "conflict": round(float(intelligence.conflict_score if intelligence else metadata.get("conflict_score", round(float(clip.viral_score or 0) * 72)))),
            "hook": round(float(intelligence.hook_strength_score if intelligence else metadata.get("hook_strength_score", retention_score))),
            "viral_probability": round(float((intelligence.viral_probability * 100) if intelligence else metadata.get("viral_probability", float(clip.viral_score or 0)) * 100), 1),
            "dead_zone": round(float(dead_zone_score or 0), 1),
            "watchability": round(float(watchability_score or retention_score), 1),
        },
        "hook_type": intelligence.hook_type if intelligence else metadata.get("hook_type"),
        "decision": intelligence.decision if intelligence else metadata.get("retention_decision", "review"),
        "human_review": metadata.get("human_review"),
        "hook_variants": metadata.get("hook_variants", []),
        "dead_zone": dead_zone_payload or None,
    }


def serialize_video(video: Video) -> dict[str, Any]:
    return {
        "id": video.id,
        "youtube_video_id": video.youtube_video_id,
        "title": video.title,
        "url": video.url,
        "status": video.status,
        "error": video.error,
        "published_at": _iso(video.published_at),
        "created_at": _iso(video.created_at),
    }


def serialize_upload(upload: Upload) -> dict[str, Any]:
    return {
        "id": upload.id,
        "clip_id": upload.clip_id,
        "youtube_video_id": upload.youtube_video_id,
        "status": upload.status,
        "privacy_status": upload.privacy_status,
        "scheduled_for": _iso(upload.scheduled_for),
        "uploaded_at": _iso(upload.uploaded_at),
        "error": upload.error,
        "created_at": _iso(upload.created_at),
    }


def serialize_channel(channel: Channel) -> dict[str, Any]:
    return {
        "id": channel.id,
        "name": channel.name or channel.channel_id or "Untitled channel",
        "channel_id": channel.channel_id,
        "url": channel.url,
        "rss_url": channel.rss_url,
        "active": channel.active,
        "last_checked_at": _iso(channel.last_checked_at),
        "created_at": _iso(channel.created_at),
    }


async def overview_payload(session: AsyncSession) -> dict[str, Any]:
    """Return the overview dashboard payload."""

    total_videos = await session.scalar(select(func.count(Video.id))) or 0
    total_clips = await session.scalar(select(func.count(Clip.id))) or 0
    queued_uploads = await session.scalar(select(func.count(Upload.id)).where(Upload.status == "queued")) or 0
    active_channels = await session.scalar(select(func.count(Channel.id)).where(Channel.active.is_(True))) or 0
    active_pipelines = await session.scalar(
        select(func.count(Video.id)).where(Video.status.in_(["processing", "downloaded", "audio_extracted", "transcribed"]))
    ) or 0
    avg_score = await session.scalar(select(func.avg(Clip.viral_score))) or 0
    latest_views = (
        select(func.max(AnalyticsSnapshot.views).label("views"))
        .where(AnalyticsSnapshot.metric_source == "REAL")
        .group_by(AnalyticsSnapshot.clip_id)
        .subquery()
    )
    total_views = await session.scalar(select(func.coalesce(func.sum(latest_views.c.views), 0))) or 0

    videos_result = await session.execute(select(Video).order_by(desc(Video.created_at)).limit(8))
    clips_result = await session.execute(select(Clip).order_by(desc(Clip.viral_score)).limit(8))
    uploads_result = await session.execute(select(Upload).order_by(desc(Upload.created_at)).limit(8))
    analytics_result = await session.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.metric_source == "REAL")
        .order_by(asc(AnalyticsSnapshot.captured_at))
        .limit(30)
    )

    clip_rows = list(clips_result.scalars().all())
    intelligence_result = await session.execute(
        select(ClipIntelligence).where(ClipIntelligence.clip_id.in_([clip.id for clip in clip_rows] or [-1]))
    )
    intelligence_by_clip = {item.clip_id: item for item in intelligence_result.scalars().all()}
    clips = [serialize_clip(item, intelligence=intelligence_by_clip.get(item.id)) for item in clip_rows]
    videos = [serialize_video(item) for item in videos_result.scalars().all()]
    uploads = [serialize_upload(item) for item in uploads_result.scalars().all()]
    analytics = list(analytics_result.scalars().all())

    activity = build_activity(videos, clips, uploads)
    timeline = [
        {
            "label": item.captured_at.strftime("%b %d") if item.captured_at else "Now",
            "views": item.views,
            "likes": item.likes,
            "comments": item.comments,
            "retention": item.retention_avg or 0,
            "ctr": item.ctr or 0,
        }
        for item in analytics
    ]

    return {
        "truth_mode": {
            "actual_metrics": "REAL",
            "predicted_metrics": "PREDICTED",
            "estimated_revenue": "ESTIMATED",
            "message": "No real analytics collected yet." if not analytics else None,
        },
        "stats": {
            "processed_videos": total_videos,
            "generated_shorts": total_clips,
            "queued_uploads": queued_uploads,
            "average_retention": round(float(avg_score) * 100, 1),
            "average_retention_source": "PREDICTED",
            "total_views": int(total_views),
            "total_views_source": "REAL",
            "active_pipelines": active_pipelines,
            "active_channels": active_channels,
        },
        "clips": clips,
        "videos": videos,
        "uploads": uploads,
        "activity": activity,
        "timeline": timeline,
        "pipeline": pipeline_state(videos),
        "insights": ai_insights(clips),
    }


async def clips_payload(
    session: AsyncSession,
    *,
    limit: int = 24,
    offset: int = 0,
    status: str | None = None,
    sort: str = "score",
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    query = select(Clip)
    count_query = select(func.count(Clip.id))
    if status:
        query = query.where(Clip.status == status)
        count_query = count_query.where(Clip.status == status)

    sort_map = {
        "newest": desc(Clip.created_at),
        "oldest": asc(Clip.created_at),
        "duration": desc(Clip.end_time - Clip.start_time),
        "score": desc(Clip.viral_score),
    }
    query = query.order_by(sort_map.get(sort, desc(Clip.viral_score))).limit(limit).offset(offset)
    result = await session.execute(query)
    clips = list(result.scalars().all())

    upload_result = await session.execute(select(Upload).where(Upload.clip_id.in_([clip.id for clip in clips] or [-1])))
    upload_by_clip = {item.clip_id: item.status for item in upload_result.scalars().all()}
    intelligence_result = await session.execute(
        select(ClipIntelligence).where(ClipIntelligence.clip_id.in_([clip.id for clip in clips] or [-1]))
    )
    intelligence_by_clip = {item.clip_id: item for item in intelligence_result.scalars().all()}

    return {
        "items": [serialize_clip(clip, upload_by_clip.get(clip.id), intelligence_by_clip.get(clip.id)) for clip in clips],
        "total": await session.scalar(count_query) or 0,
        "limit": limit,
        "offset": offset,
        "status": status,
        "sort": sort,
    }


async def analytics_payload(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.metric_source == "REAL")
        .order_by(asc(AnalyticsSnapshot.captured_at))
        .limit(60)
    )
    snapshots = list(result.scalars().all())
    timeline = [
        {
            "label": item.captured_at.strftime("%b %d") if item.captured_at else "Now",
            "views": item.views,
            "likes": item.likes,
            "comments": item.comments,
            "retention": item.retention_avg or 0,
            "ctr": item.ctr or 0,
        }
        for item in snapshots
    ]

    top_result = await session.execute(
        select(Clip)
        .join(AnalyticsSnapshot, AnalyticsSnapshot.clip_id == Clip.id)
        .where(AnalyticsSnapshot.metric_source == "REAL")
        .order_by(desc(AnalyticsSnapshot.views))
        .limit(8)
    )
    top_rows = list(top_result.scalars().all())
    intelligence_result = await session.execute(
        select(ClipIntelligence).where(ClipIntelligence.clip_id.in_([clip.id for clip in top_rows] or [-1]))
    )
    intelligence_by_clip = {item.clip_id: item for item in intelligence_result.scalars().all()}
    top_clips = [serialize_clip(item, intelligence=intelligence_by_clip.get(item.id)) for item in top_rows]
    return {
        "truth_mode": {
            "actual_metrics": "REAL",
            "predicted_scores": "PREDICTED",
            "message": "No real analytics collected yet." if not snapshots else None,
        },
        "timeline": timeline,
        "top_clips": top_clips,
        "best_hooks": [
            {"hook": item["hook_text"], "score": item["retention_score"], "metric_source": "PREDICTED"}
            for item in top_clips[:5]
        ],
        "styles": [],
    }


async def channels_payload(session: AsyncSession) -> dict[str, Any]:
    return await media_network_payload(session)


async def uploads_payload(session: AsyncSession, *, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    query = select(Upload)
    if status:
        query = query.where(Upload.status == status)
    result = await session.execute(query.order_by(desc(Upload.created_at)).limit(max(1, min(limit, 100))))
    return {"items": [serialize_upload(item) for item in result.scalars().all()]}


async def media_network_payload(session: AsyncSession) -> dict[str, Any]:
    """Return managed-channel profile and network summary data."""

    payload = await profile_service.payload(session)
    sources_result = await session.execute(select(SourceFeed).order_by(desc(SourceFeed.created_at)).limit(50))
    payload["sources"] = [
        {
            "id": item.id,
            "channel_id": item.channel_id,
            "source_type": item.source_type,
            "url": item.url,
            "label": item.label,
            "active": item.active,
            "last_checked_at": _iso(item.last_checked_at),
        }
        for item in sources_result.scalars().all()
    ]
    return payload


async def ai_insights_payload(session: AsyncSession) -> dict[str, Any]:
    """Return retention intelligence and AI reasoning aggregates."""

    result = await session.execute(select(ClipIntelligence).order_by(desc(ClipIntelligence.retention_score)).limit(80))
    rows = list(result.scalars().all())
    if not rows:
        return {
            "summary": {
                "avg_retention": 0,
                "avg_viral_probability": 0,
                "auto_schedule_ready": 0,
                "review_queue": 0,
                "metric_source": "PREDICTED",
                "message": "No clip intelligence yet.",
            },
            "signals": [],
            "top_reasons": [],
            "clips": [],
        }
    avg = lambda attr: round(sum(float(getattr(item, attr) or 0) for item in rows) / len(rows), 1)
    reasons: dict[str, int] = {}
    for item in rows:
        for reason in item.reasons_json or []:
            reasons[reason] = reasons.get(reason, 0) + 1
    clip_result = await session.execute(select(Clip).where(Clip.id.in_([item.clip_id for item in rows[:10]])))
    clips_by_id = {item.id: item for item in clip_result.scalars().all()}
    return {
        "summary": {
            "avg_retention": avg("retention_score"),
            "avg_viral_probability": round(avg("viral_probability") * 100, 1),
            "auto_schedule_ready": sum(1 for item in rows if item.decision == "auto_schedule"),
            "review_queue": sum(1 for item in rows if item.decision == "review"),
        },
        "signals": [
            {"label": "Curiosity", "value": avg("curiosity_score"), "tone": "cyan"},
            {"label": "Emotional lift", "value": avg("emotional_score"), "tone": "violet"},
            {"label": "Pacing", "value": avg("pacing_score"), "tone": "emerald"},
            {"label": "Hook strength", "value": avg("hook_strength_score"), "tone": "amber"},
        ],
        "top_reasons": [
            {"label": label, "value": count}
            for label, count in sorted(reasons.items(), key=lambda item: item[1], reverse=True)[:8]
        ],
        "clips": [
            serialize_clip(clips_by_id[item.clip_id], intelligence=item)
            for item in rows[:10]
            if item.clip_id in clips_by_id
        ],
    }


async def upload_intelligence_payload(session: AsyncSession) -> dict[str, Any]:
    """Return recommended upload times, packaging, and auto-upload candidates."""

    return await upload_intelligence.payload(session)


async def revenue_payload(session: AsyncSession) -> dict[str, Any]:
    """Return estimated Shorts revenue and forecast."""

    return await revenue_estimator.payload(session)


async def trend_center_payload(session: AsyncSession) -> dict[str, Any]:
    """Return local topic and hook trend signals."""

    return await trend_engine.payload(session)


async def learning_payload(session: AsyncSession) -> dict[str, Any]:
    """Return learned patterns and exported training dataset metadata."""

    return await learning_engine.payload(session)


async def logs_payload(session: AsyncSession, *, limit: int = 80, level: str | None = None) -> dict[str, Any]:
    overview = await overview_payload(session)
    rows = []
    for item in overview["activity"]:
        rows.append(
            {
                "timestamp": item["time"],
                "level": "error" if "failed" in item["status"].lower() else "info",
                "source": item["type"],
                "message": item["message"],
            }
        )
    if level:
        rows = [row for row in rows if row["level"] == level]
    return {"items": rows[: max(1, min(limit, 200))]}


async def storage_payload() -> dict[str, Any]:
    return await storage_lifecycle.payload()


def settings_payload() -> dict[str, Any]:
    return {
        "ollama_model": settings.ollama_model,
        "ollama_base_url": settings.ollama_base_url,
        "ffmpeg_quality": {"crf": settings.crf, "preset": settings.video_preset},
        "subtitle_style": "TikTok punch captions",
        "upload_frequency": f"Every {settings.scheduler_interval_minutes} minutes",
        "render_quality": f"{settings.shorts_width}x{settings.shorts_height}",
        "hook_intensity": round(settings.viral_score_threshold * 100),
        "youtube_upload_enabled": settings.youtube_upload_enabled,
    }


def pipeline_state(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_counts: dict[str, int] = {}
    for video in videos:
        status_counts[video["status"]] = status_counts.get(video["status"], 0) + 1
    stages = [
        ("Download", "downloaded"),
        ("Transcription", "transcribed"),
        ("Clip Detection", "completed"),
        ("Subtitle Generation", "generated"),
        ("Rendering", "generated"),
        ("Upload Queue", "queued"),
    ]
    return [
        {
            "name": name,
            "status": "active" if status_counts.get(status) else "ready",
            "count": status_counts.get(status, 0),
            "timing": "local",
            "error": None,
        }
        for name, status in stages
    ]


def build_activity(
    videos: list[dict[str, Any]],
    clips: list[dict[str, Any]],
    uploads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    activity = []
    for item in videos[:5]:
        activity.append(
            {
                "type": "video",
                "status": item["status"],
                "message": f"Ingested {item['title']}",
                "time": item["created_at"],
            }
        )
    for item in clips[:5]:
        activity.append(
            {
                "type": "clip",
                "status": item["status"],
                "message": f"Generated {item['hook_text']} ({item['retention_score']}%)",
                "time": item["created_at"],
            }
        )
    for item in uploads[:5]:
        activity.append(
            {
                "type": "upload",
                "status": item["status"],
                "message": f"Upload #{item['id']} is {item['status']}",
                "time": item["created_at"],
            }
        )
    return sorted(activity, key=lambda item: item["time"] or "", reverse=True)[:12]


def ai_insights(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not clips:
        return []
    avg = lambda key: round(sum(item["insights"][key] for item in clips) / len(clips))
    return [
        {"label": "Curiosity", "value": avg("curiosity"), "tone": "cyan"},
        {"label": "Emotional lift", "value": avg("emotional"), "tone": "violet"},
        {"label": "Pacing", "value": avg("pacing"), "tone": "emerald"},
        {"label": "Conflict", "value": avg("conflict"), "tone": "amber"},
    ]
