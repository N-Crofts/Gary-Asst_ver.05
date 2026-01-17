import os
from datetime import datetime, timedelta
from typing import List, Protocol

from app.calendar.types import Event


class CalendarProvider(Protocol):
    def fetch_events(self, date: str) -> List[Event]:
        """
        Fetch normalized calendar events for the given ISO date (YYYY-MM-DD).

        All times must be ISO 8601 strings in ET.
        """
        ...


def fetch_events_range(provider: CalendarProvider, start_date: str, end_date: str) -> List[Event]:
    """
    Fetch events across a date range (inclusive).

    Args:
        provider: Calendar provider instance
        start_date: Start date in YYYY-MM-DD format (inclusive)
        end_date: End date in YYYY-MM-DD format (inclusive)

    Returns:
        List of events across the date range
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return []

    if start > end:
        return []

    all_events = []
    current = start

    while current <= end:
        day_str = current.strftime("%Y-%m-%d")
        day_events = provider.fetch_events(day_str)
        all_events.extend(day_events)
        current += timedelta(days=1)

    return all_events


def select_calendar_provider() -> CalendarProvider:
    """Factory function to select calendar provider based on CALENDAR_PROVIDER env var."""
    import logging
    logger = logging.getLogger(__name__)

    provider = os.getenv("CALENDAR_PROVIDER", "mock").lower()
    logger.info(f"Selecting calendar provider: {provider}")

    if provider == "mock":
        from app.calendar.mock_provider import MockCalendarProvider
        logger.info("Using MockCalendarProvider")
        return MockCalendarProvider()
    elif provider == "ms_graph":
        from app.calendar.ms_graph_adapter import create_ms_graph_adapter
        logger.info("Creating MS Graph adapter")
        adapter = create_ms_graph_adapter()
        logger.info(f"MS Graph adapter created - user_email: {adapter.user_email}, group: {adapter.allowed_mailbox_group}")
        return adapter
    else:
        raise ValueError(f"Unsupported CALENDAR_PROVIDER: {provider}")


