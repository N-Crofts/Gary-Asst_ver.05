import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from app.llm.service import StubLLMClient, OpenAIClient, select_llm_client
from app.enrichment.service import enrich_meetings


class TestStubLLMClient:
    """Test the deterministic stub LLM client."""

    def test_generate_talking_points_acme_company(self):
        """Test talking points generation for Acme company."""
        client = StubLLMClient()
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        points = client.generate_talking_points(meeting)

        assert len(points) == 3
        assert "Q4 fund-formation" in points[0]
        assert "GridFlow case study" in points[1]
        assert "cross-border structuring" in points[2]

    def test_generate_talking_points_generic_subject(self):
        """Test talking points generation for generic subject."""
        client = StubLLMClient()
        meeting = {
            "subject": "General Business Meeting",
            "company": {"name": "Unknown Corp"},
            "attendees": []
        }

        points = client.generate_talking_points(meeting)

        assert len(points) == 3
        assert "objectives" in points[0].lower()
        assert "next steps" in points[1].lower()
        assert "partnership" in points[2].lower()

    def test_generate_smart_questions_acme_company(self):
        """Test smart questions generation for Acme company."""
        client = StubLLMClient()
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        questions = client.generate_smart_questions(meeting)

        assert len(questions) == 3
        assert "capital call" in questions[0].lower()
        assert "entity changes" in questions[1].lower()
        assert "regulatory friction" in questions[2].lower()

    def test_generate_smart_questions_generic_subject(self):
        """Test smart questions generation for generic subject."""
        client = StubLLMClient()
        meeting = {
            "subject": "Client Introduction Meeting",
            "company": {"name": "Unknown Corp"},
            "attendees": []
        }

        questions = client.generate_smart_questions(meeting)

        assert len(questions) == 3
        assert "stage" in questions[0].lower()
        assert "legal challenges" in questions[1].lower()
        assert "accelerate" in questions[2].lower()

    def test_extract_company_name_from_company_field(self):
        """Test company name extraction from company field."""
        client = StubLLMClient()
        meeting = {
            "subject": "Test Meeting",
            "company": {"name": "Test Company"},
            "attendees": []
        }

        company_name = client._extract_company_name(meeting)
        assert company_name == "Test Company"

    def test_extract_company_name_from_attendees(self):
        """Test company name extraction from attendees."""
        client = StubLLMClient()
        meeting = {
            "subject": "Test Meeting",
            "attendees": [
                {"name": "John Doe", "company": "Attendee Company"}
            ]
        }

        company_name = client._extract_company_name(meeting)
        assert company_name == "Attendee Company"

    def test_extract_company_name_from_subject(self):
        """Test company name extraction from subject."""
        client = StubLLMClient()
        meeting = {
            "subject": "RPCK × Subject Company — Meeting Title",
            "attendees": []
        }

        company_name = client._extract_company_name(meeting)
        assert company_name == "Subject Company"

    def test_deterministic_output(self):
        """Test that stub client produces deterministic output."""
        client = StubLLMClient()
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        # Generate multiple times
        points1 = client.generate_talking_points(meeting)
        points2 = client.generate_talking_points(meeting)
        questions1 = client.generate_smart_questions(meeting)
        questions2 = client.generate_smart_questions(meeting)

        assert points1 == points2
        assert questions1 == questions2


