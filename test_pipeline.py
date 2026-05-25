"""Focused end-to-end pipeline test for one YouTube URL.

This script is intentionally narrower than the production API. It exists to
debug the integration chain and produce one working `data/clips/final_short.mp4`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

import httpx
import yt_dlp

from app.captions.subtitles import SubtitleEngine
from app.clip_detector.service import ClipCandidate, ViralClipDetector
from app.config import settings
from app.editor.smart_crop import OpenCVFocusAnalyzer
from app.transcription.service import WhisperCppTranscriber
from app.utils.process import run_command

PROJECT_ROOT = Path(__file__).resolve().parent
FINAL_SHORT = settings.clips_dir / "final_short.mp4"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin?download=true"
)


@dataclass(frozen=True)
class DownloadedVideo:
    """Downloaded media metadata."""

    youtube_id: str
    title: str
    path: Path


@contextmanager
def stage_logger(name: str):
    """Log start, completion time, and errors for one stage."""

    start = time.perf_counter()
    logging.info("[%s] Started", name)
    try:
        yield
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logging.exception("[%s] Failed after %.2fs: %s", name, elapsed, exc)
        raise
    else:
        elapsed = time.perf_counter() - start
        logging.info("[%s] Completed in %.2fs", name, elapsed)


def setup_logging() -> None:
    """Configure console logging for the test runner."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )


def ensure_runtime_paths() -> None:
    """Create output folders and prepend venv Scripts to PATH on Windows."""

    settings.ensure_directories()
    scripts_dir = PROJECT_ROOT / ".venv" / "Scripts"
    if scripts_dir.exists():
        os.environ["PATH"] = f"{scripts_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def resolve_ffmpeg() -> str:
    """Return a working FFmpeg executable path."""

    configured = shutil.which(settings.ffmpeg_binary)
    if configured:
        logging.info("[FFmpeg] Using system FFmpeg: %s", configured)
        return configured

    try:
        import imageio_ffmpeg

        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        shim_dir = settings.resolve_path(settings.temp_dir) / "ffmpeg-bin"
        shim_dir.mkdir(parents=True, exist_ok=True)
        shim_path = shim_dir / "ffmpeg.exe"
        source_path = Path(ffmpeg_path)
        if not shim_path.exists() or shim_path.stat().st_size != source_path.stat().st_size:
            shutil.copy2(source_path, shim_path)
        os.environ["PATH"] = f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        logging.info("[FFmpeg] Using bundled imageio-ffmpeg shim: %s", shim_path)
        return str(shim_path)
    except Exception as exc:
        raise RuntimeError("FFmpeg not found and imageio-ffmpeg fallback failed") from exc


def resolve_whisper_binary() -> str:
    """Return a working whisper.cpp executable path."""

    candidates = [
        settings.whisper_cpp_binary,
        "whisper-cpp",
        "whisper-cpp.exe",
        "whisper-cli",
        "whisper-cli.exe",
    ]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            logging.info("[Whisper] Using whisper.cpp binary: %s", resolved)
            return resolved
    raise FileNotFoundError(
        "whisper.cpp binary not found. Install with: .\\.venv\\Scripts\\python.exe -m pip install whisper.cpp-cli"
    )


def ensure_model(download_model: bool) -> Path:
    """Ensure a whisper.cpp model exists locally."""

    model_path = settings.resolve_path(settings.whisper_model_path)
    if model_path.exists() and model_path.stat().st_size > 1024:
        logging.info("[Whisper] Using model: %s", model_path)
        return model_path

    if not download_model:
        raise FileNotFoundError(
            f"Whisper model missing at {model_path}. Re-run with --download-model."
        )

    model_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info("[Whisper] Downloading tiny English model to %s", model_path)
    urlretrieve(DEFAULT_MODEL_URL, model_path)
    if model_path.stat().st_size <= 1024:
        raise RuntimeError(f"Downloaded model is unexpectedly small: {model_path}")
    return model_path


async def validate_command(command: list[str], name: str) -> None:
    """Run a lightweight command validation."""

    with stage_logger(name):
        result = await run_command(command, cwd=PROJECT_ROOT, timeout_seconds=30)
        tail = (result.stdout or result.stderr).strip().splitlines()
        if tail:
            logging.info("[%s] %s", name, tail[0][:180])


async def validate_ollama() -> bool:
    """Check whether Ollama is reachable."""

    with stage_logger("Ollama"):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
            models = response.json().get("models", [])
            logging.info("[Ollama] Connected. Installed models: %s", len(models))
            return True
        except Exception as exc:
            logging.warning("[Ollama] Unavailable; clip detection will use local fallback: %s", exc)
            return False


