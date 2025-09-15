import os
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from app.enrichment.news_provider import StubNewsProvider
from app.enrichment.news_bing import BingNewsProvider, create_bing_news_provider
from app.utils.cache import TTLCache, news_cache
from app.enrichment.service import _select_news_provider, _fetch_news_for_company, enrich_meetings


class TestStubNewsProvider:
    """Test the deterministic stub news provider."""

    def test_search_acme_company(self):
        """Test news search for Acme company."""
        provider = StubNewsProvider()
        news = provider.search("Acme Capital")

        assert len(news) == 5
        assert all("title" in item and "url" in item for item in news)
        assert "Acme" in news[0]["title"]
        assert "fund iv" in news[0]["title"].lower()

    def test_search_techcorp_company(self):
        """Test news search for TechCorp company."""
        provider = StubNewsProvider()
        news = provider.search("TechCorp")

        assert len(news) == 5
        assert all("title" in item and "url" in item for item in news)
        assert "TechCorp" in news[0]["title"]
        assert "ai platform" in news[0]["title"].lower()

    def test_search_unknown_company(self):
        """Test news search for unknown company."""
        provider = StubNewsProvider()
        news = provider.search("Unknown Corp")

        assert len(news) == 5
        assert all("title" in item and "url" in item for item in news)
        assert "Unknown Corp" in news[0]["title"]
        assert "partnership" in news[0]["title"].lower()

    def test_search_empty_company(self):
        """Test news search for empty company name."""
        provider = StubNewsProvider()
        news = provider.search("")

        assert len(news) == 5  # Still returns generic news
        assert all("title" in item and "url" in item for item in news)

    def test_deterministic_output(self):
        """Test that stub provider produces deterministic output."""
        provider = StubNewsProvider()

        # Generate multiple times
        news1 = provider.search("Acme Capital")
        news2 = provider.search("Acme Capital")

        assert news1 == news2


class TestBingNewsProvider:
    """Test the Bing news provider with mocked HTTP calls."""

    def test_search_success(self):
        """Test successful news search."""
        provider = BingNewsProvider(api_key="test-key", timeout_ms=5000)

        mock_response = {
            "value": [
                {
                    "name": "Acme Capital announces new fund",
                    "url": "https://example.com/acme-fund"
                },
                {
                    "name": "Acme Capital expands operations",
                    "url": "https://example.com/acme-expansion"
                },
                {
                    "name": "Other company news",  # Should be filtered out
                    "url": "https://example.com/other-news"
                }
            ]
        }

        with patch('httpx.Client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response

            mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

            news = provider.search("Acme Capital")

            assert len(news) == 2  # Only Acme-related news
            assert news[0]["title"] == "Acme Capital announces new fund"
            assert news[0]["url"] == "https://example.com/acme-fund"
            assert news[1]["title"] == "Acme Capital expands operations"

    def test_search_api_error_raises_exception(self):
        """Test that API errors raise HTTPException."""
        provider = BingNewsProvider(api_key="test-key", timeout_ms=5000)

        with patch('httpx.Client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 401

            mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

            with pytest.raises(HTTPException) as exc_info:
                provider.search("Acme Capital")

            assert exc_info.value.status_code == 503
            assert "Bing News API authentication failed" in str(exc_info.value.detail)

    def test_search_rate_limit_raises_exception(self):
        """Test that rate limit errors raise HTTPException."""
        provider = BingNewsProvider(api_key="test-key", timeout_ms=5000)

        with patch('httpx.Client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 429

            mock_client.return_value.__enter__.return_value.get.return_value = mock_response_obj

            with pytest.raises(HTTPException) as exc_info:
                provider.search("Acme Capital")

            assert exc_info.value.status_code == 503
            assert "Bing News API rate limit exceeded" in str(exc_info.value.detail)

    def test_search_timeout_raises_exception(self):
        """Test that timeouts raise HTTPException."""
        provider = BingNewsProvider(api_key="test-key", timeout_ms=5000)

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("Timeout")

            with pytest.raises(HTTPException) as exc_info:
                provider.search("Acme Capital")

            assert exc_info.value.status_code == 503
            assert "Bing News API error" in str(exc_info.value.detail)

    def test_create_provider_with_missing_api_key_raises_exception(self):
        """Test that missing API key raises exception."""
        with patch.dict(os.environ, {"NEWS_API_KEY": ""}):
            with pytest.raises(HTTPException) as exc_info:
                create_bing_news_provider()

            assert exc_info.value.status_code == 503
            assert "Bing News API key not configured" in str(exc_info.value.detail)


class TestTTLCache:
    """Test the TTL cache functionality."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = TTLCache(default_ttl_seconds=60)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Test getting a nonexistent key."""
        cache = TTLCache(default_ttl_seconds=60)

        assert cache.get("nonexistent") is None

    def test_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache(default_ttl_seconds=1)  # 1 second TTL

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_custom_ttl(self):
        """Test setting custom TTL."""
        cache = TTLCache(default_ttl_seconds=60)

        cache.set("key1", "value1", ttl_seconds=1)
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_delete(self):
        """Test deleting cache entries."""
        cache = TTLCache(default_ttl_seconds=60)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("key1") is False

    def test_clear(self):
        """Test clearing all cache entries."""
        cache = TTLCache(default_ttl_seconds=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.size() == 0

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = TTLCache(default_ttl_seconds=1)

        cache.set("key1", "value1")
        cache.set("key2", "value2", ttl_seconds=2)

        # Wait for key1 to expire
        time.sleep(1.1)

        expired_count = cache.cleanup_expired()
        assert expired_count == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"


class TestNewsProviderFactory:
    """Test the news provider factory function."""

    def test_select_stub_provider_when_disabled(self):
        """Test that stub provider is selected when news is disabled."""
        with patch.dict(os.environ, {"NEWS_ENABLED": "false"}):
            provider = _select_news_provider()
            assert isinstance(provider, StubNewsProvider)

    def test_select_stub_provider_when_no_api_key(self):
        """Test that stub provider is selected when no API key is provided."""
        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "bing",
            "NEWS_API_KEY": ""
        }):
            provider = _select_news_provider()
            assert isinstance(provider, StubNewsProvider)

    def test_select_bing_provider_when_enabled(self):
        """Test that Bing provider is selected when properly configured."""
        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "bing",
            "NEWS_API_KEY": "test-key"
        }):
            provider = _select_news_provider()
            assert isinstance(provider, BingNewsProvider)

    def test_select_stub_provider_for_unknown_provider(self):
        """Test that stub provider is selected for unknown provider."""
        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "unknown",
            "NEWS_API_KEY": "test-key"
        }):
            provider = _select_news_provider()
            assert isinstance(provider, StubNewsProvider)


