"""
Research provider selector.

Central place for research gating: should_run_research() and provider selection.
Tavily is never called in development unless ENABLE_RESEARCH_DEV is set.
"""
import os
import logging
from typing import Optional, Tuple

from app.research.provider import StubResearchProvider, ResearchProvider

logger = logging.getLogger(__name__)


def should_run_research() -> Tuple[bool, Optional[str]]:
    """
    Whether research is allowed and, if not, the skip reason for logging.

    Returns:
        (True, None) if research may run (may call Tavily).
        (False, "disabled") if RESEARCH_ENABLED is not truthy.
        (False, "dev_guard") if APP_ENV/ENVIRONMENT is development and ENABLE_RESEARCH_DEV is not truthy.
    """
    raw_enabled = (os.getenv("RESEARCH_ENABLED") or "").strip().lower()
    research_enabled = raw_enabled in ("true", "1", "yes")

    if not research_enabled:
        return (False, "disabled")

    app_env = (
        (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development") or "development"
    ).strip().lower()
    if app_env == "development":
        raw_dev = (os.getenv("ENABLE_RESEARCH_DEV") or "").strip().lower()
        if raw_dev not in ("true", "1", "yes"):
            return (False, "dev_guard")

    return (True, None)


def is_research_effectively_enabled() -> bool:
    """True if research should run. Convenience wrapper for should_run_research()[0]."""
    allowed, _ = should_run_research()
    return allowed


def select_research_provider() -> ResearchProvider:
    """
    Return Tavily provider only when research is allowed and key is set;
    otherwise StubResearchProvider (no Tavily instantiation or network call).
    """
    allowed, _ = should_run_research()
    if not allowed:
        return StubResearchProvider()

    from app.research.provider import create_tavily_provider
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "RESEARCH_ENABLED=true but TAVILY_API_KEY is missing or empty. "
            "Using StubResearchProvider."
        )
        return StubResearchProvider()
    try:
        return create_tavily_provider()
    except RuntimeError:
        logger.warning(
            "RESEARCH_ENABLED=true but Tavily provider creation failed. "
            "Using StubResearchProvider."
        )
        return StubResearchProvider()
