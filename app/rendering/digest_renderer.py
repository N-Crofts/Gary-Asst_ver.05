from datetime import datetime
from typing import Dict, Any, Literal, Optional
from zoneinfo import ZoneInfo
import os

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.data.sample_digest import SAMPLE_MEETINGS


templates = Jinja2Templates(directory="app/templates")


def _today_et_str(tz_name: str) -> str:
    """Format today's date in the specified timezone."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    day = str(int(now.strftime("%d")))
    return f"{now.strftime('%a')}, {now.strftime('%b')} {day}, {now.strftime('%Y')}"


def _format_date_et_str(date_str: str, tz_name: str) -> str:
    """Format a specific date (YYYY-MM-DD) in the specified timezone."""
    try:
        # Parse the date string
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        # Get timezone
        tz = ZoneInfo(tz_name)
        # Localize the date to the timezone (at midnight)
        date_tz = date_obj.replace(tzinfo=tz)
        day = str(int(date_tz.strftime("%d")))
        return f"{date_tz.strftime('%a')}, {date_tz.strftime('%b')} {day}, {date_tz.strftime('%Y')}"
    except (ValueError, TypeError):
        # Fallback to today if parsing fails
        return _today_et_str(tz_name)


def _get_timezone() -> str:
    """Get timezone from environment or default to America/New_York."""
    return os.getenv("TIMEZONE", "America/New_York")


def _assemble_live_meetings() -> list:
    """Placeholder for future live assembly; return empty to trigger fallback."""
    return []


def build_digest_context(
    source: Literal['sample', 'live'],
    date: Optional[str] = None,
    exec_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build the context dictionary for digest rendering.

    Args:
        source: 'sample' or 'live' data source
        date: Optional ISO date (YYYY-MM-DD) - ignored in MVP unless live path supports it
        exec_name: Optional string to override header label

    Returns:
        Context dictionary with meetings, date_human, exec_name, current_year
    """
    # Get meetings based on source
    if source == 'sample':
        meetings = SAMPLE_MEETINGS
        actual_source = 'sample'
    else:  # source == 'live'
        live_meetings = _assemble_live_meetings()
        if live_meetings:
            meetings = live_meetings
            actual_source = 'live'
        else:
            # Fallback to sample if live is empty/unavailable
            meetings = SAMPLE_MEETINGS
            actual_source = 'sample'  # Indicate we fell back to sample

    # Build context
    context = {
        "meetings": meetings,
        "date_human": _today_et_str(_get_timezone()),
        "current_year": datetime.now().strftime("%Y"),
        "exec_name": exec_name or "Sorum Crofts",
        "source": actual_source,
    }

    return context


def render_digest_html(context: Dict[str, Any]) -> str:
    """Render the digest HTML using the provided context."""
    request = context.get("request")
    if request is None:
        request = Request(scope={"type": "http"})
    template = templates.get_template("digest.html")
    html = template.render({**context, "request": request})
    return html


