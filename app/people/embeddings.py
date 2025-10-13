"""
Embeddings Similarity Boost for Person-News Results

Implements optional semantic similarity scoring between article snippets and person/company profiles
to boost relevant results in person-news matching.
"""

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.people.normalizer import PersonHint
from app.llm.service import LLMClient, select_llm_client

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding similarity scoring."""
    result: 'PersonResult'
    similarity_score: float
    profile_text: str
    article_snippet: str


class PersonEmbeddings:
    """
    Computes semantic similarity between person-news articles and person/company profiles.
    """

    def __init__(self):
        self.enabled = os.getenv("PEOPLE_EMBEDDINGS", "false").lower() == "true"
        self.provider = os.getenv("EMBEDDINGS_PROVIDER", "openai")
        self.similarity_bonus = float(os.getenv("PEOPLE_EMBEDDINGS_BONUS", "0.1"))
        self.llm_client: LLMClient = select_llm_client()

        logger.info(f"PersonEmbeddings initialized: enabled={self.enabled}, provider={self.provider}, bonus={self.similarity_bonus}")

    def boost_results_with_similarity(
        self,
        results: List['PersonResult'],
        person_hint: PersonHint,
        meeting_context: Dict[str, Any]
    ) -> List['PersonResult']:
        """
        Boost results with embedding similarity scores.

        Args:
            results: List of PersonResult objects to boost
            person_hint: PersonHint with person/company context
            meeting_context: Meeting context for additional profile information

        Returns:
            List of PersonResult objects with boosted confidence scores
        """
        if not self.enabled or not results:
            return results

        try:
            # Generate profile text for the person/company
            profile_text = self._build_profile_text(person_hint, meeting_context)

            # Get profile embedding
            profile_embedding = self._get_embedding(profile_text)
            if profile_embedding is None:
                logger.warning("Failed to get profile embedding, skipping similarity boost")
                return results

            boosted_results = []

            for result in results:
                # Extract article snippet
                article_snippet = self._extract_article_snippet(result)

                # Get article embedding
                article_embedding = self._get_embedding(article_snippet)
                if article_embedding is None:
                    # Keep original result if embedding fails
                    boosted_results.append(result)
                    continue

                # Calculate cosine similarity
                similarity = self._cosine_similarity(profile_embedding, article_embedding)

                # Only apply positive similarity as bonus (clamp negative similarities to 0)
                positive_similarity = max(0.0, similarity)

                # Apply similarity bonus to confidence
                boosted_confidence = min(1.0, result.confidence + (positive_similarity * self.similarity_bonus))

                # Create boosted result
                boosted_result = PersonResult(
                    title=result.title,
                    url=result.url,
                    confidence=boosted_confidence,
                    source=result.source,
                    matched_anchors=result.matched_anchors,
                    negative_signals=result.negative_signals
                )

                boosted_results.append(boosted_result)

                logger.debug(f"Boosted {result.title[:50]}... similarity={similarity:.3f}, confidence: {result.confidence:.3f} -> {boosted_confidence:.3f}")

            return boosted_results

        except Exception as e:
            logger.error(f"Error in embedding similarity boost: {e}")
            return results

    def _build_profile_text(self, person_hint: PersonHint, meeting_context: Dict[str, Any]) -> str:
        """Build a profile text from person hint and meeting context."""
        profile_parts = []

        # Add person name
        if person_hint.name:
            profile_parts.append(f"Person: {person_hint.name}")

        # Add company information
        if person_hint.company:
            profile_parts.append(f"Company: {person_hint.company}")

        # Add domain information
        if person_hint.domain:
            profile_parts.append(f"Domain: {person_hint.domain}")

        # Add keywords/roles
        if person_hint.keywords:
            profile_parts.append(f"Roles/Keywords: {', '.join(person_hint.keywords)}")

        # Add meeting context
        if meeting_context.get("subject"):
            profile_parts.append(f"Meeting: {meeting_context['subject']}")

        if meeting_context.get("company"):
            profile_parts.append(f"Meeting Company: {meeting_context['company']}")

        return " | ".join(profile_parts)

    def _extract_article_snippet(self, result: 'PersonResult') -> str:
        """Extract a snippet from the article result for embedding."""
        # Use title as the primary snippet
        snippet = result.title

        # Add matched anchors for context
        if result.matched_anchors:
            snippet += f" | Keywords: {', '.join(result.matched_anchors)}"

        return snippet

    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for text using the configured provider."""
        try:
            if self.provider == "openai":
                return self.llm_client.get_embedding(text)
            else:
                logger.warning(f"Unsupported embeddings provider: {self.provider}")
                return None
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            # Normalize vectors
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            # Calculate cosine similarity
            similarity = np.dot(vec1, vec2) / (norm1 * norm2)
            return float(similarity)

        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0


# Import PersonResult here to avoid circular imports
from app.people.reranker import PersonResult
