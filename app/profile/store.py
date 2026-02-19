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
        # If no exact match found, create a profile with exec_name derived from mailbox
        # This ensures the heading matches the mailbox user even if no profile exists
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"No profile found for mailbox {mailbox}, deriving exec_name from mailbox")
        derived_exec_name = _derive_exec_name_from_mailbox(mailbox)
        return _build_profile_for_mailbox(mailbox, derived_exec_name)

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
    
    Performs case-insensitive comparison and normalizes mailboxes before matching.

    Args:
        profiles_data: All profiles data from JSON
        mailbox: Mailbox address to search for

    Returns:
        Profile data if found, None otherwise
    """
    # Normalize mailbox for comparison (lowercase, strip whitespace)
    mailbox_normalized = mailbox.strip().lower() if mailbox else ""
    
    for profile_id, profile_data in profiles_data.items():
        # Check if this profile has a mailbox mapping (case-insensitive)
        if "mailbox" in profile_data:
            profile_mailbox_normalized = profile_data["mailbox"].strip().lower()
            if profile_mailbox_normalized == mailbox_normalized:
                return profile_data
        # Also check if the profile_id itself is a mailbox (case-insensitive)
        profile_id_normalized = profile_id.strip().lower()
        if profile_id_normalized == mailbox_normalized:
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
    profile_data.setdefault("exec_name", "Sorum Crofts")
    profile_data.setdefault("default_recipients", ["sorum.crofts@rpck.com", "bizdev@rpck.com"])
    profile_data.setdefault("sections_order", ["company", "news", "talking_points", "smart_questions"])
    profile_data.setdefault("max_items", {
        "news": 5,
        "talking_points": 3,
        "smart_questions": 3
    })
    profile_data.setdefault("company_aliases", {})

    return ExecProfile(**profile_data)


def _derive_exec_name_from_mailbox(mailbox: str) -> str:
    """
    Derive a display name from a mailbox email address.
    
    Examples:
        chintan.panchal@rpck.com -> "Chintan Panchal"
        sorum.crofts@rpck.com -> "Sorum Crofts"
        john.doe@example.com -> "John Doe"
        jane@example.com -> "Jane"
    
    Args:
        mailbox: Email address
        
    Returns:
        Formatted name derived from email local part
    """
    if not mailbox or "@" not in mailbox:
        return "User"
    
    # Extract local part (before @)
    local_part = mailbox.split("@")[0].strip()
    
    # Split by dots and capitalize each part
    parts = local_part.split(".")
    if len(parts) >= 2:
        # Format: firstname.lastname -> "Firstname Lastname"
        formatted = " ".join(part.capitalize() for part in parts if part)
        return formatted
    else:
        # Single part: just capitalize
        return local_part.capitalize()


def _build_profile_for_mailbox(mailbox: str, exec_name: str) -> ExecProfile:
    """
    Build a profile for a mailbox when no profile exists.
    
    Uses default settings but with the derived exec_name.
    
    Args:
        mailbox: Mailbox email address
        exec_name: Derived executive name
        
    Returns:
        ExecProfile with default settings and custom exec_name
    """
    return ExecProfile(
        id=f"mailbox:{mailbox}",
        exec_name=exec_name,
        mailbox=mailbox,
        default_recipients=[mailbox],
        sections_order=["company", "news", "talking_points", "smart_questions"],
        max_items={
            "news": 5,
            "talking_points": 3,
            "smart_questions": 3
        },
        company_aliases={}
    )


def _get_default_profile(profile_id: str = "default") -> ExecProfile:
    """Return a default profile when no data is available."""
    return ExecProfile(
        id=profile_id,
        exec_name="Sorum Crofts",
        default_recipients=["sorum.crofts@rpck.com", "bizdev@rpck.com"],
        sections_order=["company", "news", "talking_points", "smart_questions"],
        max_items={
            "news": 5,
            "talking_points": 3,
            "smart_questions": 3
        },
        company_aliases={}
    )
