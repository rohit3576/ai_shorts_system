"""SQLAlchemy ORM schema for the AI Shorts system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
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
    rights_review_id: Mapped[int | None] = mapped_column(ForeignKey("rights_reviews.id"), nullable=True)
    quality_gate_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    clip: Mapped[Clip] = relationship(back_populates="uploads")
    analytics: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="upload")
    rights_review: Mapped["RightsReview | None"] = relationship()


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
    average_view_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_view_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    subscriber_gain: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rewatch_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_window_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_age_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_source: Mapped[str] = mapped_column(String(20), default="REAL", nullable=False)
    capture_status: Mapped[str] = mapped_column(String(40), default="captured", nullable=False)
    unavailable_metrics: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    clip: Mapped[Clip] = relationship(back_populates="analytics")
    upload: Mapped[Upload | None] = relationship(back_populates="analytics")


class ReviewDecision(TimestampMixin, Base):
    """Human review labels and decisions used as learning signals."""

    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    labels_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    clip: Mapped[Clip] = relationship()


class RightsReview(TimestampMixin, Base):
    """Structured rights/originality approval required before upload."""

    __tablename__ = "rights_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), nullable=False)
    owned_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    licensed_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    commentary_added: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    narration_added: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transformative_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_for_upload: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    originality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    policy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    clip: Mapped[Clip] = relationship()


class QualityGateResult(TimestampMixin, Base):
    """Upload preflight result for a clip."""

    __tablename__ = "quality_gate_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), nullable=False)
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    originality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hook_quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    subtitle_readability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pacing_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dead_zone_risk: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    render_quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    review_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reasons_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    clip: Mapped[Clip] = relationship()
    upload: Mapped[Upload | None] = relationship()


class NegativeSample(TimestampMixin, Base):
    """Failures and rejected patterns used to teach the system what to avoid."""

    __tablename__ = "negative_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int | None] = mapped_column(ForeignKey("clips.id"), nullable=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    severity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="system", nullable=False)

    clip: Mapped[Clip | None] = relationship()
    video: Mapped[Video | None] = relationship()


class ChannelProfile(TimestampMixin, Base):
    """Creator-facing strategy profile for a managed Shorts channel."""

    __tablename__ = "channel_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), unique=True, nullable=False)
    niche_type: Mapped[str] = mapped_column(String(80), default="general", nullable=False)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upload_style: Mapped[str] = mapped_column(String(80), default="curiosity clips", nullable=False)
    hook_style: Mapped[str] = mapped_column(String(80), default="curiosity gap", nullable=False)
    subtitle_style: Mapped[str] = mapped_column(String(80), default="tiktok punch captions", nullable=False)
    pacing_style: Mapped[str] = mapped_column(String(80), default="fast cut", nullable=False)
    target_duration_seconds: Mapped[int] = mapped_column(Integer, default=38, nullable=False)
    upload_frequency_per_day: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    schedule_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    estimated_shorts_rpm: Mapped[float] = mapped_column(Float, default=0.06, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    channel: Mapped[Channel] = relationship()


class SourceFeed(TimestampMixin, Base):
    """A local-first ingest source such as a channel, playlist, or creator URL."""

    __tablename__ = "source_feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="channel", nullable=False)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    channel: Mapped[Channel | None] = relationship()


class ClipIntelligence(TimestampMixin, Base):
    """Retention and virality scoring captured before rendering a Short."""

    __tablename__ = "clip_intelligence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id"), unique=True, nullable=False)
    channel_profile_id: Mapped[int | None] = mapped_column(ForeignKey("channel_profiles.id"), nullable=True)
    retention_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    viral_probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    curiosity_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    emotional_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pacing_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hook_strength_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    conflict_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    danger_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    surprise_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    humor_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    hook_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision: Mapped[str] = mapped_column(String(40), default="review", nullable=False)
    reasons_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    clip: Mapped[Clip] = relationship()
    channel_profile: Mapped[ChannelProfile | None] = relationship()


class TrendSignal(TimestampMixin, Base):
    """Locally mined keyword/topic trend signal."""

    __tablename__ = "trend_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    niche_type: Mapped[str] = mapped_column(String(80), default="general", nullable=False)
    keyword: Mapped[str] = mapped_column(String(140), nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="local_metadata", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    velocity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (UniqueConstraint("niche_type", "keyword", "source", name="uq_trend_keyword_source"),)


class LearningEvent(TimestampMixin, Base):
    """A reusable learning sample from performance, rendering, or AI scoring."""

    __tablename__ = "learning_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    clip_id: Mapped[int | None] = mapped_column(ForeignKey("clips.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), default="clip_outcome", nullable=False)
    outcome_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    learned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    channel: Mapped[Channel | None] = relationship()
    clip: Mapped[Clip | None] = relationship()


class RevenueSnapshot(TimestampMixin, Base):
    """Estimated Shorts revenue based on local analytics and RPM assumptions."""

    __tablename__ = "revenue_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    clip_id: Mapped[int | None] = mapped_column(ForeignKey("clips.id"), nullable=True)
    upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    watch_time_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_rpm: Mapped[float] = mapped_column(Float, default=0.06, nullable=False)
    estimated_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    projected_monthly_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    channel: Mapped[Channel | None] = relationship()
    clip: Mapped[Clip | None] = relationship()
    upload: Mapped[Upload | None] = relationship()


class UploadRecommendation(TimestampMixin, Base):
    """AI/media-ops recommendation for when and how to publish a Short."""

    __tablename__ = "upload_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    clip_id: Mapped[int | None] = mapped_column(ForeignKey("clips.id"), nullable=True)
    recommended_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hashtags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    thumbnail_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="recommended", nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    channel: Mapped[Channel | None] = relationship()
    clip: Mapped[Clip | None] = relationship()


class ProcessingJob(TimestampMixin, Base):
    """Durable job queue record for resumable local automation."""

    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    stages: Mapped[list["JobStage"]] = relationship(back_populates="job")


class JobStage(TimestampMixin, Base):
    """Stage-level state inside a durable processing job."""

    __tablename__ = "job_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    stderr_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    job: Mapped[ProcessingJob] = relationship(back_populates="stages")

    __table_args__ = (UniqueConstraint("job_id", "name", name="uq_job_stage_name"),)


class MediaAsset(TimestampMixin, Base):
    """Tracked filesystem asset with retention policy metadata."""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    owner_table: Mapped[str | None] = mapped_column(String(80), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retention_state: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    keep_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CalibrationReport(TimestampMixin, Base):
    """Prediction-vs-outcome report for retention calibration."""

    __tablename__ = "calibration_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retention_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    virality_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    hook_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


Index("ix_videos_channel_status", Video.channel_id, Video.status)
Index("ix_clips_video_score", Clip.video_id, Clip.viral_score)
Index("ix_uploads_status_scheduled", Upload.status, Upload.scheduled_for)
Index("ix_analytics_clip_captured", AnalyticsSnapshot.clip_id, AnalyticsSnapshot.captured_at)
Index("ix_channel_profiles_niche", ChannelProfile.niche_type, ChannelProfile.active)
Index("ix_source_feeds_type_active", SourceFeed.source_type, SourceFeed.active)
Index("ix_clip_intelligence_scores", ClipIntelligence.retention_score, ClipIntelligence.viral_probability)
Index("ix_trend_signals_niche_score", TrendSignal.niche_type, TrendSignal.score)
Index("ix_learning_events_type_score", LearningEvent.event_type, LearningEvent.outcome_score)
Index("ix_revenue_snapshots_channel_period", RevenueSnapshot.channel_id, RevenueSnapshot.period_end)
Index("ix_upload_recommendations_status_time", UploadRecommendation.status, UploadRecommendation.recommended_for)
Index("ix_review_decisions_clip_action", ReviewDecision.clip_id, ReviewDecision.action)
Index("ix_rights_reviews_clip_approved", RightsReview.clip_id, RightsReview.approved_for_upload)
Index("ix_quality_gate_clip_passed", QualityGateResult.clip_id, QualityGateResult.passed)
Index("ix_negative_samples_category", NegativeSample.category, NegativeSample.severity)
Index("ix_processing_jobs_status_next", ProcessingJob.status, ProcessingJob.next_run_at, ProcessingJob.priority)
Index("ix_job_stages_job_status", JobStage.job_id, JobStage.status)
Index("ix_media_assets_type_state", MediaAsset.asset_type, MediaAsset.retention_state)
Index("ix_calibration_reports_generated", CalibrationReport.generated_at)
