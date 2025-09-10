from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from zoneinfo import ZoneInfo
import os

from app.schemas.digest import DigestSendRequest, DigestSendResponse
from app.services.emailer import select_emailer_from_env
from app.rendering.digest_renderer import render_digest_html
from app.data.sample_digest import SAMPLE_MEETINGS
from app.core.config import load_config


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
    return os.getenv("DEFAULT_SENDER", "gary@rpck.com")


def _assemble_live_meetings() -> list:
    # Placeholder for future live assembly; return empty to trigger fallback
    return []


@router.get("/send")
async def get_send_digest(request: Request, send: bool = False, recipients: list[str] | None = None, subject: str | None = None, source: str | None = "sample"):
    _require_api_key_if_configured(request)
    body = DigestSendRequest(send=send, recipients=recipients, subject=subject, source=source)  # type: ignore[arg-type]
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
    meetings = SAMPLE_MEETINGS if data_source == "sample" else (_assemble_live_meetings() or SAMPLE_MEETINGS)

    context = {
        "request": request,
        "meetings": meetings,
        "exec_name": "Biz Dev",
        "date_human": _today_et_str(_get_timezone()),
        "current_year": datetime.now().strftime("%Y"),
    }
    html = render_digest_html(context)

    recipients_final = _get_default_recipients()
    if body.recipients is not None and _allow_override():
        recipients_final = [str(r) for r in body.recipients]

    if not recipients_final:
        recipients_final = []

    subject_final = body.subject or _default_subject()

    action = "rendered"
    message_id: str | None = None
    driver_used = os.getenv("MAIL_DRIVER", "console").lower()
    if body.send:
        emailer = select_emailer_from_env()
        message_id = emailer.send(subject=subject_final, html=html, recipients=recipients_final, sender=_get_sender())
        action = "sent"

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


@router.get("/preview")
async def preview_digest_html(request: Request, source: str | None = "sample"):
    _require_api_key_if_configured(request)
    data_source = source or "sample"
    meetings = SAMPLE_MEETINGS if data_source == "sample" else (_assemble_live_meetings() or SAMPLE_MEETINGS)
    context = {
        "request": request,
        "meetings": meetings,
        "exec_name": "Biz Dev",
        "date_human": _today_et_str(_get_timezone()),
        "current_year": datetime.now().strftime("%Y"),
    }
    html = render_digest_html(context)
    return JSONResponse({"ok": True, "html": html, "source": data_source})


@router.get("/preview.json")
async def preview_digest_json(request: Request, source: str | None = "sample"):
    _require_api_key_if_configured(request)
    data_source = source or "sample"
    meetings = SAMPLE_MEETINGS if data_source == "sample" else (_assemble_live_meetings() or SAMPLE_MEETINGS)
    return JSONResponse({"ok": True, "meetings": meetings, "source": data_source})
