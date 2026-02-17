"""
Tests for Graph 403 error handling with Application Access Policy detection.
"""
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException

from app.calendar.ms_graph_adapter import MSGraphAdapter


class TestGraph403ErrorHandling:
    """Test Graph 403 error handling and Application Access Policy detection."""

    def test_403_app_access_policy_error(self):
        """Test that Application Access Policy errors return 403 with actionable message."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="user@example.com",
            allowed_mailboxes=["user@example.com"]
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 403
                mock_response_obj.json.return_value = {
                    "error": {
                        "code": "ErrorAccessDenied",
                        "message": "Access to OData is disabled. Blocked by tenant configured AppOnly AccessPolicy settings."
                    }
                }

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                
                assert exc_info.value.status_code == 403
                assert "Tenant policy blocks app-only access" in str(exc_info.value.detail)
                assert "Application Access Policy" in str(exc_info.value.detail)
                assert "Ask IT" in str(exc_info.value.detail)

    def test_403_apponly_accesspolicy_error(self):
        """Test detection of 'AppOnly AccessPolicy' error message."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="user@example.com",
            allowed_mailboxes=["user@example.com"]
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 403
                mock_response_obj.json.return_value = {
                    "error": {
                        "code": "ErrorAccessDenied",
                        "message": "Access denied. AppOnly AccessPolicy configured."
                    }
                }

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                
                assert exc_info.value.status_code == 403
                assert "Tenant policy blocks app-only access" in str(exc_info.value.detail)

    def test_403_generic_access_denied(self):
        """Test that generic 403 errors return 403 with generic message."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="user@example.com",
            allowed_mailboxes=["user@example.com"]
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 403
                mock_response_obj.json.return_value = {
                    "error": {
                        "code": "ErrorAccessDenied",
                        "message": "Insufficient privileges to complete the operation."
                    }
                }

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                
                assert exc_info.value.status_code == 403
                assert "Access denied to calendar" in str(exc_info.value.detail)
                assert "ErrorAccessDenied" in str(exc_info.value.detail)

    def test_403_malformed_error_response(self):
        """Test handling of malformed 403 error response."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="user@example.com",
            allowed_mailboxes=["user@example.com"]
        )

        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 403
                mock_response_obj.json.side_effect = ValueError("Invalid JSON")

                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

                with pytest.raises(HTTPException) as exc_info:
                    adapter.fetch_events("2025-01-15")
                
                assert exc_info.value.status_code == 403
                assert "Access denied to calendar" in str(exc_info.value.detail)
