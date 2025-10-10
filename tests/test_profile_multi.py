import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.profile.store import get_profile, _find_profile_by_mailbox, _build_profile_from_data
from app.rendering.context_builder import build_digest_context_with_provider
from app.main import app


class TestProfileStoreMultiUser:
    """Test profile store with mailbox-based multi-user support."""

    def test_get_profile_by_mailbox_success(self):
        """Test getting profile by mailbox address."""
        profile = get_profile(mailbox="sorum.crofts@rpck.com")

        assert profile.id == "sorum"
        assert profile.exec_name == "Sorum Crofts"
        assert profile.default_recipients == ["sorum.crofts@rpck.com", "bizdev@rpck.com"]
        assert profile.max_items["news"] == 6
        assert profile.max_items["talking_points"] == 4
        assert profile.max_items["smart_questions"] == 4
        assert "venture partners" in profile.company_aliases

    def test_get_profile_by_mailbox_with_mailbox_field(self):
        """Test getting profile by mailbox field in profile data."""
        profile = get_profile(mailbox="chintan@rpck.com")

        assert profile.id == "chintan"
        assert profile.exec_name == "Chintan Panchal"
        assert profile.default_recipients == ["chintan@rpck.com", "carolyn@rpck.com"]
        assert profile.max_items["news"] == 3
        assert profile.max_items["talking_points"] == 2
        assert profile.max_items["smart_questions"] == 2

    def test_get_profile_by_mailbox_fallback_to_default(self):
        """Test that unknown mailbox falls back to default profile."""
        profile = get_profile(mailbox="unknown@rpck.com")

        assert profile.id == "default"
        assert profile.exec_name == "RPCK Biz Dev"
        assert profile.default_recipients == ["bizdev@rpck.com"]

    def test_get_profile_mailbox_takes_precedence_over_profile_id(self):
        """Test that mailbox parameter takes precedence over profile_id."""
        profile = get_profile(profile_id="chintan", mailbox="sorum.crofts@rpck.com")

        # Should use Sorum's profile, not Chintan's
        assert profile.id == "sorum"
        assert profile.exec_name == "Sorum Crofts"

    def test_get_profile_fallback_to_profile_id_when_no_mailbox(self):
        """Test that profile_id is used when no mailbox is provided."""
        profile = get_profile(profile_id="chintan")

        assert profile.id == "chintan"
        assert profile.exec_name == "Chintan Panchal"

    def test_find_profile_by_mailbox_direct_key(self):
        """Test finding profile when mailbox is the direct key."""
        profiles_data = {
            "sorum.crofts@rpck.com": {
                "id": "sorum",
                "exec_name": "Sorum Crofts",
                "default_recipients": ["sorum.crofts@rpck.com"]
            }
        }

        result = _find_profile_by_mailbox(profiles_data, "sorum.crofts@rpck.com")

        assert result is not None
        assert result["id"] == "sorum"
        assert result["exec_name"] == "Sorum Crofts"

    def test_find_profile_by_mailbox_field(self):
        """Test finding profile when mailbox is in the mailbox field."""
        profiles_data = {
            "chintan": {
                "id": "chintan",
                "exec_name": "Chintan Panchal",
                "mailbox": "chintan@rpck.com",
                "default_recipients": ["chintan@rpck.com"]
            }
        }

        result = _find_profile_by_mailbox(profiles_data, "chintan@rpck.com")

        assert result is not None
        assert result["id"] == "chintan"
        assert result["exec_name"] == "Chintan Panchal"

    def test_find_profile_by_mailbox_not_found(self):
        """Test that None is returned when mailbox is not found."""
        profiles_data = {
            "default": {
                "id": "default",
                "exec_name": "Default User"
            }
        }

        result = _find_profile_by_mailbox(profiles_data, "unknown@rpck.com")

        assert result is None

    def test_build_profile_from_data_with_defaults(self):
        """Test building profile from data with proper defaults."""
        profile_data = {
            "id": "test",
            "exec_name": "Test User",
            "default_recipients": ["test@rpck.com"]
        }

        profile = _build_profile_from_data(profile_data, "test")

        assert profile.id == "test"
        assert profile.exec_name == "Test User"
        assert profile.default_recipients == ["test@rpck.com"]
        assert profile.sections_order == ["company", "news", "talking_points", "smart_questions"]
        assert profile.max_items["news"] == 5
        assert profile.max_items["talking_points"] == 3
        assert profile.max_items["smart_questions"] == 3
        assert profile.company_aliases == {}


