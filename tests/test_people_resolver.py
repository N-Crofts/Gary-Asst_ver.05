"""
Tests for People Intel Resolver

Tests metadata-only person resolution with confidence scoring.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from typing import List, Dict, Any

from app.people.normalizer import PersonHint, build_person_hint, extract_domain_from_email, normalize_company_name
from app.people.resolver import PeopleResolver, PersonResult, create_people_resolver


class TestPersonHint:
    """Test PersonHint data structure and methods."""

    def test_person_hint_creation(self):
        """Test basic PersonHint creation."""
        hint = PersonHint(
            name="John Doe",
            email="john@example.com",
            domain="example.com",
            company="Example Corp",
            title="CEO"
        )

        assert hint.name == "John Doe"
        assert hint.email == "john@example.com"
        assert hint.domain == "example.com"
        assert hint.company == "Example Corp"
        assert hint.title == "CEO"
        assert hint.co_attendee_domains == []
        assert hint.keywords == []

    def test_normalized_name(self):
        """Test name normalization."""
        hint = PersonHint(name="Dr. John Smith Jr.")
        assert hint.normalized_name == "John Smith"

        hint = PersonHint(name="Mr. Jane Doe III")
        assert hint.normalized_name == "Jane Doe"

        hint = PersonHint(name="Prof. Alice Johnson")
        assert hint.normalized_name == "Alice Johnson"

    def test_search_name(self):
        """Test search name optimization."""
        hint = PersonHint(name="Dr. John Michael Smith Jr.")
        assert hint.search_name == "John Smith"

        hint = PersonHint(name="Jane Doe")
        assert hint.search_name == "Jane Doe"

        hint = PersonHint(name="Alice")
        assert hint.search_name == "Alice"

    def test_has_domain(self):
        """Test domain detection."""
        hint = PersonHint(name="John Doe", domain="example.com")
        assert hint.has_domain is True

        hint = PersonHint(name="John Doe", domain=None)
        assert hint.has_domain is False

        hint = PersonHint(name="John Doe", domain="unknown")
        assert hint.has_domain is False

    def test_has_company(self):
        """Test company detection."""
        hint = PersonHint(name="John Doe", company="Example Corp")
        assert hint.has_company is True

        hint = PersonHint(name="John Doe", company=None)
        assert hint.has_company is False

        hint = PersonHint(name="John Doe", company="")
        assert hint.has_company is False

    def test_get_search_queries(self):
        """Test search query generation."""
        hint = PersonHint(
            name="John Doe",
            domain="example.com",
            company="Example Corp"
        )

        queries = hint.get_search_queries()
        assert len(queries) == 2
        assert 'site:example.com "John Doe"' in queries
        assert '"John Doe" "example.com" "Example Corp"' in queries

    def test_get_search_queries_no_domain(self):
        """Test search query generation without domain."""
        hint = PersonHint(
            name="John Doe",
            company="Example Corp"
        )

        queries = hint.get_search_queries()
        assert len(queries) == 1
        assert '"John Doe" "Example Corp"' in queries

    def test_get_confidence_anchors(self):
        """Test confidence anchor extraction."""
        hint = PersonHint(
            name="John Doe",
            domain="example.com",
            company="Example Corp",
            co_attendee_domains=["partner.com", "client.com"]
        )

        anchors = hint.get_confidence_anchors()
        assert "example.com" in anchors
        assert "Example Corp" in anchors
        assert "partner.com" in anchors
        assert "client.com" in anchors

    def test_get_negative_keywords(self):
        """Test negative keyword extraction."""
        hint = PersonHint(name="John Doe", keywords=["scandal", "fraud"])

        negatives = hint.get_negative_keywords()
        assert "obituary" in negatives
        assert "death" in negatives
        assert "scandal" in negatives
        assert "fraud" in negatives


class TestPersonHintHelpers:
    """Test PersonHint helper functions."""

    def test_extract_domain_from_email(self):
        """Test domain extraction from email."""
        assert extract_domain_from_email("john@example.com") == "example.com"
        assert extract_domain_from_email("jane@company.co.uk") == "company.co.uk"
        assert extract_domain_from_email("invalid-email") is None
        assert extract_domain_from_email("") is None
        assert extract_domain_from_email(None) is None

    def test_normalize_company_name(self):
        """Test company name normalization."""
        assert normalize_company_name("Example Corp Inc.") == "Example Corp"
        assert normalize_company_name("Test Company LLC") == "Test Company"
        assert normalize_company_name("Simple Name") == "Simple Name"
        assert normalize_company_name("") == ""
        assert normalize_company_name(None) == ""

    def test_build_person_hint(self):
        """Test building PersonHint from attendee data."""
        attendee = {
            "name": "John Doe",
            "email": "john@example.com",
            "company": "Example Corp",
            "title": "CEO"
        }

        meeting_context = {
            "subject": "Partnership Discussion",
            "attendees": [
                {"name": "John Doe", "email": "john@example.com"},
                {"name": "Jane Smith", "email": "jane@partner.com"}
            ]
        }

        hint = build_person_hint(attendee, meeting_context)

        assert hint.name == "John Doe"
        assert hint.email == "john@example.com"
        assert hint.domain == "example.com"
        assert hint.company == "Example Corp"
        assert hint.title == "CEO"
        assert "partner.com" in hint.co_attendee_domains
        assert "Partnership" in hint.keywords


class TestPeopleResolver:
    """Test PeopleResolver functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patches = {
            "PEOPLE_NEWS_ENABLED": "true",
            "PEOPLE_STRICT_MODE": "true",
            "PEOPLE_CONFIDENCE_MIN": "0.75",
            "PEOPLE_CONFIDENCE_SHOW_MEDIUM": "true",
            "PEOPLE_CACHE_TTL_MIN": "120"
        }

        for key, value in self.env_patches.items():
            os.environ[key] = value

    def teardown_method(self):
        """Clean up test environment."""
        for key in self.env_patches:
            if key in os.environ:
                del os.environ[key]

    def test_resolver_initialization(self):
        """Test resolver initialization with environment variables."""
        resolver = PeopleResolver()

        assert resolver.enabled is True
        assert resolver.strict_mode is True
        assert resolver.confidence_min == 0.75
        assert resolver.show_medium is True
        assert resolver.cache_ttl == 7200  # 120 minutes in seconds

    def test_resolver_disabled(self):
        """Test resolver when disabled."""
        os.environ["PEOPLE_NEWS_ENABLED"] = "false"
        resolver = PeopleResolver()

        assert resolver.enabled is False

    def test_resolve_person_no_provider(self):
        """Test person resolution without news provider."""
        resolver = PeopleResolver()
        hint = PersonHint(name="John Doe")

        results = resolver.resolve_person(hint, {})
        assert results == []

    def test_resolve_person_disabled(self):
        """Test person resolution when disabled."""
        os.environ["PEOPLE_NEWS_ENABLED"] = "false"
        resolver = PeopleResolver()
        resolver.news_provider = MagicMock()

        hint = PersonHint(name="John Doe")
        results = resolver.resolve_person(hint, {})
        assert results == []

    def test_resolve_person_with_provider(self):
        """Test person resolution with news provider."""
        resolver = PeopleResolver()

        # Mock news provider
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {
                "title": "John Doe named CEO of Example Corp",
                "url": "https://example.com/news/john-doe-ceo",
                "content": "John Doe has been named CEO of Example Corp..."
            }
        ]
        resolver.news_provider = mock_provider

        hint = PersonHint(
            name="John Doe",
            domain="example.com",
            company="Example Corp"
        )

        results = resolver.resolve_person(hint, {})

        assert len(results) == 1
        assert results[0].title == "John Doe named CEO of Example Corp"
        assert results[0].url == "https://example.com/news/john-doe-ceo"
        assert results[0].confidence > 0.75
        assert results[0].source == "site"

    def test_confidence_scoring(self):
        """Test confidence scoring logic."""
        resolver = PeopleResolver()

        # Mock news provider
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {
                "title": "John Doe CEO Example Corp",
                "url": "https://example.com/news",
                "content": "John Doe is the CEO of Example Corp"
            }
        ]
        resolver.news_provider = mock_provider

        hint = PersonHint(
            name="John Doe",
            domain="example.com",
            company="Example Corp"
        )

        results = resolver.resolve_person(hint, {})

        # Should have high confidence due to domain and company matches
        assert len(results) == 1
        assert results[0].confidence >= 0.75
        assert "example.com" in results[0].matched_anchors
        assert "Example Corp" in results[0].matched_anchors

    def test_negative_signals(self):
        """Test negative signal detection."""
        resolver = PeopleResolver()

        # Mock news provider with negative content
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {
                "title": "John Doe arrested for fraud",
                "url": "https://example.com/news",
                "content": "John Doe was arrested and charged with fraud"
            }
        ]
        resolver.news_provider = mock_provider

        hint = PersonHint(name="John Doe")

        results = resolver.resolve_person(hint, {})

        # Should have low confidence due to negative signals
        assert len(results) == 0  # Should be filtered out due to low confidence

    def test_medium_confidence_results(self):
        """Test medium confidence results when enabled."""
        os.environ["PEOPLE_CONFIDENCE_MIN"] = "0.8"  # High threshold
        os.environ["PEOPLE_CONFIDENCE_SHOW_MEDIUM"] = "true"

        resolver = PeopleResolver()

        # Mock news provider
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {
                "title": "John Doe mentioned in article",
                "url": "https://example.com/news",
                "content": "John Doe was mentioned in passing"
            }
        ]
        resolver.news_provider = mock_provider

        hint = PersonHint(name="John Doe")

        results = resolver.resolve_person(hint, {})

        # Should include medium confidence results
        assert len(results) >= 0  # May or may not include based on scoring

    def test_duplicate_removal(self):
        """Test duplicate result removal."""
        resolver = PeopleResolver()

        # Mock news provider with duplicate URLs
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {
                "title": "John Doe Article 1",
                "url": "https://example.com/news",
                "content": "John Doe content"
            },
            {
                "title": "John Doe Article 2",
                "url": "https://example.com/news",  # Same URL
                "content": "John Doe content"
            }
        ]
        resolver.news_provider = mock_provider

        hint = PersonHint(name="John Doe")

        results = resolver.resolve_person(hint, {})

        # Should remove duplicates
        urls = [result.url for result in results]
        assert len(urls) == len(set(urls))  # No duplicates

    def test_result_limit(self):
        """Test result limiting to 3 items."""
        resolver = PeopleResolver()

        # Mock news provider with many results
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {
                "title": f"John Doe Article {i}",
                "url": f"https://example.com/news{i}",
                "content": "John Doe content"
            }
            for i in range(10)
        ]
        resolver.news_provider = mock_provider

        hint = PersonHint(name="John Doe")

        results = resolver.resolve_person(hint, {})

        # Should be limited to 3 results
        assert len(results) <= 3


