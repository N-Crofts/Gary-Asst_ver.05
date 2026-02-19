"""
Research provider interface and implementations.

Provides research summaries for digest enrichment via Tavily or stub provider.
Single POST per call, no retries. Basic search only unless TAVILY_ALLOW_ADVANCED=true.
"""
import os
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List

import httpx

from app.research.config import (
    TAVILY_TIMEOUT_SECONDS,
    MAX_RESEARCH_SOURCES,
    MAX_RESEARCH_SUMMARY_CHARS,
    MAX_RESEARCH_KEYPOINTS,
    MAX_KEYPOINT_CHARS,
    allow_tavily_advanced,
)

logger = logging.getLogger(__name__)

# Operation type for future advanced ops; only "search" is allowed by default
TAVILY_OP_SEARCH = "search"


class ResearchProvider(ABC):
    """Base interface for research providers."""
    
    @abstractmethod
    def get_research(self, topic: str) -> Dict[str, Any]:
        """
        Get research summary for a topic.
        
        Args:
            topic: Research topic string
            
        Returns:
            Dict with keys:
                - summary: str (short synthesized summary)
                - key_points: List[str] (3-5 bullet points)
                - sources: List[Dict[str, str]] (list of {title, url})
        """
        ...


class StubResearchProvider(ResearchProvider):
    """Stub research provider that returns fixed mock data."""
    
    def get_research(self, topic: str) -> Dict[str, Any]:
        """
        Return stub research data.
        
        Args:
            topic: Research topic (ignored for stub)
            
        Returns:
            Mock research structure
        """
        return {
            "summary": f"Stub research summary for topic: {topic}",
            "key_points": [
                "Stub key point 1",
                "Stub key point 2"
            ],
            "sources": []
        }


class TavilyResearchProvider(ResearchProvider):
    """Tavily API research provider."""
    
    def __init__(self, api_key: str, timeout: float = None, allow_advanced: bool = None):
        """
        Initialize Tavily provider.
        
        Args:
            api_key: Tavily API key
            timeout: Request timeout in seconds (default: TAVILY_TIMEOUT_SECONDS)
            allow_advanced: If False, only basic search is allowed. Default from env TAVILY_ALLOW_ADVANCED.
        """
        self.api_key = api_key
        self.timeout = float(timeout) if timeout is not None else TAVILY_TIMEOUT_SECONDS
        self.base_url = "https://api.tavily.com"
        self.allow_advanced = allow_advanced if allow_advanced is not None else allow_tavily_advanced()
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for deduplication (strip trailing slash, lowercase).
        
        Args:
            url: Raw URL string
            
        Returns:
            Normalized URL string
        """
        if not url:
            return ""
        url = url.strip().lower()
        # Remove trailing slash
        if url.endswith("/"):
            url = url[:-1]
        return url
    
    def _is_low_quality_domain(self, url: str) -> bool:
        """
        Check if URL is from a low-quality domain or contains suspicious content.
        
        Args:
            url: URL string to check
            
        Returns:
            True if URL should be filtered out
        """
        if not url:
            return True
        
        url_lower = url.lower()
        
        # Low-quality domains
        low_quality_domains = [
            "tripod.com",
            "blogspot.com",
            "livejournal.com",
            "tumblr.com",
            "pinterest.com",
        ]
        
        for domain in low_quality_domains:
            if domain in url_lower:
                return True
        
        # Suspicious content patterns
        suspicious_patterns = [
            "people-search",
            "find out the truth",
        ]
        
        for pattern in suspicious_patterns:
            if pattern in url_lower:
                return True
        
        return False
    
    def get_research(self, topic: str, operation: str = TAVILY_OP_SEARCH) -> Dict[str, Any]:
        """
        Get research from Tavily API. Single POST, no retries.
        Only operation "search" is allowed unless allow_advanced is True.
        
        Args:
            topic: Research topic string (already sanitized by caller)
            operation: Must be "search" unless allow_advanced; reserved for future advanced ops.
            
        Returns:
            Research structure with summary, key_points, sources.
            Returns empty structure on failure or if advanced op blocked.
        """
        if operation != TAVILY_OP_SEARCH and not self.allow_advanced:
            logger.warning(
                "RESEARCH_FAILED",
                extra={"error_type": "AdvancedOperationBlocked"}
            )
            return {"summary": "", "key_points": [], "sources": []}
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/search",
                    json={
                        "api_key": self.api_key,
                        "query": topic,
                        "search_depth": "basic",
                        "include_answer": True,
                        "include_raw_content": False,
                        "max_results": 5
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract sources with filtering and deduplication
                sources = []
                seen_urls = set()
                max_sources = MAX_RESEARCH_SOURCES
                for result in data.get("results", [])[:max_sources]:
                    title = result.get("title", "").strip()
                    url = result.get("url", "").strip()
                    
                    if not title or not url:
                        continue
                    
                    # Filter low-quality domains
                    if self._is_low_quality_domain(url):
                        continue
                    
                    # Deduplicate by normalized URL
                    normalized_url = self._normalize_url(url)
                    if normalized_url in seen_urls:
                        continue
                    seen_urls.add(normalized_url)
                    
                    sources.append({
                        "title": title,
                        "url": url
                    })
                    if len(sources) >= max_sources:
                        break
                
                # Extract key points (from filtered results)
                key_points = []
                for result in data.get("results", [])[:max_sources]:
                    title = result.get("title", "").strip()
                    url = result.get("url", "").strip()
                    if title and url and not self._is_low_quality_domain(url):
                        key_points.append(title)
                
                # Extract summary from Tavily response
                summary = data.get("answer", "")
                
                # Safeguard: if answer exists but sources are low-quality or empty,
                # do not show answer (prevent hallucinations without citations)
                if summary and (not sources or len(sources) == 0):
                    summary = ""
                elif not summary and data.get("results"):
                    # Fallback: use first result snippet only if we have good sources
                    if sources:
                        summary = data["results"][0].get("content", "")[:200] if data["results"] else ""
                    else:
                        summary = ""
                
                # Apply output caps
                summary_capped = (summary[:MAX_RESEARCH_SUMMARY_CHARS] if summary else "").strip()
                key_points_capped = [
                    (p[:MAX_KEYPOINT_CHARS].strip() if p else "")
                    for p in (key_points[:MAX_RESEARCH_KEYPOINTS])
                ]
                key_points_capped = [p for p in key_points_capped if p]
                sources_capped = sources[:MAX_RESEARCH_SOURCES]
                
                duration_ms = int((time.perf_counter() - start) * 1000)
                return {
                    "summary": summary_capped,
                    "key_points": key_points_capped,
                    "sources": sources_capped,
                    "_duration_ms": duration_ms,
                }
                
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "RESEARCH_FAILED",
                extra={"error_type": type(e).__name__, "duration_ms": duration_ms}
            )
            return {
                "summary": "",
                "key_points": [],
                "sources": [],
                "_duration_ms": duration_ms,
            }


def create_tavily_provider() -> TavilyResearchProvider:
    """
    Factory function to create TavilyResearchProvider from environment.
    
    Returns:
        TavilyResearchProvider instance
        
    Raises:
        RuntimeError: If TAVILY_API_KEY is not set
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not configured")
    
    return TavilyResearchProvider(
        api_key=api_key,
        timeout=TAVILY_TIMEOUT_SECONDS,
        allow_advanced=allow_tavily_advanced(),
    )