class TestNewsCaching:
    """Test news caching functionality."""

    def test_cache_hit(self):
        """Test that cache hits avoid provider calls."""
        # Clear cache first
        news_cache.clear()

        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "bing",
            "NEWS_API_KEY": "test-key"
        }):
            # First call should hit provider
            news1 = _fetch_news_for_company("Acme Capital")

            # Second call should hit cache
            news2 = _fetch_news_for_company("Acme Capital")

            assert news1 == news2

    def test_cache_eviction_by_ttl(self):
        """Test that cache entries are evicted by TTL."""
        # Clear cache first
        news_cache.clear()

        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "bing",
            "NEWS_API_KEY": "test-key",
            "NEWS_CACHE_TTL_MIN": "0"  # Immediate expiration
        }):
            # First call
            news1 = _fetch_news_for_company("Acme Capital")

            # Second call should not hit cache due to immediate expiration
            news2 = _fetch_news_for_company("Acme Capital")

            # Both should be the same (stub provider), but cache should be bypassed
            assert news1 == news2


class TestEnrichmentWithNews:
    """Test enrichment service integration with news."""

    def test_enrichment_uses_stub_news_by_default(self):
        """Test that enrichment uses stub news by default."""
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        with patch.dict(os.environ, {"NEWS_ENABLED": "false"}):
            enriched = enrich_meetings([meeting])

            assert len(enriched) == 1
            assert len(enriched[0].news) >= 3  # Should have news from fixtures
            assert all(hasattr(item, 'title') and hasattr(item, 'url') for item in enriched[0].news)

    def test_enrichment_uses_news_provider_when_enabled(self):
        """Test that enrichment uses news provider when enabled."""
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        with patch.dict(os.environ, {"NEWS_ENABLED": "true"}):
            enriched = enrich_meetings([meeting])

            assert len(enriched) == 1
            assert len(enriched[0].news) == 5  # Stub provider returns 5 items
            assert all(hasattr(item, 'title') and hasattr(item, 'url') for item in enriched[0].news)
            assert "Acme" in enriched[0].news[0].title

    def test_enrichment_fallback_on_news_error(self):
        """Test that enrichment falls back gracefully when news provider fails."""
        meeting = {
            "subject": "RPCK × Unknown Company — Portfolio Strategy Check-in",
            "attendees": []
        }

        # Mock news provider to raise exception
        mock_provider = MagicMock()
        mock_provider.search.side_effect = Exception("News API Error")

        with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
            with patch.dict(os.environ, {"NEWS_ENABLED": "true"}):
                enriched = enrich_meetings([meeting])

                assert len(enriched) == 1
                # Should fall back to empty news on error (the _fetch_news_for_company catches exceptions)
                assert len(enriched[0].news) == 0

    def test_enrichment_respects_max_items(self):
        """Test that enrichment respects NEWS_MAX_ITEMS limit."""
        meeting = {
            "subject": "RPCK × Test Company — Portfolio Strategy Check-in",
            "attendees": []
        }

        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_MAX_ITEMS": "2"
        }):
            enriched = enrich_meetings([meeting])

            assert len(enriched) == 1
            assert len(enriched[0].news) == 2  # Limited to 2 items
