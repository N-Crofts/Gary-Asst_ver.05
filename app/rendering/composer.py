from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional


def truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"


def safe_join(items: List[str], sep: str = ", ") -> str:
    return sep.join(escape(s) for s in items)


def compose_digest_model(
    meetings: List[Dict[str, Any]],
    exec_name: Optional[str],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    dt = now or datetime.now()
    day = str(int(dt.strftime("%d")))
    date_human = f"{dt.strftime('%a')}, {dt.strftime('%b')} {day}, {dt.strftime('%Y')}"

    normalized_meetings: list[dict] = []
    for m in meetings:
        md = m
        # Allow pydantic models
        if hasattr(m, "model_dump"):
            md = m.model_dump()
        # Ensure all template-expected keys exist
        normalized_meetings.append(
            {
                "subject": md.get("subject", ""),
                "start_time": md.get("start_time", ""),
                "location": md.get("location"),
                "attendees": md.get("attendees", []),
                "company": md.get("company"),
                "news": md.get("news", []),
                "talking_points": md.get("talking_points", []),
                "smart_questions": md.get("smart_questions", []),
            }
        )

    context = {
        "date_human": date_human,
        "current_year": dt.strftime("%Y"),
        "exec_name": exec_name or "RPCK Biz Dev",
        "meetings": normalized_meetings,
    }
    return context