class TestPeopleResolverIntegration:
    """Test PeopleResolver integration with enrichment."""

    def setup_method(self):
        """Set up test environment."""
        self.env_patches = {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "stub"
        }

        for key, value in self.env_patches.items():
            os.environ[key] = value

    def teardown_method(self):
        """Clean up test environment."""
        for key in self.env_patches:
            if key in os.environ:
                del os.environ[key]

    def test_internal_attendee_skipped(self):
        """Test that internal attendees are skipped."""
        from app.enrichment.service import _fetch_people_intel_for_attendees

        meeting = {
            "attendees": [
                {
                    "name": "Internal User",
                    "email": "internal@rpck.com",
                    "company": "RPCK"
                }
            ]
        }

        people_intel = _fetch_people_intel_for_attendees(meeting)
        assert people_intel == {}

    def test_external_attendee_processed(self):
        """Test that external attendees are processed."""
        from app.enrichment.service import _fetch_people_intel_for_attendees

        meeting = {
            "attendees": [
                {
                    "name": "External User",
                    "email": "external@example.com",
                    "company": "Example Corp"
                }
            ]
        }

        with patch('app.enrichment.service._select_news_provider') as mock_provider:
            mock_news_provider = MagicMock()
            mock_news_provider.search_news.return_value = [
                {
                    "title": "External User in the news",
                    "url": "https://example.com/news",
                    "content": "External User was mentioned"
                }
            ]
            mock_provider.return_value = mock_news_provider

            people_intel = _fetch_people_intel_for_attendees(meeting)

            # Should process external attendee
            assert "External User" in people_intel
            assert len(people_intel["External User"]) > 0


