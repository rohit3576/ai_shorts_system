"""Source ingestion for channels, playlists, and creator URLs."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.scraper.service import YouTubeScraper
from app.utils.process import ToolExecutionError, run_command
from database.models import Channel, SourceFeed, Video

logger = logging.getLogger(__name__)


class SourceIngestionService:
    """Manage extra ingest sources without changing the core pipeline."""

    def __init__(self) -> None:
        self.scraper = YouTubeScraper()

    async def add_source(
        self,
        session: AsyncSession,
        *,
        url: str,
        source_type: str = "channel",
        label: str | None = None,
        channel_id: int | None = None,
    ) -> SourceFeed:
        url = url.strip()
        source_type = source_type.strip().lower()
        metadata: dict[str, Any] = {"created_by": "source_ingestion"}
        if source_type == "topic" and not url.lower().startswith(("http://", "https://", "ytsearch")):
            query = url
            url = f"topic:{query.lower()}"
            label = label or query
            metadata.update({"query": query, "scan_url": f"ytsearch{8}:{query}"})
        existing = await session.scalar(select(SourceFeed).where(SourceFeed.url == url))
        if existing:
            return existing
        linked_channel_id = channel_id
        if source_type == "channel":
            channel = await self.scraper.add_channel(session, url=url, name=label)
            linked_channel_id = channel.id
        source = SourceFeed(
            channel_id=linked_channel_id,
            source_type=source_type,
            url=url,
            label=label,
            metadata_json=metadata,
        )
        session.add(source)
        await session.flush()
        return source

    async def scan_sources(self, session: AsyncSession, *, limit_per_source: int = 8) -> list[Video]:
        """Use yt-dlp metadata to discover videos from playlist/creator sources."""

        result = await session.execute(select(SourceFeed).where(SourceFeed.active.is_(True)))
        sources = list(result.scalars().all())
        discovered: list[Video] = []
        for source in sources:
            if source.source_type == "channel":
                continue
            try:
                discovered.extend(await self._scan_source(session, source, limit_per_source=limit_per_source))
            except Exception as exc:
                logger.warning("Source scan failed for %s: %s", source.url, exc)
        return discovered

    async def _scan_source(self, session: AsyncSession, source: SourceFeed, *, limit_per_source: int) -> list[Video]:
        try:
            result = await run_command(
                [
                    sys.executable,
                    "-m",
                    "yt_dlp",
                    "--dump-single-json",
                    "--playlist-end",
                    str(limit_per_source),
                    (source.metadata_json or {}).get("scan_url") or source.url,
                ],
                timeout_seconds=settings.request_timeout_seconds * 2,
            )
        except (ToolExecutionError, FileNotFoundError, TimeoutError) as exc:
            logger.warning("Could not scan source %s: %s", source.url, exc)
            return []

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("yt-dlp returned non-JSON source metadata for %s", source.url)
            return []

        channel = await self._ensure_source_channel(session, source, payload)
        entries = list(self._iter_video_entries(payload))
        new_videos: list[Video] = []
        for entry in entries:
            if not entry:
                continue
            youtube_id = entry.get("id") or entry.get("display_id")
            url = entry.get("webpage_url") or entry.get("url")
            if youtube_id and not str(youtube_id).startswith("http"):
                url = url or f"https://www.youtube.com/watch?v={youtube_id}"
            if not youtube_id or not url:
                continue
            existing = await session.scalar(select(Video).where(Video.youtube_video_id == str(youtube_id)))
            if existing:
                continue
            video = Video(
                channel_id=channel.id,
                youtube_video_id=str(youtube_id),
                url=str(url),
                title=entry.get("title") or "Untitled source upload",
                description=entry.get("description"),
                duration_seconds=entry.get("duration"),
                status="discovered",
                metadata_json={"source": source.source_type, "source_feed_id": source.id},
            )
            session.add(video)
            new_videos.append(video)
        source.last_checked_at = datetime.now(timezone.utc)
        await session.flush()
        return new_videos

    def _iter_video_entries(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten yt-dlp channel tab payloads into concrete videos."""

        found: list[dict[str, Any]] = []
        for entry in payload.get("entries") or [payload]:
            if not entry:
                continue
            nested = entry.get("entries")
            if nested:
                found.extend(self._iter_video_entries({"entries": nested}))
                continue
            youtube_id = entry.get("id") or entry.get("display_id")
            url = entry.get("webpage_url") or entry.get("url")
            if youtube_id and url and not str(youtube_id).startswith("UC"):
                found.append(entry)
        return found

    async def _ensure_source_channel(self, session: AsyncSession, source: SourceFeed, payload: dict[str, Any]) -> Channel:
        if source.channel_id:
            channel = await session.get(Channel, source.channel_id)
            if channel:
                return channel
        label = source.label or payload.get("channel") or payload.get("uploader") or "Source collection"
        existing = await session.scalar(select(Channel).where(Channel.url == source.url))
        if existing:
            source.channel_id = existing.id
            return existing
        channel = Channel(
            name=label,
            url=source.url,
            channel_id=payload.get("channel_id") or payload.get("uploader_id"),
            active=True,
        )
        session.add(channel)
        await session.flush()
        source.channel_id = channel.id
        return channel
