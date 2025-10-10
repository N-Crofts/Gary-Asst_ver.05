import os
import time
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from app.calendar.types import Event, Attendee
from app.core.config import load_config


class MSGraphAdapter:
    """Microsoft Graph calendar adapter that fetches events and normalizes them to Event objects."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, user_email: Optional[str] = None, allowed_mailbox_group: Optional[str] = None):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_email = user_email
        self.allowed_mailbox_group = allowed_mailbox_group
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _get_access_token(self) -> str:
        """Get or refresh access token using client credentials flow."""
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:  # Refresh 1min early
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }

        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(token_url, data=data)
                response.raise_for_status()
                token_data = response.json()

                self._access_token = token_data["access_token"]
                self._token_expires_at = now + token_data.get("expires_in", 3600)
                return self._access_token
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"MS Graph auth failed: {exc}")

    def _convert_to_et_time(self, graph_datetime: str) -> str:
        """Convert Graph ISO datetime to ET time string like '9:30 AM ET'."""
        try:
            # Parse the Graph datetime (assumes it's in UTC or has timezone info)
            dt = datetime.fromisoformat(graph_datetime.replace('Z', '+00:00'))

            # Convert to ET
            et_tz = ZoneInfo("America/New_York")
            et_dt = dt.astimezone(et_tz)

            # Format as "9:30 AM ET" (handle Windows strftime limitations)
            hour = et_dt.hour
            if hour == 0:
                hour = 12
            elif hour > 12:
                hour = hour - 12
            minute = et_dt.minute
            am_pm = "AM" if et_dt.hour < 12 else "PM"
            return f"{hour}:{minute:02d} {am_pm} ET"
        except Exception:
            # Fallback: return original string if parsing fails
            return graph_datetime

    def _normalize_attendees(self, graph_attendees: List[dict]) -> List[Attendee]:
        """Normalize Graph attendees to Attendee objects."""
        attendees = []
        for attendee in graph_attendees or []:
            email_address = attendee.get("emailAddress", {})
            name = email_address.get("name", "")
            email = email_address.get("address", "")

            # Extract company from email domain if no explicit company
            company = None
            if email and "@" in email:
                domain = email.split("@")[1]
                if domain and domain != "rpck.com":  # Don't show RPCK as company
                    company = domain.split(".")[0].title()

            attendees.append(Attendee(
                name=name,
                email=email,
                company=company
            ))

        return attendees

    def _get_group_members(self, group_id: str) -> List[str]:
        """Fetch all members of a security group."""
        access_token = self._get_access_token()

        # First, get the group object to find its ID
        group_url = f"https://graph.microsoft.com/v1.0/groups"
        params = {"$filter": f"displayName eq '{group_id}'"}
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=15) as client:
                response = client.get(group_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                if not data.get("value"):
                    raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

                group_object_id = data["value"][0]["id"]

                # Now get the members of the group
                members_url = f"https://graph.microsoft.com/v1.0/groups/{group_object_id}/members"
                members_params = {"$select": "mail,userPrincipalName"}

                response = client.get(members_url, headers=headers, params=members_params)
                response.raise_for_status()
                members_data = response.json()

                # Extract email addresses from members
                member_emails = []
                for member in members_data.get("value", []):
                    # Prefer mail field, fallback to userPrincipalName
                    email = member.get("mail") or member.get("userPrincipalName")
                    if email:
                        member_emails.append(email)

                return member_emails

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to fetch group members: {exc}")

    def _fetch_events_for_user(self, user_email: str, date: str) -> List[Event]:
        """Fetch events for a specific user."""
        access_token = self._get_access_token()

        # Build Graph API URL for calendar events
        url = f"https://graph.microsoft.com/v1.0/users/{user_email}/calendar/events"

        # Calculate start and end of day in ET
        et_tz = ZoneInfo("America/New_York")
        start_of_day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=et_tz)
        end_of_day = start_of_day.replace(hour=23, minute=59, second=59)

        # Convert to UTC for Graph API
        start_utc = start_of_day.astimezone(ZoneInfo("UTC"))
        end_utc = end_of_day.astimezone(ZoneInfo("UTC"))

        params = {
            "startDateTime": start_utc.isoformat(),
            "endDateTime": end_utc.isoformat(),
            "$select": "subject,start,end,location,attendees,bodyPreview",
            "$orderby": "start/dateTime"
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=15) as client:
                response = client.get(url, headers=headers, params=params)

                if response.status_code == 401:
                    raise HTTPException(status_code=503, detail="MS Graph authentication failed")
                elif response.status_code == 403:
                    # Permission denied for this user - skip silently
                    return []
                elif response.status_code == 404:
                    # User not found - skip silently
                    return []

                response.raise_for_status()
                data = response.json()

                events = []
                for item in data.get("value", []):
                    # Extract start/end times
                    start_time = item.get("start", {}).get("dateTime", "")
                    end_time = item.get("end", {}).get("dateTime", "")

                    # Convert to ET time strings
                    start_et = self._convert_to_et_time(start_time)
                    end_et = self._convert_to_et_time(end_time)

                    # Normalize attendees
                    attendees = self._normalize_attendees(item.get("attendees", []))

                    # Extract location
                    location = item.get("location", {}).get("displayName")

                    # Extract notes (bodyPreview, trimmed)
                    notes = item.get("bodyPreview", "")
                    if notes:
                        notes = notes.strip()[:500]  # Limit length

                    events.append(Event(
                        subject=item.get("subject", ""),
                        start_time=start_et,
                        end_time=end_et,
                        location=location,
                        attendees=attendees,
                        notes=notes
                    ))

                return events

        except HTTPException:
            raise
        except Exception as exc:
            # For individual user errors, return empty list rather than failing completely
            return []

    def fetch_events(self, date: str, tz: Optional[str] = None, user: Optional[str] = None) -> List[Event]:
        """
        Fetch calendar events for the given date from Microsoft Graph.

        Args:
            date: ISO date string (YYYY-MM-DD)
            tz: Timezone (ignored, always uses ET)
            user: User email (ignored, uses configured user_email or group members)

        Returns:
            List of normalized Event objects
        """
        try:
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        all_events = []

        # If group-based access is configured, fetch events for all group members
        if self.allowed_mailbox_group:
            try:
                # Get all members of the allowed group
                group_members = self._get_group_members(self.allowed_mailbox_group)

                # Fetch events for each group member
                for member_email in group_members:
                    try:
                        member_events = self._fetch_events_for_user(member_email, date)
                        all_events.extend(member_events)
                    except Exception:
                        # Skip individual user errors, continue with other members
                        continue

            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"Failed to fetch group events: {exc}")

        # If single user is configured, fetch events for that user
        elif self.user_email:
            try:
                user_events = self._fetch_events_for_user(self.user_email, date)
                all_events.extend(user_events)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"Failed to fetch user events: {exc}")

        else:
            raise HTTPException(
                status_code=503,
                detail="MS Graph configuration missing: Either MS_USER_EMAIL or ALLOWED_MAILBOX_GROUP must be provided"
            )

        # Sort all events by start time (convert to sortable format)
        def get_sortable_time(event):
            # Extract time from "9:30 AM ET" format for proper sorting
            time_str = event.start_time
            if "AM" in time_str or "PM" in time_str:
                # Convert "9:30 AM ET" to sortable format
                time_part = time_str.split(" ")[0]  # "9:30"
                am_pm = time_str.split(" ")[1]     # "AM"
                hour, minute = time_part.split(":")
                hour = int(hour)
                if am_pm == "PM" and hour != 12:
                    hour += 12
                elif am_pm == "AM" and hour == 12:
                    hour = 0
                return f"{hour:02d}:{minute}"
            return time_str

        all_events.sort(key=get_sortable_time)

        return all_events


def create_ms_graph_adapter() -> MSGraphAdapter:
    """Factory function to create MSGraphAdapter from environment variables."""
    tenant_id = os.getenv("MS_TENANT_ID")
    client_id = os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("MS_CLIENT_SECRET")
    user_email = os.getenv("MS_USER_EMAIL")
    allowed_mailbox_group = os.getenv("ALLOWED_MAILBOX_GROUP")

    if not all([tenant_id, client_id, client_secret]):
        raise HTTPException(
            status_code=503,
            detail="MS Graph configuration missing: MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET required"
        )

    # Either user_email or allowed_mailbox_group must be provided
    if not user_email and not allowed_mailbox_group:
        raise HTTPException(
            status_code=503,
            detail="MS Graph configuration missing: Either MS_USER_EMAIL or ALLOWED_MAILBOX_GROUP must be provided"
        )

    return MSGraphAdapter(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        user_email=user_email,
        allowed_mailbox_group=allowed_mailbox_group
    )
