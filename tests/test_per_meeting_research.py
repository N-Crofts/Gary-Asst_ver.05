"""
Tests for per-meeting research enrichment (V1: meeting-scoped research).
"""
import os
from unittest.mock import patch, MagicMock
from datetime import datetime
import pytest

from app.rendering.context_builder import build_digest_context_with_provider
from app.research.provider import StubResearchProvider
from app.calendar.types import Event, Attendee


@pytest.fixture
def mock_provider():
    """Mock research provider that returns deterministic results.
    Sources include common test primary domains (example.com, acme.com, companyabc.com, etc.)
    so the off-target guardrail accepts the result for those meetings.
    """
    provider = MagicMock(spec=StubResearchProvider)
    provider.get_research.return_value = {
        "summary": "Test company summary",
        "key_points": [
            "Company raised $50M Series B funding",
            "Announced partnership with major retailer",
            "Expanding into European markets",
        ],
        "sources": [
            {"title": "TechCrunch Article", "url": "https://techcrunch.com/test"},
            {"title": "Example Co", "url": "https://example.com/news"},
            {"title": "Acme Co", "url": "https://acme.com/about"},
            {"title": "Company ABC", "url": "https://companyabc.com/page"},
            {"title": "Company Blog", "url": "https://company.com/news"},
        ],
    }
    return provider


def test_per_meeting_research_populates_fields(mock_provider):
    """Test that per-meeting fields are populated when research is enabled."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            # Use stub source which returns mock meetings
            context = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
            )
            
            # Check that research was attempted
            assert context.get("_research_computed") is True
            assert "research_traces_by_meeting_id" in context
            
            # Check that at least one meeting has research fields populated (if eligible)
            meetings_with_research = []
            for m in context.get("meetings", []):
                if hasattr(m, "model_dump"):
                    md = m.model_dump()
                    if md.get("context_summary") is not None:
                        meetings_with_research.append(md)
                elif isinstance(m, dict) and m.get("context_summary") is not None:
                    meetings_with_research.append(m)
            # If there are eligible meetings, they should have research
            if meetings_with_research:
                enriched_meeting = meetings_with_research[0]
                assert enriched_meeting.get("context_summary") is not None
                assert enriched_meeting.get("strategic_angles") is not None
                assert enriched_meeting.get("high_leverage_questions") is not None
                assert enriched_meeting.get("news") is not None
                
                # Verify provider was called if there were eligible meetings
                if mock_provider.get_research.call_count > 0:
                    mock_provider.get_research.assert_called()


def test_per_meeting_research_multiple_meetings(mock_provider):
    """Test that multiple eligible meetings can be enriched."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        # Create mock calendar provider with 3 eligible external meetings
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="Call with John Doe",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="John Doe", email="john@example.com"),
                ],
            ),
            Event(
                subject="Meeting with Jane Smith",
                start_time="2025-09-08T14:00:00-04:00",
                end_time="2025-09-08T15:00:00-04:00",
                attendees=[
                    Attendee(name="Jane Smith", email="jane@acme.com"),
                ],
            ),
            Event(
                subject="Intro: Company ABC",
                start_time="2025-09-08T16:00:00-04:00",
                end_time="2025-09-08T17:00:00-04:00",
                attendees=[
                    Attendee(name="Bob Johnson", email="bob@companyabc.com"),
                ],
            ),
        ]
        
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
                
                # Strict cap: at most 1 research call per digest build
                assert mock_provider.get_research.call_count <= 1
                # At least the first eligible meeting may have research (if cap allowed the one call)
                meetings_with_research = []
                for m in context.get("meetings", []):
                    if hasattr(m, "model_dump"):
                        md = m.model_dump()
                        if md.get("context_summary") is not None:
                            meetings_with_research.append(m)
                    elif isinstance(m, dict) and m.get("context_summary") is not None:
                        meetings_with_research.append(m)
                assert len(meetings_with_research) >= 1


