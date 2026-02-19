"""
ResearchTrace: non-PII observability for research runs.

Returned alongside research results in digest context. Do not include:
subject, attendee emails, anchor strings, raw query string, URLs.
"""
import hashlib
from enum import Enum
from typing import Any, Dict, Optional


class ResearchOutcome(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


class SkipReason(str, Enum):
    ENDPOINT_GUARD = "endpoint_guard"
    DISABLED = "disabled"
    DEV_GUARD = "dev_guard"
    NO_CANDIDATE = "no_candidate"
    NO_ANCHOR = "no_anchor"
    QUERY_SANITIZED_EMPTY = "query_sanitized_empty"
    BUDGET_EXHAUSTED = "budget_exhausted"
    LOW_CONFIDENCE_ANCHOR = "low_confidence_anchor"
    MEETING_MARKED_TEST = "meeting_marked_test"


class AnchorType(str, Enum):
    PERSON = "person"
    ORG = "org"
    DOMAIN = "domain"


class AnchorSource(str, Enum):
    SUBJECT_COUNTERPARTY = "subject_counterparty"
    SUBJECT_ORG = "subject_org"
    ORGANIZER_DOMAIN = "organizer_domain"
    ATTENDEE = "attendee"


def query_hash_prefix(query: str, length: int = 10) -> str:
    """First `length` chars of sha256(query). Non-PII identifier for logging."""
    if not query:
        return ""
    h = hashlib.sha256(query.encode("utf-8", errors="replace")).hexdigest()
    return h[:length]


def build_research_trace(
    *,
    attempted: bool,
    outcome: str,
    skip_reason: Optional[str] = None,
    anchor_type: Optional[str] = None,
    anchor_source: Optional[str] = None,
    confidence: Optional[float] = None,
    query_hash: Optional[str] = None,
    query_len: Optional[int] = None,
    timings_ms: Optional[Dict[str, int]] = None,
    sources_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build a ResearchTrace dict for context and logging. All fields are non-PII.
    """
    trace: Dict[str, Any] = {
        "attempted": attempted,
        "outcome": outcome,
    }
    if skip_reason is not None:
        trace["skip_reason"] = skip_reason
    if anchor_type is not None:
        trace["anchor_type"] = anchor_type
    if anchor_source is not None:
        trace["anchor_source"] = anchor_source
    if confidence is not None:
        trace["confidence"] = round(confidence, 4)
    if query_hash is not None:
        trace["query_hash"] = query_hash
    if query_len is not None:
        trace["query_len"] = query_len
    if timings_ms is not None:
        trace["timings_ms"] = dict(timings_ms)
    if sources_count is not None:
        trace["sources_count"] = sources_count
    return trace
