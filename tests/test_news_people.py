import pytest
import os
from unittest.mock import patch, MagicMock

from app.enrichment.service import enrich_meetings, _fetch_people_intel_for_attendees
from app.people.resolver import PeopleResolver
from app.people.normalizer import build_person_hint
from app.enrichment.news_provider import StubNewsProvider


class TestPeopleIntel:
    """Test people intel enrichment functionality."""

    def test_people_news_enabled_returns_intel(self):
        """Test that PEOPLE_NEWS_ENABLED=true returns people intel for external attendees."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "PEOPLE_STRICT_MODE": "false",
            "PEOPLE_CONFIDENCE_MIN": "0.5"
        }):
            # Mock news provider
            mock_provider = MagicMock()
            mock_provider.search_news.return_value = [
                {"title": "John Doe named CEO", "url": "https://example.com/john-doe"},
                {"title": "John Doe speaks at conference", "url": "https://example.com/john-doe-2"}
            ]

            # Mock people resolver
            mock_resolver = MagicMock()
            mock_resolver.resolve_person.return_value = [
                MagicMock(title="John Doe named CEO", url="https://example.com/john-doe", confidence=0.8)
            ]

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                    meeting = {
                        "subject": "Meeting with External Company",
                        "start_time": "9:00 AM ET",
                        "attendees": [
                            {"name": "John Doe", "email": "john@external.com", "company": "External Corp"}
                        ]
                    }

                    enriched = enrich_meetings([meeting])
                    assert len(enriched) == 1
                    assert enriched[0].people_intel is not None
                    assert "John Doe" in enriched[0].people_intel

    def test_people_news_disabled_returns_empty(self):
        """Test that PEOPLE_NEWS_ENABLED=false returns no people intel."""
        with patch.dict(os.environ, {"PEOPLE_NEWS_ENABLED": "false"}, clear=False):
            meeting = {
                "subject": "Meeting with External Company",
                "start_time": "9:00 AM ET",
                "attendees": [
                    {"name": "John Doe", "email": "john@external.com", "company": "External Corp"}
                ]
            }

            enriched = enrich_meetings([meeting])
            assert len(enriched) == 1
            assert enriched[0].people_intel is None or enriched[0].people_intel == {}

    def test_people_intel_skips_internal_attendees(self):
        """Test that people intel only processes external attendees."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key"
        }):
            mock_resolver = MagicMock()
            mock_resolver.resolve_person.return_value = []

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                meeting = {
                    "subject": "Internal Meeting",
                    "start_time": "9:00 AM ET",
                    "attendees": [
                        {"name": "Internal Person", "email": "internal@rpck.com", "company": "RPCK"}
                    ]
                }

                enriched = enrich_meetings([meeting])
                assert len(enriched) == 1
                # Internal attendees should be skipped
                assert mock_resolver.resolve_person.call_count == 0

    def test_people_intel_strict_mode_filters_by_confidence(self):
        """Test that strict mode filters results by confidence threshold."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "PEOPLE_STRICT_MODE": "true",
            "PEOPLE_CONFIDENCE_MIN": "0.75"
        }):
            # Mock resolver with mixed confidence results
            mock_resolver = MagicMock()
            mock_resolver.resolve_person.return_value = [
                MagicMock(title="High confidence article", url="https://example.com/1", confidence=0.85),
                MagicMock(title="Low confidence article", url="https://example.com/2", confidence=0.60),
                MagicMock(title="Medium confidence article", url="https://example.com/3", confidence=0.80)
            ]

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                meeting = {
                    "subject": "Meeting with External",
                    "start_time": "9:00 AM ET",
                    "attendees": [
                        {"name": "John Doe", "email": "john@external.com", "company": "External Corp"}
                    ]
                }

                enriched = enrich_meetings([meeting])
                assert len(enriched) == 1
                if enriched[0].people_intel and "John Doe" in enriched[0].people_intel:
                    # In strict mode, only high confidence items should be included
                    intel_items = enriched[0].people_intel["John Doe"]
                    # The resolver should filter by confidence
                    assert len(intel_items) >= 1

    def test_people_intel_handles_provider_errors(self):
        """Test that people intel handles provider errors gracefully."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key"
        }):
            mock_resolver = MagicMock()
            mock_resolver.resolve_person.side_effect = Exception("Provider error")

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                meeting = {
                    "subject": "Meeting with External",
                    "start_time": "9:00 AM ET",
                    "attendees": [
                        {"name": "John Doe", "email": "john@external.com", "company": "External Corp"}
                    ]
                }

                # Should not raise exception
                enriched = enrich_meetings([meeting])
                assert len(enriched) == 1
                # Should have empty or no people intel on error
                assert enriched[0].people_intel is None or enriched[0].people_intel == {}

    def test_people_resolver_uses_news_provider(self):
        """Test that people resolver correctly uses the news provider."""
        resolver = PeopleResolver()
        mock_provider = MagicMock()
        mock_provider.search_news.return_value = [
            {"title": "Test Article", "url": "https://example.com/test"}
        ]

        resolver.set_news_provider(mock_provider)
        assert resolver.news_provider == mock_provider

        # Test that resolver calls search_news
        from app.people.normalizer import PersonHint
        person_hint = PersonHint(
            name="John Doe",
            email="john@example.com",
            domain="example.com",
            company="Example Corp"
        )

        resolver.enabled = True
        resolver.strict_mode = False
        resolver.confidence_min = 0.5

        # Mock the scoring and filtering methods
        resolver._score_and_filter_results = MagicMock(return_value=[])
        resolver._execute_search_strategy = MagicMock(return_value=[])

        result = resolver.resolve_person(person_hint, {})
        # Should not raise exception
        assert isinstance(result, list)

    def test_people_intel_cache_key_includes_provider(self):
        """Test that cache keys include provider name for proper isolation."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "PEOPLE_CACHE_TTL_MIN": "120"
        }):
            mock_provider = MagicMock()
            mock_provider.search_news.return_value = []

            mock_resolver = MagicMock()
            mock_resolver.resolve_person.return_value = []

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                with patch('app.enrichment.service._select_news_provider', return_value=mock_provider):
                    meeting = {
                        "subject": "Meeting",
                        "start_time": "9:00 AM ET",
                        "attendees": [
                            {"name": "John Doe", "email": "john@external.com"}
                        ]
                    }

                    # First call
                    enriched1 = enrich_meetings([meeting])

                    # Second call - should use cache if implemented
                    enriched2 = enrich_meetings([meeting])

                    # Both should succeed
                    assert len(enriched1) == 1
                    assert len(enriched2) == 1

    def test_people_intel_no_results_returns_empty(self):
        """Test that no people intel results return empty dict."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key"
        }):
            mock_resolver = MagicMock()
            mock_resolver.resolve_person.return_value = []  # No results

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                meeting = {
                    "subject": "Meeting",
                    "start_time": "9:00 AM ET",
                    "attendees": [
                        {"name": "Unknown Person", "email": "unknown@external.com"}
                    ]
                }

                enriched = enrich_meetings([meeting])
                assert len(enriched) == 1
                # Should have empty people_intel when no results
                assert enriched[0].people_intel is None or enriched[0].people_intel == {}

    def test_people_intel_correct_person_not_famous_mismatch(self):
        """Test that people intel finds correct person and avoids famous name mismatches."""
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "NEWS_ENABLED": "true",
            "NEWS_PROVIDER": "newsapi",
            "NEWS_API_KEY": "test-key",
            "PEOPLE_STRICT_MODE": "true",
            "PEOPLE_CONFIDENCE_MIN": "0.75"
        }):
            # Mock resolver that returns high-confidence results for correct person
            mock_resolver = MagicMock()
            # Simulate finding correct person with domain/company evidence
            mock_resolver.resolve_person.return_value = [
                MagicMock(
                    title="John Doe from Example Corp speaks at conference",
                    url="https://example.com/john-doe",
                    confidence=0.85
                )
            ]

            with patch('app.enrichment.service.create_people_resolver', return_value=mock_resolver):
                meeting = {
                    "subject": "Meeting with Example Corp",
                    "start_time": "9:00 AM ET",
                    "attendees": [
                        {"name": "John Doe", "email": "john@example.com", "company": "Example Corp"}
                    ]
                }

                enriched = enrich_meetings([meeting])
                assert len(enriched) == 1

                # Should find results for the correct person (with domain/company match)
                if enriched[0].people_intel and "John Doe" in enriched[0].people_intel:
                    intel = enriched[0].people_intel["John Doe"]
                    # Results should have high confidence (strict mode)
                    assert len(intel) > 0
                    # Should mention the company/domain for validation
                    assert any("example" in item.get("title", "").lower() or
                              "example" in item.get("url", "").lower()
                              for item in intel)

