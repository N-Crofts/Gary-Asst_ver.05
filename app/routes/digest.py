from fastapi import APIRouter
from app.core.renderer import render_digest
from app.integrations.bing import get_news_stub

router = APIRouter()


@router.post("/send")
def send_digest():
    # Placeholder data; replace with real Graph/Bing/LLM outputs
    company_name = "Acme Capital"
    headlines = get_news_stub(company_name)
    meetings = [
        {
            "subject": f"Intro with {company_name}",
            "start_time": "2025-09-03T10:00:00-04:00",
            "attendees": [
                {"name": "Jane Doe", "title": "Partner", "company": company_name}
            ],
            "company": {
                "name": company_name,
                "one_liner": "Growth equity firm.",
            },
            # now populated from stub, not hardcoded
            "news": [h["title"] for h in headlines],
            "talking_points": [
                "Ask about Fund III thesis",
                "Share RPCK Launch offerings",
                "Explore co-invest patterns",
            ],
            "smart_questions": [
                "What diligence gaps slow your deals?",
                "How do you resource ops post-close?",
                "Where do you need legal automation?",
            ],
        }
    ]

    html = render_digest(meetings)
    # TODO: send via Graph API. For now just return the HTML so you can preview.
    return {
        "ok": True,
        "company": company_name,
        "enrichment": {"headlines": headlines},  # keep full stub in JSON
        "html": html,
    }