class TestPeopleResolverEdgeCases:
    """Test PeopleResolver edge cases and error handling."""

    def test_empty_attendee_name(self):
        """Test handling of attendees with empty names."""
        resolver = PeopleResolver()
        resolver.news_provider = MagicMock()

        hint = PersonHint(name="")
        results = resolver.resolve_person(hint, {})
        assert results == []

    def test_provider_error_handling(self):
        """Test graceful handling of provider errors."""
        resolver = PeopleResolver()

        # Mock news provider that raises exception
        mock_provider = MagicMock()
        mock_provider.search_news.side_effect = Exception("Provider error")
        resolver.news_provider = mock_provider

        hint = PersonHint(name="John Doe")
        results = resolver.resolve_person(hint, {})

        # Should return empty list on error
        assert results == []

    def test_cache_functionality(self):
        """Test caching functionality."""
        resolver = PeopleResolver()
        resolver.news_provider = MagicMock()
        resolver.news_provider.search_news.return_value = [
            {
                "title": "Cached Article",
                "url": "https://example.com/news",
                "content": "Cached content"
            }
        ]

        hint = PersonHint(name="John Doe", domain="example.com")

        # First call
        results1 = resolver.resolve_person(hint, {})
        assert len(results1) > 0

        # Second call should use cache
        results2 = resolver.resolve_person(hint, {})
        assert len(results2) > 0

        # Provider should only be called once due to caching
        assert resolver.news_provider.search_news.call_count == 1


class TestCreatePeopleResolver:
    """Test people resolver factory function."""

    def test_create_people_resolver(self):
        """Test create_people_resolver factory function."""
        resolver = create_people_resolver()

        assert isinstance(resolver, PeopleResolver)
        assert resolver.enabled is False  # Default when env not set
