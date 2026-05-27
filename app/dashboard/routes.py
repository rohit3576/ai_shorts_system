"""Dashboard HTML and JSON routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard import services
from database.session import get_read_session

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


async def _bootstrap(session: AsyncSession) -> dict[str, Any]:
    overview = await services.overview_payload(session)
    return {
        "overview": overview,
        "clips": await services.clips_payload(session, limit=24),
        "analytics": await services.analytics_payload(session),
        "channels": await services.channels_payload(session),
        "uploadIntelligence": await services.upload_intelligence_payload(session),
        "uploads": await services.uploads_payload(session),
        "settings": services.settings_payload(),
    }


async def _render_app(
    request: Request,
    session: AsyncSession,
    *,
    page: str,
    template_name: str,
) -> HTMLResponse:
    bootstrap = await _bootstrap(session)
    overview = bootstrap["overview"]
    context = {
        "request": request,
        "page": page,
        "bootstrap": bootstrap,
        "stats": overview["stats"],
        "clips": overview["clips"],
        "videos": overview["videos"],
    }
    return templates.TemplateResponse(request, template_name, context)


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
@router.get("/review", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Render the review queue as the creator home screen."""

    return await _render_app(request, session, page="review", template_name="dashboard.html")


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Render source management."""

    return await _render_app(request, session, page="sources", template_name="dashboard.html")


@router.get("/generate", response_class=HTMLResponse)
async def generate_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Render the generation workflow."""

    return await _render_app(request, session, page="generate", template_name="dashboard.html")


@router.get("/uploads", response_class=HTMLResponse)
async def uploads_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Render private and scheduled uploads."""

    return await _render_app(request, session, page="uploads", template_name="dashboard.html")


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route for the generation workflow."""

    return await _render_app(request, session, page="generate", template_name="dashboard.html")


@router.get("/clips", response_class=HTMLResponse)
async def clips_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route for the review queue."""

    return await _render_app(request, session, page="review", template_name="dashboard.html")


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Render analytics."""

    return await _render_app(request, session, page="analytics", template_name="analytics.html")


@router.get("/ai-insights", response_class=HTMLResponse)
async def ai_insights_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into the review queue."""

    return await _render_app(request, session, page="review", template_name="dashboard.html")


@router.get("/upload-intelligence", response_class=HTMLResponse)
async def upload_intelligence_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into uploads."""

    return await _render_app(request, session, page="uploads", template_name="dashboard.html")


@router.get("/revenue", response_class=HTMLResponse)
async def revenue_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into creator analytics."""

    return await _render_app(request, session, page="analytics", template_name="dashboard.html")


@router.get("/trends", response_class=HTMLResponse)
async def trends_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into sources."""

    return await _render_app(request, session, page="sources", template_name="dashboard.html")


@router.get("/learning", response_class=HTMLResponse)
async def learning_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into creator analytics."""

    return await _render_app(request, session, page="analytics", template_name="dashboard.html")


@router.get("/channels", response_class=HTMLResponse)
async def channels_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route for sources."""

    return await _render_app(request, session, page="sources", template_name="dashboard.html")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into sources."""

    return await _render_app(request, session, page="sources", template_name="dashboard.html")


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    session: AsyncSession = Depends(get_read_session),
) -> HTMLResponse:
    """Legacy route folded into generation."""

    return await _render_app(request, session, page="generate", template_name="dashboard.html")


@router.get("/dashboard/api/overview")
async def dashboard_overview(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    return await services.overview_payload(session)


@router.get("/dashboard/api/clips")
async def dashboard_clips(
    session: AsyncSession = Depends(get_read_session),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None),
    sort: str = Query("score"),
) -> dict[str, Any]:
    return await services.clips_payload(session, limit=limit, offset=offset, status=status, sort=sort)


@router.get("/dashboard/api/analytics")
async def dashboard_analytics(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    return await services.analytics_payload(session)


@router.get("/dashboard/api/channels")
async def dashboard_channels(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    return await services.channels_payload(session)


@router.get("/dashboard/api/ai-insights")
async def dashboard_ai_insights(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    payload = await services.ai_insights_payload(session)
    return payload


@router.get("/dashboard/api/upload-intelligence")
async def dashboard_upload_intelligence(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    payload = await services.upload_intelligence_payload(session)
    return payload


@router.get("/dashboard/api/jobs")
async def dashboard_jobs(
    session: AsyncSession = Depends(get_read_session),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return await services.jobs_payload(session, limit=limit)


@router.get("/dashboard/api/revenue")
async def dashboard_revenue(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    payload = await services.revenue_payload(session)
    return payload


@router.get("/dashboard/api/trends")
async def dashboard_trends(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    payload = await services.trend_center_payload(session)
    return payload


@router.get("/dashboard/api/learning")
async def dashboard_learning(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    payload = await services.learning_payload(session)
    return payload


@router.get("/dashboard/api/uploads")
async def dashboard_uploads(
    session: AsyncSession = Depends(get_read_session),
    status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    return await services.uploads_payload(session, status=status, limit=limit)


@router.get("/dashboard/api/logs")
async def dashboard_logs(
    session: AsyncSession = Depends(get_read_session),
    limit: int = Query(80, ge=1, le=200),
    level: str | None = Query(default=None),
) -> dict[str, Any]:
    return await services.logs_payload(session, limit=limit, level=level)


@router.get("/dashboard/api/settings")
async def dashboard_settings() -> dict[str, Any]:
    return services.settings_payload()


@router.get("/dashboard/api/storage")
async def dashboard_storage(session: AsyncSession = Depends(get_read_session)) -> dict[str, Any]:
    return await services.storage_payload(session)


@router.get("/favicon.ico")
async def favicon() -> Response:
    """Handle browser favicon requests without a 500 or noisy 404."""

    icon_path = Path(__file__).parent / "static" / "images" / "favicon.svg"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/svg+xml")
    return Response(status_code=204)
