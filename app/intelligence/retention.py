"""Local retention and virality scoring.

The scorer is intentionally heuristic-first so it remains free and laptop
friendly. Ollama can still influence upstream clip detection and metadata, but
this layer gives every rendered Short a consistent set of comparable signals.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clip_detector.service import ClipCandidate
from app.intelligence.deadzone import DeadZoneReport
from app.intelligence.hooks import HookVariant
from app.intelligence.profiles import persona_for_profile
from database.models import ChannelProfile, Clip, ClipIntelligence, Video


KEYWORDS: dict[str, list[str]] = {
    "curiosity": ["why", "how", "secret", "truth", "nobody", "what happens", "watch", "turns out", "unknown"],
    "emotion": ["love", "hate", "angry", "cry", "terrified", "excited", "beautiful", "fear", "shock"],
    "conflict": ["wrong", "fight", "against", "problem", "mistake", "but", "however", "can't", "never"],
    "danger": ["danger", "risk", "crash", "dead", "kill", "scared", "afraid", "trap", "survive"],
    "surprise": ["suddenly", "crazy", "insane", "shocking", "unexpected", "surprise", "wild", "actually"],
    "humor": ["funny", "laugh", "joke", "ridiculous", "awkward", "hilarious", "meme"],
    "payoff": ["because", "so", "then", "that's why", "finally", "actually", "revealed"],
}


@dataclass(frozen=True)
class RetentionScores:
    """Structured retention signals for one Short candidate."""

    retention_score: float
    viral_probability: float
    curiosity_score: float
    emotional_score: float
    pacing_score: float
    hook_strength_score: float
    conflict_score: float
    danger_score: float
    surprise_score: float
    humor_score: float
    quality_score: float
    dead_zone_score: float
    watchability_score: float
    hook_type: str
    decision: str
    reasons: list[str]


class RetentionScorer:
    """Score clips for retention before rendering or scheduling."""

    async def score_clip(
        self,
        session: AsyncSession,
        clip: Clip,
        *,
        transcript_excerpt: str,
        candidate: ClipCandidate | None = None,
        dead_zone_report: DeadZoneReport | None = None,
        hook_variants: list[HookVariant] | None = None,
    ) -> ClipIntelligence:
        """Create or update the intelligence row for a clip."""

        profile = await self._profile_for_clip(session, clip)
        duration = max(1.0, float(clip.end_time or 0) - float(clip.start_time or 0))
        scores = self.score_text(
            text=transcript_excerpt,
            duration=duration,
            model_score=float(candidate.viral_score if candidate else clip.viral_score or 0),
            hook_text=(candidate.hook_text if candidate else clip.hook_text) or "",
            profile=profile,
            dead_zone_score=dead_zone_report.dead_zone_score if dead_zone_report else 0.0,
        )

        existing = await session.scalar(select(ClipIntelligence).where(ClipIntelligence.clip_id == clip.id))
        intelligence = existing or ClipIntelligence(clip_id=clip.id)
        intelligence.channel_profile_id = profile.id if profile else None
        intelligence.retention_score = scores.retention_score
        intelligence.viral_probability = scores.viral_probability
        intelligence.curiosity_score = scores.curiosity_score
        intelligence.emotional_score = scores.emotional_score
        intelligence.pacing_score = scores.pacing_score
        intelligence.hook_strength_score = scores.hook_strength_score
        intelligence.conflict_score = scores.conflict_score
        intelligence.danger_score = scores.danger_score
        intelligence.surprise_score = scores.surprise_score
        intelligence.humor_score = scores.humor_score
        intelligence.quality_score = scores.quality_score
        intelligence.hook_type = scores.hook_type
        intelligence.decision = scores.decision
        intelligence.reasons_json = scores.reasons
        intelligence.metadata_json = {
            "duration": duration,
            "profile_niche": profile.niche_type if profile else "general",
            "persona": persona_for_profile(profile).__dict__,
            "dead_zone": dead_zone_report.to_dict() if dead_zone_report else None,
            "hook_variants": [item.__dict__ for item in hook_variants or []],
            "watchability_score": scores.watchability_score,
            "source": "local_retention_scorer",
        }
        if not existing:
            session.add(intelligence)

        metadata = dict(clip.metadata_json or {})
        metadata.update(
            {
                "retention_score": scores.retention_score,
                "viral_probability": scores.viral_probability,
                "curiosity_score": scores.curiosity_score,
                "emotional_score": scores.emotional_score,
                "pacing_score": scores.pacing_score,
                "hook_strength_score": scores.hook_strength_score,
                "conflict_score": scores.conflict_score,
                "danger_score": scores.danger_score,
                "surprise_score": scores.surprise_score,
                "humor_score": scores.humor_score,
                "hook_type": scores.hook_type,
                "dead_zone_score": scores.dead_zone_score,
                "watchability_score": scores.watchability_score,
                "dead_zone": dead_zone_report.to_dict() if dead_zone_report else None,
                "retention_decision": scores.decision,
            }
        )
        clip.metadata_json = metadata
        await session.flush()
        return intelligence

    def score_text(
        self,
        *,
        text: str,
        duration: float,
        model_score: float,
        hook_text: str,
        profile: ChannelProfile | None = None,
        dead_zone_score: float = 0.0,
    ) -> RetentionScores:
        """Score a transcript excerpt without touching the database."""

        lowered = text.lower()
        words = re.findall(r"[a-z0-9']+", lowered)
        words_per_second = len(words) / max(1.0, duration)
        category_scores = {
            key: self._keyword_score(lowered, terms)
            for key, terms in KEYWORDS.items()
        }
        pacing = self._pacing_score(words_per_second, duration, profile)
        hook_strength, hook_type = self._hook_score(hook_text, text)
        model_points = max(0.0, min(100.0, model_score * 100))

        curiosity = category_scores["curiosity"]
        emotion = category_scores["emotion"]
        conflict = category_scores["conflict"]
        danger = category_scores["danger"]
        surprise = category_scores["surprise"]
        humor = category_scores["humor"]
        payoff = category_scores["payoff"]

        dead_zone_penalty = max(0.0, min(100.0, dead_zone_score)) * 0.23
        retention = (
            model_points * 0.22
            + curiosity * 0.16
            + hook_strength * 0.16
            + pacing * 0.16
            + emotion * 0.10
            + surprise * 0.08
            + conflict * 0.06
            + payoff * 0.06
        ) - dead_zone_penalty
        niche_bonus = self._niche_bonus(profile, danger=danger, humor=humor, conflict=conflict, emotion=emotion)
        retention = max(35.0, min(98.0, retention + niche_bonus))
        viral_probability = max(0.05, min(0.98, (retention / 100) ** 1.18))
        quality = max(35.0, min(98.0, (retention * 0.66) + (pacing * 0.18) + (payoff * 0.16)))
        watchability = max(0.0, min(98.0, quality - (dead_zone_score * 0.30)))
        reasons = self._reasons(
            curiosity=curiosity,
            emotion=emotion,
            pacing=pacing,
            hook=hook_strength,
            conflict=conflict,
            danger=danger,
            surprise=surprise,
            humor=humor,
            dead_zone=100 - dead_zone_score,
        )
        if dead_zone_score >= 62 and retention < 78:
            decision = "review"
        else:
            decision = "auto_schedule" if retention >= 84 and viral_probability >= 0.72 else "render" if retention >= 70 else "review"
        return RetentionScores(
            retention_score=round(retention, 1),
            viral_probability=round(viral_probability, 3),
            curiosity_score=round(curiosity, 1),
            emotional_score=round(emotion, 1),
            pacing_score=round(pacing, 1),
            hook_strength_score=round(hook_strength, 1),
            conflict_score=round(conflict, 1),
            danger_score=round(danger, 1),
            surprise_score=round(surprise, 1),
            humor_score=round(humor, 1),
            quality_score=round(quality, 1),
            dead_zone_score=round(dead_zone_score, 1),
            watchability_score=round(watchability, 1),
            hook_type=hook_type,
            decision=decision,
            reasons=reasons,
        )

    async def _profile_for_clip(self, session: AsyncSession, clip: Clip) -> ChannelProfile | None:
        video = await session.get(Video, clip.video_id)
        if not video:
            return None
        return await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == video.channel_id))

    def _keyword_score(self, text: str, terms: list[str]) -> float:
        hits = sum(1 for term in terms if term in text)
        density = min(1.0, hits / 4)
        question_bonus = 0.12 if "?" in text else 0
        emphasis_bonus = 0.08 if "!" in text else 0
        return max(15.0, min(98.0, 34 + (density * 54) + (question_bonus + emphasis_bonus) * 100))

    def _pacing_score(self, words_per_second: float, duration: float, profile: ChannelProfile | None) -> float:
        target = 3.25
        if profile and profile.pacing_style.lower().startswith("fast"):
            target = 3.7
        distance = abs(words_per_second - target)
        score = 94 - (distance * 24)
        if 24 <= duration <= 44:
            score += 4
        elif duration > 55:
            score -= 8
        return max(30.0, min(98.0, score))

    def _hook_score(self, hook_text: str, transcript: str) -> tuple[float, str]:
        hook = hook_text.lower().strip()
        opener = " ".join(re.findall(r"[a-z0-9']+", transcript.lower())[:12])
        combined = f"{hook} {opener}"
        if any(term in combined for term in ["danger", "wrong", "mistake", "survive"]):
            return 88.0, "stakes"
        if any(term in combined for term in ["wild", "crazy", "insane", "shocking"]):
            return 86.0, "surprise"
        if any(term in combined for term in ["wait", "watch", "this", "nobody", "secret", "why"]):
            return 92.0, "curiosity gap"
        if len(hook.split()) <= 5 and hook:
            return 78.0, "short punch"
        return 62.0, "context hook"

    def _niche_bonus(self, profile: ChannelProfile | None, **scores: float) -> float:
        if not profile:
            return 0.0
        niche = profile.niche_type.lower()
        if "survival" in niche or "nature" in niche:
            return (scores["danger"] - 50) * 0.05
        if "gaming" in niche:
            return max(scores["surprise"], scores["humor"]) * 0.035
        if "podcast" in niche:
            return max(scores["conflict"], scores["emotion"]) * 0.03
        return 0.0

    def _reasons(self, **signals: float) -> list[str]:
        labels = {
            "curiosity": "curiosity gap",
            "emotion": "emotional charge",
            "pacing": "strong pacing",
            "hook": "strong opening hook",
            "conflict": "conflict/stakes",
            "danger": "danger or risk",
            "surprise": "surprise/reversal",
            "humor": "humor signal",
            "dead_zone": "low dead-zone risk",
        }
        ranked = sorted(signals.items(), key=lambda item: item[1], reverse=True)
        return [labels[key] for key, value in ranked[:4] if value >= 62] or ["self-contained short-form moment"]


def retention_decay(days_old: float) -> float:
    """Small recency helper used by other intelligence modules."""

    return math.exp(-max(0.0, days_old) / 28.0)
