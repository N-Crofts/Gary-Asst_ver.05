import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from app.schemas.digest import DigestSendRequest, DigestSendResponse
from app.services.emailer import select_emailer_from_env
from app.rendering.digest_renderer import render_digest_html
from app.rendering.plaintext import render_plaintext
from app.rendering.context_builder import build_digest_context_with_provider
from app.data.sample_digest import SAMPLE_MEETINGS
from app.research.config import MAX_TAVILY_CALLS_PER_REQUEST, ResearchBudget
from app.core.config import load_config
from app.observability.logger import log_event, timing
from app.routes.health import update_last_run


router = APIRouter()


def _today_et_str(tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    day = str(int(now.strftime("%d")))
    return f"{now.strftime('%a')}, {now.strftime('%b')} {day}, {now.strftime('%Y')}"


def _get_timezone() -> str:
    return os.getenv("TIMEZONE", "America/New_York")


def _default_subject() -> str:
    return f"RPCK – Morning Briefing: {_today_et_str(_get_timezone())}"


def _get_default_recipients() -> list[str]:
    raw = os.getenv("DEFAULT_RECIPIENTS", "")
    recipients = [r.strip() for r in raw.split(",") if r.strip()]
    return recipients


def _allow_override() -> bool:
    return os.getenv("ALLOW_RECIPIENT_OVERRIDE", "false").lower() == "true"


def _get_sender() -> str:
    return os.getenv("DEFAULT_SENDER", "gary-asst@rpck.com")


def _assemble_live_meetings() -> list:
    # Placeholder for future live assembly; return empty to trigger fallback
    return []


def _build_digest_context() -> dict:
    """Build digest context for scheduled sending."""
    meetings = SAMPLE_MEETINGS  # For now, use sample data

    return {
        "request": None,
        "meetings": meetings,
        "exec_name": "Biz Dev",
        "date_human": _today_et_str(_get_timezone()),
        "current_year": datetime.now().strftime("%Y"),
    }


@router.get("/send")
async def get_send_digest(request: Request, send: bool = False, recipients: list[str] | None = None, subject: str | None = None, source: str | None = "sample", mailbox: str | None = None):
    _require_api_key_if_configured(request)
    body = DigestSendRequest(send=send, recipients=recipients, subject=subject, source=source, mailbox=mailbox)  # type: ignore[arg-type]
    return await _handle_send(request, body)


@router.post("/send")
async def post_send_digest(request: Request, body: DigestSendRequest):
    _require_api_key_if_configured(request)
    return await _handle_send(request, body)


async def _handle_send(request: Request, body: DigestSendRequest):
    if body.source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    if body.recipients is not None and not _allow_override():
        raise HTTPException(status_code=400, detail="Recipient override not allowed")

    data_source = body.source or "sample"

    # Build context using the context builder (research allowed for digest send)
    request_id = str(uuid.uuid4())
    research_budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    context = build_digest_context_with_provider(
        source=data_source,
        mailbox=body.mailbox,
        allow_research=True,
        research_budget=research_budget,
        request_id=request_id,
    )
    context["request"] = request

    html = render_digest_html(context)
    plaintext = render_plaintext(context)

    # Get profile for default recipients
    from app.profile.store import get_profile
    profile = get_profile(mailbox=body.mailbox)
    recipients_final = profile.default_recipients
    if body.recipients is not None and _allow_override():
        recipients_final = [str(r) for r in body.recipients]

    if not recipients_final:
        recipients_final = []

    subject_final = body.subject or _default_subject()

    action = "rendered"
    message_id: str | None = None
    driver_used = os.getenv("MAIL_DRIVER", "console").lower()

    # Time the email sending operation
    with timing("digest_send") as timer:
        if body.send:
            emailer = select_emailer_from_env()
            message_id = emailer.send(subject=subject_final, html=html, recipients=recipients_final, sender=_get_sender(), plaintext=plaintext)
            action = "sent"

    # Log the event with structured data
    log_event(
        action=action,
        driver=driver_used,
        source=data_source,
        subject=subject_final,
        recipients_count=len(recipients_final),
        message_id=message_id,
        duration_ms=timer.get_duration_ms(),
    )

    # Update last run information for health endpoint
    update_last_run(
        action=action,
        driver=driver_used,
        source=data_source,
        subject=subject_final,
        recipients_count=len(recipients_final),
        message_id=message_id,
        duration_ms=timer.get_duration_ms(),
        success=True,
    )

    response = DigestSendResponse(
        ok=True,
        action=action,
        subject=subject_final,
        recipients=recipients_final,
        message_id=message_id,
        preview_chars=len(html),
        driver=driver_used,  # type: ignore[arg-type]
        source=data_source,  # type: ignore[arg-type]
    )
    return JSONResponse(status_code=200, content=response.dict())


def _require_api_key_if_configured(request: Request) -> None:
    cfg = load_config()
    if not cfg.api_key:
        return
    provided = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if provided != cfg.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


