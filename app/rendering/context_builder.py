import os
import re
import logging
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Literal, Optional, List
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.calendar.provider import select_calendar_provider
from app.calendar.types import Event, Attendee
from app.data.sample_digest import SAMPLE_MEETINGS, STUB_MEETINGS_RAW_GRAPH
from app.rendering.digest_renderer import _today_et_str, _format_date_et_str, _get_timezone
from app.enrichment.service import enrich_meetings
from app.profile.store import get_profile
from app.memory.service import attach_memory_to_meetings
from app.research.config import (
    MAX_TAVILY_CALLS_PER_REQUEST,
    MAX_RESEARCH_SOURCES,
    ResearchBudget,
)
from app.research.query_safety import sanitize_research_query, is_query_usable_after_sanitization

logger = logging.getLogger(__name__)


def _normalize_url_for_dedup(url: str) -> str:
    """
    Normalize URL for deduplication: trim, lowercase scheme/host, remove trailing slash.
    Returns normalized string for comparison.
    """
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    url_lower = url.lower()
    # Normalize http/https to http for comparison (treat as equivalent)
    if url_lower.startswith("https://"):
        url_lower = "http://" + url_lower[8:]
    # Remove trailing slash
    if url_lower.endswith("/"):
        url_lower = url_lower[:-1]
    return url_lower


def _dedupe_and_cap_sources(sources: List[Dict[str, Any]], max_items: int = 5) -> List[Dict[str, Any]]:
    """
    Deduplicate sources by normalized URL and cap to max_items (preserve order).
    
    Args:
        sources: List of source dicts with 'title' and 'url' keys
        max_items: Maximum number of sources to return (default 5)
        
    Returns:
        Deduplicated and capped list of sources
    """
    if not sources:
        return []
    seen = set()
    deduped = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = s.get("url", "").strip()
        title = s.get("title", "").strip()
        if not url or not title:
            continue
        normalized = _normalize_url_for_dedup(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append({"title": title, "url": url})
            if len(deduped) >= max_items:
                break
    return deduped


def _format_time_for_display(iso_time: str) -> str:
    """Format ISO time string for display in digest."""
    try:
        # Extract time part (HH:MM)
        time_part = iso_time.split("T")[1].split("-")[0][:5]
        hour, minute = time_part.split(":")
        hour_int = int(hour)

        # Convert to 12-hour format
        if hour_int == 0:
            return f"12:{minute} AM ET"
        elif hour_int < 12:
            return f"{hour_int}:{minute} AM ET"
        elif hour_int == 12:
            return f"12:{minute} PM ET"
        else:
            return f"{hour_int - 12}:{minute} PM ET"
    except (ValueError, IndexError):
        # Fallback to original time if parsing fails
        return iso_time


def _apply_company_aliases(meetings: list[dict], aliases: Dict[str, List[str]]) -> list[dict]:
    """Apply company aliases to canonicalize company names for enrichment."""
    if not aliases:
        return meetings

    # Create reverse lookup: alias -> canonical name
    alias_to_canonical = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            alias_to_canonical[alias.lower()] = canonical.lower()

    for meeting in meetings:
        # Check company field
        if meeting.get("company") and isinstance(meeting["company"], dict):
            company_name = meeting["company"].get("name", "").lower()
            if company_name in alias_to_canonical:
                meeting["company"]["name"] = alias_to_canonical[company_name].title()

        # Check attendees for company names
        for attendee in meeting.get("attendees", []):
            if attendee.get("company"):
                company_name = attendee["company"].lower()
                if company_name in alias_to_canonical:
                    attendee["company"] = alias_to_canonical[company_name].title()

    return meetings


def _trim_meeting_sections(meetings: list, max_items: Dict[str, int]) -> list:
    """Trim meeting sections to respect max_items limits."""
    for meeting in meetings:
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'model_dump'):
            # Pydantic model - convert to dict, trim, then back to model
            meeting_dict = meeting.model_dump()
            for section, max_count in max_items.items():
                if section in meeting_dict and isinstance(meeting_dict[section], list):
                    meeting_dict[section] = meeting_dict[section][:max_count]

            # Update the model with trimmed data
            for section, max_count in max_items.items():
                if section in meeting_dict and isinstance(meeting_dict[section], list):
                    setattr(meeting, section, meeting_dict[section])
        else:
            # Regular dict
            for section, max_count in max_items.items():
                if section in meeting and isinstance(meeting[section], list):
                    meeting[section] = meeting[section][:max_count]

    return meetings


