"""SQLAlchemy ORM schema for the AI Shorts system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class TimestampMixin:
    """Created and updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Channel(TimestampMixin, Base):
    """A monitored YouTube channel."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    rss_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    videos: Mapped[list["Video"]] = relationship(back_populates="channel")


class Video(TimestampMixin, Base):
    """Source video discovered from a monitored channel."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    youtube_video_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="discovered", nullable=False)
    downloaded_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    transcript_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel: Mapped[Channel] = relationship(back_populates="videos")
    clips: Mapped[list["Clip"]] = relationship(back_populates="video")


class Clip(TimestampMixin, Base):
    """A generated Shorts candidate."""

    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    viral_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    hook_text: Mapped[str | None] = mapped_column(String(140), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    subtitle_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="detected", nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    video: Mapped[Video] = relationship(back_populates="clips")
    uploads: Mapped[list["Upload"]] = relationship(back_populates="clip")
    analytics: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="clip")


class Upload(TimestampMixin, Base):
    """YouTube upload queue and status records."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), nullable=False)
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    privacy_status: Mapped[str] = mapped_column(String(32), default="private", nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    clip: Mapped[Clip] = relationship(back_populates="uploads")
    analytics: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="upload")


class AnalyticsSnapshot(TimestampMixin, Base):
    """Point-in-time analytics for an uploaded Short."""

    __tablename__ = "analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), nullable=False)
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    clip: Mapped[Clip] = relationship(back_populates="analytics")
    upload: Mapped[Upload | None] = relationship(back_populates="analytics")


Index("ix_videos_channel_status", Video.channel_id, Video.status)
Index("ix_clips_video_score", Clip.video_id, Clip.viral_score)
Index("ix_uploads_status_scheduled", Upload.status, Upload.scheduled_for)
Index("ix_analytics_clip_captured", AnalyticsSnapshot.clip_id, AnalyticsSnapshot.captured_at)

