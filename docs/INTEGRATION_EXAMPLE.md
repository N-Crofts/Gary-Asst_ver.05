# Integration Layer Example

This document provides a complete example of a mocked integration layer that demonstrates how external services are integrated into Gary-Asst.

## Overview

The integration layer abstracts external services (Microsoft Graph, News APIs, LLM services) behind clean interfaces, making the system testable and maintainable.

## Calendar Integration Example

### Interface Definition

```python
# app/calendar/types.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Attendee:
    """Calendar attendee."""
    name: str
    email: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None

@dataclass
class Event:
    """Calendar event."""
    subject: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    attendees: List[Attendee] = None
    notes: Optional[str] = None
```

### Mock Implementation

```python
# app/calendar/mock_provider.py
"""
Mock calendar provider for testing and development.

This implementation reads from a JSON file instead of making
real API calls, allowing for:
- Offline development
- Consistent test data
- No API rate limits
"""

from typing import List, Optional
from datetime import datetime
from pathlib import Path
import json

from app.calendar.types import Event, Attendee

DATA_PATH = Path("app/data/sample_calendar.json")

class MockCalendarProvider:
    """Mock calendar provider using sample data."""

    def __init__(self, data_path: Path | None = None):
        self._path = data_path or DATA_PATH

    def fetch_events(self, date: str, user: Optional[str] = None) -> List[Event]:
        """
        Fetch events from sample data file.

        Args:
            date: ISO date string (YYYY-MM-DD)
            user: Optional user email (ignored in mock)

        Returns:
            List of Event objects for the specified date
        """
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        # Load sample data
        if not self._path.exists():
            return []

        raw_data = json.loads(self._path.read_text())
        events_raw = raw_data.get("events", [])

        # Filter by date
        events = []
        for e in events_raw:
            start_time = str(e.get("start_time", ""))
            if not start_time.startswith(date):
                continue

            # Parse attendees
            attendees = []
            for a in e.get("attendees", []):
                attendees.append(Attendee(
                    name=a.get("name", ""),
                    title=a.get("title"),
                    company=a.get("company"),
                    email=a.get("email")
                ))

            # Create Event object
            events.append(Event(
                subject=e.get("subject", ""),
                start_time=start_time,
                end_time=e.get("end_time", ""),
                location=e.get("location"),
                attendees=attendees,
                notes=e.get("notes")
            ))

        return events
```

### Sample Data Format

```json
// app/data/sample_calendar.json
{
  "events": [
    {
      "subject": "Meeting with Acme Corp",
      "start_time": "2026-01-17T09:00:00-05:00",
      "end_time": "2026-01-17T10:00:00-05:00",
      "location": "Conference Room A",
      "attendees": [
        {
          "name": "Jane Smith",
          "email": "jane@acme.com",
          "title": "CEO",
          "company": "Acme Corp"
        },
        {
          "name": "John Doe",
          "email": "john@example.com",
          "title": "VP Sales"
        }
      ],
      "notes": "Quarterly business review"
    }
  ]
}
```

## News Integration Example

### Interface Definition

```python
# app/enrichment/news_provider.py
from abc import ABC, abstractmethod
from typing import List, Dict

class NewsProvider(ABC):
    """Abstract base class for news providers."""

    @abstractmethod
    def search(self, query: str) -> List[Dict[str, str]]:
        """
        Search for news articles.

        Args:
            query: Search query (company name, person name, etc.)

        Returns:
            List of news items with 'title' and 'url' keys
        """
        pass
```

### Mock Implementation

```python
# app/enrichment/news_stub.py
"""
Stub news provider that returns empty results.

Useful when:
- News API is not configured
- Testing without external dependencies
- News enrichment is disabled
"""

from typing import List, Dict
from app.enrichment.news_provider import NewsProvider

class StubNewsProvider(NewsProvider):
    """Stub news provider that returns no results."""

    def search(self, query: str) -> List[Dict[str, str]]:
        """Return empty list (no news)."""
        return []
```

### Real Implementation Example (NewsAPI)

