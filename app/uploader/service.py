"""YouTube upload queue and uploader."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.quality_gate import QualityGateService, UploadGateError
from app.uploader.auth import YouTubeAuth
from database.models import Clip, Upload
from database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """Queue and upload generated Shorts to YouTube."""

    def __init__(self, auth: YouTubeAuth | None = None) -> None:
        self.auth = auth or YouTubeAuth()
        self.quality_gate = QualityGateService()

    async def enqueue_upload(
        self,
        session: AsyncSession,
        *,
        clip_id: int,
        scheduled_for: datetime | None = None,
        rights_review: dict | None = None,
    ) -> Upload:
        """Create an upload queue row for a clip."""

        clip = await session.get(Clip, clip_id)
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        existing = await session.scalar(
            select(Upload).where(Upload.clip_id == clip_id, Upload.status.in_(["queued", "uploading"]))
        )
        if existing:
            return existing

        try:
            gate = await self.quality_gate.validate_for_upload(
                session,
                clip=clip,
                rights_review_payload=rights_review,
            )
        except UploadGateError:
            clip.status = "upload_blocked"
            metadata = dict(clip.metadata_json or {})
            metadata["upload_gate_status"] = "failed"
            clip.metadata_json = metadata
            await session.flush()
            raise

        upload = Upload(
            clip_id=clip_id,
            status="queued",
            privacy_status=settings.youtube_privacy_status,
            scheduled_for=scheduled_for,
            quality_gate_status="passed",
            metadata_json={"quality_gate_id": gate.id},
        )
        session.add(upload)
        await session.flush()
        gate.upload_id = upload.id
        if gate.metadata_json and gate.metadata_json.get("rights_review_id"):
            upload.rights_review_id = int(gate.metadata_json["rights_review_id"])
        logger.info("Queued clip %s for YouTube upload", clip_id)
        return upload

    async def upload_by_id(self, upload_id: int) -> None:
        """Upload a queued item using a fresh database session."""

        async with AsyncSessionLocal() as session:
            await self.upload(session, upload_id)
            await session.commit()

    async def upload(self, session: AsyncSession, upload_id: int) -> Upload:
        """Upload a queued Short to YouTube if uploads are enabled."""

        upload = await session.get(Upload, upload_id)
        if not upload:
            raise ValueError(f"Upload {upload_id} not found")
        clip = await session.get(Clip, upload.clip_id)
        if not clip or not clip.clip_path:
            raise ValueError(f"Upload {upload_id} has no rendered clip")

        try:
            gate = await self.quality_gate.validate_for_upload(session, clip=clip, upload_id=upload.id)
            upload.quality_gate_status = "passed" if gate.passed else "failed"
        except UploadGateError as exc:
            upload.status = "blocked"
            upload.quality_gate_status = "failed"
            upload.error = str(exc)
            await session.flush()
            raise

        if not settings.youtube_upload_enabled:
            upload.status = "dry_run"
            upload.error = "YOUTUBE_UPLOAD_ENABLED=false; upload not sent."
            await session.flush()
            logger.info("Dry-run upload for clip %s", clip.id)
            return upload

        upload.status = "uploading"
        await session.flush()

        try:
            youtube_video_id = await asyncio.to_thread(self._upload_sync, clip, upload)
            upload.youtube_video_id = youtube_video_id
            upload.status = "uploaded"
            upload.uploaded_at = datetime.now(timezone.utc)
            clip.status = "uploaded"
            logger.info("Uploaded clip %s as YouTube video %s", clip.id, youtube_video_id)
        except Exception as exc:
            upload.status = "failed"
            upload.error = str(exc)
            logger.exception("YouTube upload failed for clip %s", clip.id)
        await session.flush()
        return upload

    async def process_due_uploads(self) -> int:
        """Upload due queued items."""

        if not settings.youtube_upload_enabled:
            logger.info("YouTube upload processing skipped because uploads are disabled")
            return 0

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Upload)
                .where(
                    Upload.status == "queued",
                    or_(Upload.scheduled_for.is_(None), Upload.scheduled_for <= now),
                )
                .limit(5)
            )
            uploads = list(result.scalars().all())
            for upload in uploads:
                await self.upload(session, upload.id)
            await session.commit()
            return len(uploads)

    def _upload_sync(self, clip: Clip, upload: Upload) -> str:
        from googleapiclient.http import MediaFileUpload

        youtube = self.auth.build("youtube", "v3")
        description_parts = [clip.description or ""]
        if clip.hashtags:
            description_parts.append(" ".join(clip.hashtags))

        status_body = {"privacyStatus": upload.privacy_status}
        if upload.scheduled_for:
            status_body["privacyStatus"] = "private"
            status_body["publishAt"] = upload.scheduled_for.astimezone(timezone.utc).isoformat()

        body = {
            "snippet": {
                "title": clip.title or "AI Generated Short",
                "description": "\n\n".join(part for part in description_parts if part),
                "tags": [tag.lstrip("#") for tag in (clip.hashtags or [])],
                "categoryId": "22",
            },
            "status": status_body,
        }
        media = MediaFileUpload(
            str(Path(clip.clip_path)),
            chunksize=8 * 1024 * 1024,
            resumable=True,
            mimetype="video/mp4",
        )
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        response = None
        while response is None:
            _status, response = request.next_chunk()
        return response["id"]
