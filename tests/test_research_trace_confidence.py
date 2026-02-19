"""Tests for research observability: ResearchTrace, confidence gating, fallback, test-meeting skip.

No Microsoft Graph or Tavily calls in tests; use stubs and patched providers only.
"""
import pytest
from unittest.mock import patch

from app.research.config import ResearchBudget, MAX_TAVILY_CALLS_PER_REQUEST, get_confidence_min
from app.research.trace import SkipReason
from app.research.confidence import (
    is_domain_ambiguous_short,
    is_domain_generic,
    is_meeting_like_test,
)
from app.research.provider import ResearchProvider


# Stub meeting: ambiguous short domain (smg.com) + person name -> fallback A should use person query
STUB_RAW_AMBIGUOUS_DOMAIN_PERSON = [
    {
        "id": "stub-ambiguous",
        "subject": "Meeting",
        "start": {"dateTime": "2025-02-18T10:00:00", "timeZone": "America/New_York"},
        "end": {"dateTime": "2025-02-18T11:00:00", "timeZone": "America/New_York"},
        "location": {"displayName": "Zoom"},
        "attendees": [
            {
                "emailAddress": {
                    "name": "Justin Jacot",
                    "address": "justin.jacot@smg.com",
                }
            }
        ],
        "organizer": {
            "emailAddress": {
                "name": "External",
                "address": "jane@smg.com",
            }
        },
        "isCancelled": False,
        "bodyPreview": "",
    }
]

# Person-only, generic domain, no org_context -> low confidence skip
STUB_RAW_PERSON_GENERIC_NO_ORG = [
    {
        "id": "stub-person-gmail",
        "subject": "Call with Bob",
        "start": {"dateTime": "2025-02-18T10:00:00", "timeZone": "America/New_York"},
        "end": {"dateTime": "2025-02-18T11:00:00", "timeZone": "America/New_York"},
        "location": {"displayName": "Zoom"},
        "attendees": [
            {
                "emailAddress": {
                    "name": "Bob",
                    "address": "bob@gmail.com",
                }
            }
        ],
        "organizer": {
            "emailAddress": {"name": "Sorum Crofts", "address": "sorum.crofts@rpck.com"}
        },
        "isCancelled": False,
        "bodyPreview": "",
    }
]

# Test meeting: subject contains "test"
STUB_RAW_TEST_MEETING = [
    {
        "id": "stub-test",
        "subject": "test sync with team",
        "start": {"dateTime": "2025-02-18T10:00:00", "timeZone": "America/New_York"},
        "end": {"dateTime": "2025-02-18T11:00:00", "timeZone": "America/New_York"},
        "location": {"displayName": "Zoom"},
        "attendees": [
            {
                "emailAddress": {
                    "name": "Jane Doe",
                    "address": "jane@external.com",
                }
            }
        ],
        "organizer": {
            "emailAddress": {"name": "Sorum Crofts", "address": "sorum.crofts@rpck.com"}
        },
        "isCancelled": False,
        "bodyPreview": "",
    }
]

# Test meeting override: subject contains "Test" but otherwise high-confidence (external non-generic domain, display name)
STUB_RAW_TEST_MEETING_HIGH_SIGNALS = [
    {
        "id": "stub-test-override",
        "subject": "Test call with Acme Capital",
        "start": {"dateTime": "2025-02-18T10:00:00", "timeZone": "America/New_York"},
        "end": {"dateTime": "2025-02-18T11:00:00", "timeZone": "America/New_York"},
        "location": {"displayName": "Zoom"},
        "attendees": [
            {
                "emailAddress": {
                    "name": "Jane Doe",
                    "address": "jane.doe@acmecapital.com",
                }
            }
        ],
        "organizer": {
            "emailAddress": {
                "name": "External Partner",
                "address": "partner@acmecapital.com",
            }
        },
        "isCancelled": False,
        "bodyPreview": "",
    }
]

# Person anchor, no org_context, non-generic domain -> primary fails, fallback B (domain query) passes
STUB_RAW_PERSON_NO_ORG_FALLBACK_B = [
    {
        "id": "stub-fallback-b",
        "subject": "Call with Alice",
        "start": {"dateTime": "2025-02-18T10:00:00", "timeZone": "America/New_York"},
        "end": {"dateTime": "2025-02-18T11:00:00", "timeZone": "America/New_York"},
        "location": {"displayName": "Zoom"},
        "attendees": [],
        "organizer": {
            "emailAddress": {
                "name": "External",
                "address": "jane@acmecapital.com",
            }
        },
        "isCancelled": False,
        "bodyPreview": "",
    }
]


class RecordingProvider(ResearchProvider):
    """Records last topic passed to get_research (for assertion only; not logged)."""

    def __init__(self):
        self.call_count = 0
        self.last_topic = ""

    def get_research(self, topic: str):
        self.call_count += 1
        self.last_topic = topic
        return {"summary": "x", "key_points": [], "sources": []}


