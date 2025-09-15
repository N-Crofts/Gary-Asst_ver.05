import os
import time
from typing import List, Dict, Any

import httpx
from fastapi import HTTPException

from app.enrichment.news_provider import NewsProvider


class BingNewsProvider(NewsProvider):
    """Bing News Search API provider for real news headlines."""

    def __init__(self, api_key: str, timeout_ms: int = 5000):
        self.api_key = api_key
        self.timeout_seconds = timeout_ms / 1000.0
        self.base_url = "https://api.bing.microsoft.com/v7.0/news/search"

    def search(self, company: str) -> List[Dict[str, str]]:
        """
        Search for news articles related to a company using Bing News API.

        Args:
            company: Company name to search for

        Returns:
            List of news items with 'title' and 'url' keys
        """
        if not company or not company.strip():
            return []

        # Build search query - focus on recent news
        query = f'"{company}" business news'

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json"
        }

        params = {
            "q": query,
            "count": 10,  # Request more to filter for quality
            "sortBy": "Date",  # Most recent first
            "freshness": "Week",  # Last week's news
            "mkt": "en-US"
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
                    return self._parse_bing_response(data, company)
                elif response.status_code == 401:
                    raise HTTPException(
                        status_code=503,
                        detail="Bing News API authentication failed"
                    )
                elif response.status_code == 429:
                    raise HTTPException(
                        status_code=503,
                        detail="Bing News API rate limit exceeded"
                    )
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Bing News API error: {response.status_code}"
                    )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=503,
                detail=f"Bing News API timeout after {self.timeout_seconds}s"
            )
        except HTTPException:
            raise  # Re-raise HTTPExceptions
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Bing News API error: {str(e)}"
            )

    def _parse_bing_response(self, data: Dict[str, Any], company: str) -> List[Dict[str, str]]:
        """Parse Bing API response and filter for relevant news."""
        news_items = []

        # Extract news articles from response
        articles = data.get("value", [])

        for article in articles:
            title = article.get("name", "").strip()
            url = article.get("url", "").strip()

            # Basic quality filters
            if not title or not url:
                continue

            # Skip if title doesn't mention the company (case-insensitive)
            if company.lower() not in title.lower():
                continue

            # Skip obvious spam or low-quality sources
            if any(spam in title.lower() for spam in ["click here", "read more", "sponsored", "advertisement"]):
                continue

            news_items.append({
                "title": title,
                "url": url
            })

            # Limit to reasonable number
            if len(news_items) >= 5:
                break

        return news_items


def create_bing_news_provider() -> BingNewsProvider:
    """Factory function to create a BingNewsProvider instance from environment variables."""
    api_key = os.getenv("NEWS_API_KEY")
    timeout_ms = int(os.getenv("NEWS_TIMEOUT_MS", "5000"))

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Bing News API key not configured (NEWS_API_KEY)"
        )

    return BingNewsProvider(api_key=api_key, timeout_ms=timeout_ms)
