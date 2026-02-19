"""Tests for research sources deduplication and capping."""
import pytest

from app.rendering.context_builder import _normalize_url_for_dedup, _dedupe_and_cap_sources


def test_normalize_url_for_dedup_trims_and_lowercases():
    """URL normalization: trim, lowercase, normalize https->http for comparison, remove trailing slash."""
    assert _normalize_url_for_dedup("https://Example.com/Path/") == "http://example.com/path"
    assert _normalize_url_for_dedup("HTTP://TEST.COM") == "http://test.com"
    assert _normalize_url_for_dedup("  https://site.com  ") == "http://site.com"


def test_normalize_url_for_dedup_removes_trailing_slash():
    """Trailing slash is removed; https normalized to http for comparison."""
    assert _normalize_url_for_dedup("https://example.com/") == "http://example.com"
    assert _normalize_url_for_dedup("https://example.com/path/") == "http://example.com/path"


def test_normalize_url_for_dedup_empty():
    """Empty URLs return empty string."""
    assert _normalize_url_for_dedup("") == ""
    assert _normalize_url_for_dedup("   ") == ""


def test_dedupe_and_cap_sources_removes_duplicates():
    """Duplicate URLs (normalized) are removed."""
    sources = [
        {"title": "Article 1", "url": "https://example.com/article"},
        {"title": "Article 2", "url": "https://example.com/article/"},
        {"title": "Article 3", "url": "HTTP://EXAMPLE.COM/article"},
    ]
    result = _dedupe_and_cap_sources(sources)
    assert len(result) == 1
    assert result[0]["title"] == "Article 1"  # First occurrence preserved


def test_dedupe_and_cap_sources_preserves_order():
    """Order is preserved; first occurrence of each URL is kept."""
    sources = [
        {"title": "First", "url": "https://site1.com"},
        {"title": "Second", "url": "https://site2.com"},
        {"title": "Duplicate", "url": "https://site1.com/"},
    ]
    result = _dedupe_and_cap_sources(sources)
    assert len(result) == 2
    assert result[0]["title"] == "First"
    assert result[1]["title"] == "Second"


def test_dedupe_and_cap_sources_caps_to_max_items():
    """Sources are capped to max_items (default 5)."""
    sources = [
        {"title": f"Article {i}", "url": f"https://example.com/article{i}"}
        for i in range(10)
    ]
    result = _dedupe_and_cap_sources(sources, max_items=5)
    assert len(result) == 5
    assert result[0]["title"] == "Article 0"
    assert result[4]["title"] == "Article 4"


def test_dedupe_and_cap_sources_skips_invalid():
    """Sources without url or title are skipped."""
    sources = [
        {"title": "Valid", "url": "https://example.com"},
        {"title": "", "url": "https://example.com"},
        {"title": "Valid2", "url": ""},
        {"title": "Valid3", "url": "https://example.com/other"},
    ]
    result = _dedupe_and_cap_sources(sources)
    assert len(result) == 2
    assert result[0]["title"] == "Valid"
    assert result[1]["title"] == "Valid3"


def test_dedupe_and_cap_sources_empty_list():
    """Empty list returns empty list."""
    assert _dedupe_and_cap_sources([]) == []
    assert _dedupe_and_cap_sources(None) == []
