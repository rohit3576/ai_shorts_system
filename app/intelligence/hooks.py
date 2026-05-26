"""Hook template generation and learning-aware selection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.profiles import ChannelPersona, persona_for_profile
from database.models import ChannelProfile, Clip, LearningEvent, Video


@dataclass(frozen=True)
class HookVariant:
    """A candidate opening hook."""

    hook_type: str
    text: str
    score: float
    reason: str


HOOK_TEMPLATES: dict[str, list[str]] = {
    "curiosity": [
        "Nobody Expected This",
        "Watch What Happens",
        "This Changes Everything",
        "The Truth Is Weird",
    ],
    "danger": [
        "This Gets Dangerous",
        "He Almost Missed It",
        "That Was A Mistake",
        "This Is The Risk",
    ],
    "surprise": [
        "Wait For It",
        "This Is Wild",
        "Then It Flipped",
        "The Ending Is Insane",
    ],
    "emotional": [
        "This Hit Hard",
        "He Finally Said It",
        "That Changed Him",
        "This Moment Hurt",
    ],
    "conflict": [
        "He Was Wrong",
        "They All Disagreed",
        "This Started A Fight",
        "That Was The Problem",
    ],
    "authority": [
        "Experts Miss This",
        "Here Is The Rule",
        "This Is Why",
        "The Real Reason",
    ],
}


class HookTemplateEngine:
    """Generate hooks and choose the best variant from local learning."""

    async def generate_variants(
        self,
        session: AsyncSession,
        clip: Clip,
        *,
        transcript_excerpt: str,
        max_variants: int = 8,
    ) -> list[HookVariant]:
        profile = await self._profile_for_clip(session, clip)
        persona = persona_for_profile(profile)
        text_signals = self._signals(transcript_excerpt)
        learned = await self.hook_performance(session)
        variants: list[HookVariant] = []

        for hook_type, templates in HOOK_TEMPLATES.items():
            type_boost = self._persona_boost(hook_type, persona)
            signal_boost = text_signals.get(hook_type, 0)
            learned_boost = learned.get(hook_type, 0)
            for template in templates[:2]:
                score = 52 + type_boost + signal_boost + learned_boost + self._specificity_bonus(template, transcript_excerpt)
                variants.append(
                    HookVariant(
                        hook_type=hook_type,
                        text=self._compact(template),
                        score=round(max(35, min(98, score)), 1),
                        reason=f"{hook_type} hook matched {persona.niche_type} persona",
                    )
                )

        if clip.hook_text:
            variants.append(
                HookVariant(
                    hook_type="existing",
                    text=self._compact(clip.hook_text),
                    score=70 + learned.get("existing", 0),
                    reason="Existing generated hook retained as fallback",
                )
            )
        return sorted(variants, key=lambda item: item.score, reverse=True)[:max_variants]

    async def apply_best_hook(
        self,
        session: AsyncSession,
        clip: Clip,
        *,
        transcript_excerpt: str,
        preferred_type: str | None = None,
    ) -> HookVariant:
        variants = await self.generate_variants(session, clip, transcript_excerpt=transcript_excerpt)
        if preferred_type:
            preferred = [item for item in variants if item.hook_type == preferred_type]
            best = preferred[0] if preferred else variants[0]
        else:
            best = variants[0]
        clip.hook_text = best.text
        metadata = dict(clip.metadata_json or {})
        metadata["hook_variants"] = [asdict(item) for item in variants]
        metadata["selected_hook"] = asdict(best)
        metadata["hook_type"] = best.hook_type
        clip.metadata_json = metadata
        await session.flush()
        return best

    async def hook_performance(self, session: AsyncSession) -> dict[str, float]:
        result = await session.execute(select(LearningEvent).order_by(desc(LearningEvent.learned_at)).limit(300))
        buckets: dict[str, list[float]] = {}
        for event in result.scalars().all():
            hook_type = str((event.features_json or {}).get("hook_type") or "").strip()
            if not hook_type:
                continue
            buckets.setdefault(hook_type, []).append(float(event.outcome_score or 0))
        return {
            hook_type: max(-8.0, min(14.0, (sum(values) / len(values) - 62) / 2.2))
            for hook_type, values in buckets.items()
        }

    async def _profile_for_clip(self, session: AsyncSession, clip: Clip) -> ChannelProfile | None:
        video = await session.get(Video, clip.video_id)
        if not video:
            return None
        return await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == video.channel_id))

    def _signals(self, text: str) -> dict[str, int]:
        lowered = text.lower()
        return {
            "curiosity": 16 if any(word in lowered for word in ["why", "secret", "truth", "nobody", "what"]) else 5,
            "danger": 18 if any(word in lowered for word in ["danger", "risk", "afraid", "trap", "survive"]) else 0,
            "surprise": 16 if any(word in lowered for word in ["suddenly", "actually", "wild", "insane", "unexpected"]) else 3,
            "emotional": 16 if any(word in lowered for word in ["love", "hate", "cry", "hurt", "beautiful"]) else 2,
            "conflict": 17 if any(word in lowered for word in ["wrong", "fight", "but", "however", "problem"]) else 3,
            "authority": 14 if any(word in lowered for word in ["rule", "expert", "because", "reason", "study"]) else 2,
        }

    def _persona_boost(self, hook_type: str, persona: ChannelPersona) -> int:
        preferred = persona.hook_style.lower()
        if hook_type in preferred:
            return 16
        if hook_type == "danger" and "danger" in persona.emotional_profile:
            return 11
        return int(persona.emotional_profile.get(hook_type, 50) / 10)

    def _specificity_bonus(self, template: str, transcript: str) -> int:
        first_words = set(re.findall(r"[a-z0-9']+", transcript.lower())[:28])
        template_words = set(re.findall(r"[a-z0-9']+", template.lower()))
        return min(8, len(first_words & template_words) * 2)

    def _compact(self, text: str, max_chars: int = 32) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        if len(cleaned) <= max_chars:
            return cleaned
        words: list[str] = []
        for word in cleaned.split():
            candidate = " ".join([*words, word])
            if len(candidate) > max_chars:
                break
            words.append(word)
        return " ".join(words) or cleaned[:max_chars]
