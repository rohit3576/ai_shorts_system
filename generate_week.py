"""Generate a practical 7-day Shorts batch from saved sources."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from app.config import settings
from app.intelligence.sources import SourceIngestionService
from app.pipeline import ShortsPipeline
from app.scraper.service import YouTubeScraper
from database.models import Clip, Video
from database.session import AsyncSessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a 7-day local Shorts batch.")
    parser.add_argument("--target", type=int, default=7, help="Number of usable Shorts to prepare.")
    parser.add_argument("--max-download-seconds", type=int, default=180, help="Source window to download per video.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings.max_download_seconds = min(settings.max_download_seconds, args.max_download_seconds)
    settings.allow_heuristic_clip_fallback = True

    print("Personal AI Shorts Studio weekly generator")
    print(f"Target usable Shorts: {args.target}")
    print(f"Download window per source: {settings.max_download_seconds}s")

    await scan_sources()
    before_ids = {clip["id"] for clip in await usable_clips()}
    videos = await candidate_videos()
    print(f"Candidate source videos found: {len(videos)}")

    pipeline = ShortsPipeline()
    for video in videos:
        usable = await usable_clips()
        if len([clip for clip in usable if clip["id"] not in before_ids]) >= args.target:
            break
        print("")
        print(f"Processing video #{video['id']}: {video['title']}")
        result = await pipeline.process_video(video["id"])
        print(f"Result: {result}")

    clips = await usable_clips()
    new_clips = [clip for clip in clips if clip["id"] not in before_ids]
    selected = (new_clips or clips)[: args.target]

    print("")
    print("7-day schedule draft")
    print("-" * 72)
    for index, clip in enumerate(selected):
        day = datetime.now().date() + timedelta(days=index)
        time = ["12:30", "18:30", "21:00"][index % 3]
        print(f"{index + 1}. {day} {time} | Clip #{clip['id']} | {clip['hook_text']}")
        print(f"   {clip['title']}")
        print(f"   {clip['clip_path']}")

    if len(selected) < args.target:
        print("")
        print(f"Only {len(selected)} usable Shorts are ready. Run this command again after checking source availability.")
        return 2
    return 0


async def scan_sources() -> None:
    async with AsyncSessionLocal() as session:
        discovered = await YouTubeScraper().scan_all_channels(session)
        discovered.extend(await SourceIngestionService().scan_sources(session, limit_per_source=20))
        await session.commit()
    print(f"Source scan added {len(discovered)} new videos.")


async def candidate_videos() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Video)
            .where(Video.status.in_(["discovered", "failed"]))
            .order_by(desc(Video.published_at), desc(Video.created_at))
            .limit(80)
        )
        rows = list(result.scalars().all())
    candidates = []
    for video in rows:
        if "/shorts/" in (video.url or "").lower():
            continue
        title = (video.title or "").lower()
        if "live stream" in title:
            continue
        candidates.append(
            {
                "id": video.id,
                "title": video.title,
                "url": video.url,
                "duration_seconds": video.duration_seconds,
            }
        )
    return candidates


async def usable_clips() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Clip).where(Clip.clip_path.is_not(None)).order_by(desc(Clip.created_at)))
        clips = []
        for clip in result.scalars().all():
            if clip.status == "rejected":
                continue
            if not clip.clip_path or not Path(clip.clip_path).exists():
                continue
            clips.append(
                {
                    "id": clip.id,
                    "title": clip.title or "Untitled Short",
                    "hook_text": clip.hook_text or "Watch This",
                    "clip_path": clip.clip_path,
                    "created_at": clip.created_at,
                }
            )
        return clips


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