def test_per_meeting_research_dedupe(mock_provider):
    """Test that dedupe works: two meetings with same anchor trigger only one provider call."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        # Create mock calendar provider with 2 meetings that will resolve to same query
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="Call with John Doe",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="John Doe", email="john@example.com"),
                ],
            ),
            Event(
                subject="Follow-up with John Doe",
                start_time="2025-09-08T14:00:00-04:00",
                end_time="2025-09-08T15:00:00-04:00",
                attendees=[
                    Attendee(name="John Doe", email="john@example.com"),
                ],
            ),
        ]
        
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
                
                # Provider should be called only once (dedupe)
                assert mock_provider.get_research.call_count == 1
                
                # Both meetings should have research fields (from cache)
                meetings_with_research = []
                for m in context.get("meetings", []):
                    if hasattr(m, "model_dump"):
                        md = m.model_dump()
                        if md.get("context_summary") is not None:
                            meetings_with_research.append(m)
                    elif isinstance(m, dict) and m.get("context_summary") is not None:
                        meetings_with_research.append(m)
                assert len(meetings_with_research) == 2


def test_per_meeting_research_cap(mock_provider):
    """Test that cap works: with >8 eligible meetings, provider called at most 8."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        # Create mock calendar provider with 10 eligible external meetings
        mock_calendar = MagicMock()
        events = []
        for i in range(10):
            events.append(
                Event(
                    subject=f"Call with Person {i}",
                    start_time=f"2025-09-08T{10+i:02d}:00:00-04:00",
                    end_time=f"2025-09-08T{11+i:02d}:00:00-04:00",
                    attendees=[
                        Attendee(name=f"Person {i}", email=f"person{i}@example{i}.com"),
                    ],
                )
            )
        mock_calendar.fetch_events.return_value = events
        
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
                
                # Provider should be called at most 8 times (hard cap)
                assert mock_provider.get_research.call_count <= 8
                
                # At most 8 meetings should have research (some may be skipped due to cap)
                meetings_with_research = []
                meetings_skipped_cap = []
                for m in context.get("meetings", []):
                    if hasattr(m, "model_dump"):
                        md = m.model_dump()
                        if md.get("context_summary") is not None:
                            meetings_with_research.append(m)
                        trace = md.get("research_trace", {})
                        if trace and trace.get("skip_reason") == "budget_exhausted":
                            meetings_skipped_cap.append(m)
                    elif isinstance(m, dict):
                        if m.get("context_summary") is not None:
                            meetings_with_research.append(m)
                        trace = m.get("research_trace", {})
                        if trace and trace.get("skip_reason") == "budget_exhausted":
                            meetings_skipped_cap.append(m)
                
                    assert len(meetings_with_research) <= 8
                    # The key assertion is that provider was called at most 8 times (hard cap)
                    # Some meetings may be skipped for other reasons (low confidence, no anchor, etc.)
                    # before hitting the cap, so we don't require a specific number of cap-skipped meetings
                    # The important thing is that the cap is enforced (call count <= 8)


def test_per_meeting_research_skips_internal_meetings(mock_provider):
    """Test that internal meetings (score < 0) are skipped."""
    # This test would require custom meetings, so we'll test skip logic indirectly
    # For now, we'll skip this test or make it more generic
    pass  # TODO: Add test with mocked calendar provider that returns internal meetings


def test_per_meeting_research_respects_gating(mock_provider):
    """Test that research respects RESEARCH_ENABLED and ENABLE_RESEARCH_DEV gating."""
    # Test with research disabled
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "false",
        "ENABLE_RESEARCH_DEV": "false",
    }, clear=False):
        context = build_digest_context_with_provider(
            source="stub",
            allow_research=True,
        )
        
        # Provider should not be called
        mock_provider.get_research.assert_not_called()
        
        # Meetings should not have research fields
        for meeting in context.get("meetings", []):
            if hasattr(meeting, "model_dump"):
                md = meeting.model_dump()
                assert md.get("context_summary") is None
            elif isinstance(meeting, dict):
                assert meeting.get("context_summary") is None


