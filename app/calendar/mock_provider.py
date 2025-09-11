import json
from datetime import datetime
from pathlib import Path
from typing import List

from app.calendar.types import Event, Attendee


DATA_PATH = Path("app/data/sample_calendar.json")


def _parse_attendees(raw_list) -> list[Attendee]:
    attendees: list[Attendee] = []
    for a in raw_list or []:
        attendees.append(
            Attendee(
                name=a.get("name", ""),
                title=a.get("title"),
                company=a.get("company"),
                email=a.get("email"),
            )
        )
    return attendees


def _iso_et(dt_str: str) -> str:
    # Assume incoming is already ISO with TZ or naive local ET string; keep as-is for mock
    # In real provider, we would parse and convert; for fixtures, store ISO with -04:00/-05:00
    return dt_str


class MockCalendarProvider:
    def __init__(self, data_path: Path | None = None) -> None:
        self._path = data_path or DATA_PATH

    def fetch_events(self, date: str) -> List[Event]:
        day = date
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            # Invalid date -> return no events
            return []

        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        events_raw = raw.get("events", [])

        events: List[Event] = []
        for e in events_raw:
            # Filter by requested date using start_time prefix
            start_time = str(e.get("start_time", ""))
            if not start_time.startswith(day):
                continue
            end_time = str(e.get("end_time", ""))
            attendees = _parse_attendees(e.get("attendees", []))
            events.append(
                Event(
                    subject=e.get("subject", ""),
                    start_time=_iso_et(start_time),
                    end_time=_iso_et(end_time),
                    location=e.get("location"),
                    attendees=attendees,
                    notes=e.get("notes"),
                )
            )

        return events


