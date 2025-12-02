import os
import logging
from typing import List, Dict, Any

import httpx
from fastapi import HTTPException

from app.enrichment.news_provider import NewsProvider

logger = logging.getLogger(__name__)


class NewsAPIProvider(NewsProvider):
    """NewsAPI.org provider for real news headlines."""

    def __init__(self, api_key: str, timeout_seconds: float = 5.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://newsapi.org/v2/everything"

    def search(self, query: str) -> List[Dict[str, str]]:
        """
        Search for news articles using NewsAPI.

        Args:
            query: Search query (company name or person search query)

        Returns:
            List of news items with 'title' and 'url' keys
        """
        if not query or not query.strip():
            return []

        # Build search query - focus on recent news
        # NewsAPI supports advanced queries, so we can use the query as-is
        search_query = query.strip()

        headers = {
            "X-API-Key": self.api_key
        }

        params = {
            "q": search_query,
            "pageSize": 10,  # Request more to filter for quality
            "sortBy": "publishedAt",  # Most recent first
            "language": "en",
            # Limit to last 7 days for freshness
            "from": None,  # Will be set dynamically if needed
            "to": None
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(
                    self.base_url,
                    headers=headers,
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_newsapi_response(data, query)
                elif response.status_code == 401:
                    logger.warning("NewsAPI authentication failed - check API key")
                    return []
                elif response.status_code == 429:
                    logger.warning("NewsAPI rate limit exceeded")
                    return []
                else:
                    logger.warning(f"NewsAPI error: {response.status_code} - {response.text}")
                    return []
        except httpx.TimeoutException:
            logger.warning(f"NewsAPI timeout after {self.timeout_seconds}s")
            return []
        except Exception as e:
            logger.warning(f"NewsAPI error: {str(e)}")
            return []

    def _parse_newsapi_response(self, data: Dict[str, Any], original_query: str) -> List[Dict[str, str]]:
        """Parse NewsAPI response and filter for relevant news."""
        news_items = []

        # Extract articles from response
        articles = data.get("articles", [])

        # Extract company name from query for filtering
        # Remove quotes and site: prefixes for matching
        query_clean = original_query.lower()
        query_clean = query_clean.replace('"', '').replace("'", '')
        if 'site:' in query_clean:
            # For site: queries, extract the name part
            parts = query_clean.split('site:')
            if len(parts) > 1:
                query_clean = parts[0].strip()
            else:
                query_clean = query_clean.replace('site:', '').strip()

        for article in articles:
            title = article.get("title", "").strip()
            url = article.get("url", "").strip()

            # Basic quality filters
            if not title or not url:
                continue

            # Skip if URL is None or invalid
            if url == "null" or not url.startswith(("http://", "https://")):
                continue

            # For company searches, check if title mentions the company (case-insensitive)
            # For person searches, we're more lenient
            if 'site:' not in original_query.lower() and query_clean:
                # Extract main terms from query (remove common words)
                query_terms = [q for q in query_clean.split() if len(q) > 2]
                if query_terms:
                    title_lower = title.lower()
                    # Check if at least one significant term appears in title
                    if not any(term in title_lower for term in query_terms):
                        continue

            # Skip obvious spam or low-quality sources
            spam_indicators = ["click here", "read more", "sponsored", "advertisement", "[removed]"]
            if any(spam in title.lower() for spam in spam_indicators):
                continue

            news_items.append({
                "title": title,
                "url": url
            })

            # Limit to reasonable number
            if len(news_items) >= 5:
                break

        return news_items


def create_newsapi_provider() -> NewsAPIProvider:
    """Factory function to create a NewsAPIProvider instance from environment variables."""
    api_key = os.getenv("NEWS_API_KEY")
    timeout_seconds = float(os.getenv("NEWS_TIMEOUT_MS", "5000")) / 1000.0

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="NewsAPI key not configured (NEWS_API_KEY)"
        )

    return NewsAPIProvider(api_key=api_key, timeout_seconds=timeout_seconds)

