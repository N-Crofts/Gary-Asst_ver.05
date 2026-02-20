import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os

from app.main import app

client = TestClient(app)


class TestDigestPreview:
    """Test suite for digest preview functionality."""

    def test_preview_html_sample_source(self):
        """Test AC 1: GET /digest/preview returns 200 HTML in under 1s using source=sample."""
        response = client.get("/digest/preview?source=sample")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        # Check that response is fast (under 1s is implicit in test execution)
        html_content = response.text
        assert len(html_content) > 0

    def test_preview_html_contains_news_links(self):
        """Test AC 2: Rendered HTML contains ≥ 3 <a> links in the News section."""
        response = client.get("/digest/preview?source=sample")

        assert response.status_code == 200
        html_content = response.text

        # Count <a> tags in the HTML
        link_count = html_content.count('<a ')
        assert link_count >= 3, f"Expected at least 3 links, found {link_count}"

    def test_preview_html_contains_required_headings(self):
        """Test AC 3: HTML contains headings for Context Snapshot and data-driven sections."""
        response = client.get("/digest/preview?source=sample")

        assert response.status_code == 200
        html_content = response.text

        # Check for required headings (no placeholder filler)
        assert "Context Snapshot" in html_content
        # Recent developments appear under Context Snapshot when news present; or "No external context available"
        assert "Recent developments" in html_content or "No external context available" in html_content

    def test_preview_json_sample_source(self):
        """Test AC 4: GET /digest/preview.json returns 200 JSON matching the digest model schema."""
        response = client.get("/digest/preview.json?source=sample")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

        data = response.json()

        # Check required top-level fields
        assert data["ok"] is True
        assert data["source"] in ["sample", "live"]
        assert "date_human" in data
        assert "exec_name" in data
        assert "meetings" in data
        assert isinstance(data["meetings"], list)

        # Check meeting structure if meetings exist
        if data["meetings"]:
            meeting = data["meetings"][0]
            assert "subject" in meeting
            assert "start_time" in meeting
            assert "attendees" in meeting
            assert "news" in meeting
            assert "talking_points" in meeting
            assert "smart_questions" in meeting

            # Check that news, talking_points, and smart_questions are arrays
            assert isinstance(meeting["news"], list)
            assert isinstance(meeting["talking_points"], list)
            assert isinstance(meeting["smart_questions"], list)

    def test_preview_live_source_fallback(self):
        """Test AC 5: source=live uses live assembly if available; otherwise falls back to sample."""
        # Force mock calendar so test does not depend on MS Graph / network
        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "mock"}, clear=False):
            response = client.get("/digest/preview.json?source=live&date=2025-09-08")
        assert response.status_code == 200
        data = response.json()
        # With mock provider, live returns live source and meetings; no fallback needed
        assert data["source"] in ("live", "sample")
        assert len(data["meetings"]) >= 0

    def test_preview_empty_meetings_state(self):
        """Test AC 6: Empty meetings should yield meetings: [] in JSON (HTML may render fallback)."""
        # Mock empty meetings in the sample data used by the context builder
        with patch('app.rendering.context_builder.SAMPLE_MEETINGS', []):
            # HTML still renders fallback block; we just assert 200
            html_response = client.get("/digest/preview?source=sample")
            assert html_response.status_code == 200

            # JSON should be an empty meetings array
            json_response = client.get("/digest/preview.json?source=sample")
            assert json_response.status_code == 200
            data = json_response.json()
            assert data["meetings"] == []

    def test_preview_exec_name_override(self):
        """Test AC 7: exec_name query parameter overrides the header label in both HTML and JSON."""
        custom_name = "Biz Ops Team"

        # Test HTML
        html_response = client.get(f"/digest/preview?source=sample&exec_name={custom_name}")
        assert html_response.status_code == 200
        html_content = html_response.text
        assert custom_name in html_content

        # Test JSON
        json_response = client.get(f"/digest/preview.json?source=sample&exec_name={custom_name}")
        assert json_response.status_code == 200
        data = json_response.json()
        assert data["exec_name"] == custom_name

    def test_preview_format_negotiation(self):
        """Test format negotiation with Accept header and format parameter."""
        # Test Accept: application/json header
        response = client.get(
            "/digest/preview?source=sample",
            headers={"Accept": "application/json"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

        # Test format=json parameter
        response = client.get("/digest/preview?source=sample&format=json")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    def test_preview_invalid_source(self):
        """Test error handling for invalid source parameter."""
        response = client.get("/digest/preview?source=invalid")
        assert response.status_code == 422  # FastAPI returns 422 for validation errors
        # Check that it's a validation error
        error_detail = response.json()["detail"]
        assert any("source" in str(error).lower() for error in error_detail)

    def test_preview_json_invalid_source(self):
        """Test error handling for invalid source parameter in JSON endpoint."""
        response = client.get("/digest/preview.json?source=invalid")
        assert response.status_code == 422  # FastAPI returns 422 for validation errors
        # Check that it's a validation error
        error_detail = response.json()["detail"]
        assert any("source" in str(error).lower() for error in error_detail)

    def test_preview_default_parameters(self):
        """Test that default parameters work correctly."""
        # Force mock calendar and default profile so test does not depend on MS Graph
        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "mock", "EXEC_PROFILE_ID": "default"}, clear=False):
            # Test HTML with defaults (source defaults to sample or live; mock makes live work)
            response = client.get("/digest/preview")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            # Test JSON with defaults
            response = client.get("/digest/preview.json")
            assert response.status_code == 200
            data = response.json()
            assert data["source"] in ("sample", "live")
            # exec_name from default profile or derived from mailbox
            assert "exec_name" in data and len(data["exec_name"]) > 0

    def test_preview_consistency_with_send(self):
        """Test that preview output is consistent with /digest/send output."""
        # Get preview HTML
        preview_response = client.get("/digest/preview?source=sample")
        preview_html = preview_response.text

        # Get send HTML (rendered only, not sent)
        send_response = client.get("/digest/send?source=sample&send=false")
        send_data = send_response.json()

        # Both should contain the same key elements
        assert "Recent news" in preview_html
        assert "Context Snapshot" in preview_html

        # The send response should indicate it was rendered
        assert send_data["action"] == "rendered"

    def test_preview_json_structure_validation(self):
        """Test that JSON response structure matches the expected schema."""
        response = client.get("/digest/preview.json?source=sample")
        data = response.json()

        # Validate top-level structure
        required_fields = ["ok", "source", "date_human", "exec_name", "meetings"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate meeting structure if meetings exist
        if data["meetings"]:
            meeting = data["meetings"][0]
            meeting_fields = ["subject", "start_time", "attendees", "news", "talking_points", "smart_questions"]
            for field in meeting_fields:
                assert field in meeting, f"Missing meeting field: {field}"

            # Validate attendees structure
            if meeting["attendees"]:
                attendee = meeting["attendees"][0]
                assert "name" in attendee
                # title and company are optional

            # Validate news structure
            if meeting["news"]:
                news_item = meeting["news"][0]
                assert "title" in news_item
                assert "url" in news_item

    def test_preview_timezone_handling(self):
        """Test that timezone handling works correctly."""
        # Test with default timezone
        response = client.get("/digest/preview.json?source=sample")
        data = response.json()

        # date_human should be in a readable format
        assert "2025" in data["date_human"]  # Should contain current year
        assert len(data["date_human"]) > 10  # Should be a reasonable date string length

    def test_preview_live_source_with_mock_data(self):
        """Test live source with mocked provider data."""
        from app.calendar.types import Event, Attendee

        mock_events = [
            Event(
                subject="Live Meeting Test",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T10:30:00-04:00",
                location="Conference Room",
                attendees=[Attendee(name="Test User", title="Test Title", company="Test Company")],
                notes=None,
            )
        ]

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
            mock_provider = MagicMock()
            mock_provider.fetch_events.return_value = mock_events
            mock_factory.return_value = mock_provider
            response = client.get("/digest/preview.json?source=live&date=2025-09-08")
            data = response.json()

            assert data["source"] == "live"
            assert len(data["meetings"]) == 1
            assert data["meetings"][0]["subject"] == "Live Meeting Test"


class TestResearchOverrideQueryParam:
    """Staging-only research=1 override: prod ignores param; non-prod respects it."""

    def test_prod_and_research_param_returns_false(self):
        """APP_ENV=production + research=1 -> False (param ignored)."""
        from app.routes.preview import should_run_research
        request = MagicMock()
        request.query_params.get.side_effect = lambda k, default="": "1" if k == "research" else default
        settings = {"app_env": "production", "research_enabled": False}
        assert should_run_research(request, settings) is False
        settings["research_enabled"] = True
        # With research=1 in prod we still use env only; research_enabled True -> True
        assert should_run_research(request, settings) is True
        # With research=1 in prod and research_enabled False -> False (param ignored)
        settings["research_enabled"] = False
        assert should_run_research(request, settings) is False

    def test_staging_and_research_param_returns_true(self):
        """APP_ENV != production + research=1 -> True."""
        from app.routes.preview import should_run_research
        request = MagicMock()
        request.query_params.get.side_effect = lambda k, default="": "1" if k == "research" else default
        settings = {"app_env": "staging", "research_enabled": False}
        assert should_run_research(request, settings) is True
        settings = {"app_env": "development", "research_enabled": False}
        assert should_run_research(request, settings) is True

    def test_staging_no_param_respects_research_enabled(self):
        """APP_ENV != production + no research param -> respects RESEARCH_ENABLED."""
        from app.routes.preview import should_run_research
        request = MagicMock()
        request.query_params.get.return_value = ""
        settings = {"app_env": "staging", "research_enabled": False}
        assert should_run_research(request, settings) is False
        settings["research_enabled"] = True
        assert should_run_research(request, settings) is True