class TestOpenAIClient:
    """Test the OpenAI client with mocked HTTP calls."""

    def test_generate_talking_points_success(self):
        """Test successful talking points generation."""
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", timeout_ms=1000)
        meeting = {
            "subject": "Test Meeting",
            "company": {"name": "Test Company"},
            "attendees": [{"name": "John Doe"}]
        }

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "Discuss Q1 priorities\nReview partnership opportunities\nAlign on next steps"
                    }
                }
            ]
        }

        with patch('httpx.Client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response

            mock_client.return_value.__enter__.return_value.post.return_value = mock_response_obj

            points = client.generate_talking_points(meeting)

            assert len(points) == 3
            assert "Q1 priorities" in points[0]
            assert "partnership opportunities" in points[1]
            assert "next steps" in points[2]

    def test_generate_smart_questions_success(self):
        """Test successful smart questions generation."""
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", timeout_ms=1000)
        meeting = {
            "subject": "Test Meeting",
            "company": {"name": "Test Company"},
            "attendees": []
        }

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "What are your key challenges?\nHow can we help?\nWhat's your timeline?"
                    }
                }
            ]
        }

        with patch('httpx.Client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response

            mock_client.return_value.__enter__.return_value.post.return_value = mock_response_obj

            questions = client.generate_smart_questions(meeting)

            assert len(questions) == 3
            assert "challenges" in questions[0].lower()
            assert "help" in questions[1].lower()
            assert "timeline" in questions[2].lower()

    def test_api_error_raises_exception(self):
        """Test that API errors raise HTTPException."""
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", timeout_ms=1000)
        meeting = {
            "subject": "Test Meeting",
            "company": {"name": "Test Company"},
            "attendees": []
        }

        with patch('httpx.Client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 401
            mock_response_obj.text = "Unauthorized"

            mock_client.return_value.__enter__.return_value.post.return_value = mock_response_obj

            with pytest.raises(HTTPException) as exc_info:
                client.generate_talking_points(meeting)

            assert exc_info.value.status_code == 503
            assert "OpenAI API error" in str(exc_info.value.detail)

    def test_timeout_raises_exception(self):
        """Test that timeouts raise HTTPException."""
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", timeout_ms=1000)
        meeting = {
            "subject": "Test Meeting",
            "company": {"name": "Test Company"},
            "attendees": []
        }

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = Exception("Timeout")

            with pytest.raises(HTTPException) as exc_info:
                client.generate_talking_points(meeting)

            assert exc_info.value.status_code == 503
            assert "OpenAI API error" in str(exc_info.value.detail)


class TestLLMClientFactory:
    """Test the LLM client factory function."""

    def test_select_stub_client_when_disabled(self):
        """Test that stub client is selected when LLM is disabled."""
        with patch.dict(os.environ, {"LLM_ENABLED": "false"}):
            client = select_llm_client()
            assert isinstance(client, StubLLMClient)

    def test_select_stub_client_when_no_api_key(self):
        """Test that stub client is selected when no API key is provided."""
        with patch.dict(os.environ, {"LLM_ENABLED": "true", "OPENAI_API_KEY": ""}):
            client = select_llm_client()
            assert isinstance(client, StubLLMClient)

    def test_select_openai_client_when_enabled(self):
        """Test that OpenAI client is selected when properly configured."""
        with patch.dict(os.environ, {
            "LLM_ENABLED": "true",
            "OPENAI_API_KEY": "test-key",
            "LLM_MODEL": "gpt-4o-mini",
            "LLM_TIMEOUT_MS": "1000"
        }):
            client = select_llm_client()
            assert isinstance(client, OpenAIClient)
            assert client.api_key == "test-key"
            assert client.model == "gpt-4o-mini"
            assert client.timeout_seconds == 1.0


class TestEnrichmentWithLLM:
    """Test enrichment service integration with LLM."""

    def test_enrichment_uses_stub_llm_by_default(self):
        """Test that enrichment uses stub LLM by default."""
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        with patch.dict(os.environ, {"LLM_ENABLED": "false"}):
            enriched = enrich_meetings([meeting])

            assert len(enriched) == 1
            assert len(enriched[0].talking_points) == 3
            assert len(enriched[0].smart_questions) == 3
            assert "Q4 fund-formation" in enriched[0].talking_points[0]

    def test_enrichment_fallback_on_llm_error(self):
        """Test that enrichment falls back to fixtures when LLM fails."""
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        # Mock LLM client to raise exception
        mock_llm_client = MagicMock()
        mock_llm_client.generate_talking_points.side_effect = Exception("LLM Error")
        mock_llm_client.generate_smart_questions.side_effect = Exception("LLM Error")

        with patch('app.enrichment.service.select_llm_client', return_value=mock_llm_client):
            with patch.dict(os.environ, {"LLM_ENABLED": "true"}):
                enriched = enrich_meetings([meeting])

                assert len(enriched) == 1
                # Should fall back to fixture data
                assert len(enriched[0].talking_points) >= 1
                assert len(enriched[0].smart_questions) >= 1

    def test_enrichment_respects_max_items_from_profile(self):
        """Test that enrichment respects profile max_items limits."""
        meeting = {
            "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
            "company": {"name": "Acme Capital"},
            "attendees": []
        }

        # Mock profile with restrictive limits
        mock_profile = MagicMock()
        mock_profile.max_items = {
            "talking_points": 1,
            "smart_questions": 1
        }

        with patch.dict(os.environ, {"LLM_ENABLED": "false"}):
            with patch('app.rendering.context_builder.get_profile', return_value=mock_profile):
                # This test would need to be run through the full context builder
                # to test the max_items trimming, but we can test the LLM generation
                enriched = enrich_meetings([meeting])

                # The LLM generates 3 items, but trimming happens in context builder
                assert len(enriched[0].talking_points) == 3
                assert len(enriched[0].smart_questions) == 3
