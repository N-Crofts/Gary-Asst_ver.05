from typing import List, Optional

from pydantic import BaseModel, EmailStr


class Attendee(BaseModel):
    name: str
    title: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None


class Event(BaseModel):
    subject: str
    start_time: str  # ISO 8601 datetime string in America/New_York timezone (e.g., "2025-01-15T09:30:00-05:00")
    end_time: str    # ISO 8601 datetime string in America/New_York timezone (e.g., "2025-01-15T10:30:00-05:00")
    location: Optional[str] = None
    attendees: List[Attendee] = []
    notes: Optional[str] = None
    id: Optional[str] = None  # Graph event ID
    organizer: Optional[str] = None  # Organizer email address


