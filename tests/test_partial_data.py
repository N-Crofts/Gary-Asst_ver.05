"""
Tests for Partial-Data Mode

Tests the replacement of sample fallback with real meeting details
and gentle empty states for missing enrichment.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.rendering.context_builder import build_digest_context_with_provider


class TestPartialDataMode:
    """Test partial-data mode functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Ensure we're in live mode for these tests
        self.env_patches = {
            "ENRICHMENT_ENABLED": "false",  # Disable enrichment to test partial data
            "NEWS_ENABLED": "false",
            "PEOPLE_NEWS_ENABLED": "false"
        }

        for key, value in self.env_patches.items():
            os.environ[key] = value

    def teardown_method(self):
        """Clean up test environment."""
        for key in self.env_patches:
            if key in os.environ:
                del os.environ[key]

    def test_no_events_empty_state(self):
        """Test empty state when no events exist for the day."""
        client = TestClient(app)

        # Mock calendar provider to return no events
        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = []
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            html_content = response.text
            assert "No meetings for this date." in html_content
            assert "Check your calendar or try a different date." in html_content

    def test_no_events_json_response(self):
        """Test JSON response when no events exist."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = []
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview.json?source=live")

            assert response.status_code == 200
            assert "application/json" in response.headers["content-type"]

            data = response.json()
            assert data["ok"] is True
            assert data["source"] == "live"
            assert len(data["meetings"]) == 0

    def test_real_events_no_enrichment(self):
        """Test real events with no enrichment - should show basic details."""
        client = TestClient(app)

        # Mock calendar provider to return real events
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Real Meeting with Client",
            "start_time": "2025-09-18T10:00:00-04:00",
            "location": "Conference Room A",
            "attendees": [
                {"name": "John Doe", "title": "CEO", "company": "Client Corp"},
                {"name": "Jane Smith", "title": "CTO", "company": "Client Corp"}
            ]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Should show real meeting details
            assert "Real Meeting with Client" in html_content
            assert "10:00 AM ET" in html_content
            assert "Conference Room A" in html_content
            assert "John Doe" in html_content
            assert "Jane Smith" in html_content

            # Should show gentle empty states for enrichment (check for the pattern)
            assert "Not available" in html_content

    def test_real_events_json_no_enrichment(self):
        """Test JSON response for real events with no enrichment."""
        client = TestClient(app)

        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Real Meeting with Client",
            "start_time": "2025-09-18T10:00:00-04:00",
            "location": "Conference Room A",
            "attendees": [
                {"name": "John Doe", "title": "CEO", "company": "Client Corp"}
            ]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview.json?source=live")

            assert response.status_code == 200
            data = response.json()

            assert data["ok"] is True
            assert data["source"] == "live"
            assert len(data["meetings"]) == 1

            meeting = data["meetings"][0]
            assert meeting["subject"] == "Real Meeting with Client"
            assert meeting["start_time"] == "10:00 AM ET"
            assert meeting["location"] == "Conference Room A"
            assert len(meeting["attendees"]) == 1
            assert meeting["attendees"][0]["name"] == "John Doe"

            # Enrichment should be empty
            assert len(meeting["news"]) == 0
            assert len(meeting["talking_points"]) == 0
            assert len(meeting["smart_questions"]) == 0

    def test_provider_error_graceful_handling(self):
        """Test graceful handling when calendar provider fails."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider.side_effect = Exception("Provider error")

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Should show empty state when provider fails
            assert "No meetings for this date." in html_content

    def test_context_builder_no_events(self):
        """Test context builder directly with no events."""
        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = []
            mock_provider.return_value = mock_provider_instance

            context = build_digest_context_with_provider(source="live")

            assert context["source"] == "live"
            assert len(context["meetings"]) == 0
            assert "date_human" in context
            assert "exec_name" in context

    def test_context_builder_real_events(self):
        """Test context builder directly with real events."""
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Test Meeting",
            "start_time": "2025-09-18T14:00:00-04:00",
            "location": "Zoom",
            "attendees": [{"name": "Test User", "title": "Manager", "company": "Test Corp"}]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            context = build_digest_context_with_provider(source="live")

            assert context["source"] == "live"
            assert len(context["meetings"]) == 1

            meeting = context["meetings"][0]
            # Handle both dict and Pydantic model
            if hasattr(meeting, 'subject'):
                assert meeting.subject == "Test Meeting"
                assert meeting.start_time == "2:00 PM ET"  # Time formatting
                assert meeting.location == "Zoom"
                assert len(meeting.attendees) == 1
                assert meeting.attendees[0]["name"] == "Test User"
            else:
                assert meeting["subject"] == "Test Meeting"
                assert meeting["start_time"] == "2:00 PM ET"  # Time formatting
                assert meeting["location"] == "Zoom"
                assert len(meeting["attendees"]) == 1
                assert meeting["attendees"][0]["name"] == "Test User"

    def test_context_builder_provider_error(self):
        """Test context builder with provider error."""
        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider.side_effect = Exception("Provider error")

            context = build_digest_context_with_provider(source="live")

            assert context["source"] == "live"
            assert len(context["meetings"]) == 0

    def test_sample_mode_still_works(self):
        """Test that sample mode still works as expected."""
        client = TestClient(app)

        response = client.get("/digest/preview?source=sample")

        assert response.status_code == 200
        html_content = response.text

        # Should show sample data
        assert "RPCK × Acme Capital" in html_content
        assert "Portfolio Strategy Check-in" in html_content

    def test_enrichment_disabled_but_events_exist(self):
        """Test that real events are shown even when enrichment is disabled."""
        client = TestClient(app)

        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Client Meeting",
            "start_time": "2025-09-18T09:00:00-04:00",
            "location": "Office",
            "attendees": [{"name": "Client", "title": "CEO", "company": "Client Inc"}]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Should show real meeting
            assert "Client Meeting" in html_content
            assert "9:00 AM ET" in html_content
            assert "Office" in html_content
            assert "Client" in html_content

            # Should show empty states for enrichment
            assert "Not available" in html_content


