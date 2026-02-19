"""
POST /run-digest: run the digest pipeline and return run result JSON.
Requires X-API-Key header matching INTERNAL_API_KEY.
"""
import logging
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import load_config
from app.rendering.context_builder import build_digest_context_with_provider
from app.rendering.digest_renderer import render_digest_html
from app.research.config import MAX_TAVILY_CALLS_PER_REQUEST, ResearchBudget
from app.rendering.plaintext import render_plaintext

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_MAILBOX = "sorum.crofts@rpck.com"
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")


def _today_yyyymmdd() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")


def _require_internal_api_key(request: Request) -> None:
    cfg = load_config()
    if not cfg.internal_api_key:
        raise HTTPException(status_code=403, detail="INTERNAL_API_KEY not configured")
    provided = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if provided != cfg.internal_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key")


class RunDigestBody(BaseModel):
    mailbox: str = Field(default=DEFAULT_MAILBOX, description="Mailbox for profile/calendar")
    date: str | None = Field(default=None, description="Date YYYY-MM-DD; default today (America/New_York)")
    source: str = Field(default="live", description="'live' or 'stub'")


@router.post("/run-digest")
async def run_digest(
    request: Request,
    body: RunDigestBody,
    include_html: bool = Query(False, description="Include digest_html in response"),
):
    _require_internal_api_key(request)

    run_id = str(uuid.uuid4())
    mailbox = body.mailbox or DEFAULT_MAILBOX
    date = body.date or _today_yyyymmdd()
    source = body.source if body.source in ("live", "stub") else "live"

    try:
        research_budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
        context = build_digest_context_with_provider(
            source=source,
            date=date,
            mailbox=mailbox,
            allow_research=True,
            research_budget=research_budget,
            request_id=run_id,
        )
    except HTTPException as e:
        logger.info(
            "run_digest run_id=%s mailbox=%s date=%s source=%s meeting_count=0 status=error status_code=%s",
            run_id,
            mailbox,
            date,
            source,
            e.status_code,
        )
        raise

    meetings = context.get("meetings", [])
    meeting_count = len(meetings)

    plaintext = render_plaintext(context)
    digest_text_preview = plaintext[:2000] if len(plaintext) > 2000 else plaintext

    response_payload = {
        "run_id": run_id,
        "status": "ok",
        "mailbox": mailbox,
        "date": date,
        "meeting_count": meeting_count,
        "digest_text_preview": digest_text_preview,
    }
    if include_html:
        html = render_digest_html(context)
        response_payload["digest_html"] = html

    logger.info(
        "run_digest run_id=%s mailbox=%s date=%s source=%s meeting_count=%s status=ok status_code=200",
        run_id,
        mailbox,
        date,
        source,
        meeting_count,
    )
    return JSONResponse(status_code=200, content=response_payload)
