"""Dead-zone detection for slow, silent, or low-emotion Shorts candidates."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

EMOTION_TERMS = {
    "love", "hate", "afraid", "scared", "danger", "wrong", "beautiful", "insane",
    "crazy", "shock", "wild", "hurt", "angry", "excited", "risk", "survive",
}
FILLER_TERMS = {"um", "uh", "like", "you know", "kind of", "sort of", "basically"}


@dataclass(frozen=True)
class DeadZoneReport:
    """Watchability risk report for one clip window."""

    dead_zone_score: float
    silence_score: float
    low_pacing_score: float
    low_emotion_score: float
    low_motion_score: float | None
    filler_score: float
    flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeadZoneDetector:
    """Detect dead zones before a Short is approved for upload."""

    def analyze_transcript_file(self, transcript_path: str | Path, start_time: float, end_time: float) -> DeadZoneReport:
        path = Path(transcript_path)
        if not path.exists():
            return DeadZoneReport(65, 60, 60, 60, None, 0, ["missing transcript"])
        data = json.loads(path.read_text(encoding="utf-8"))
        return self.analyze_segments(data.get("segments", []), start_time, end_time)

    def analyze_segments(
        self,
        segments: list[dict[str, Any]],
        start_time: float,
        end_time: float,
    ) -> DeadZoneReport:
        selected = [
            item for item in segments
            if float(item.get("end", 0)) >= start_time and float(item.get("start", 0)) <= end_time
        ]
        duration = max(1.0, end_time - start_time)
        text = " ".join(str(item.get("text", "")) for item in selected)
        words = re.findall(r"[a-z0-9']+", text.lower())
        words_per_second = len(words) / duration
        silence_gaps = self._silence_gaps(selected, start_time, end_time)
        silence_seconds = sum(silence_gaps)
        silence_score = min(100.0, (silence_seconds / duration) * 160)
        low_pacing_score = max(0.0, min(100.0, (2.2 - words_per_second) * 38)) if words_per_second < 2.2 else 0.0
        emotion_hits = sum(1 for word in words if word in EMOTION_TERMS)
        low_emotion_score = max(0.0, 76 - (emotion_hits * 18))
        filler_hits = sum(text.lower().count(term) for term in FILLER_TERMS)
        filler_score = min(100.0, filler_hits * 12)

        flags: list[str] = []
        if silence_score >= 28:
            flags.append("silence gaps")
        if low_pacing_score >= 28:
            flags.append("slow pacing")
        if low_emotion_score >= 58:
            flags.append("low emotion")
        if filler_score >= 24:
            flags.append("filler-heavy speech")

        dead_zone_score = (
            silence_score * 0.30
            + low_pacing_score * 0.30
            + low_emotion_score * 0.24
            + filler_score * 0.16
        )
        return DeadZoneReport(
            dead_zone_score=round(max(0.0, min(100.0, dead_zone_score)), 1),
            silence_score=round(silence_score, 1),
            low_pacing_score=round(low_pacing_score, 1),
            low_emotion_score=round(low_emotion_score, 1),
            low_motion_score=None,
            filler_score=round(filler_score, 1),
            flags=flags,
        )

    def _silence_gaps(
        self,
        segments: list[dict[str, Any]],
        start_time: float,
        end_time: float,
    ) -> list[float]:
        if not segments:
            return [end_time - start_time]
        ordered = sorted(segments, key=lambda item: float(item.get("start", 0)))
        gaps: list[float] = []
        cursor = start_time
        for segment in ordered:
            segment_start = max(start_time, float(segment.get("start", start_time)))
            if segment_start - cursor > 0.65:
                gaps.append(segment_start - cursor)
            cursor = max(cursor, min(end_time, float(segment.get("end", cursor))))
        if end_time - cursor > 0.65:
            gaps.append(end_time - cursor)
        return gaps
