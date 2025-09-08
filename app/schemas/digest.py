from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr


class DigestSendRequest(BaseModel):
    send: bool = False
    recipients: Optional[List[EmailStr]] = None
    subject: Optional[str] = None
    source: Optional[Literal["sample", "live"]] = "sample"


class DigestSendResponse(BaseModel):
    ok: bool = True
    action: Literal["rendered", "sent"]
    subject: str
    recipients: List[EmailStr]
    message_id: Optional[str] = None
    preview_chars: int
    driver: Literal["console", "smtp", "sendgrid"]
    source: Literal["sample", "live"]


