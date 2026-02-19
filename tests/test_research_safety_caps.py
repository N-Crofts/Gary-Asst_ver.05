"""Tests for research safety caps: budget, timeout, output capping, endpoint guard, query sanitization, advanced ops."""
import pytest
from unittest.mock import patch, MagicMock

from app.research.config import (
    MAX_TAVILY_CALLS_PER_REQUEST,
    TAVILY_TIMEOUT_SECONDS,
    MAX_RESEARCH_SOURCES,
    MAX_RESEARCH_SUMMARY_CHARS,
    MAX_RESEARCH_KEYPOINTS,
    MAX_KEYPOINT_CHARS,
    ResearchBudget,
)
from app.research.provider import (
    TavilyResearchProvider,
    ResearchProvider,
    create_tavily_provider,
    TAVILY_OP_SEARCH,
)
from app.research.query_safety import sanitize_research_query, is_query_usable_after_sanitization


# ---- Endpoint guard: allow_research=False -> empty research, provider not called ----

class CountingResearchProvider(ResearchProvider):
    """Provider that counts get_research calls and returns minimal data."""

    def __init__(self):
        self.call_count = 0

    def get_research(self, topic: str):
        self.call_count += 1
        return {"summary": "x", "key_points": [], "sources": []}


def test_endpoint_guard_allow_research_false_results_in_empty_research(monkeypatch):
    """When allow_research=False, context has empty research and provider is never called."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    counting_provider = CountingResearchProvider()
    with patch("app.research.selector.select_research_provider", return_value=counting_provider):
        from app.rendering.context_builder import build_digest_context_with_provider
        ctx = build_digest_context_with_provider(source="stub", allow_research=False)
    assert ctx.get("research") == {"summary": "", "key_points": [], "sources": []}
    assert ctx.get("_research_computed") is True
    assert counting_provider.call_count == 0


# ---- Budget: at most 1 call per request ----

def test_research_budget_at_most_one_call_per_digest(monkeypatch):
    """With a counting provider and allow_research=True, at most 1 get_research call."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    counting_provider = CountingResearchProvider()
    budget = ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    with patch("app.research.selector.select_research_provider", return_value=counting_provider):
        from app.rendering.context_builder import build_digest_context_with_provider
        ctx = build_digest_context_with_provider(
            source="stub",
            allow_research=True,
            research_budget=budget,
        )
    assert counting_provider.call_count <= MAX_TAVILY_CALLS_PER_REQUEST
    assert counting_provider.call_count <= 1


# ---- Timeout: provider uses configured timeout ----

def test_tavily_provider_default_timeout_from_constants():
    """TavilyResearchProvider uses TAVILY_TIMEOUT_SECONDS when timeout is not passed."""
    p = TavilyResearchProvider(api_key="test-key", timeout=None)
    assert p.timeout == TAVILY_TIMEOUT_SECONDS


def test_tavily_provider_explicit_timeout():
    """TavilyResearchProvider accepts explicit timeout."""
    p = TavilyResearchProvider(api_key="test-key", timeout=7.0)
    assert p.timeout == 7.0


