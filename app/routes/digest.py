# app/routes/digest.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from zoneinfo import ZoneInfo

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def _sample_meetings():
    return [{
        "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
        "start_time": "9:30 AM ET",
        "location": "Zoom",
        "attendees": [
            {"name": "Chintan Panchal", "title": "Managing Partner", "company": "RPCK"},
            {"name": "Carolyn", "title": "Chief of Staff", "company": "RPCK"},
            {"name": "A. Rivera", "title": "Partner", "company": "Acme Capital"},
        ],
        "company": {"name": "Acme Capital", "one_liner": "Growth-stage investor in climate tech & fintech."},
        "news": [
            "Closed $250M Fund IV; focusing on decarbonization infrastructure.",
            "Led Series B in GridFlow (portfolio overlap with RPCK client).",
        ],
        "talking_points": [
            "Confirm Q4 fund-formation timeline & counsel needs.",
            "Explore co-marketing with GridFlow case study.",
            "Flag cross-border structuring considerations early.",
        ],
        "smart_questions": [
            "What milestones unlock the next capital call, and where might legal support accelerate them?",
            "Any portfolio companies evaluating EU/US entity changes in 2025 that we should prep guidance for?",
        ],
    }]

def _today_et_str():
    now = datetime.now(ZoneInfo("America/New_York"))
    # Avoid %-d (not supported on Windows). Strip leading zero manually.
    day = str(int(now.strftime("%d")))
    return f"{now.strftime('%a')}, {now.strftime('%b')} {day}, {now.strftime('%Y')}"

@router.get("/send", response_class=HTMLResponse)
@router.post("/send", response_class=HTMLResponse)
async def send_digest(request: Request):
    # If you have real meetings, load them here; otherwise we fall back
    meetings = []  # TODO: replace with real data
    if not meetings:
        meetings = _sample_meetings()

    context = {
        "request": request,        # required by Jinja2Templates
        "meetings": meetings,
        "exec_name": "Biz Dev",
        "date_human": _today_et_str(),
        "current_year": datetime.now().strftime("%Y"),
    }
    return templates.TemplateResponse("digest.html", context)
