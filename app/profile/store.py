import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from app.profile.models import ExecProfile


DATA_PATH = Path("app/data/exec_profiles.json")


def get_profile(profile_id: Optional[str] = None, mailbox: Optional[str] = None) -> ExecProfile:
    """
    Load an executive profile by ID or mailbox.

    Args:
        profile_id: Profile ID to load. If None, uses EXEC_PROFILE_ID env var or 'default'
        mailbox: Mailbox address to look up profile for. Takes precedence over profile_id

    Returns:
        ExecProfile object with the specified configuration
    """
    # Load profiles from JSON file
    if not DATA_PATH.exists():
        # Return a default profile if file doesn't exist
        return _get_default_profile(profile_id or "default")

    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            profiles_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        # Return default profile if file is corrupted
        return _get_default_profile(profile_id or "default")

    # If mailbox is provided, try to find profile by mailbox first
    if mailbox:
        profile_data = _find_profile_by_mailbox(profiles_data, mailbox)
        if profile_data:
            return _build_profile_from_data(profile_data, f"mailbox:{mailbox}")

    # Fall back to profile_id lookup
    if profile_id is None:
        profile_id = os.getenv("EXEC_PROFILE_ID", "default")

    # Find the requested profile
    profile_data = profiles_data.get(profile_id)
    if profile_data is None:
        # Fall back to default if profile not found
        profile_data = profiles_data.get("default", {})

    return _build_profile_from_data(profile_data, profile_id)


def _find_profile_by_mailbox(profiles_data: Dict[str, Any], mailbox: str) -> Optional[Dict[str, Any]]:
    """
    Find a profile by mailbox address.

    Args:
        profiles_data: All profiles data from JSON
        mailbox: Mailbox address to search for

    Returns:
        Profile data if found, None otherwise
    """
    for profile_id, profile_data in profiles_data.items():
        # Check if this profile has a mailbox mapping
        if "mailbox" in profile_data and profile_data["mailbox"] == mailbox:
            return profile_data
        # Also check if the profile_id itself is a mailbox
        if profile_id == mailbox:
            return profile_data
    return None


def _build_profile_from_data(profile_data: Dict[str, Any], profile_id: str) -> ExecProfile:
    """
    Build an ExecProfile from profile data with defaults.

    Args:
        profile_data: Raw profile data from JSON
        profile_id: Profile ID to use

    Returns:
        ExecProfile object
    """
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
