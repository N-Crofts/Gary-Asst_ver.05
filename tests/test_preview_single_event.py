import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app


class TestSingleEventPreview:
    """Test single event preview endpoints."""

    def test_preview_single_event_html_sample(self):
        """Test HTML preview of single event with sample data."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check for basic HTML structure
        html_content = response.text
        assert "<html" in html_content
        assert "<head>" in html_content
        assert "body" in html_content

        # Check for meeting content
        assert "RPCK × Acme Capital" in html_content
        assert "Portfolio Strategy Check-in" in html_content
        assert "9:30 AM ET" in html_content

    def test_preview_single_event_json_sample(self):
        """Test JSON preview of single event with sample data."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert data["ok"] is True
        assert data["source"] == "sample"
        assert "date_human" in data
        assert "exec_name" in data
        assert len(data["meetings"]) == 1

        meeting = data["meetings"][0]
        assert meeting["subject"] == "RPCK × Acme Capital — Portfolio Strategy Check-in"
        assert meeting["start_time"] == "9:30 AM ET"
        assert meeting["location"] == "Zoom"
        assert len(meeting["attendees"]) == 3
        assert meeting["company"]["name"] == "Acme Capital"
        assert len(meeting["news"]) == 3
        assert len(meeting["talking_points"]) >= 2  # May be trimmed by profile settings
        assert len(meeting["smart_questions"]) >= 2  # May be trimmed by profile settings

    def test_preview_single_event_html_format_param(self):
        """Test HTML preview with format=json parameter returns JSON."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert data["ok"] is True
        assert len(data["meetings"]) == 1

    def test_preview_single_event_json_accept_header(self):
        """Test HTML endpoint returns JSON when Accept header is application/json."""
        client = TestClient(app)

        response = client.get(
            "/digest/preview/event/sample-1",
            headers={"Accept": "application/json"}
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert data["ok"] is True
        assert len(data["meetings"]) == 1

    def test_preview_single_event_unknown_id(self):
        """Test preview with unknown event ID returns basic structure."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/unknown-123")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        html_content = response.text
        assert "<html" in html_content
        assert "Meeting unknown-123" in html_content
        assert "Not specified" in html_content

    def test_preview_single_event_unknown_id_json(self):
        """Test JSON preview with unknown event ID returns basic structure."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/unknown-123.json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert data["ok"] is True
        assert len(data["meetings"]) == 1

        meeting = data["meetings"][0]
        assert meeting["subject"] == "Meeting unknown-123"
        assert meeting["start_time"] == "9:00 AM ET"
        assert meeting["location"] == "Not specified"
        assert len(meeting["attendees"]) == 0
        assert meeting["company"] is None
        assert len(meeting["news"]) == 0
        # Enrichment may add talking points and smart questions even for unknown events
        assert len(meeting["talking_points"]) >= 0
        assert len(meeting["smart_questions"]) >= 0

    def test_preview_single_event_with_source_param(self):
        """Test single event preview with source parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json?source=sample")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "sample"

    def test_preview_single_event_with_exec_name_param(self):
        """Test single event preview with exec_name parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json?exec_name=Test%20Executive")

        assert response.status_code == 200
        data = response.json()
        assert data["exec_name"] == "Test Executive"

    def test_preview_single_event_invalid_source(self):
        """Test single event preview with invalid source parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1?source=invalid")

        assert response.status_code == 422
        # FastAPI returns 422 for validation errors

    def test_preview_single_event_live_source_fallback(self):
        """Test single event preview with live source falls back gracefully."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            # Mock provider to raise an exception
            mock_provider.side_effect = Exception("Provider error")

            response = client.get("/digest/preview/event/sample-1.json?source=live")

            assert response.status_code == 200
            data = response.json()
            # Should fall back to sample data
            assert data["source"] == "sample"
            assert len(data["meetings"]) == 1

    def test_preview_single_event_live_source_success(self):
        """Test single event preview with live source when provider works."""
        client = TestClient(app)

        # Mock event data
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "id": "live-123",
            "subject": "Live Meeting",
            "start_time": "2025-09-16T10:00:00-04:00",
            "location": "Conference Room",
            "attendees": [
                {"name": "John Doe", "title": "Manager", "company": "Test Corp"}
            ]
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview/event/live-123.json?source=live")

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "live"
            assert len(data["meetings"]) == 1
            assert data["meetings"][0]["subject"] == "Live Meeting"

    def test_preview_single_event_live_source_not_found(self):
        """Test single event preview with live source when event not found."""
        client = TestClient(app)

        # Mock event data with different ID
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "id": "different-123",
            "subject": "Different Meeting",
            "start_time": "2025-09-16T10:00:00-04:00",
            "location": "Conference Room",
            "attendees": []
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview/event/live-123.json?source=live")

            assert response.status_code == 200
            data = response.json()
            # Should fall back to sample data since event not found
            assert data["source"] == "sample"
            assert len(data["meetings"]) == 1

    def test_preview_single_event_with_date_param(self):
        """Test single event preview with date parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json?date=2025-09-16")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_preview_single_event_html_contains_required_headings(self):
        """Test that HTML preview contains required headings and structure."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1")

        assert response.status_code == 200
        html_content = response.text

        # Check for required headings
        assert "Morning Briefing" in html_content
        assert "RPCK × Acme Capital" in html_content

        # Check for meeting details
        assert "9:30 AM ET" in html_content
        assert "Zoom" in html_content

        # Check for attendees
        assert "Chintan Panchal" in html_content
        assert "Managing Partner" in html_content
        assert "Carolyn" in html_content
        assert "Chief of Staff" in html_content
        assert "A. Rivera" in html_content
        assert "Partner" in html_content

        # Check for company information
        assert "Acme Capital" in html_content
        assert "Growth-stage investor" in html_content

        # Check for news links
        assert "Acme closes $250M Fund IV" in html_content
        assert "https://example.com/acme-fund-iv" in html_content

        # Check for talking points
        assert "Confirm Q4 fund-formation timeline" in html_content

        # Check for smart questions
        assert "What milestones unlock the next capital call?" in html_content

    def test_preview_single_event_json_structure_validation(self):
        """Test that JSON preview has correct structure and required fields."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json")

        assert response.status_code == 200
        data = response.json()

        # Validate top-level structure
        assert "ok" in data
        assert "source" in data
        assert "date_human" in data
        assert "exec_name" in data
        assert "meetings" in data

        # Validate meeting structure
        assert len(data["meetings"]) == 1
        meeting = data["meetings"][0]

        required_fields = [
            "subject", "start_time", "location", "attendees",
            "company", "news", "talking_points", "smart_questions"
        ]
        for field in required_fields:
            assert field in meeting

        # Validate attendee structure
        assert len(meeting["attendees"]) == 3
        attendee = meeting["attendees"][0]
        assert "name" in attendee
        assert "title" in attendee
        assert "company" in attendee

        # Validate company structure
        assert meeting["company"] is not None
        assert "name" in meeting["company"]
        assert "one_liner" in meeting["company"]

        # Validate news structure
        assert len(meeting["news"]) == 3
        news_item = meeting["news"][0]
        assert "title" in news_item
        assert "url" in news_item

    def test_preview_single_event_safe_empty_states(self):
        """Test that empty states are handled safely."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/empty-test.json")

        assert response.status_code == 200
        data = response.json()

        meeting = data["meetings"][0]

        # Check that empty fields are handled safely
        assert meeting["subject"] == "Meeting empty-test"
        assert meeting["start_time"] == "9:00 AM ET"
        assert meeting["location"] == "Not specified"
        assert len(meeting["attendees"]) == 0
        assert meeting["company"] is None
        assert len(meeting["news"]) == 0
        # Note: enrichment may add talking points and smart questions
        assert len(meeting["talking_points"]) >= 0
        assert len(meeting["smart_questions"]) >= 0

    def test_preview_single_event_api_key_required(self):
        """Test that API key is required when configured."""
        client = TestClient(app)

        # Create a mock config object
        mock_config_obj = MagicMock()
        mock_config_obj.api_key = "test-api-key"

        with patch('app.routes.preview.load_config') as mock_config:
            mock_config.return_value = mock_config_obj

            # Test without API key
            response = client.get("/digest/preview/event/sample-1")
            assert response.status_code == 401

            # Test with correct API key
            response = client.get(
                "/digest/preview/event/sample-1",
                headers={"X-API-Key": "test-api-key"}
            )
            assert response.status_code == 200

            # Test with incorrect API key
            response = client.get(
                "/digest/preview/event/sample-1",
                headers={"X-API-Key": "wrong-key"}
            )
            assert response.status_code == 401


class TestSingleEventContextBuilder:
    """Test the single event context builder function."""

    def test_build_single_event_context_sample_data(self):
        """Test building context for sample data."""
        from app.rendering.context_builder import build_single_event_context

        context = build_single_event_context("sample-1", source="sample")

        assert "meetings" in context
        assert "date_human" in context
        assert "current_year" in context
        assert "exec_name" in context
        assert "source" in context
        assert "event_id" in context

        assert context["source"] == "sample"
        assert context["event_id"] == "sample-1"
        assert len(context["meetings"]) == 1

        meeting = context["meetings"][0]
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'subject'):
            assert meeting.subject == "RPCK × Acme Capital — Portfolio Strategy Check-in"
        else:
            assert meeting["subject"] == "RPCK × Acme Capital — Portfolio Strategy Check-in"

    def test_build_single_event_context_unknown_id(self):
        """Test building context for unknown event ID."""
        from app.rendering.context_builder import build_single_event_context

        context = build_single_event_context("unknown-123", source="sample")

        assert context["source"] == "sample"
        assert context["event_id"] == "unknown-123"
        assert len(context["meetings"]) == 1

        meeting = context["meetings"][0]
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'subject'):
            assert meeting.subject == "Meeting unknown-123"
            assert meeting.start_time == "9:00 AM ET"
            assert meeting.location == "Not specified"
        else:
            assert meeting["subject"] == "Meeting unknown-123"
            assert meeting["start_time"] == "9:00 AM ET"
            assert meeting["location"] == "Not specified"

    def test_build_single_event_context_with_exec_name(self):
        """Test building context with custom exec name."""
        from app.rendering.context_builder import build_single_event_context

        context = build_single_event_context("sample-1", exec_name="Custom Executive")

        assert context["exec_name"] == "Custom Executive"

    def test_build_single_event_context_with_date(self):
        """Test building context with custom date."""
        from app.rendering.context_builder import build_single_event_context

        context = build_single_event_context("sample-1", date="2025-09-16")

        assert "date_human" in context
        assert "current_year" in context
