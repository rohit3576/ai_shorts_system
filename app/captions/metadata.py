"""Ollama-based title, description, hashtag, and hook generation."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.clip_detector.service import ClipCandidate
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptionMetadata:
    """Generated Shorts metadata."""

    title: str
    description: str
    hashtags: list[str]
    hook_text: str


class CaptionGenerator:
    """Generate Shorts metadata with a local Ollama model."""

    async def generate(
        self,
        *,
        source_title: str,
        candidate: ClipCandidate,
        transcript_excerpt: str,
    ) -> CaptionMetadata:
        """Generate title, description, hashtags, and hook overlay text."""

        prompt = f"""
You are a retention-focused YouTube Shorts packaging editor. Create metadata for a Short.

Source video title: {source_title}
Clip timestamps: {candidate.start_time:.2f}-{candidate.end_time:.2f}
Why selected: {candidate.reason}
Transcript excerpt:
{transcript_excerpt[:2500]}

Return only JSON with:
{{
  "title": "Max 70 chars, curiosity-driven, specific, no clickbait lies",
  "description": "1-2 natural sentences with context and payoff tease",
  "hashtags": ["#shorts", "#topic", "#topic"],
  "hook_text": "2-5 urgent words for the first 2 seconds",
  "hook_type": "curiosity | danger | emotional | suspense"
}}

Create one of these hook types:
- curiosity: opens a specific unanswered question
- danger: points at risk or consequences
- emotional: names the human feeling or stakes
- suspense: makes the viewer wait for the reveal

Avoid generic hooks, repeated phrasing, and full sentences.
""".strip()
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.35, "num_ctx": 4096},
                    },
                )
                response.raise_for_status()
            data = self._parse_response(response.json().get("response", ""))
            return CaptionMetadata(
                title=str(data.get("title", "")).strip()[:90] or self._fallback_title(source_title),
                description=str(data.get("description", "")).strip()
                or "A standout moment from the full conversation.",
                hashtags=self._normalize_hashtags(data.get("hashtags")),
                hook_text=self._compact_hook(str(data.get("hook_text", "")).strip())
                or candidate.hook_text
                or "Watch This",
            )
        except Exception as exc:
            logger.warning("Caption generation failed, using fallback metadata: %s", exc)
            return CaptionMetadata(
                title=self._fallback_title(source_title),
                description="A high-signal moment clipped automatically from the source video.",
                hashtags=["#shorts", "#ai", "#viral"],
                hook_text=self._compact_hook(candidate.hook_text) or "Wait For This",
            )

    def _parse_response(self, response_text: str) -> dict:
        text = response_text.strip()
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            text = match.group(0) if match else text
        return json.loads(text)

    def _normalize_hashtags(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return ["#shorts"]
        hashtags = []
        for item in value:
            tag = str(item).strip()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag}"
            hashtags.append(tag.replace(" ", ""))
        if "#shorts" not in [tag.lower() for tag in hashtags]:
            hashtags.insert(0, "#shorts")
        return hashtags[:8]

    def _fallback_title(self, source_title: str) -> str:
        return f"{source_title[:58].rstrip()} #Shorts"

    def _compact_hook(self, text: str, max_chars: int = 30) -> str:
        cleaned = re.sub(r"\s+", " ", text.replace("{", "").replace("}", "")).strip()
        if not cleaned:
            return ""
        words = cleaned.split()
        selected: list[str] = []
        for word in words:
            candidate = " ".join([*selected, word])
            if len(candidate) > max_chars:
                break
            selected.append(word)
        return " ".join(selected) or cleaned[:max_chars]
