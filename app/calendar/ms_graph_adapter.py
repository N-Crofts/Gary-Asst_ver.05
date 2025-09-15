import os
import time
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from app.calendar.types import Event, Attendee


class MSGraphAdapter:
    """Microsoft Graph calendar adapter that fetches events and normalizes them to Event objects."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, user_email: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_email = user_email
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

    def fetch_events(self, date: str, tz: Optional[str] = None, user: Optional[str] = None) -> List[Event]:
        """
        Fetch calendar events for the given date from Microsoft Graph.

        Args:
            date: ISO date string (YYYY-MM-DD)
            tz: Timezone (ignored, always uses ET)
            user: User email (ignored, uses configured user_email)

        Returns:
            List of normalized Event objects
        """
        try:
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        # Get access token
        access_token = self._get_access_token()

        # Build Graph API URL for calendar events
        # Use the configured user email or the provided user
        target_user = user or self.user_email
        url = f"https://graph.microsoft.com/v1.0/users/{target_user}/calendar/events"

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
                    raise HTTPException(status_code=503, detail="MS Graph permission denied")
                elif response.status_code == 404:
                    raise HTTPException(status_code=503, detail="MS Graph user not found")

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
            raise HTTPException(status_code=503, detail=f"MS Graph API error: {exc}")


def create_ms_graph_adapter() -> MSGraphAdapter:
    """Factory function to create MSGraphAdapter from environment variables."""
    tenant_id = os.getenv("MS_TENANT_ID")
    client_id = os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("MS_CLIENT_SECRET")
    user_email = os.getenv("MS_USER_EMAIL")

    if not all([tenant_id, client_id, client_secret, user_email]):
        raise HTTPException(
            status_code=503,
            detail="MS Graph configuration missing: MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, MS_USER_EMAIL required"
        )

    return MSGraphAdapter(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        user_email=user_email
    )