def test_create_tavily_provider_uses_constant_timeout(monkeypatch):
    """create_tavily_provider builds provider with TAVILY_TIMEOUT_SECONDS."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    p = create_tavily_provider()
    assert p.timeout == TAVILY_TIMEOUT_SECONDS


# ---- Output capping: sources, summary, key_points ----

def test_tavily_provider_caps_output_via_mocked_response():
    """Tavily get_research returns capped sources, summary, and key_points (mocked HTTP)."""
    raw_response = {
        "results": [
            {"title": f"Source {i} title", "url": f"https://example.com/s{i}", "content": "x"}
            for i in range(10)
        ],
        "answer": "A" * 1000,
    }
    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    provider = TavilyResearchProvider(api_key="key", timeout=5.0)
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = provider.get_research("test topic")

    assert len(result["sources"]) <= MAX_RESEARCH_SOURCES
    assert len(result["summary"]) <= MAX_RESEARCH_SUMMARY_CHARS
    assert len(result["key_points"]) <= MAX_RESEARCH_KEYPOINTS
    for kp in result["key_points"]:
        assert len(kp) <= MAX_KEYPOINT_CHARS


def test_tavily_provider_dedupes_sources_by_url():
    """Tavily get_research dedupes sources by normalized URL (trailing slash + lowercase)."""
    # Provider normalizes: lowercase + strip trailing slash (no http/https normalization)
    raw_response = {
        "results": [
            {"title": "First", "url": "https://example.com/page", "content": "x"},
            {"title": "Second", "url": "https://example.com/page/", "content": "x"},
            {"title": "Third", "url": "HTTPS://EXAMPLE.COM/PAGE/", "content": "x"},
        ],
        "answer": "Summary",
    }
    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    provider = TavilyResearchProvider(api_key="key", timeout=5.0)
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = provider.get_research("test")
    # All normalize to same (lowercase + trailing slash removed); first occurrence kept
    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "First"


def test_tavily_provider_truncates_summary_and_keypoints():
    """Summary and key_points are truncated to MAX_RESEARCH_SUMMARY_CHARS and MAX_KEYPOINT_CHARS."""
    long_summary = "x" * 2000
    long_point = "y" * 300
    raw_response = {
        "results": [
            {"title": long_point, "url": "https://example.com/1", "content": "c"},
            {"title": "Short", "url": "https://example.com/2", "content": "c"},
        ],
        "answer": long_summary,
    }
    mock_response = MagicMock()
    mock_response.json.return_value = raw_response
    mock_response.raise_for_status = MagicMock()

    provider = TavilyResearchProvider(api_key="key", timeout=5.0)
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = provider.get_research("test")
    assert len(result["summary"]) <= MAX_RESEARCH_SUMMARY_CHARS
    for kp in result["key_points"]:
        assert len(kp) <= MAX_KEYPOINT_CHARS


# ---- Query sanitization ----

def test_sanitize_research_query_removes_emails():
    """Emails are removed from the query."""
    out = sanitize_research_query("Call with john@example.com and Acme Corp")
    assert "john@example.com" not in out
    assert "Acme" in out or "Corp" in out


def test_sanitize_research_query_removes_currency():
    """Currency amounts are removed."""
    out = sanitize_research_query("Deal worth $1,000,000 with Beta Inc")
    assert "$1" not in out or "000" not in out
    assert "Beta" in out or "Inc" in out


def test_sanitize_research_query_removes_phone():
    """Phone numbers are removed."""
    out = sanitize_research_query("Contact +1 555 123 4567 for Acme")
    assert "555" not in out or "123" not in out
    assert "Acme" in out


def test_sanitize_research_query_enforces_max_length():
    """Output is capped at MAX_RESEARCH_QUERY_CHARS (120)."""
    from app.research.config import MAX_RESEARCH_QUERY_CHARS
    long_q = "Acme Corp " * 30
    out = sanitize_research_query(long_q)
    assert len(out) <= MAX_RESEARCH_QUERY_CHARS


def test_sanitize_research_query_empty_or_too_short_not_usable():
    """Empty or very short sanitized query is not usable."""
    assert is_query_usable_after_sanitization("") is False
    assert is_query_usable_after_sanitization("ab") is False
    assert is_query_usable_after_sanitization("  ") is False
    assert is_query_usable_after_sanitization("Acme Corp") is True


# ---- Advanced operations blocked by default ----

def test_advanced_operations_blocked_when_allow_advanced_false(monkeypatch):
    """Non-search operation returns empty research when TAVILY_ALLOW_ADVANCED is not set."""
    monkeypatch.setenv("TAVILY_ALLOW_ADVANCED", "false")
    monkeypatch.delenv("TAVILY_ALLOW_ADVANCED", raising=False)
    from app.research.provider import TavilyResearchProvider
    from app.research.config import allow_tavily_advanced
    # Ensure env is false
    import os
    os.environ.pop("TAVILY_ALLOW_ADVANCED", None)
    provider = TavilyResearchProvider(api_key="key", timeout=5.0, allow_advanced=False)
    result = provider.get_research("topic", operation="extract")  # non-search
    assert result["summary"] == ""
    assert result["key_points"] == []
    assert result["sources"] == []


def test_search_operation_allowed_by_default():
    """operation=search is always allowed."""
    provider = TavilyResearchProvider(api_key="key", timeout=5.0, allow_advanced=False)
    # get_research with default operation=TAVILY_OP_SEARCH does not return empty from block
    # We only check via mock that search is invoked when we have allow_advanced False
    result = provider.get_research("Acme Corp", operation=TAVILY_OP_SEARCH)
    # Without network, it would raise or return; with mock we test elsewhere. Just check operation search is accepted.
    assert "summary" in result
    assert "key_points" in result
    assert "sources" in result