class TestPartialDataTemplateRendering:
    """Test template rendering for partial data scenarios."""

    def test_empty_state_rendering(self):
        """Test that empty state is rendered correctly."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = []
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Check for empty state styling
            assert 'style="font-size:16px; font-weight:600; color:#6b7280; margin-bottom:8px;">No meetings for this date.' in html_content
            assert 'style="font-size:13px; color:#9ca3af;">Check your calendar or try a different date.' in html_content

    def test_gentle_empty_states_rendering(self):
        """Test that gentle empty states are rendered correctly."""
        client = TestClient(app)

        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Test Meeting",
            "start_time": "2025-09-18T10:00:00-04:00",
            "location": "Test Location",
            "attendees": [{"name": "Test User", "title": "Manager", "company": "Test Corp"}]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Check for gentle empty state styling (more flexible)
            assert 'Not available' in html_content
            assert 'Recent news:' in html_content or 'Recent news' in html_content
            assert 'Talking points:' in html_content or 'Talking points' in html_content
            assert 'Smart questions:' in html_content or 'Smart questions' in html_content


class TestPartialDataEdgeCases:
    """Test edge cases for partial data mode."""

    def test_malformed_event_data(self):
        """Test handling of malformed event data."""
        client = TestClient(app)

        # Mock event with missing fields
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Incomplete Meeting",
            # Missing start_time, location, attendees
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Should show what we have
            assert "Incomplete Meeting" in html_content
            # Should handle missing fields gracefully
            assert "Not specified" in html_content or "Not available" in html_content

    def test_multiple_events_partial_data(self):
        """Test multiple events with partial enrichment data."""
        client = TestClient(app)

        mock_events = [
            MagicMock(),
            MagicMock()
        ]
        mock_events[0].model_dump.return_value = {
            "subject": "First Meeting",
            "start_time": "2025-09-18T09:00:00-04:00",
            "location": "Room 1",
            "attendees": [{"name": "Person 1", "title": "Manager", "company": "Corp 1"}]
        }
        mock_events[1].model_dump.return_value = {
            "subject": "Second Meeting",
            "start_time": "2025-09-18T14:00:00-04:00",
            "location": "Room 2",
            "attendees": [{"name": "Person 2", "title": "Director", "company": "Corp 2"}]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = mock_events
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live")

            assert response.status_code == 200
            html_content = response.text

            # Should show both meetings
            assert "First Meeting" in html_content
            assert "Second Meeting" in html_content
            assert "Person 1" in html_content
            assert "Person 2" in html_content

            # Should show empty states for both (check for pattern)
            assert html_content.count("Not available") >= 2

    def test_date_parameter_handling(self):
        """Test that date parameter is handled correctly."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = []
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview?source=live&date=2025-12-25")

            assert response.status_code == 200

            # Verify the provider was called with the correct date
            mock_provider_instance.fetch_events.assert_called_once_with("2025-12-25")
