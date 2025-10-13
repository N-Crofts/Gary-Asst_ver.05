"""
People Intel Resolver

Implements metadata-only person resolution using search queries and confidence scoring.
No LLM required - uses domain/company anchors and negative keywords.
"""

import os
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

from app.people.normalizer import PersonHint, is_internal_attendee
from app.people.reranker import PersonReranker, PersonResult
from app.utils.cache import TTLCache

logger = logging.getLogger(__name__)


@dataclass
class SearchSignals:
    """Signals used for person search scoring."""
    positive_signals: List[str]
    negative_signals: List[str]


class PeopleResolver:
    """
    Resolves people using metadata-only search with confidence scoring.
    """

    def __init__(self):
        """Initialize the people resolver with configuration."""
        self.enabled = os.getenv("PEOPLE_NEWS_ENABLED", "false").lower() == "true"
        self.strict_mode = os.getenv("PEOPLE_STRICT_MODE", "true").lower() == "true"
        self.confidence_min = float(os.getenv("PEOPLE_CONFIDENCE_MIN", "0.75"))
        self.show_medium = os.getenv("PEOPLE_CONFIDENCE_SHOW_MEDIUM", "true").lower() == "true"
        self.cache_ttl = int(os.getenv("PEOPLE_CACHE_TTL_MIN", "120")) * 60  # Convert to seconds

        # Initialize cache
        self.cache = TTLCache(default_ttl_seconds=self.cache_ttl)

        # News provider (will be injected)
        self.news_provider = None

        # Initialize re-ranker
        self.reranker = PersonReranker()

        logger.info(f"PeopleResolver initialized: enabled={self.enabled}, strict={self.strict_mode}, "
                   f"min_confidence={self.confidence_min}, show_medium={self.show_medium}")

    def set_news_provider(self, news_provider):
        """Set the news provider for making search requests."""
        self.news_provider = news_provider

    def resolve_person(self, person_hint: PersonHint, meeting_context: Dict[str, Any]) -> List[PersonResult]:
        """
        Resolve a person using metadata-only search with confidence scoring.

        Args:
            person_hint: PersonHint with person metadata
            meeting_context: Meeting context for additional clues

        Returns:
            List of PersonResult objects with confidence scores
        """
        if not self.enabled or not self.news_provider:
            return []

        # Skip internal attendees
        if is_internal_attendee(person_hint):
            logger.debug(f"Skipping internal attendee: {person_hint.name}")
            return []

        # Check cache first
        cache_key = f"person_{person_hint.name}_{person_hint.domain or 'no_domain'}"
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for {person_hint.name}")
            return cached_result

        try:
            # Execute search strategy
            results = self._execute_search_strategy(person_hint)

            # Score and filter results
            scored_results = self._score_and_filter_results(results, person_hint)

            # Re-rank results using LLM if enabled
            reranked_results = self.reranker.rerank_results(scored_results, person_hint, meeting_context)

            # Cache results
            self.cache.set(cache_key, reranked_results)

            logger.info(f"Resolved {person_hint.name}: {len(reranked_results)} results")
            return reranked_results

        except Exception as e:
            logger.error(f"Error resolving person {person_hint.name}: {e}")
            return []

    def _execute_search_strategy(self, person_hint: PersonHint) -> List[Dict[str, Any]]:
        """
        Execute the two-pass search strategy.

        Pass A: site:<domain> query
        Pass B: name + (domain OR company) query

        Args:
            person_hint: PersonHint with search metadata

        Returns:
            List of raw search results
        """
        all_results = []

        # Pass A: Site-specific search
        if person_hint.has_domain:
            site_query = f'site:{person_hint.domain}'
            if person_hint.search_name:
                site_query += f' "{person_hint.search_name}"'

            try:
                site_results = self.news_provider.search_news(site_query, max_items=5)
                for result in site_results:
                    result["source"] = "site"
                all_results.extend(site_results)
                logger.debug(f"Site search '{site_query}': {len(site_results)} results")
            except Exception as e:
                logger.warning(f"Site search failed for {person_hint.name}: {e}")

        # Pass B: Name + domain/company search
        if person_hint.search_name:
            name_query = f'"{person_hint.search_name}"'

            # Add domain if available
            if person_hint.has_domain:
                name_query += f' "{person_hint.domain}"'

            # Add company if available and different from domain
            if person_hint.has_company and person_hint.company != person_hint.domain:
                name_query += f' "{person_hint.company}"'

            try:
                name_results = self.news_provider.search_news(name_query, max_items=5)
                for result in name_results:
                    result["source"] = "name"
                all_results.extend(name_results)
                logger.debug(f"Name search '{name_query}': {len(name_results)} results")
            except Exception as e:
                logger.warning(f"Name search failed for {person_hint.name}: {e}")

        return all_results

    def _score_and_filter_results(
        self,
        results: List[Dict[str, Any]],
        person_hint: PersonHint
    ) -> List[PersonResult]:
        """
        Score results using confidence anchors and negative keywords.

        Args:
            results: Raw search results
            person_hint: PersonHint for scoring context

        Returns:
            List of scored and filtered PersonResult objects
        """
        if not results:
            return []

        # Get scoring anchors and negative keywords
        anchors = person_hint.get_confidence_anchors()
        negatives = person_hint.get_negative_keywords()

        scored_results = []

        for result in results:
            confidence = self._calculate_confidence(result, anchors, negatives)

            if confidence >= self.confidence_min:
                # High confidence - always include
                person_result = PersonResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    confidence=confidence,
                    source=result.get("source", "unknown"),
                    matched_anchors=self._find_matched_anchors(result, anchors),
                    negative_signals=self._find_negative_signals(result, negatives)
                )
                scored_results.append(person_result)

            elif confidence >= 0.5 and self.show_medium:
                # Medium confidence - include only if no high confidence results
                person_result = PersonResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    confidence=confidence,
                    source=result.get("source", "unknown"),
                    matched_anchors=self._find_matched_anchors(result, anchors),
                    negative_signals=self._find_negative_signals(result, negatives)
                )
                scored_results.append(person_result)

        # Remove duplicates based on URL
        seen_urls = set()
        unique_results = []
        for result in scored_results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)

        # Sort by confidence (highest first) and limit to 3 results
        unique_results.sort(key=lambda x: x.confidence, reverse=True)
        return unique_results[:3]

    def _calculate_confidence(
        self,
        result: Dict[str, Any],
        anchors: List[str],
        negatives: List[str]
    ) -> float:
        """
        Calculate confidence score for a search result.

        Args:
            result: Search result dictionary
            anchors: Confidence anchor terms
            negatives: Negative signal terms

        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence

        # Check title and content for anchors
        text_to_check = f"{result.get('title', '')} {result.get('content', '')}".lower()

        # Boost for anchor matches
        anchor_matches = 0
        for anchor in anchors:
            if anchor.lower() in text_to_check:
                anchor_matches += 1
                confidence += 0.2  # +0.2 per anchor match

        # Penalty for negative signals
        negative_matches = 0
        for negative in negatives:
            if negative.lower() in text_to_check:
                negative_matches += 1
                confidence -= 0.3  # -0.3 per negative match

        # Clamp to [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))

        return confidence

    def _find_matched_anchors(self, result: Dict[str, Any], anchors: List[str]) -> List[str]:
        """Find which anchors matched in the result."""
        text_to_check = f"{result.get('title', '')} {result.get('content', '')}".lower()
        matched = []
        for anchor in anchors:
            if anchor.lower() in text_to_check:
                matched.append(anchor)
        return matched

    def _find_negative_signals(self, result: Dict[str, Any], negatives: List[str]) -> List[str]:
        """Find which negative signals matched in the result."""
        text_to_check = f"{result.get('title', '')} {result.get('content', '')}".lower()
        matched = []
        for negative in negatives:
            if negative.lower() in text_to_check:
                matched.append(negative)
        return matched


def create_people_resolver() -> PeopleResolver:
    """Create and configure a PeopleResolver instance."""
    return PeopleResolver()
