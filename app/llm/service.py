import os
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import httpx
from fastapi import HTTPException


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


class StubLLMClient(LLMClient):
    """Deterministic stub LLM client for testing and when LLM is disabled."""

    def generate_talking_points(self, meeting: Dict[str, Any]) -> List[str]:
        """Generate deterministic talking points based on meeting data."""
        subject = meeting.get("subject", "").lower()
        company_name = self._extract_company_name(meeting).lower()

        points = []

        # Company-specific talking points
        if "acme" in company_name:
            points.extend([
                "Confirm Q4 fund-formation timeline & counsel needs.",
                "Explore co-marketing with GridFlow case study.",
                "Flag cross-border structuring considerations early."
            ])
        elif "techcorp" in company_name:
            points.extend([
                "Review recent product launches and market positioning.",
                "Discuss potential partnership opportunities.",
                "Align on next quarter's strategic priorities."
            ])
        elif "gridflow" in company_name:
            points.extend([
                "Update on Series B progress and investor interest.",
                "Review technical roadmap and scaling challenges.",
                "Explore potential RPCK client introductions."
            ])
        else:
            # Generic talking points based on subject
            if "portfolio" in subject:
                points.extend([
                    "Review portfolio performance and strategic direction.",
                    "Discuss upcoming investment opportunities.",
                    "Align on portfolio company support needs."
                ])
            elif "intro" in subject:
                points.extend([
                    "Understand company background and current stage.",
                    "Explore potential collaboration opportunities.",
                    "Discuss RPCK services and value proposition."
                ])
            else:
                points.extend([
                    "Review meeting objectives and desired outcomes.",
                    "Discuss next steps and follow-up timeline.",
                    "Explore potential partnership opportunities."
                ])

        return points[:3]  # Limit to 3 points

    def generate_smart_questions(self, meeting: Dict[str, Any]) -> List[str]:
        """Generate deterministic smart questions based on meeting data."""
        subject = meeting.get("subject", "").lower()
        company_name = self._extract_company_name(meeting).lower()

        questions = []

        # Company-specific questions
        if "acme" in company_name:
            questions.extend([
                "What milestones unlock the next capital call?",
                "Any portfolio companies evaluating EU/US entity changes in 2025?",
                "Where is the biggest regulatory friction next 2 quarters?"
            ])
        elif "techcorp" in company_name:
            questions.extend([
                "What's driving your recent growth trajectory?",
                "How are you positioning against larger competitors?",
                "What legal challenges are you anticipating this year?"
            ])
        elif "gridflow" in company_name:
            questions.extend([
                "What's the timeline for your Series B close?",
                "How are you handling international expansion?",
                "Which RPCK practice areas would be most valuable?"
            ])
        else:
            # Generic questions based on subject
            if "portfolio" in subject:
                questions.extend([
                    "What are your key portfolio performance metrics?",
                    "Which sectors are you most excited about?",
                    "How can RPCK support your portfolio companies?"
                ])
            elif "intro" in subject:
                questions.extend([
                    "What stage is your company at currently?",
                    "What are your biggest legal challenges?",
                    "How can RPCK help accelerate your growth?"
                ])
            else:
                questions.extend([
                    "What are your top priorities for this quarter?",
                    "What challenges are you facing that we could help with?",
                    "How do you see the market evolving in your space?"
                ])

        return questions[:3]  # Limit to 3 questions

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
