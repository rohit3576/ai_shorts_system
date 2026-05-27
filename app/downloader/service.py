"""Download source videos and extract audio."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils.process import run_command
from database.models import Video

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Download YouTube videos with yt-dlp."""

    async def download(self, session: AsyncSession, video: Video) -> Path:
        """Download the highest quality source video for a Video row."""

        metadata = await self.fetch_metadata(video.url)
        self.validate_metadata(metadata)
        duration = float(metadata.get("duration") or video.duration_seconds or 0)
        section_end = min(
            duration or settings.max_download_seconds,
            settings.processing_start_seconds + settings.max_download_seconds,
        )
        output_template = settings.videos_dir / f"{video.youtube_video_id}.%(ext)s"
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--download-sections",
            f"*{settings.processing_start_seconds}-{int(section_end)}",
            "-f",
            settings.ytdlp_format,
            "--merge-output-format",
            settings.ytdlp_merge_output_format,
            "--print",
            "after_move:filepath",
            "-o",
            str(output_template),
            video.url,
        ]

        result = await run_command(command, timeout_seconds=None)
        downloaded_path = self._resolve_download_path(video.youtube_video_id, result.stdout)
        video.downloaded_path = str(downloaded_path)
        video.status = "downloaded"
        video.metadata_json = {
            **(video.metadata_json or {}),
            "download_stdout": result.stdout[-2000:],
            "ingestion_safety": self.safety_summary(metadata),
            "processed_section": {
                "start_seconds": settings.processing_start_seconds,
                "end_seconds": int(section_end),
                "max_download_seconds": settings.max_download_seconds,
            },
        }
        video.duration_seconds = duration or video.duration_seconds
        await session.flush()
        logger.info("Downloaded video %s to %s", video.youtube_video_id, downloaded_path)
        return downloaded_path

    async def fetch_metadata(self, video_url: str) -> dict:
        """Fetch yt-dlp metadata without downloading media."""

        result = await run_command(
            [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-playlist", video_url],
            timeout_seconds=settings.request_timeout_seconds * 2,
        )
        return json.loads(result.stdout)

    def validate_metadata(self, metadata: dict) -> None:
        """Reject source videos that are unsafe for daily creator operations."""

        if metadata.get("is_live") or metadata.get("was_live") or metadata.get("live_status") in {"is_live", "is_upcoming"}:
            raise ValueError("Ingestion rejected: live streams and upcoming streams are not processed.")
        availability = str(metadata.get("availability") or "").lower()
        if availability in {"private", "subscriber_only", "premium_only"}:
            raise ValueError(f"Ingestion rejected: source video availability is {availability}.")
        duration = float(metadata.get("duration") or 0)
        if duration <= 0:
            raise ValueError("Ingestion rejected: source video duration is unavailable.")
        if duration > settings.max_video_duration_seconds:
            raise ValueError(
                f"Ingestion rejected: source video is {duration:.0f}s, above "
                f"{settings.max_video_duration_seconds}s limit."
            )

    def safety_summary(self, metadata: dict) -> dict:
        """Persist the ingest gate inputs for auditability."""

        return {
            "duration_seconds": metadata.get("duration"),
            "availability": metadata.get("availability"),
            "is_live": bool(metadata.get("is_live")),
            "was_live": bool(metadata.get("was_live")),
            "live_status": metadata.get("live_status"),
            "max_video_duration_seconds": settings.max_video_duration_seconds,
            "max_download_seconds": settings.max_download_seconds,
        }

    def _resolve_download_path(self, youtube_video_id: str, stdout: str) -> Path:
        for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
            candidate = Path(line)
            if candidate.exists():
                return candidate.resolve()
        matches = sorted(settings.videos_dir.glob(f"{youtube_video_id}.*"))
        if not matches:
            raise FileNotFoundError(f"yt-dlp completed but no file was found for {youtube_video_id}")
        return matches[-1].resolve()


class AudioExtractor:
    """Extract normalized mono WAV audio using FFmpeg for whisper.cpp."""

    async def extract_mp3(self, session: AsyncSession, video: Video) -> Path:
        """Extract clean speech-friendly audio from a downloaded video."""

        if not video.downloaded_path:
            raise ValueError(f"Video {video.id} has no downloaded_path")

        input_path = Path(video.downloaded_path)
        output_path = settings.audio_dir / f"{video.youtube_video_id}.wav"
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        await run_command(command, timeout_seconds=None)
        video.audio_path = str(output_path.resolve())
        video.status = "audio_extracted"
        await session.flush()
        logger.info("Extracted audio for video %s to %s", video.youtube_video_id, output_path)
        return output_path.resolve()
