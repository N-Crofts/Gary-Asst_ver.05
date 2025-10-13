"""
Tests for LLM Re-ranker functionality.

Tests the optional LLM re-ranking of person-news results with deterministic stubs.
"""

import os
import json
import time
from unittest.mock import patch, MagicMock
import pytest

from app.people.reranker import PersonReranker, RerankResult
from app.people.resolver import PersonResult
from app.people.normalizer import PersonHint
from app.llm.service import StubLLMClient, OpenAIClient


class TestPersonReranker:
    """Test the PersonReranker class."""

    def setup_method(self):
        """Set up test environment."""
        self.person_hint = PersonHint(
            name="John Smith",
            email="john.smith@acme.com",
            domain="acme.com",
            company="Acme Corp",
            co_attendee_domains=["techcorp.com"],
            keywords=["CEO", "founder"]
        )

        self.meeting_context = {
            "subject": "RPCK × Acme Corp — Portfolio Strategy Check-in",
            "company": "Acme Corp"
        }

        self.sample_results = [
            PersonResult(
                title="Acme Corp CEO John Smith Announces New Funding Round",
                url="https://example.com/acme-funding",
                confidence=0.85,
                source="name",
                matched_anchors=["acme.com", "Acme Corp"]
            ),
            PersonResult(
                title="John Smith from TechCorp Discusses AI Strategy",
                url="https://example.com/techcorp-ai",
                confidence=0.75,
                source="name",
                matched_anchors=["John Smith"]
            ),
            PersonResult(
                title="Acme Corp Expands Operations in Europe",
                url="https://example.com/acme-europe",
                confidence=0.80,
                source="site",
                matched_anchors=["acme.com"]
            )
        ]

    def test_reranker_initialization_disabled(self):
        """Test re-ranker initialization when disabled."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "false"}):
            reranker = PersonReranker()
            assert not reranker.enabled
            assert reranker.timeout_seconds == 2.0
            assert reranker.max_candidates == 5

    def test_reranker_initialization_enabled(self):
        """Test re-ranker initialization when enabled."""
        with patch.dict(os.environ, {
            "PEOPLE_RERANK_LLM": "true",
            "PEOPLE_RERANK_TIMEOUT_MS": "3000",
            "PEOPLE_RERANK_MAX_CANDIDATES": "3"
        }):
            reranker = PersonReranker()
            assert reranker.enabled
            assert reranker.timeout_seconds == 3.0
            assert reranker.max_candidates == 3

    def test_rerank_results_disabled(self):
        """Test that re-ranking returns original order when disabled."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "false"}):
            reranker = PersonReranker()
            result = reranker.rerank_results(self.sample_results, self.person_hint, self.meeting_context)
            assert result == self.sample_results

    def test_rerank_results_empty_list(self):
        """Test re-ranking with empty results list."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()
            result = reranker.rerank_results([], self.person_hint, self.meeting_context)
            assert result == []

    def test_rerank_results_with_stub_llm(self):
        """Test re-ranking with stub LLM client (deterministic)."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()
            # Stub LLM client should return original order
            result = reranker.rerank_results(self.sample_results, self.person_hint, self.meeting_context)
            assert result == self.sample_results

    def test_rerank_results_limits_candidates(self):
        """Test that re-ranking limits candidates to max_candidates."""
        with patch.dict(os.environ, {
            "PEOPLE_RERANK_LLM": "true",
            "PEOPLE_RERANK_MAX_CANDIDATES": "2"
        }):
            reranker = PersonReranker()
            result = reranker.rerank_results(self.sample_results, self.person_hint, self.meeting_context)
            # Should return all results (stub LLM returns original order)
            assert len(result) == 3
            assert result == self.sample_results

    def test_rerank_results_with_many_candidates(self):
        """Test re-ranking with more candidates than max_candidates."""
        many_results = self.sample_results * 3  # 9 results

        with patch.dict(os.environ, {
            "PEOPLE_RERANK_LLM": "true",
            "PEOPLE_RERANK_MAX_CANDIDATES": "3"
        }):
            reranker = PersonReranker()
            result = reranker.rerank_results(many_results, self.person_hint, self.meeting_context)
            # Should return all results (stub LLM returns original order)
            assert len(result) == 9
            assert result == many_results

    def test_build_rerank_prompt(self):
        """Test prompt building for LLM re-ranking."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()
            prompt = reranker._build_rerank_prompt(self.sample_results, self.person_hint, self.meeting_context)

            # Check that prompt contains expected elements
            assert "John Smith" in prompt
            assert "acme.com" in prompt
            assert "Acme Corp" in prompt
            assert "Portfolio Strategy Check-in" in prompt
            assert "CANDIDATE ARTICLES:" in prompt
            assert "1. Acme Corp CEO John Smith Announces New Funding Round" in prompt
            assert "2. John Smith from TechCorp Discusses AI Strategy" in prompt
            assert "3. Acme Corp Expands Operations in Europe" in prompt
            assert "RESPONSE FORMAT:" in prompt
            assert "[2, 1, 3, 4, 5]" in prompt

    def test_parse_llm_response_valid(self):
        """Test parsing valid LLM response."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Test valid JSON response
            response = "[2, 1, 3]"
            result = reranker._parse_llm_response(response, self.sample_results)

            # Should re-rank: original [0, 1, 2] -> [1, 0, 2]
            expected = [self.sample_results[1], self.sample_results[0], self.sample_results[2]]
            assert result == expected

    def test_parse_llm_response_with_markdown(self):
        """Test parsing LLM response with markdown formatting."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Test response with markdown
            response = "```json\n[3, 1, 2]\n```"
            result = reranker._parse_llm_response(response, self.sample_results)

            # Should re-rank: original [0, 1, 2] -> [2, 0, 1]
            expected = [self.sample_results[2], self.sample_results[0], self.sample_results[1]]
            assert result == expected

    def test_parse_llm_response_invalid_json(self):
        """Test parsing invalid LLM response falls back to original order."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Test invalid JSON response
            response = "invalid json response"
            result = reranker._parse_llm_response(response, self.sample_results)

            # Should return original order
            assert result == self.sample_results

    def test_parse_llm_response_wrong_length(self):
        """Test parsing LLM response with wrong length falls back to original order."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Test response with wrong length
            response = "[1, 2]"  # Should be [1, 2, 3] for 3 candidates
            result = reranker._parse_llm_response(response, self.sample_results)

            # Should return original order
            assert result == self.sample_results

    def test_parse_llm_response_invalid_indices(self):
        """Test parsing LLM response with invalid indices falls back to original order."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Test response with invalid indices
            response = "[1, 2, 4]"  # 4 is out of range for 3 candidates
            result = reranker._parse_llm_response(response, self.sample_results)

            # Should return original order
            assert result == self.sample_results

    def test_rerank_with_timeout(self):
        """Test re-ranking with timeout."""
        with patch.dict(os.environ, {
            "PEOPLE_RERANK_LLM": "true",
            "PEOPLE_RERANK_TIMEOUT_MS": "1"  # Very short timeout
        }):
            reranker = PersonReranker()

            # Mock LLM client to simulate slow response
            mock_llm = MagicMock()
            mock_llm.rerank_person_results.side_effect = lambda x: time.sleep(2) or "[1, 2, 3]"
            reranker.llm_client = mock_llm

            # Should fall back to original order on timeout
            result = reranker.rerank_results(self.sample_results, self.person_hint, self.meeting_context)
            assert result == self.sample_results

    def test_rerank_with_llm_error(self):
        """Test re-ranking with LLM error falls back to original order."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Mock LLM client to raise exception
            mock_llm = MagicMock()
            mock_llm.rerank_person_results.side_effect = Exception("LLM API error")
            reranker.llm_client = mock_llm

            # Should fall back to original order on error
            result = reranker.rerank_results(self.sample_results, self.person_hint, self.meeting_context)
            assert result == self.sample_results


class TestStubLLMClientRerank:
    """Test the StubLLMClient re-ranking functionality."""

    def test_stub_llm_rerank_simple(self):
        """Test stub LLM client re-ranking with simple prompt."""
        client = StubLLMClient()

        prompt = """
