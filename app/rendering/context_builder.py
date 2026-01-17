from datetime import datetime
from typing import Dict, Any, Literal, Optional, List

from app.calendar.provider import select_calendar_provider
from app.data.sample_digest import SAMPLE_MEETINGS
from app.rendering.digest_renderer import _today_et_str, _format_date_et_str, _get_timezone
from app.enrichment.service import enrich_meetings
from app.profile.store import get_profile
from app.memory.service import attach_memory_to_meetings


def _format_time_for_display(iso_time: str) -> str:
    """Format ISO time string for display in digest."""
    try:
        # Extract time part (HH:MM)
        time_part = iso_time.split("T")[1].split("-")[0][:5]
        hour, minute = time_part.split(":")
        hour_int = int(hour)

        # Convert to 12-hour format
        if hour_int == 0:
            return f"12:{minute} AM ET"
        elif hour_int < 12:
            return f"{hour_int}:{minute} AM ET"
        elif hour_int == 12:
            return f"12:{minute} PM ET"
        else:
            return f"{hour_int - 12}:{minute} PM ET"
    except (ValueError, IndexError):
        # Fallback to original time if parsing fails
        return iso_time


def _apply_company_aliases(meetings: list[dict], aliases: Dict[str, List[str]]) -> list[dict]:
    """Apply company aliases to canonicalize company names for enrichment."""
    if not aliases:
        return meetings

    # Create reverse lookup: alias -> canonical name
    alias_to_canonical = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            alias_to_canonical[alias.lower()] = canonical.lower()

    for meeting in meetings:
        # Check company field
        if meeting.get("company") and isinstance(meeting["company"], dict):
            company_name = meeting["company"].get("name", "").lower()
            if company_name in alias_to_canonical:
                meeting["company"]["name"] = alias_to_canonical[company_name].title()

        # Check attendees for company names
        for attendee in meeting.get("attendees", []):
            if attendee.get("company"):
                company_name = attendee["company"].lower()
                if company_name in alias_to_canonical:
                    attendee["company"] = alias_to_canonical[company_name].title()

    return meetings


def _trim_meeting_sections(meetings: list, max_items: Dict[str, int]) -> list:
    """Trim meeting sections to respect max_items limits."""
    for meeting in meetings:
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'model_dump'):
            # Pydantic model - convert to dict, trim, then back to model
            meeting_dict = meeting.model_dump()
            for section, max_count in max_items.items():
                if section in meeting_dict and isinstance(meeting_dict[section], list):
                    meeting_dict[section] = meeting_dict[section][:max_count]

            # Update the model with trimmed data
            for section, max_count in max_items.items():
                if section in meeting_dict and isinstance(meeting_dict[section], list):
                    setattr(meeting, section, meeting_dict[section])
        else:
            # Regular dict
            for section, max_count in max_items.items():
                if section in meeting and isinstance(meeting[section], list):
                    meeting[section] = meeting[section][:max_count]

    return meetings


def _map_events_to_meetings(events: list[dict] | list) -> list[dict]:
    meetings: list[dict] = []
    for e in events:
        # e is a pydantic model dict-like; support both dict and model
        subject = getattr(e, "subject", None) or e.get("subject", "")
        start_time = getattr(e, "start_time", None) or e.get("start_time", "")
        location = getattr(e, "location", None) or e.get("location")
        attendees_raw = getattr(e, "attendees", None) or e.get("attendees", [])
        attendees = []
        for a in attendees_raw:
            name = getattr(a, "name", None) or a.get("name", "")
            title = getattr(a, "title", None) or a.get("title")
            company = getattr(a, "company", None) or a.get("company")
            attendees.append({"name": name, "title": title, "company": company})

        meetings.append(
            {
                "subject": subject,
                # For MVP, show only time component in ET readable form; use ISO string's time
                "start_time": _format_time_for_display(start_time) if "T" in start_time else start_time,
                "location": location,
                "attendees": attendees,
                "company": None,
                "news": [],
                "talking_points": [],
                "smart_questions": [],
            }
        )
    return meetings


