"""Whisper.cpp transcription wrapper."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils.process import run_command
from database.models import Video

logger = logging.getLogger(__name__)

TIMESTAMP_RE = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})")


def parse_timestamp(value: Any) -> float:
    """Parse whisper.cpp timestamps into seconds."""

    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    match = TIMESTAMP_RE.match(value.strip())
    if not match:
        return 0.0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int(match.group(4))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


class WhisperCppTranscriber:
    """Run whisper.cpp and normalize JSON transcript output."""

    async def transcribe(self, session: AsyncSession, video: Video) -> Path:
        """Generate a timestamped transcript JSON file for a video."""

        if not video.audio_path:
            raise ValueError(f"Video {video.id} has no audio_path")

        model_path = settings.resolve_path(settings.whisper_model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Whisper model not found at {model_path}. Download a ggml model first."
            )

        output_stem = settings.transcripts_dir / video.youtube_video_id
        command = [
            settings.whisper_cpp_binary,
            "-m",
            str(model_path),
            "-f",
            video.audio_path,
            "-oj",
            "-of",
            str(output_stem),
            "-t",
            str(settings.whisper_threads),
        ]
        if settings.whisper_language != "auto":
            command.extend(["-l", settings.whisper_language])

        await run_command(command, timeout_seconds=None)
        whisper_json = output_stem.with_suffix(".json")
        if not whisper_json.exists():
            raise FileNotFoundError(f"whisper.cpp did not create {whisper_json}")

        normalized = self.normalize_whisper_json(whisper_json, video.youtube_video_id, video.audio_path)
        normalized_path = settings.transcripts_dir / f"{video.youtube_video_id}.normalized.json"
        normalized_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

        video.transcript_path = str(normalized_path.resolve())
        video.status = "transcribed"
        await session.flush()
        logger.info("Transcribed video %s to %s", video.youtube_video_id, normalized_path)
        return normalized_path.resolve()

    def normalize_whisper_json(
        self,
        whisper_json: Path,
        youtube_video_id: str,
        audio_path: str,
    ) -> dict[str, Any]:
        """Normalize whisper.cpp variants into a stable transcript schema."""

        raw = json.loads(whisper_json.read_text(encoding="utf-8"))
        source_segments = raw.get("segments") or raw.get("transcription") or []
        segments: list[dict[str, Any]] = []

        for index, item in enumerate(source_segments):
            timestamps = item.get("timestamps") or {}
            offsets = item.get("offsets") or {}
            start = item.get("start")
            end = item.get("end")
            if start is None:
                start = timestamps.get("from")
            if end is None:
                end = timestamps.get("to")
            if start is None and offsets.get("from") is not None:
                start = float(offsets["from"]) / 1000
            if end is None and offsets.get("to") is not None:
                end = float(offsets["to"]) / 1000

            segment = {
                "index": index,
                "start": parse_timestamp(start),
                "end": parse_timestamp(end),
                "text": (item.get("text") or "").strip(),
                "words": self._normalize_words(item),
            }
            if segment["text"]:
                segments.append(segment)

        return {
            "youtube_video_id": youtube_video_id,
            "source_audio": audio_path,
            "language": raw.get("result", {}).get("language") or raw.get("language"),
            "segments": segments,
            "raw_engine": "whisper.cpp",
        }

    def _normalize_words(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        words = item.get("words") or []
        normalized: list[dict[str, Any]] = []
        for word in words:
            normalized.append(
                {
                    "start": parse_timestamp(word.get("start")),
                    "end": parse_timestamp(word.get("end")),
                    "text": str(word.get("text") or word.get("word") or "").strip(),
                }
            )
        return [word for word in normalized if word["text"]]

