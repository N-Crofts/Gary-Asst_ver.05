from typing import Dict, Any, List


def render_plaintext(context: Dict[str, Any]) -> str:
    """
    Render a readable plaintext digest from the context.

    Args:
        context: Digest context with meetings and metadata

    Returns:
        Plaintext digest string
    """
    lines = []

    # Header
    lines.append("RPCK – Morning Briefing")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Prepared for {context.get('exec_name', 'Sorum Crofts')}")
    lines.append(f"Date: {context.get('date_human', '')}")
    lines.append("")

    # Legend
    lines.append("Legend: [Today] [Action-oriented]")
    lines.append("")

    meetings = context.get("meetings", [])
    if not meetings:
        lines.append("No meetings scheduled for today.")
        return "\n".join(lines)

    # Meetings
    for i, meeting in enumerate(meetings, 1):
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'model_dump'):
            # Pydantic model
            meeting_dict = meeting.model_dump()
            subject = meeting_dict.get("subject", "Untitled Meeting")
            start_time = meeting_dict.get("start_time", "")
            location = meeting_dict.get("location", "")
            attendees = meeting_dict.get("attendees", [])
            company = meeting_dict.get("company")
            news = meeting_dict.get("news", [])
            context_summary = meeting_dict.get("context_summary")
            industry_signal = meeting_dict.get("industry_signal")
            strategic_angles = meeting_dict.get("strategic_angles", [])
            high_leverage_questions = meeting_dict.get("high_leverage_questions", [])
            research_trace = meeting_dict.get("research_trace")
            memory = meeting_dict.get("memory")
        else:
            # Regular dict
            subject = meeting.get("subject", "Untitled Meeting")
            start_time = meeting.get("start_time", "")
            location = meeting.get("location", "")
            attendees = meeting.get("attendees", [])
            company = meeting.get("company")
            news = meeting.get("news", [])
            context_summary = meeting.get("context_summary")
            industry_signal = meeting.get("industry_signal")
            strategic_angles = meeting.get("strategic_angles", [])
            high_leverage_questions = meeting.get("high_leverage_questions", [])
            research_trace = meeting.get("research_trace")
            memory = meeting.get("memory")

        lines.append(f"Meeting {i}: {subject}")
        lines.append("-" * 60)

        # Time and location
        if start_time:
            lines.append(f"Starts: {start_time}")
        if location:
            lines.append(f"Location: {location}")
        lines.append("")

        # Attendees
        if attendees:
            lines.append("Attendees:")
            for attendee in attendees:
                name = attendee.get("name", "")
                title = attendee.get("title", "")
                attendee_company = attendee.get("company", "")

                attendee_line = f"  • {name}"
                if title:
                    attendee_line += f", {title}"
                if attendee_company:
                    attendee_line += f" ({attendee_company})"
                lines.append(attendee_line)
            lines.append("")

        # Company
        if company:
            # Handle both dict and Pydantic model
            if hasattr(company, 'model_dump'):
                # Pydantic model
                company_dict = company.model_dump()
                company_name = company_dict.get("name", "")
                one_liner = company_dict.get("one_liner", "")
            elif isinstance(company, dict):
                # Regular dict
                company_name = company.get("name", "")
                one_liner = company.get("one_liner", "")
            else:
                # Skip if company is not a dict or model (e.g., string)
                company_name = ""
                one_liner = ""

            if company_name:
                lines.append("Company:")
                lines.append(f"  {company_name}")
                if one_liner:
                    lines.append(f"  {one_liner}")
                lines.append("")

        # 1) Context Snapshot
        has_context = context_summary or news or industry_signal or strategic_angles or high_leverage_questions
        lines.append("Context Snapshot:")
        if has_context:
            if context_summary:
                lines.append(f"  {context_summary}")
            if news:
                lines.append("  Recent developments:")
                for item in news:
                    if isinstance(item, dict):
                        title = item.get("title", "")
                        url = item.get("url", "")
                        if title and url:
                            lines.append(f"    • {title} ({url})")
                        elif title:
                            lines.append(f"    • {title}")
                    else:
                        lines.append(f"    • {item}")
            if industry_signal:
                lines.append(f"  Industry signal: {industry_signal}")
        else:
            lines.append("  No external context available")
        # Dev-only anchor diagnostics (non-PII)
        app_env = context.get("app_env", "").strip().lower()
        enable_research_dev = context.get("enable_research_dev", False)
        if research_trace and (app_env == "development" or enable_research_dev):
            anchor_type = research_trace.get("anchor_type") or "—"
            primary_domain = research_trace.get("primary_domain") or "—"
            dm = research_trace.get("domain_match_passed")
            domain_match_str = "true" if dm is True else ("false" if dm is False else "—")
            match_url = (research_trace.get("domain_match_url") or "—") if dm is True else "—"
            top_hosts = research_trace.get("top_source_hosts") or []
            hosts_str = ",".join(top_hosts[:3]) if top_hosts else "—"
            part = f"  [Dev] Anchor={anchor_type} | domain={primary_domain} | domain_match={domain_match_str} | match_url={match_url} | hosts={hosts_str}"
            em = research_trace.get("entity_match_passed")
            if em is not None:
                part += f" | entity_match={'true' if em else 'false'}"
            if research_trace.get("skip_reason"):
                part += f" | skip={research_trace.get('skip_reason')}"
            if research_trace.get("mismatch_reason"):
                part += f" | mismatch={research_trace.get('mismatch_reason')}"
            if research_trace.get("retry_used"):
                part += " | retry=true"
            if research_trace.get("outcome") == "error":
                part += " | outcome=error"
            lines.append(part)
        lines.append("")

        # 2) Strategic Angles (only if data; no filler)
        if strategic_angles:
            lines.append("Strategic Angles:")
            for a in strategic_angles:
                lines.append(f"  • {a}")
            lines.append("")

        # 3) High-Leverage Questions (only if data; no filler)
        if high_leverage_questions:
            lines.append("High-Leverage Questions:")
            for q in high_leverage_questions:
                lines.append(f"  • {q}")
            lines.append("")

        # Memory (Recent with them)
        if memory and isinstance(memory, dict):
            previous_meetings = memory.get("previous_meetings", [])
            if previous_meetings:
                lines.append("Recent with them:")
                for past_meeting in previous_meetings:
                    if isinstance(past_meeting, dict):
                        date = past_meeting.get("date", "")
                        subject = past_meeting.get("subject", "")
                        key_attendees = past_meeting.get("key_attendees", [])

                        meeting_line = f"  • {date} — {subject}"
                        if key_attendees:
                            attendees_str = ", ".join(key_attendees)
                            meeting_line += f" (with {attendees_str})"
                        lines.append(meeting_line)
                lines.append("")

        # Separator between meetings
        if i < len(meetings):
            lines.append("")
            lines.append("=" * 60)
            lines.append("")

    # Footer
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"© {context.get('current_year', '2025')} RPCK Rastegar Panchal LLP — Internal briefing.")
    lines.append("If anything looks off, reply and I'll regenerate with fixes.")

    return "\n".join(lines)


def _format_attendees_plaintext(attendees: List[Dict[str, Any]]) -> str:
    """
    Format attendees list for plaintext.

    Args:
        attendees: List of attendee dictionaries

    Returns:
        Formatted attendees string
    """
    if not attendees:
        return ""

    formatted = []
    for attendee in attendees:
        name = attendee.get("name", "")
        title = attendee.get("title", "")
        company = attendee.get("company", "")

        attendee_str = name
        if title:
            attendee_str += f", {title}"
        if company:
            attendee_str += f" ({company})"

        formatted.append(attendee_str)

    return "; ".join(formatted)


def _format_news_plaintext(news: List[Any]) -> str:
    """
    Format news items for plaintext with URLs.

    Args:
        news: List of news items (dicts or strings)

    Returns:
        Formatted news string
    """
    if not news:
        return ""

    formatted = []
    for item in news:
        if isinstance(item, dict):
            title = item.get("title", "")
            url = item.get("url", "")
            if title and url:
                formatted.append(f"{title} ({url})")
            elif title:
                formatted.append(title)
        else:
            # Back-compat for plain strings
            formatted.append(str(item))

    return "\n".join(formatted)
