import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.main import app
from app.calendar.types import Event, Attendee


class TestSearchPerson:
    """Test person search functionality."""

    def test_search_by_email_exact_match(self):
        """Test search with exact email match."""
        client = TestClient(app)

        # Mock calendar provider
        mock_event = Event(
            subject="Test Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            location="Conference Room",
            attendees=[
                Attendee(name="John Doe", email="john@example.com", title="Manager")
            ]
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&email=john@example.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["count"] == 1
            assert len(data["matches"]) == 1
            assert data["matches"][0]["subject"] == "Test Meeting"
            assert data["matches"][0]["attendees"][0]["email"] == "john@example.com"

    def test_search_by_domain_match(self):
        """Test search with domain match across multiple events."""
        client = TestClient(app)

        # Mock multiple events with same domain
        mock_events = [
            Event(
                subject="Meeting 1",
                start_time="2025-12-05T10:00:00-05:00",
                end_time="2025-12-05T11:00:00-05:00",
                attendees=[
                    Attendee(name="John Doe", email="john@acme.com")
                ]
            ),
            Event(
                subject="Meeting 2",
                start_time="2025-12-06T14:00:00-05:00",
                end_time="2025-12-06T15:00:00-05:00",
                attendees=[
                    Attendee(name="Jane Smith", email="jane@acme.com")
                ]
            )
        ]

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            # Simulate fetching events for multiple days
            def fetch_events_side_effect(date):
                if date == "2025-12-05":
                    return [mock_events[0]]
                elif date == "2025-12-06":
                    return [mock_events[1]]
                return []

            mock_provider_instance.fetch_events.side_effect = fetch_events_side_effect
            mock_provider.return_value = mock_provider_instance

            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-06&domain=acme.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["count"] == 2
            assert len(data["matches"]) == 2
            # Check that both matches have acme.com domain
            for match in data["matches"]:
                found = False
                for attendee in match["attendees"]:
                    if attendee.get("email") and "@acme.com" in attendee["email"]:
                        found = True
                        break
                assert found, f"Match {match['subject']} should have acme.com attendee"

    def test_search_by_name_case_insensitive(self):
        """Test search with name match (case-insensitive)."""
        client = TestClient(app)

        mock_event = Event(
            subject="Team Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            attendees=[
                Attendee(name="John Doe", email="john@example.com")
            ]
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            # Test case-insensitive search
            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&name=john&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["count"] == 1

            # Test with different case
            response2 = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&name=JOHN&source=live"
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["count"] == 1

    def test_search_empty_result(self):
        """Test search that returns no matches."""
        client = TestClient(app)

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = []
            mock_provider.return_value = mock_provider_instance

            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&email=nonexistent@example.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["count"] == 0
            assert data["matches"] == []

    def test_search_input_validation_missing_dates(self):
        """Test search with missing required parameters."""
        client = TestClient(app)

        # Missing start date
        response = client.get("/digest/search?end=2025-12-05&email=test@example.com")
        assert response.status_code == 422

        # Missing end date
        response = client.get("/digest/search?start=2025-12-05&email=test@example.com")
        assert response.status_code == 422

    def test_search_input_validation_invalid_date_format(self):
        """Test search with invalid date formats."""
        client = TestClient(app)

        # Invalid start date
        response = client.get(
            "/digest/search?start=invalid&end=2025-12-05&email=test@example.com"
        )
        assert response.status_code == 422
        assert "Invalid date format" in response.json()["detail"]

        # Invalid end date
        response = client.get(
            "/digest/search?start=2025-12-05&end=invalid&email=test@example.com"
        )
        assert response.status_code == 422

    def test_search_input_validation_start_after_end(self):
        """Test search with start date after end date."""
        client = TestClient(app)

        response = client.get(
            "/digest/search?start=2025-12-06&end=2025-12-05&email=test@example.com"
        )
        assert response.status_code == 422
        assert "Start date" in response.json()["detail"]
        assert "must be before or equal to end date" in response.json()["detail"]

    def test_search_input_validation_no_filters(self):
        """Test search without any filter parameters."""
        client = TestClient(app)

        response = client.get("/digest/search?start=2025-12-05&end=2025-12-05")
        assert response.status_code == 422
        assert "At least one filter must be provided" in response.json()["detail"]

    def test_search_priority_email_over_domain(self):
        """Test that email filter takes priority over domain."""
        client = TestClient(app)

        # Event with attendee matching both email and domain
        mock_event = Event(
            subject="Test Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            attendees=[
                Attendee(name="John Doe", email="john@acme.com"),
                Attendee(name="Jane Smith", email="jane@acme.com")
            ]
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            # Search by email - should only match that specific email
            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&email=john@acme.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            # Should have both attendees in the match, but only matched because of john@acme.com
            assert len(data["matches"][0]["attendees"]) == 2

    def test_search_domain_with_leading_at(self):
        """Test that domain filter handles leading @ symbol."""
        client = TestClient(app)

        mock_event = Event(
            subject="Test Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            attendees=[
                Attendee(name="John Doe", email="john@acme.com")
            ]
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            # Test with leading @
            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&domain=@acme.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1

    def test_search_name_partial_match(self):
        """Test that name search does partial (contains) matching."""
        client = TestClient(app)

        mock_event = Event(
            subject="Test Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            attendees=[
                Attendee(name="John Michael Doe", email="john@example.com")
            ]
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            # Search for partial name
            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&name=Michael&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1

    def test_search_date_range_multiple_days(self):
        """Test search across a date range spanning multiple days."""
        client = TestClient(app)

        mock_events = [
            Event(
                subject="Day 1 Meeting",
                start_time="2025-12-05T10:00:00-05:00",
                end_time="2025-12-05T11:00:00-05:00",
                attendees=[Attendee(name="John Doe", email="john@example.com")]
            ),
            Event(
                subject="Day 2 Meeting",
                start_time="2025-12-06T14:00:00-05:00",
                end_time="2025-12-06T15:00:00-05:00",
                attendees=[Attendee(name="John Doe", email="john@example.com")]
            ),
            Event(
                subject="Day 3 Meeting",
                start_time="2025-12-07T16:00:00-05:00",
                end_time="2025-12-07T17:00:00-05:00",
                attendees=[Attendee(name="John Doe", email="john@example.com")]
            )
        ]

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            def fetch_events_side_effect(date):
                if date == "2025-12-05":
                    return [mock_events[0]]
                elif date == "2025-12-06":
                    return [mock_events[1]]
                elif date == "2025-12-07":
                    return [mock_events[2]]
                return []

            mock_provider_instance.fetch_events.side_effect = fetch_events_side_effect
            mock_provider.return_value = mock_provider_instance

            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-07&email=john@example.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["count"] == 3
            assert len(data["matches"]) == 3
            # Verify matches are sorted by date
            dates = [match["date"] for match in data["matches"]]
            assert dates == ["2025-12-05", "2025-12-06", "2025-12-07"]

    def test_search_sample_source(self):
        """Test search with sample source."""
        client = TestClient(app)

        # Sample calendar data has events on 2025-09-08 with chintan@rpck.com
        response = client.get(
            "/digest/search?start=2025-09-08&end=2025-09-08&email=chintan@rpck.com&source=sample"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        # Should find at least one match from sample data
        assert data["count"] >= 1
        if data["count"] > 0:
            assert "chintan@rpck.com" in str(data["matches"][0]["attendees"])

    def test_search_response_structure(self):
        """Test that search response has correct structure."""
        client = TestClient(app)

        mock_event = Event(
            subject="Test Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            location="Conference Room",
            notes="Test notes",
            attendees=[
                Attendee(name="John Doe", email="john@example.com", title="Manager", company="Example Corp")
            ]
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&email=john@example.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()

            # Check top-level structure
            assert "ok" in data
            assert "matches" in data
            assert "count" in data

            # Check match structure
            assert len(data["matches"]) == 1
            match = data["matches"][0]
            assert "event_id" in match
            assert "date" in match
            assert "start_time" in match
            assert "subject" in match
            assert "attendees" in match
            assert "location" in match
            assert "notes" in match

            # Check attendee structure
            assert len(match["attendees"]) == 1
            attendee = match["attendees"][0]
            assert "name" in attendee
            assert "email" in attendee
            assert "title" in attendee
            assert "company" in attendee

    def test_search_no_attendees_in_event(self):
        """Test that events without attendees don't match."""
        client = TestClient(app)

        mock_event = Event(
            subject="Test Meeting",
            start_time="2025-12-05T10:00:00-05:00",
            end_time="2025-12-05T11:00:00-05:00",
            attendees=[]  # No attendees
        )

        with patch('app.routes.search.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get(
                "/digest/search?start=2025-12-05&end=2025-12-05&email=test@example.com&source=live"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 0
            assert data["matches"] == []