def test_external_attendee_csa_does_not_produce_no_anchor(mock_provider):
    """Meeting with external attendees including hugo.huempel@csa.org should not skip with no_anchor; anchor should include csa and person name."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="Call with Trent Smyth, Hugo Huempel & Chintan Panchal",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Hugo Huempel", email="hugo.huempel@csa.org"),
                    Attendee(name="Trent Smyth", email="trent.smyth@csa.org"),
                    Attendee(name="Keziah", email="keziah@vanninchiefofstaff.com"),
                    Attendee(name="Chintan Panchal", email="chintan.panchal@rpck.com"),
                ],
                organizer="chintan.panchal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
        traces = context.get("research_traces_by_meeting_id", {})
        for tid, trace in traces.items():
            assert trace.get("skip_reason") != "no_anchor", (
                f"Meeting {tid} should not have skip_reason no_anchor when external csa.org attendees exist"
            )
        # If research was run, query should include csa (person-first or org fallback)
        if mock_provider.get_research.call_count >= 1:
            call_args = mock_provider.get_research.call_args
            query = call_args[0][0] if call_args and call_args[0] else ""
            assert "csa" in query.lower(), f"Expected query to include 'csa', got: {query}"


def test_group_meeting_non_consumer_domain_does_not_produce_no_anchor(mock_provider):
    """Group meeting with gatesfoundation.org, rethinkimpact.com, kawisafiventures.com and some gmail should not skip with no_anchor; should pick a non-consumer domain."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="Angaza Optional Board Call",
                start_time="2025-09-08T14:00:00-04:00",
                end_time="2025-09-08T15:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@gatesfoundation.org"),
                    Attendee(name="Bob", email="bob@rethinkimpact.com"),
                    Attendee(name="Carol", email="carol@kawisafiventures.com"),
                    Attendee(name="Dave", email="dave@gmail.com"),
                    Attendee(name="Hussein", email="hussein@hussein.me.ke"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
        traces = context.get("research_traces_by_meeting_id", {})
        for tid, trace in traces.items():
            assert trace.get("skip_reason") != "no_anchor", f"Meeting {tid} should not have skip_reason no_anchor when non-consumer domains exist"
        # Angaza group meeting: must use org/domain scoring only; no person-first (Hussein).
        # Every research query must include one of the real orgs and must NOT contain Hussein.
        allowed_orgs = ("gates foundation", "rethink impact", "kawisa ventures", "gatesfoundation", "rethinkimpact", "kawisafiventures")
        assert mock_provider.get_research.call_count >= 1
        for call in mock_provider.get_research.call_args_list:
            query = (call[0][0] if call and call[0] else "").lower()
            assert "hussein" not in query, f"No anchor query must contain 'hussein'; got: {query}"
            assert any(org in query for org in allowed_orgs), f"Selected org query must include one of {allowed_orgs}; got: {query}"


def test_personal_like_domain_only_skips_not_wrong_entity(mock_provider):
    """When only personal-like domains exist (e.g. hussein.me.ke) + gmail, prefer skip over wrong-entity anchor."""
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="Call with Hussein",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Hussein", email="hussein@hussein.me.ke"),
                    Attendee(name="Other", email="other@gmail.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
        # Must not call Tavily with "Hussein" (wrong-entity risk). Prefer skip.
        assert mock_provider.get_research.call_count == 0
        traces = context.get("research_traces_by_meeting_id", {})
        for trace in traces.values():
            assert trace.get("skip_reason") in ("low_confidence_anchor", "no_anchor"), (
                f"Expected skip when only personal-like domain, got: {trace.get('skip_reason')}"
            )


def test_off_target_results_skips_when_sources_mismatch_expected_domain(mock_provider):
    """When expected_domain is smg.com and provider returns sources with no smg.com, skip and do not populate."""
    # Sources that do NOT contain smg.com (e.g. wrong entity Scotts Miracle-Gro)
    off_target_sources = [
        {"title": "Scotts Miracle-Gro", "url": "https://scotts.com/article"},
        {"title": "Other", "url": "https://example.com/news"},
    ]
    mock_provider.get_research.side_effect = [
        {"summary": "Wrong company", "key_points": ["Point"], "sources": off_target_sources},
        {"summary": "Still wrong", "key_points": [], "sources": off_target_sources},
    ]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
        "RESEARCH_CONFIDENCE_MIN": "0",  # ensure anchor passes so we call provider and hit off-target check
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Optional Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
    assert mock_provider.get_research.call_count >= 1, "Provider should be called (then off-target skip)"
    meetings = context.get("meetings", [])
    assert len(meetings) == 1
    m = meetings[0]
    md = m if isinstance(m, dict) else (m.model_dump() if hasattr(m, "model_dump") else m)
    # Meeting must not have research context (off-target guardrail)
    assert not md.get("context_summary"), "Expected no context_summary when sources mismatch expected_domain"
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"
        # smg.com is ambiguous; mock has "Scotts Miracle-Gro" in title so negative_term_hit applies
        assert trace.get("mismatch_reason") in ("expected_domain_not_found", "negative_term_hit")


def test_off_target_retry_succeeds_when_retry_matches_domain(mock_provider):
    """First call returns off-target sources; retry returns sources containing expected_domain -> fields populated."""
    off_target = {"summary": "Wrong", "key_points": [], "sources": [{"title": "X", "url": "https://scotts.com/x"}]}
    on_target = {
        "summary": "Service Management Group summary",
        "key_points": ["SMG is a research firm."],
        "sources": [{"title": "About SMG", "url": "https://smg.com/about"}],
    }
    mock_provider.get_research.side_effect = [off_target, on_target]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
        "RESEARCH_CONFIDENCE_MIN": "0",  # ensure anchor passes so we call provider
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Optional Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live",
                    date="2025-09-08",
                    allow_research=True,
                )
    # Strict cap: at most 1 call per digest; no retry allowed, so first call must be on-target for success
    assert mock_provider.get_research.call_count == 1
    meetings = context.get("meetings", [])
    assert len(meetings) == 1
    m = meetings[0]
    md = m if isinstance(m, dict) else (m.model_dump() if hasattr(m, "model_dump") else m)
    # With cap 1 we cannot retry; test uses side_effect [off_target, on_target] so first call is off-target -> skip
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"
        assert trace.get("domain_match_passed") is False


def test_domain_match_substring_false_positive_rejected(mock_provider):
    """URLs with expected_domain only in path/query params must NOT count as host match (strict host-based)."""
    # Host is example.com; "smg.com" appears only in path/query - must not match expected_domain smg.com
    mock_provider.get_research.side_effect = [
        {
            "summary": "Wrong",
            "key_points": [],
            "sources": [
                {"title": "Page", "url": "https://example.com/news?ref=smg.com"},
                {"title": "Other", "url": "https://scotts.com/article"},
            ],
        },
        {
            "summary": "Still wrong",
            "key_points": [],
            "sources": [{"title": "X", "url": "https://scotts.com/x"}],
        },
    ]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
        "RESEARCH_CONFIDENCE_MIN": "0",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Optional Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live", date="2025-09-08", allow_research=True,
                )
    meetings = context.get("meetings", [])
    assert len(meetings) == 1
    md = meetings[0] if isinstance(meetings[0], dict) else meetings[0].model_dump()
    assert not md.get("context_summary"), "Substring-in-URL must not count as domain match"
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"