def download_video(url: str, ffmpeg_path: str, max_download_seconds: int | None) -> DownloadedVideo:
    """Download one YouTube video with yt-dlp's Python API."""

    output_template = str(settings.videos_dir / "%(id)s.%(ext)s")
    ydl_opts: dict[str, Any] = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "ffmpeg_location": str(ffmpeg_path),
    }
    if max_download_seconds:
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
            None,
            [(0, max_download_seconds)],
        )
        ydl_opts["force_keyframes_at_cuts"] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    youtube_id = str(info.get("id") or "download")
    title = str(info.get("title") or youtube_id)
    candidates = sorted(settings.videos_dir.glob(f"{youtube_id}.*"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"yt-dlp finished but no media file was found for {youtube_id}")
    output_path = candidates[-1].resolve()
    logging.info("[Downloader] Download complete: %s", output_path)
    return DownloadedVideo(youtube_id=youtube_id, title=title, path=output_path)


async def extract_audio(video: DownloadedVideo, ffmpeg_path: str) -> Path:
    """Extract whisper.cpp-compatible WAV audio."""

    output_path = settings.audio_dir / f"{video.youtube_id}.wav"
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video.path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    await run_command(command, cwd=PROJECT_ROOT, timeout_seconds=None)
    logging.info("[Audio] Output path: %s", output_path.resolve())
    return output_path.resolve()


async def transcribe(
    *,
    audio_path: Path,
    youtube_id: str,
    whisper_binary: str,
    model_path: Path,
) -> Path:
    """Run whisper.cpp and normalize transcript JSON."""

    output_stem = settings.transcripts_dir / youtube_id
    command = [
        whisper_binary,
        "-m",
        str(model_path),
        "-f",
        str(audio_path),
        "-oj",
        "-of",
        str(output_stem),
        "-t",
        str(settings.whisper_threads),
        "-l",
        settings.whisper_language,
    ]
    await run_command(command, cwd=PROJECT_ROOT, timeout_seconds=None)
    raw_json = output_stem.with_suffix(".json")
    if not raw_json.exists():
        raise FileNotFoundError(f"whisper.cpp did not create JSON output: {raw_json}")

    normalizer = WhisperCppTranscriber()
    normalized = normalizer.normalize_whisper_json(raw_json, youtube_id, str(audio_path))
    normalized_path = settings.transcripts_dir / f"{youtube_id}.normalized.json"
    normalized_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    logging.info("[Whisper] Transcript generated: %s", normalized_path.resolve())
    return normalized_path.resolve()


def transcript_excerpt(transcript_path: Path, start: float, end: float) -> str:
    """Return transcript text inside a time range."""

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    return " ".join(
        segment["text"]
        for segment in transcript.get("segments", [])
        if float(segment["end"]) >= start and float(segment["start"]) <= end
    )


async def detect_clip(transcript_path: Path) -> ClipCandidate:
    """Detect the best clip candidate."""

    detector = ViralClipDetector()
    candidates = await detector.detect(transcript_path)
    if not candidates:
        raise RuntimeError("No viral clip candidates found")
    best = candidates[0]
    logging.info(
        "[ClipDetector] Viral segments found: %s; selected %.2fs-%.2fs score %.2f",
        len(candidates),
        best.start_time,
        best.end_time,
        best.viral_score,
    )
    return best


def add_hook_to_ass(ass_path: Path, hook_text: str) -> None:
    """Insert hook text into the ASS subtitle file to avoid drawtext font issues."""

    if not hook_text:
        hook_text = "Watch This"
    content = ass_path.read_text(encoding="utf-8")
    safe_hook = compact_hook(hook_text)
    event = (
        "Dialogue: 1,0:00:00.00,0:00:03.20,Default,,0,0,0,,"
        r"{\an8\fs58\fscx100\fscy100\bord7\shad2\c&H00D7FF&}"
        + safe_hook
        + "\n"
    )
    ass_path.write_text(content + event, encoding="utf-8")


def compact_hook(text: str, max_chars: int = 28) -> str:
    """Return a short hook that fits a 9:16 frame."""

    cleaned = re.sub(r"\s+", " ", text.replace("{", "").replace("}", "")).strip()
    if not cleaned:
        return "Watch This"
    words = cleaned.split()
    selected: list[str] = []
    for word in words:
        candidate = " ".join([*selected, word])
        if len(candidate) > max_chars:
            break
        selected.append(word)
    return (" ".join(selected) or cleaned[:max_chars]).strip()


def retention_video_filter(subtitle_path: Path, focus_x: float) -> str:
    """Build the high-retention vertical render filter."""

    width = settings.shorts_width
    height = settings.shorts_height
    focus_x = max(0.18, min(0.82, focus_x))
    zoom_base = 1.055
    zoom_pulse = 0.018
    drift = 0.030
    return ",".join(
        [
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
            f"ass='{escape_filter_path(subtitle_path)}'",
            "fps=30",
        ]
    )


def escape_filter_path(path: Path) -> str:
    """Escape a Windows path for FFmpeg filter arguments."""

    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


async def render_short(
    *,
    video: DownloadedVideo,
    candidate: ClipCandidate,
    transcript_path: Path,
    ffmpeg_path: str,
) -> Path:
    """Generate subtitles and render final vertical MP4."""

    subtitle_engine = SubtitleEngine()
    subtitle_path = subtitle_engine.generate_for_clip(
        transcript_path=transcript_path,
        clip_id=999999,
        start_time=candidate.start_time,
        end_time=candidate.end_time,
    )
    duration = max(1.0, candidate.end_time - candidate.start_time)
    add_hook_to_ass(subtitle_path, candidate.hook_text)
    logging.info("[Subtitles] Subtitle file generated: %s", subtitle_path)

    focus_x = OpenCVFocusAnalyzer().estimate_focus_x(
        video.path,
        candidate.start_time,
        candidate.end_time,
    )
    video_filter = retention_video_filter(subtitle_path, focus_x)
    command = [
        ffmpeg_path,
        "-y",
        "-ss",
        f"{candidate.start_time:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(video.path),
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
        str(FINAL_SHORT),
    ]
    await run_command(command, cwd=PROJECT_ROOT, timeout_seconds=None)
    logging.info("[Renderer] Final MP4 generated: %s", FINAL_SHORT.resolve())
    return FINAL_SHORT.resolve()


def validate_output(video_path: Path) -> None:
    """Validate final output dimensions with OpenCV."""

    import cv2

    capture = cv2.VideoCapture(str(video_path))
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"Could not read rendered video: {video_path}")
    height, width = frame.shape[:2]
    if (width, height) != (settings.shorts_width, settings.shorts_height):
        raise RuntimeError(f"Expected 1080x1920 output, got {width}x{height}")
    logging.info("[Validator] Output is vertical %sx%s with readable frames", width, height)


