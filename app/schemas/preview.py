from typing import List, Optional, Literal
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


class DigestPreviewModel(BaseModel):
    ok: bool = True
    source: Literal['sample', 'live'] = 'sample'
    date_human: str
    exec_name: str = 'RPCK Biz Dev'
    meetings: List[MeetingModel]
