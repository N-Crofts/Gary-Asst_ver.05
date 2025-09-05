# app/routes/digest.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from zoneinfo import ZoneInfo

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def _today_et_str():
    now = datetime.now(ZoneInfo("America/New_York"))
    day = str(int(now.strftime("%d")))  # avoid %-d on Windows
    return f"{now.strftime('%a')}, {now.strftime('%b')} {day}, {now.strftime('%Y')}"

def _sample_meetings_with_enrichment():
    return [
        {
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
                {"title": "Acme closes $250M Fund IV focused on decarbonization", "url": "https://example.com/acme-fund-iv"},
                {"title": "GridFlow raises Series B led by Acme; overlap with RPCK client", "url": "https://example.com/gridflow-series-b"},
                {"title": "Acme announces climate infrastructure partnership", "url": "https://example.com/infra-partnership"},
            ],
            "talking_points": [
                "Confirm Q4 fund-formation timeline & counsel needs.",
                "Explore co-marketing with GridFlow case study.",
                "Flag cross-border structuring considerations early.",
            ],
            "smart_questions": [
                "What milestones unlock the next capital call, and where might legal support accelerate them?",
                "Any portfolio companies evaluating EU/US entity changes in 2025 that we should prep guidance for?",
                "Where do you anticipate the biggest regulatory friction in the next 2 quarters?",
            ],
        },
        {
            "subject": "RPCK × GreenSpark Energy — Counsel Scope Review",
            "start_time": "1:00 PM ET",
            "location": "Teams",
            "attendees": [
                {"name": "Chintan Panchal", "title": "Managing Partner", "company": "RPCK"},
                {"name": "N. Crofts", "title": "Dev/AI", "company": "RPCK"},
                {"name": "M. Chen", "title": "CFO", "company": "GreenSpark"},
            ],
            "company": {"name": "GreenSpark Energy", "one_liner": "Community-scale solar developer."},
            "news": [
                {"title": "GreenSpark wins 30MW community solar RFP in NY", "url": "https://example.com/gs-rfp-win"},
                {"title": "Tax credit transfer program expands eligibility", "url": "https://example.com/itc-transfer-update"},
                {"title": "NYSERDA revises interconnection timelines", "url": "https://example.com/nyserda-interconnect"},
            ],
            "talking_points": [
                "Align on scope for tax credit transfer documentation.",
                "Timeline risks around interconnection; mitigation options.",
                "Data room checklist before diligence starts.",
            ],
            "smart_questions": [
                "Which projects are most impacted by interconnection delays and why?",
                "How will expanded transferability change your financing mix?",
                "Any counterparties that require special regulatory handling?",
            ],
        },
    ]

@router.get("/send", response_class=HTMLResponse)
@router.post("/send", response_class=HTMLResponse)
async def send_digest(request: Request):
    meetings = _sample_meetings_with_enrichment()  # replace with real data source later
    context = {
        "request": request,
        "meetings": meetings,
        "exec_name": "Biz Dev",
        "date_human": _today_et_str(),
        "current_year": datetime.now().strftime("%Y"),
    }
    return templates.TemplateResponse("digest.html", context)
