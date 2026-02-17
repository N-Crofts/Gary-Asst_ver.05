"""
Tests for mailbox allowlist enforcement.
"""
import os
from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException

from app.calendar.ms_graph_adapter import MSGraphAdapter, create_ms_graph_adapter
from app.core.config import load_config


class TestMailboxAllowlist:
    """Test mailbox allowlist enforcement."""

    def test_allowed_mailbox_succeeds(self):
        """Test that allowed mailbox can be accessed."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="sorum.crofts@rpck.com",
            allowed_mailboxes=["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"]
        )
        
        # Should not raise
        adapter._validate_mailbox_access("sorum.crofts@rpck.com")
        adapter._validate_mailbox_access("chintan.panchal@rpck.com")

    def test_disallowed_mailbox_raises_exception(self):
        """Test that disallowed mailbox raises ValueError."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="sorum.crofts@rpck.com",
            allowed_mailboxes=["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"]
        )
        
        with pytest.raises(ValueError) as exc_info:
            adapter._validate_mailbox_access("unauthorized@example.com")
        assert "Mailbox access denied" in str(exc_info.value)
        assert "unauthorized@example.com" in str(exc_info.value)

    def test_mailbox_comparison_case_insensitive(self):
        """Test that mailbox comparison is case-insensitive."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="sorum.crofts@rpck.com",
            allowed_mailboxes=["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"]
        )
        
        # Should accept various case combinations
        adapter._validate_mailbox_access("SORUM.CROFTS@RPCK.COM")
        adapter._validate_mailbox_access("SorUm.CrOfTs@RpCk.CoM")
        adapter._validate_mailbox_access("chintan.panchal@rpck.com")

    def test_empty_mailbox_raises_exception(self):
        """Test that empty mailbox raises ValueError."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            allowed_mailboxes=["sorum.crofts@rpck.com"]
        )
        
        with pytest.raises(ValueError) as exc_info:
            adapter._validate_mailbox_access("")
        assert "Mailbox cannot be empty" in str(exc_info.value)

    def test_no_allowed_mailboxes_raises_exception(self):
        """Test that no allowed mailboxes configured raises exception."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            allowed_mailboxes=[]
        )
        
        with pytest.raises(ValueError) as exc_info:
            adapter._validate_mailbox_access("any@example.com")
        assert "No allowed mailboxes configured" in str(exc_info.value)

    def test_fetch_events_validates_mailbox(self):
        """Test that fetch_events validates mailbox before making Graph request."""
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            user_email="sorum.crofts@rpck.com",
            allowed_mailboxes=["sorum.crofts@rpck.com"]
        )
        
        # Mock Graph API to avoid actual calls
        with patch.object(adapter, '_get_access_token', return_value="fake_token"):
            with patch('httpx.Client') as mock_client:
                mock_response_obj = MagicMock()
                mock_response_obj.status_code = 200
                mock_response_obj.json.return_value = {"value": []}
                mock_response_obj.raise_for_status.return_value = None
                mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj
                
                # Allowed mailbox should work
                events = adapter.fetch_events("2025-01-15", user="sorum.crofts@rpck.com")
                assert isinstance(events, list)
                
                # Disallowed mailbox should raise
                with pytest.raises(ValueError) as exc_info:
                    adapter.fetch_events("2025-01-15", user="unauthorized@example.com")
                assert "Mailbox access denied" in str(exc_info.value)

    def test_fetch_events_between_validates_mailbox(self):
        """Test that fetch_events_between validates mailbox."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        adapter = MSGraphAdapter(
            "tenant", "client", "secret",
            allowed_mailboxes=["sorum.crofts@rpck.com"]
        )
        
        start_dt = datetime(2025, 1, 15, 0, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        end_dt = datetime(2025, 1, 15, 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))
        
        # Disallowed mailbox should raise before making Graph request
        with pytest.raises(ValueError) as exc_info:
            adapter.fetch_events_between("unauthorized@example.com", start_dt, end_dt)
        assert "Mailbox access denied" in str(exc_info.value)

    def test_create_adapter_loads_allowed_mailboxes_from_config(self):
        """Test that create_ms_graph_adapter loads allowed mailboxes from config."""
        with patch.dict(os.environ, {
            "CALENDAR_PROVIDER": "ms_graph",
            "MS_TENANT_ID": "tenant",
            "MS_CLIENT_ID": "client",
            "MS_CLIENT_SECRET": "secret",
            "MS_USER_EMAIL": "sorum.crofts@rpck.com",
            "ALLOWED_MAILBOXES": "sorum.crofts@rpck.com,chintan.panchal@rpck.com"
        }):
            adapter = create_ms_graph_adapter()
            assert adapter.allowed_mailboxes == ["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"]
            
            # Should validate correctly
            adapter._validate_mailbox_access("sorum.crofts@rpck.com")
            adapter._validate_mailbox_access("chintan.panchal@rpck.com")
            
            with pytest.raises(ValueError):
                adapter._validate_mailbox_access("unauthorized@example.com")

    def test_config_parses_allowed_mailboxes_normalized(self):
        """Test that config normalizes allowed mailboxes to lowercase."""
        with patch.dict(os.environ, {
            "ALLOWED_MAILBOXES": "SORUM.CROFTS@RPCK.COM,Chintan.Panchal@RPCK.COM"
        }):
            config = load_config()
            assert "sorum.crofts@rpck.com" in config.allowed_mailboxes
            assert "chintan.panchal@rpck.com" in config.allowed_mailboxes
            assert "SORUM.CROFTS@RPCK.COM" not in config.allowed_mailboxes  # Should be normalized
