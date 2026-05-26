"""End-to-end orchestration for the AI Shorts pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.captions.metadata import CaptionGenerator
from app.captions.subtitles import SubtitleEngine
from app.clip_detector.service import ClipCandidate, ViralClipDetector
from app.config import settings
from app.downloader.service import AudioExtractor, VideoDownloader
from app.editor.service import ShortsEditor
from app.intelligence.deadzone import DeadZoneDetector
from app.intelligence.hooks import HookTemplateEngine
from app.intelligence.negative_samples import NegativeSampleService
from app.intelligence.retention import RetentionScorer
from app.intelligence.sources import SourceIngestionService
from app.intelligence.upload import UploadIntelligenceService
from app.jobs.tracker import job_stage
from app.persistence.samples import ensure_generated_clip_records, upsert_video_media_assets
from app.scraper.service import YouTubeScraper
from app.transcription.service import WhisperCppTranscriber
from app.uploader.service import YouTubeUploader
from database.models import Clip, Video
from database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class ShortsPipeline:
    """Coordinate discovery, download, transcription, clipping, and queuing."""

    def __init__(self) -> None:
        self.scraper = YouTubeScraper()
        self.downloader = VideoDownloader()
        self.audio_extractor = AudioExtractor()
        self.transcriber = WhisperCppTranscriber()
        self.detector = ViralClipDetector()
        self.dead_zone_detector = DeadZoneDetector()
        self.hook_engine = HookTemplateEngine()
        self.retention_scorer = RetentionScorer()
        self.negative_samples = NegativeSampleService()
        self.caption_generator = CaptionGenerator()
        self.subtitle_engine = SubtitleEngine()
        self.editor = ShortsEditor()
        self.uploader = YouTubeUploader()
        self.source_ingestion = SourceIngestionService()
        self.upload_intelligence = UploadIntelligenceService()

    async def process_new_videos(self, job_id: int | None = None) -> dict[str, Any]:
        """Scan channels and process discovered videos."""

        async with AsyncSessionLocal() as session:
            async with job_stage(session, job_id, "scan_sources", stage_order=1):
                discovered = await self.scraper.scan_all_channels(session)
                discovered.extend(await self.source_ingestion.scan_sources(session))
            await session.commit()

            result = await session.execute(
                select(Video).where(Video.status == "discovered").order_by(Video.published_at.desc())
            )
            videos = list(result.scalars().all())

        processed = []
        for video in videos:
            processed.append(await self.process_video(video.id, job_id=job_id))

        return {"discovered": len(discovered), "processed": processed}

    async def process_video(self, video_id: int, job_id: int | None = None) -> dict[str, Any]:
        """Process a single video end-to-end."""

        async with AsyncSessionLocal() as session:
            video = await session.get(Video, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found")

            try:
                video.status = "processing"
                video.error = None
                await session.commit()

                if not video.downloaded_path:
                    async with job_stage(session, job_id, f"download_video_{video.id}", stage_order=10):
                        await self.downloader.download(session, video)
                        await upsert_video_media_assets(session, video)
                    await session.commit()

                if not video.audio_path:
                    async with job_stage(session, job_id, f"extract_audio_{video.id}", stage_order=20):
                        await self.audio_extractor.extract_mp3(session, video)
                        await upsert_video_media_assets(session, video)
                    await session.commit()

                if not video.transcript_path:
                    async with job_stage(session, job_id, f"transcribe_{video.id}", stage_order=30):
                        await self.transcriber.transcribe(session, video)
                        await upsert_video_media_assets(session, video)
                    await session.commit()

                existing_clips = await session.execute(select(Clip).where(Clip.video_id == video.id))
                existing = list(existing_clips.scalars().all())
                if existing:
                    for clip in existing:
                        await ensure_generated_clip_records(session, clip, source="pipeline_resume")
                    video.status = "completed"
                    await session.commit()
                    return {"video_id": video.id, "status": "already_completed"}

                async with job_stage(session, job_id, f"detect_clips_{video.id}", stage_order=40):
                    candidates = await self.detector.detect(video.transcript_path)
                candidates = candidates[: settings.max_render_count_per_video]
                rendered_clip_ids: list[int] = []
                failed_candidates: list[dict[str, Any]] = []
                for candidate in candidates:
                    try:
                        clip = await self._create_clip(session, video, candidate, job_id=job_id)
                        rendered_clip_ids.append(clip.id)
                    except Exception as exc:
                        logger.exception("Candidate failed for video %s", video.id)
                        failed_candidates.append(
                            {
                                "start_time": candidate.start_time,
                                "end_time": candidate.end_time,
                                "error": str(exc),
                            }
                        )
                        await session.commit()

                video.status = "completed" if rendered_clip_ids else "failed"
                if failed_candidates:
                    metadata = dict(video.metadata_json or {})
                    metadata["failed_candidates"] = failed_candidates
                    video.metadata_json = metadata
                await session.commit()
                return {
                    "video_id": video.id,
                    "status": video.status,
                    "clips": rendered_clip_ids,
                    "failed_candidates": failed_candidates,
                }
            except Exception as exc:
                logger.exception("Pipeline failed for video %s", video_id)
                video.status = "failed"
                video.error = str(exc)
                await session.commit()
                return {"video_id": video_id, "status": "failed", "error": str(exc)}

    async def _create_clip(
        self,
        session,
        video: Video,
        candidate: ClipCandidate,
        job_id: int | None = None,
    ) -> Clip:
        transcript_excerpt = self._transcript_excerpt(
            Path(video.transcript_path or ""),
            candidate.start_time,
            candidate.end_time,
        )
        metadata = await self.caption_generator.generate(
            source_title=video.title,
            candidate=candidate,
            transcript_excerpt=transcript_excerpt,
        )
        clip = Clip(
            video_id=video.id,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
            viral_score=candidate.viral_score,
            reason=candidate.reason,
            title=metadata.title,
            description=metadata.description,
            hashtags=metadata.hashtags,
            hook_text=metadata.hook_text or candidate.hook_text,
            status="detected",
            metadata_json={
                "transcript_excerpt": transcript_excerpt,
                "source_title": video.title,
                "source_url": video.url,
                "title_variants": metadata.title_variants,
                "description_variants": metadata.description_variants,
                "hook_type": candidate.hook_type,
                "ingestion_limits": {
                    "max_video_duration_seconds": settings.max_video_duration_seconds,
                    "max_download_seconds": settings.max_download_seconds,
                    "max_render_count_per_video": settings.max_render_count_per_video,
                },
            },
        )
        session.add(clip)
        await session.flush()
        async with job_stage(session, job_id, f"score_clip_{clip.id}", stage_order=50):
            selected_hook = await self.hook_engine.apply_best_hook(
                session,
                clip,
                transcript_excerpt=transcript_excerpt,
            )
            dead_zone_report = self.dead_zone_detector.analyze_transcript_file(
                video.transcript_path or "",
                clip.start_time,
                clip.end_time,
            )
            intelligence = await self.retention_scorer.score_clip(
                session,
                clip,
                transcript_excerpt=transcript_excerpt,
                candidate=candidate,
                dead_zone_report=dead_zone_report,
                hook_variants=[
                    selected_hook,
                    *[
                        type(selected_hook)(**item)
                        for item in (clip.metadata_json or {}).get("hook_variants", [])
                        if item.get("text") != selected_hook.text
                    ][:5],
                ],
            )
            await self._store_predicted_negatives(session, clip, intelligence)

        async with job_stage(session, job_id, f"subtitles_clip_{clip.id}", stage_order=60):
            subtitle_path = self.subtitle_engine.generate_for_clip(
                transcript_path=video.transcript_path or "",
                clip_id=clip.id,
                start_time=clip.start_time,
                end_time=clip.end_time,
            )
            clip.subtitle_path = str(subtitle_path)

        try:
            async with job_stage(session, job_id, f"render_clip_{clip.id}", stage_order=70):
                await self.editor.render_clip(session, clip)
        except Exception as exc:
            metadata = dict(clip.metadata_json or {})
            metadata["render_error"] = str(exc)
            clip.metadata_json = metadata
            clip.status = "render_failed"
            await self.negative_samples.record(
                session,
                category="failed_render",
                clip=clip,
                video=video,
                reason=str(exc),
                labels=["failed renders"],
                severity=90.0,
                source="pipeline",
            )
            await session.flush()
            raise

        await ensure_generated_clip_records(session, clip, source="pipeline_render")
        await self.upload_intelligence.build_recommendations(session)

        if settings.youtube_upload_enabled:
            metadata = dict(clip.metadata_json or {})
            metadata["upload_blocked"] = "Structured rights/originality review is required before upload."
            clip.metadata_json = metadata
            clip.status = "awaiting_rights_review"
        return clip

    def _transcript_excerpt(self, transcript_path: Path, start_time: float, end_time: float) -> str:
        if not transcript_path.exists():
            return ""
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        lines = []
        for segment in transcript.get("segments", []):
            if float(segment["end"]) >= start_time and float(segment["start"]) <= end_time:
                lines.append(segment["text"])
        return " ".join(lines)

    async def _store_predicted_negatives(self, session, clip: Clip, intelligence) -> None:
        metadata = clip.metadata_json or {}
        if intelligence.hook_strength_score < 62:
            await self.negative_samples.record(
                session,
                category="weak_hook",
                clip=clip,
                reason="Predicted hook strength is weak.",
                labels=["weak hook"],
                severity=100 - intelligence.hook_strength_score,
                source="retention_scorer",
            )
        if intelligence.retention_score < 65:
            await self.negative_samples.record(
                session,
                category="low_retention_candidate",
                clip=clip,
                reason="Predicted retention is below upload threshold.",
                labels=["low-retention clips"],
                severity=100 - intelligence.retention_score,
                source="retention_scorer",
            )
        dead_zone = float(metadata.get("dead_zone_score") or 0)
        if dead_zone >= 55:
            await self.negative_samples.record(
                session,
                category="dead_zone_candidate",
                clip=clip,
                reason="Dead-zone detector found slow or low-payoff segment risk.",
                labels=["dead-zone candidates", "boring moments"],
                severity=dead_zone,
                source="dead_zone_detector",
            )
