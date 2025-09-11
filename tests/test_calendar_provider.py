from datetime import datetime

from fastapi.testclient import TestClient

from app.calendar.mock_provider import MockCalendarProvider
from app.main import app


def test_mock_provider_filters_by_date_and_normalizes():
    provider = MockCalendarProvider()
    events = provider.fetch_events("2025-09-08")
    assert len(events) >= 2
    e = events[0]
    assert e.subject
    assert e.start_time.startswith("2025-09-08T")
    assert e.end_time.startswith("2025-09-08T")
    if e.attendees:
        a = e.attendees[0]
        assert a.name


def test_mock_provider_other_day_has_different_events():
    provider = MockCalendarProvider()
    events_8 = provider.fetch_events("2025-09-08")
    events_9 = provider.fetch_events("2025-09-09")
    assert events_8 and events_9
    # different subjects imply different filtering
    assert set(e.subject for e in events_8) != set(e.subject for e in events_9)


def test_preview_live_uses_provider_and_fallback():
    client = TestClient(app)
    # With sample data available, live should use provider and mark live
    r = client.get("/digest/preview.json?source=live&date=2025-09-08")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "live"
    assert len(data["meetings"]) >= 1

    # If provider returns empty for a date, fallback to sample and mark sample
    r2 = client.get("/digest/preview.json?source=live&date=1900-01-01")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["source"] == "sample"
    assert len(data2["meetings"]) >= 1