CANDIDATE ARTICLES:
1. Article 1
2. Article 2
3. Article 3
"""
        result = client.rerank_person_results(prompt)
        assert result == "[1, 2, 3]"

    def test_stub_llm_rerank_complex(self):
        """Test stub LLM client re-ranking with complex prompt."""
        client = StubLLMClient()

        prompt = """
PERSON CONTEXT:
- Name: John Smith

CANDIDATE ARTICLES:
1. John Smith CEO of Acme Corp
2. John Smith from TechCorp
3. Acme Corp Expands Operations
4. TechCorp AI Strategy
5. John Smith Interview

TASK:
Rank these articles...
"""
        result = client.rerank_person_results(prompt)
        assert result == "[1, 2, 3, 4, 5]"

    def test_stub_llm_rerank_no_candidates(self):
        """Test stub LLM client re-ranking with no candidates."""
        client = StubLLMClient()

        prompt = """
PERSON CONTEXT:
- Name: John Smith

CANDIDATE ARTICLES:

TASK:
Rank these articles...
"""
        result = client.rerank_person_results(prompt)
        assert result == "[1]"


class TestOpenAIClientRerank:
    """Test the OpenAIClient re-ranking functionality."""

    def test_openai_client_rerank_method_exists(self):
        """Test that OpenAIClient has rerank_person_results method."""
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", timeout_ms=1000)
        assert hasattr(client, 'rerank_person_results')
        assert callable(client.rerank_person_results)

    def test_openai_client_rerank_calls_string_method(self):
        """Test that OpenAIClient rerank calls the string method."""
        with patch.object(OpenAIClient, '_call_openai_string') as mock_call:
            client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", timeout_ms=1000)
            mock_call.return_value = "[2, 1, 3]"

            result = client.rerank_person_results("test prompt")

            mock_call.assert_called_once_with("test prompt")
            assert result == "[2, 1, 3]"


class TestRerankerIntegration:
    """Test re-ranker integration with people resolver."""

    def test_reranker_integration_disabled(self):
        """Test that re-ranker integration works when disabled."""
        from app.people.resolver import PeopleResolver

        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "PEOPLE_RERANK_LLM": "false"
        }):
            resolver = PeopleResolver()
            assert not resolver.reranker.enabled

    def test_reranker_integration_enabled(self):
        """Test that re-ranker integration works when enabled."""
        from app.people.resolver import PeopleResolver

        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "PEOPLE_RERANK_LLM": "true"
        }):
            resolver = PeopleResolver()
            assert resolver.reranker.enabled

    def test_reranker_with_different_configurations(self):
        """Test re-ranker with different configuration combinations."""
        from app.people.resolver import PeopleResolver

        # Test with custom timeout and max candidates
        with patch.dict(os.environ, {
            "PEOPLE_NEWS_ENABLED": "true",
            "PEOPLE_RERANK_LLM": "true",
            "PEOPLE_RERANK_TIMEOUT_MS": "5000",
            "PEOPLE_RERANK_MAX_CANDIDATES": "10"
        }):
            resolver = PeopleResolver()
            assert resolver.reranker.enabled
            assert resolver.reranker.timeout_seconds == 5.0
            assert resolver.reranker.max_candidates == 10


class TestRerankerEdgeCases:
    """Test edge cases for the re-ranker."""

    def setup_method(self):
        """Set up test data."""
        self.sample_results = [
            PersonResult(
                title="John Smith CEO of Acme Corp",
                url="https://example.com/john-smith-ceo",
                confidence=0.9,
                source="name",
                matched_anchors=["John Smith", "CEO"]
            ),
            PersonResult(
                title="Acme Corp Expands Operations",
                url="https://example.com/acme-expands",
                confidence=0.7,
                source="site",
                matched_anchors=["Acme Corp"]
            ),
            PersonResult(
                title="Tech Industry News",
                url="https://example.com/tech-news",
                confidence=0.5,
                source="site",
                matched_anchors=["Tech"]
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

    def test_reranker_with_single_candidate(self):
        """Test re-ranking with single candidate."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            single_result = [self.sample_results[0]]
            result = reranker.rerank_results(single_result, self.person_hint, self.meeting_context)

            # Should return the single result
            assert result == single_result

    def test_reranker_with_duplicate_results(self):
        """Test re-ranking with duplicate results."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Create duplicate results
            duplicate_results = self.sample_results + self.sample_results
            result = reranker.rerank_results(duplicate_results, self.person_hint, self.meeting_context)

            # Should return all results (stub LLM returns original order)
            assert len(result) == 6
            assert result == duplicate_results

    def test_reranker_prompt_with_special_characters(self):
        """Test re-ranking prompt with special characters in person/meeting data."""
        with patch.dict(os.environ, {"PEOPLE_RERANK_LLM": "true"}):
            reranker = PersonReranker()

            # Person with special characters
            special_person = PersonHint(
                name="José María O'Connor-Smith",
                email="jose.oconnor@acme-corp.com",
                domain="acme-corp.com",
                company="Acme-Corp & Associates",
                co_attendee_domains=["tech-corp.com"],
                keywords=["CEO", "founder", "AI/ML"]
            )

            special_meeting = {
                "subject": "RPCK × Acme-Corp & Associates — Q4 2024 Strategy",
                "company": "Acme-Corp & Associates"
            }

            prompt = reranker._build_rerank_prompt(self.sample_results, special_person, special_meeting)

            # Should handle special characters properly
            assert "José María O'Connor-Smith" in prompt
            assert "acme-corp.com" in prompt
            assert "Acme-Corp & Associates" in prompt
            assert "Q4 2024 Strategy" in prompt
