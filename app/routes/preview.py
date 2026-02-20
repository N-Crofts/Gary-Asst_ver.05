import os
import uuid
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Literal, Optional
from datetime import datetime

from app.rendering.digest_renderer import render_digest_html
from app.rendering.context_builder import build_digest_context_with_provider, build_single_event_context
from app.schemas.preview import DigestPreviewModel, MeetingModel, Attendee, Company, NewsItem
from app.core.config import load_config
from app.storage.cache import get_preview_cache
from app.research.config import MAX_TAVILY_CALLS_PER_REQUEST, ResearchBudget


def _validate_date(date_str: Optional[str]) -> Optional[str]:
    """
    Validate date string format (YYYY-MM-DD).

    Returns the date string if valid, None if None, or raises HTTPException for invalid format.
    """
    if date_str is None:
        return None

    # First check the format strictly - must be exactly YYYY-MM-DD
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format: '{date_str}'. Expected format: YYYY-MM-DD (e.g., 2025-12-05)"
        )

    try:
        # Try to parse the date to validate it's a real date
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
        # Verify the parsed date matches the input (catches cases like 2025-12-5 which becomes 2025-12-05)
        if parsed_date.strftime("%Y-%m-%d") != date_str:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date format: '{date_str}'. Expected format: YYYY-MM-DD (e.g., 2025-12-05)"
            )
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format: '{date_str}'. Expected format: YYYY-MM-DD (e.g., 2025-12-05)"
        )


router = APIRouter()


def _require_api_key_if_configured(request: Request) -> None:
    """Require API key if configured in environment."""
    cfg = load_config()
    if not cfg.api_key:
        return
    provided = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if provided != cfg.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def should_run_research(request: Request, settings: dict) -> bool:
    """
    Whether to run research for this request (staging-only override via research=1).

    - If APP_ENV == production: ignore query param, return settings["research_enabled"].
    - If APP_ENV != production and research=1: return True (force research for this request).
    - Otherwise: return settings["research_enabled"].

    settings must have: app_env (str), research_enabled (bool).
    """
    app_env = (settings.get("app_env") or "development").strip().lower()
    research_enabled = settings.get("research_enabled", False)
    if app_env == "production":
        return research_enabled
    if request and request.query_params.get("research", "").strip() == "1":
        return True
    return research_enabled


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
        smart_questions=meeting.get("smart_questions", []),
        context_summary=meeting.get("context_summary"),
        industry_signal=meeting.get("industry_signal"),
        strategic_angles=meeting.get("strategic_angles", []),
        high_leverage_questions=meeting.get("high_leverage_questions", []),
        research_trace=meeting.get("research_trace"),
    )


