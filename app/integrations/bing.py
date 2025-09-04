from datetime import datetime, timezone
from typing import List, Dict


def get_news_stub(company: str) -> List[Dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "title": f"{company} raises new fund",
            "url": "https://example.com/fund",
            "source": "Example News",
            "ts": now,
        },
        {
            "title": f"{company} announces new partnership",
            "url": "https://example.com/partner",
            "source": "Example Daily",
            "ts": now,
        },
        {
            "title": f"{company} expands into new market",
            "url": "https://example.com/market",
            "source": "Example Wire",
            "ts": now,
        },
    ]