async def run_pipeline(args: argparse.Namespace) -> Path:
    """Execute the full test pipeline."""

    ensure_runtime_paths()

    with stage_logger("Environment"):
        logging.info("[Environment] Python: %s", sys.version.split()[0])
        ffmpeg_path = resolve_ffmpeg()
        whisper_binary = resolve_whisper_binary()
        model_path = ensure_model(args.download_model)

    await validate_command([ffmpeg_path, "-version"], "FFmpeg")
    await validate_command([whisper_binary, "--help"], "Whisper")
    await validate_command([sys.executable, "-m", "yt_dlp", "--version"], "yt-dlp")
    await validate_ollama()

    with stage_logger("Downloader"):
        video = download_video(args.url, ffmpeg_path, args.max_download_seconds)

    with stage_logger("Audio"):
        audio_path = await extract_audio(video, ffmpeg_path)

    with stage_logger("Whisper"):
        transcript_path = await transcribe(
            audio_path=audio_path,
            youtube_id=video.youtube_id,
            whisper_binary=whisper_binary,
            model_path=model_path,
        )

    with stage_logger("ClipDetector"):
        candidate = await detect_clip(transcript_path)
        if not candidate.hook_text:
            excerpt = transcript_excerpt(transcript_path, candidate.start_time, candidate.end_time)
            hook = re.sub(r"\s+", " ", excerpt).strip()[:60] or "Watch This"
            candidate = ClipCandidate(
                candidate.start_time,
                candidate.end_time,
                candidate.viral_score,
                candidate.reason,
                hook,
            )

    with stage_logger("Renderer"):
        final_path = await render_short(
            video=video,
            candidate=candidate,
            transcript_path=transcript_path,
            ffmpeg_path=ffmpeg_path,
        )

    with stage_logger("Validator"):
        validate_output(final_path)

    return final_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one end-to-end Shorts generation test.")
    parser.add_argument("url", help="YouTube URL to process. Use content you own or have permission to repurpose.")
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Download ggml-tiny.en.bin if the configured whisper.cpp model is missing.",
    )
    parser.add_argument(
        "--max-download-seconds",
        type=int,
        default=None,
        help="Optional first-N-seconds download limit for fast debugging.",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()
    try:
        final_path = asyncio.run(run_pipeline(args))
    except Exception:
        logging.error("[Pipeline] Stopped gracefully because a required stage failed.")
        return 1
    logging.info("[Pipeline] SUCCESS: %s", final_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
