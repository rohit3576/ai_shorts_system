"""FFmpeg-based vertical Shorts generation."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.editor.smart_crop import OpenCVFocusAnalyzer
from app.utils.process import run_command
from database.models import Clip, Video

logger = logging.getLogger(__name__)


class ShortsEditor:
    """Render 9:16 Shorts with subtitles, hook text, and audio normalization."""

    def __init__(self, focus_analyzer: OpenCVFocusAnalyzer | None = None) -> None:
        self.focus_analyzer = focus_analyzer or OpenCVFocusAnalyzer()

    async def render_clip(self, session: AsyncSession, clip: Clip) -> Path:
        """Render a vertical MP4 for a clip."""

        video = await session.get(Video, clip.video_id)
        if not video or not video.downloaded_path:
            raise ValueError(f"Clip {clip.id} does not have a downloaded source video")
        if not clip.subtitle_path:
            raise ValueError(f"Clip {clip.id} does not have subtitles")

        duration = max(1.0, clip.end_time - clip.start_time)
        output_path = settings.clips_dir / f"short_{clip.id}.mp4"
        focus_x = await asyncio.to_thread(
            self.focus_analyzer.estimate_focus_x,
            Path(video.downloaded_path),
            clip.start_time,
            clip.end_time,
        )
        video_filter = self._video_filter(
            subtitle_path=Path(clip.subtitle_path),
            hook_text=clip.hook_text or "",
            duration=duration,
            focus_x=focus_x,
        )
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-ss",
            f"{clip.start_time:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            video.downloaded_path,
            "-vf",
            video_filter,
            "-af",
            "highpass=f=70,acompressor=threshold=0.08:ratio=2.4:attack=6:release=120,loudnorm=I=-14:TP=-1.5:LRA=10",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            settings.video_preset,
            "-crf",
            str(settings.crf),
            "-c:a",
            "aac",
            "-b:a",
            settings.audio_bitrate,
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        await run_command(command, cwd=settings.project_root, timeout_seconds=None)
        clip.clip_path = str(output_path.resolve())
        clip.status = "generated"
        await session.flush()
        logger.info("Rendered clip %s to %s", clip.id, output_path)
        return output_path.resolve()

    def _video_filter(
        self,
        *,
        subtitle_path: Path,
        hook_text: str,
        duration: float,
        focus_x: float,
    ) -> str:
        fade_out_start = max(0.1, duration - 0.18)
        width = settings.shorts_width
        height = settings.shorts_height
        zoom_base = 1.055
        zoom_pulse = 0.018
        drift = 0.030
        focus_x = max(0.18, min(0.82, focus_x))
        filters = [
            (
                "scale="
                f"w='trunc({width}*({zoom_base}+{zoom_pulse}*sin(t*2.4))/2)*2':"
                f"h='trunc({height}*({zoom_base}+{zoom_pulse}*sin(t*2.4))/2)*2':"
                "force_original_aspect_ratio=increase:eval=frame"
            ),
            (
                f"crop={width}:{height}:"
                f"x='(iw-ow)*({focus_x:.3f}+{drift}*sin(t*0.9))':"
                "y='(ih-oh)/2'"
            ),
            "setsar=1",
            "eq=contrast=1.08:saturation=1.14:brightness=0.015",
            "unsharp=5:5:0.45",
            "fps=30",
            "fade=t=in:st=0:d=0.12",
            f"fade=t=out:st={fade_out_start:.2f}:d=0.18",
        ]

        if hook_text:
            hook_text = self._compact_hook(hook_text)
            filters.append(
                "drawtext="
                f"text='{self._escape_drawtext(hook_text)}':"
                "fontcolor=white:"
                "fontsize=58:"
                "box=1:"
                "boxcolor=black@0.50:"
                "boxborderw=20:"
                "x=(w-text_w)/2:"
                "y=150:"
                "shadowcolor=black@0.6:"
                "shadowx=2:"
                "shadowy=2"
            )

        filters.append(f"ass='{self._filter_path(subtitle_path)}'")
        return ",".join(filters)

    def _filter_path(self, path: Path) -> str:
        try:
            path = path.resolve().relative_to(settings.project_root)
        except ValueError:
            path = path.resolve()
        return path.as_posix().replace(":", r"\:").replace("'", r"\'")

    def _escape_drawtext(self, text: str) -> str:
        return (
            text.replace("\\", r"\\")
            .replace(":", r"\:")
            .replace("'", r"\'")
            .replace("%", r"\%")
            .replace("\n", " ")
        )[:120]

    def _compact_hook(self, text: str, max_chars: int = 30) -> str:
        words = text.replace("{", "").replace("}", "").replace("\n", " ").split()
        selected: list[str] = []
        for word in words:
            candidate = " ".join([*selected, word])
            if len(candidate) > max_chars:
                break
            selected.append(word)
        return " ".join(selected) or "Wait For This"
