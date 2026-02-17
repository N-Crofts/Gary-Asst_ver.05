"""
Debug endpoint to test calendar access directly.
"""
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime

from app.calendar.provider import select_calendar_provider, fetch_events_range
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
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today."),
    start: Optional[str] = Query(None, description="Start datetime (ISO 8601). Use with 'end' parameter."),
    end: Optional[str] = Query(None, description="End datetime (ISO 8601). Use with 'start' parameter."),
    mailbox: Optional[str] = Query(None, description="Mailbox address to query. Defaults to MAILBOX_ADDRESS or MS_USER_EMAIL.")
):
    """
    Debug endpoint to test calendar provider directly.

    Returns detailed information about calendar fetching including:
    - Provider type
    - Configuration
    - Events found with raw Graph data and parsed ET times
    - Any errors

    Supports:
    - Single date: ?date=YYYY-MM-DD
    - Date range: ?start=ISO&end=ISO
    - Mailbox selection: ?mailbox=user@example.com
    """
    _require_api_key_if_configured(request)

    import os
    import logging
    from zoneinfo import ZoneInfo
    
    logger = logging.getLogger(__name__)

    # Determine which mailbox to use
    mailbox_to_use = mailbox
    if not mailbox_to_use:
        mailbox_to_use = os.getenv("MAILBOX_ADDRESS") or os.getenv("MS_USER_EMAIL")

    debug_info = {
        "calendar_provider": os.getenv("CALENDAR_PROVIDER", "mock"),
        "ms_tenant_id": "SET" if os.getenv("MS_TENANT_ID") or os.getenv("AZURE_TENANT_ID") else "NOT SET",
        "ms_client_id": "SET" if os.getenv("MS_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") else "NOT SET",
        "ms_client_secret": "SET" if os.getenv("MS_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") else "NOT SET",
        "ms_user_email": os.getenv("MS_USER_EMAIL") or "NOT SET",
        "mailbox_address": os.getenv("MAILBOX_ADDRESS") or "NOT SET",
        "mailbox_requested": mailbox_to_use or "NOT SET",
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
            if hasattr(provider, 'allowed_mailboxes'):
                debug_info["adapter_allowed_mailboxes"] = provider.allowed_mailboxes
            if hasattr(provider, 'tenant_id'):
                tenant_id = provider.tenant_id
                debug_info["adapter_tenant_id"] = f"{tenant_id[:8]}...{tenant_id[-8:]}" if len(tenant_id) > 16 else tenant_id

        # Determine query type
        if start and end:
            # ISO datetime range query
            try:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                debug_info["query_type"] = "datetime_range"
                debug_info["start"] = start
                debug_info["end"] = end
                
                if hasattr(provider, 'fetch_events_between'):
                    if not mailbox_to_use:
                        raise ValueError("Mailbox must be specified for datetime range queries")
                    events = provider.fetch_events_between(mailbox_to_use, start_dt, end_dt)
                else:
                    raise ValueError("Provider does not support fetch_events_between")
            except ValueError as e:
                debug_info["error"] = f"Invalid datetime format or missing mailbox: {e}"
                return JSONResponse(content=debug_info, status_code=422)
        else:
            # Single date query
            test_date = date or datetime.now().strftime("%Y-%m-%d")
            debug_info["query_type"] = "date"
            debug_info["date"] = test_date
            # Use mailbox parameter if provided, otherwise use default
            events = provider.fetch_events(test_date, user=mailbox_to_use)

        debug_info["event_count"] = len(events)
        debug_info["events"] = [
            {
                "subject": e.subject,
                "start_time": e.start_time,  # ISO string in ET
                "end_time": e.end_time,      # ISO string in ET
                "location": e.location,
                "attendee_count": len(e.attendees),
                "attendees": [
                    {
                        "name": a.name,
                        "email": a.email,
                        "title": a.title,
                        "company": a.company
                    }
                    for a in e.attendees
                ],
                "notes": e.notes
            }
            for e in events
        ]

    except Exception as e:
        logger.error(f"Debug calendar error: {e}", exc_info=True)
        debug_info["error"] = str(e)
        debug_info["error_type"] = type(e).__name__
        if hasattr(e, 'detail'):
            debug_info["error_detail"] = str(e.detail)

    return JSONResponse(content=debug_info)


@router.get("/debug/calendar/events")
async def debug_calendar_events(
    request: Request,
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD). Defaults to today."),
    start_date: Optional[str] = Query(None, description="Start date for range query (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for range query (YYYY-MM-DD)"),
    user: Optional[str] = Query(None, description="User email to filter events for specific user")
):
    """
    Get all calendar events with full details.
    
    Can query a single date or a date range.
    Returns complete event information including all attendees.
    """
    _require_api_key_if_configured(request)

    import logging
    logger = logging.getLogger(__name__)

    # Determine date range
    if start_date and end_date:
        # Range query
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD")
        
        test_date = None
        use_range = True
    elif date:
        # Single date query
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD")
        test_date = date
        use_range = False
    else:
        # Default to today
        test_date = datetime.now().strftime("%Y-%m-%d")
        use_range = False

    result = {
        "query": {
            "date": test_date,
            "start_date": start_date,
            "end_date": end_date,
            "user": user,
            "use_range": use_range
        },
        "events": [],
        "event_count": 0,
        "error": None
    }

    try:
        provider = select_calendar_provider()
        
        if use_range:
            events = fetch_events_range(provider, start_date, end_date, user=user)
        else:
            events = provider.fetch_events(test_date, user=user)
        
        result["event_count"] = len(events)
        result["events"] = [
            {
                "subject": e.subject,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "location": e.location,
                "notes": e.notes,
                "attendees": [
                    {
                        "name": a.name,
                        "email": a.email,
                        "title": a.title,
                        "company": a.company
                    }
                    for a in e.attendees
                ],
                "attendee_count": len(e.attendees)
            }
            for e in events
        ]

    except Exception as e:
        logger.error(f"Debug calendar events error: {e}", exc_info=True)
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        if hasattr(e, 'detail'):
            result["error_detail"] = str(e.detail)

    return JSONResponse(content=result)

