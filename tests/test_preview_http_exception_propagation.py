"""
Tests for HTTPException propagation in preview routes.
"""
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app


class TestHTTPExceptionPropagation:
    """Test that HTTPExceptions from calendar provider propagate correctly."""

    def test_preview_propagates_403_error(self):
        """Test that 403 errors from MSGraphAdapter propagate with correct status code."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
            mock_provider = MagicMock()
            mock_provider.fetch_events.side_effect = HTTPException(
                status_code=403,
                detail="Tenant policy blocks app-only access to mailbox user@example.com (Application Access Policy). Ask IT to add the mailbox to the app's allowed scope."
            )
            mock_factory.return_value = mock_provider

            response = client.get("/digest/preview.json?source=live&date=2025-01-15")

            # 403 should propagate with original status code
            assert response.status_code == 403
            data = response.json()
            assert "Tenant policy blocks app-only access" in data["detail"]
            assert "Application Access Policy" in data["detail"]

    def test_preview_propagates_401_error(self):
        """Test that 401 errors from calendar provider propagate with correct status code."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
            mock_provider = MagicMock()
            mock_provider.fetch_events.side_effect = HTTPException(
                status_code=401,
                detail="MS Graph authentication failed"
            )
            mock_factory.return_value = mock_provider

            response = client.get("/digest/preview.json?source=live&date=2025-01-15")

            # 401 should propagate with original status code
            assert response.status_code == 401
            data = response.json()
            assert "MS Graph authentication failed" in data["detail"]

    def test_preview_propagates_404_error(self):
        """Test that 404 errors from calendar provider propagate with correct status code."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
            mock_provider = MagicMock()
            mock_provider.fetch_events.side_effect = HTTPException(
                status_code=404,
                detail="User not found: user@example.com"
            )
            mock_factory.return_value = mock_provider

            response = client.get("/digest/preview.json?source=live&date=2025-01-15")

            # 404 should propagate with original status code
            assert response.status_code == 404
            data = response.json()
            assert "User not found" in data["detail"]

    def test_preview_html_propagates_403_error(self):
        """Test that 403 errors propagate correctly in HTML preview endpoint."""
        client = TestClient(app)

        with patch('app.rendering.context_builder.select_calendar_provider') as mock_factory:
            mock_provider = MagicMock()
            mock_provider.fetch_events.side_effect = HTTPException(
                status_code=403,
                detail="Access denied"
            )
            mock_factory.return_value = mock_provider

            response = client.get("/digest/preview?source=live&date=2025-01-15")

            # 403 should propagate with original status code
            assert response.status_code == 403
