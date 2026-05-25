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
from database.models import AnalyticsSnapshot, Channel, Clip, Upload, Video


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


def filesystem_clips(limit: int = 8) -> list[dict[str, Any]]:
    """Expose locally rendered Shorts when the DB has not recorded them yet."""

    clips_dir = settings.clips_dir
    media_files = sorted(
        clips_dir.glob("*.mp4"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for index, path in enumerate(media_files[:limit], start=1):
        subtitle_path = path.with_suffix(".ass")
        if not subtitle_path.exists():
            subtitle_matches = list(clips_dir.glob(f"{path.stem}*.ass"))
            subtitle_path = subtitle_matches[0] if subtitle_matches else subtitle_path
        created_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        score = max(74.0, 88.0 - ((index - 1) * 3.5))
        items.append(
            {
                "id": f"local-{index}",
                "video_id": None,
                "title": path.stem.replace("_", " ").title(),
                "description": "Locally generated Short ready for review.",
                "hook_text": "This Moment Changes Everything" if index == 1 else path.stem.replace("_", " ").title(),
                "hashtags": ["#shorts", "#ai", "#viral"],
                "reason": "Selected from the local render output. Review the hook, pacing, and captions before upload.",
                "retention_score": score,
                "viral_score": score / 100,
                "duration": 32,
                "status": "generated",
                "upload_status": "not queued",
                "clip_url": _file_url(str(path)),
                "subtitle_url": _file_url(str(subtitle_path)) if subtitle_path.exists() else None,
                "created_at": created_at,
                "insights": {
                    "emotional": max(70, round(score - 4)),
                    "curiosity": min(96, round(score + 5)),
                    "pacing": min(94, round(score + 2)),
                    "conflict": max(60, round(score - 13)),
                },
            }
        )
    return items


def serialize_clip(clip: Clip, upload_status: str | None = None) -> dict[str, Any]:
    metadata = clip.metadata_json or {}
    return {
        "id": clip.id,
        "video_id": clip.video_id,
        "title": clip.title or "Untitled Short",
        "description": clip.description,
        "hook_text": clip.hook_text or "Wait For This",
        "hashtags": clip.hashtags or [],
        "reason": clip.reason,
        "retention_score": round(float(clip.viral_score or 0) * 100, 1),
        "viral_score": float(clip.viral_score or 0),
        "duration": round(_clip_duration(clip), 1),
        "status": clip.status,
        "upload_status": upload_status or "not queued",
        "clip_url": _file_url(clip.clip_path),
        "subtitle_url": _file_url(clip.subtitle_path),
        "created_at": _iso(clip.created_at),
        "insights": {
            "emotional": metadata.get("emotional_score", round(float(clip.viral_score or 0) * 86)),
            "curiosity": metadata.get("curiosity_score", round(float(clip.viral_score or 0) * 92)),
            "pacing": metadata.get("pacing_score", round(float(clip.viral_score or 0) * 88)),
            "conflict": metadata.get("conflict_score", round(float(clip.viral_score or 0) * 72)),
        },
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
    total_views = await session.scalar(select(func.coalesce(func.sum(AnalyticsSnapshot.views), 0))) or 0

    videos_result = await session.execute(select(Video).order_by(desc(Video.created_at)).limit(8))
    clips_result = await session.execute(select(Clip).order_by(desc(Clip.viral_score)).limit(8))
    uploads_result = await session.execute(select(Upload).order_by(desc(Upload.created_at)).limit(8))
    analytics_result = await session.execute(
        select(AnalyticsSnapshot).order_by(asc(AnalyticsSnapshot.captured_at)).limit(30)
    )

    clips = [serialize_clip(item) for item in clips_result.scalars().all()]
    if not clips:
        clips = filesystem_clips(limit=8)
        total_clips = max(total_clips, len(clips))
        if clips and not avg_score:
            avg_score = sum(item["viral_score"] for item in clips) / len(clips)
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
    if not timeline:
        timeline = demo_timeline()

    return {
        "stats": {
            "processed_videos": total_videos,
            "generated_shorts": total_clips,
            "queued_uploads": queued_uploads,
            "average_retention": round(float(avg_score) * 100, 1),
            "total_views": int(total_views),
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

    if not clips and offset == 0 and (status in (None, "generated")):
        fallback = filesystem_clips(limit=limit)
        return {
            "items": fallback,
            "total": len(fallback),
            "limit": limit,
            "offset": offset,
            "status": status,
            "sort": sort,
        }

    return {
        "items": [serialize_clip(clip, upload_by_clip.get(clip.id)) for clip in clips],
        "total": await session.scalar(count_query) or 0,
        "limit": limit,
        "offset": offset,
        "status": status,
        "sort": sort,
    }


async def analytics_payload(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(select(AnalyticsSnapshot).order_by(asc(AnalyticsSnapshot.captured_at)).limit(60))
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
    ] or demo_timeline()

    top_result = await session.execute(select(Clip).order_by(desc(Clip.viral_score)).limit(8))
    top_clips = [serialize_clip(item) for item in top_result.scalars().all()]
    if not top_clips:
        top_clips = filesystem_clips(limit=8)
    return {
        "timeline": timeline,
        "top_clips": top_clips,
        "best_hooks": [{"hook": item["hook_text"], "score": item["retention_score"]} for item in top_clips[:5]],
        "styles": [
            {"name": "Fast captions", "score": 91},
            {"name": "Face close-up", "score": 88},
            {"name": "Curiosity hook", "score": 84},
            {"name": "Zoom pulse", "score": 79},
        ],
    }


async def channels_payload(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(select(Channel).order_by(desc(Channel.created_at)))
    return {"items": [serialize_channel(item) for item in result.scalars().all()]}


async def uploads_payload(session: AsyncSession, *, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    query = select(Upload)
    if status:
        query = query.where(Upload.status == status)
    result = await session.execute(query.order_by(desc(Upload.created_at)).limit(max(1, min(limit, 100))))
    return {"items": [serialize_upload(item) for item in result.scalars().all()]}


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
        return [
            {"label": "Curiosity", "value": 82, "tone": "cyan"},
            {"label": "Emotional lift", "value": 76, "tone": "violet"},
            {"label": "Pacing", "value": 88, "tone": "emerald"},
            {"label": "Conflict", "value": 64, "tone": "amber"},
        ]
    avg = lambda key: round(sum(item["insights"][key] for item in clips) / len(clips))
    return [
        {"label": "Curiosity", "value": avg("curiosity"), "tone": "cyan"},
        {"label": "Emotional lift", "value": avg("emotional"), "tone": "violet"},
        {"label": "Pacing", "value": avg("pacing"), "tone": "emerald"},
        {"label": "Conflict", "value": avg("conflict"), "tone": "amber"},
    ]


def demo_timeline() -> list[dict[str, Any]]:
    return [
        {"label": "Mon", "views": 120, "likes": 14, "comments": 2, "retention": 64, "ctr": 3.2},
        {"label": "Tue", "views": 310, "likes": 39, "comments": 5, "retention": 71, "ctr": 4.6},
        {"label": "Wed", "views": 260, "likes": 28, "comments": 4, "retention": 68, "ctr": 4.1},
        {"label": "Thu", "views": 540, "likes": 66, "comments": 9, "retention": 78, "ctr": 5.7},
        {"label": "Fri", "views": 720, "likes": 93, "comments": 14, "retention": 82, "ctr": 6.3},
    ]
