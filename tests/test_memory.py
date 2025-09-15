import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.memory.service import (
    _lookback_days, _memory_max_items, _canonicalize_company_name,
    _extract_company_from_meeting, _is_past_meeting, _format_past_meeting,
    fetch_recent_meetings, attach_memory_to_meetings
)
from app.calendar.types import Event, Attendee


class TestMemoryConfiguration:
    """Test memory configuration functions."""

    def test_lookback_days_default(self):
        """Test default lookback days."""
        with patch.dict(os.environ, {}, clear=True):
            assert _lookback_days() == 90

    def test_lookback_days_custom(self):
        """Test custom lookback days."""
        with patch.dict(os.environ, {"LOOKBACK_DAYS": "30"}):
            assert _lookback_days() == 30

    def test_lookback_days_invalid(self):
        """Test invalid lookback days falls back to default."""
        with patch.dict(os.environ, {"LOOKBACK_DAYS": "invalid"}):
            assert _lookback_days() == 90

    def test_memory_max_items_default(self):
        """Test default max items."""
        with patch.dict(os.environ, {}, clear=True):
            assert _memory_max_items() == 3

    def test_memory_max_items_custom(self):
        """Test custom max items."""
        with patch.dict(os.environ, {"MEMORY_MAX_ITEMS": "5"}):
            assert _memory_max_items() == 5


class TestCompanyCanonicalization:
    """Test company name canonicalization."""

    def test_canonicalize_company_name_no_aliases(self):
        """Test canonicalization with no aliases."""
        aliases = {}
        result = _canonicalize_company_name("Acme Capital", aliases)
        assert result == "Acme Capital"

    def test_canonicalize_company_name_exact_match(self):
        """Test canonicalization with exact alias match."""
        aliases = {
            "Acme Capital": ["Acme", "Acme Co"]
        }
        result = _canonicalize_company_name("acme", aliases)
        assert result == "Acme Capital"

    def test_canonicalize_company_name_partial_match(self):
        """Test canonicalization with partial match."""
        aliases = {
            "Acme Capital": ["Acme", "Acme Co"]
        }
        result = _canonicalize_company_name("Acme Co", aliases)
        assert result == "Acme Capital"

    def test_canonicalize_company_name_no_match(self):
        """Test canonicalization with no match."""
        aliases = {
            "Acme Capital": ["Acme", "Acme Co"]
        }
        result = _canonicalize_company_name("TechCorp", aliases)
        assert result == "TechCorp"


class TestCompanyExtraction:
    """Test company extraction from meetings."""

    def test_extract_company_from_company_field(self):
        """Test extracting company from company field."""
        meeting = {
            "company": {"name": "Acme Capital"},
            "attendees": []
        }
        aliases = {}
        result = _extract_company_from_meeting(meeting, aliases)
        assert result == "Acme Capital"

    def test_extract_company_from_attendees(self):
        """Test extracting company from attendees."""
        meeting = {
            "attendees": [
                {"name": "John Doe", "company": "TechCorp"}
            ]
        }
        aliases = {}
        result = _extract_company_from_meeting(meeting, aliases)
        assert result == "TechCorp"

    def test_extract_company_from_subject(self):
        """Test extracting company from subject."""
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "attendees": []
        }
        aliases = {}
        result = _extract_company_from_meeting(meeting, aliases)
        assert result == "Acme Capital"

    def test_extract_company_with_aliases(self):
        """Test extracting company with aliases applied."""
        meeting = {
            "attendees": [
                {"name": "John Doe", "company": "Acme"}
            ]
        }
        aliases = {
            "Acme Capital": ["Acme", "Acme Co"]
        }
        result = _extract_company_from_meeting(meeting, aliases)
        assert result == "Acme Capital"

    def test_extract_company_no_match(self):
        """Test extracting company when no company found."""
        meeting = {
            "subject": "General Meeting",
            "attendees": []
        }
        aliases = {}
        result = _extract_company_from_meeting(meeting, aliases)
        assert result is None