```python
# app/enrichment/news_newsapi.py
"""
NewsAPI.org integration.

This implementation makes real API calls to NewsAPI.org
to fetch news articles for companies and people.
"""

import os
import httpx
import logging
from typing import List, Dict

from app.enrichment.news_provider import NewsProvider

logger = logging.getLogger(__name__)

class NewsAPIProvider(NewsProvider):
    """NewsAPI.org provider."""

    def __init__(self, api_key: str, timeout_seconds: float = 5.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://newsapi.org/v2/everything"

    def search(self, query: str) -> List[Dict[str, str]]:
        """Search for news articles."""
        if not query or not query.strip():
            return []

        headers = {"X-API-Key": self.api_key}
        params = {
            "q": query.strip(),
            "pageSize": 10,
            "sortBy": "publishedAt",
            "language": "en"
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(self.base_url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_response(data)
                elif response.status_code == 401:
                    logger.warning("NewsAPI authentication failed")
                    return []
                else:
                    logger.warning(f"NewsAPI error: {response.status_code}")
                    return []
        except Exception as e:
            logger.warning(f"NewsAPI error: {e}")
            return []

    def _parse_response(self, data: Dict) -> List[Dict[str, str]]:
        """Parse NewsAPI response."""
        news_items = []
        for article in data.get("articles", []):
            title = article.get("title", "").strip()
            url = article.get("url", "").strip()

            if title and url:
                news_items.append({"title": title, "url": url})

        return news_items[:5]  # Limit to 5 items
```

## LLM Integration Example

### Interface Definition

```python
# app/llm/service.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

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
```

### Mock Implementation

```python
# app/llm/stub.py
"""
Stub LLM client that returns default content.

Useful when:
- LLM API is not configured
- Testing without external dependencies
- LLM generation is disabled
"""

from typing import List, Dict, Any
from app.llm.service import LLMClient

class StubLLMClient(LLMClient):
    """Stub LLM client with default responses."""

    def generate_talking_points(self, meeting: Dict[str, Any]) -> List[str]:
        """Return default talking points."""
        return [
            "Review meeting objectives and desired outcomes",
            "Discuss next steps and follow-up timeline",
            "Explore potential partnership opportunities"
        ]

    def generate_smart_questions(self, meeting: Dict[str, Any]) -> List[str]:
        """Return default smart questions."""
        return [
            "What are your top priorities for this quarter?",
            "What challenges are you facing that we could help with?",
            "How do you see the market evolving in your space?"
        ]
```

## Email Integration Example

### Interface Definition

```python
# app/services/emailer.py
from abc import ABC, abstractmethod
from typing import List

class Emailer(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    def send(
        self,
        to: List[str],
        subject: str,
        html: str,
        plaintext: str = None
    ) -> None:
        """Send email."""
        pass
```

### Mock Implementation (Console)

```python
# app/services/console_emailer.py
"""
Console emailer for testing.

Prints emails to console instead of sending them.
"""

from typing import List
from app.services.emailer import Emailer

class ConsoleEmailer(Emailer):
    """Console emailer for testing."""

    def send(
        self,
        to: List[str],
        subject: str,
        html: str,
        plaintext: str = None
    ) -> None:
        """Print email to console."""
        print("=" * 60)
        print(f"TO: {', '.join(to)}")
        print(f"SUBJECT: {subject}")
        print("=" * 60)
        print(plaintext or html)
        print("=" * 60)
```

## Factory Pattern for Integration Selection

```python
# app/enrichment/service.py
import os
import logging

logger = logging.getLogger(__name__)

def _select_news_provider():
    """Select news provider based on configuration."""
    if not _news_enabled():
        from app.enrichment.news_stub import StubNewsProvider
        return StubNewsProvider()

    provider = os.getenv("NEWS_PROVIDER", "newsapi").lower()

    if provider == "newsapi":
        from app.enrichment.news_newsapi import create_newsapi_provider
        return create_newsapi_provider()
    elif provider == "bing":
        from app.enrichment.news_bing import create_bing_news_provider
        return create_bing_news_provider()
    else:
        from app.enrichment.news_stub import StubNewsProvider
        return StubNewsProvider()

def _news_enabled() -> bool:
    """Check if news enrichment is enabled."""
    return os.getenv("NEWS_ENABLED", "false").lower() == "true"
```

## Benefits of This Pattern

1. **Testability**: Easy to swap real implementations with mocks
2. **Development**: Work offline with sample data
3. **Reliability**: Graceful degradation when services are unavailable
4. **Flexibility**: Easy to add new providers (Google Calendar, different news APIs, etc.)
5. **Configuration**: Enable/disable features via environment variables

## Usage Example

```python
# In your application code
from app.calendar.provider import select_calendar_provider

# Automatically selects mock or real provider based on config
provider = select_calendar_provider()

# Use the provider (works the same regardless of implementation)
events = provider.fetch_events("2026-01-17", user="user@domain.com")
```