class TestContextBuilderMultiUser:
    """Test context builder with mailbox-based profile routing."""

    def test_build_digest_context_with_mailbox(self):
        """Test building digest context with mailbox-specific profile."""
        context = build_digest_context_with_provider(
            source="sample",
            mailbox="sorum.crofts@rpck.com"
        )

        assert context["exec_name"] == "Sorum Crofts"
        assert len(context["meetings"]) >= 1
        assert context["source"] == "sample"

    def test_build_digest_context_with_different_mailbox(self):
        """Test building digest context with different mailbox."""
        context = build_digest_context_with_provider(
            source="sample",
            mailbox="chintan@rpck.com"
        )

        assert context["exec_name"] == "Chintan Panchal"
        assert len(context["meetings"]) >= 1
        assert context["source"] == "sample"

    def test_build_digest_context_without_mailbox_uses_default(self):
        """Test building digest context without mailbox uses default profile."""
        context = build_digest_context_with_provider(source="sample")

        assert context["exec_name"] == "RPCK Biz Dev"
        assert len(context["meetings"]) >= 1
        assert context["source"] == "sample"

    def test_build_digest_context_exec_name_override(self):
        """Test that exec_name parameter overrides profile exec_name."""
        context = build_digest_context_with_provider(
            source="sample",
            mailbox="sorum.crofts@rpck.com",
            exec_name="Custom Name"
        )

        assert context["exec_name"] == "Custom Name"
        assert len(context["meetings"]) >= 1


