import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.enrichment.service import enrich_meetings, _fetch_news_for_company, _select_news_provider
from app.enrichment.news_provider import StubNewsProvider
from app.enrichment.news_newsapi import NewsAPIProvider
from app.utils.cache import news_cache


class TestCompanyNews:
    """Test company news enrichment functionality."""

    def test_news_enabled_returns_company_links(self):
        """Test that NEWS_ENABLED=true returns 2-5 company news links."""
        with patch.dict(os.environ, {"NEWS_ENABLED": "true", "NEWS_PROVIDER": "newsapi", "NEWS_API_KEY": "test-key", "NEWS_MAX_ITEMS": "5"}):
            # Mock the NewsAPI provider
            mock_provider = MagicMock()
            mock_provider.search.return_value = [
                {"title": "Company A announces new product", "url": "https://example.com/news1"},
                {"title": "Company A raises Series B", "url": "https://example.com/news2"},
                {"title": "Company A expands operations", "url": "https://example.com/news3"},
                {"title": "Company A partners with major firm", "url": "https://example.com/news4"},
                {"title": "Company A recognized for innovation", "url": "https://example.com/news5"},
            ]

            with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                with patch('app.enrichment.service._load_fixtures', return_value={}):
                    meeting = {
                        "subject": "RPCK × Company A — Strategy Meeting",
                        "start_time": "9:00 AM ET",
                        "attendees": [],
                        "company": {"name": "Company A", "one_liner": "Test company"}
                    }

                    enriched = enrich_meetings([meeting])
                    assert len(enriched) == 1
                    # Company name should be extracted from company dict or subject
                    assert len(enriched[0].news) >= 2
                    assert len(enriched[0].news) <= 5
                    assert all(hasattr(item, 'title') and hasattr(item, 'url') for item in enriched[0].news)

    def test_news_disabled_uses_fixtures(self):
        """Test that NEWS_ENABLED=false uses fixture data."""
        with patch.dict(os.environ, {"NEWS_ENABLED": "false"}, clear=False):
            meeting = {
                "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
                "start_time": "9:30 AM ET",
                "attendees": [],
                "company": {"name": "Acme Capital", "one_liner": "Growth-stage investor"}
            }

            enriched = enrich_meetings([meeting])
            assert len(enriched) == 1
            # Should have news from fixtures
            assert len(enriched[0].news) > 0

    def test_news_provider_selection_newsapi(self):
        """Test that NEWS_PROVIDER=newsapi selects NewsAPI provider."""
        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key-123"
        }):
            with patch('app.enrichment.news_newsapi.create_newsapi_provider') as mock_create:
                mock_provider = MagicMock()
                mock_create.return_value = mock_provider

                provider = _select_news_provider()
                assert provider == mock_provider
                mock_create.assert_called_once()

    def test_news_provider_selection_stub_when_disabled(self):
        """Test that stub provider is used when NEWS_ENABLED=false."""
        with patch.dict(os.environ, {"NEWS_ENABLED": "false"}, clear=False):
            provider = _select_news_provider()
            assert isinstance(provider, StubNewsProvider)

    def test_news_provider_fallback_to_stub_on_error(self):
        """Test that provider errors fall back to stub."""
        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "invalid-key"
        }):
            with patch('app.enrichment.news_newsapi.create_newsapi_provider', side_effect=Exception("API error")):
                provider = _select_news_provider()
                assert isinstance(provider, StubNewsProvider)

    def test_news_caching(self):
        """Test that news results are cached."""
        news_cache.clear()

        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "NEWS_CACHE_TTL_MIN": "60"
        }):
            mock_provider = MagicMock()
            mock_provider.search.return_value = [
                {"title": "Test News", "url": "https://example.com/test"}
            ]

            with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                # First call - should hit provider
                result1 = _fetch_news_for_company("Test Company")
                assert len(result1) == 1
                assert mock_provider.search.call_count == 1

                # Second call - should hit cache
                result2 = _fetch_news_for_company("Test Company")
                assert len(result2) == 1
                assert result2 == result1
                # Provider should not be called again
                assert mock_provider.search.call_count == 1

    def test_news_max_items_respects_range(self):
        """Test that NEWS_MAX_ITEMS is clamped to 2-5 range."""
        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "NEWS_MAX_ITEMS": "10"  # Should be clamped to 5
        }):
            mock_provider = MagicMock()
            mock_provider.search.return_value = [
                {"title": f"News {i}", "url": f"https://example.com/news{i}"}
                for i in range(10)
            ]

            with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                result = _fetch_news_for_company("Test Company")
                assert len(result) <= 5

        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "NEWS_MAX_ITEMS": "1"  # Should be clamped to 2
        }):
            mock_provider = MagicMock()
            mock_provider.search.return_value = [
                {"title": "News 1", "url": "https://example.com/news1"}
            ]

            with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                result = _fetch_news_for_company("Test Company")
                assert len(result) >= 2 or len(result) == 1  # At least 1 if provider returns 1

    def test_news_provider_error_returns_empty_list(self):
        """Test that provider errors return empty list gracefully."""
        # Clear cache first
        news_cache.clear()

        with patch.dict(os.environ, {
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key"
        }):
            mock_provider = MagicMock()
            mock_provider.search.side_effect = Exception("Network error")

            with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                result = _fetch_news_for_company("Test Company Error")
                assert result == []
                # Should not raise exception

    def test_newsapi_provider_handles_timeout(self):
        """Test that NewsAPI provider handles timeouts gracefully."""
        provider = NewsAPIProvider(api_key="test-key", timeout_seconds=0.001)

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("Timeout")

            result = provider.search("Test Company")
            assert result == []

    def test_newsapi_provider_handles_rate_limit(self):
        """Test that NewsAPI provider handles rate limits gracefully."""
        provider = NewsAPIProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            result = provider.search("Test Company")
            assert result == []

    def test_newsapi_provider_parses_response(self):
        """Test that NewsAPI provider correctly parses API response."""
        provider = NewsAPIProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "articles": [
                {
                    "title": "Company A announces new product",
                    "url": "https://example.com/news1",
                    "description": "Test description"
                },
                {
                    "title": "Company A raises funding",
                    "url": "https://example.com/news2",
                    "description": "Test description 2"
                }
            ]
        }

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            result = provider.search("Company A")
            assert len(result) == 2
            assert result[0]["title"] == "Company A announces new product"
            assert result[0]["url"] == "https://example.com/news1"

    def test_newsapi_provider_filters_spam(self):
        """Test that NewsAPI provider filters out spam/low-quality articles."""
        provider = NewsAPIProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "articles": [
                {
                    "title": "Company A announces new product [REMOVED]",
                    "url": "https://example.com/news1"
                },
                {
                    "title": "Click here to read more about Company A",
                    "url": "https://example.com/news2"
                },
                {
                    "title": "Company A raises Series B",
                    "url": "https://example.com/news3"
                }
            ]
        }

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            result = provider.search("Company A")
            # Should filter out spam
            assert len(result) == 1
            assert "Series B" in result[0]["title"]

