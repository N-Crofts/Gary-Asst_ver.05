"""
Helpers for research anchor extraction: org/project from subject and from email domain.
"""
import re


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
