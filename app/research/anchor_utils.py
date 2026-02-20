"""
Helpers for research anchor extraction: org/project from subject and from email domain.
"""
import re
from typing import Set

# Domains we treat as consumer/personal; do not use as org anchors
CONSUMER_DOMAINS: Set[str] = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "outlook.com",
    "hotmail.com", "hotmail.co.uk", "live.com", "msn.com", "icloud.com",
    "aol.com", "mail.com", "protonmail.com", "zoho.com", "yandex.com",
    "gmx.com", "gmx.net", "fastmail.com", "me.com", "mac.com",
}

# Known domain (first segment) -> display org name for research query
DOMAIN_ORG_OVERRIDES = {
    "csa": "CSA",
    "gatesfoundation": "Gates Foundation",
    "rethinkimpact": "Rethink Impact",
    "kawisafiventures": "Kawisa Ventures",
    "smg": "Service Management Group",
}

# First-segment tokens that suggest assistant/PA/concierge rather than org
ASSISTANT_DOMAIN_MARKERS = (
    "chiefofstaff", "assistant", "ea", "pa", "admin", "concierge",
    "chief-of-staff", "executive-assistant", "personal-assistant",
)


def _first_segment(domain: str) -> str:
    """Return lowercased first segment (registrable) of domain."""
    if not domain or not isinstance(domain, str):
        return ""
    d = domain.strip().lower()
    if "." in d:
        return d.split(".", 1)[0]
    return d


def looks_like_personal_domain(domain: str) -> bool:
    """
    Heuristics for domains that look like a personal name rather than an organization.
    Used to deprioritize them in primary_domain selection to avoid wrong-entity research.
    """
    if not domain or not domain.strip():
        return False
    d = domain.strip().lower()
    parts = d.split(".")
    segment = _first_segment(domain)
    if not segment:
        return False
    key = segment.replace("-", "").replace("_", "")
    if key in DOMAIN_ORG_OVERRIDES:
        return False
    # Short alphabetic first segment not in known-org overrides -> potentially personal
    if len(segment) <= 6 and key.isalpha():
        return True
    # Pattern <name>.me.<cc> (e.g. hussein.me.ke) -> personal
    if len(parts) >= 3 and parts[-2] == "me" and len(parts[-1]) == 2:
        return True
    # Pattern <name>.<cc> (e.g. firstname.ke) with short first segment
    if len(parts) == 2 and len(parts[-1]) == 2 and len(segment) <= 12 and segment.isalpha():
        return True
    return False


def looks_like_assistant_domain(domain: str) -> bool:
    """
    Heuristics for domains that look like an assistant/PA service rather than the principal org.
    Matches when the first segment equals a marker or contains it as a whole word (not substring like 'ea' in 'rethink').
    """
    if not domain or not isinstance(domain, str):
        return False
    segment = _first_segment(domain)
    segment_flat = segment.replace("-", "").replace("_", "")
    for marker in ASSISTANT_DOMAIN_MARKERS:
        m = marker.replace("-", "")
        if segment_flat == m:
            return True
        if len(m) >= 4 and m in segment_flat:  # longer markers (chiefofstaff, assistant, admin, concierge) as substring
            return True
    return False


def is_consumer_domain(domain: str) -> bool:
    """Return True if domain is a consumer/personal email provider (ignore for org anchor)."""
    if not domain or not isinstance(domain, str):
        return True
    return domain.strip().lower() in CONSUMER_DOMAINS


def domain_to_org_name(domain: str) -> str:
    """
    Convert email domain to human-readable org name for research query.
    Uses overrides for known acronyms/names (e.g. csa -> CSA, gatesfoundation -> Gates Foundation).
    Otherwise same logic as org_from_email_domain (first segment, title-case).
    """
    if not domain or not domain.strip():
        return ""
    d = domain.strip().lower()
    for prefix in ("www.", "mail.", "calendar.", "cms.", "cms-"):
        if d.startswith(prefix):
            d = d[len(prefix):]
            break
    if "." in d:
        registrable = d.split(".", 1)[0]
    else:
        registrable = d
    registrable = registrable.replace("-", " ").replace("_", " ")
    # Known override (e.g. csa -> CSA, gatesfoundation -> Gates Foundation)
    key = registrable.replace(" ", "").lower()
    if key in DOMAIN_ORG_OVERRIDES:
        return DOMAIN_ORG_OVERRIDES[key]
    return " ".join(w.capitalize() for w in registrable.split() if w)


def extract_org_from_subject(subject: str) -> str:
    """
    Extract org/project phrase from subject (e.g. 'Introductory call on Kheyti Project' -> 'Kheyti Project').
    Returns "" if no strong candidate.
    """
    if not subject or not subject.strip():
        return ""
    subj = subject.strip()
    trailing = ""
    if " on " in subj:
        trailing = subj.split(" on ", 1)[1].strip()
    elif " re: " in subj.lower():
        parts = re.split(r"\s+re:\s+", subj, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) > 1:
            trailing = parts[1].strip()
    elif " regarding " in subj.lower():
        parts = re.split(r"\s+regarding\s+", subj, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) > 1:
            trailing = parts[1].strip()
    elif ":" in subj:
        trailing = subj.split(":", 1)[1].strip()
    if not trailing:
        return ""
    generic_suffixes = ("call", "meeting", "introductory", "intro", "sync")
    for suf in generic_suffixes:
        if trailing.lower().endswith(" " + suf):
            trailing = trailing[: -(len(suf) + 1)].strip()
        if trailing.lower() == suf:
            trailing = ""
            break
    if not trailing or len(trailing) < 3 or len(trailing) > 60:
        return ""
    tokens = trailing.split()
    if any(t[0:1].isupper() for t in tokens if t):
        return trailing
    return ""


def org_from_email_domain(domain: str) -> str:
    """
    Convert email domain to human-readable org name (e.g. cms-induslaw.com -> Induslaw).
    Returns "" if domain empty.
    """
    if not domain or not domain.strip():
        return ""
    d = domain.strip().lower()
    for prefix in ("www.", "mail.", "calendar.", "cms.", "cms-"):
        if d.startswith(prefix):
            d = d[len(prefix):]
            break
    # Take first segment (e.g. betacorp.co.uk -> betacorp, induslaw.com -> induslaw)
    if "." in d:
        registrable = d.split(".", 1)[0]
    else:
        registrable = d
    registrable = registrable.replace("-", " ").replace("_", " ")
    result = " ".join(w.capitalize() for w in registrable.split() if w)
    return result
