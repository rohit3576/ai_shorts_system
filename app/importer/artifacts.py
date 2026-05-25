"""Import generated MP4 artifacts that predate the canonical database flow."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.persistence.samples import ensure_generated_clip_records
from database.models import Channel, Clip, Video
from database.session import AsyncSessionLocal


class ArtifactImporter:
    """Backfill existing rendered Shorts into Video/Clip/Learning records."""

    async def import_existing(self) -> dict[str, Any]:
        settings.ensure_directories()
        async with AsyncSessionLocal() as session:
            channel = await self._local_import_channel(session)
            imported = 0
            skipped = 0
            for path in self._candidate_paths():
                resolved = str(path.resolve())
                existing = await session.scalar(select(Clip).where(Clip.clip_path == resolved))
                if existing:
                    await ensure_generated_clip_records(session, existing, event_type="imported_clip", source="artifact_importer")
                    skipped += 1
                    continue
                video = await self._video_for_artifact(session, channel, path)
                duration = _duration_seconds(path)
                clip = Clip(
                    video_id=video.id,
                    start_time=0.0,
                    end_time=duration,
                    viral_score=0.0,
                    reason="Imported existing generated Short artifact.",
                    title=path.stem.replace("_", " ").title(),
                    description="Imported from local clip storage; review before upload.",
                    hashtags=["#shorts"],
                    hook_text=path.stem.replace("_", " ").title()[:120],
                    clip_path=resolved,
                    subtitle_path=self._subtitle_for(path),
                    status="generated",
                    metadata_json={
                        "imported_from_filesystem": True,
                        "metric_source": "PREDICTED",
                        "transcript_excerpt": "",
                    },
                )
                session.add(clip)
                await session.flush()
                await ensure_generated_clip_records(session, clip, event_type="imported_clip", source="artifact_importer")
                imported += 1
            await session.commit()
            return {"imported": imported, "skipped": skipped}

    async def _local_import_channel(self, session) -> Channel:
        channel = await session.scalar(select(Channel).where(Channel.url == "local://imports"))
        if channel:
            return channel
        channel = Channel(
            name="Local Imports",
            channel_id="local-imports",
            url="local://imports",
            active=False,
        )
        session.add(channel)
        await session.flush()
        return channel

    async def _video_for_artifact(self, session, channel: Channel, path: Path) -> Video:
        digest = _artifact_id(path)
        video = await session.scalar(select(Video).where(Video.youtube_video_id == digest))
        if video:
            return video
        video = Video(
            channel_id=channel.id,
            youtube_video_id=digest,
            url=f"local://clips/{path.name}",
            title=path.stem.replace("_", " ").title(),
            status="imported",
            duration_seconds=_duration_seconds(path),
            metadata_json={"source": "artifact_importer", "file_path": str(path.resolve())},
        )
        session.add(video)
        await session.flush()
        return video

    def _candidate_paths(self) -> list[Path]:
        patterns = ["*.mp4", "*.mov", "*.m4v"]
        paths: list[Path] = []
        for pattern in patterns:
            paths.extend(settings.clips_dir.glob(pattern))
        paths.extend(settings.resolve_path(settings.temp_dir).glob("preview*.mp4"))
        paths.extend(settings.resolve_path(settings.temp_dir).glob("*preview*.mp4"))
        return sorted({path.resolve() for path in paths if path.is_file()})

    def _subtitle_for(self, path: Path) -> str | None:
        for suffix in [".ass", ".srt", ".vtt"]:
            candidate = path.with_suffix(suffix)
            if candidate.exists():
                return str(candidate.resolve())
        matches = list(path.parent.glob(f"{path.stem}*.ass"))
        return str(matches[0].resolve()) if matches else None


def _artifact_id(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime}".encode("utf-8", errors="ignore")
    return "local-" + hashlib.sha1(raw).hexdigest()[:32]


def _duration_seconds(path: Path) -> float:
    try:
        import cv2

        capture = cv2.VideoCapture(str(path))
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = capture.get(cv2.CAP_PROP_FPS) or 0
        capture.release()
        if fps > 0 and frames > 0:
            return round(float(frames / fps), 3)
    except Exception:
        pass
    return 30.0
