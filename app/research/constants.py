"""
Research safety constants. Re-exports from config for backward compatibility.
"""
from app.research.config import (
    MAX_TAVILY_CALLS_PER_REQUEST,
    TAVILY_TIMEOUT_SECONDS,
    MAX_RESEARCH_SOURCES,
    MAX_RESEARCH_SUMMARY_CHARS,
    MAX_RESEARCH_KEYPOINTS,
    MAX_KEYPOINT_CHARS,
)

# Backward compatibility alias
MAX_TAVILY_CALLS_PER_DIGEST = MAX_TAVILY_CALLS_PER_REQUEST
