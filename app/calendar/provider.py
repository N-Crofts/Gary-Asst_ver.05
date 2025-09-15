import os
from typing import List, Protocol

from app.calendar.types import Event


class CalendarProvider(Protocol):
    def fetch_events(self, date: str) -> List[Event]:
        """
        Fetch normalized calendar events for the given ISO date (YYYY-MM-DD).

        All times must be ISO 8601 strings in ET.
        """
        ...


def select_calendar_provider() -> CalendarProvider:
    """Factory function to select calendar provider based on CALENDAR_PROVIDER env var."""
    provider = os.getenv("CALENDAR_PROVIDER", "mock").lower()

    if provider == "mock":
        from app.calendar.mock_provider import MockCalendarProvider
        return MockCalendarProvider()
    elif provider == "ms_graph":
        from app.calendar.ms_graph_adapter import create_ms_graph_adapter
        return create_ms_graph_adapter()
    else:
        raise ValueError(f"Unsupported CALENDAR_PROVIDER: {provider}")


