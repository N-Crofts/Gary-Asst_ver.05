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

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, user_email: Optional[str] = None, allowed_mailbox_group: Optional[str] = None, allowed_mailboxes: Optional[List[str]] = None):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_email = user_email
        self.allowed_mailbox_group = allowed_mailbox_group
        self.allowed_mailboxes = allowed_mailboxes or []
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        
        # Log allowed mailboxes at startup
        if self.allowed_mailboxes:
            logger.info(f"Allowed mailboxes: {self.allowed_mailboxes}")
        else:
            logger.warning("No allowed mailboxes configured - all mailbox access will be denied")

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

    def _parse_403_error(self, response: httpx.Response, user_email: str) -> str:
        """
        Parse Graph 403 error response to determine if it's an Application Access Policy issue.
        
        Args:
            response: HTTP response with status_code 403
            user_email: User email that was being accessed
            
        Returns:
            Clear, actionable error message string
        """
        try:
            error_data = response.json()
            error_obj = error_data.get("error", {})
            error_code = error_obj.get("code", "")
            error_message = error_obj.get("message", "")
            
            # Log error details (short version, no secrets)
            logger.error(f"Graph 403 error details - code: {error_code}, message: {error_message[:200]}")
            
            # Check if this is an Application Access Policy error
            if error_code == "ErrorAccessDenied":
                error_message_lower = error_message.lower()
                policy_keywords = [
                    "apponly accesspolicy",
                    "access to odata is disabled",
                    "blocked by tenant configured apponly accesspolicy settings"
                ]
                
                if any(keyword in error_message_lower for keyword in policy_keywords):
                    return (
                        f"Tenant policy blocks app-only access to mailbox {user_email} "
                        "(Application Access Policy). Ask IT to add the mailbox to the app's allowed scope."
                    )
            
            # Generic 403 error
            return f"Access denied to calendar for {user_email}. Error: {error_code}"
            
        except Exception as e:
            # If we can't parse the error response, return generic message
            logger.warning(f"Failed to parse Graph 403 error response: {e}")
            return f"Access denied to calendar for {user_email}"

    def _validate_mailbox_access(self, mailbox: str) -> None:
        """
        Validate that the requested mailbox is in the allowlist.
        
        Args:
            mailbox: Mailbox email address to validate
            
        Raises:
            ValueError: If mailbox is not in allowlist
        """
        if not mailbox:
            raise ValueError("Mailbox cannot be empty")
        
        mailbox_lower = mailbox.strip().lower()
        
        if not self.allowed_mailboxes:
            raise ValueError(f"Mailbox access denied: No allowed mailboxes configured. Requested: {mailbox}")
        
        if mailbox_lower not in self.allowed_mailboxes:
            raise ValueError(f"Mailbox access denied: {mailbox} is not in allowlist. Allowed: {self.allowed_mailboxes}")

    def _parse_graph_datetime(self, graph_datetime_obj: dict) -> datetime:
        """
        Parse Graph datetime object to timezone-aware datetime in ET.
        
        Args:
            graph_datetime_obj: Graph datetime object with 'dateTime' and 'timeZone' fields
            
        Returns:
            timezone-aware datetime in America/New_York timezone
        """
        et_tz = ZoneInfo("America/New_York")
        
        # Get the datetime string and timezone from Graph response
        dt_str = graph_datetime_obj.get("dateTime", "")
        tz_str = graph_datetime_obj.get("timeZone", "UTC")
        
        if not dt_str:
            raise ValueError("Missing dateTime in Graph response")
        
        # Parse the datetime string (Graph returns it in the requested timezone when Prefer header is used)
        try:
            # Handle Z suffix (UTC)
            if dt_str.endswith('Z'):
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            else:
                # Parse as-is (should already be in ET if Prefer header was used)
                dt = datetime.fromisoformat(dt_str)
            
            # If timezone info is missing, assume it's in the timeZone specified
            if dt.tzinfo is None:
                # Graph returned naive datetime, use the timeZone field
                if tz_str == "UTC" or tz_str == "Etc/UTC":
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                else:
                    # Try to parse the timezone
                    try:
                        dt = dt.replace(tzinfo=ZoneInfo(tz_str))
                    except:
                        # Fallback to UTC if timezone parsing fails
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            
            # Convert to ET timezone
            et_dt = dt.astimezone(et_tz)
            return et_dt
            
        except Exception as e:
            logger.error(f"Failed to parse datetime '{dt_str}' with timezone '{tz_str}': {e}")
            raise ValueError(f"Invalid datetime format: {dt_str}") from e

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

    def fetch_events_between(self, user_email: str, start_dt: datetime, end_dt: datetime) -> List[Event]:
        """
        Fetch calendar events between two datetime objects (timezone-aware).
        
        Args:
            user_email: User email to fetch events for
            start_dt: Start datetime (timezone-aware)
            end_dt: End datetime (timezone-aware)
            
        Returns:
            List of Event objects with ISO datetime strings in ET timezone
            
        Raises:
            ValueError: If mailbox is not in allowlist
        """
        # Validate mailbox access before making Graph request
        self._validate_mailbox_access(user_email)
        
        logger.info(f"Fetching calendar for mailbox: {user_email}")
        
        access_token = self._get_access_token()
        et_tz = ZoneInfo("America/New_York")
        
        # Ensure datetimes are timezone-aware
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=et_tz)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=et_tz)
        
        # Convert to UTC for Graph API (calendarView requires UTC)
        start_utc = start_dt.astimezone(ZoneInfo("UTC"))
        end_utc = end_dt.astimezone(ZoneInfo("UTC"))
        
        # Build Graph API URL
        url = f"https://graph.microsoft.com/v1.0/users/{user_email}/calendarView"
        
        params = {
            "startDateTime": start_utc.isoformat(),
            "endDateTime": end_utc.isoformat(),
            "$select": "subject,start,end,location,attendees,organizer,isCancelled,onlineMeeting,bodyPreview",
            "$orderby": "start/dateTime"
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Prefer": 'outlook.timezone="America/New_York"'
        }
        
        # Log Graph request details
        headers_loggable = headers.copy()
        if "Authorization" in headers_loggable:
            headers_loggable["Authorization"] = "Bearer <REDACTED>"
        
        logger.info(f"GRAPH REQUEST:")
        logger.info(f"  user_email: {user_email}")
        logger.info(f"  url: {url}")
        logger.info(f"  params: {params}")
        logger.info(f"  headers: {headers_loggable}")
        logger.info(f"  start_utc: {start_utc.isoformat()}")
        logger.info(f"  end_utc: {end_utc.isoformat()}")
        logger.info(f"  start_et: {start_dt.isoformat()}")
        logger.info(f"  end_et: {end_dt.isoformat()}")
        
        all_events = []
        next_link = None
        page_number = 0
        
        try:
            with httpx.Client(timeout=15) as client:
                # Handle paging
                while True:
                    page_number += 1
                    current_url = next_link or url
                    current_params = None if next_link else params
                    
                    if next_link:
                        logger.info(f"GRAPH REQUEST PAGE {page_number}: {current_url}")
                    else:
                        logger.info(f"GRAPH REQUEST PAGE {page_number}: {current_url} with params {current_params}")
                    
                    response = client.get(current_url, headers=headers, params=current_params)
                    
                    # Log response status
                    logger.info(f"GRAPH RESPONSE STATUS: {response.status_code}")
                    
                    if response.status_code == 401:
                        logger.error(f"MS Graph authentication failed for {user_email}")
                        raise HTTPException(status_code=503, detail="MS Graph authentication failed")
                    elif response.status_code == 403:
                        # Parse error response to determine if it's an Application Access Policy issue
                        error_detail = self._parse_403_error(response, user_email)
                        logger.error(f"Graph 403 error for {user_email}: {error_detail}")
                        raise HTTPException(status_code=403, detail=error_detail)
                    elif response.status_code == 404:
                        logger.warning(f"User not found: {user_email}")
                        raise HTTPException(status_code=404, detail=f"User not found: {user_email}")
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    raw_events = data.get("value", [])
                    logger.info(f"GRAPH RAW EVENT COUNT: {len(raw_events)}")
                    
                    # Log first 10 raw events before any filtering
                    for raw_ev in raw_events[:10]:
                        logger.info("GRAPH RAW EVENT:")
                        logger.info(f"  subject: {raw_ev.get('subject')}")
                        logger.info(f"  start: {raw_ev.get('start', {}).get('dateTime')}")
                        logger.info(f"  end: {raw_ev.get('end', {}).get('dateTime')}")
                        logger.info(f"  organizer: {raw_ev.get('organizer', {}).get('emailAddress', {}).get('address')}")
                        logger.info(f"  id: {raw_ev.get('id')}")
                    
                    # Process events from this page
                    for item in raw_events:
                        subject = item.get("subject", "")
                        start_obj = item.get("start", {})
                        
                        # Skip cancelled events
                        if item.get("isCancelled", False):
                            skip_reason = "cancelled event"
                            logger.info("GRAPH FILTER SKIP:")
                            logger.info(f"  subject: {subject}")
                            logger.info(f"  start: {start_obj.get('dateTime')}")
                            logger.info(f"  organizer: {item.get('organizer', {}).get('emailAddress', {}).get('address')}")
                            logger.info(f"  reason: {skip_reason}")
                            logger.info(f"  id: {item.get('id')}")
                            continue
                        
                        try:
                            # Parse start/end times using Graph's timeZone fields
                            start_dt_et = self._parse_graph_datetime(item.get("start", {}))
                            end_dt_et = self._parse_graph_datetime(item.get("end", {}))
                            
                            # Normalize attendees
                            attendees = self._normalize_attendees(item.get("attendees", []))
                            
                            # Check if user is organizer (add to attendees if not already there)
                            organizer = item.get("organizer", {}).get("emailAddress", {})
                            organizer_email = organizer.get("address", "")
                            organizer_name = organizer.get("name", "")
                            
                            # If organizer is not in attendees list, add them
                            if organizer_email:
                                organizer_in_attendees = any(
                                    (a.email or "").lower() == organizer_email.lower() 
                                    for a in attendees
                                )
                                if not organizer_in_attendees:
                                    # Extract company from email domain
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
                            
                            # Create Event with ISO datetime strings in ET
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
                            
                            all_events.append(event)
                            logger.info("GRAPH FILTER ACCEPT:")
                            logger.info(f"  subject: {item.get('subject', '')}")
                            logger.info(f"  start: {start_dt_et.isoformat() if start_dt_et else 'None'}")
                            logger.info(f"  end: {end_dt_et.isoformat() if end_dt_et else 'None'}")
                            logger.info(f"  organizer: {organizer_email}")
                            logger.info(f"  id: {item.get('id')}")
                            
                        except Exception as e:
                            subject = item.get("subject", "Unknown")
                            start_dt_str = item.get('start', {}).get('dateTime')
                            skip_reason = f"invalid timezone conversion / parse error: {e}"
                            logger.warning(f"Failed to parse event '{subject}': {e}")
                            logger.info("GRAPH FILTER SKIP:")
                            logger.info(f"  subject: {subject}")
                            logger.info(f"  start: {start_dt_str}")
                            logger.info(f"  organizer: {item.get('organizer', {}).get('emailAddress', {}).get('address')}")
                            logger.info(f"  reason: {skip_reason}")
                            logger.info(f"  id: {item.get('id')}")
                            continue
                    
                    # Check for next page
                    next_link = data.get("@odata.nextLink")
                    if not next_link:
                        break
                
                logger.info(f"GRAPH FINAL EVENT COUNT (from fetch_events_between): {len(all_events)}")
                logger.info(f"Fetched {len(all_events)} events from Graph API for {user_email}")
                return all_events
                
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error fetching events for {user_email}: {exc}", exc_info=True)
            raise HTTPException(status_code=503, detail=f"Failed to fetch events: {exc}") from exc

    def _fetch_events_for_user(self, user_email: str, date: str) -> List[Event]:
        """
        Fetch events for a specific user on a given date.
        
        Args:
            user_email: User email to fetch events for
            date: ISO date string (YYYY-MM-DD)
            
        Returns:
            List of Event objects
        """
        logger.info(f"GRAPH MAILBOX QUERY: {user_email}")
        
        et_tz = ZoneInfo("America/New_York")
        
        # Parse date and create start/end of day in ET
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"Invalid date format: {date}")
            return []
        
        start_of_day = datetime.combine(date_obj, datetime.min.time()).replace(tzinfo=et_tz)
        end_of_day = datetime.combine(date_obj, datetime.max.time()).replace(tzinfo=et_tz)
        
        # Fetch events using fetch_events_between
        all_events = self.fetch_events_between(user_email, start_of_day, end_of_day)
        
        # Filter to only events that start on the requested date and where user is attendee/organizer
        requested_date_obj = date_obj
        user_email_lower = user_email.lower()
        filtered_events = []
        
        logger.info(f"GRAPH FILTERING: Starting with {len(all_events)} events from Graph, filtering for date={requested_date_obj} and user={user_email}")
        
        for event in all_events:
            subject = event.subject
            start_dt = None
            end_dt = None
            organizer_email = event.organizer or "N/A"
            event_id = event.id or "N/A"

            # Parse event start time to get date
            try:
                event_start_dt = datetime.fromisoformat(event.start_time)
                start_dt = event_start_dt
                event_date = event_start_dt.date()
                try:
                    end_dt = datetime.fromisoformat(event.end_time)
                except Exception:
                    end_dt = None

                # Strict date filtering: only include events that start on the requested date
                if event_date != requested_date_obj:
                    skip_reason = "not on requested date"
                    logger.info("GRAPH FILTER SKIP:")
                    logger.info(f"  subject: {subject}")
                    logger.info(f"  start: {start_dt.isoformat() if start_dt else 'None'}")
                    logger.info(f"  organizer: {organizer_email}")
                    logger.info(f"  reason: {skip_reason}")
                    logger.info(f"  id: {event_id}")
                    continue

                # Filter: only include events where the user is an attendee
                user_is_attendee = False
                attendee_emails = []
                for attendee in event.attendees:
                    attendee_email = (attendee.email or "").lower()
                    attendee_emails.append(attendee_email)
                    if attendee_email == user_email_lower:
                        user_is_attendee = True
                        break

                if not user_is_attendee:
                    skip_reason = "user not in attendees list"
                    logger.info("GRAPH FILTER SKIP:")
                    logger.info(f"  subject: {subject}")
                    logger.info(f"  start: {start_dt.isoformat() if start_dt else 'None'}")
                    logger.info(f"  organizer: {organizer_email}")
                    logger.info(f"  reason: {skip_reason}")
                    logger.info(f"  id: {event_id}")
                    continue

                filtered_events.append(event)
                logger.info("GRAPH FILTER ACCEPT:")
                logger.info(f"  subject: {subject}")
                logger.info(f"  start: {start_dt.isoformat() if start_dt else 'None'}")
                logger.info(f"  end: {end_dt.isoformat() if end_dt else 'None'}")
                logger.info(f"  organizer: {organizer_email}")
                logger.info(f"  id: {event_id}")

            except Exception as e:
                skip_reason = f"invalid timezone conversion / parse error: {e}"
                logger.warning(f"Failed to parse event start time '{event.start_time}': {e}")
                logger.info("GRAPH FILTER SKIP:")
                logger.info(f"  subject: {subject}")
                logger.info(f"  start: {start_dt.isoformat() if start_dt else 'None'}")
                logger.info(f"  organizer: {organizer_email}")
                logger.info(f"  reason: {skip_reason}")
                logger.info(f"  id: {event_id}")
                continue
        
        logger.info(f"GRAPH FINAL EVENT COUNT: {len(filtered_events)}")
        logger.info(f"After filtering: {len(filtered_events)} events for {user_email} on {date}")
        return filtered_events

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
            
        Raises:
            ValueError: If mailbox is not in allowlist
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
            user_events = self._fetch_events_for_user(user, date)
            all_events.extend(user_events)
            logger.info(f"Total events fetched for {user}: {len(all_events)}")
            return all_events
        
        # Determine which mailbox to use (default fallback)
        mailbox_to_use = self.user_email
        if not mailbox_to_use:
            # Try MAILBOX_ADDRESS as fallback
            mailbox_to_use = os.getenv("MAILBOX_ADDRESS")
        
        # Validate default mailbox if using it
        if mailbox_to_use:
            self._validate_mailbox_access(mailbox_to_use)

        # If group-based access is configured, fetch events for all group members
        # Note: Group members are validated individually in _fetch_events_for_user
        if self.allowed_mailbox_group:
            logger.info(f"Fetching events for group '{self.allowed_mailbox_group}' on {date}")
            # Get all members of the allowed group
            group_members = self._get_group_members(self.allowed_mailbox_group)
            logger.info(f"Found {len(group_members)} members in group '{self.allowed_mailbox_group}'")

            # Fetch events for each group member (each validated in _fetch_events_for_user)
            for member_email in group_members:
                try:
                    member_events = self._fetch_events_for_user(member_email, date)
                    all_events.extend(member_events)
                except ValueError as e:
                    # Mailbox not in allowlist - skip this member
                    logger.warning(f"Skipping group member {member_email}: {e}")
                    continue

        # If single user is configured, fetch events for that user
        elif self.user_email:
            logger.info(f"Fetching events for user '{self.user_email}' on {date}")
            # Validate mailbox access
            self._validate_mailbox_access(self.user_email)
            user_events = self._fetch_events_for_user(self.user_email, date)
            all_events.extend(user_events)
            logger.info(f"Total events fetched: {len(all_events)}")

        else:
            raise HTTPException(
                status_code=503,
                detail="MS Graph configuration missing: Either MS_USER_EMAIL or ALLOWED_MAILBOX_GROUP must be provided"
            )

        # Sort all events by start time (ISO datetime strings sort correctly)
        all_events.sort(key=lambda e: e.start_time)

        return all_events


def create_ms_graph_adapter() -> MSGraphAdapter:
    """Factory function to create MSGraphAdapter from environment variables."""
    # Support both MS_* and AZURE_* naming conventions
    tenant_id = (os.getenv("MS_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or "").strip()
    client_id = (os.getenv("MS_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("MS_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") or "").strip()
    user_email = (os.getenv("MS_USER_EMAIL") or "").strip() or None
    allowed_mailbox_group = (os.getenv("ALLOWED_MAILBOX_GROUP") or "").strip() or None
    
    # Load allowed mailboxes from config
    config = load_config()
    allowed_mailboxes = config.allowed_mailboxes

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
        allowed_mailbox_group=allowed_mailbox_group,
        allowed_mailboxes=allowed_mailboxes
    )
