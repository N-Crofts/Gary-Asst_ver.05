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
            talking_points = meeting_dict.get("talking_points", [])
            smart_questions = meeting_dict.get("smart_questions", [])
            memory = meeting_dict.get("memory")
        else:
            # Regular dict
            subject = meeting.get("subject", "Untitled Meeting")
            start_time = meeting.get("start_time", "")
            location = meeting.get("location", "")
            attendees = meeting.get("attendees", [])
            company = meeting.get("company")
            news = meeting.get("news", [])
            talking_points = meeting.get("talking_points", [])
            smart_questions = meeting.get("smart_questions", [])
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

        # News
        if news:
            lines.append("Recent news:")
            for item in news:
                if isinstance(item, dict):
                    title = item.get("title", "")
                    url = item.get("url", "")
                    if title and url:
                        lines.append(f"  • {title} ({url})")
                    elif title:
                        lines.append(f"  • {title}")
                else:
                    # Back-compat for plain strings
                    lines.append(f"  • {item}")
            lines.append("")

        # Talking points
        if talking_points:
            lines.append("Talking points (prioritize):")
            for j, point in enumerate(talking_points, 1):
                lines.append(f"  {j}. {point}")
            lines.append("")

        # Smart questions
        if smart_questions:
            lines.append("Smart questions:")
            for j, question in enumerate(smart_questions, 1):
                lines.append(f"  {j}. {question}")
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
