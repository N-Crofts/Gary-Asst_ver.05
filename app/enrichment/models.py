from typing import List, Optional

from pydantic import BaseModel


class Company(BaseModel):
    name: str
    one_liner: Optional[str] = None


class NewsItem(BaseModel):
    title: str
    url: str


class MeetingWithEnrichment(BaseModel):
    subject: str
    start_time: str
    location: Optional[str] = None
    organizer: Optional[str] = None  # Organizer email for external-meeting detection
    attendees: List[dict] = []
    company: Optional[Company] = None
    news: List[NewsItem] = []
    talking_points: List[str] = []
    smart_questions: List[str] = []
    memory: Optional[dict] = None
    people_intel: Optional[dict] = None


