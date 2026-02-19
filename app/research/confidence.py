"""
Anchor confidence scoring and gating for research.

Confidence in [0, 1]. Research runs only when confidence >= CONF_MIN (default 0.70).
One fallback strategy is allowed before skipping.
"""
from typing import Any, Dict, Optional

# Generic email/consumer domains (low signal for B2B research)
GENERIC_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "live.com", "msn.com", "icloud.com", "me.com", "aol.com", "protonmail.com",
    "mail.com", "zoho.com", "yandex.com", "gmial.com", "google.com",
})


def domain_root(domain: str) -> str:
    """Registrable part of domain (e.g. smg.com -> smg, acmecapital.com -> acmecapital)."""
    if not domain or not isinstance(domain, str):
        return ""
    d = domain.strip().lower().split("@")[-1]
    for prefix in ("www.", "mail.", "calendar."):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.split(".", 1)[0] if "." in d else d


def domain_root_length(domain: str) -> int:
    """Length of domain root (e.g. smg.com -> 3)."""
    return len(domain_root(domain))


def is_domain_generic(domain: str) -> bool:
    """True if domain is a generic consumer email provider."""
    if not domain:
        return False
    root = domain_root(domain)
    # Check full domain and root
    full = domain.strip().lower()
    if full in GENERIC_DOMAINS:
        return True
    return root in GENERIC_DOMAINS or full.endswith(".gmail.com") or "google" in full


def is_domain_ambiguous_short(domain: str) -> bool:
    """True if domain root length <= 3 (e.g. smg.com, ac.co)."""
    return domain_root_length(domain) <= 3


def subject_has_org_keyword(subject: str) -> bool:
    """True if subject contains org/project-style keywords."""
    if not subject:
        return False
    s = subject.lower()
    keywords = ("intro", "introductory", "call on", "meeting on", "re:", "regarding", "project", "partnership")
    return any(kw in s for kw in keywords)


def is_vague_subject(subject: str) -> bool:
    """True if subject is vague (catch up, quick chat, sync, check-in)."""
    if not subject:
        return True
    s = subject.strip().lower()
    vague = ("catch up", "catch-up", "quick chat", "sync", "check-in", "check in", "touch base", "reconnect")
    return any(s == v or s.startswith(v + " ") or s.endswith(" " + v) for v in vague)


def is_meeting_like_test(
    meeting_data: Dict[str, Any],
    mailbox: Optional[str] = None,
) -> bool:
    """True if meeting looks like a test (subject or single self-attendee)."""
    subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip().lower()
    test_markers = ("test", "dummy", "sandbox", "qa", "asdf", "zzz")
    if any(m in subject for m in test_markers):
        return True
    attendees = meeting_data.get("attendees") or []
    if not attendees and mailbox:
        return False
    if len(attendees) != 1:
        return False
    # Only one attendee: check if it's the mailbox (self-invite test)
    def _email(a: Any) -> str:
        if isinstance(a, dict):
            return (a.get("email") or a.get("address") or "").strip().lower()
        return getattr(a, "email", None) or getattr(a, "address", "") or ""
    if not mailbox:
        return False
    mailbox_lower = mailbox.strip().lower()
    return _email(attendees[0]) == mailbox_lower


def compute_confidence(
    *,
    meeting_data: Dict[str, Any],
    anchor_type: str,
    has_org_context: bool,
    primary_domain: str,
    anchor_from_subject: bool,
    has_external_domain: bool,
    has_attendee_display_name: bool,
    mailbox: Optional[str] = None,
) -> float:
    """
    Compute anchor confidence in [0, 1].
    Uses only non-PII inputs (flags and domain root, not raw subject/names).
    """
    conf = 0.55

    # +0.20 if external domain non-generic
    if has_external_domain and primary_domain and not is_domain_generic(primary_domain):
        conf += 0.20

    # +0.15 if subject has org keyword
    subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip()
    if subject_has_org_keyword(subject):
        conf += 0.15

    # +0.10 if attendee display_name present
    if has_attendee_display_name:
        conf += 0.10

    # +0.10 if anchor derived from subject AND meeting is external
    if anchor_from_subject and has_external_domain:
        conf += 0.10

    # -0.35 if domain generic
    if primary_domain and is_domain_generic(primary_domain):
        conf -= 0.35

    # -0.30 if domain root length <= 3
    if primary_domain and is_domain_ambiguous_short(primary_domain):
        conf -= 0.30

    # -0.25 if anchor_type == person and org_context missing
    if anchor_type == "person" and not has_org_context:
        conf -= 0.25

    # -0.20 if subject is vague
    if is_vague_subject(subject):
        conf -= 0.20

    # -0.30 if meeting looks like test
    if is_meeting_like_test(meeting_data, mailbox):
        conf -= 0.30

    return max(0.0, min(1.0, conf))
