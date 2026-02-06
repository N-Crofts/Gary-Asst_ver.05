# Code Examples

This document provides sanitized examples of key modules and patterns used in Gary-Asst.

## Calendar Provider Pattern

### Protocol Definition

```python
# app/calendar/provider.py
from typing import Protocol, List, Optional
from app.calendar.types import Event

class CalendarProvider(Protocol):
    """Protocol for calendar providers."""

    def fetch_events(self, date: str, user: Optional[str] = None) -> List[Event]:
        """
        Fetch calendar events for a specific date and user.

        Args:
            date: ISO date string (YYYY-MM-DD)
            user: Optional user email to filter events

        Returns:
            List of Event objects
        """
        ...
```

### Implementation Example (Mock)

```python
# app/calendar/mock_provider.py
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import json

from app.calendar.types import Event

class MockCalendarProvider:
    """Mock calendar provider for testing."""

    def __init__(self, data_path: Path | None = None):
        self._path = data_path or Path("app/data/sample_calendar.json")

    def fetch_events(self, date: str, user: Optional[str] = None) -> List[Event]:
        """Fetch events from sample data file."""
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

            # Create Event object
            events.append(Event(
                subject=e.get("subject", ""),
                start_time=start_time,
                end_time=e.get("end_time", ""),
                location=e.get("location"),
                attendees=self._parse_attendees(e.get("attendees", [])),
                notes=e.get("notes")
            ))

        return events
```

### Factory Pattern

```python
# app/calendar/provider.py
import os
import logging

def select_calendar_provider() -> CalendarProvider:
    """Factory function to select calendar provider."""
    logger = logging.getLogger(__name__)

    provider = os.getenv("CALENDAR_PROVIDER", "mock").lower()
    logger.info(f"Selecting calendar provider: {provider}")

    if provider == "mock":
        from app.calendar.mock_provider import MockCalendarProvider
        return MockCalendarProvider()
    elif provider == "ms_graph":
        from app.calendar.ms_graph_adapter import create_ms_graph_adapter
        return create_ms_graph_adapter()
    else:
        raise ValueError(f"Unsupported CALENDAR_PROVIDER: {provider}")
```

## Route Handler Pattern

### Example Route Handler

```python
# app/routes/preview.py
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Literal, Optional
from datetime import datetime

from app.rendering.context_builder import build_digest_context_with_provider
from app.core.config import load_config

router = APIRouter()

def _require_api_key_if_configured(request: Request) -> None:
    """Require API key if configured."""
    cfg = load_config()
    if not cfg.api_key:
        return
    provided = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if provided != cfg.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

@router.get("/preview", response_class=HTMLResponse)
async def preview_digest_html(
    request: Request,
    source: Literal["sample", "live"] = Query("sample"),
    date: Optional[str] = Query(None),
    mailbox: Optional[str] = Query(None)
):
    """Preview digest as HTML."""
    # Authentication check
    _require_api_key_if_configured(request)

    # Validate source
    if source not in ("sample", "live"):
        raise HTTPException(status_code=400, detail="source must be 'sample' or 'live'")

    # Build context
    context = build_digest_context_with_provider(
        source=source,
        date=date,
        mailbox=mailbox
    )

    # Render HTML
    html = render_digest_html(context)
    return HTMLResponse(content=html)
```

## Service Layer Pattern

### Enrichment Service Example

```python
# app/enrichment/service.py
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def enrich_meetings(meetings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich meetings with company data, news, and LLM-generated content.

    Args:
        meetings: List of meeting dictionaries

    Returns:
        Enriched meetings with additional data
    """
    enriched = []

    for meeting in meetings:
        # Fetch company data
        company_name = _extract_company_name(meeting)
        if company_name:
            company_data = _fetch_company_data(company_name)
            meeting["company"] = company_data

        # Fetch news
        if _news_enabled():
            news_items = _fetch_news_for_company(company_name)
            meeting["news"] = news_items[:5]  # Limit to 5 items

        # Generate talking points and questions
        if _llm_enabled():
            talking_points = _generate_talking_points(meeting)
            smart_questions = _generate_smart_questions(meeting)
            meeting["talking_points"] = talking_points
            meeting["smart_questions"] = smart_questions

        enriched.append(meeting)

    return enriched

def _news_enabled() -> bool:
    """Check if news enrichment is enabled."""
    return os.getenv("NEWS_ENABLED", "false").lower() == "true"

def _llm_enabled() -> bool:
    """Check if LLM generation is enabled."""
    return os.getenv("LLM_ENABLED", "false").lower() == "true"
```

## Configuration Pattern

### Configuration Model

```python
# app/core/config.py
import os
from typing import Optional
from pydantic import BaseModel

class AppConfig(BaseModel):
    """Application configuration."""

    # Email settings
    mail_driver: str = "console"
    default_sender: str = "gary-asst@rpck.com"
    default_recipients: list[str] = []

    # Calendar settings
    timezone: str = "America/New_York"

    # Security
    api_key: Optional[str] = None

    # Feature flags
    slack_enabled: bool = False

def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    recipients_raw = os.getenv("DEFAULT_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    return AppConfig(
        mail_driver=os.getenv("MAIL_DRIVER", "console").lower(),
        default_sender=os.getenv("DEFAULT_SENDER", "gary-asst@rpck.com"),
        default_recipients=recipients,
        timezone=os.getenv("TIMEZONE", "America/New_York"),
        api_key=os.getenv("API_KEY"),
        slack_enabled=os.getenv("SLACK_ENABLED", "false").lower() == "true"
    )
```

## Error Handling Pattern

### Example Error Handling

```python
# app/routes/digest.py
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

async def send_digest(request: Request, body: DigestSendRequest):
    """Send digest email."""
    try:
        # Validate request
        if not body.send:
            raise HTTPException(status_code=400, detail="send must be true")

        # Process request
        result = await _process_digest(body)

        return JSONResponse(content={
            "ok": True,
            "message": "Digest sent successfully",
            **result
        })

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Failed to send digest: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send digest: {str(e)}"
        )
```

## Caching Pattern

### TTL Cache Example

```python
# app/storage/cache.py
import time
import hashlib
from typing import Optional, Dict, Any
from pathlib import Path

class PreviewCache:
    """TTL-based cache for preview data."""

    def __init__(self, ttl_minutes: int = 10):
        self.ttl_seconds = ttl_minutes * 60
        self._cache: Dict[str, tuple] = {}

    def _get_cache_key(self, mailbox: Optional[str], date: str) -> str:
        """Generate cache key."""
        key_data = f"{mailbox or 'default'}:{date}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, mailbox: Optional[str], date: str) -> Optional[Dict[str, Any]]:
        """Get cached data if not expired."""
        cache_key = self._get_cache_key(mailbox, date)

        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.ttl_seconds:
                return data
            else:
                # Expired, remove it
                del self._cache[cache_key]

        return None

    def set(self, mailbox: Optional[str], date: str, data: Dict[str, Any]) -> None:
        """Cache data with timestamp."""
        cache_key = self._get_cache_key(mailbox, date)
        self._cache[cache_key] = (data, time.time())
```

## Integration Layer Example

See `docs/INTEGRATION_EXAMPLE.md` for a complete mocked integration layer example.