class TestPreviewEndpointMultiUser:
    """Test preview endpoints with mailbox-based profile routing."""

    def test_preview_with_mailbox_parameter(self):
        """Test preview endpoint with mailbox parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com")

        assert response.status_code == 200
        data = response.json()
        assert data["exec_name"] == "Sorum Crofts"
        assert len(data["meetings"]) >= 1

    def test_preview_with_different_mailbox(self):
        """Test preview endpoint with different mailbox."""
        client = TestClient(app)

        response = client.get("/digest/preview.json?source=sample&mailbox=chintan@rpck.com")

        assert response.status_code == 200
        data = response.json()
        assert data["exec_name"] == "Chintan Panchal"
        assert len(data["meetings"]) >= 1

    def test_preview_without_mailbox_uses_default(self):
        """Test preview endpoint without mailbox uses default profile."""
        client = TestClient(app)

        response = client.get("/digest/preview.json?source=sample")

        assert response.status_code == 200
        data = response.json()
        assert data["exec_name"] == "RPCK Biz Dev"
        assert len(data["meetings"]) >= 1

    def test_preview_exec_name_override_with_mailbox(self):
        """Test that exec_name parameter overrides profile exec_name."""
        client = TestClient(app)

        response = client.get("/digest/preview.json?source=sample&mailbox=sorum.crofts@rpck.com&exec_name=Custom Name")

        assert response.status_code == 200
        data = response.json()
        assert data["exec_name"] == "Custom Name"
        assert len(data["meetings"]) >= 1

    def test_preview_single_event_with_mailbox(self):
        """Test single event preview with mailbox parameter."""
        client = TestClient(app)

        response = client.get("/digest/preview/event/sample-1.json?source=sample&mailbox=sorum.crofts@rpck.com")

        assert response.status_code == 200
        data = response.json()
        assert data["exec_name"] == "Sorum Crofts"
        assert len(data["meetings"]) == 1


class TestDigestSendMultiUser:
    """Test digest send endpoint with mailbox-based profile routing."""

    def test_send_digest_with_mailbox_parameter(self):
        """Test digest send with mailbox parameter."""
        client = TestClient(app)

        response = client.get("/digest/send?source=sample&mailbox=sorum.crofts@rpck.com")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["action"] == "rendered"
        assert "Sorum Crofts" in data["subject"] or "sorum.crofts@rpck.com" in str(data["recipients"])

    def test_send_digest_with_different_mailbox(self):
        """Test digest send with different mailbox."""
        client = TestClient(app)

        response = client.get("/digest/send?source=sample&mailbox=chintan@rpck.com")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["action"] == "rendered"
        assert "chintan@rpck.com" in str(data["recipients"])

    def test_send_digest_without_mailbox_uses_default(self):
        """Test digest send without mailbox uses default profile."""
        client = TestClient(app)

        response = client.get("/digest/send?source=sample")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["action"] == "rendered"
        assert "bizdev@rpck.com" in str(data["recipients"])

    def test_send_digest_post_with_mailbox(self):
        """Test digest send POST with mailbox in body."""
        client = TestClient(app)

        response = client.post("/digest/send", json={
            "source": "sample",
            "mailbox": "sorum.crofts@rpck.com"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["action"] == "rendered"
        assert "sorum.crofts@rpck.com" in str(data["recipients"])

    def test_send_digest_recipient_override_with_mailbox(self):
        """Test that recipient override works with mailbox-based profiles."""
        client = TestClient(app)

        # Mock ALLOW_RECIPIENT_OVERRIDE to be true for this test
        with patch.dict(os.environ, {"ALLOW_RECIPIENT_OVERRIDE": "true"}):
            response = client.post("/digest/send", json={
                "source": "sample",
                "mailbox": "sorum.crofts@rpck.com",
                "recipients": ["override@rpck.com"]
            })

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["action"] == "rendered"
            assert "override@rpck.com" in str(data["recipients"])


class TestProfileIntegration:
    """Test integration between profile system and other components."""

    def test_profile_company_aliases_work_with_mailbox(self):
        """Test that company aliases from mailbox-specific profiles work."""
        profile = get_profile(mailbox="sorum.crofts@rpck.com")

        # Sorum's profile should have "venture partners" alias
        assert "venture partners" in profile.company_aliases
        assert "vp" in profile.company_aliases["venture partners"]
        assert "venture partners llc" in profile.company_aliases["venture partners"]

    def test_profile_max_items_work_with_mailbox(self):
        """Test that max_items from mailbox-specific profiles work."""
        profile = get_profile(mailbox="chintan@rpck.com")

        # Chintan's profile should have different limits
        assert profile.max_items["news"] == 3
        assert profile.max_items["talking_points"] == 2
        assert profile.max_items["smart_questions"] == 2

    def test_profile_sections_order_work_with_mailbox(self):
        """Test that sections_order from mailbox-specific profiles work."""
        profile = get_profile(mailbox="sorum.crofts@rpck.com")

        # Should have default sections order
        expected_order = ["company", "news", "talking_points", "smart_questions"]
        assert profile.sections_order == expected_order

    def test_profile_fallback_behavior(self):
        """Test profile fallback behavior for unknown mailboxes."""
        # Test with completely unknown mailbox
        profile = get_profile(mailbox="completely.unknown@rpck.com")

        assert profile.id == "default"
        assert profile.exec_name == "RPCK Biz Dev"
        assert profile.default_recipients == ["bizdev@rpck.com"]
        assert profile.max_items["news"] == 5
        assert profile.max_items["talking_points"] == 3
        assert profile.max_items["smart_questions"] == 3

    def test_profile_with_missing_data_file(self):
        """Test profile behavior when data file is missing."""
        with patch('app.profile.store.DATA_PATH', return_value=__import__('pathlib').Path("/nonexistent/file.json")):
            profile = get_profile(mailbox="sorum.crofts@rpck.com")

            # Should fall back to default profile
            assert profile.id == "default"
            assert profile.exec_name == "RPCK Biz Dev"
            assert profile.default_recipients == ["bizdev@rpck.com"]
