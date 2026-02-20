import os
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import httpx
import numpy as np
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate_talking_points(self, meeting: Dict[str, Any]) -> List[str]:
        """Generate talking points for a meeting."""
        pass

    @abstractmethod
    def generate_smart_questions(self, meeting: Dict[str, Any]) -> List[str]:
        """Generate smart questions for a meeting."""
        pass

    @abstractmethod
    def rerank_person_results(self, prompt: str) -> str:
        """Re-rank person-news results using LLM."""
        pass

    @abstractmethod
    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding vector for text."""
        pass


class StubLLMClient(LLMClient):
    """Stub LLM client for testing and when LLM is disabled. Returns no placeholder filler."""

    def generate_talking_points(self, meeting: Dict[str, Any]) -> List[str]:
        """Return empty list; no hardcoded placeholder content."""
        return []

    def generate_smart_questions(self, meeting: Dict[str, Any]) -> List[str]:
        """Return empty list; no hardcoded placeholder content."""
        return []

    def rerank_person_results(self, prompt: str) -> str:
        """Return deterministic ranking for testing."""
        # Extract number of candidates from prompt
        lines = prompt.split('\n')
        candidate_count = 0
        in_candidates_section = False

        for line in lines:
            line = line.strip()
            if line.startswith('CANDIDATE ARTICLES:'):
                in_candidates_section = True
                continue

            if in_candidates_section:
                # Look for numbered candidates (1., 2., etc.)
                if line and line[0].isdigit() and '.' in line:
                    candidate_count += 1
                elif line and not line.startswith(' ') and not line.startswith('TASK:'):
                    # End of candidates section
                    break

        if candidate_count == 0:
            return "[1]"

        # Return original order for stub client
        return str(list(range(1, candidate_count + 1)))

    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Return deterministic fake embedding for testing."""
        # Create a deterministic fake embedding based on text hash
        import hashlib

        # Use text hash to create deterministic vector
        text_hash = hashlib.md5(text.encode()).hexdigest()

        # Convert hash to deterministic vector (1536 dimensions like OpenAI text-embedding-3-small)
        vector = np.zeros(1536)
        for i, char in enumerate(text_hash[:16]):  # Use first 16 chars of hash
            # Map hex char to float in range [-1, 1]
            val = (int(char, 16) - 7.5) / 7.5
            # Distribute across vector dimensions
            for j in range(96):  # 1536 / 16 = 96
                vector[i * 96 + j] = val * (0.1 ** (j % 3))  # Decay factor

        return vector

    def _extract_company_name(self, meeting: Dict[str, Any]) -> str:
        """Extract company name from meeting data."""
        # Check company field first
        company = meeting.get("company")
        if isinstance(company, dict) and company.get("name"):
            return company["name"]

        # Check attendees for company names
        attendees = meeting.get("attendees", [])
        for attendee in attendees:
            if isinstance(attendee, dict) and attendee.get("company"):
                return attendee["company"]

        # Fall back to subject parsing
        subject = meeting.get("subject", "")
        if "×" in subject:
            # Format: "RPCK × Company Name — Meeting"
            parts = subject.split("×")
            if len(parts) > 1:
                company_part = parts[1].split("—")[0].strip()
                return company_part

        return ""


class OpenAIClient(LLMClient):
    """OpenAI API client for generating talking points and questions."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout_ms: int = 800):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_ms / 1000.0
        self.base_url = "https://api.openai.com/v1"

    def generate_talking_points(self, meeting: Dict[str, Any]) -> List[str]:
        """Generate talking points using OpenAI API."""
        prompt = self._build_talking_points_prompt(meeting)
        return self._call_openai(prompt, "talking points")

    def generate_smart_questions(self, meeting: Dict[str, Any]) -> List[str]:
        """Generate smart questions using OpenAI API."""
        prompt = self._build_questions_prompt(meeting)
        return self._call_openai(prompt, "questions")

    def _build_talking_points_prompt(self, meeting: Dict[str, Any]) -> str:
        """Build prompt for talking points generation."""
        subject = meeting.get("subject", "")
        company_name = self._extract_company_name(meeting)
        attendees = meeting.get("attendees", [])

        attendee_info = ""
        if attendees:
            attendee_names = [a.get("name", "") for a in attendees if isinstance(a, dict)]
            attendee_info = f"Attendees: {', '.join(attendee_names)}"

        return f"""Generate 3 concise, action-oriented talking points for this meeting:

Meeting: {subject}
Company: {company_name}
{attendee_info}

Focus on:
- Specific business outcomes to achieve
- Legal/counsel needs to discuss
- Partnership opportunities to explore

Return only the 3 talking points, one per line, without numbering or bullets."""

    def _build_questions_prompt(self, meeting: Dict[str, Any]) -> str:
        """Build prompt for smart questions generation."""
        subject = meeting.get("subject", "")
        company_name = self._extract_company_name(meeting)

        return f"""Generate 3 insightful questions for this meeting:

Meeting: {subject}
Company: {company_name}

Focus on:
- Strategic business insights
- Legal/compliance challenges
- Growth opportunities

Return only the 3 questions, one per line, without numbering or bullets."""

    def _call_openai(self, prompt: str, content_type: str) -> List[str]:
        """Make API call to OpenAI with timeout and error handling."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    # Parse response into list of items
                    items = [line.strip() for line in content.split('\n') if line.strip()]
                    return items[:3]  # Limit to 3 items
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"OpenAI API error: {response.status_code} {response.text}"
                    )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=503,
                detail=f"OpenAI API timeout after {self.timeout_seconds}s"
            )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"OpenAI API error: {str(e)}"
            )

    def _call_openai_string(self, prompt: str) -> str:
        """Make API call to OpenAI and return raw string response."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"OpenAI API error: {response.status_code} {response.text}"
                    )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=503,
                detail=f"OpenAI API timeout after {self.timeout_seconds}s"
            )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"OpenAI API error: {str(e)}"
            )

    def rerank_person_results(self, prompt: str) -> str:
        """Re-rank person results using OpenAI API."""
        return self._call_openai_string(prompt)

    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding vector using OpenAI API."""
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "text-embedding-3-small",
                        "input": text
                    }
                )
                response.raise_for_status()
                data = response.json()

                # Extract embedding vector
                embedding = data["data"][0]["embedding"]
                return np.array(embedding, dtype=np.float32)

        except Exception as e:
            logger.error(f"Error getting embedding from OpenAI: {e}")
            return None

    def _extract_company_name(self, meeting: Dict[str, Any]) -> str:
        """Extract company name from meeting data."""
        # Check company field first
        company = meeting.get("company")
        if isinstance(company, dict) and company.get("name"):
            return company["name"]

        # Check attendees for company names
        attendees = meeting.get("attendees", [])
        for attendee in attendees:
            if isinstance(attendee, dict) and attendee.get("company"):
                return attendee["company"]

        # Fall back to subject parsing
        subject = meeting.get("subject", "")
        if "×" in subject:
            # Format: "RPCK × Company Name — Meeting"
            parts = subject.split("×")
            if len(parts) > 1:
                company_part = parts[1].split("—")[0].strip()
                return company_part

        return ""


def select_llm_client() -> LLMClient:
    """Factory function to select LLM client based on configuration."""
    llm_enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"

    if not llm_enabled:
        return StubLLMClient()

    # LLM is enabled, try to create OpenAI client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Fall back to stub if no API key
        return StubLLMClient()

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    timeout_ms = int(os.getenv("LLM_TIMEOUT_MS", "800"))

    return OpenAIClient(api_key=api_key, model=model, timeout_ms=timeout_ms)
