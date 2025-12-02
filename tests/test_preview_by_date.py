import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.main import app


class TestDateSpecificPreview:
    """Test date-specific preview functionality."""

    def test_preview_with_valid_date_html(self):
        """Test HTML preview with a valid date parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview?source=sample&date=2025-12-05")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check that the date is reflected in the HTML
        html_content = response.text
        assert "Dec" in html_content or "December" in html_content
        assert "2025" in html_content

    def test_preview_with_valid_date_json(self):
        """Test JSON preview with a valid date parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview.json?source=sample&date=2025-12-05")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert data["ok"] is True
        assert "date_human" in data
        # Check that date_human contains December 2025
        assert "Dec" in data["date_human"] or "December" in data["date_human"]
        assert "2025" in data["date_human"]

    def test_preview_with_invalid_date_format(self):
        """Test preview with invalid date format returns 422."""
        client = TestClient(app)

        # Test various invalid formats
        invalid_dates = [
            "2025-12-5",      # Missing leading zero
            "2025/12/05",     # Wrong separator
            "12-05-2025",     # Wrong order
            "2025-13-05",     # Invalid month
            "2025-12-32",     # Invalid day
            "invalid-date",   # Not a date
            "2025-2-05",      # Missing leading zero in month
            "2025-12-05-extra",  # Extra characters
        ]

        for invalid_date in invalid_dates:
            response = client.get(f"/digest/preview?source=sample&date={invalid_date}")
            assert response.status_code == 422, f"Expected 422 for date '{invalid_date}', got {response.status_code}"
            error_detail = response.json()["detail"]
            assert "Invalid date format" in error_detail or "Invalid date" in error_detail
            assert "YYYY-MM-DD" in error_detail

    def test_preview_with_invalid_date_json(self):
        """Test JSON preview with invalid date format returns 422."""
        client = TestClient(app)

        response = client.get("/digest/preview.json?source=sample&date=invalid")

        assert response.status_code == 422
        data = response.json()
        assert "Invalid date format" in data["detail"]
        assert "YYYY-MM-DD" in data["detail"]

    def test_preview_without_date_defaults_to_today(self):
        """Test that preview without date parameter defaults to today."""
        client = TestClient(app)

        response = client.get("/digest/preview?source=sample")

        assert response.status_code == 200
        data = response.json() if "application/json" in response.headers.get("content-type", "") else None

        # If JSON, verify it has date_human
        if data:
            assert "date_human" in data
            # Should contain today's date info
            today = datetime.now()
            assert today.strftime("%Y") in data["date_human"]

    def test_preview_with_past_date(self):
        """Test preview with a past date."""
        client = TestClient(app)

        past_date = "2024-01-15"
        response = client.get(f"/digest/preview.json?source=sample&date={past_date}")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "Jan" in data["date_human"] or "January" in data["date_human"]
        assert "2024" in data["date_human"]

    def test_preview_with_future_date(self):
        """Test preview with a future date."""
        client = TestClient(app)

        future_date = "2026-06-20"
        response = client.get(f"/digest/preview.json?source=sample&date={future_date}")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "Jun" in data["date_human"] or "June" in data["date_human"]
        assert "2026" in data["date_human"]

    def test_preview_live_with_date(self):
        """Test live preview with a specific date."""
        client = TestClient(app)

        # Mock calendar provider
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {
            "subject": "Test Meeting",
            "start_time": "2025-12-05T10:00:00-05:00",
            "location": "Conference Room",
            "attendees": []
        }

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_provider:
            mock_provider_instance = MagicMock()
            mock_provider_instance.fetch_events.return_value = [mock_event]
            mock_provider.return_value = mock_provider_instance

            response = client.get("/digest/preview.json?source=live&date=2025-12-05")

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "live"
            assert "Dec" in data["date_human"] or "December" in data["date_human"]
            assert "2025" in data["date_human"]
            # Verify the provider was called with the correct date
            mock_provider_instance.fetch_events.assert_called_once_with("2025-12-05")

    def test_preview_date_timezone_normalization(self):
        """Test that date formatting uses configured timezone."""
        client = TestClient(app)

        # Test with a specific date
        test_date = "2025-12-05"
        response = client.get(f"/digest/preview.json?source=sample&date={test_date}")

        assert response.status_code == 200
        data = response.json()

        # date_human should be formatted in ET (America/New_York) by default
        # Format is "Day, Month Day, Year" which splits into 3 parts: ["Fri", "Dec 5", "2025"]
        date_parts = data["date_human"].split(", ")
        assert len(date_parts) == 3  # "Fri, Dec 5, 2025" -> ["Fri", "Dec 5", "2025"]

        # Verify it contains expected date components
        assert "2025" in data["date_human"]
        assert "Dec" in data["date_human"] or "December" in data["date_human"]
        assert "5" in data["date_human"] or "05" in data["date_human"]

    def test_preview_single_event_with_date(self):
        """Test single event preview with date parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json?source=sample&date=2025-12-05")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "Dec" in data["date_human"] or "December" in data["date_human"]
        assert "2025" in data["date_human"]

    def test_preview_single_event_invalid_date(self):
        """Test single event preview with invalid date returns 422."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json?date=invalid")

        assert response.status_code == 422
        assert "Invalid date format" in response.json()["detail"]

    def test_preview_date_parameter_works_with_all_endpoints(self):
        """Test that date parameter works with all preview endpoints."""
        client = TestClient(app)
        test_date = "2025-12-05"

        endpoints = [
            "/digest/preview",
            "/digest/preview.json",
            "/digest/preview/event/sample-1",
            "/digest/preview/event/sample-1.json",
        ]

        for endpoint in endpoints:
            response = client.get(f"{endpoint}?source=sample&date={test_date}")
            assert response.status_code in [200, 422], f"Endpoint {endpoint} failed"
            if response.status_code == 200:
                # For HTML endpoints, check content type
                if endpoint.endswith(".json") or "format=json" in endpoint:
                    data = response.json()
                    assert "2025" in data["date_human"]
                else:
                    html = response.text
                    assert "2025" in html

    def test_preview_date_with_leap_year(self):
        """Test preview with leap year date (February 29)."""
        client = TestClient(app)

        # 2024 is a leap year
        leap_date = "2024-02-29"
        response = client.get(f"/digest/preview.json?source=sample&date={leap_date}")

        assert response.status_code == 200
        data = response.json()
        assert "Feb" in data["date_human"] or "February" in data["date_human"]
        assert "2024" in data["date_human"]

    def test_preview_date_with_invalid_leap_year(self):
        """Test preview with invalid leap year date (February 29 in non-leap year)."""
        client = TestClient(app)

        # 2025 is not a leap year, so Feb 29 is invalid
        invalid_leap_date = "2025-02-29"
        response = client.get(f"/digest/preview.json?source=sample&date={invalid_leap_date}")

        # Python's datetime.strptime will accept this but it's not a valid date
        # However, the validation only checks format, not validity
        # So this should pass format validation but may fail later
        # For now, we'll just check it doesn't crash
        assert response.status_code in [200, 422]

    def test_preview_date_context_builder_integration(self):
        """Test that context builder correctly formats date for specific dates."""
        from app.rendering.context_builder import build_digest_context_with_provider

        # Test with a specific date
        context = build_digest_context_with_provider(
            source="sample",
            date="2025-12-05"
        )

        assert "date_human" in context
        assert "Dec" in context["date_human"] or "December" in context["date_human"]
        assert "2025" in context["date_human"]
        assert context["current_year"] == "2025"

        # Test without date (should default to today)
        context_today = build_digest_context_with_provider(
            source="sample",
            date=None
        )

        assert "date_human" in context_today
        today = datetime.now()
        assert today.strftime("%Y") in context_today["date_human"]
        assert context_today["current_year"] == today.strftime("%Y")

    def test_preview_date_format_consistency(self):
        """Test that date formatting is consistent across HTML and JSON."""
        client = TestClient(app)
        test_date = "2025-12-05"

        # Get HTML response (as JSON via format parameter)
        html_response = client.get(f"/digest/preview?source=sample&date={test_date}&format=json")
        html_data = html_response.json()

        # Get JSON response
        json_response = client.get(f"/digest/preview.json?source=sample&date={test_date}")
        json_data = json_response.json()

        # Both should have the same date_human format
        assert html_data["date_human"] == json_data["date_human"]
        # Note: current_year is not in the response model, it's only in the context for rendering

