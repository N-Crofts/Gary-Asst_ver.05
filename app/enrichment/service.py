import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any

from app.enrichment.models import MeetingWithEnrichment, Company, NewsItem


DATA_PATH = Path("app/data/sample_enrichment.json")


def _enrichment_enabled() -> bool:
    return os.getenv("ENRICHMENT_ENABLED", "true").lower() == "true"


def _timeout_ms() -> int:
    try:
        return int(os.getenv("ENRICHMENT_TIMEOUT_MS", "250"))
    except ValueError:
        return 250


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

    fixtures = _load_fixtures()
    start_time = now if now is not None else time.perf_counter()
    per_meeting_budget = timeout_s if timeout_s is not None else (_timeout_ms() / 1000.0)

    enriched: List[MeetingWithEnrichment] = []
    for m in meetings:
        key = _key_for_meeting(m)
        fixture = fixtures.get(key, {})
        news = [NewsItem(**n) for n in fixture.get("news", [])]
        talking_points = fixture.get("talking_points", [])
        smart_questions = fixture.get("smart_questions", [])
        company = fixture.get("company")
        company_model = Company(**company) if isinstance(company, dict) else None

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