@router.get("/preview", response_class=HTMLResponse)
async def preview_digest_html(
    request: Request,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today if omitted."),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile"),
    format: Optional[str] = Query(None, description="Response format: json")
):
    """
    Preview the digest as HTML or JSON.

    Returns HTML by default, or JSON if format=json or Accept: application/json.

    The date parameter allows previewing any single date (past or future) in YYYY-MM-DD format.
    If omitted, defaults to today's date.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"=== PREVIEW REQUEST START ===")
    logger.info(f"Preview request received: source={source}, date={date}, mailbox={mailbox}")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request path: {request.url.path}")
    logger.info(f"Query params: {dict(request.query_params)}")

    try:
        _require_api_key_if_configured(request)
        logger.info("API key check passed")
    except Exception as e:
        logger.error(f"API key check failed: {e}")
        raise

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Validate date format
    _validate_date(date)

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
    import logging
    logger = logging.getLogger(__name__)
    
    # Build context using shared context builder (research allowed only here and run-digest/digest send)
    request_id = str(uuid.uuid4())
    research_budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    research_enabled_env = (os.getenv("RESEARCH_ENABLED") or "").strip().lower() in ("true", "1", "yes")
    settings = {
        "app_env": os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development",
        "research_enabled": research_enabled_env,
    }
    allow_research = should_run_research(request, settings)
    logger.info(f"Building digest context: source={source}, date={date}, mailbox={mailbox}, allow_research={allow_research}")
    context = build_digest_context_with_provider(
        source=source,
        date=date,
        exec_name=exec_name,
        mailbox=mailbox,
        allow_research=allow_research,
        research_budget=research_budget,
        request_id=request_id,
    )
    meeting_count = len(context.get("meetings", []))
    logger.info(f"Context built: source={context.get('source')}, meeting_count={meeting_count}, mailbox={mailbox}")

    # Add request to context for template rendering
    context["request"] = request

    # Render HTML
    html = render_digest_html(context)

    # Cache the result if it's for today
    if date is None or date == datetime.now().strftime("%Y-%m-%d"):
        cache = get_preview_cache()
        # Convert context to serializable format
        context_for_cache = {
            "source": context["source"],
            "date_human": context["date_human"],
            "exec_name": context["exec_name"],
            "meetings": [meeting.model_dump() for meeting in context["meetings"]]
        }
        cache_date = date or datetime.now().strftime("%Y-%m-%d")
        cache.set(mailbox, cache_date, html, context_for_cache)

    return HTMLResponse(content=html)


@router.get("/preview/latest")
@router.get("/preview/latest.json")
async def preview_digest_latest(
    request: Request,
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile"),
    format: Optional[str] = Query(None, description="Response format: json")
):
    """
    Get the latest cached preview for today.

    Returns the most recently cached HTML or JSON preview if it's within the TTL window.
    If no cached version exists or it's expired, returns a 404.
    """
    _require_api_key_if_configured(request)

    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")

    # Try to get cached data
    cache = get_preview_cache()
    cached_data = cache.get(mailbox, today)

    if cached_data is None:
        raise HTTPException(status_code=404, detail="No cached preview available for today")

    # Check if JSON format is requested
    accept_json = request.headers.get("accept", "").startswith("application/json")
    format_json = format == "json"
    path_json = request.url.path.endswith(".json")

    if accept_json or format_json or path_json:
        # Return JSON response from cached context
        context = cached_data['context']

        # Convert meetings to Pydantic models (context["meetings"] are already dicts from cache)
        meetings = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]

        # Build response model (research_trace from cached context if present)
        response = DigestPreviewModel(
            ok=True,
            source=context["source"],
            date_human=context["date_human"],
            exec_name=context["exec_name"],
            meetings=meetings,
            research_trace=context.get("research_trace"),
        )

        return JSONResponse(content=response.model_dump())
    else:
        # Return HTML response from cache or generate from context
        if cached_data['html']:
            return HTMLResponse(content=cached_data['html'])
        else:
            # Generate HTML from cached context
            context = cached_data['context']
            # Convert dict meetings back to objects for rendering
            context["meetings"] = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]
            context["request"] = request
            html = render_digest_html(context)
            return HTMLResponse(content=html)


@router.get("/preview.json")
async def preview_digest_json(
    request: Request,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today if omitted."),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile")
):
    """
    Preview the digest as JSON.

    Returns the structured digest model that the template uses.

    The date parameter allows previewing any single date (past or future) in YYYY-MM-DD format.
    If omitted, defaults to today's date.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Validate date format
    _validate_date(date)

    # Build context using shared context builder (research allowed only here and run-digest/digest send)
    request_id = str(uuid.uuid4())
    research_budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    research_enabled_env = (os.getenv("RESEARCH_ENABLED") or "").strip().lower() in ("true", "1", "yes")
    settings = {
        "app_env": os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development",
        "research_enabled": research_enabled_env,
    }
    allow_research = should_run_research(request, settings)
    context = build_digest_context_with_provider(
        source=source,
        date=date,
        exec_name=exec_name,
        mailbox=mailbox,
        allow_research=allow_research,
        research_budget=research_budget,
        request_id=request_id,
    )

    # Convert meetings to Pydantic models
    meetings = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]

    # Build response model (include research_trace for dev/debug; non-PII only)
    response = DigestPreviewModel(
        ok=True,
        source=context["source"],
        date_human=context["date_human"],
        exec_name=context["exec_name"],
        meetings=meetings,
        research_trace=context.get("research_trace"),
    )

    # Cache the result if it's for today (same as HTML preview)
    if date is None or date == datetime.now().strftime("%Y-%m-%d"):
        cache = get_preview_cache()
        # Convert context to serializable format
        context_for_cache = {
            "source": context["source"],
            "date_human": context["date_human"],
            "exec_name": context["exec_name"],
            "meetings": [meeting.model_dump() for meeting in meetings]  # Convert to dict
        }
        # For JSON endpoint, we cache the context but not the HTML
        # The latest endpoint will generate HTML from the cached context
        cache_date = date or datetime.now().strftime("%Y-%m-%d")
        cache.set(mailbox, cache_date, "", context_for_cache)

    return JSONResponse(content=response.model_dump())