def test_ambiguous_short_domain_with_person_uses_fallback_person_query(monkeypatch):
    """Ambiguous short domain (smg.com) + person name: fallback A builds person query with domain; Tavily called with it."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "0.70")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.rendering.context_builder.STUB_MEETINGS_RAW_GRAPH", STUB_RAW_AMBIGUOUS_DOMAIN_PERSON):
        with patch("app.research.selector.select_research_provider", return_value=provider):
            from app.rendering.context_builder import build_digest_context_with_provider
            ctx = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
                research_budget=budget,
            )
    trace = ctx.get("research_trace", {})
    # Either success or skipped; if success, we should have used a query containing domain (fallback A) or primary
    if provider.call_count == 1:
        # Query should be person+domain style (fallback A): e.g. "Justin Jacot smg.com (company, role, recent news)"
        assert "smg" in provider.last_topic or "company" in provider.last_topic or "role" in provider.last_topic
    assert trace.get("outcome") in ("success", "skipped")
    assert trace.get("attempted") is True


def test_person_only_no_org_context_skipped_low_confidence(monkeypatch):
    """Person anchor with generic domain and no org context is skipped with low_confidence_anchor."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "0.70")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.rendering.context_builder.STUB_MEETINGS_RAW_GRAPH", STUB_RAW_PERSON_GENERIC_NO_ORG):
        with patch("app.research.selector.select_research_provider", return_value=provider):
            from app.rendering.context_builder import build_digest_context_with_provider
            ctx = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
                research_budget=budget,
            )
    assert ctx["research"]["summary"] == ""
    trace = ctx.get("research_trace", {})
    assert trace.get("outcome") == "skipped"
    assert trace.get("skip_reason") == SkipReason.LOW_CONFIDENCE_ANCHOR.value
    assert provider.call_count == 0


def test_meeting_marked_test_skipped(monkeypatch):
    """Meeting with subject containing 'test' is skipped with meeting_marked_test."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.rendering.context_builder.STUB_MEETINGS_RAW_GRAPH", STUB_RAW_TEST_MEETING):
        with patch("app.research.selector.select_research_provider", return_value=provider):
            from app.rendering.context_builder import build_digest_context_with_provider
            ctx = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
                research_budget=budget,
            )
    assert ctx["research"]["summary"] == ""
    trace = ctx.get("research_trace", {})
    assert trace.get("outcome") == "skipped"
    assert trace.get("skip_reason") == SkipReason.MEETING_MARKED_TEST.value
    assert provider.call_count == 0


def test_budget_still_enforced_one_call_max(monkeypatch):
    """MAX_TAVILY_CALLS_PER_REQUEST is still 1; at most one provider call."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.research.selector.select_research_provider", return_value=provider):
        from app.rendering.context_builder import build_digest_context_with_provider
        ctx = build_digest_context_with_provider(
            source="stub",
            allow_research=True,
            research_budget=budget,
        )
    assert provider.call_count <= 1


# ---- Confidence helpers ----

def test_domain_root_ambiguous_short():
    assert is_domain_ambiguous_short("smg.com") is True
    assert is_domain_ambiguous_short("ac.co") is True
    assert is_domain_ambiguous_short("acmecapital.com") is False


def test_domain_generic():
    assert is_domain_generic("gmail.com") is True
    assert is_domain_generic("outlook.com") is True
    assert is_domain_generic("acmecapital.com") is False


def test_is_meeting_like_test_subject():
    assert is_meeting_like_test({"subject": "test call", "attendees": []}, None) is True
    assert is_meeting_like_test({"subject": "dummy meeting", "attendees": [{}]}, None) is True
    assert is_meeting_like_test({"subject": "Call with Acme", "attendees": [{"email": "jane@acme.com"}]}, None) is False


def test_is_meeting_like_test_only_self_attendee():
    meeting = {"subject": "Sync", "attendees": [{"email": "me@rpck.com"}]}
    assert is_meeting_like_test(meeting, "me@rpck.com") is True
    assert is_meeting_like_test(meeting, "other@rpck.com") is False


def test_confidence_min_from_env(monkeypatch):
    assert get_confidence_min() == 0.70
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "0.85")
    assert get_confidence_min() == 0.85
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "2.0")
    assert get_confidence_min() == 1.0


# ---- A. Test meeting override ----

