from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, HttpUrl


class Attendee(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None


class Company(BaseModel):
    name: str
    one_liner: Optional[str] = None


class NewsItem(BaseModel):
    title: str
    url: str  # Changed from HttpUrl to str for JSON serialization


class MeetingModel(BaseModel):
    subject: str
    start_time: str
    location: Optional[str] = None
    attendees: List[Attendee] = []
    company: Optional[Company] = None
    news: List[NewsItem] = []
    talking_points: List[str] = []
    smart_questions: List[str] = []
    # Data-driven sections for research/signals (no placeholder filler)
    context_summary: Optional[str] = None
    industry_signal: Optional[str] = None
    strategic_angles: List[str] = []
    high_leverage_questions: List[str] = []
    # Per-meeting research trace (dev/debug only, non-PII)
    research_trace: Optional[Dict[str, Any]] = None


class DigestPreviewModel(BaseModel):
    ok: bool = True
    source: Literal['sample', 'live'] = 'sample'
    date_human: str
    exec_name: str = 'Sorum Crofts'
    meetings: List[MeetingModel]
    research_trace: Optional[Dict[str, Any]] = None  # Non-PII observability; for dev/debug only
