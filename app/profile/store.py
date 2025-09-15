import json
import os
from pathlib import Path
from typing import Optional

from app.profile.models import ExecProfile


DATA_PATH = Path("app/data/exec_profiles.json")


def get_profile(profile_id: Optional[str] = None) -> ExecProfile:
    """
    Load an executive profile by ID.

    Args:
        profile_id: Profile ID to load. If None, uses EXEC_PROFILE_ID env var or 'default'

    Returns:
        ExecProfile object with the specified configuration
    """
    if profile_id is None:
        profile_id = os.getenv("EXEC_PROFILE_ID", "default")

    # Load profiles from JSON file
    if not DATA_PATH.exists():
        # Return a default profile if file doesn't exist
        return _get_default_profile(profile_id)

    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            profiles_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        # Return default profile if file is corrupted
        return _get_default_profile(profile_id)

    # Find the requested profile
    profile_data = profiles_data.get(profile_id)
    if profile_data is None:
        # Fall back to default if profile not found
        profile_data = profiles_data.get("default", {})

    # Ensure required fields exist
    profile_data.setdefault("id", profile_id)
    profile_data.setdefault("exec_name", "RPCK Biz Dev")
    profile_data.setdefault("default_recipients", ["bizdev@rpck.com"])
    profile_data.setdefault("sections_order", ["company", "news", "talking_points", "smart_questions"])
    profile_data.setdefault("max_items", {
        "news": 5,
        "talking_points": 3,
        "smart_questions": 3
    })
    profile_data.setdefault("company_aliases", {})

    return ExecProfile(**profile_data)


def _get_default_profile(profile_id: str = "default") -> ExecProfile:
    """Return a default profile when no data is available."""
    return ExecProfile(
        id=profile_id,
        exec_name="RPCK Biz Dev",
        default_recipients=["bizdev@rpck.com"],
        sections_order=["company", "news", "talking_points", "smart_questions"],
        max_items={
            "news": 5,
            "talking_points": 3,
            "smart_questions": 3
        },
        company_aliases={}
    )