def test_test_meeting_override_skipped_provider_not_called(monkeypatch):
    """Meeting with subject containing 'Test' and high-confidence signals is skipped with meeting_marked_test; no provider call."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "0.70")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.rendering.context_builder.STUB_MEETINGS_RAW_GRAPH", STUB_RAW_TEST_MEETING_HIGH_SIGNALS):
        with patch("app.research.selector.select_research_provider", return_value=provider):
            from app.rendering.context_builder import build_digest_context_with_provider
            ctx = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
                research_budget=budget,
            )
    assert ctx["research"]["summary"] == ""
    trace = ctx.get("research_trace", {})
    assert trace.get("outcome") == "skipped"
    assert trace.get("skip_reason") == SkipReason.MEETING_MARKED_TEST.value
    assert trace.get("sources_count", 0) == 0
    assert trace.get("query_hash") in (None, "")
    assert trace.get("query_len") in (None, 0)
    assert provider.call_count == 0


# ---- B. Disabled research should not log attempt ----

def test_disabled_research_no_provider_call_no_research_result_log(monkeypatch, caplog):
    """When RESEARCH_ENABLED=false, no Tavily provider call and no RESEARCH_RESULT log (trace has attempted=false, skip_reason=disabled)."""
    import logging
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("RESEARCH_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "production")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.research.selector.select_research_provider", return_value=provider):
        from app.rendering.context_builder import build_digest_context_with_provider
        ctx = build_digest_context_with_provider(
            source="stub",
            allow_research=True,
            research_budget=budget,
        )
    assert provider.call_count == 0
    trace = ctx.get("research_trace", {})
    assert trace.get("attempted") is False
    assert trace.get("skip_reason") == SkipReason.DISABLED.value
    assert not any(getattr(r, "message", r.msg or "") == "RESEARCH_RESULT" for r in caplog.records)


# ---- C. Query hash presence ----

def test_successful_research_has_query_hash_and_len(monkeypatch):
    """Successful research run (stub returns sources): query_hash is 10 chars, query_len > 0."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    provider = RecordingProvider()
    provider.get_research = lambda topic: {"summary": "x", "key_points": ["a"], "sources": [{"title": "T", "url": "https://example.com/1"}]}
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.research.selector.select_research_provider", return_value=provider):
        from app.rendering.context_builder import build_digest_context_with_provider
        ctx = build_digest_context_with_provider(
            source="stub",
            allow_research=True,
            research_budget=budget,
        )
    trace = ctx.get("research_trace", {})
    assert trace.get("outcome") == "success"
    assert len(trace.get("query_hash", "")) == 10
    assert (trace.get("query_len") or 0) > 0


def test_skipped_research_has_no_query_hash_or_zero_len(monkeypatch):
    """Skipped run (no_anchor): query_hash absent or empty, query_len absent or 0."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    # Stub with no external anchor: e.g. only rpck attendees
    stub_no_anchor = [
        {
            "id": "stub-no-anchor",
            "subject": "Internal sync",
            "start": {"dateTime": "2025-02-18T10:00:00", "timeZone": "America/New_York"},
            "end": {"dateTime": "2025-02-18T11:00:00", "timeZone": "America/New_York"},
            "location": {"displayName": "Zoom"},
            "attendees": [{"emailAddress": {"name": "Colleague", "address": "colleague@rpck.com"}}],
            "organizer": {"emailAddress": {"name": "Sorum Crofts", "address": "sorum.crofts@rpck.com"}},
            "isCancelled": False,
            "bodyPreview": "",
        }
    ]
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.rendering.context_builder.STUB_MEETINGS_RAW_GRAPH", stub_no_anchor):
        with patch("app.research.selector.select_research_provider", return_value=provider):
            from app.rendering.context_builder import build_digest_context_with_provider
            ctx = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
                research_budget=budget,
            )
    trace = ctx.get("research_trace", {})
    assert trace.get("outcome") == "skipped"
    assert trace.get("query_hash") in (None, "")
    assert trace.get("query_len") in (None, 0)
    assert provider.call_count == 0


# ---- D. One-call budget hard guarantee ----

def test_primary_fails_fallback_passes_exactly_one_call(monkeypatch):
    """When primary confidence fails and fallback B passes, provider is called exactly once."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "0.70")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.rendering.context_builder.STUB_MEETINGS_RAW_GRAPH", STUB_RAW_PERSON_NO_ORG_FALLBACK_B):
        with patch("app.research.selector.select_research_provider", return_value=provider):
            from app.rendering.context_builder import build_digest_context_with_provider
            ctx = build_digest_context_with_provider(
                source="stub",
                allow_research=True,
                research_budget=budget,
            )
    assert provider.call_count == 1
    trace = ctx.get("research_trace", {})
    assert trace.get("outcome") in ("success", "error")
    assert trace.get("query_len", 0) > 0


def test_both_primary_and_fallback_eligible_still_one_call(monkeypatch):
    """When both primary and fallback would pass, first (primary) wins; provider called exactly once."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RESEARCH_CONFIDENCE_MIN", "0.70")
    provider = RecordingProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.research.selector.select_research_provider", return_value=provider):
        from app.rendering.context_builder import build_digest_context_with_provider
        ctx = build_digest_context_with_provider(
            source="stub",
            allow_research=True,
            research_budget=budget,
        )
    assert provider.call_count == 1
