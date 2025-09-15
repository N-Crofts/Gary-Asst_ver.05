import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.calendar.provider import select_calendar_provider
from app.calendar.types import Event
from app.profile.store import get_profile


def _lookback_days() -> int:
    """Get lookback days from environment variable."""
    try:
        return int(os.getenv("LOOKBACK_DAYS", "90"))
    except ValueError:
        return 90


def _memory_max_items() -> int:
    """Get max memory items from environment variable."""
    try:
        return int(os.getenv("MEMORY_MAX_ITEMS", "3"))
    except ValueError:
        return 3


def _canonicalize_company_name(company_name: str, aliases: Dict[str, List[str]]) -> str:
    """
    Canonicalize company name using profile aliases.

    Args:
        company_name: Raw company name
        aliases: Company aliases mapping from canonical to list of aliases

    Returns:
        Canonical company name
    """
    if not company_name or not aliases:
        return company_name

    company_lower = company_name.lower().strip()

    # Create reverse lookup: alias -> canonical name
    alias_to_canonical = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            alias_to_canonical[alias.lower()] = canonical.lower()

    # Check if this company name matches any alias
    if company_lower in alias_to_canonical:
        return alias_to_canonical[company_lower].title()

    # Check if any alias matches this company name
    for alias, canonical in alias_to_canonical.items():
        if alias in company_lower or company_lower in alias:
            return canonical.title()

    return company_name


def _extract_company_from_meeting(meeting: Dict[str, Any], aliases: Dict[str, List[str]]) -> Optional[str]:
    """
    Extract and canonicalize company name from a meeting.

    Args:
        meeting: Meeting data
        aliases: Company aliases for canonicalization

    Returns:
        Canonical company name or None
    """
    # Check company field directly
    company_field = meeting.get("company")
    if isinstance(company_field, dict) and company_field.get("name"):
        return _canonicalize_company_name(company_field["name"], aliases)

    # Check attendees for company names
    for attendee in meeting.get("attendees", []):
        if attendee.get("company"):
            return _canonicalize_company_name(attendee["company"], aliases)

    # Parse from subject: "RPCK × Company Name — Meeting"
    subject = meeting.get("subject", "")
    if "×" in subject:
        parts = subject.split("×")
        if len(parts) > 1:
            company_part = parts[1].split("—")[0].strip()
            return _canonicalize_company_name(company_part, aliases)

    return None


def _is_past_meeting(event: Event, current_date: str) -> bool:
    """
    Check if an event is in the past relative to current date.

    Args:
        event: Calendar event
        current_date: Current date in YYYY-MM-DD format

    Returns:
        True if event is in the past
    """
    try:
        # Parse event start time (should be in ET format)
        event_date = event.start_time.split("T")[0]  # Extract date part
        return event_date < current_date
    except (IndexError, AttributeError):
        return False


