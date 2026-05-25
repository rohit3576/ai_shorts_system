"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AddChannelRequest(BaseModel):
    """Request body for adding a monitored channel."""

    url: str = Field(..., description="YouTube channel URL, channel ID, or RSS feed URL")
    name: str | None = None
    niche_type: str = "general"
    upload_style: str = "curiosity clips"
    hook_style: str = "curiosity gap"
    target_audience: str | None = None


class AddSourceRequest(BaseModel):
    """Request body for adding a playlist, creator, or source URL."""

    url: str
    source_type: str = Field("channel", description="channel, playlist, creator, or url")
    label: str | None = None
    channel_id: int | None = None


class ScheduleUploadRequest(BaseModel):
    """Request body for upload scheduling."""

    scheduled_for: datetime | None = None


class ReviewClipRequest(BaseModel):
    """Human review action for a generated Short."""

    reason: str | None = None
    schedule_upload: bool = False
    scheduled_for: datetime | None = None


class RegenerateHookRequest(BaseModel):
    """Request body for regenerating a clip hook."""

    preferred_type: str | None = Field(
        default=None,
        description="curiosity, fear, surprise, emotional, conflict, authority",
    )


class TriggerResponse(BaseModel):
    """Simple async task response."""

    status: str
    detail: str


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    channel_id: str | None
    url: str
    rss_url: str | None
    active: bool
    last_checked_at: datetime | None
    created_at: datetime


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    youtube_video_id: str
    url: str
    title: str
    published_at: datetime | None
    status: str
    downloaded_path: str | None
    audio_path: str | None
    transcript_path: str | None
    error: str | None
    created_at: datetime


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    start_time: float
    end_time: float
    viral_score: float
    reason: str | None
    title: str | None
    description: str | None
    hashtags: list[str] | None
    hook_text: str | None
    clip_path: str | None
    subtitle_path: str | None
    status: str
    created_at: datetime


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clip_id: int
    youtube_video_id: str | None
    status: str
    privacy_status: str
    scheduled_for: datetime | None
    uploaded_at: datetime | None
    error: str | None
    created_at: datetime


class AnalyticsSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clip_id: int
    upload_id: int | None
    views: int
    likes: int
    comments: int
    ctr: float | None
    retention_avg: float | None
    captured_at: datetime


class AnalyticsSummaryOut(BaseModel):
    """API response for analytics summary."""

    snapshots: list[AnalyticsSnapshotOut]
    top_clips: list[ClipOut]
    totals: dict[str, Any]
