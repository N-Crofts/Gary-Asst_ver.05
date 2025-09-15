import json
import os
import time
import logging
from pathlib import Path
from typing import List, Dict, Any

from app.enrichment.models import MeetingWithEnrichment, Company, NewsItem
from app.llm.service import select_llm_client
from app.enrichment.news_provider import StubNewsProvider
from app.enrichment.news_bing import create_bing_news_provider
from app.utils.cache import news_cache

logger = logging.getLogger(__name__)


DATA_PATH = Path("app/data/sample_enrichment.json")


def _enrichment_enabled() -> bool:
    return os.getenv("ENRICHMENT_ENABLED", "true").lower() == "true"


def _timeout_ms() -> int:
    try:
        return int(os.getenv("ENRICHMENT_TIMEOUT_MS", "250"))
    except ValueError:
        return 250


def _news_enabled() -> bool:
    return os.getenv("NEWS_ENABLED", "false").lower() == "true"


def _news_max_items() -> int:
    try:
        return int(os.getenv("NEWS_MAX_ITEMS", "5"))
    except ValueError:
        return 5


def _news_cache_ttl_min() -> int:
    try:
        return int(os.getenv("NEWS_CACHE_TTL_MIN", "60"))
    except ValueError:
        return 60


def _select_news_provider():
    """Select news provider based on configuration."""
    if not _news_enabled():
        return StubNewsProvider()

    provider = os.getenv("NEWS_PROVIDER", "bing").lower()

    if provider == "bing":
        try:
            return create_bing_news_provider()
        except Exception as e:
            logger.warning(f"Failed to create Bing news provider: {e}")
            return StubNewsProvider()
    else:
        logger.warning(f"Unknown news provider: {provider}, using stub")
        return StubNewsProvider()


def _fetch_news_for_company(company_name: str) -> List[Dict[str, str]]:
    """Fetch news for a company with caching."""
    if not company_name or not company_name.strip():
        return []

    # Create cache key
    cache_key = f"news:{company_name.lower().strip()}"

    # Check cache first
    cached_news = news_cache.get(cache_key)
    if cached_news is not None:
        return cached_news

    # Fetch from provider
    try:
        provider = _select_news_provider()
        news_items = provider.search(company_name)

        # Limit to max items
        max_items = _news_max_items()
        if len(news_items) > max_items:
            news_items = news_items[:max_items]

        # Cache the result
        cache_ttl_seconds = _news_cache_ttl_min() * 60
        news_cache.set(cache_key, news_items, cache_ttl_seconds)

        return news_items
    except Exception as e:
        logger.warning(f"Failed to fetch news for {company_name}: {e}")
        return []


def _key_for_meeting(meeting: Dict[str, Any]) -> str:
    # Prefer company name; fallback to first attendee company; else subject
    company_name = None
    comp = meeting.get("company")
    if isinstance(comp, dict):
        company_name = comp.get("name")
    if not company_name:
        for a in meeting.get("attendees", []) or []:
            company_name = a.get("company")
            if company_name:
                break
    return (company_name or meeting.get("subject") or "").lower()


def _load_fixtures() -> Dict[str, Any]:
    if not DATA_PATH.exists():
        return {}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def enrich_meetings(meetings: List[Dict[str, Any]], now: float | None = None, timeout_s: float | None = None) -> List[MeetingWithEnrichment]:
    if not _enrichment_enabled():
        # Return input minimally wrapped for type compatibility
        return [MeetingWithEnrichment(**m) for m in meetings]

    # Get LLM client (will be StubLLMClient if LLM is disabled)
    llm_client = select_llm_client()

    fixtures = _load_fixtures()
    start_time = now if now is not None else time.perf_counter()
    per_meeting_budget = timeout_s if timeout_s is not None else (_timeout_ms() / 1000.0)

    enriched: List[MeetingWithEnrichment] = []
    for m in meetings:
        key = _key_for_meeting(m)
        fixture = fixtures.get(key, {})
        company = fixture.get("company")
        company_model = Company(**company) if isinstance(company, dict) else None

        # Fetch news - use provider if enabled, otherwise use fixtures
        if _news_enabled():
            # Extract company name for news search
            company_name = None
            if company_model and company_model.name:
                company_name = company_model.name
            else:
                # Fallback to attendee company or subject parsing
                for a in m.get("attendees", []) or []:
                    if a.get("company"):
                        company_name = a.get("company")
                        break
                if not company_name and "×" in m.get("subject", ""):
                    # Parse from subject: "RPCK × Company Name — Meeting"
                    parts = m.get("subject", "").split("×")
                    if len(parts) > 1:
                        company_name = parts[1].split("—")[0].strip()

            # Fetch news from provider
            news_items = _fetch_news_for_company(company_name) if company_name else []
            news = [NewsItem(**item) for item in news_items]
        else:
            # Use fixture news when news provider is disabled
            news = [NewsItem(**n) for n in fixture.get("news", [])]

        # Generate talking points and smart questions using LLM client
        try:
            talking_points = llm_client.generate_talking_points(m)
            smart_questions = llm_client.generate_smart_questions(m)
        except Exception:
            # Fall back to fixture data if LLM fails
            talking_points = fixture.get("talking_points", [])
            smart_questions = fixture.get("smart_questions", [])

        enriched.append(
            MeetingWithEnrichment(
                subject=m.get("subject", ""),
                start_time=m.get("start_time", ""),
                location=m.get("location"),
                attendees=m.get("attendees", []),
                company=company_model,
                news=news,
                talking_points=talking_points,
                smart_questions=smart_questions,
            )
        )

        # Timebox: if we exceed budget for this meeting, break early
        if (time.perf_counter() - start_time) > per_meeting_budget:
            break

    return enriched


