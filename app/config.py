"""Central application configuration.

The system is intentionally local-first. Every path defaults to a project-local
directory, while external services such as Ollama, whisper.cpp, and YouTube API
credentials are configured through environment variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Shorts Automation System"
    environment: str = "local"
    log_level: str = "INFO"
    sql_echo: bool = False

    database_url: str = "sqlite+aiosqlite:///./database/shorts.db"

    data_dir: Path = Path("data")
    temp_dir: Path = Path("temp")
    models_dir: Path = Path("models")
    training_dir: Path = Path("data/training")

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    ytdlp_format: str = "bv*+ba/b"
    ytdlp_merge_output_format: str = "mp4"

    whisper_cpp_binary: str = "whisper-cpp"
    whisper_model_path: Path = Path("models/ggml-tiny.en.bin")
    whisper_language: str = "auto"
    whisper_threads: int = 4

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 120

    scheduler_interval_minutes: int = 30
    scheduler_enabled: bool = True
    max_clips_per_video: int = 3
    min_clip_seconds: int = 18
    max_clip_seconds: int = 58
    viral_score_threshold: float = 0.72
    allow_heuristic_clip_fallback: bool = True

    shorts_width: int = 1080
    shorts_height: int = 1920
    crf: int = 23
    video_preset: str = "veryfast"
    audio_bitrate: str = "160k"

    youtube_upload_enabled: bool = False
    youtube_client_secret_file: Path = Path("client_secret.json")
    youtube_token_file: Path = Path("youtube_token.json")
    youtube_privacy_status: str = "private"

    analytics_refresh_hours: int = 6
    analytics_snapshot_hours: str = "1,6,24,72,168"
    analytics_min_refresh_minutes: int = 30
    dashboard_page_size: int = 50

    job_worker_interval_minutes: int = 1
    job_max_attempts: int = 3

    cleanup_enabled: bool = True
    storage_cleanup_mode: str = Field(
        "mark_only",
        description="mark_only, archive, or delete",
    )
    source_video_retention_days: int = 30
    audio_retention_days: int = 14
    transcript_retention_days: int = 180
    preview_retention_days: int = 14
    rendered_clip_retention_days: int = 365
    temp_retention_days: int = 3

    upload_min_originality_score: float = 60.0
    upload_min_hook_quality: float = 55.0
    upload_min_pacing_score: float = 50.0
    upload_max_dead_zone_risk: float = 65.0

    request_timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.5

    @property
    def project_root(self) -> Path:
        """Return the project directory containing main.py."""

        return Path(__file__).resolve().parents[1]

    def resolve_path(self, value: Path) -> Path:
        """Resolve a possibly relative path against the project root."""

        return value if value.is_absolute() else self.project_root / value

    @property
    def videos_dir(self) -> Path:
        return self.resolve_path(self.data_dir) / "videos"

    @property
    def audio_dir(self) -> Path:
        return self.resolve_path(self.data_dir) / "audio"

    @property
    def transcripts_dir(self) -> Path:
        return self.resolve_path(self.data_dir) / "transcripts"

    @property
    def clips_dir(self) -> Path:
        return self.resolve_path(self.data_dir) / "clips"

    @property
    def thumbnails_dir(self) -> Path:
        return self.resolve_path(self.data_dir) / "thumbnails"

    @property
    def training_data_dir(self) -> Path:
        return self.resolve_path(self.training_dir)

    @property
    def archive_dir(self) -> Path:
        return self.resolve_path(self.data_dir) / "archive"

    @property
    def analytics_windows(self) -> list[int]:
        windows: list[int] = []
        for raw in self.analytics_snapshot_hours.split(","):
            raw = raw.strip()
            if raw.isdigit():
                windows.append(int(raw))
        return windows or [1, 6, 24, 72, 168]

    def ensure_directories(self) -> None:
        """Create all local runtime directories if they do not exist."""

        for path in [
            self.resolve_path(self.data_dir),
            self.videos_dir,
            self.audio_dir,
            self.transcripts_dir,
            self.clips_dir,
            self.thumbnails_dir,
            self.training_data_dir,
            self.archive_dir,
            self.resolve_path(self.temp_dir),
            self.resolve_path(self.models_dir),
            self.project_root / "database",
        ]:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings."""

    return Settings()


settings: Settings = get_settings()