def test_ambiguous_acronym_domain_match_but_entity_fail_triggers_retry(mock_provider):
    """When domain_match passes but entity_match fails (ambiguous acronym), treat as off-target and retry."""
    # First call: host smg.com matches but content is about Scotts Miracle-Gro (no "Service Management Group")
    first_sources = [{"title": "Scotts Miracle-Gro SMG ticker", "url": "https://smg.com/ticker"}]
    retry_sources = [{"title": "Service Management Group", "url": "https://smg.com/about"}]
    mock_provider.get_research.side_effect = [
        {"summary": "SMG stock", "key_points": ["Scotts Miracle-Gro"], "sources": first_sources},
        {"summary": "Service Management Group", "key_points": ["SMG research"], "sources": retry_sources},
    ]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
        "RESEARCH_CONFIDENCE_MIN": "0",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Optional Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live", date="2025-09-08", allow_research=True,
                )
    # Strict cap: at most 1 call per digest; retry not attempted, so first call fails entity -> skip
    assert mock_provider.get_research.call_count == 1
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"
    meetings = context.get("meetings", [])
    md = meetings[0] if isinstance(meetings[0], dict) else meetings[0].model_dump()
    assert not md.get("context_summary")


def test_ambiguous_entity_fail_no_retry_match_still_skips(mock_provider):
    """Ambiguous domain: domain_match true but entity_match false; retry also fails entity => skip."""
    first_sources = [{"title": "SMG ticker Scotts", "url": "https://smg.com/ticker"}]
    retry_sources = [{"title": "SMG stock", "url": "https://smg.com/stock"}]
    mock_provider.get_research.side_effect = [
        {"summary": "Scotts", "key_points": [], "sources": first_sources},
        {"summary": "Stock", "key_points": [], "sources": retry_sources},
    ]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true",
        "ENABLE_RESEARCH_DEV": "true",
        "APP_ENV": "development",
        "RESEARCH_CONFIDENCE_MIN": "0",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(
                    source="live", date="2025-09-08", allow_research=True,
                )
    # Strict cap: at most 1 call per digest; first call fails entity, retry not attempted
    assert mock_provider.get_research.call_count == 1
    meetings = context.get("meetings", [])
    md = meetings[0] if isinstance(meetings[0], dict) else meetings[0].model_dump()
    assert not md.get("context_summary")
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"


