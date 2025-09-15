import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.calendar.ms_graph_adapter import MSGraphAdapter, create_ms_graph_adapter
from app.calendar.provider import select_calendar_provider
from app.main import app


class TestMSGraphAdapter:
    """Test MS Graph adapter with mocked HTTP calls."""

    def test_create_adapter_with_missing_env_raises_exception(self):
        """Test that missing environment variables raise HTTPException."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                create_ms_graph_adapter()
            assert exc_info.value.status_code == 503
            assert "MS Graph configuration missing" in str(exc_info.value.detail)

    def test_fetch_events_invalid_date_returns_empty(self):
        """Test that invalid date format returns empty list."""
        adapter = MSGraphAdapter("tenant", "client", "secret", "user@example.com")
        result = adapter.fetch_events("invalid-date")
        assert result == []

    def test_fetch_events_success_normalizes_data(self):
        """Test successful fetch with data normalization."""
        # Mock Graph API response
        mock_response = {
            "value": [
                {
                    "subject": "Test Meeting",
                    "start": {"dateTime": "2025-01-15T14:30:00.0000000Z"},
                    "end": {"dateTime": "2025-01-15T15:30:00.0000000Z"},
                    "location": {"displayName": "Conference Room A"},
                    "attendees": [
                        {
                            "emailAddress": {
                                "name": "John Doe",
                                "address": "john@acme.com"
                            }
                        }
                    ],
                    "bodyPreview": "Meeting notes here"
                }
            ]
        }

        adapter = MSGraphAdapter("tenant", "client", "secret", "user@example.com")

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 200
                mock_response_obj.json.return_value = mock_response
                mock_response_obj.raise_for_status.return_value = None

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                events = adapter.fetch_events("2025-01-15")

                assert len(events) == 1
                event = events[0]
                assert event.subject == "Test Meeting"
                assert "9:30 AM ET" in event.start_time  # Converted to ET
                assert "10:30 AM ET" in event.end_time
                assert event.location == "Conference Room A"
                assert len(event.attendees) == 1
                assert event.attendees[0].name == "John Doe"
                assert event.attendees[0].email == "john@acme.com"
                assert event.attendees[0].company == "Acme"  # Extracted from domain
                assert event.notes == "Meeting notes here"

    def test_fetch_events_auth_failure_raises_exception(self):
        """Test that authentication failures raise HTTPException."""
        adapter = MSGraphAdapter("tenant", "client", "secret", "user@example.com")

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 401

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                assert exc_info.value.status_code == 503
                assert "authentication failed" in str(exc_info.value.detail)

    def test_fetch_events_permission_denied_raises_exception(self):
        """Test that permission denied raises HTTPException."""
        adapter = MSGraphAdapter("tenant", "client", "secret", "user@example.com")

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 403

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                assert exc_info.value.status_code == 503
                assert "permission denied" in str(exc_info.value.detail)

    def test_convert_to_et_time_handles_various_formats(self):
        """Test timezone conversion handles different input formats."""
        adapter = MSGraphAdapter("tenant", "client", "secret", "user@example.com")

        # Test UTC format
        result = adapter._convert_to_et_time("2025-01-15T14:30:00.0000000Z")
        assert "9:30 AM ET" in result

        # Test with timezone offset
        result = adapter._convert_to_et_time("2025-01-15T14:30:00+00:00")
        assert "9:30 AM ET" in result

        # Test invalid format fallback
        result = adapter._convert_to_et_time("invalid-time")
        assert result == "invalid-time"

    def test_normalize_attendees_extracts_company_from_domain(self):
        """Test that company is extracted from email domain."""
        adapter = MSGraphAdapter("tenant", "client", "secret", "user@example.com")

        graph_attendees = [
            {
                "emailAddress": {
                    "name": "Jane Smith",
                    "address": "jane@techcorp.com"
                }
            },
            {
                "emailAddress": {
                    "name": "Bob Wilson",
                    "address": "bob@rpck.com"  # RPCK should not be shown as company
                }
            }
        ]

        attendees = adapter._normalize_attendees(graph_attendees)

        assert len(attendees) == 2
        assert attendees[0].name == "Jane Smith"
        assert attendees[0].email == "jane@techcorp.com"
        assert attendees[0].company == "Techcorp"

        assert attendees[1].name == "Bob Wilson"
        assert attendees[1].email == "bob@rpck.com"
        assert attendees[1].company is None  # RPCK domain should not set company


class TestProviderFactory:
    """Test the calendar provider factory."""

    def test_select_provider_mock_default(self):
        """Test that mock provider is selected by default."""
        with patch.dict(os.environ, {}, clear=True):
            provider = select_calendar_provider()
            assert provider.__class__.__name__ == "MockCalendarProvider"

    def test_select_provider_ms_graph_with_env(self):
        """Test that MS Graph provider is selected when configured."""
        with patch.dict(os.environ, {
            "CALENDAR_PROVIDER": "ms_graph",
            "MS_TENANT_ID": "tenant",
            "MS_CLIENT_ID": "client",
            "MS_CLIENT_SECRET": "secret",
            "MS_USER_EMAIL": "user@example.com"
        }):
            provider = select_calendar_provider()
            assert provider.__class__.__name__ == "MSGraphAdapter"

    def test_select_provider_invalid_raises_exception(self):
        """Test that invalid provider raises ValueError."""
        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "invalid"}):
            with pytest.raises(ValueError) as exc_info:
                select_calendar_provider()
            assert "Unsupported CALENDAR_PROVIDER" in str(exc_info.value)


class TestPreviewEndpointWithMSGraph:
    """Test preview endpoint with MS Graph provider."""

    def test_preview_live_with_ms_graph_success(self):
        """Test preview with MS Graph provider returns live data."""
        client = TestClient(app)

        # Mock the provider to return events
        mock_events = [
            MagicMock(
                subject="Live Meeting",
                start_time="9:30 AM ET",
                end_time="10:30 AM ET",
                location="Zoom",
                attendees=[],
                notes=None,
                model_dump=lambda: {
                    "subject": "Live Meeting",
                    "start_time": "9:30 AM ET",
                    "end_time": "10:30 AM ET",
                    "location": "Zoom",
                    "attendees": [],
                    "notes": None
                }
            )
        ]

        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "ms_graph"}):
            with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
                mock_provider = MagicMock()
                mock_provider.fetch_events.return_value = mock_events
                mock_factory.return_value = mock_provider

                response = client.get("/digest/preview.json?source=live&date=2025-01-15")

                assert response.status_code == 200
                data = response.json()
                assert data["source"] == "live"
                assert len(data["meetings"]) == 1
                assert data["meetings"][0]["subject"] == "Live Meeting"

    def test_preview_live_with_ms_graph_fallback(self):
        """Test preview with MS Graph provider falls back to sample on error."""
        client = TestClient(app)

        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "ms_graph"}):
            with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
                mock_provider = MagicMock()
                mock_provider.fetch_events.side_effect = HTTPException(status_code=503, detail="API error")
                mock_factory.return_value = mock_provider

                response = client.get("/digest/preview.json?source=live&date=2025-01-15")

                assert response.status_code == 200
                data = response.json()
                assert data["source"] == "sample"  # Fallback to sample
                assert len(data["meetings"]) >= 1  # Sample data should be present

    def test_preview_live_with_empty_events_fallback(self):
        """Test preview with MS Graph provider falls back to sample when no events."""
        client = TestClient(app)

        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "ms_graph"}):
            with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
                mock_provider = MagicMock()
                mock_provider.fetch_events.return_value = []  # Empty events
                mock_factory.return_value = mock_provider

                response = client.get("/digest/preview.json?source=live&date=2025-01-15")

                assert response.status_code == 200
                data = response.json()
                assert data["source"] == "sample"  # Fallback to sample
                assert len(data["meetings"]) >= 1  # Sample data should be present
