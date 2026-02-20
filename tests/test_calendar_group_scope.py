import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.calendar.ms_graph_adapter import MSGraphAdapter, create_ms_graph_adapter
from app.calendar.provider import select_calendar_provider
from app.main import app


class TestMSGraphGroupAccess:
    """Test MS Graph adapter with group-based calendar access."""

    def test_create_adapter_with_group_config(self):
        """Test that adapter can be created with group configuration."""
        with patch.dict(os.environ, {
            "MS_TENANT_ID": "tenant",
            "MS_CLIENT_ID": "client",
            "MS_CLIENT_SECRET": "secret",
            "ALLOWED_MAILBOX_GROUP": "GaryAsst-AllowedMailboxes"
        }):
            adapter = create_ms_graph_adapter()
            assert adapter.allowed_mailbox_group == "GaryAsst-AllowedMailboxes"
            assert adapter.user_email is None

    def test_create_adapter_with_user_and_group_prioritizes_group(self):
        """Test that when both user and group are configured, group takes precedence and user_email is None."""
        with patch.dict(os.environ, {
            "MS_TENANT_ID": "tenant",
            "MS_CLIENT_ID": "client",
            "MS_CLIENT_SECRET": "secret",
            "MS_USER_EMAIL": "user@example.com",
            "ALLOWED_MAILBOX_GROUP": "GaryAsst-AllowedMailboxes"
        }):
            adapter = create_ms_graph_adapter()
            assert adapter.allowed_mailbox_group == "GaryAsst-AllowedMailboxes"
            assert adapter.user_email is None

    def test_create_adapter_missing_both_user_and_group_raises_exception(self):
        """Test that missing both user and group raises HTTPException."""
        with patch.dict(os.environ, {
            "MS_TENANT_ID": "tenant",
            "MS_CLIENT_ID": "client",
            "MS_CLIENT_SECRET": "secret",
            "MS_USER_EMAIL": "",
            "ALLOWED_MAILBOX_GROUP": "",
        }, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                create_ms_graph_adapter()
            assert exc_info.value.status_code == 503
            assert "Either MS_USER_EMAIL or ALLOWED_MAILBOX_GROUP must be provided" in str(exc_info.value.detail)

    def test_get_group_members_success(self):
        """Test successful group member retrieval."""
        # Mock Graph API responses
        group_response = {
            "value": [
                {
                    "id": "group-123",
                    "displayName": "GaryAsst-AllowedMailboxes"
                }
            ]
        }

        members_response = {
            "value": [
                {
                    "mail": "user1@example.com",
                    "userPrincipalName": "user1@example.com"
                },
                {
                    "mail": "user2@example.com",
                    "userPrincipalName": "user2@example.com"
                },
                {
                    "mail": None,
                    "userPrincipalName": "user3@example.com"
                }
            ]
        }

        adapter = MSGraphAdapter("tenant", "client", "secret", allowed_mailbox_group="GaryAsst-AllowedMailboxes")

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('app.calendar.ms_graph_adapter.httpx.Client') as mock_client:
                # Mock the group lookup response
                mock_group_response = MagicMock()
                mock_group_response.status_code = 200
                mock_group_response.json.return_value = group_response
                mock_group_response.raise_for_status.return_value = None

                # Mock the members lookup response
                mock_members_response = MagicMock()
                mock_members_response.status_code = 200
                mock_members_response.json.return_value = members_response
                mock_members_response.raise_for_status.return_value = None

                # Configure the mock client to return different responses for different calls
                mock_client.return_value.__enter__.return_value.get.side_effect = [
                    mock_group_response,  # First call for group lookup
                    mock_members_response  # Second call for members lookup
                ]

                members = adapter._get_group_members("GaryAsst-AllowedMailboxes")

                assert len(members) == 3
                assert "user1@example.com" in members
                assert "user2@example.com" in members
                assert "user3@example.com" in members

    def test_get_group_members_group_not_found(self):
        """Test that group not found raises HTTPException."""
        group_response = {"value": []}  # Empty response means group not found

        adapter = MSGraphAdapter("tenant", "client", "secret", allowed_mailbox_group="GaryAsst-AllowedMailboxes")

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('app.calendar.ms_graph_adapter.httpx.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = group_response
                mock_response.raise_for_status.return_value = None

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response

                with pytest.raises(HTTPException) as exc_info:
                    adapter._get_group_members("GaryAsst-AllowedMailboxes")
                assert exc_info.value.status_code == 404
                assert "Group 'GaryAsst-AllowedMailboxes' not found" in str(exc_info.value.detail)

    def test_fetch_events_with_group_access_success(self):
        """Test successful event fetching with group access."""
        # Mock group members
        group_members = ["user1@example.com", "user2@example.com"]

        # Mock events for each user (organizer so filter includes event for that mailbox)
        user1_events = {
            "value": [
                {
                    "subject": "User 1 Meeting",
                    "start": {"dateTime": "2025-01-15T14:30:00.0000000Z"},
                    "end": {"dateTime": "2025-01-15T15:30:00.0000000Z"},
                    "location": {"displayName": "Room A"},
                    "attendees": [],
                    "organizer": {"emailAddress": {"address": "user1@example.com", "name": "User 1"}},
                    "bodyPreview": "User 1 notes"
                }
            ]
        }

        user2_events = {
            "value": [
                {
                    "subject": "User 2 Meeting",
                    "start": {"dateTime": "2025-01-15T16:00:00.0000000Z"},
                    "end": {"dateTime": "2025-01-15T17:00:00.0000000Z"},
                    "location": {"displayName": "Room B"},
                    "attendees": [],
                    "organizer": {"emailAddress": {"address": "user2@example.com", "name": "User 2"}},
                    "bodyPreview": "User 2 notes"
                }
            ]
        }

        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            allowed_mailbox_group="GaryAsst-AllowedMailboxes",
            allowed_mailboxes=group_members,
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch.object(adapter, '_get_group_members', return_value=group_members):
                with patch('app.calendar.ms_graph_adapter.httpx.Client') as mock_client:
                    # Mock responses for each user's calendar
                    mock_user1_response = MagicMock()
                    mock_user1_response.status_code = 200
                    mock_user1_response.json.return_value = user1_events
                    mock_user1_response.raise_for_status.return_value = None

                    mock_user2_response = MagicMock()
                    mock_user2_response.status_code = 200
                    mock_user2_response.json.return_value = user2_events
                    mock_user2_response.raise_for_status.return_value = None

                    # Configure mock to return different responses for different users
                    mock_client.return_value.__enter__.return_value.get.side_effect = [
                        mock_user1_response,  # First call for user1
                        mock_user2_response   # Second call for user2
                    ]

                    events = adapter.fetch_events("2025-01-15")

                    assert len(events) == 2
                    # Events should be sorted by start time (User 1 at 14:30 UTC = 9:30 ET, User 2 at 16:00 UTC = 11:00 ET)
                    assert events[0].subject == "User 1 Meeting"
                    assert events[1].subject == "User 2 Meeting"
                    assert "09:30" in events[0].start_time or "2025-01-15" in events[0].start_time
                    assert "11:00" in events[1].start_time or "16:00" in events[1].start_time

    def test_fetch_events_with_group_access_handles_user_errors(self):
        """Test that individual user errors don't break the entire operation."""
        group_members = ["user1@example.com", "user2@example.com", "user3@example.com"]

        # Only user2 will have successful events (organizer so filter includes event for that mailbox)
        user2_events = {
            "value": [
                {
                    "subject": "User 2 Meeting",
                    "start": {"dateTime": "2025-01-15T14:30:00.0000000Z"},
                    "end": {"dateTime": "2025-01-15T15:30:00.0000000Z"},
                    "location": {"displayName": "Room B"},
                    "attendees": [],
                    "organizer": {"emailAddress": {"address": "user2@example.com", "name": "User 2"}},
                    "bodyPreview": "User 2 notes"
                }
            ]
        }

        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            allowed_mailbox_group="GaryAsst-AllowedMailboxes",
            allowed_mailboxes=group_members,
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch.object(adapter, '_get_group_members', return_value=group_members):
                with patch('app.calendar.ms_graph_adapter.httpx.Client') as mock_client:
                    # Mock responses: user1 and user3 will fail, user2 will succeed
                    mock_user1_response = MagicMock()
                    mock_user1_response.status_code = 403  # Permission denied
                    mock_user1_response.json.return_value = {"error": {"code": "ErrorAccessDenied", "message": "Access denied"}}

                    mock_user2_response = MagicMock()
                    mock_user2_response.status_code = 200
                    mock_user2_response.json.return_value = user2_events
                    mock_user2_response.raise_for_status.return_value = None

                    mock_user3_response = MagicMock()
                    mock_user3_response.status_code = 404  # User not found
                    mock_user3_response.json.return_value = {"error": {"code": "ErrorItemNotFound", "message": "Not found"}}

                    # Configure mock to return different responses
                    mock_client.return_value.__enter__.return_value.get.side_effect = [
                        mock_user1_response,  # user1 - permission denied
                        mock_user2_response,  # user2 - success
                        mock_user3_response   # user3 - not found
                    ]

                    events = adapter.fetch_events("2025-01-15")

                    # Should still get events from user2 despite user1 and user3 failing
                    assert len(events) == 1
                    assert events[0].subject == "User 2 Meeting"

    def test_fetch_events_fallback_to_user_email(self):
        """Test that when group is not configured, it falls back to user email."""
        user_events = {
            "value": [
                {
                    "subject": "Single User Meeting",
                    "start": {"dateTime": "2025-01-15T14:30:00.0000000Z"},
                    "end": {"dateTime": "2025-01-15T15:30:00.0000000Z"},
                    "location": {"displayName": "Room A"},
                    "attendees": [],
                    "organizer": {"emailAddress": {"address": "user@example.com", "name": "User"}},
                    "bodyPreview": "Single user notes"
                }
            ]
        }

        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="user@example.com",
            allowed_mailboxes=["user@example.com"],
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('app.calendar.ms_graph_adapter.httpx.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = user_events
                mock_response.raise_for_status.return_value = None

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response

                events = adapter.fetch_events("2025-01-15")

                assert len(events) == 1
                assert events[0].subject == "Single User Meeting"

    def test_fetch_events_no_configuration_raises_exception(self):
        """Test that missing both user and group configuration raises exception."""
        adapter = MSGraphAdapter("tenant", "client", "secret")

        with pytest.raises(HTTPException) as exc_info:
            adapter.fetch_events("2025-01-15")
        assert exc_info.value.status_code == 503
        assert "Either MS_USER_EMAIL or ALLOWED_MAILBOX_GROUP must be provided" in str(exc_info.value.detail)


class TestProviderFactoryWithGroupAccess:
    """Test the calendar provider factory with group access configuration."""

    def test_select_provider_ms_graph_with_group_config(self):
        """Test that MS Graph provider is selected when configured with group."""
        with patch.dict(os.environ, {
            "CALENDAR_PROVIDER": "ms_graph",
            "MS_TENANT_ID": "tenant",
            "MS_CLIENT_ID": "client",
            "MS_CLIENT_SECRET": "secret",
            "ALLOWED_MAILBOX_GROUP": "GaryAsst-AllowedMailboxes"
        }):
            provider = select_calendar_provider()
            assert provider.__class__.__name__ == "MSGraphAdapter"
            assert provider.allowed_mailbox_group == "GaryAsst-AllowedMailboxes"


class TestPreviewEndpointWithGroupAccess:
    """Test preview endpoint with group-based MS Graph provider."""

    def test_preview_live_with_group_access_success(self):
        """Test preview with group-based MS Graph provider returns live data."""
        client = TestClient(app)

        # Mock the provider to return events from multiple users
        mock_events = [
            MagicMock(
                subject="Group User 1 Meeting",
                start_time="9:30 AM ET",
                end_time="10:30 AM ET",
                location="Zoom",
                attendees=[],
                notes=None,
                model_dump=lambda: {
                    "subject": "Group User 1 Meeting",
                    "start_time": "9:30 AM ET",
                    "end_time": "10:30 AM ET",
                    "location": "Zoom",
                    "attendees": [],
                    "notes": None
                }
            ),
            MagicMock(
                subject="Group User 2 Meeting",
                start_time="2:00 PM ET",
                end_time="3:00 PM ET",
                location="Teams",
                attendees=[],
                notes=None,
                model_dump=lambda: {
                    "subject": "Group User 2 Meeting",
                    "start_time": "2:00 PM ET",
                    "end_time": "3:00 PM ET",
                    "location": "Teams",
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
                assert len(data["meetings"]) == 2
                assert data["meetings"][0]["subject"] == "Group User 1 Meeting"
                assert data["meetings"][1]["subject"] == "Group User 2 Meeting"

    def test_preview_live_with_group_access_error_handling(self):
        """Test preview with group-based MS Graph provider propagates HTTPExceptions."""
        client = TestClient(app)

        with patch.dict(os.environ, {"CALENDAR_PROVIDER": "ms_graph"}):
            with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
                mock_provider = MagicMock()
                mock_provider.fetch_events.side_effect = HTTPException(status_code=503, detail="Group API error")
                mock_factory.return_value = mock_provider

                response = client.get("/digest/preview.json?source=live&date=2025-01-15")

                # HTTPExceptions should propagate with their original status code
                assert response.status_code == 503
                data = response.json()
                assert "Group API error" in data["detail"]
