from typing import List, Protocol

from app.calendar.types import Event


class CalendarProvider(Protocol):
    def fetch_events(self, date: str) -> List[Event]:
        """
        Fetch normalized calendar events for the given ISO date (YYYY-MM-DD).

        All times must be ISO 8601 strings in ET.
        """
        ...


