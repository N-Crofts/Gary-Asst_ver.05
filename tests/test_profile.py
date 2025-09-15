import os
import json
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
from fastapi.testclient import TestClient

from app.profile.models import ExecProfile
from app.profile.store import get_profile, _get_default_profile
from app.rendering.context_builder import _apply_company_aliases, _trim_meeting_sections
from app.main import app


class TestExecProfile:
    """Test ExecProfile model."""

    def test_default_profile_creation(self):
        """Test creating a profile with default values."""
        profile = ExecProfile(
            id="test",
            exec_name="Test User",
            default_recipients=["test@example.com"]
        )

        assert profile.id == "test"
        assert profile.exec_name == "Test User"
        assert profile.default_recipients == ["test@example.com"]
        assert profile.sections_order == ["company", "news", "talking_points", "smart_questions"]
        assert profile.max_items["news"] == 5
        assert profile.max_items["talking_points"] == 3
        assert profile.max_items["smart_questions"] == 3
        assert profile.company_aliases == {}


class TestProfileStore:
    """Test profile store functionality."""

    def test_get_default_profile_when_file_missing(self):
        """Test that default profile is returned when file doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            profile = get_profile("nonexistent")
            assert profile.id == "nonexistent"
            assert profile.exec_name == "RPCK Biz Dev"
            assert profile.default_recipients == ["bizdev@rpck.com"]

    def test_get_profile_from_json(self):
        """Test loading profile from JSON file."""
        test_data = {
            "test_profile": {
                "id": "test_profile",
                "exec_name": "Test Executive",
                "default_recipients": ["test@example.com", "admin@example.com"],
                "max_items": {
                    "news": 2,
                    "talking_points": 1,
                    "smart_questions": 1
                },
                "company_aliases": {
                    "acme": ["acme corp", "acme inc"]
                }
            }
        }

        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(test_data))):
                profile = get_profile("test_profile")

                assert profile.id == "test_profile"
                assert profile.exec_name == "Test Executive"
                assert profile.default_recipients == ["test@example.com", "admin@example.com"]
                assert profile.max_items["news"] == 2
                assert profile.max_items["talking_points"] == 1
                assert profile.company_aliases["acme"] == ["acme corp", "acme inc"]

    def test_get_profile_fallback_to_default(self):
        """Test that missing profile falls back to default."""
        test_data = {
            "default": {
                "id": "default",
                "exec_name": "Default User",
                "default_recipients": ["default@example.com"]
            }
        }

        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(test_data))):
                profile = get_profile("nonexistent_profile")

                # Should fall back to default
                assert profile.id == "default"
                assert profile.exec_name == "Default User"
                assert profile.default_recipients == ["default@example.com"]

    def test_get_profile_with_env_var(self):
        """Test that EXEC_PROFILE_ID environment variable is used."""
        test_data = {
            "chintan": {
                "id": "chintan",
                "exec_name": "Chintan Panchal",
                "default_recipients": ["chintan@rpck.com"]
            }
        }

        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(test_data))):
                with patch.dict(os.environ, {"EXEC_PROFILE_ID": "chintan"}):
                    profile = get_profile()  # No profile_id provided

                    assert profile.id == "chintan"
                    assert profile.exec_name == "Chintan Panchal"
                    assert profile.default_recipients == ["chintan@rpck.com"]

    def test_corrupted_json_fallback(self):
        """Test that corrupted JSON falls back to default profile."""
        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="invalid json")):
                profile = get_profile("test")

                # Should return default profile
                assert profile.id == "test"
                assert profile.exec_name == "RPCK Biz Dev"
                assert profile.default_recipients == ["bizdev@rpck.com"]


class TestContextBuilderHelpers:
    """Test context builder helper functions."""

    def test_apply_company_aliases(self):
        """Test company alias application."""
        meetings = [
            {
                "subject": "Test Meeting",
                "company": {"name": "acme corp"},
                "attendees": [
                    {"name": "John", "company": "acme inc"}
                ]
            }
        ]

        aliases = {
            "acme capital": ["acme corp", "acme inc", "acme llc"]
        }

        result = _apply_company_aliases(meetings, aliases)

        assert result[0]["company"]["name"] == "Acme Capital"
        assert result[0]["attendees"][0]["company"] == "Acme Capital"

    def test_apply_company_aliases_no_aliases(self):
        """Test that meetings are unchanged when no aliases provided."""
        meetings = [
            {
                "subject": "Test Meeting",
                "company": {"name": "acme corp"}
            }
        ]

        result = _apply_company_aliases(meetings, {})

        assert result[0]["company"]["name"] == "acme corp"

    def test_trim_meeting_sections(self):
        """Test trimming meeting sections to max_items limits."""
        meetings = [
            {
                "subject": "Test Meeting",
                "news": ["news1", "news2", "news3", "news4", "news5", "news6"],
                "talking_points": ["point1", "point2", "point3", "point4"],
                "smart_questions": ["q1", "q2", "q3", "q4", "q5"]
            }
        ]

        max_items = {
            "news": 3,
            "talking_points": 2,
            "smart_questions": 4
        }

        result = _trim_meeting_sections(meetings, max_items)

        assert len(result[0]["news"]) == 3
        assert len(result[0]["talking_points"]) == 2
        assert len(result[0]["smart_questions"]) == 4
        assert result[0]["news"] == ["news1", "news2", "news3"]
        assert result[0]["talking_points"] == ["point1", "point2"]
        assert result[0]["smart_questions"] == ["q1", "q2", "q3", "q4"]


class TestPreviewEndpointWithProfiles:
    """Test preview endpoint with profile integration."""

    def test_preview_uses_profile_exec_name(self):
        """Test that preview uses profile exec_name by default."""
        client = TestClient(app)

        # Mock profile to return specific exec_name
        mock_profile = ExecProfile(
            id="test",
            exec_name="Test Executive",
            default_recipients=["test@example.com"]
        )

        with patch('app.rendering.context_builder.get_profile', return_value=mock_profile):
            response = client.get("/digest/preview.json?source=sample")
            data = response.json()

            assert response.status_code == 200
            assert data["exec_name"] == "Test Executive"

    def test_preview_exec_name_override(self):
        """Test that ?exec_name= parameter overrides profile default."""
        client = TestClient(app)

        # Mock profile with default exec_name
        mock_profile = ExecProfile(
            id="test",
            exec_name="Default Executive",
            default_recipients=["test@example.com"]
        )

        with patch('app.rendering.context_builder.get_profile', return_value=mock_profile):
            response = client.get("/digest/preview.json?source=sample&exec_name=Override Name")
            data = response.json()

            assert response.status_code == 200
            assert data["exec_name"] == "Override Name"

    def test_preview_applies_max_items_limits(self):
        """Test that preview respects profile max_items limits."""
        client = TestClient(app)

        # Mock profile with restrictive limits
        mock_profile = ExecProfile(
            id="test",
            exec_name="Test Executive",
            default_recipients=["test@example.com"],
            max_items={
                "news": 1,
                "talking_points": 1,
                "smart_questions": 1
            }
        )

        with patch('app.rendering.context_builder.get_profile', return_value=mock_profile):
            response = client.get("/digest/preview.json?source=sample")
            data = response.json()

            assert response.status_code == 200
            meeting = data["meetings"][0]

            # Should be limited to 1 item each
            assert len(meeting["news"]) <= 1
            assert len(meeting["talking_points"]) <= 1
            assert len(meeting["smart_questions"]) <= 1

    def test_preview_applies_company_aliases(self):
        """Test that preview applies company aliases for enrichment."""
        client = TestClient(app)

        # Mock profile with company aliases
        mock_profile = ExecProfile(
            id="test",
            exec_name="Test Executive",
            default_recipients=["test@example.com"],
            company_aliases={
                "acme capital": ["acme", "acme corp", "acme inc"]
            }
        )

        with patch('app.rendering.context_builder.get_profile', return_value=mock_profile):
            response = client.get("/digest/preview.json?source=sample")
            data = response.json()

            assert response.status_code == 200
            # The enrichment should work with canonicalized company names
            # This test verifies the alias application doesn't break the flow
