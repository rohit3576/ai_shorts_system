"""Upload safety, rights, and quality preflight checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import Clip, ClipIntelligence, QualityGateResult, ReviewDecision, RightsReview


class UploadGateError(ValueError):
    """Raised when a clip is not safe or strong enough to upload."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("Upload gate failed: " + "; ".join(reasons))


class QualityGateService:
    """Evaluate whether a generated Short can be queued for YouTube."""

    async def record_rights_review(
        self,
        session: AsyncSession,
        *,
        clip_id: int,
        review: dict[str, Any],
    ) -> RightsReview:
        """Persist a structured rights/originality review."""

        existing = await session.scalar(
            select(RightsReview).where(RightsReview.clip_id == clip_id).order_by(desc(RightsReview.created_at)).limit(1)
        )
        row = existing or RightsReview(clip_id=clip_id)
        row.owned_content = bool(review.get("owned_content"))
        row.licensed_content = bool(review.get("licensed_content"))
        row.commentary_added = bool(review.get("commentary_added"))
        row.narration_added = bool(review.get("narration_added"))
        row.transformative_edit = bool(review.get("transformative_edit"))
        row.approved_for_upload = bool(review.get("approved_for_upload"))
        row.policy_notes = review.get("policy_notes")
        row.reviewer = review.get("reviewer")
        row.originality_score = self.originality_score(row)
        row.metadata_json = {"source": "structured_rights_review"}
        if not existing:
            session.add(row)
        await session.flush()
        return row

    async def validate_for_upload(
        self,
        session: AsyncSession,
        *,
        clip: Clip,
        rights_review_payload: dict[str, Any] | None = None,
        upload_id: int | None = None,
    ) -> QualityGateResult:
        """Create a quality gate result and raise if it fails."""

        rights = None
        if rights_review_payload:
            rights = await self.record_rights_review(session, clip_id=clip.id, review=rights_review_payload)
        if rights is None:
            rights = await session.scalar(
                select(RightsReview)
                .where(RightsReview.clip_id == clip.id)
                .order_by(desc(RightsReview.created_at))
                .limit(1)
            )

        intelligence = await session.scalar(select(ClipIntelligence).where(ClipIntelligence.clip_id == clip.id))
        latest_review = await session.scalar(
            select(ReviewDecision)
            .where(ReviewDecision.clip_id == clip.id)
            .order_by(desc(ReviewDecision.created_at))
            .limit(1)
        )

        originality = rights.originality_score if rights else 0.0
        hook_quality = float(
            intelligence.hook_strength_score
            if intelligence
            else (clip.metadata_json or {}).get("hook_strength_score") or float(clip.viral_score or 0) * 100
        )
        pacing_score = float(
            intelligence.pacing_score
            if intelligence
            else (clip.metadata_json or {}).get("pacing_score") or 0
        )
        dead_zone_risk = float((clip.metadata_json or {}).get("dead_zone_score") or 0)
        subtitle_readability = self.subtitle_readability(clip)
        render_quality = self.render_quality(clip)
        review_approved = clip.status in {"approved", "queued", "uploaded"} or (
            latest_review is not None and latest_review.action == "approved"
        )

        reasons: list[str] = []
        if not rights:
            reasons.append("Missing structured rights review.")
        elif not rights.approved_for_upload:
            reasons.append("Rights review is not approved for upload.")
        elif not self._rights_are_safe(rights):
            reasons.append("Rights review does not show owned/licensed or meaningfully transformed content.")
        if originality < settings.upload_min_originality_score:
            reasons.append(f"Originality score {originality:.1f} is below {settings.upload_min_originality_score:.1f}.")
        if hook_quality < settings.upload_min_hook_quality:
            reasons.append(f"Hook quality {hook_quality:.1f} is below {settings.upload_min_hook_quality:.1f}.")
        if pacing_score < settings.upload_min_pacing_score:
            reasons.append(f"Pacing score {pacing_score:.1f} is below {settings.upload_min_pacing_score:.1f}.")
        if dead_zone_risk > settings.upload_max_dead_zone_risk:
            reasons.append(f"Dead-zone risk {dead_zone_risk:.1f} is above {settings.upload_max_dead_zone_risk:.1f}.")
        if subtitle_readability <= 0:
            reasons.append("Subtitle file is missing.")
        if render_quality <= 0:
            reasons.append("Rendered MP4 is missing or empty.")
        if not review_approved:
            reasons.append("Human review approval is required before upload.")

        gate = QualityGateResult(
            clip_id=clip.id,
            upload_id=upload_id,
            passed=not reasons,
            originality_score=originality,
            hook_quality=hook_quality,
            subtitle_readability=subtitle_readability,
            pacing_score=pacing_score,
            dead_zone_risk=dead_zone_risk,
            render_quality=render_quality,
            review_approved=review_approved,
            reasons_json=reasons,
            metadata_json={"metric_source": "PREDICTED", "rights_review_id": rights.id if rights else None},
        )
        session.add(gate)
        await session.flush()
        if reasons:
            raise UploadGateError(reasons)
        return gate

    def originality_score(self, review: RightsReview) -> float:
        """Score originality without pretending to detect copyright automatically."""

        score = 0.0
        if review.owned_content:
            score += 70
        if review.licensed_content:
            score += 55
        if review.commentary_added:
            score += 18
        if review.narration_added:
            score += 18
        if review.transformative_edit:
            score += 22
        if review.approved_for_upload:
            score += 5
        return round(min(100.0, score), 1)

    def subtitle_readability(self, clip: Clip) -> float:
        path = Path(clip.subtitle_path or "")
        if not clip.subtitle_path or not path.exists():
            return 0.0
        size = path.stat().st_size
        return 100.0 if size > 200 else 40.0

    def render_quality(self, clip: Clip) -> float:
        path = Path(clip.clip_path or "")
        if not clip.clip_path or not path.exists():
            return 0.0
        size_mb = path.stat().st_size / (1024 * 1024)
        return round(max(20.0, min(100.0, size_mb * 8)), 1)

    def _rights_are_safe(self, review: RightsReview) -> bool:
        owned_or_licensed = review.owned_content or review.licensed_content
        transformed = review.commentary_added or review.narration_added or review.transformative_edit
        return bool(owned_or_licensed or transformed)
