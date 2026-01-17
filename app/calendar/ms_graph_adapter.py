import os
import time
import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from app.calendar.types import Event, Attendee

logger = logging.getLogger(__name__)
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

        # Ensure tenant_id is clean (no whitespace, proper format)
        tenant_id = self.tenant_id.strip()
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        logger.info(f"Requesting MS Graph token - tenant_id: {tenant_id}, client_id: {self.client_id[:8]}...{self.client_id[-8:]}")
        logger.debug(f"Token URL: {token_url}")

        data = {
            "client_id": self.client_id.strip(),
            "client_secret": self.client_secret.strip(),
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }

        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(token_url, data=data)

                # Log response details for debugging
                if response.status_code != 200:
                    logger.error(f"MS Graph token request failed: {response.status_code}")
                    logger.error(f"Request URL was: {token_url}")
                    logger.error(f"Tenant ID used: {repr(tenant_id)} (length: {len(tenant_id)})")
                    logger.error(f"Response text: {response.text[:500]}")
                    try:
                        error_data = response.json()
                        logger.error(f"Error details: {error_data}")
                        # Extract the actual tenant ID from error if available
                        if "error_description" in error_data:
                            logger.error(f"Full error description: {error_data['error_description']}")
                    except:
                        pass

                response.raise_for_status()
                token_data = response.json()

                self._access_token = token_data["access_token"]
                self._token_expires_at = now + token_data.get("expires_in", 3600)
                logger.debug("Successfully acquired MS Graph access token")
                return self._access_token
        except httpx.HTTPStatusError as exc:
            error_detail = f"MS Graph auth failed: {exc.response.status_code}"
            try:
                error_json = exc.response.json()
                if "error_description" in error_json:
                    error_detail += f" - {error_json['error_description']}"
                elif "error" in error_json:
                    error_detail += f" - {error_json['error']}"
            except:
                error_detail += f" - {exc.response.text[:200]}"
            logger.error(error_detail, exc_info=True)
            raise HTTPException(status_code=503, detail=error_detail)
        except Exception as exc:
            logger.error(f"MS Graph authentication failed: {exc}", exc_info=True)
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
            "$select": "subject,start,end,location,attendees,bodyPreview,organizer",
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
                    logger.error(f"MS Graph authentication failed for {user_email} on {date}")
                    raise HTTPException(status_code=503, detail="MS Graph authentication failed")
                elif response.status_code == 403:
                    # Permission denied for this user
                    logger.warning(f"Permission denied accessing calendar for {user_email} on {date}. Response: {response.text[:200]}")
                    return []
                elif response.status_code == 404:
                    # User not found
                    logger.warning(f"User not found: {user_email} on {date}")
                    return []

                response.raise_for_status()
                data = response.json()
                raw_events_count = len(data.get('value', []))
                logger.info(f"Successfully fetched {raw_events_count} raw events from Graph API for {user_email} on {date}")

                events = []
                # Parse the requested date for strict filtering
                requested_date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                logger.info(f"Filtering events to only those starting on {requested_date_obj} with {user_email} as attendee/organizer")

                # Normalize user email for comparison (lowercase)
                user_email_lower = user_email.lower()

                for item in data.get("value", []):
                    # Extract start/end times
                    start_time = item.get("start", {}).get("dateTime", "")
                    end_time = item.get("end", {}).get("dateTime", "")

                    # Skip if no start time
                    if not start_time:
                        continue

                    # Parse the start time to get the actual date
                    try:
                        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        # Convert to ET to get the date
                        start_et_dt = start_dt.astimezone(et_tz)
                        event_date = start_et_dt.date()

                        # Strict date filtering: only include events that start on the requested date
                        if event_date != requested_date_obj:
                            logger.info(f"Skipping event '{item.get('subject', '')}' - starts on {event_date}, requested {requested_date_obj}")
                            continue
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Could not parse start time '{start_time}' for event '{item.get('subject', '')}': {e}")
                        continue

                    # Normalize attendees
                    attendees = self._normalize_attendees(item.get("attendees", []))

                    # Filter: only include events where the user is an attendee
                    user_is_attendee = False
                    attendee_emails = []
                    for attendee in attendees:
                        attendee_email = (attendee.email or "").lower()
                        attendee_emails.append(attendee_email)
                        if attendee_email == user_email_lower:
                            user_is_attendee = True
                            logger.debug(f"User {user_email} found in attendees for event '{item.get('subject', '')}'")
                            break

                    # Also check if the user is the organizer (organizer email might not be in attendees)
                    organizer = item.get("organizer", {}).get("emailAddress", {})
                    organizer_email = (organizer.get("address", "") or "").lower()
                    if organizer_email == user_email_lower:
                        user_is_attendee = True
                        logger.debug(f"User {user_email} is organizer for event '{item.get('subject', '')}'")

                    if not user_is_attendee:
                        logger.info(f"Skipping event '{item.get('subject', '')}' - user {user_email} is not an attendee/organizer. Attendees: {attendee_emails}, Organizer: {organizer_email}")
                        continue

                    # Convert to ET time strings
                    start_et = self._convert_to_et_time(start_time)
                    end_et = self._convert_to_et_time(end_time)

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

                logger.info(f"After filtering: {len(events)} events for {user_email} on {date} (started on date and user is attendee)")
                return events

        except HTTPException:
            raise
        except Exception as exc:
            # For individual user errors, log and return empty list rather than failing completely
            logger.warning(f"Error fetching events for {user_email} on {date}: {exc}", exc_info=True)
            return []

    def fetch_events(self, date: str, user: Optional[str] = None) -> List[Event]:
        """
        Fetch calendar events for the given date from Microsoft Graph.

        Args:
            date: ISO date string (YYYY-MM-DD)
            user: Optional user email to filter events for a specific user.
                  If provided, only fetches events for that user.
                  If None, uses configured user_email or fetches for all group members.

        Returns:
            List of normalized Event objects
        """
        try:
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Invalid date format: {date}")
            return []

        all_events = []

        # If a specific user is requested, fetch events only for that user
        if user:
            logger.info(f"Fetching events for requested user '{user}' on {date}")
            try:
                user_events = self._fetch_events_for_user(user, date)
                all_events.extend(user_events)
                logger.info(f"Total events fetched for {user}: {len(all_events)}")
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(f"Failed to fetch events for user {user}: {exc}", exc_info=True)
                raise HTTPException(status_code=503, detail=f"Failed to fetch events for user {user}: {exc}")
            return all_events

        # If group-based access is configured, fetch events for all group members
        if self.allowed_mailbox_group:
            logger.info(f"Fetching events for group '{self.allowed_mailbox_group}' on {date}")
            try:
                # Get all members of the allowed group
                group_members = self._get_group_members(self.allowed_mailbox_group)
                logger.info(f"Found {len(group_members)} members in group '{self.allowed_mailbox_group}'")

                # Fetch events for each group member
                for member_email in group_members:
                    try:
                        member_events = self._fetch_events_for_user(member_email, date)
                        all_events.extend(member_events)
                    except Exception as e:
                        # Skip individual user errors, continue with other members
                        logger.warning(f"Error fetching events for group member {member_email}: {e}")
                        continue

            except HTTPException:
                raise
            except Exception as exc:
                logger.error(f"Failed to fetch group events: {exc}", exc_info=True)
                raise HTTPException(status_code=503, detail=f"Failed to fetch group events: {exc}")

        # If single user is configured, fetch events for that user
        elif self.user_email:
            logger.info(f"Fetching events for user '{self.user_email}' on {date}")
            try:
                user_events = self._fetch_events_for_user(self.user_email, date)
                all_events.extend(user_events)
                logger.info(f"Total events fetched: {len(all_events)}")
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(f"Failed to fetch user events: {exc}", exc_info=True)
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
    # Support both MS_* and AZURE_* naming conventions
    tenant_id = (os.getenv("MS_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or "").strip()
    client_id = (os.getenv("MS_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("MS_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") or "").strip()
    user_email = (os.getenv("MS_USER_EMAIL") or "").strip() or None
    allowed_mailbox_group = (os.getenv("ALLOWED_MAILBOX_GROUP") or "").strip() or None

    logger.debug(f"Creating MS Graph adapter - tenant_id: {tenant_id[:8]}...{tenant_id[-8:] if len(tenant_id) > 16 else tenant_id}, client_id: {client_id[:8]}...{client_id[-8:] if len(client_id) > 16 else client_id}")

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
