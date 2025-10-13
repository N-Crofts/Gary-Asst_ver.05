"""
Tests for Person Embeddings Similarity Boost

Tests the embedding similarity scoring functionality for person-news results.
Uses deterministic fake vectors for testing.
"""

import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from typing import List, Dict, Any

from app.people.embeddings import PersonEmbeddings, EmbeddingResult
from app.people.reranker import PersonResult
from app.people.normalizer import PersonHint
from app.llm.service import StubLLMClient, OpenAIClient


class TestPersonEmbeddings:
    """Test the PersonEmbeddings class."""

    def setup_method(self):
        """Set up test data."""
        self.sample_results = [
            PersonResult(
                title="John Smith CEO of Acme Corp",
                url="https://example.com/john-smith-ceo",
                confidence=0.8,
                source="name",
                matched_anchors=["John Smith", "CEO"],
                negative_signals=[]
            ),
            PersonResult(
                title="Acme Corp Expands Operations",
                url="https://example.com/acme-expands",
                confidence=0.7,
                source="site",
                matched_anchors=["Acme Corp"],
                negative_signals=[]
            ),
            PersonResult(
                title="Tech Industry News",
                url="https://example.com/tech-news",
                confidence=0.6,
                source="site",
                matched_anchors=["Tech"],
                negative_signals=[]
            )
        ]

        self.person_hint = PersonHint(
            name="John Smith",
            email="john.smith@acme.com",
            domain="acme.com",
            company="Acme Corp",
            co_attendee_domains=["techcorp.com"],
            keywords=["CEO", "founder"]
        )

        self.meeting_context = {
            "subject": "Q4 Strategy Meeting",
            "company": "Acme Corp"
        }

    def test_embeddings_initialization_disabled(self):
        """Test embeddings initialization when disabled."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "false"}):
            embeddings = PersonEmbeddings()
            assert not embeddings.enabled
            assert embeddings.provider == "openai"
            assert embeddings.similarity_bonus == 0.1

    def test_embeddings_initialization_enabled(self):
        """Test embeddings initialization when enabled."""
        with patch.dict(os.environ, {
            "PEOPLE_EMBEDDINGS": "true",
            "EMBEDDINGS_PROVIDER": "openai",
            "PEOPLE_EMBEDDINGS_BONUS": "0.15"
        }):
            embeddings = PersonEmbeddings()
            assert embeddings.enabled
            assert embeddings.provider == "openai"
            assert embeddings.similarity_bonus == 0.15

    def test_boost_results_disabled(self):
        """Test that results are returned unchanged when embeddings disabled."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "false"}):
            embeddings = PersonEmbeddings()
            result = embeddings.boost_results_with_similarity(
                self.sample_results, self.person_hint, self.meeting_context
            )
            assert result == self.sample_results

    def test_boost_results_empty_list(self):
        """Test boosting with empty results list."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()
            result = embeddings.boost_results_with_similarity(
                [], self.person_hint, self.meeting_context
            )
            assert result == []

    def test_boost_results_with_stub_llm(self):
        """Test boosting results with stub LLM client."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            # Mock the LLM client to return deterministic embeddings
            mock_client = StubLLMClient()
            embeddings.llm_client = mock_client

            result = embeddings.boost_results_with_similarity(
                self.sample_results, self.person_hint, self.meeting_context
            )

            # Should have same number of results
            assert len(result) == len(self.sample_results)

            # All results should have boosted confidence
            for i, boosted_result in enumerate(result):
                original_result = self.sample_results[i]
                assert boosted_result.title == original_result.title
                assert boosted_result.url == original_result.url
                assert boosted_result.source == original_result.source
                assert boosted_result.matched_anchors == original_result.matched_anchors
                assert boosted_result.negative_signals == original_result.negative_signals
                # Confidence should be boosted (but not exceed 1.0)
                assert boosted_result.confidence >= original_result.confidence
                assert boosted_result.confidence <= 1.0

    def test_build_profile_text(self):
        """Test profile text building."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            profile_text = embeddings._build_profile_text(self.person_hint, self.meeting_context)

            assert "Person: John Smith" in profile_text
            assert "Company: Acme Corp" in profile_text
            assert "Domain: acme.com" in profile_text
            assert "Roles/Keywords: CEO, founder" in profile_text
            assert "Meeting: Q4 Strategy Meeting" in profile_text
            assert "Meeting Company: Acme Corp" in profile_text

    def test_extract_article_snippet(self):
        """Test article snippet extraction."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            snippet = embeddings._extract_article_snippet(self.sample_results[0])

            assert "John Smith CEO of Acme Corp" in snippet
            assert "Keywords: John Smith, CEO" in snippet

    def test_cosine_similarity_identical_vectors(self):
        """Test cosine similarity with identical vectors."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            vec = np.array([1.0, 0.0, 0.0])
            similarity = embeddings._cosine_similarity(vec, vec)
            assert abs(similarity - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        """Test cosine similarity with orthogonal vectors."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            vec1 = np.array([1.0, 0.0, 0.0])
            vec2 = np.array([0.0, 1.0, 0.0])
            similarity = embeddings._cosine_similarity(vec1, vec2)
            assert abs(similarity - 0.0) < 1e-6

    def test_cosine_similarity_opposite_vectors(self):
        """Test cosine similarity with opposite vectors."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            vec1 = np.array([1.0, 0.0, 0.0])
            vec2 = np.array([-1.0, 0.0, 0.0])
            similarity = embeddings._cosine_similarity(vec1, vec2)
            assert abs(similarity - (-1.0)) < 1e-6

    def test_cosine_similarity_zero_vectors(self):
        """Test cosine similarity with zero vectors."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            vec1 = np.array([0.0, 0.0, 0.0])
            vec2 = np.array([1.0, 0.0, 0.0])
            similarity = embeddings._cosine_similarity(vec1, vec2)
            assert similarity == 0.0

    def test_boost_with_embedding_failure(self):
        """Test boosting when embedding generation fails."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            # Mock LLM client to return None (embedding failure)
            mock_client = MagicMock()
            mock_client.get_embedding.return_value = None
            embeddings.llm_client = mock_client

            result = embeddings.boost_results_with_similarity(
                self.sample_results, self.person_hint, self.meeting_context
            )

            # Should return original results unchanged
            assert result == self.sample_results

    def test_boost_with_partial_embedding_failure(self):
        """Test boosting when some embeddings fail."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            # Mock LLM client to fail for some embeddings
            mock_client = MagicMock()
            mock_client.get_embedding.side_effect = [
                np.array([1.0, 0.0, 0.0]),  # Success for profile
                np.array([0.8, 0.6, 0.0]),  # Success for first article (positive similarity)
                None,  # Failure for second article
                np.array([0.9, 0.1, 0.0])   # Success for third article (positive similarity)
            ]
            embeddings.llm_client = mock_client

            result = embeddings.boost_results_with_similarity(
                self.sample_results, self.person_hint, self.meeting_context
            )

            # Should have same number of results
            assert len(result) == len(self.sample_results)

            # First and third results should be boosted, second unchanged
            assert result[0].confidence > self.sample_results[0].confidence
            assert result[1].confidence == self.sample_results[1].confidence
            assert result[2].confidence > self.sample_results[2].confidence