@router.get("/preview/event/{event_id}.json")
async def preview_single_event_json(
    request: Request,
    event_id: str,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today if omitted."),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile")
):
    """
    Preview a single event by ID as JSON.

    Returns the structured event model that the template uses.

    The date parameter allows previewing events from a specific date (past or future) in YYYY-MM-DD format.
    If omitted, defaults to today's date.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Validate date format
    _validate_date(date)

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

    # Build response model (single event may not have research_trace)
    response = DigestPreviewModel(
        ok=True,
        source=context["source"],
        date_human=context["date_human"],
        exec_name=context["exec_name"],
        meetings=meetings,
        research_trace=context.get("research_trace"),
    )

    return JSONResponse(content=response.model_dump())


@router.get("/preview/event/{event_id}")
async def preview_single_event_html(
    request: Request,
    event_id: str,
    source: Literal["sample", "live"] = Query("sample", description="Data source: sample or live"),
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today if omitted."),
    exec_name: Optional[str] = Query(None, description="Override header label"),
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile"),
    format: Optional[str] = Query(None, description="Response format: json")
):
    """
    Preview a single event by ID as HTML or JSON.

    Returns HTML by default, or JSON if format=json or Accept: application/json.

    The date parameter allows previewing events from a specific date (past or future) in YYYY-MM-DD format.
    If omitted, defaults to today's date.
    """
    _require_api_key_if_configured(request)

    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Validate date format
    _validate_date(date)

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


@router.get("/preview/latest")
@router.get("/preview/latest.json")
async def preview_digest_latest(
    request: Request,
    mailbox: Optional[str] = Query(None, description="Mailbox address to determine profile"),
    format: Optional[str] = Query(None, description="Response format: json")
):
    """
    Get the latest cached preview for today.

    Returns the most recently cached HTML or JSON preview if it's within the TTL window.
    If no cached version exists or it's expired, returns a 404.
    """
    _require_api_key_if_configured(request)

    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")

    # Try to get cached data
    cache = get_preview_cache()
    cached_data = cache.get(mailbox, today)

    if cached_data is None:
        raise HTTPException(status_code=404, detail="No cached preview available for today")

    # Check if JSON format is requested
    accept_json = request.headers.get("accept", "").startswith("application/json")
    format_json = format == "json"
    path_json = request.url.path.endswith(".json")

    if accept_json or format_json or path_json:
        # Return JSON response from cached context
        context = cached_data['context']

        # Convert meetings to Pydantic models (context["meetings"] are already dicts from cache)
        meetings = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]

        # Build response model (research_trace from cached context if present)
        response = DigestPreviewModel(
            ok=True,
            source=context["source"],
            date_human=context["date_human"],
            exec_name=context["exec_name"],
            meetings=meetings,
            research_trace=context.get("research_trace"),
        )

        return JSONResponse(content=response.model_dump())
    else:
        # Return HTML response from cache or generate from context
        if cached_data['html']:
            return HTMLResponse(content=cached_data['html'])
        else:
            # Generate HTML from cached context
            context = cached_data['context']
            # Convert dict meetings back to objects for rendering
            context["meetings"] = [_convert_meeting_to_model(meeting) for meeting in context["meetings"]]
            context["request"] = request
            html = render_digest_html(context)
            return HTMLResponse(content=html)