def _format_past_meeting(event: Event) -> Dict[str, Any]:
    """
    Format a past meeting for memory display.

    Args:
        event: Calendar event

    Returns:
        Formatted meeting data for memory
    """
    # Extract key attendees (limit to 2 for brevity)
    key_attendees = []
    for attendee in event.attendees[:2]:
        name = attendee.name
        if attendee.title:
            name = f"{name} ({attendee.title})"
        key_attendees.append(name)

    # Format date
    try:
        event_date = event.start_time.split("T")[0]  # Extract date part
        date_obj = datetime.strptime(event_date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%b %d, %Y")
    except (IndexError, ValueError):
        formatted_date = event.start_time

    return {
        "date": formatted_date,
        "subject": event.subject,
        "key_attendees": key_attendees
    }


def fetch_recent_meetings(events_today: List[Event], lookback_days: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch recent past meetings for companies/contacts in today's events.

    Args:
        events_today: Today's calendar events
        lookback_days: Number of days to look back (uses env var if None)

    Returns:
        Dictionary mapping canonical company names to list of past meetings
    """
    if not events_today:
        return {}

    lookback = lookback_days if lookback_days is not None else _lookback_days()
    max_items = _memory_max_items()

    # Get profile for company aliases
    profile = get_profile()
    aliases = profile.company_aliases

    # Extract companies from today's events
    companies_today = set()
    for event in events_today:
        # Convert event to meeting format for company extraction
        meeting_data = {
            "subject": event.subject,
            "attendees": [{"name": a.name, "company": a.company} for a in event.attendees],
            "company": None  # Events don't have company field directly
        }

        company = _extract_company_from_meeting(meeting_data, aliases)
        if company:
            companies_today.add(company)

    if not companies_today:
        return {}

    # Calculate date range for lookback
    current_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback)).strftime("%Y-%m-%d")

    # Fetch past events from calendar provider
    try:
        provider = select_calendar_provider()
        past_events = []

        # Fetch events for each day in the lookback period
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(current_date, "%Y-%m-%d")

        while current < end:
            day_events = provider.fetch_events(current.strftime("%Y-%m-%d"))
            past_events.extend(day_events)
            current += timedelta(days=1)

        # Filter and group past meetings by company
        company_memories = {}

        for event in past_events:
            if not _is_past_meeting(event, current_date):
                continue

            # Extract company from past event
            meeting_data = {
                "subject": event.subject,
                "attendees": [{"name": a.name, "company": a.company} for a in event.attendees],
                "company": None
            }

            company = _extract_company_from_meeting(meeting_data, aliases)

            # Only include if this company has a meeting today
            if company and company in companies_today:
                if company not in company_memories:
                    company_memories[company] = []

                # Add to memory if we haven't reached max items
                if len(company_memories[company]) < max_items:
                    company_memories[company].append(_format_past_meeting(event))

        # Sort past meetings by date (most recent first)
        for company in company_memories:
            company_memories[company].sort(
                key=lambda x: datetime.strptime(x["date"], "%b %d, %Y") if "Jan" in x["date"] or "Feb" in x["date"] or "Mar" in x["date"] or "Apr" in x["date"] or "May" in x["date"] or "Jun" in x["date"] or "Jul" in x["date"] or "Aug" in x["date"] or "Sep" in x["date"] or "Oct" in x["date"] or "Nov" in x["date"] or "Dec" in x["date"] else datetime.min,
                reverse=True
            )

        return company_memories

    except Exception:
        # Return empty dict on any provider error
        return {}


def attach_memory_to_meetings(meetings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Attach memory data to meetings based on company matching.

    Args:
        meetings: List of meeting dictionaries or Pydantic models

    Returns:
        Meetings with memory data attached
    """
    if not meetings:
        return meetings

    # Convert meetings to events for memory fetching
    events_today = []
    for meeting in meetings:
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'model_dump'):
            # Pydantic model
            meeting_dict = meeting.model_dump()
            subject = meeting_dict.get("subject", "")
            start_time = meeting_dict.get("start_time", "")
            location = meeting_dict.get("location")
            attendees = meeting_dict.get("attendees", [])
        else:
            # Regular dict
            subject = meeting.get("subject", "")
            start_time = meeting.get("start_time", "")
            location = meeting.get("location")
            attendees = meeting.get("attendees", [])

        # Create a minimal event from meeting data
        event = Event(
            subject=subject,
            start_time=start_time,
            end_time="",  # Not needed for memory
            location=location,
            attendees=[],  # Will be populated from meeting attendees
            notes=None
        )
        events_today.append(event)

    # Fetch recent meetings
    company_memories = fetch_recent_meetings(events_today)

    # Attach memory to meetings
    for meeting in meetings:
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'model_dump'):
            # Pydantic model - convert to dict for processing
            meeting_dict = meeting.model_dump()
            profile = get_profile()
            company = _extract_company_from_meeting(meeting_dict, profile.company_aliases)

            if company and company in company_memories:
                meeting_dict["memory"] = {
                    "previous_meetings": company_memories[company]
                }
            else:
                meeting_dict["memory"] = {
                    "previous_meetings": []
                }

            # Update the model with memory data
            meeting.memory = meeting_dict["memory"]
        else:
            # Regular dict
            profile = get_profile()
            company = _extract_company_from_meeting(meeting, profile.company_aliases)

            if company and company in company_memories:
                meeting["memory"] = {
                    "previous_meetings": company_memories[company]
                }
            else:
                meeting["memory"] = {
                    "previous_meetings": []
                }

    return meetings
