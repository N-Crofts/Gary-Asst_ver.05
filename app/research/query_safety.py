"""
Sanitize research query to avoid leaking confidential info. Do not log raw or sanitized query.
"""
import re
from app.research.config import MAX_RESEARCH_QUERY_CHARS, MIN_RESEARCH_QUERY_CHARS


# Patterns to remove (sensitive)
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}([-.\s]?\d{2,4})?|\d{10,}",
)
# Currency: $1,000,000 / $1.5m / EUR 5m / £100k etc.
_CURRENCY_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d+)?[kmb]?\b|"
    r"(?:USD|EUR|GBP|USD)\s*[\d,]+(?:\.\d+)?[kmb]?\b|"
    r"£[\d,]+(?:\.\d+)?[kmb]?\b|"
    r"[\d,]+(?:\.\d+)?\s*(?:m|k|M|K)\s*(?:USD|EUR|dollars?|euros?)\b",
    re.IGNORECASE,
)
# Confidentiality markers (remove phrase only; we strip whole phrases that look like markers)
_CONFIDENTIAL_PHRASES = re.compile(
    r"\b(?:confidential|NDA|term\s+sheet|non[\s-]?disclosure)\b",
    re.IGNORECASE,
)
# Long numeric IDs/codes (6+ digits)
_LONG_NUMERIC_PATTERN = re.compile(r"\b\d{6,}\b")
# Collapse whitespace
_WHITESPACE_PATTERN = re.compile(r"\s+")


def sanitize_research_query(raw: str) -> str:
    """
    Sanitize a research query to avoid leaking emails, phones, amounts, confidential markers, long IDs.
    Collapses whitespace and trims. Enforces max length. Do not log input or output.

    Args:
        raw: Raw query string (may contain PII or confidential terms).

    Returns:
        Sanitized string (max MAX_RESEARCH_QUERY_CHARS), or empty if nothing left.
    """
    if not raw or not isinstance(raw, str):
        return ""
    s = raw.strip()
    s = _EMAIL_PATTERN.sub(" ", s)
    s = _PHONE_PATTERN.sub(" ", s)
    s = _CURRENCY_PATTERN.sub(" ", s)
    s = _CONFIDENTIAL_PHRASES.sub(" ", s)
    s = _LONG_NUMERIC_PATTERN.sub(" ", s)
    s = _WHITESPACE_PATTERN.sub(" ", s).strip()
    if len(s) > MAX_RESEARCH_QUERY_CHARS:
        s = s[:MAX_RESEARCH_QUERY_CHARS].strip()
    return s


def is_query_usable_after_sanitization(sanitized: str) -> bool:
    """True if sanitized query is long enough to use (>= MIN_RESEARCH_QUERY_CHARS)."""
    return len(sanitized.strip()) >= MIN_RESEARCH_QUERY_CHARS