def _convert_raw_graph_to_events(raw_graph_events: List[dict]) -> List[Event]:
    """
    Convert raw Microsoft Graph API event shapes to Event objects.
    
    This mimics the conversion logic in MSGraphAdapter.fetch_events_between
    to ensure stub mode exercises the same transformation pipeline.
    
    Args:
        raw_graph_events: List of raw Graph API event dicts
        
    Returns:
        List of Event objects
    """
    et_tz = ZoneInfo("America/New_York")
    events = []
    
    for item in raw_graph_events:
        # Skip cancelled events (same as adapter)
        if item.get("isCancelled", False):
            continue
        
        try:
            # Parse start/end times (same logic as adapter)
            start_obj = item.get("start", {})
            start_dt_str = start_obj.get("dateTime", "")
            start_tz_str = start_obj.get("timeZone", "America/New_York")
            
            end_obj = item.get("end", {})
            end_dt_str = end_obj.get("dateTime", "")
            end_tz_str = end_obj.get("timeZone", "America/New_York")
            
            if not start_dt_str or not end_dt_str:
                continue
            
            # Parse datetime strings
            start_dt = datetime.fromisoformat(start_dt_str)
            end_dt = datetime.fromisoformat(end_dt_str)
            
            # Apply timezone if naive
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=ZoneInfo(start_tz_str))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=ZoneInfo(end_tz_str))
            
            # Convert to ET
            start_dt_et = start_dt.astimezone(et_tz)
            end_dt_et = end_dt.astimezone(et_tz)
            
            # Normalize attendees (same logic as adapter)
            attendees = []
            for attendee in item.get("attendees", []):
                email_address = attendee.get("emailAddress", {})
                name = email_address.get("name", "")
                email = email_address.get("address", "")
                
                # Extract company from email domain
                company = None
                if "@" in email:
                    domain = email.split("@")[1]
                    if domain and domain != "rpck.com":
                        company = domain.split(".")[0].title()
                
                attendees.append(Attendee(
                    name=name or email,
                    email=email,
                    company=company
                ))
            
            # Add organizer to attendees if not already there
            organizer = item.get("organizer", {}).get("emailAddress", {})
            organizer_email = organizer.get("address", "")
            organizer_name = organizer.get("name", "")
            
            if organizer_email:
                organizer_in_attendees = any(
                    (a.email or "").lower() == organizer_email.lower()
                    for a in attendees
                )
                if not organizer_in_attendees:
                    company = None
                    if "@" in organizer_email:
                        domain = organizer_email.split("@")[1]
                        if domain and domain != "rpck.com":
                            company = domain.split(".")[0].title()
                    attendees.append(Attendee(
                        name=organizer_name or organizer_email,
                        email=organizer_email,
                        company=company
                    ))
            
            # Extract location
            location = item.get("location", {}).get("displayName")
            
            # Extract notes
            notes = item.get("bodyPreview", "")
            if notes:
                notes = notes.strip()[:500]
            
            # Create Event object
            event = Event(
                subject=item.get("subject", ""),
                start_time=start_dt_et.isoformat(),
                end_time=end_dt_et.isoformat(),
                location=location,
                attendees=attendees,
                notes=notes,
                id=item.get("id"),
                organizer=organizer_email
            )
            
            events.append(event)
            
        except Exception as e:
            # Skip events that fail to parse (same as adapter)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to parse stub event: {e}")
            continue
    
    return events


