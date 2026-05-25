"""Managed channel profile helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AnalyticsSnapshot, Channel, ChannelProfile, Clip, Upload, Video


DEFAULT_SCHEDULES: dict[str, list[str]] = {
    "gaming": ["12:30", "18:30", "22:00"],
    "nature/survival": ["09:00", "17:30", "20:30"],
    "podcast": ["08:30", "13:00", "19:00"],
    "documentary": ["10:00", "16:00", "21:00"],
    "general": ["11:30", "18:00", "21:00"],
}


@dataclass(frozen=True)
class ChannelPersona:
    """Retention strategy defaults for a managed media channel."""

    niche_type: str
    pacing_style: str
    subtitle_style: str
    hook_style: str
    emotional_profile: dict[str, int]
    preferred_upload_schedule: list[str]
    target_duration_seconds: int
    dead_zone_tolerance: int


PERSONA_PRESETS: dict[str, ChannelPersona] = {
    "gaming": ChannelPersona(
        niche_type="gaming",
        pacing_style="fast/high energy",
        subtitle_style="large kinetic punch captions",
        hook_style="surprise/conflict",
        emotional_profile={"surprise": 90, "humor": 78, "conflict": 82, "danger": 58, "curiosity": 84},
        preferred_upload_schedule=DEFAULT_SCHEDULES["gaming"],
        target_duration_seconds=32,
        dead_zone_tolerance=18,
    ),
    "nature/survival": ChannelPersona(
        niche_type="nature/survival",
        pacing_style="cinematic suspense",
        subtitle_style="bold suspense captions",
        hook_style="fear/curiosity",
        emotional_profile={"danger": 92, "curiosity": 88, "surprise": 76, "emotion": 72, "conflict": 62},
        preferred_upload_schedule=DEFAULT_SCHEDULES["nature/survival"],
        target_duration_seconds=42,
        dead_zone_tolerance=24,
    ),
    "podcast": ChannelPersona(
        niche_type="podcast",
        pacing_style="emotional storytelling",
        subtitle_style="clean word-emphasis captions",
        hook_style="emotional/conflict",
        emotional_profile={"emotion": 90, "conflict": 82, "curiosity": 78, "authority": 70, "surprise": 62},
        preferred_upload_schedule=DEFAULT_SCHEDULES["podcast"],
        target_duration_seconds=46,
        dead_zone_tolerance=28,
    ),
    "documentary": ChannelPersona(
        niche_type="documentary",
        pacing_style="cinematic reveal",
        subtitle_style="premium documentary captions",
        hook_style="authority/curiosity",
        emotional_profile={"curiosity": 90, "authority": 86, "surprise": 72, "emotion": 68, "danger": 52},
        preferred_upload_schedule=DEFAULT_SCHEDULES["documentary"],
        target_duration_seconds=44,
        dead_zone_tolerance=26,
    ),
    "general": ChannelPersona(
        niche_type="general",
        pacing_style="fast cut",
        subtitle_style="tiktok punch captions",
        hook_style="curiosity gap",
        emotional_profile={"curiosity": 84, "surprise": 72, "emotion": 68, "conflict": 64, "humor": 58},
        preferred_upload_schedule=DEFAULT_SCHEDULES["general"],
        target_duration_seconds=38,
        dead_zone_tolerance=24,
    ),
}


def persona_for_niche(niche_type: str | None) -> ChannelPersona:
    """Return the closest built-in persona for a niche label."""

    normalized = (niche_type or "general").strip().lower()
    if normalized in PERSONA_PRESETS:
        return PERSONA_PRESETS[normalized]
    if "survival" in normalized or "nature" in normalized:
        return PERSONA_PRESETS["nature/survival"]
    if "game" in normalized:
        return PERSONA_PRESETS["gaming"]
    if "podcast" in normalized or "interview" in normalized:
        return PERSONA_PRESETS["podcast"]
    if "doc" in normalized or "history" in normalized:
        return PERSONA_PRESETS["documentary"]
    return PERSONA_PRESETS["general"]


def persona_for_profile(profile: ChannelProfile | None) -> ChannelPersona:
    """Return a persona, merging persisted profile overrides where present."""

    base = persona_for_niche(profile.niche_type if profile else None)
    if not profile:
        return base
    metadata = profile.metadata_json or {}
    emotional_profile = metadata.get("emotional_profile") or base.emotional_profile
    return ChannelPersona(
        niche_type=profile.niche_type or base.niche_type,
        pacing_style=profile.pacing_style or base.pacing_style,
        subtitle_style=profile.subtitle_style or base.subtitle_style,
        hook_style=profile.hook_style or base.hook_style,
        emotional_profile=emotional_profile,
        preferred_upload_schedule=(profile.schedule_json or {}).get("times", base.preferred_upload_schedule),
        target_duration_seconds=profile.target_duration_seconds or base.target_duration_seconds,
        dead_zone_tolerance=int(metadata.get("dead_zone_tolerance", base.dead_zone_tolerance)),
    )


class ChannelProfileService:
    """Create and summarize managed media-channel profiles."""

    async def ensure_profile(
        self,
        session: AsyncSession,
        channel: Channel,
        *,
        niche_type: str = "general",
        upload_style: str = "curiosity clips",
        hook_style: str = "curiosity gap",
        target_audience: str | None = None,
    ) -> ChannelProfile:
        existing = await session.scalar(select(ChannelProfile).where(ChannelProfile.channel_id == channel.id))
        if existing:
            return existing
        normalized_niche = niche_type.strip().lower() or "general"
        persona = persona_for_niche(normalized_niche)
        profile = ChannelProfile(
            channel_id=channel.id,
            niche_type=normalized_niche,
            target_audience=target_audience,
            upload_style=upload_style or persona.hook_style,
            hook_style=hook_style or persona.hook_style,
            subtitle_style=persona.subtitle_style,
            pacing_style=persona.pacing_style,
            target_duration_seconds=persona.target_duration_seconds,
            schedule_json={"times": persona.preferred_upload_schedule},
            metadata_json={
                "created_by": "dashboard",
                "persona": asdict(persona),
                "emotional_profile": persona.emotional_profile,
                "dead_zone_tolerance": persona.dead_zone_tolerance,
            },
        )
        session.add(profile)
        await session.flush()
        return profile

    async def payload(self, session: AsyncSession) -> dict[str, Any]:
        result = await session.execute(select(Channel).order_by(desc(Channel.created_at)))
        channels = list(result.scalars().all())
        profiles = {
            item.channel_id: item
            for item in (
                await session.execute(select(ChannelProfile))
            ).scalars().all()
        }
        items = []
        for channel in channels:
            profile = profiles.get(channel.id)
            views = await self._channel_views(session, channel.id)
            clips = await session.scalar(
                select(func.count(Clip.id)).join(Video, Clip.video_id == Video.id).where(Video.channel_id == channel.id)
            ) or 0
            uploads = await session.scalar(
                select(func.count(Upload.id))
                .join(Clip, Upload.clip_id == Clip.id)
                .join(Video, Clip.video_id == Video.id)
                .where(Video.channel_id == channel.id)
            ) or 0
            items.append(
                self._serialize_channel(channel, profile, views=views, clips=clips, uploads=uploads)
            )
        return {
            "items": items,
            "personas": {key: asdict(value) for key, value in PERSONA_PRESETS.items()},
            "network": {
                "managed_channels": len(items),
                "active_channels": sum(1 for item in items if item["active"]),
                "total_views": sum(item["views"] for item in items),
                "total_clips": sum(item["clips"] for item in items),
                "avg_upload_frequency": round(sum(item["upload_frequency"] for item in items) / max(1, len(items)), 1),
            },
        }

    def _serialize_channel(
        self,
        channel: Channel,
        profile: ChannelProfile | None,
        *,
        views: int,
        clips: int,
        uploads: int,
    ) -> dict[str, Any]:
        persona = persona_for_profile(profile)
        return (
                {
                    "id": channel.id,
                    "name": channel.name or channel.channel_id or "Managed channel",
                    "url": channel.url,
                    "active": channel.active,
                    "niche_type": profile.niche_type if profile else "general",
                    "upload_style": profile.upload_style if profile else "curiosity clips",
                    "hook_style": profile.hook_style if profile else "curiosity gap",
                    "subtitle_style": profile.subtitle_style if profile else "tiktok punch captions",
                    "upload_frequency": profile.upload_frequency_per_day if profile else 2,
                    "pacing_style": persona.pacing_style,
                    "emotional_profile": persona.emotional_profile,
                    "preferred_upload_schedule": persona.preferred_upload_schedule,
                    "dead_zone_tolerance": persona.dead_zone_tolerance,
                    "schedule": persona.preferred_upload_schedule,
                    "estimated_rpm": profile.estimated_shorts_rpm if profile else 0.06,
                    "clips": clips,
                    "uploads": uploads,
                    "views": views,
                    "growth": self._growth_label(views, clips),
                    "last_checked_at": channel.last_checked_at.isoformat() if channel.last_checked_at else None,
                }
        )

    async def _channel_views(self, session: AsyncSession, channel_id: int) -> int:
        result = await session.execute(
            select(AnalyticsSnapshot)
            .join(Clip, AnalyticsSnapshot.clip_id == Clip.id)
            .join(Video, Clip.video_id == Video.id)
            .where(Video.channel_id == channel_id)
        )
        return sum(item.views for item in result.scalars().all())

    def _growth_label(self, views: int, clips: int) -> str:
        if views >= 100000:
            return "scaling"
        if views >= 10000:
            return "accelerating"
        if clips:
            return "learning"
        return "warming up"
