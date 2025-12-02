from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Literal, Optional
from datetime import datetime

from app.calendar.provider import select_calendar_provider, fetch_events_range
from app.calendar.types import Event
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


def _validate_date(date_str: str) -> str:
    """Validate date string format (YYYY-MM-DD)."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format: '{date_str}'. Expected format: YYYY-MM-DD (e.g., 2025-12-05)"
        )


def _event_matches_criteria(event: Event, email: Optional[str] = None, domain: Optional[str] = None, name: Optional[str] = None) -> bool:
    """
    Check if an event matches the search criteria.

    Priority: email (exact match) > domain > name (case-insensitive contains)
    """
    if not event.attendees:
        return False

    # Check email first (exact match, case-insensitive)
    if email:
        email_lower = email.lower()
        for attendee in event.attendees:
            if attendee.email and attendee.email.lower() == email_lower:
                return True
        return False

    # Check domain (case-insensitive)
    if domain:
        domain_lower = domain.lower().lstrip('@')  # Remove leading @ if present
        for attendee in event.attendees:
            if attendee.email:
                attendee_domain = attendee.email.split('@')[-1].lower() if '@' in attendee.email else None
                if attendee_domain == domain_lower:
                    return True
        return False

    # Check name (case-insensitive contains)
    if name:
        name_lower = name.lower()
        for attendee in event.attendees:
            if attendee.name and name_lower in attendee.name.lower():
                return True
        return False

    return False


def _event_to_match_dict(event: Event, date: str) -> dict:
    """Convert an Event to a match dictionary for the search response."""
    # Extract event ID from subject or generate one
    event_id = f"{date}-{event.subject[:50]}"  # Simple ID based on date and subject

    return {
        "event_id": event_id,
        "date": date,
        "start_time": event.start_time,
        "subject": event.subject,
        "attendees": [
            {
                "name": attendee.name,
                "email": attendee.email,
                "title": attendee.title,
                "company": attendee.company
            }
            for attendee in event.attendees
        ],
        "location": event.location,
        "notes": event.notes
    }


@router.get("/search")
async def search_person(
    request: Request,
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    email: Optional[str] = Query(None, description="Exact email match (preferred)"),
    domain: Optional[str] = Query(None, description="Domain match (e.g., company.com)"),
    name: Optional[str] = Query(None, description="Name match (case-insensitive contains)"),
    source: Literal["live", "sample"] = Query("live", description="Data source: live or sample")
):
    """
    Search for meetings with a specific person across a date range.

    Filters by email (exact match), domain, or name (case-insensitive contains).
    Priority: email > domain > name.

    Returns JSON with matches array and count.
    """
    _require_api_key_if_configured(request)

    # Validate dates
    start_date = _validate_date(start)
    end_date = _validate_date(end)

    # Validate date range
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if start_dt > end_dt:
            raise HTTPException(
                status_code=422,
                detail=f"Start date ({start_date}) must be before or equal to end date ({end_date})"
            )
    except ValueError:
        pass  # Already validated above

    # Validate that at least one filter is provided
    if not email and not domain and not name:
        raise HTTPException(
            status_code=422,
            detail="At least one filter must be provided: email, domain, or name"
        )

    # Fetch events based on source
    all_events = []

    if source == "live":
        try:
            provider = select_calendar_provider()
            all_events = fetch_events_range(provider, start_date, end_date)
        except Exception as exc:
            # Return empty results on error rather than failing
            all_events = []
    else:
        # Sample source - use mock provider with sample data
        try:
            from app.calendar.mock_provider import MockCalendarProvider
            provider = MockCalendarProvider()
            all_events = fetch_events_range(provider, start_date, end_date)
        except Exception as exc:
            # Return empty results on error
            all_events = []

    # Filter events by criteria
    matches = []
    seen_events = set()  # To avoid duplicates

    for event in all_events:
        if _event_matches_criteria(event, email=email, domain=domain, name=name):
            # Extract date from event start_time
            try:
                # Parse the start_time to get the date
                if "T" in event.start_time:
                    event_date = event.start_time.split("T")[0]
                else:
                    # Fallback: use start_date if parsing fails
                    event_date = start_date
            except Exception:
                event_date = start_date

            # Create a unique key for deduplication
            event_key = (event_date, event.subject, event.start_time)
            if event_key not in seen_events:
                seen_events.add(event_key)
                matches.append(_event_to_match_dict(event, event_date))

    # Sort matches by date, then by start_time
    matches.sort(key=lambda x: (x["date"], x["start_time"]))

    return JSONResponse(content={
        "ok": True,
        "matches": matches,
        "count": len(matches)
    })

