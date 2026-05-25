"""FastAPI JSON API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.captions.subtitles import SubtitleEngine
from app.editor.service import ShortsEditor
from app.intelligence.deadzone import DeadZoneDetector
from app.intelligence.hooks import HookTemplateEngine
from app.intelligence.learning import LearningEngine
from app.intelligence.negative_samples import NegativeSampleService
from app.intelligence.profiles import ChannelProfileService
from app.intelligence.quality_gate import QualityGateService, UploadGateError
from app.intelligence.revenue import RevenueEstimator
from app.intelligence.sources import SourceIngestionService
from app.intelligence.trends import TrendEngine
from app.intelligence.upload import UploadIntelligenceService
from app.jobs.service import JobService
from app.persistence.samples import ensure_generated_clip_records
from app.storage.lifecycle import StorageLifecycleService
from app.pipeline import ShortsPipeline
from app.schemas import (
    AddChannelRequest,
    AddSourceRequest,
    AnalyticsSnapshotOut,
    AnalyticsSummaryOut,
    ChannelOut,
    ClipOut,
    RegenerateHookRequest,
    ReviewClipRequest,
    RightsReviewRequest,
    ScheduleUploadRequest,
    TriggerResponse,
    UploadOut,
    VideoOut,
)
from app.scraper.service import YouTubeScraper
from app.uploader.service import YouTubeUploader
from database.models import AnalyticsSnapshot, Channel, Clip, ProcessingJob, ReviewDecision, Upload, Video
from database.session import get_session

router = APIRouter(prefix="/api", tags=["api"])

pipeline = ShortsPipeline()
scraper = YouTubeScraper()
uploader = YouTubeUploader()
analytics = AnalyticsService()
subtitle_engine = SubtitleEngine()
editor = ShortsEditor()
dead_zone_detector = DeadZoneDetector()
hook_engine = HookTemplateEngine()
profile_service = ChannelProfileService()
source_service = SourceIngestionService()
trend_engine = TrendEngine()
upload_intelligence = UploadIntelligenceService()
revenue_estimator = RevenueEstimator()
learning_engine = LearningEngine()
job_service = JobService()
quality_gate = QualityGateService()
negative_samples = NegativeSampleService()
storage_lifecycle = StorageLifecycleService()


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
    await profile_service.ensure_profile(
        session,
        channel,
        niche_type=payload.niche_type,
        upload_style=payload.upload_style,
        hook_style=payload.hook_style,
        target_audience=payload.target_audience,
    )
    await session.commit()
    await session.refresh(channel)
    return channel


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(session: AsyncSession = Depends(get_session)) -> list[Channel]:
    """List monitored channels."""

    result = await session.execute(select(Channel).order_by(desc(Channel.created_at)))
    return list(result.scalars().all())


@router.post("/sources", response_model=TriggerResponse)
async def add_source(
    payload: AddSourceRequest,
    session: AsyncSession = Depends(get_session),
) -> TriggerResponse:
    """Add a monitored channel, playlist, creator, or source URL."""

    source = await source_service.add_source(
        session,
        url=payload.url,
        source_type=payload.source_type,
        label=payload.label,
        channel_id=payload.channel_id,
    )
    await session.commit()
    return TriggerResponse(status="created", detail=f"Source {source.id} added.")


@router.post("/sources/scan", response_model=TriggerResponse)
async def scan_sources(session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Scan source feeds and queue newly discovered videos."""

    discovered = await source_service.scan_sources(session)
    await session.commit()
    return TriggerResponse(status="completed", detail=f"Discovered {len(discovered)} source videos.")


@router.get("/videos", response_model=list[VideoOut])
async def list_videos(session: AsyncSession = Depends(get_session)) -> list[Video]:
    """List source videos."""

    result = await session.execute(select(Video).order_by(desc(Video.created_at)).limit(100))
    return list(result.scalars().all())