def _map_events_to_meetings(events: list[dict] | list) -> list[dict]:
    meetings: list[dict] = []
    for e in events:
        # e is a pydantic model dict-like; support both dict and model
        subject = getattr(e, "subject", None) or e.get("subject", "")
        start_time = getattr(e, "start_time", None) or e.get("start_time", "")
        location = getattr(e, "location", None) or e.get("location")
        organizer = getattr(e, "organizer", None) or e.get("organizer")
        attendees_raw = getattr(e, "attendees", None) or e.get("attendees", [])
        attendees = []
        for a in attendees_raw:
            name = getattr(a, "name", None) or a.get("name", "")
            title = getattr(a, "title", None) or a.get("title")
            company = getattr(a, "company", None) or a.get("company")
            email = getattr(a, "email", None) or a.get("email")
            attendees.append({"name": name, "title": title, "company": company, "email": email})

        meetings.append(
            {
                "subject": subject,
                # For MVP, show only time component in ET readable form; use ISO string's time
                "start_time": _format_time_for_display(start_time) if "T" in start_time else start_time,
                "location": location,
                "organizer": organizer,
                "attendees": attendees,
                "company": None,
                "news": [],
                "talking_points": [],
                "smart_questions": [],
            }
        )
    return meetings


def build_digest_context_with_provider(
    source: Literal["sample", "live", "stub"],
    date: Optional[str] = None,
    exec_name: Optional[str] = None,
    mailbox: Optional[str] = None,
    *,
    allow_research: bool = False,
    research_budget: Optional[ResearchBudget] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    # Load executive profile (use mailbox if provided)
    profile = get_profile(mailbox=mailbox)

    # Determine which user's calendar to fetch
    # Use explicit mailbox parameter, or fall back to profile's mailbox field
    user_mailbox = mailbox
    if not user_mailbox and hasattr(profile, 'mailbox') and profile.mailbox:
        user_mailbox = profile.mailbox

    actual_source = "live"
    meetings: list[dict] = []

    if source == "live":
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Fetching live calendar events for date={requested_date}, user={user_mailbox}")
            provider = select_calendar_provider()
            provider_name = type(provider).__name__
            logger.info(f"Using calendar provider: {provider_name} (CALENDAR_PROVIDER={os.getenv('CALENDAR_PROVIDER', 'not set')})")
            # Pass mailbox/user to filter events for specific user
            events = provider.fetch_events(requested_date, user=user_mailbox)
            logger.info(f"Received {len(events)} events from provider {provider_name} for {requested_date}, mailbox={user_mailbox}")
            if events:
                meetings = _map_events_to_meetings([e.model_dump() for e in events])
                actual_source = "live"
                logger.info(f"Mapped to {len(meetings)} meetings")
            else:
                # No events for this date - meetings will be empty
                meetings = []
                actual_source = "live"
                logger.info(f"No events found for {requested_date}")
        except HTTPException:
            # Re-raise HTTPExceptions (e.g., 403, 401) so they propagate with correct status codes
            raise
        except Exception as e:
            # Provider error - log full exception with context
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(
                "PREVIEW_FAILED",
                extra={
                    "source": source,
                    "date": requested_date,
                    "mailbox": user_mailbox,
                    "error_type": type(e).__name__,
                }
            )
            raise HTTPException(status_code=500, detail="preview failed: PREVIEW_FAILED")
    elif source == "stub":
        # Stub mode - convert raw Graph shapes to Event objects, then through mapping pipeline
        # This ensures stub mode exercises the same transformation as live mode
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Using stub mode with {len(STUB_MEETINGS_RAW_GRAPH)} raw Graph events")
        
        # Convert raw Graph shapes to Event objects (same as adapter does)
        stub_events = _convert_raw_graph_to_events(STUB_MEETINGS_RAW_GRAPH)
        logger.info(f"Converted to {len(stub_events)} Event objects")
        
        # Pass through same mapping as live mode
        if stub_events:
            meetings = _map_events_to_meetings([e.model_dump() for e in stub_events])
            actual_source = "stub"
            logger.info(f"Mapped to {len(meetings)} meetings")
        else:
            meetings = []
            actual_source = "stub"
            logger.info("No valid stub events after conversion")
    else:
        # Sample mode - use sample data
        meetings = SAMPLE_MEETINGS
        actual_source = "sample"

    # Apply company aliases before enrichment
    meetings = _apply_company_aliases(meetings, profile.company_aliases)

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    # Apply profile max_items limits
    meetings_trimmed = _trim_meeting_sections(meetings_enriched, profile.max_items)

    # Attach memory data (past meetings) to each meeting
    meetings_with_memory = attach_memory_to_meetings(meetings_trimmed)

    # Format date_human based on requested date (or today if not specified)
    tz_name = _get_timezone()
    if requested_date:
        date_human = _format_date_et_str(requested_date, tz_name)
        # Extract year from requested date for current_year
        try:
            date_obj = datetime.strptime(requested_date, "%Y-%m-%d")
            current_year = date_obj.strftime("%Y")
        except ValueError:
            current_year = datetime.now().strftime("%Y")
    else:
        date_human = _today_et_str(tz_name)
        current_year = datetime.now().strftime("%Y")

    context = {
        "meetings": meetings_with_memory,
        "date_human": date_human,
        "current_year": current_year,
        "exec_name": exec_name or profile.exec_name,  # Use profile default unless overridden
        "source": actual_source,
    }
    req_id = request_id or str(uuid.uuid4())

    # Endpoint/call-site gating: research only when allow_research=True (digest preview, run-digest, digest send)
    if not allow_research:
        context["research"] = {"summary": "", "key_points": [], "sources": []}
        context["_research_computed"] = True
        logger.info("RESEARCH_SKIPPED", extra={"reason": "endpoint_guard", "request_id": req_id})
        return context

    # Research computed once here and attached to context; no later step should call provider again
    budget = research_budget if research_budget is not None else ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    context["_research_computed"] = False  # set True after we set context["research"]

    from app.research.selector import should_run_research, select_research_provider
    allowed, skip_reason = should_run_research()
    if not allowed:
        context["research"] = {"summary": "", "key_points": [], "sources": []}
        context["_research_computed"] = True
        logger.info("RESEARCH_SKIPPED", extra={"reason": skip_reason, "request_id": req_id})
        return context

    try:

            def _meeting_to_data(m: Any) -> Dict[str, Any]:
                """Normalize meeting to dict (handle Pydantic models)."""
                if hasattr(m, "model_dump"):
                    return m.model_dump()
                if hasattr(m, "dict"):
                    return m.dict()
                if isinstance(m, dict):
                    return m
                return {}

            def _domain_from_email(email: Any) -> str:
                """Extract domain from email string; empty if not present."""
                if not email:
                    return ""
                s = (email if isinstance(email, str) else str(email)).strip().lower()
                if "@" in s:
                    return s.split("@", 1)[1]
                return ""

            def _normalize_attendee(a: Any) -> Dict[str, Any]:
                """Normalize attendee to dict."""
                if isinstance(a, dict):
                    return a
                if hasattr(a, "model_dump"):
                    return a.model_dump()
                if hasattr(a, "dict"):
                    return a.dict()
                return {}

            def score_meeting_for_research(meeting_data: Dict[str, Any]) -> int:
                """Score meeting for research priority. Higher score = better candidate."""
                subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip().lower()
                
                # Skip internal/admin subjects
                skip_patterns = ["blocked time", "recap voice note", "complete forms", "admin", "internal hold"]
                if any(pattern in subject for pattern in skip_patterns):
                    return -9999
                
                score = 0
                
                # External organizer boost
                org = meeting_data.get("organizer")
                org_domain = _domain_from_email(org)
                has_external_org = org_domain and org_domain != "rpck.com"
                if has_external_org:
                    score += 30
                
                # External attendee boost (cap at +45 for 3+ external attendees)
                external_attendee_count = 0
                for a in meeting_data.get("attendees") or []:
                    ad = _normalize_attendee(a)
                    if not isinstance(ad, dict):
                        continue
                    email = ad.get("email") or ad.get("address")
                    dom = _domain_from_email(email)
                    if dom and dom != "rpck.com":
                        external_attendee_count += 1
                score += min(external_attendee_count * 15, 45)
                
                # Subject keyword boosts
                high_value_keywords = [
                    "intro", "introductory", "kickoff", "diligence", "closing",
                    "negotiation", "term sheet", "board", "investor", "financing",
                    "acquisition", "dispute", "arbitration"
                ]
                if any(kw in subject for kw in high_value_keywords):
                    score += 20
                
                if "call with" in subject or "meeting with" in subject:
                    score += 10
                
                negative_keywords = ["internal", "admin", "recap", "blocked", "hold"]
                if any(kw in subject for kw in negative_keywords):
                    score -= 15
                
                # Attendee count shaping
                attendee_count = len(meeting_data.get("attendees") or [])
                has_external = has_external_org or external_attendee_count > 0
                if 1 <= attendee_count <= 3 and has_external:
                    score += 10
                if attendee_count >= 8:
                    score -= 5
                
                return score

            def extract_counterparty_from_subject(subj: str) -> str:
                """Extract counterparty name from subject patterns like 'Call with X', 'Intro: X'."""
                if not subj or not subj.strip():
                    return ""
                subj = subj.strip()
                m = re.search(
                    r"^(?:call|meeting|intro|catch[- ]?up|1:1|one[- ]?on[- ]?one)\s+with\s+(.+)$",
                    subj,
                    re.IGNORECASE,
                )
                if m:
                    name = m.group(1).strip().rstrip(".,;:—-")
                    return name if name else ""
                m = re.search(r"^intro\s*[:\-]\s*(.+)$", subj, re.IGNORECASE)
                if m:
                    name = m.group(1).strip().rstrip(".,;:—-")
                    return name if name else ""
                return ""

            from app.research.anchor_utils import extract_org_from_subject, org_from_email_domain

            # Score all meetings and pick highest-scoring candidate
            candidate_meeting = None
            best_score = -9999
            for m in meetings_with_memory or []:
                data = _meeting_to_data(m)
                score = score_meeting_for_research(data)
                if score > best_score:
                    best_score = score
                    candidate_meeting = m

            if not candidate_meeting or best_score < 0:
                context["research"] = {"summary": "", "key_points": [], "sources": []}
                context["_research_computed"] = True
                logger.info("RESEARCH_SKIPPED", extra={"reason": "no_candidate", "request_id": req_id})
            else:
                meeting_data = _meeting_to_data(candidate_meeting)
                subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip()
                exec_name = (context.get("exec_name") or "").strip().lower()
                exec_mailbox = (user_mailbox or "").strip().lower()
                anchor = ""
                org_context = ""

                # a) Try counterparty from subject (must not be exec)
                counterparty_from_subject = extract_counterparty_from_subject(subject)
                if counterparty_from_subject and counterparty_from_subject.lower() != exec_name:
                    anchor = counterparty_from_subject.strip()

                # b) Else try org/project from subject
                if not anchor:
                    org_from_subj = extract_org_from_subject(subject)
                    if org_from_subj:
                        anchor = org_from_subj

                # c) Else if organizer is external, use org from organizer domain (prefer over person name)
                if not anchor:
                    org = meeting_data.get("organizer")
                    org_domain = _domain_from_email(org)
                    if org_domain and org_domain != "rpck.com":
                        anchor = org_from_email_domain(org_domain)

                # d) Else first external attendee: display_name + org_from_domain, or org_from_domain only
                if not anchor:
                    attendees_raw = meeting_data.get("attendees") or []
                    if attendees_raw and isinstance(attendees_raw, list):
                        for a in attendees_raw:
                            a_data = _normalize_attendee(a)
                            if not isinstance(a_data, dict):
                                continue
                            email = a_data.get("email") or a_data.get("address")
                            dom = _domain_from_email(email)
                            if not dom or dom == "rpck.com":
                                continue
                            display_name = (a_data.get("display_name") or a_data.get("name") or "").strip()
                            display_name = str(display_name) if display_name else ""
                            candidate_lower = display_name.lower()
                            if exec_name and candidate_lower == exec_name:
                                continue
                            if exec_mailbox and display_name and exec_mailbox in candidate_lower:
                                continue
                            attendee_org = org_from_email_domain(dom)
                            if display_name:
                                anchor = display_name
                                if attendee_org:
                                    org_context = attendee_org
                            else:
                                anchor = attendee_org
                            break

                if not anchor:
                    context["research"] = {"summary": "", "key_points": [], "sources": []}
                    context["_research_computed"] = True
                    logger.info("RESEARCH_SKIPPED", extra={"reason": "no_anchor", "request_id": req_id})
                else:
                    # Org/project-like: contains spaces and no comma-separated first/last
                    has_comma_first_last = "," in anchor and len(anchor.split(",")) == 2
                    anchor_has_spaces = " " in anchor
                    is_org_like = anchor_has_spaces and not has_comma_first_last
                    if is_org_like:
                        research_topic = f"{anchor} (organization, leadership, business, recent news)"
                    else:
                        person_part = f"{anchor} {org_context}".strip()
                        research_topic = f"{person_part} (role, company, recent news)"
                    if len(research_topic) > 120:
                        research_topic = research_topic[:117] + "..."
                    research_topic = sanitize_research_query(research_topic)
                    if not is_query_usable_after_sanitization(research_topic):
                        context["research"] = {"summary": "", "key_points": [], "sources": []}
                        context["_research_computed"] = True
                        logger.info("RESEARCH_SKIPPED", extra={"reason": "query_sanitized_empty", "request_id": req_id})
                    elif not budget.consume_one_or_false():
                        context["research"] = {"summary": "", "key_points": [], "sources": []}
                        context["_research_computed"] = True
                        logger.info("RESEARCH_SKIPPED", extra={"reason": "budget_exhausted", "request_id": req_id})
                    else:
                        provider = select_research_provider()
                        research_start = time.perf_counter()
                        try:
                            research_result = provider.get_research(research_topic)
                        except Exception:
                            research_result = {"summary": "", "key_points": [], "sources": []}
                        duration_ms = int((time.perf_counter() - research_start) * 1000)
                        if research_result.get("_duration_ms") is not None:
                            duration_ms = research_result.pop("_duration_ms", duration_ms)
                        if research_result.get("sources"):
                            research_result["sources"] = _dedupe_and_cap_sources(
                                research_result["sources"], max_items=MAX_RESEARCH_SOURCES
                            )
                        context["research"] = research_result
                        context["_research_computed"] = True
                        sources_count = len(context["research"].get("sources") or [])
                        key_points_count = len(context["research"].get("key_points") or [])
                        logger.info(
                            "RESEARCH_OK",
                            extra={
                                "duration_ms": duration_ms,
                                "sources_count": sources_count,
                                "key_points_count": key_points_count,
                                "request_id": req_id,
                            },
                        )

    except Exception as e:
        logger.exception(
            "RESEARCH_CONTEXT_FAILURE",
            extra={"error_type": type(e).__name__, "request_id": req_id}
        )
        context["research"] = {"summary": "", "key_points": [], "sources": []}
        context["_research_computed"] = True

    return context


def build_single_event_context(
    event_id: str,
    source: Literal["sample", "live"] = "sample",
    date: Optional[str] = None,
    exec_name: Optional[str] = None,
    mailbox: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context for a single event by ID.

    Args:
        event_id: The ID of the event to fetch
        source: Data source ("sample" or "live")
        date: Optional date for live data
        exec_name: Optional executive name override
        mailbox: Optional mailbox to determine profile

    Returns:
        Context dictionary with single meeting
    """
    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    # Load executive profile (use mailbox if provided)
    profile = get_profile(mailbox=mailbox)

    # Determine which user's calendar to fetch
    # Use explicit mailbox parameter, or fall back to profile's mailbox field
    user_mailbox = mailbox
    if not user_mailbox and hasattr(profile, 'mailbox') and profile.mailbox:
        user_mailbox = profile.mailbox

    actual_source = "sample"
    meeting: Optional[dict] = None

    if source == "live":
        try:
            provider = select_calendar_provider()
            # For now, we'll fetch all events and find by ID
            # In a real implementation, the provider would have a fetch_event_by_id method
            # Pass mailbox/user to filter events for specific user
            events = provider.fetch_events(requested_date, user=user_mailbox)
            if events:
                # Find event by ID (assuming event has an 'id' field)
                for event in events:
                    event_dict = event.model_dump() if hasattr(event, 'model_dump') else event
                    if event_dict.get('id') == event_id:
                        meetings = _map_events_to_meetings([event_dict])
                        if meetings:
                            meeting = meetings[0]
                            actual_source = "live"
                        break
        except HTTPException:
            # Re-raise HTTPExceptions (e.g., 403, 401) so they propagate with correct status codes
            raise
        except Exception as e:
            # Unexpected error - log and raise HTTPException
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(
                "PREVIEW_FAILED",
                extra={
                    "source": source,
                    "date": requested_date,
                    "mailbox": user_mailbox,
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                }
            )
            raise HTTPException(status_code=500, detail="preview failed: PREVIEW_FAILED")

    # If no meeting found in live data, try sample data
    if not meeting:
        # For sample data, we'll use a simple ID mapping
        # In a real implementation, sample data would have proper IDs
        if event_id == "sample-1" or event_id == "1":
            meeting = SAMPLE_MEETINGS[0].copy() if SAMPLE_MEETINGS else None
        else:
            # Create a basic meeting structure for unknown IDs
            meeting = {
                "subject": f"Meeting {event_id}",
                "start_time": "9:00 AM ET",
                "location": "Not specified",
                "attendees": [],
                "company": None,
                "news": [],
                "talking_points": [],
                "smart_questions": [],
            }

    if not meeting:
        # Create a minimal meeting structure for missing events
        meeting = {
            "subject": "Meeting not found",
            "start_time": "Not available",
            "location": "Not available",
            "attendees": [],
            "company": None,
            "news": [],
            "talking_points": [],
            "smart_questions": [],
        }

    # Apply company aliases before enrichment
    meetings = [meeting]
    meetings = _apply_company_aliases(meetings, profile.company_aliases)

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    # Apply profile max_items limits
    meetings_trimmed = _trim_meeting_sections(meetings_enriched, profile.max_items)

    # Attach memory data (past meetings) to each meeting
    meetings_with_memory = attach_memory_to_meetings(meetings_trimmed)

    # Format date_human based on requested date (or today if not specified)
    tz_name = _get_timezone()
    if requested_date:
        date_human = _format_date_et_str(requested_date, tz_name)
        # Extract year from requested date for current_year
        try:
            date_obj = datetime.strptime(requested_date, "%Y-%m-%d")
            current_year = date_obj.strftime("%Y")
        except ValueError:
            current_year = datetime.now().strftime("%Y")
    else:
        date_human = _today_et_str(tz_name)
        current_year = datetime.now().strftime("%Y")

    context = {
        "meetings": meetings_with_memory,
        "date_human": date_human,
        "current_year": current_year,
        "exec_name": exec_name or profile.exec_name,
        "source": actual_source,
        "event_id": event_id,  # Include event ID in context for reference
    }
    return context


