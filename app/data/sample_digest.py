SAMPLE_MEETINGS = [
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
            {"title": "GridFlow B led by Acme; overlap with RPCK client", "url": "https://example.com/gridflow-b"},
            {"title": "Acme announces climate infrastructure partnership", "url": "https://example.com/infra-partnership"},
        ],
        "talking_points": [
            "Confirm Q4 fund-formation timeline & counsel needs.",
            "Explore co-marketing with GridFlow case study.",
            "Flag cross-border structuring considerations early.",
        ],
        "smart_questions": [
            "What milestones unlock the next capital call?",
            "Any portfolio companies evaluating EU/US entity changes in 2025?",
            "Where is the biggest regulatory friction next 2 quarters?",
        ],
    }
]

# Stub meetings for POST /run-digest with source=stub
# Raw Microsoft Graph API event shapes (before transformation to Event objects)
# These mimic exactly what Graph API returns from /calendarView endpoint
STUB_MEETINGS_RAW_GRAPH = [
    {
        "id": "stub-event-1",
        "subject": "Stub: Acme Capital Check-in",
        "start": {
            "dateTime": "2025-02-18T09:30:00",
            "timeZone": "America/New_York"
        },
        "end": {
            "dateTime": "2025-02-18T10:30:00",
            "timeZone": "America/New_York"
        },
        "location": {
            "displayName": "Zoom"
        },
        "attendees": [
            {
                "emailAddress": {
                    "name": "Jane Doe",
                    "address": "jane.doe@acmecapital.com"
                }
            }
        ],
        "organizer": {
            "emailAddress": {
                "name": "Sorum Crofts",
                "address": "sorum.crofts@rpck.com"
            }
        },
        "isCancelled": False,
        "bodyPreview": ""
    },
    {
        "id": "stub-event-2",
        "subject": "Stub: Beta Corp Intro",
        "start": {
            "dateTime": "2025-02-18T14:00:00",
            "timeZone": "America/New_York"
        },
        "end": {
            "dateTime": "2025-02-18T15:00:00",
            "timeZone": "America/New_York"
        },
        "location": {
            "displayName": "Microsoft Teams"
        },
        "attendees": [
            {
                "emailAddress": {
                    "name": "John Smith",
                    "address": "john.smith@betacorp.com"
                }
            }
        ],
        "organizer": {
            "emailAddress": {
                "name": "Sorum Crofts",
                "address": "sorum.crofts@rpck.com"
            }
        },
        "isCancelled": False,
        "bodyPreview": ""
    },
]