def build_digest_context_with_provider(
    source: Literal["sample", "live"],
    date: Optional[str] = None,
    exec_name: Optional[str] = None,
    mailbox: Optional[str] = None,
) -> Dict[str, Any]:
    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    # Load executive profile (use mailbox if provided)
    profile = get_profile(mailbox=mailbox)

    actual_source = "live"
    meetings: list[dict] = []

    if source == "live":
        try:
            provider = select_calendar_provider()
            events = provider.fetch_events(requested_date)
            if events:
                meetings = _map_events_to_meetings([e.model_dump() for e in events])
                actual_source = "live"
            else:
                # No events for this date - meetings will be empty
                meetings = []
                actual_source = "live"
        except Exception as e:
            # Provider error - log and return empty meetings
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to fetch calendar events for {requested_date}: {e}", exc_info=True)
            meetings = []
            actual_source = "live"
    else:
        # Sample mode - use sample data
        meetings = SAMPLE_MEETINGS
        actual_source = "sample"

    # Apply company aliases before enrichment
    meetings = _apply_company_aliases(meetings, profile.company_aliases)

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    # Apply profile max_items limits
    meetings_trimmed = _trim_meeting_sections(meetings_enriched, profile.max_items)

    # Attach memory data (past meetings) to each meeting
    meetings_with_memory = attach_memory_to_meetings(meetings_trimmed)

    # Format date_human based on requested date (or today if not specified)
    tz_name = _get_timezone()
    if requested_date:
        date_human = _format_date_et_str(requested_date, tz_name)
        # Extract year from requested date for current_year
        try:
            date_obj = datetime.strptime(requested_date, "%Y-%m-%d")
            current_year = date_obj.strftime("%Y")
        except ValueError:
            current_year = datetime.now().strftime("%Y")
    else:
        date_human = _today_et_str(tz_name)
        current_year = datetime.now().strftime("%Y")

    context = {
        "meetings": meetings_with_memory,
        "date_human": date_human,
        "current_year": current_year,
        "exec_name": exec_name or profile.exec_name,  # Use profile default unless overridden
        "source": actual_source,
    }
    return context


def build_single_event_context(
    event_id: str,
    source: Literal["sample", "live"] = "sample",
    date: Optional[str] = None,
    exec_name: Optional[str] = None,
    mailbox: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context for a single event by ID.

    Args:
        event_id: The ID of the event to fetch
        source: Data source ("sample" or "live")
        date: Optional date for live data
        exec_name: Optional executive name override
        mailbox: Optional mailbox to determine profile

    Returns:
        Context dictionary with single meeting
    """
    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    # Load executive profile (use mailbox if provided)
    profile = get_profile(mailbox=mailbox)

    actual_source = "sample"
    meeting: Optional[dict] = None

    if source == "live":
        try:
            provider = select_calendar_provider()
            # For now, we'll fetch all events and find by ID
            # In a real implementation, the provider would have a fetch_event_by_id method
            events = provider.fetch_events(requested_date)
            if events:
                # Find event by ID (assuming event has an 'id' field)
                for event in events:
                    event_dict = event.model_dump() if hasattr(event, 'model_dump') else event
                    if event_dict.get('id') == event_id:
                        meetings = _map_events_to_meetings([event_dict])
                        if meetings:
                            meeting = meetings[0]
                            actual_source = "live"
                        break
        except Exception:
            # Fallback to sample on any provider error
            pass

    # If no meeting found in live data, try sample data
    if not meeting:
        # For sample data, we'll use a simple ID mapping
        # In a real implementation, sample data would have proper IDs
        if event_id == "sample-1" or event_id == "1":
            meeting = SAMPLE_MEETINGS[0].copy() if SAMPLE_MEETINGS else None
        else:
            # Create a basic meeting structure for unknown IDs
            meeting = {
                "subject": f"Meeting {event_id}",
                "start_time": "9:00 AM ET",
                "location": "Not specified",
                "attendees": [],
                "company": None,
                "news": [],
                "talking_points": [],
                "smart_questions": [],
            }

    if not meeting:
        # Create a minimal meeting structure for missing events
        meeting = {
            "subject": "Meeting not found",
            "start_time": "Not available",
            "location": "Not available",
            "attendees": [],
            "company": None,
            "news": [],
            "talking_points": [],
            "smart_questions": [],
        }

    # Apply company aliases before enrichment
    meetings = [meeting]
    meetings = _apply_company_aliases(meetings, profile.company_aliases)

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    # Apply profile max_items limits
    meetings_trimmed = _trim_meeting_sections(meetings_enriched, profile.max_items)

    # Attach memory data (past meetings) to each meeting
    meetings_with_memory = attach_memory_to_meetings(meetings_trimmed)

    # Format date_human based on requested date (or today if not specified)
    tz_name = _get_timezone()
    if requested_date:
        date_human = _format_date_et_str(requested_date, tz_name)
        # Extract year from requested date for current_year
        try:
            date_obj = datetime.strptime(requested_date, "%Y-%m-%d")
            current_year = date_obj.strftime("%Y")
        except ValueError:
            current_year = datetime.now().strftime("%Y")
    else:
        date_human = _today_et_str(tz_name)
        current_year = datetime.now().strftime("%Y")

    context = {
        "meetings": meetings_with_memory,
        "date_human": date_human,
        "current_year": current_year,
        "exec_name": exec_name or profile.exec_name,
        "source": actual_source,
        "event_id": event_id,  # Include event ID in context for reference
    }
    return context