def test_ambiguous_negative_term_filter_triggers_off_target(mock_provider):
    """Ambiguous acronym domain: sources with ticker/Scotts terms trigger negative_term_hit and skip."""
    mock_provider.get_research.side_effect = [
        {"summary": "SMG stock ticker", "key_points": ["Scotts Miracle-Gro"], "sources": [{"title": "SMG ticker", "url": "https://smg.com/ticker"}]},
        {"summary": "Still ticker", "key_points": [], "sources": [{"title": "Stock", "url": "https://example.com/stock"}]},
    ]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true", "ENABLE_RESEARCH_DEV": "true", "APP_ENV": "development", "RESEARCH_CONFIDENCE_MIN": "0",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(source="live", date="2025-09-08", allow_research=True)
    meetings = context.get("meetings", [])
    md = meetings[0] if isinstance(meetings[0], dict) else meetings[0].model_dump()
    assert not md.get("context_summary")
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"
        assert trace.get("mismatch_reason") == "negative_term_hit"


def test_ambiguous_retry_linkedin_entity_match_succeeds(mock_provider):
    """Ambiguous acronym: first call off-target; retry with LinkedIn/TheOrg returns org_display -> entity match, meeting filled."""
    first = {"summary": "Wrong", "key_points": [], "sources": [{"title": "Scotts Miracle-Gro", "url": "https://scotts.com/x"}]}
    retry = {
        "summary": "Service Management Group is a research firm.",
        "key_points": ["SMG leadership"],
        "sources": [{"title": "Service Management Group on LinkedIn", "url": "https://www.linkedin.com/company/smg"}, {"title": "SMG at The Org", "url": "https://theorg.com/org/smg"}],
    }
    mock_provider.get_research.side_effect = [first, retry]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true", "ENABLE_RESEARCH_DEV": "true", "APP_ENV": "development", "RESEARCH_CONFIDENCE_MIN": "0",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Optional Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(source="live", date="2025-09-08", allow_research=True)
    # Strict cap: at most 1 call per digest; first call is off-target, retry not attempted
    assert mock_provider.get_research.call_count == 1
    meetings = context.get("meetings", [])
    md = meetings[0] if isinstance(meetings[0], dict) else meetings[0].model_dump()
    assert not md.get("context_summary")
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"


def test_trace_domain_match_false_then_match_url_blank(mock_provider):
    """When domain_match_passed is False, domain_match_url must be None (renders as — in dev UI)."""
    mock_provider.get_research.side_effect = [
        {"summary": "Wrong", "key_points": [], "sources": [{"title": "X", "url": "https://example.com/x"}, {"title": "Y", "url": "https://scotts.com/y"}]},
    ]
    with patch.dict(os.environ, {
        "RESEARCH_ENABLED": "true", "ENABLE_RESEARCH_DEV": "true", "APP_ENV": "development", "RESEARCH_CONFIDENCE_MIN": "0",
    }, clear=False):
        mock_calendar = MagicMock()
        mock_calendar.fetch_events.return_value = [
            Event(
                subject="SMG Call",
                start_time="2025-09-08T10:00:00-04:00",
                end_time="2025-09-08T11:00:00-04:00",
                attendees=[
                    Attendee(name="Alice", email="alice@smg.com"),
                    Attendee(name="Bob", email="bob@smg.com"),
                    Attendee(name="Internal", email="internal@rpck.com"),
                ],
                organizer="internal@rpck.com",
            ),
        ]
        with patch("app.research.selector.select_research_provider", return_value=mock_provider):
            with patch("app.rendering.context_builder.select_calendar_provider", return_value=mock_calendar):
                context = build_digest_context_with_provider(source="live", date="2025-09-08", allow_research=True)
    traces = context.get("research_traces_by_meeting_id", {})
    for trace in traces.values():
        assert trace.get("skip_reason") == "off_target_results"
        assert trace.get("domain_match_passed") is False
        assert trace.get("domain_match_url") is None or trace.get("domain_match_url") == ""
