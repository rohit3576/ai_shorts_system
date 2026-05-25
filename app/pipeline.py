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
from app.intelligence.retention import RetentionScorer
from app.intelligence.sources import SourceIngestionService
from app.intelligence.upload import UploadIntelligenceService
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
        self.caption_generator = CaptionGenerator()
        self.subtitle_engine = SubtitleEngine()
        self.editor = ShortsEditor()
        self.uploader = YouTubeUploader()
        self.source_ingestion = SourceIngestionService()
        self.upload_intelligence = UploadIntelligenceService()

    async def process_new_videos(self) -> dict[str, Any]:
        """Scan channels and process discovered videos."""

        async with AsyncSessionLocal() as session:
            discovered = await self.scraper.scan_all_channels(session)
            discovered.extend(await self.source_ingestion.scan_sources(session))
            await session.commit()

            result = await session.execute(
                select(Video).where(Video.status == "discovered").order_by(Video.published_at.desc())
            )
            videos = list(result.scalars().all())

        processed = []
        for video in videos:
            processed.append(await self.process_video(video.id))

        return {"discovered": len(discovered), "processed": processed}

    async def process_video(self, video_id: int) -> dict[str, Any]:
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
                    await self.downloader.download(session, video)
                    await session.commit()

                if not video.audio_path:
                    await self.audio_extractor.extract_mp3(session, video)
                    await session.commit()

                if not video.transcript_path:
                    await self.transcriber.transcribe(session, video)
                    await session.commit()

                existing_clips = await session.execute(select(Clip).where(Clip.video_id == video.id))
                if existing_clips.scalars().first():
                    video.status = "completed"
                    await session.commit()
                    return {"video_id": video.id, "status": "already_completed"}

                candidates = await self.detector.detect(video.transcript_path)
                rendered_clip_ids: list[int] = []
                for candidate in candidates:
                    clip = await self._create_clip(session, video, candidate)
                    rendered_clip_ids.append(clip.id)

                video.status = "completed"
                await session.commit()
                return {"video_id": video.id, "status": "completed", "clips": rendered_clip_ids}
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
            metadata_json={"transcript_excerpt": transcript_excerpt},
        )
        session.add(clip)
        await session.flush()
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
        await self.retention_scorer.score_clip(
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

        subtitle_path = self.subtitle_engine.generate_for_clip(
            transcript_path=video.transcript_path or "",
            clip_id=clip.id,
            start_time=clip.start_time,
            end_time=clip.end_time,
        )
        clip.subtitle_path = str(subtitle_path)
        await self.editor.render_clip(session, clip)
        await self.upload_intelligence.build_recommendations(session)

        if settings.youtube_upload_enabled:
            await self.uploader.enqueue_upload(session, clip_id=clip.id)
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