class TestPastMeetingDetection:
    """Test past meeting detection."""

    def test_is_past_meeting_true(self):
        """Test that past meetings are detected."""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        event = Event(
            subject="Past Meeting",
            start_time=f"{yesterday}T10:00:00-05:00",
            end_time=f"{yesterday}T11:00:00-05:00",
            location="Zoom",
            attendees=[],
            notes=None
        )
        current_date = datetime.now().strftime("%Y-%m-%d")
        assert _is_past_meeting(event, current_date) is True

    def test_is_past_meeting_false(self):
        """Test that future meetings are not detected as past."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        event = Event(
            subject="Future Meeting",
            start_time=f"{tomorrow}T10:00:00-05:00",
            end_time=f"{tomorrow}T11:00:00-05:00",
            location="Zoom",
            attendees=[],
            notes=None
        )
        current_date = datetime.now().strftime("%Y-%m-%d")
        assert _is_past_meeting(event, current_date) is False

    def test_is_past_meeting_invalid_date(self):
        """Test handling of invalid date formats."""
        event = Event(
            subject="Invalid Date Meeting",
            start_time="invalid-date",
            end_time="invalid-date",
            location="Zoom",
            attendees=[],
            notes=None
        )
        current_date = datetime.now().strftime("%Y-%m-%d")
        assert _is_past_meeting(event, current_date) is False


class TestPastMeetingFormatting:
    """Test past meeting formatting."""

    def test_format_past_meeting(self):
        """Test formatting a past meeting."""
        event = Event(
            subject="Portfolio Review",
            start_time="2024-12-15T14:30:00-05:00",
            end_time="2024-12-15T15:30:00-05:00",
            location="Zoom",
            attendees=[
                Attendee(name="John Doe", title="Partner", company="Acme Capital"),
                Attendee(name="Jane Smith", title="VP", company="Acme Capital")
            ],
            notes=None
        )

        result = _format_past_meeting(event)

        assert result["date"] == "Dec 15, 2024"
        assert result["subject"] == "Portfolio Review"
        assert len(result["key_attendees"]) == 2
        assert "John Doe (Partner)" in result["key_attendees"]
        assert "Jane Smith (VP)" in result["key_attendees"]

    def test_format_past_meeting_no_attendees(self):
        """Test formatting a past meeting with no attendees."""
        event = Event(
            subject="Solo Meeting",
            start_time="2024-12-15T14:30:00-05:00",
            end_time="2024-12-15T15:30:00-05:00",
            location="Zoom",
            attendees=[],
            notes=None
        )

        result = _format_past_meeting(event)

        assert result["date"] == "Dec 15, 2024"
        assert result["subject"] == "Solo Meeting"
        assert result["key_attendees"] == []

    def test_format_past_meeting_invalid_date(self):
        """Test formatting a past meeting with invalid date."""
        event = Event(
            subject="Invalid Date Meeting",
            start_time="invalid-date",
            end_time="invalid-date",
            location="Zoom",
            attendees=[],
            notes=None
        )

        result = _format_past_meeting(event)

        assert result["date"] == "invalid-date"
        assert result["subject"] == "Invalid Date Meeting"


class TestFetchRecentMeetings:
    """Test fetching recent meetings."""

    def test_fetch_recent_meetings_empty_events(self):
        """Test fetching recent meetings with no events today."""
        result = fetch_recent_meetings([])
        assert result == {}

    def test_fetch_recent_meetings_no_companies(self):
        """Test fetching recent meetings with no companies in events."""
        event = Event(
            subject="General Meeting",
            start_time="2024-12-15T14:30:00-05:00",
            end_time="2024-12-15T15:30:00-05:00",
            location="Zoom",
            attendees=[],
            notes=None
        )

        with patch('app.memory.service.get_profile') as mock_profile:
            mock_profile.return_value.company_aliases = {}
            result = fetch_recent_meetings([event])
            assert result == {}

    def test_fetch_recent_meetings_with_mock_provider(self):
        """Test fetching recent meetings with mock provider."""
        # Today's event with company
        today_event = Event(
            subject="RPCK × Acme Capital — Portfolio Strategy Check-in",
            start_time="2024-12-15T14:30:00-05:00",
            end_time="2024-12-15T15:30:00-05:00",
            location="Zoom",
            attendees=[
                Attendee(name="John Doe", company="Acme Capital")
            ],
            notes=None
        )

        # Past event with same company
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        past_event = Event(
            subject="Previous Acme Meeting",
            start_time=f"{yesterday}T10:00:00-05:00",
            end_time=f"{yesterday}T11:00:00-05:00",
            location="Zoom",
            attendees=[
                Attendee(name="John Doe", company="Acme Capital")
            ],
            notes=None
        )

        # Mock profile
        mock_profile = MagicMock()
        mock_profile.company_aliases = {}

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.fetch_events.return_value = [past_event]

        with patch('app.memory.service.get_profile', return_value=mock_profile):
            with patch('app.memory.service.select_calendar_provider', return_value=mock_provider):
                with patch.dict(os.environ, {"LOOKBACK_DAYS": "1"}):  # Only look back 1 day
                    result = fetch_recent_meetings([today_event])

                    assert "Acme Capital" in result
                    assert len(result["Acme Capital"]) == 1
                    assert result["Acme Capital"][0]["subject"] == "Previous Acme Meeting"

    def test_fetch_recent_meetings_respects_max_items(self):
        """Test that fetch respects max items limit."""
        # Today's event
        today_event = Event(
            subject="RPCK × Acme Capital — Portfolio Strategy Check-in",
            start_time="2024-12-15T14:30:00-05:00",
            end_time="2024-12-15T15:30:00-05:00",
            location="Zoom",
            attendees=[
                Attendee(name="John Doe", company="Acme Capital")
            ],
            notes=None
        )

        # Multiple past events
        past_events = []
        for i in range(5):  # More than max_items (3)
            date = (datetime.now() - timedelta(days=i+1)).strftime("%Y-%m-%d")
            past_event = Event(
                subject=f"Past Meeting {i+1}",
                start_time=f"{date}T10:00:00-05:00",
                end_time=f"{date}T11:00:00-05:00",
                location="Zoom",
                attendees=[
                    Attendee(name="John Doe", company="Acme Capital")
                ],
                notes=None
            )
            past_events.append(past_event)

        # Mock profile
        mock_profile = MagicMock()
        mock_profile.company_aliases = {}

        # Mock provider
        mock_provider = MagicMock()
        mock_provider.fetch_events.return_value = past_events

        with patch('app.memory.service.get_profile', return_value=mock_profile):
            with patch('app.memory.service.select_calendar_provider', return_value=mock_provider):
                with patch.dict(os.environ, {"MEMORY_MAX_ITEMS": "3"}):
                    result = fetch_recent_meetings([today_event])

                    assert "Acme Capital" in result
                    assert len(result["Acme Capital"]) == 3  # Limited to max_items

    def test_fetch_recent_meetings_provider_error(self):
        """Test that provider errors return empty result."""
        today_event = Event(
            subject="RPCK × Acme Capital — Portfolio Strategy Check-in",
            start_time="2024-12-15T14:30:00-05:00",
            end_time="2024-12-15T15:30:00-05:00",
            location="Zoom",
            attendees=[
                Attendee(name="John Doe", company="Acme Capital")
            ],
            notes=None
        )

        # Mock profile
        mock_profile = MagicMock()
        mock_profile.company_aliases = {}

        # Mock provider that raises exception
        mock_provider = MagicMock()
        mock_provider.fetch_events.side_effect = Exception("Provider Error")

        with patch('app.memory.service.get_profile', return_value=mock_profile):
            with patch('app.memory.service.select_calendar_provider', return_value=mock_provider):
                result = fetch_recent_meetings([today_event])
                assert result == {}


class TestAttachMemoryToMeetings:
    """Test attaching memory to meetings."""

    def test_attach_memory_to_empty_meetings(self):
        """Test attaching memory to empty meetings list."""
        result = attach_memory_to_meetings([])
        assert result == []

    def test_attach_memory_to_meetings_with_memory(self):
        """Test attaching memory to meetings."""
        meetings = [
            {
                "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
                "attendees": [
                    {"name": "John Doe", "company": "Acme Capital"}
                ]
            }
        ]

        # Mock the fetch_recent_meetings function
        mock_memories = {
            "Acme Capital": [
                {
                    "date": "Dec 14, 2024",
                    "subject": "Previous Meeting",
                    "key_attendees": ["John Doe"]
                }
            ]
        }

        with patch('app.memory.service.fetch_recent_meetings', return_value=mock_memories):
            with patch('app.memory.service.get_profile') as mock_profile:
                mock_profile.return_value.company_aliases = {}
                result = attach_memory_to_meetings(meetings)

                assert len(result) == 1
                assert "memory" in result[0]
                assert "previous_meetings" in result[0]["memory"]
                assert len(result[0]["memory"]["previous_meetings"]) == 1
                assert result[0]["memory"]["previous_meetings"][0]["subject"] == "Previous Meeting"

    def test_attach_memory_to_meetings_no_memory(self):
        """Test attaching memory when no past meetings found."""
        meetings = [
            {
                "subject": "RPCK × New Company — First Meeting",
                "attendees": [
                    {"name": "John Doe", "company": "New Company"}
                ]
            }
        ]

        with patch('app.memory.service.fetch_recent_meetings', return_value={}):
            with patch('app.memory.service.get_profile') as mock_profile:
                mock_profile.return_value.company_aliases = {}
                result = attach_memory_to_meetings(meetings)

                assert len(result) == 1
                assert "memory" in result[0]
                assert "previous_meetings" in result[0]["memory"]
                assert result[0]["memory"]["previous_meetings"] == []
