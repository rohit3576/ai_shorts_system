"""Ollama-powered viral clip detection."""

from __future__ import annotations

import json
import logging
import re
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClipCandidate:
    """Candidate viral moment returned by the detector."""

    start_time: float
    end_time: float
    viral_score: float
    reason: str
    hook_text: str
    hook_type: str = "curiosity"


class ViralClipDetector:
    """Detect and rank Shorts candidates from transcript segments."""

    async def detect(self, transcript_path: str | Path) -> list[ClipCandidate]:
        """Return ranked viral moments for a transcript."""

        transcript = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        segments = transcript.get("segments", [])
        if not segments:
            return []

        chunks = self._chunk_segments(segments)
        candidates: list[ClipCandidate] = []
        for chunk in chunks:
            try:
                candidates.extend(await self._ask_ollama(chunk))
            except Exception as exc:
                logger.warning("Ollama clip detection failed for chunk: %s", exc)

        if not candidates and settings.allow_heuristic_clip_fallback:
            candidates = self._heuristic_candidates(segments)
        elif not candidates:
            raise RuntimeError("LLM clip detection returned no candidates and heuristic fallback is disabled.")

        ranked = self._diversify_candidates(self._rank_candidates(candidates, segments))
        filtered = [
            item
            for item in ranked
            if item.viral_score >= settings.viral_score_threshold
            and settings.min_clip_seconds <= item.end_time - item.start_time <= settings.max_clip_seconds
        ]
        if not filtered:
            filtered = ranked[: settings.max_clips_per_video]
        return filtered[: settings.max_clips_per_video]

    async def _ask_ollama(self, segments: list[dict[str, Any]]) -> list[ClipCandidate]:
        prompt = self._build_prompt(segments)
        last_error: Exception | None = None
        for attempt in range(1, settings.retry_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
                    response = await client.post(
                        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                        json={
                            "model": settings.ollama_model,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json",
                            "options": {"temperature": 0.15, "num_ctx": 8192},
                        },
                    )
                    response.raise_for_status()
                payload = response.json()
                return self._parse_candidates(payload.get("response", ""))
            except Exception as exc:
                last_error = exc
                if attempt < settings.retry_attempts:
                    await asyncio.sleep(settings.retry_backoff_seconds * attempt)
        assert last_error is not None
        raise last_error

    def _build_prompt(self, segments: list[dict[str, Any]]) -> str:
        transcript_lines = "\n".join(
            f"[{item['start']:.2f}-{item['end']:.2f}] {item['text']}" for item in segments
        )
        return f"""
You are an expert short-form retention editor. Analyze this timestamped transcript and find moments
that could become high-retention YouTube Shorts or TikTok clips.

Score clips using these factors:
- immediate hook in the first 2 seconds
- suspense, unresolved tension, or danger
- conflict, contradiction, stakes, or social pressure
- surprise, humor, shock, or reversal
- emotional intensity and fast pacing
- curiosity gap that makes viewers wait for the payoff
- clear payoff before the clip ends

Rules:
- Return only valid JSON.
- Choose clips between {settings.min_clip_seconds} and {settings.max_clip_seconds} seconds.
- Prefer complete thoughts with a strong opening hook and payoff.
- Do not pick intros, sponsor reads, or generic setup unless the payoff is inside the clip.
- Use exact transcript timestamps.
- Avoid slow context unless the next sentence creates tension or curiosity.
- hook_text must be 2-5 words, punchy, and safe to show in large text.
- hook_type must be one of: curiosity, danger, emotional, suspense.
- Return varied hook_type values and varied pacing; do not repeat the same opening pattern.

JSON schema:
{{
  "clips": [
    {{
      "start": 12.3,
      "end": 52.0,
      "score": 0.91,
      "reason": "Retention reason: hook, tension, payoff",
      "hook_text": "Wait For This",
      "hook_type": "suspense"
    }}
  ]
}}

Transcript:
{transcript_lines[:14000]}
""".strip()

    def _parse_candidates(self, response_text: str) -> list[ClipCandidate]:
        text = response_text.strip().strip("`")
        text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            text = match.group(0) if match else text
        data = json.loads(text)
        if isinstance(data, list):
            data = {"clips": data}
        candidates: list[ClipCandidate] = []
        for item in data.get("clips", []):
            start = max(0.0, float(item["start"]))
            end = max(start + 1, float(item["end"]))
            duration = end - start
            if duration < settings.min_clip_seconds:
                end = start + settings.min_clip_seconds
                duration = end - start
            if duration > settings.max_clip_seconds:
                end = start + settings.max_clip_seconds
            candidates.append(
                ClipCandidate(
                    start_time=start,
                    end_time=end,
                    viral_score=max(0.0, min(1.0, float(item.get("score", 0.0)))),
                    reason=str(item.get("reason", "")).strip(),
                    hook_text=self._compact_hook(str(item.get("hook_text", "")).strip()),
                    hook_type=self._normalize_hook_type(str(item.get("hook_type", "")).strip()),
                )
            )
        return candidates

    def _chunk_segments(
        self,
        segments: list[dict[str, Any]],
        max_chars: int = 10000,
    ) -> list[list[dict[str, Any]]]:
        chunks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        for segment in segments:
            line_length = len(segment.get("text", "")) + 32
            if current and current_chars + line_length > max_chars:
                chunks.append(current)
                current = []
                current_chars = 0
            current.append(segment)
            current_chars += line_length
        if current:
            chunks.append(current)
        return chunks

    def _heuristic_candidates(self, segments: list[dict[str, Any]]) -> list[ClipCandidate]:
        """Fallback detector used only when Ollama is unavailable."""

        windows: list[ClipCandidate] = []
        for start_index, segment in enumerate(segments):
            start = float(segment["start"])
            end = start
            texts: list[str] = []
            cursor = start_index
            while cursor < len(segments) and end - start < settings.max_clip_seconds:
                texts.append(str(segments[cursor].get("text", "")))
                end = float(segments[cursor]["end"])
                duration = end - start
                if duration >= settings.min_clip_seconds:
                    text = " ".join(texts)
                    score, reason = self._score_window(text, duration, is_first=start_index == 0)
                    hook_text = self._make_hook(text, reason)
                    windows.append(
                        ClipCandidate(
                            start_time=start,
                            end_time=end,
                            viral_score=score,
                            reason=reason,
                            hook_text=hook_text,
                            hook_type=self._infer_hook_type(text, reason),
                        )
                    )
                cursor += 1

        if not windows and segments:
            start = float(segments[0]["start"])
            end = float(segments[-1]["end"])
            text = " ".join(str(segment.get("text", "")) for segment in segments)
            score, reason = self._score_window(text, max(1.0, end - start), is_first=True)
            windows.append(
                ClipCandidate(
                    start_time=start,
                    end_time=end,
                    viral_score=score,
                    reason=reason,
                    hook_text=self._make_hook(text, reason),
                    hook_type=self._infer_hook_type(text, reason),
                )
            )
        return windows

    def _rank_candidates(
        self,
        candidates: list[ClipCandidate],
        segments: list[dict[str, Any]],
    ) -> list[ClipCandidate]:
        """Blend model score with local retention heuristics before ranking."""

        ranked: list[ClipCandidate] = []
        for candidate in candidates:
            text = self._excerpt(segments, candidate.start_time, candidate.end_time)
            duration = max(1.0, candidate.end_time - candidate.start_time)
            quality_score, quality_reason = self._score_window(
                text,
                duration,
                is_first=candidate.start_time <= 1.0,
            )
            blended_score = min(1.0, candidate.viral_score * 0.72 + quality_score * 0.28)
            reason = candidate.reason or quality_reason
            if quality_reason and quality_reason not in reason:
                reason = f"{reason} Quality signals: {quality_reason}".strip()
            ranked.append(
                ClipCandidate(
                    start_time=candidate.start_time,
                    end_time=candidate.end_time,
                    viral_score=blended_score,
                    reason=reason,
                    hook_text=self._compact_hook(candidate.hook_text or self._make_hook(text, reason)),
                    hook_type=self._normalize_hook_type(candidate.hook_type) or self._infer_hook_type(text, reason),
                )
            )
        return sorted(ranked, key=lambda item: item.viral_score, reverse=True)

    def _diversify_candidates(self, candidates: list[ClipCandidate]) -> list[ClipCandidate]:
        """Prefer diverse clip windows, hook types, and pacing profiles."""

        selected: list[ClipCandidate] = []
        hook_counts: dict[str, int] = {}
        pacing_counts: dict[str, int] = {}
        for candidate in candidates:
            if any(self._overlap_ratio(candidate, existing) >= 0.28 for existing in selected):
                continue
            hook_type = self._normalize_hook_type(candidate.hook_type)
            pacing = self._pacing_bucket(candidate)
            if hook_counts.get(hook_type, 0) >= 2:
                continue
            if pacing_counts.get(pacing, 0) >= 2:
                continue
            selected.append(candidate)
            hook_counts[hook_type] = hook_counts.get(hook_type, 0) + 1
            pacing_counts[pacing] = pacing_counts.get(pacing, 0) + 1
        return selected

    def _overlap_ratio(self, first: ClipCandidate, second: ClipCandidate) -> float:
        overlap = max(0.0, min(first.end_time, second.end_time) - max(first.start_time, second.start_time))
        shorter = max(1.0, min(first.end_time - first.start_time, second.end_time - second.start_time))
        return overlap / shorter

    def _score_window(self, text: str, duration: float, *, is_first: bool) -> tuple[float, str]:
        """Score transcript text for retention qualities."""

        lowered = text.lower()
        categories = {
            "curiosity": [
                "why",
                "how",
                "secret",
                "truth",
                "nobody",
                "what happens",
                "watch",
                "turns out",
            ],
            "conflict": ["wrong", "fight", "against", "problem", "mistake", "but", "however", "can't"],
            "danger": ["danger", "risk", "crash", "dead", "kill", "scared", "afraid", "trap"],
            "surprise": ["suddenly", "crazy", "insane", "shocking", "unexpected", "surprise", "wild"],
            "emotion": ["love", "hate", "angry", "cry", "terrified", "excited", "beautiful", "cool"],
            "payoff": ["because", "so", "then", "that's why", "finally", "actually"],
        }
        hits: list[str] = []
        score = 0.38
        for category, keywords in categories.items():
            count = sum(1 for keyword in keywords if keyword in lowered)
            if count:
                hits.append(category)
                score += min(0.12, 0.045 * count)

        score += 0.08 if "?" in text else 0
        score += 0.06 if "!" in text else 0
        score += 0.04 if is_first else 0

        words = re.findall(r"[A-Za-z0-9']+", text)
        words_per_second = len(words) / max(1.0, duration)
        if 2.2 <= words_per_second <= 4.2:
            score += 0.08
            hits.append("tight pacing")
        elif words_per_second < 1.3:
            score -= 0.08

        first_words = " ".join(words[:10]).lower()
        if any(keyword in first_words for keyword in ["wait", "why", "this", "but", "so", "watch"]):
            score += 0.05
            hits.append("fast open")

        if duration > settings.max_clip_seconds * 0.9:
            score -= 0.03

        reason = ", ".join(dict.fromkeys(hits)) or "clear self-contained moment"
        return max(0.35, min(0.93, score)), reason

    def _excerpt(
        self,
        segments: list[dict[str, Any]],
        start_time: float,
        end_time: float,
    ) -> str:
        return " ".join(
            str(segment.get("text", ""))
            for segment in segments
            if float(segment["end"]) >= start_time and float(segment["start"]) <= end_time
        )

    def _make_hook(self, text: str, reason: str) -> str:
        lowered = f"{text} {reason}".lower()
        if any(word in lowered for word in ["danger", "risk", "scared", "crash", "trap"]):
            return "This Gets Risky"
        if any(word in lowered for word in ["wrong", "mistake", "problem", "but", "however"]):
            return "I Was Wrong"
        if any(word in lowered for word in ["secret", "truth", "nobody", "why"]):
            return "The Shortcut Is Hidden"
        if any(word in lowered for word in ["crazy", "insane", "shocking", "unexpected", "surprise"]):
            return "Wait For It"
        if any(word in lowered for word in ["automate", "automation", "ai", "build", "coding", "workflow", "hours"]):
            return "This Saved Hours"
        if any(word in lowered for word in ["cool", "beautiful", "excited", "love"]):
            return "This Is Wild"
        return "Watch The Payoff"

    def _normalize_hook_type(self, value: str) -> str:
        normalized = value.strip().lower().replace("fear", "danger")
        if normalized in {"curiosity", "danger", "emotional", "suspense"}:
            return normalized
        return "curiosity"

    def _infer_hook_type(self, text: str, reason: str) -> str:
        lowered = f"{text} {reason}".lower()
        if any(word in lowered for word in ["danger", "risk", "crash", "trap", "survive", "kill"]):
            return "danger"
        if any(word in lowered for word in ["hurt", "cry", "love", "hate", "angry", "beautiful"]):
            return "emotional"
        if any(word in lowered for word in ["wait", "then", "suddenly", "payoff", "ending"]):
            return "suspense"
        return "curiosity"

    def _pacing_bucket(self, candidate: ClipCandidate) -> str:
        duration = max(1.0, candidate.end_time - candidate.start_time)
        if duration < 22:
            return "fast"
        if duration > 34:
            return "slow_build"
        return "mid"

    def _compact_hook(self, text: str, max_chars: int = 30) -> str:
        cleaned = re.sub(r"\s+", " ", text.replace("{", "").replace("}", "")).strip()
        if not cleaned:
            return "Wait For This"
        words = cleaned.split()
        selected: list[str] = []
        for word in words:
            candidate = " ".join([*selected, word])
            if len(candidate) > max_chars:
                break
            selected.append(word)
        return " ".join(selected) or cleaned[:max_chars]
