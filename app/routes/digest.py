from fastapi import APIRouter
from app.core.renderer import render_digest

router = APIRouter()


@router.post("/send")
def send_digest():
    # Placeholder data; replace with real Graph/Bing/LLM outputs
    meetings = [
        {
            "subject": "Intro with Acme Capital",
            "start_time": "2025-09-03T10:00:00-04:00",
            "attendees": [
                {"name": "Jane Doe", "title": "Partner", "company": "Acme Capital"}
            ],
            "company": {"name": "Acme Capital", "one_liner": "Growth equity firm."},
            "news": ["Acme closes $250M Fund III", "Acme backs FinTech X"],
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
    # TODO: send via Graph API (Nick). For now just return the HTML so you can preview.
    return {"ok": True, "html": html}
