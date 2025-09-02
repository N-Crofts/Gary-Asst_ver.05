from pydantic import BaseModel
from typing import List, Optional


class Person(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None


class Company(BaseModel):
    name: str
    one_liner: Optional[str] = None
    linkedin_url: Optional[str] = None


class Meeting(BaseModel):
    subject: str
    start_time: str  # ISO string for now
    attendees: List[Person]
    company: Optional[Company] = None
    news: List[str] = []
    talking_points: List[str] = []
    smart_questions: List[str] = []
