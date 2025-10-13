"""
LLM Re-ranker for Person-News Results

Implements optional LLM-based re-ranking of person-news results to improve precision.
Falls back to metadata-based ordering on timeout or error.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.people.normalizer import PersonHint
from app.llm.service import LLMClient, select_llm_client

logger = logging.getLogger(__name__)


@dataclass
class PersonResult:
    """Result of a person search with confidence scoring."""
    title: str
    url: str
    confidence: float
    source: str  # "site" or "name"
    matched_anchors: List[str]


@dataclass
class RerankResult:
    """Result of LLM re-ranking with score and reasoning."""
    result: PersonResult
    llm_score: float
    reasoning: str


class PersonReranker:
    """
    Re-ranks person-news results using LLM to improve precision.

    Operates on already-accepted candidates and sorts them by LLM score.
    Falls back to metadata order on timeout/error.
    """

    def __init__(self):
        """Initialize the re-ranker with configuration."""
        self.enabled = os.getenv("PEOPLE_RERANK_LLM", "false").lower() == "true"
        self.timeout_seconds = float(os.getenv("PEOPLE_RERANK_TIMEOUT_MS", "2000")) / 1000.0
        self.max_candidates = int(os.getenv("PEOPLE_RERANK_MAX_CANDIDATES", "5"))

        # Get LLM client (will be StubLLMClient if LLM is disabled)
        self.llm_client = select_llm_client()

        logger.info(f"PersonReranker initialized: enabled={self.enabled}, "
                   f"timeout={self.timeout_seconds}s, max_candidates={self.max_candidates}")

    def rerank_results(
        self,
        results: List[PersonResult],
        person_hint: PersonHint,
        meeting_context: Dict[str, Any]
    ) -> List[PersonResult]:
        """
        Re-rank person results using LLM scoring.

        Args:
            results: List of PersonResult objects to re-rank
            person_hint: PersonHint for context
            meeting_context: Meeting context for additional clues

        Returns:
            Re-ranked list of PersonResult objects
        """
        if not self.enabled or not results:
            return results

        # Limit candidates to avoid expensive LLM calls
        candidates = results[:self.max_candidates]

        try:
            # Attempt LLM re-ranking with timeout
            reranked = self._rerank_with_llm(candidates, person_hint, meeting_context)

            # Combine re-ranked candidates with remaining results
            remaining = results[self.max_candidates:]
            final_results = reranked + remaining

            logger.info(f"Re-ranked {len(candidates)} candidates for {person_hint.name}")
            return final_results

        except Exception as e:
            logger.warning(f"LLM re-ranking failed for {person_hint.name}: {e}, "
                          "falling back to metadata order")
            return results

    def _rerank_with_llm(
        self,
        candidates: List[PersonResult],
        person_hint: PersonHint,
        meeting_context: Dict[str, Any]
    ) -> List[PersonResult]:
        """
        Re-rank candidates using LLM with timeout protection.

        Args:
            candidates: List of PersonResult objects to re-rank
            person_hint: PersonHint for context
            meeting_context: Meeting context for additional clues

        Returns:
            Re-ranked list of PersonResult objects
        """
        if not candidates:
            return []

        # Build prompt for LLM re-ranking
        prompt = self._build_rerank_prompt(candidates, person_hint, meeting_context)

        # Call LLM with timeout
        start_time = time.time()
        try:
            # Use the LLM client's rerank method
            response = self.llm_client.rerank_person_results(prompt)

            # Check timeout
            if time.time() - start_time > self.timeout_seconds:
                raise TimeoutError("LLM re-ranking timed out")

            # Parse LLM response and re-rank
            reranked_results = self._parse_llm_response(response, candidates)

            return reranked_results

        except TimeoutError:
            logger.warning(f"LLM re-ranking timed out after {self.timeout_seconds}s")
            raise
        except Exception as e:
            logger.error(f"LLM re-ranking error: {e}")
            raise

    def _build_rerank_prompt(
        self,
        candidates: List[PersonResult],
        person_hint: PersonHint,
        meeting_context: Dict[str, Any]
    ) -> str:
        """
        Build prompt for LLM re-ranking.

        Args:
            candidates: List of PersonResult objects
            person_hint: PersonHint for context
            meeting_context: Meeting context

        Returns:
            Formatted prompt string
        """
        # Extract meeting context
        meeting_subject = meeting_context.get("subject", "")
        meeting_company = meeting_context.get("company", "")

        # Build candidate list for prompt
        candidate_list = []
        for i, candidate in enumerate(candidates):
            candidate_list.append(
                f"{i+1}. {candidate.title}\n"
                f"   URL: {candidate.url}\n"
                f"   Confidence: {candidate.confidence:.2f}\n"
                f"   Source: {candidate.source}\n"
                f"   Matched: {', '.join(candidate.matched_anchors)}"
            )

        candidates_text = "\n\n".join(candidate_list)

        prompt = f"""You are helping to rank news articles about a person for a business meeting context.

PERSON CONTEXT:
- Name: {person_hint.name}
- Company: {person_hint.company or 'Unknown'}
- Domain: {person_hint.domain or 'Unknown'}
- Email: {person_hint.email or 'Unknown'}

MEETING CONTEXT:
- Subject: {meeting_subject}
- Company: {meeting_company}

CANDIDATE ARTICLES:
{candidates_text}

TASK:
Rank these articles from most relevant (1) to least relevant ({len(candidates)}) for this person in the context of this business meeting.

Consider:
- How likely is this article about the specific person (not someone else with the same name)?
- How relevant is this article to the business meeting context?
- How recent and credible is the information?

RESPONSE FORMAT:
Return only a JSON array with the ranking, like this:
[2, 1, 3, 4, 5]

Where the numbers correspond to the original candidate positions (1-based indexing)."""

        return prompt

    def _parse_llm_response(self, response: str, candidates: List[PersonResult]) -> List[PersonResult]:
        """
        Parse LLM response and re-rank candidates.

        Args:
            response: LLM response string
            candidates: Original list of candidates

        Returns:
            Re-ranked list of PersonResult objects
        """
        try:
            import json

            # Clean response - remove any markdown formatting
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            # Parse JSON array
            ranking = json.loads(response)

            if not isinstance(ranking, list):
                raise ValueError("Response is not a list")

            if len(ranking) != len(candidates):
                raise ValueError(f"Ranking length {len(ranking)} doesn't match candidates {len(candidates)}")

            # Validate ranking contains valid indices
            expected_indices = list(range(1, len(candidates) + 1))
            if sorted(ranking) != expected_indices:
                raise ValueError(f"Invalid ranking indices: {ranking}")

            # Re-rank candidates based on LLM ranking
            reranked = []
            for rank in ranking:
                # Convert from 1-based to 0-based indexing
                index = rank - 1
                reranked.append(candidates[index])

            return reranked

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}, response: {response}")
            # Return original order on parse error
            return candidates


def create_person_reranker() -> PersonReranker:
    """Create and configure a PersonReranker instance."""
    return PersonReranker()
