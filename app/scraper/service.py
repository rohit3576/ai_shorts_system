"""YouTube scraping and new-upload detection."""

from __future__ import annotations

import calendar
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils.process import ToolExecutionError, run_command
from database.models import Channel, Video

logger = logging.getLogger(__name__)

CHANNEL_ID_RE = re.compile(r"(UC[\w-]{20,})")


def extract_channel_id(value: str) -> str | None:
    """Extract a YouTube channel ID from a URL or raw channel ID."""

    if value.startswith("UC") and len(value) >= 20:
        return value
    match = CHANNEL_ID_RE.search(value)
    return match.group(1) if match else None


def rss_url_for_channel_id(channel_id: str) -> str:
    """Build the official YouTube RSS feed URL for a channel."""

    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def is_youtube_rss_url(value: str) -> bool:
    """Return true if the user supplied a YouTube feed URL directly."""

    return "youtube.com/feeds/videos.xml" in value


def parse_feed_datetime(value: Any) -> datetime | None:
    """Convert feedparser's struct_time into an aware datetime."""

    if not value:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


class YouTubeScraper:
    """Discover new uploads for configured YouTube channels."""

    async def add_channel(
        self,
        session: AsyncSession,
        *,
        url: str,
        name: str | None = None,
    ) -> Channel:
        """Add a channel to the monitor list without duplicating records."""

        channel_id = extract_channel_id(url)
        existing = await session.scalar(select(Channel).where(Channel.url == url))
        if existing:
            return existing

        if channel_id:
            existing_by_id = await session.scalar(
                select(Channel).where(Channel.channel_id == channel_id)
            )
            if existing_by_id:
                return existing_by_id

        rss_url = (
            url
            if is_youtube_rss_url(url)
            else rss_url_for_channel_id(channel_id)
            if channel_id
            else None
        )
        channel = Channel(
            name=name,
            channel_id=channel_id,
            url=url,
            rss_url=rss_url,
            active=True,
        )
        session.add(channel)
        await session.flush()
        logger.info("Added channel monitor: %s", url)
        return channel

    async def scan_all_channels(self, session: AsyncSession) -> list[Video]:
        """Scan every active channel and return newly discovered videos."""

        result = await session.execute(select(Channel).where(Channel.active.is_(True)))
        channels = list(result.scalars().all())
        discovered: list[Video] = []
        for channel in channels:
            try:
                discovered.extend(await self.scan_channel(session, channel))
            except Exception as exc:
                logger.exception("Failed scanning channel %s: %s", channel.url, exc)
        return discovered

    async def scan_channel(self, session: AsyncSession, channel: Channel) -> list[Video]:
        """Scan a single channel RSS feed for new uploads."""

        if not channel.rss_url:
            await self._resolve_channel_rss_url(channel)

        if not channel.rss_url:
            logger.warning("Skipping channel without RSS URL: %s", channel.url)
            return []

        logger.info("Scanning channel %s", channel.url)
        feed = await self._fetch_feed(channel.rss_url)
        new_videos: list[Video] = []

        for entry in feed.entries:
            youtube_video_id = entry.get("yt_videoid")
            if not youtube_video_id:
                continue

            existing = await session.scalar(
                select(Video).where(Video.youtube_video_id == youtube_video_id)
            )
            if existing:
                continue

            video = Video(
                channel_id=channel.id,
                youtube_video_id=youtube_video_id,
                url=entry.get("link") or f"https://www.youtube.com/watch?v={youtube_video_id}",
                title=entry.get("title", "Untitled upload"),
                description=entry.get("summary"),
                published_at=parse_feed_datetime(entry.get("published_parsed")),
                status="discovered",
                metadata_json={"source": "youtube_rss"},
            )
            session.add(video)
            new_videos.append(video)

        channel.last_checked_at = datetime.now(timezone.utc)
        await session.flush()
        logger.info("Channel %s produced %s new videos", channel.url, len(new_videos))
        return new_videos

    async def _fetch_feed(self, rss_url: str) -> Any:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(rss_url)
            response.raise_for_status()
        parsed = feedparser.parse(response.text)
        if parsed.bozo:
            logger.warning("Feed parser reported malformed feed for %s", rss_url)
        return parsed

    async def _resolve_channel_rss_url(self, channel: Channel) -> None:
        """Try resolving @handles and custom URLs to channel IDs with yt-dlp."""

        logger.info("Resolving channel ID with yt-dlp: %s", channel.url)
        try:
            result = await run_command(
                [
                    sys.executable,
                    "-m",
                    "yt_dlp",
                    "--dump-single-json",
                    "--playlist-end",
                    "1",
                    channel.url,
                ],
                timeout_seconds=settings.request_timeout_seconds,
            )
        except (ToolExecutionError, FileNotFoundError, TimeoutError) as exc:
            logger.warning("Could not resolve channel %s: %s", channel.url, exc)
            return

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("yt-dlp returned non-JSON channel metadata for %s", channel.url)
            return

        channel_id = payload.get("channel_id") or payload.get("uploader_id")
        if channel_id:
            channel.channel_id = channel_id
            channel.rss_url = rss_url_for_channel_id(channel_id)
            if not channel.name:
                channel.name = payload.get("channel") or payload.get("uploader")