class TestStubLLMClientEmbeddings:
    """Test the StubLLMClient embedding functionality."""

    def test_stub_llm_get_embedding_deterministic(self):
        """Test that stub LLM returns deterministic embeddings."""
        client = StubLLMClient()

        # Same text should return same embedding
        embedding1 = client.get_embedding("test text")
        embedding2 = client.get_embedding("test text")

        assert embedding1 is not None
        assert embedding2 is not None
        assert np.array_equal(embedding1, embedding2)

        # Different text should return different embedding
        embedding3 = client.get_embedding("different text")
        assert not np.array_equal(embedding1, embedding3)

    def test_stub_llm_embedding_dimensions(self):
        """Test that stub LLM returns correct embedding dimensions."""
        client = StubLLMClient()

        embedding = client.get_embedding("test text")
        assert embedding.shape == (1536,)  # OpenAI text-embedding-3-small dimensions

    def test_stub_llm_embedding_range(self):
        """Test that stub LLM embeddings are in reasonable range."""
        client = StubLLMClient()

        embedding = client.get_embedding("test text")

        # Values should be in reasonable range
        assert np.all(embedding >= -1.0)
        assert np.all(embedding <= 1.0)

        # Should not be all zeros
        assert not np.all(embedding == 0.0)


class TestOpenAIClientEmbeddings:
    """Test the OpenAIClient embedding functionality."""

    def test_openai_client_embedding_method_exists(self):
        """Test that OpenAIClient has get_embedding method."""
        client = OpenAIClient("fake-key")
        assert hasattr(client, 'get_embedding')
        assert callable(getattr(client, 'get_embedding'))

    @patch('httpx.Client')
    def test_openai_client_embedding_success(self, mock_client_class):
        """Test successful embedding generation."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3] * 512}]  # 1536 dimensions
        }
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        client = OpenAIClient("fake-key")
        embedding = client.get_embedding("test text")

        assert embedding is not None
        assert embedding.shape == (1536,)
        assert embedding.dtype == np.float32

    @patch('httpx.Client')
    def test_openai_client_embedding_failure(self, mock_client_class):
        """Test embedding generation failure."""
        # Mock API failure
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("API Error")
        mock_client_class.return_value.__enter__.return_value = mock_client

        client = OpenAIClient("fake-key")
        embedding = client.get_embedding("test text")

        assert embedding is None


class TestEmbeddingsIntegration:
    """Test embeddings integration with people resolver."""

    def test_embeddings_integration_disabled(self):
        """Test embeddings integration when disabled."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "false"}):
            from app.people.resolver import PeopleResolver

            resolver = PeopleResolver()
            assert not resolver.embeddings.enabled

    def test_embeddings_integration_enabled(self):
        """Test embeddings integration when enabled."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            from app.people.resolver import PeopleResolver

            resolver = PeopleResolver()
            assert resolver.embeddings.enabled

    def test_embeddings_with_different_configurations(self):
        """Test embeddings with different configuration values."""
        configs = [
            {"PEOPLE_EMBEDDINGS": "true", "PEOPLE_EMBEDDINGS_BONUS": "0.05"},
            {"PEOPLE_EMBEDDINGS": "true", "PEOPLE_EMBEDDINGS_BONUS": "0.2"},
            {"PEOPLE_EMBEDDINGS": "true", "EMBEDDINGS_PROVIDER": "openai"},
        ]

        for config in configs:
            with patch.dict(os.environ, config):
                embeddings = PersonEmbeddings()
                assert embeddings.enabled

                if "PEOPLE_EMBEDDINGS_BONUS" in config:
                    expected_bonus = float(config["PEOPLE_EMBEDDINGS_BONUS"])
                    assert embeddings.similarity_bonus == expected_bonus


class TestEmbeddingsEdgeCases:
    """Test edge cases for embeddings functionality."""

    def setup_method(self):
        """Set up test data."""
        self.sample_results = [
            PersonResult(
                title="John Smith CEO of Acme Corp",
                url="https://example.com/john-smith-ceo",
                confidence=0.8,
                source="name",
                matched_anchors=["John Smith", "CEO"],
                negative_signals=[]
            )
        ]

        self.person_hint = PersonHint(
            name="John Smith",
            email="john.smith@acme.com",
            domain="acme.com",
            company="Acme Corp",
            co_attendee_domains=["techcorp.com"],
            keywords=["CEO", "founder"]
        )

        self.meeting_context = {
            "subject": "Q4 Strategy Meeting",
            "company": "Acme Corp"
        }

    def test_embeddings_with_single_result(self):
        """Test embeddings with single result."""
        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            # Mock LLM client
            mock_client = StubLLMClient()
            embeddings.llm_client = mock_client

            result = embeddings.boost_results_with_similarity(
                self.sample_results, self.person_hint, self.meeting_context
            )

            assert len(result) == 1
            assert result[0].confidence >= self.sample_results[0].confidence

    def test_embeddings_with_high_confidence_results(self):
        """Test embeddings with results that already have high confidence."""
        high_confidence_results = [
            PersonResult(
                title="Perfect Match",
                url="https://example.com/perfect",
                confidence=0.95,
                source="name",
                matched_anchors=["Perfect", "Match"],
                negative_signals=[]
            )
        ]

        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            # Mock LLM client
            mock_client = StubLLMClient()
            embeddings.llm_client = mock_client

            result = embeddings.boost_results_with_similarity(
                high_confidence_results, self.person_hint, self.meeting_context
            )

            # Confidence should be capped at 1.0
            assert result[0].confidence <= 1.0
            assert result[0].confidence >= high_confidence_results[0].confidence

    def test_embeddings_with_special_characters(self):
        """Test embeddings with special characters in text."""
        special_results = [
            PersonResult(
                title="José María O'Connor-Smith & Associates",
                url="https://example.com/special",
                confidence=0.7,
                source="name",
                matched_anchors=["José", "O'Connor"],
                negative_signals=[]
            )
        ]

        special_person = PersonHint(
            name="José María O'Connor-Smith",
            email="jose.oconnor@acme-corp.com",
            domain="acme-corp.com",
            company="Acme-Corp & Associates",
            co_attendee_domains=["tech-corp.com"],
            keywords=["CEO", "founder", "AI/ML"]
        )

        with patch.dict(os.environ, {"PEOPLE_EMBEDDINGS": "true"}):
            embeddings = PersonEmbeddings()

            # Mock LLM client
            mock_client = StubLLMClient()
            embeddings.llm_client = mock_client

            result = embeddings.boost_results_with_similarity(
                special_results, special_person, self.meeting_context
            )

            assert len(result) == 1
            assert result[0].confidence >= special_results[0].confidence
