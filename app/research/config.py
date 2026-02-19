"""
Research config: safety caps, env flags, and per-request budget.

Research runs only when allow_research=True at an allowed call site (digest preview,
run-digest, digest send). Budget caps Tavily calls per request. No PII in logs.
"""
import os
from typing import Set

# Hard cap: never more than this many Tavily calls per request
MAX_TAVILY_CALLS_PER_REQUEST = 1

# HTTP timeout for Tavily API calls (seconds). No retries.
TAVILY_TIMEOUT_SECONDS = 10

# Advanced operations (extract/map/crawl) disabled unless explicitly enabled
ALLOW_TAVILY_ADVANCED_ENV = "TAVILY_ALLOW_ADVANCED"

# Output caps
MAX_RESEARCH_SOURCES = 5
MAX_RESEARCH_SUMMARY_CHARS = 600
MAX_RESEARCH_KEYPOINTS = 6
MAX_KEYPOINT_CHARS = 180

# Query sanitization: max length after sanitization
MAX_RESEARCH_QUERY_CHARS = 120
MIN_RESEARCH_QUERY_CHARS = 3

# Call-site identifiers where research is allowed (for documentation / future gating)
RESEARCH_ALLOWED_PATHS: Set[str] = {"digest_preview", "run_digest", "digest_send"}

# Minimum confidence (0..1) to run research. Below this we skip (one fallback allowed).
RESEARCH_CONFIDENCE_MIN_ENV = "RESEARCH_CONFIDENCE_MIN"
DEFAULT_CONF_MIN = 0.70


def get_confidence_min() -> float:
    """Minimum anchor confidence to run research. From env RESEARCH_CONFIDENCE_MIN, default 0.70."""
    raw = (os.getenv(RESEARCH_CONFIDENCE_MIN_ENV) or "").strip()
    if not raw:
        return DEFAULT_CONF_MIN
    try:
        v = float(raw)
        return max(0.0, min(1.0, v))
    except ValueError:
        return DEFAULT_CONF_MIN


def env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean env var consistently. True for 'true', '1', 'yes' (case-insensitive)."""
    raw = (os.getenv(key) or "").strip().lower()
    return raw in ("true", "1", "yes")


def allow_tavily_advanced() -> bool:
    """Whether advanced Tavily operations are allowed. Default False."""
    return env_bool(ALLOW_TAVILY_ADVANCED_ENV, False)


class ResearchBudget:
    """
    Per-request budget for Tavily calls. Ensures at most N calls per request.
    """
    __slots__ = ("_remaining",)

    def __init__(self, remaining_calls: int):
        if remaining_calls < 0:
            remaining_calls = 0
        self._remaining = remaining_calls

    def consume_one_or_false(self) -> bool:
        """
        Consume one call from the budget if available.
        Returns True if a call was consumed, False if budget exhausted.
        """
        if self._remaining <= 0:
            return False
        self._remaining -= 1
        return True

    @property
    def remaining_calls(self) -> int:
        return max(0, self._remaining)
