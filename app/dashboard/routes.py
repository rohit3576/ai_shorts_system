"""Server-rendered dashboard routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from database.models import AnalyticsSnapshot, Channel, Clip, Upload, Video
from database.session import get_session

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Render the local operations dashboard."""

    counts = {}
    for key, model in {
        "channels": Channel,
        "videos": Video,
        "clips": Clip,
        "uploads": Upload,
    }.items():
        counts[key] = await session.scalar(select(func.count(model.id)))

    videos = list(
        (
            await session.execute(select(Video).order_by(desc(Video.created_at)).limit(10))
        )
        .scalars()
        .all()
    )
    clips = list(
        (
            await session.execute(select(Clip).order_by(desc(Clip.viral_score)).limit(10))
        )
        .scalars()
        .all()
    )
    uploads = list(
        (
            await session.execute(select(Upload).order_by(desc(Upload.created_at)).limit(10))
        )
        .scalars()
        .all()
    )
    analytics = list(
        (
            await session.execute(
                select(AnalyticsSnapshot).order_by(desc(AnalyticsSnapshot.captured_at)).limit(8)
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": settings,
            "counts": counts,
            "videos": videos,
            "clips": clips,
            "uploads": uploads,
            "analytics": analytics,
        },
    )

