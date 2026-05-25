"""FastAPI JSON API routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.captions.subtitles import SubtitleEngine
from app.editor.service import ShortsEditor
from app.pipeline import ShortsPipeline
from app.schemas import (
    AddChannelRequest,
    AnalyticsSnapshotOut,
    AnalyticsSummaryOut,
    ChannelOut,
    ClipOut,
    ScheduleUploadRequest,
    TriggerResponse,
    UploadOut,
    VideoOut,
)
from app.scraper.service import YouTubeScraper
from app.uploader.service import YouTubeUploader
from database.models import AnalyticsSnapshot, Channel, Clip, Upload, Video
from database.session import get_session

router = APIRouter(prefix="/api", tags=["api"])

pipeline = ShortsPipeline()
scraper = YouTubeScraper()
uploader = YouTubeUploader()
analytics = AnalyticsService()
subtitle_engine = SubtitleEngine()
editor = ShortsEditor()


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""

    return {"status": "ok"}


@router.post("/channels", response_model=ChannelOut)
async def add_channel(
    payload: AddChannelRequest,
    session: AsyncSession = Depends(get_session),
) -> Channel:
    """Add a YouTube channel to the monitor list."""

    channel = await scraper.add_channel(session, url=payload.url, name=payload.name)
    await session.commit()
    await session.refresh(channel)
    return channel


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(session: AsyncSession = Depends(get_session)) -> list[Channel]:
    """List monitored channels."""

    result = await session.execute(select(Channel).order_by(desc(Channel.created_at)))
    return list(result.scalars().all())


@router.get("/videos", response_model=list[VideoOut])
async def list_videos(session: AsyncSession = Depends(get_session)) -> list[Video]:
    """List source videos."""

    result = await session.execute(select(Video).order_by(desc(Video.created_at)).limit(100))
    return list(result.scalars().all())


@router.post("/process", response_model=TriggerResponse)
async def trigger_processing(background_tasks: BackgroundTasks) -> TriggerResponse:
    """Trigger channel scanning and video processing."""

    background_tasks.add_task(pipeline.process_new_videos)
    return TriggerResponse(status="accepted", detail="Processing started in the background.")


@router.post("/videos/{video_id}/process", response_model=TriggerResponse)
async def process_video(video_id: int, background_tasks: BackgroundTasks) -> TriggerResponse:
    """Trigger processing for one video."""

    background_tasks.add_task(pipeline.process_video, video_id)
    return TriggerResponse(status="accepted", detail=f"Processing video {video_id}.")


@router.get("/clips", response_model=list[ClipOut])
async def list_clips(session: AsyncSession = Depends(get_session)) -> list[Clip]:
    """List generated clips."""

    result = await session.execute(select(Clip).order_by(desc(Clip.created_at)).limit(100))
    return list(result.scalars().all())


@router.post("/clips/{clip_id}/upload", response_model=UploadOut)
async def upload_clip(
    clip_id: int,
    payload: ScheduleUploadRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> Upload:
    """Queue and optionally upload a clip to YouTube."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    upload = await uploader.enqueue_upload(
        session,
        clip_id=clip_id,
        scheduled_for=payload.scheduled_for,
    )
    await session.commit()
    await session.refresh(upload)
    if payload.scheduled_for is None:
        background_tasks.add_task(uploader.upload_by_id, upload.id)
    return upload


@router.get("/uploads", response_model=list[UploadOut])
async def list_uploads(session: AsyncSession = Depends(get_session)) -> list[Upload]:
    """List upload queue records."""

    result = await session.execute(select(Upload).order_by(desc(Upload.created_at)).limit(100))
    return list(result.scalars().all())


@router.post("/clips/{clip_id}/subtitles/regenerate", response_model=ClipOut)
async def regenerate_subtitles(
    clip_id: int,
    session: AsyncSession = Depends(get_session),
) -> Clip:
    """Regenerate subtitles and rerender a clip."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    video = await session.get(Video, clip.video_id)
    if not video or not video.transcript_path:
        raise HTTPException(status_code=400, detail="Source transcript is missing")

    subtitle_path = subtitle_engine.generate_for_clip(
        transcript_path=video.transcript_path,
        clip_id=clip.id,
        start_time=clip.start_time,
        end_time=clip.end_time,
    )
    clip.subtitle_path = str(subtitle_path)
    await editor.render_clip(session, clip)
    await session.commit()
    await session.refresh(clip)
    return clip


@router.post("/analytics/refresh", response_model=TriggerResponse)
async def refresh_analytics(background_tasks: BackgroundTasks) -> TriggerResponse:
    """Refresh YouTube analytics in the background."""

    background_tasks.add_task(analytics.refresh_all)
    return TriggerResponse(status="accepted", detail="Analytics refresh started.")


@router.get("/analytics", response_model=AnalyticsSummaryOut)
async def fetch_analytics(session: AsyncSession = Depends(get_session)) -> AnalyticsSummaryOut:
    """Fetch analytics summary."""

    summary = await analytics.latest_summary(session)
    totals_result = await session.execute(
        select(
            func.coalesce(func.sum(AnalyticsSnapshot.views), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.likes), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.comments), 0),
        )
    )
    views, likes, comments = totals_result.one()
    return AnalyticsSummaryOut(
        snapshots=[AnalyticsSnapshotOut.model_validate(item) for item in summary["snapshots"]],
        top_clips=[ClipOut.model_validate(item) for item in summary["top_clips"]],
        totals={"views": views, "likes": likes, "comments": comments},
    )

