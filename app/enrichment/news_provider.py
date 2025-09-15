from abc import ABC, abstractmethod
from typing import List, Dict, Any


class NewsProvider(ABC):
    """Abstract base class for news providers."""

    @abstractmethod
    def search(self, company: str) -> List[Dict[str, str]]:
        """
        Search for news articles related to a company.

        Args:
            company: Company name to search for

        Returns:
            List of news items with 'title' and 'url' keys
        """
        pass


class StubNewsProvider(NewsProvider):
    """Deterministic stub news provider for testing and when news is disabled."""

    def search(self, company: str) -> List[Dict[str, str]]:
        """Generate deterministic news items based on company name."""
        company_lower = company.lower()

        # Company-specific news
        if "acme" in company_lower:
            return [
                {"title": "Acme Capital closes $250M Fund IV focused on decarbonization", "url": "https://example.com/acme-fund-iv"},
                {"title": "GridFlow B led by Acme; overlap with RPCK client", "url": "https://example.com/gridflow-b"},
                {"title": "Acme announces climate infrastructure partnership", "url": "https://example.com/infra-partnership"},
                {"title": "Acme portfolio company raises Series B", "url": "https://example.com/series-b"},
                {"title": "Acme Capital expands European operations", "url": "https://example.com/europe-expansion"}
            ]
        elif "techcorp" in company_lower:
            return [
                {"title": "TechCorp launches new AI platform for enterprise", "url": "https://example.com/ai-platform"},
                {"title": "TechCorp reports strong Q4 earnings growth", "url": "https://example.com/q4-earnings"},
                {"title": "TechCorp partners with major cloud providers", "url": "https://example.com/cloud-partnership"},
                {"title": "TechCorp expands into European markets", "url": "https://example.com/europe-expansion"},
                {"title": "TechCorp announces sustainability initiatives", "url": "https://example.com/sustainability"}
            ]
        elif "gridflow" in company_lower:
            return [
                {"title": "GridFlow B raises $15M Series B for grid optimization", "url": "https://example.com/series-b"},
                {"title": "GridFlow B partners with utility companies", "url": "https://example.com/utility-partnership"},
                {"title": "GridFlow B expands to new markets", "url": "https://example.com/market-expansion"},
                {"title": "GridFlow B announces new product features", "url": "https://example.com/product-features"},
                {"title": "GridFlow B recognized for innovation", "url": "https://example.com/innovation-award"}
            ]
        else:
            # Generic news for unknown companies
            return [
                {"title": f"{company} announces strategic partnership", "url": "https://example.com/partnership"},
                {"title": f"{company} reports quarterly results", "url": "https://example.com/quarterly-results"},
                {"title": f"{company} expands operations", "url": "https://example.com/expansion"},
                {"title": f"{company} launches new initiative", "url": "https://example.com/new-initiative"},
                {"title": f"{company} recognized for achievements", "url": "https://example.com/recognition"}
            ]
