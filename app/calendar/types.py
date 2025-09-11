from typing import List, Optional

from pydantic import BaseModel, EmailStr


class Attendee(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None


class Event(BaseModel):
    subject: str
    start_time: str  # ISO string with timezone (ET)
    end_time: str    # ISO string with timezone (ET)
    location: Optional[str] = None
    attendees: List[Attendee] = []
    notes: Optional[str] = None


