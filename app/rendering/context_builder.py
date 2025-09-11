from datetime import datetime
from typing import Dict, Any, Literal, Optional

from app.calendar.mock_provider import MockCalendarProvider
from app.data.sample_digest import SAMPLE_MEETINGS
from app.rendering.digest_renderer import _today_et_str, _get_timezone
from app.enrichment.service import enrich_meetings


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
                "start_time": start_time.split("T")[1].split("-")[0][:5] + " AM ET" if "T" in start_time else start_time,
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
) -> Dict[str, Any]:
    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    actual_source = "sample"
    meetings: list[dict]
    if source == "live":
        provider = MockCalendarProvider()
        events = provider.fetch_events(requested_date)
        if events:
            meetings = _map_events_to_meetings([e.model_dump() for e in events])
            actual_source = "live"
        else:
            meetings = SAMPLE_MEETINGS
    else:
        meetings = SAMPLE_MEETINGS

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    context = {
        "meetings": meetings_enriched,
        "date_human": _today_et_str(_get_timezone()),
        "current_year": datetime.now().strftime("%Y"),
        "exec_name": exec_name or "RPCK Biz Dev",
        "source": actual_source,
    }
    return context


