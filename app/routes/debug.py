"""
Debug endpoint to test calendar access directly.
"""
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime

from app.calendar.provider import select_calendar_provider
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


@router.get("/debug/calendar")
async def debug_calendar(
    request: Request,
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today.")
):
    """
    Debug endpoint to test calendar provider directly.

    Returns detailed information about calendar fetching including:
    - Provider type
    - Configuration
    - Events found
    - Any errors
    """
    _require_api_key_if_configured(request)

    import os
    import logging
    logger = logging.getLogger(__name__)

    # Get date
    test_date = date or datetime.now().strftime("%Y-%m-%d")

    debug_info = {
        "date": test_date,
        "calendar_provider": os.getenv("CALENDAR_PROVIDER", "mock"),
        "ms_tenant_id": "SET" if os.getenv("MS_TENANT_ID") or os.getenv("AZURE_TENANT_ID") else "NOT SET",
        "ms_client_id": "SET" if os.getenv("MS_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") else "NOT SET",
        "ms_client_secret": "SET" if os.getenv("MS_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") else "NOT SET",
        "ms_user_email": os.getenv("MS_USER_EMAIL") or "NOT SET",
        "allowed_mailbox_group": os.getenv("ALLOWED_MAILBOX_GROUP") or "NOT SET",
        "events": [],
        "error": None,
        "event_count": 0
    }

    try:
        provider = select_calendar_provider()
        debug_info["provider_type"] = type(provider).__name__

        # If it's MS Graph adapter, get more details
        if hasattr(provider, 'user_email'):
            debug_info["adapter_user_email"] = provider.user_email
            debug_info["adapter_allowed_group"] = provider.allowed_mailbox_group
            # Log tenant_id for debugging (first 8 and last 8 chars only for security)
            if hasattr(provider, 'tenant_id'):
                tenant_id = provider.tenant_id
                debug_info["adapter_tenant_id"] = f"{tenant_id[:8]}...{tenant_id[-8:]}" if len(tenant_id) > 16 else tenant_id
                debug_info["adapter_tenant_id_length"] = len(tenant_id)
                debug_info["adapter_tenant_id_repr"] = repr(tenant_id)

        events = provider.fetch_events(test_date)
        debug_info["event_count"] = len(events)
        debug_info["events"] = [
            {
                "subject": e.subject,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "location": e.location,
                "attendee_count": len(e.attendees)
            }
            for e in events
        ]

    except Exception as e:
        logger.error(f"Debug calendar error: {e}", exc_info=True)
        debug_info["error"] = str(e)
        debug_info["error_type"] = type(e).__name__
        # If it's an HTTPException, try to get more details
        if hasattr(e, 'detail'):
            debug_info["error_detail"] = str(e.detail)

    return JSONResponse(content=debug_info)