@router.post("/process", response_model=TriggerResponse)
async def trigger_processing(session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Queue channel scanning and video processing as a durable job."""

    job = await job_service.enqueue(session, job_type="process_new_videos", priority=50)
    await session.commit()
    return TriggerResponse(status="accepted", detail=f"Queued durable processing job {job.id}.")


@router.post("/videos/{video_id}/process", response_model=TriggerResponse)
async def process_video(video_id: int, session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Queue processing for one video as a durable job."""

    if not await session.get(Video, video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    job = await job_service.enqueue(
        session,
        job_type="process_video",
        payload={"video_id": video_id},
        priority=40,
    )
    await session.commit()
    return TriggerResponse(status="accepted", detail=f"Queued durable video job {job.id}.")


@router.get("/clips", response_model=list[ClipOut])
async def list_clips(session: AsyncSession = Depends(get_session)) -> list[Clip]:
    """List generated clips."""

    result = await session.execute(select(Clip).order_by(desc(Clip.created_at)).limit(100))
    return list(result.scalars().all())


@router.post("/clips/{clip_id}/upload", response_model=UploadOut)
async def upload_clip(
    clip_id: int,
    payload: ScheduleUploadRequest,
    session: AsyncSession = Depends(get_session),
) -> Upload:
    """Queue and optionally upload a clip to YouTube."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    try:
        upload = await uploader.enqueue_upload(
            session,
            clip_id=clip_id,
            scheduled_for=payload.scheduled_for,
            rights_review=payload.rights_review.model_dump() if payload.rights_review else None,
        )
    except UploadGateError as exc:
        await session.commit()
        raise HTTPException(status_code=400, detail={"message": "Upload gate failed", "reasons": exc.reasons}) from exc
    await session.commit()
    await session.refresh(upload)
    if payload.scheduled_for is None:
        job = await job_service.enqueue(
            session,
            job_type="upload",
            payload={"upload_id": upload.id},
            priority=30,
        )
        await session.commit()
        upload.metadata_json = {**(upload.metadata_json or {}), "upload_job_id": job.id}
        await session.commit()
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
    await ensure_generated_clip_records(session, clip, source="subtitles_regenerated")
    await session.commit()
    await session.refresh(clip)
    return clip


@router.post("/clips/{clip_id}/hooks/regenerate", response_model=ClipOut)
async def regenerate_hook(
    clip_id: int,
    payload: RegenerateHookRequest,
    session: AsyncSession = Depends(get_session),
) -> Clip:
    """Regenerate and select a hook using local hook templates and learned outcomes."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    transcript_excerpt = (clip.metadata_json or {}).get("transcript_excerpt", "")
    best = await hook_engine.apply_best_hook(
        session,
        clip,
        transcript_excerpt=transcript_excerpt,
        preferred_type=payload.preferred_type,
    )
    metadata = dict(clip.metadata_json or {})
    metadata["human_review"] = {"action": "regenerate_hook", "selected_hook": best.__dict__}
    clip.metadata_json = metadata
    session.add(
        ReviewDecision(
            clip_id=clip.id,
            action="regenerate_hook",
            labels_json=[],
            reason=f"selected {best.text}",
            metadata_json={"source": "api_review", "selected_hook": best.__dict__},
        )
    )
    await learning_engine.sync_events(session)
    await session.commit()
    await session.refresh(clip)
    return clip


@router.post("/clips/{clip_id}/review/approve", response_model=TriggerResponse)
async def approve_clip(
    clip_id: int,
    payload: ReviewClipRequest,
    session: AsyncSession = Depends(get_session),
) -> TriggerResponse:
    """Approve a generated Short and optionally queue it for upload."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip.status = "approved"
    labels = _normalized_review_labels(payload.labels)
    metadata = dict(clip.metadata_json or {})
    metadata["human_review"] = {"action": "approved", "reason": payload.reason, "labels": labels}
    clip.metadata_json = metadata
    session.add(
        ReviewDecision(
            clip_id=clip.id,
            action="approved",
            labels_json=labels,
            reason=payload.reason,
            reviewer=payload.reviewer,
            metadata_json={"source": "api_review"},
        )
    )
    detail = f"Clip {clip_id} approved."
    if payload.schedule_upload:
        try:
            upload = await uploader.enqueue_upload(
                session,
                clip_id=clip.id,
                scheduled_for=payload.scheduled_for,
                rights_review=payload.rights_review.model_dump() if payload.rights_review else None,
            )
        except UploadGateError as exc:
            await learning_engine.sync_events(session)
            await session.commit()
            raise HTTPException(status_code=400, detail={"message": "Upload gate failed", "reasons": exc.reasons}) from exc
        detail += f" Upload {upload.id} queued."
    await learning_engine.sync_events(session)
    await session.commit()
    return TriggerResponse(status="approved", detail=detail)


@router.post("/clips/{clip_id}/review/reject", response_model=TriggerResponse)
async def reject_clip(
    clip_id: int,
    payload: ReviewClipRequest,
    session: AsyncSession = Depends(get_session),
) -> TriggerResponse:
    """Reject a clip so future learning can avoid similar patterns."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip.status = "rejected"
    labels = _normalized_review_labels(payload.labels)
    metadata = dict(clip.metadata_json or {})
    metadata["human_review"] = {"action": "rejected", "reason": payload.reason, "labels": labels}
    clip.metadata_json = metadata
    session.add(
        ReviewDecision(
            clip_id=clip.id,
            action="rejected",
            labels_json=labels,
            reason=payload.reason,
            reviewer=payload.reviewer,
            metadata_json={"source": "api_review"},
        )
    )
    await negative_samples.record_review(
        session,
        clip=clip,
        action="rejected",
        labels=labels,
        reason=payload.reason,
    )
    await learning_engine.sync_events(session)
    await session.commit()
    return TriggerResponse(status="rejected", detail=f"Clip {clip_id} rejected and added to learning memory.")


@router.post("/clips/{clip_id}/review/rerender", response_model=ClipOut)
async def rerender_clip(
    clip_id: int,
    payload: ReviewClipRequest,
    session: AsyncSession = Depends(get_session),
) -> Clip:
    """Rerender a clip after review while preserving existing pipeline modules."""

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
    await ensure_generated_clip_records(session, clip, source="manual_rerender")
    labels = _normalized_review_labels(payload.labels)
    metadata = dict(clip.metadata_json or {})
    metadata["human_review"] = {"action": "rerendered", "reason": payload.reason, "labels": labels}
    metadata["dead_zone"] = dead_zone_detector.analyze_transcript_file(
        video.transcript_path,
        clip.start_time,
        clip.end_time,
    ).to_dict()
    clip.metadata_json = metadata
    session.add(
        ReviewDecision(
            clip_id=clip.id,
            action="rerendered",
            labels_json=labels,
            reason=payload.reason,
            reviewer=payload.reviewer,
            metadata_json={"source": "api_review"},
        )
    )
    await learning_engine.sync_events(session)
    await session.commit()
    await session.refresh(clip)
    return clip


@router.post("/clips/{clip_id}/rights", response_model=TriggerResponse)
async def record_rights_review(
    clip_id: int,
    payload: RightsReviewRequest,
    session: AsyncSession = Depends(get_session),
) -> TriggerResponse:
    """Record structured rights/originality approval for a clip."""

    clip = await session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    review = await quality_gate.record_rights_review(session, clip_id=clip.id, review=payload.model_dump())
    metadata = dict(clip.metadata_json or {})
    metadata["rights_review"] = {
        "id": review.id,
        "approved_for_upload": review.approved_for_upload,
        "originality_score": review.originality_score,
    }
    clip.metadata_json = metadata
    await session.commit()
    return TriggerResponse(
        status="recorded",
        detail=f"Rights review {review.id} recorded with originality score {review.originality_score:.1f}.",
    )


@router.post("/analytics/refresh", response_model=TriggerResponse)
async def refresh_analytics(session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Queue YouTube analytics refresh as a durable job."""

    job = await job_service.enqueue(session, job_type="refresh_analytics", priority=20)
    await session.commit()
    return TriggerResponse(status="accepted", detail=f"Queued analytics job {job.id}.")


@router.get("/analytics", response_model=AnalyticsSummaryOut)
async def fetch_analytics(session: AsyncSession = Depends(get_session)) -> AnalyticsSummaryOut:
    """Fetch analytics summary."""

    summary = await analytics.latest_summary(session)
    totals_source = (
        select(
            func.max(AnalyticsSnapshot.views).label("views"),
            func.max(AnalyticsSnapshot.likes).label("likes"),
            func.max(AnalyticsSnapshot.comments).label("comments"),
        )
        .where(AnalyticsSnapshot.metric_source == "REAL")
        .group_by(AnalyticsSnapshot.clip_id)
        .subquery()
    )
    totals_result = await session.execute(
        select(
            func.coalesce(func.sum(totals_source.c.views), 0),
            func.coalesce(func.sum(totals_source.c.likes), 0),
            func.coalesce(func.sum(totals_source.c.comments), 0),
        )
    )
    views, likes, comments = totals_result.one()
    return AnalyticsSummaryOut(
        snapshots=[AnalyticsSnapshotOut.model_validate(item) for item in summary["snapshots"]],
        top_clips=[ClipOut.model_validate(item) for item in summary["top_clips"]],
        totals={"views": views, "likes": likes, "comments": comments},
    )


@router.post("/intelligence/refresh", response_model=TriggerResponse)
async def refresh_intelligence(session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Queue local intelligence refresh as a durable job."""

    job = await job_service.enqueue(session, job_type="refresh_intelligence", priority=80)
    await session.commit()
    return TriggerResponse(status="accepted", detail=f"Queued intelligence job {job.id}.")


@router.get("/jobs")
async def list_jobs(session: AsyncSession = Depends(get_session)) -> dict[str, list[dict]]:
    """List recent durable jobs."""

    result = await session.execute(select(ProcessingJob).order_by(desc(ProcessingJob.created_at)).limit(100))
    return {"items": [_serialize_job(item) for item in result.scalars().all()]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """Fetch one durable job."""

    job = await session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(job)


@router.post("/jobs/run-next", response_model=TriggerResponse)
async def run_next_jobs() -> TriggerResponse:
    """Manually run due jobs; useful when the scheduler is disabled."""

    count = await job_service.process_due_jobs(limit=3)
    return TriggerResponse(status="completed", detail=f"Processed {count} due job(s).")


@router.get("/storage")
async def storage_status() -> dict[str, Any]:
    """Return media storage inventory and cleanup mode."""

    return await storage_lifecycle.payload()


@router.post("/storage/cleanup", response_model=TriggerResponse)
async def queue_storage_cleanup(session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Queue storage cleanup as a durable job."""

    job = await job_service.enqueue(session, job_type="cleanup_storage", priority=90)
    await session.commit()
    return TriggerResponse(status="accepted", detail=f"Queued storage cleanup job {job.id}.")


@router.post("/clips/import-existing", response_model=TriggerResponse)
async def queue_existing_clip_import(session: AsyncSession = Depends(get_session)) -> TriggerResponse:
    """Queue import of existing final_short/preview MP4 artifacts."""

    job = await job_service.enqueue(session, job_type="import_existing_clips", priority=10)
    await session.commit()
    return TriggerResponse(status="accepted", detail=f"Queued existing clip import job {job.id}.")


def _normalized_review_labels(labels: list[str]) -> list[str]:
    allowed = {
        "boring",
        "weak hook",
        "no payoff",
        "repetitive",
        "confusing",
        "low energy",
        "policy risk",
        "good pacing",
        "strong clip",
        "viral potential",
    }
    normalized = []
    for label in labels:
        value = " ".join(label.strip().lower().replace("_", " ").split())
        if value and value in allowed and value not in normalized:
            normalized.append(value)
    return normalized


def _serialize_job(job: ProcessingJob) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "payload": job.payload_json or {},
        "result": job.result_json or {},
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "duration_seconds": job.duration_seconds,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
