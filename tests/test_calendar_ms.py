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
        adapter = MSGraphAdapter("tenant", "client", "secret", user_email="user@example.com", allowed_mailboxes=["user@example.com"])
        result = adapter.fetch_events("invalid-date")
        assert result == []

    def test_fetch_events_success_normalizes_data(self):
        """Test successful fetch with data normalization."""
        # Mock Graph API response - user must be in attendees for event to be included
        mock_response = {
            "value": [
                {
                    "subject": "Test Meeting",
                    "start": {
                        "dateTime": "2025-01-15T14:30:00.0000000",
                        "timeZone": "America/New_York"
                    },
                    "end": {
                        "dateTime": "2025-01-15T15:30:00.0000000",
                        "timeZone": "America/New_York"
                    },
                    "location": {"displayName": "Conference Room A"},
                    "attendees": [
                        {
                            "emailAddress": {
                                "name": "User Name",
                                "address": "user@example.com"
                            }
                        },
                        {
                            "emailAddress": {
                                "name": "John Doe",
                                "address": "john@acme.com"
                            }
                        }
                    ],
                    "organizer": {
                        "emailAddress": {
                            "name": "User Name",
                            "address": "user@example.com"
                        }
                    },
                    "bodyPreview": "Meeting notes here",
                    "isCancelled": False,
                    "id": "AAMkAGI1AA=="
                }
            ]
        }

        adapter = MSGraphAdapter("tenant", "client", "secret", user_email="user@example.com", allowed_mailboxes=["user@example.com"])

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
                # Check ISO datetime format in ET timezone
                assert "2025-01-15T09:30:00" in event.start_time or "2025-01-15T14:30:00" in event.start_time
                assert "-05:00" in event.start_time or "-04:00" in event.start_time  # ET offset
                assert event.location == "Conference Room A"
                assert len(event.attendees) >= 2  # User + John Doe
                # Find John Doe attendee
                john_attendee = next((a for a in event.attendees if a.email == "john@acme.com"), None)
                assert john_attendee is not None
                assert john_attendee.name == "John Doe"
                assert john_attendee.company == "Acme"  # Extracted from domain
                assert event.notes == "Meeting notes here"
                # Check that id and organizer are populated
                assert event.id == "AAMkAGI1AA=="
                assert event.organizer == "user@example.com"

    def test_fetch_events_auth_failure_raises_exception(self):
        """Test that authentication failures raise HTTPException."""
        adapter = MSGraphAdapter("tenant", "client", "secret", user_email="user@example.com", allowed_mailboxes=["user@example.com"])

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
        """Test that permission denied raises HTTPException with 403 status."""
        adapter = MSGraphAdapter("tenant", "client", "secret", user_email="user@example.com", allowed_mailboxes=["user@example.com"])

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 403
                # Mock error response JSON structure
                mock_response_obj.json.return_value = {
                    "error": {
                        "code": "ErrorAccessDenied",
                        "message": "Access denied"
                    }
                }

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                assert exc_info.value.status_code == 403
                assert "Access denied" in str(exc_info.value.detail)

    def test_parse_graph_datetime_handles_various_formats(self):
        """Test datetime parsing handles different Graph response formats."""
        adapter = MSGraphAdapter("tenant", "client", "secret", user_email="user@example.com", allowed_mailboxes=["user@example.com"])

        # Test with timeZone field
        result = adapter._parse_graph_datetime({
            "dateTime": "2025-01-15T14:30:00.0000000",
            "timeZone": "America/New_York"
        })
        assert result.hour == 14 or result.hour == 9  # Depending on DST
        assert result.tzinfo is not None

        # Test UTC format
        result = adapter._parse_graph_datetime({
            "dateTime": "2025-01-15T14:30:00.0000000Z",
            "timeZone": "UTC"
        })
        assert result.tzinfo is not None

        # Test invalid format raises error
        with pytest.raises(ValueError):
            adapter._parse_graph_datetime({"dateTime": "invalid-time"})

    def test_normalize_attendees_extracts_company_from_domain(self):
        """Test that company is extracted from email domain."""
        adapter = MSGraphAdapter("tenant", "client", "secret", user_email="user@example.com", allowed_mailboxes=["user@example.com"])

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

    def test_preview_live_with_ms_graph_error_raises(self):
        """Test preview with MS Graph provider raises error instead of falling back."""
        client = TestClient(app)

        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "ms_graph"}):
            with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
                mock_provider = MagicMock()
                mock_provider.fetch_events.side_effect = HTTPException(status_code=503, detail="API error")
                mock_factory.return_value = mock_provider

                response = client.get("/digest/preview.json?source=live&date=2025-01-15")

                # HTTPExceptions should propagate with their original status code
                assert response.status_code == 503
                data = response.json()
                assert "API error" in data["detail"]

    def test_preview_live_with_empty_events_returns_empty(self):
        """Test preview with MS Graph provider returns empty when no events (no fallback)."""
        client = TestClient(app)

        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "ms_graph"}):
            with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
                mock_provider = MagicMock()
                mock_provider.fetch_events.return_value = []  # Empty events
                mock_factory.return_value = mock_provider

                response = client.get("/digest/preview.json?source=live&date=2025-01-15")

                assert response.status_code == 200
                data = response.json()
                assert data["source"] == "live"  # No fallback to sample
                assert len(data["meetings"]) == 0  # Empty meetings when no events
