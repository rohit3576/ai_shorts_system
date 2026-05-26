"""ASS subtitle generation for TikTok-style burned captions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import settings


def ass_time(seconds: float) -> str:
    """Convert seconds to ASS H:MM:SS.cc format."""

    seconds = max(0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centis:02d}"


def ass_escape(text: str) -> str:
    """Escape user text for ASS dialogue lines."""

    return text.replace("{", "").replace("}", "").replace("\n", " ").strip()


POWER_WORDS = {
    "wait",
    "secret",
    "wrong",
    "never",
    "why",
    "how",
    "but",
    "danger",
    "risk",
    "crazy",
    "insane",
    "shocking",
    "surprise",
    "truth",
    "cool",
    "really",
    "actually",
    "finally",
    "nobody",
    "ai",
    "automate",
    "automated",
    "coding",
    "build",
    "built",
    "hours",
    "shortcut",
    "workflow",
}


def is_power_word(text: str) -> bool:
    """Return true when a token should receive visual emphasis."""

    cleaned = re.sub(r"[^A-Za-z0-9']", "", text).lower()
    return cleaned in POWER_WORDS or len(cleaned) >= 9


class SubtitleEngine:
    """Generate animated ASS subtitles from timestamped transcripts."""

    def generate_for_clip(
        self,
        *,
        transcript_path: str | Path,
        clip_id: int,
        start_time: float,
        end_time: float,
    ) -> Path:
        """Create an ASS subtitle file for a clip."""

        transcript = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        words = self._collect_words(transcript.get("segments", []), start_time, end_time)
        output_path = settings.clips_dir / f"clip_{clip_id}.ass"
        output_path.write_text(self._render_ass(words, end_time - start_time), encoding="utf-8")
        return output_path.resolve()

    def _collect_words(
        self,
        segments: list[dict[str, Any]],
        start_time: float,
        end_time: float,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for segment in segments:
            seg_start = float(segment["start"])
            seg_end = float(segment["end"])
            if seg_end < start_time or seg_start > end_time:
                continue

            if segment.get("words"):
                for word in segment["words"]:
                    word_start = float(word["start"])
                    word_end = float(word["end"])
                    if start_time <= word_start < end_time:
                        collected.append(
                            {
                                "start": max(0.0, word_start - start_time),
                                "end": max(word_start + 0.05, min(end_time, word_end)) - start_time,
                                "text": word["text"],
                            }
                        )
                continue

            tokens = re.findall(r"[\w']+|[^\w\s]", segment.get("text", ""), flags=re.UNICODE)
            if not tokens:
                continue
            visible_start = max(seg_start, start_time)
            visible_end = min(seg_end, end_time)
            duration = max(0.3, visible_end - visible_start)
            step = duration / len(tokens)
            for index, token in enumerate(tokens):
                collected.append(
                    {
                        "start": visible_start - start_time + step * index,
                        "end": visible_start - start_time + step * (index + 1),
                        "text": token,
                    }
                )
        return collected

    def _render_ass(self, words: list[dict[str, Any]], duration: float) -> str:
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {settings.shorts_width}
PlayResY: {settings.shorts_height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,70,&H00FFFFFF,&H0000D7FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,7,2,2,90,90,300,1
Style: Punch,Arial Black,80,&H0000D7FF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,8,3,2,86,86,296,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        if not words:
            return header

        lines: list[str] = []
        for index, word in enumerate(words):
            start = max(0.0, float(word["start"]))
            if start >= duration:
                continue
            end = min(duration, max(start + 0.18, float(word["end"])))
            if end <= start:
                continue
            window = self._caption_window(words, index)
            rendered_tokens: list[str] = []
            for token in window:
                token_text = ass_escape(str(token["text"]))
                if not token_text:
                    continue
                if token is word:
                    color = r"\c&H00FFFF00&" if is_power_word(token_text) else r"\c&H0000D7FF&"
                    rendered_tokens.append(
                        "{"
                        + color
                        + r"\bord8\shad3\t(0,100,\fscx122\fscy122)"
                        + "}"
                        + token_text.upper()
                        + r"{\r}"
                    )
                elif is_power_word(token_text):
                    rendered_tokens.append(r"{\c&H0000D7FF&}" + token_text.upper() + r"{\r}")
                else:
                    rendered_tokens.append(token_text)
            caption_text = self._join_tokens(rendered_tokens)
            style = "Punch" if is_power_word(str(word["text"])) else "Default"
            text = r"{\fad(20,70)\an2}" + caption_text
            lines.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}"
            )
        return header + "\n".join(lines) + "\n"

    def _caption_window(self, words: list[dict[str, Any]], active_index: int) -> list[dict[str, Any]]:
        """Keep captions short enough for fast scanning."""

        window_start = max(0, active_index - 1)
        window = words[window_start : min(len(words), window_start + 3)]
        total_chars = sum(len(str(item.get("text", ""))) for item in window)
        if total_chars > 28 and len(window) > 2:
            return window[:2]
        return window

    def _join_tokens(self, tokens: list[str]) -> str:
        """Join tokenized transcript text without awkward punctuation spacing."""

        output = ""
        for token in tokens:
            if not output:
                output = token
            elif re.match(r"^[,.;:!?)]", token):
                output += token
            elif token.startswith("'"):
                output += token
            else:
                output += " " + token
        return output
