from typing import List, Dict, Optional

from pydantic import BaseModel, ConfigDict


class ExecProfile(BaseModel):
    """Executive profile containing preferences and defaults."""

    model_config = ConfigDict(extra="allow")  # Allow extra fields for future extensibility

    id: str
    exec_name: str
    default_recipients: List[str]
    sections_order: List[str] = ["company", "news", "talking_points", "smart_questions"]
    max_items: Dict[str, int] = {
        "news": 5,
        "talking_points": 3,
        "smart_questions": 3
    }
    company_aliases: Dict[str, List[str]] = {}
