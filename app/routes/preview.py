from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Literal, Optional

from app.rendering.digest_renderer import render_digest_html
from app.rendering.context_builder import build_digest_context_with_provider, build_single_event_context
from app.schemas.preview import DigestPreviewModel, MeetingModel, Attendee, Company, NewsItem
from app.core.config import load_config


router = APIRouter()


def _require_api_key_if_configured(request: Request) -> None:
    """Require API key if configured in environment."""
    cfg = load_config()
    if not cfg.api_key:
        return
    provided = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if provided != cfg.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _convert_meeting_to_model(meeting: dict) -> MeetingModel:
    """Convert a meeting (dict or pydantic model) to a MeetingModel."""
    if hasattr(meeting, "model_dump"):
        meeting = meeting.model_dump()  # type: ignore[assignment]
    # Convert attendees
    attendees = []
    for attendee in meeting.get("attendees", []):
        attendees.append(Attendee(
            name=attendee.get("name", ""),
            title=attendee.get("title"),
            company=attendee.get("company")
        ))

    # Convert company
    company = None
    if meeting.get("company"):
        company = Company(
            name=meeting["company"].get("name", ""),
            one_liner=meeting["company"].get("one_liner")
        )

    # Convert news items
    news = []
    for news_item in meeting.get("news", []):
        if isinstance(news_item, dict) and news_item.get("title") and news_item.get("url"):
            news.append(NewsItem(
                title=news_item["title"],
                url=news_item["url"]
            ))

    return MeetingModel(
        subject=meeting.get("subject", ""),
        start_time=meeting.get("start_time", ""),
        location=meeting.get("location"),
        attendees=attendees,
        company=company,
        news=news,
        talking_points=meeting.get("talking_points", []),
        smart_questions=meeting.get("smart_questions", [])
    )


@router.get("/preview", response_class=HTMLResponse)
async def preview_digest_html(
    request: Request,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) - ignored in MVP unless live path supports it"),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile"),
    format: Optional[str] = Query(None, description="Response format: json")
):
    """
    Preview the digest as HTML or JSON.

    Returns HTML by default, or JSON if format=json or Accept: application/json.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Check if JSON format is requested
    accept_json = request.headers.get("accept", "").startswith("application/json")
    format_json = format == "json"

    if accept_json or format_json:
        # Return JSON response
        return await preview_digest_json(request, source, date, exec_name, mailbox)
    else:
        # Return HTML response
        return await _render_html_preview(request, source, date, exec_name, mailbox)


async def _render_html_preview(
    request: Request,
    source: Literal["sample", "live"],
    date: Optional[str],
    exec_name: Optional[str],
    mailbox: Optional[str]
) -> HTMLResponse:
    """Internal function to render HTML preview."""
    # Build context using shared context builder
    context = build_digest_context_with_provider(source=source, date=date, exec_name=exec_name, mailbox=mailbox)

    # Add request to context for template rendering
    context["request"] = request

    # Render HTML
    html = render_digest_html(context)

    return HTMLResponse(content=html)


@router.get("/preview.json")
async def preview_digest_json(
    request: Request,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) - ignored in MVP unless live path supports it"),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile")
):
    """
    Preview the digest as JSON.

    Returns the structured digest model that the template uses.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Build context using shared context builder
    context = build_digest_context_with_provider(source=source, date=date, exec_name=exec_name, mailbox=mailbox)

    # Convert meetings to Pydantic models
    meetings = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]

    # Build response model
    response = DigestPreviewModel(
        ok=True,
        source=context["source"],
        date_human=context["date_human"],
        exec_name=context["exec_name"],
        meetings=meetings
    )

    return JSONResponse(content=response.model_dump())


@router.get("/preview/event/{event_id}.json")
async def preview_single_event_json(
    request: Request,
    event_id: str,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) - ignored in MVP unless live path supports it"),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile")
):
    """
    Preview a single event by ID as JSON.

    Returns the structured event model that the template uses.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Build context using single event context builder
    context = build_single_event_context(
        event_id=event_id,
        source=source,
        date=date,
        exec_name=exec_name,
        mailbox=mailbox
    )

    # Convert meetings to Pydantic models
    meetings = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]

    # Build response model
    response = DigestPreviewModel(
        ok=True,
        source=context["source"],
        date_human=context["date_human"],
        exec_name=context["exec_name"],
        meetings=meetings
    )

    return JSONResponse(content=response.model_dump())


@router.get("/preview/event/{event_id}")
async def preview_single_event_html(
    request: Request,
    event_id: str,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) - ignored in MVP unless live path supports it"),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile"),
    format: Optional[str] = Query(None, description="Response format: json")
):
    """
    Preview a single event by ID as HTML or JSON.

    Returns HTML by default, or JSON if format=json or Accept: application/json.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Check if JSON format is requested
    accept_json = request.headers.get("accept", "").startswith("application/json")
    format_json = format == "json"

    if accept_json or format_json:
        # Return JSON response
        return await preview_single_event_json(request, event_id, source, date, exec_name, mailbox)
    else:
        # Return HTML response
        return await _render_single_event_html(request, event_id, source, date, exec_name, mailbox)


async def _render_single_event_html(
    request: Request,
    event_id: str,
    source: Literal["sample", "live"],
    date: Optional[str],
    exec_name: Optional[str],
    mailbox: Optional[str]
) -> HTMLResponse:
    """Internal function to render single event HTML preview."""
    # Build context using single event context builder
    context = build_single_event_context(
        event_id=event_id,
        source=source,
        date=date,
        exec_name=exec_name,
        mailbox=mailbox
    )

    # Add request to context for template rendering
    context["request"] = request

    # Render HTML
    html = render_digest_html(context)

    return HTMLResponse(content=html)


