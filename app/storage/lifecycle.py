"""Storage inventory and retention cleanup for local media files."""

from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.persistence.samples import upsert_clip_media_assets, upsert_media_asset, upsert_video_media_assets
from database.models import Clip, MediaAsset, Video
from database.session import AsyncSessionLocal


class StorageLifecycleService:
    """Track media files and apply configurable retention rules."""

    async def run_cleanup(self) -> dict[str, Any]:
        """Sync media inventory and mark/archive/delete expired files."""

        async with AsyncSessionLocal() as session:
            await self.sync_assets(session)
            now = datetime.now(timezone.utc)
            result = await session.execute(select(MediaAsset))
            scanned = expired = archived = deleted = missing = 0
            bytes_reclaimable = 0
            for asset in result.scalars().all():
                scanned += 1
                path = Path(asset.file_path)
                if not path.exists():
                    asset.retention_state = "missing"
                    missing += 1
                    continue
                keep_until = asset.keep_until or self.keep_until(path, asset.asset_type)
                asset.keep_until = keep_until
                asset.size_bytes = path.stat().st_size
                if keep_until > now:
                    asset.retention_state = "active"
                    continue
                expired += 1
                bytes_reclaimable += asset.size_bytes
                if settings.storage_cleanup_mode == "archive":
                    archived_path = self.archive_path(path)
                    archived_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(archived_path))
                    asset.archived_path = str(archived_path)
                    asset.retention_state = "archived"
                    archived += 1
                elif settings.storage_cleanup_mode == "delete":
                    path.unlink(missing_ok=True)
                    asset.retention_state = "deleted"
                    deleted += 1
                else:
                    asset.retention_state = "expired"
            await session.commit()
            return {
                "mode": settings.storage_cleanup_mode,
                "scanned": scanned,
                "expired": expired,
                "archived": archived,
                "deleted": deleted,
                "missing": missing,
                "bytes_reclaimable": bytes_reclaimable,
            }

    async def payload(self) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            await self.sync_assets(session)
            result = await session.execute(select(MediaAsset))
            by_type: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "size_bytes": 0, "expired": 0})
            total = 0
            for asset in result.scalars().all():
                bucket = by_type[asset.asset_type]
                bucket["count"] += 1
                bucket["size_bytes"] += asset.size_bytes or 0
                total += asset.size_bytes or 0
                if asset.retention_state == "expired":
                    bucket["expired"] += 1
            await session.commit()
            return {
                "mode": settings.storage_cleanup_mode,
                "cleanup_enabled": settings.cleanup_enabled,
                "total_size_bytes": total,
                "by_type": dict(by_type),
            }

    async def sync_assets(self, session) -> None:
        videos = await session.execute(select(Video))
        for video in videos.scalars().all():
            await upsert_video_media_assets(session, video)
        clips = await session.execute(select(Clip))
        for clip in clips.scalars().all():
            await upsert_clip_media_assets(session, clip)
        for temp_file in settings.resolve_path(settings.temp_dir).glob("*"):
            if temp_file.is_file():
                await upsert_media_asset(
                    session,
                    asset_type="temp",
                    file_path=str(temp_file.resolve()),
                    owner_table=None,
                    owner_id=None,
                )
        result = await session.execute(select(MediaAsset))
        for asset in result.scalars().all():
            path = Path(asset.file_path)
            if path.exists():
                asset.size_bytes = path.stat().st_size
                asset.keep_until = self.keep_until(path, asset.asset_type)
                asset.last_seen_at = datetime.now(timezone.utc)
        await session.flush()

    def keep_until(self, path: Path, asset_type: str) -> datetime:
        days = {
            "source_video": settings.source_video_retention_days,
            "audio": settings.audio_retention_days,
            "transcript": settings.transcript_retention_days,
            "subtitle": settings.transcript_retention_days,
            "thumbnail": settings.preview_retention_days,
            "preview": settings.preview_retention_days,
            "rendered_clip": settings.rendered_clip_retention_days,
            "temp": settings.temp_retention_days,
        }.get(asset_type, settings.preview_retention_days)
        created = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return created + timedelta(days=days)

    def archive_path(self, path: Path) -> Path:
        data_root = settings.resolve_path(settings.data_dir)
        try:
            relative = path.resolve().relative_to(data_root)
        except ValueError:
            relative = Path(path.name)
        return settings.archive_dir / relative
