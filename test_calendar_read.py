#!/usr/bin/env python3
"""Quick test to verify the application can read calendar from sorum.crofts@rpck.com"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.calendar.ms_graph_adapter import MSGraphAdapter

def main():
    # Get credentials from environment
    tenant_id = os.getenv("AZURE_TENANT_ID") or os.getenv("MS_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.getenv("MS_CLIENT_SECRET")
    user_email = os.getenv("MS_USER_EMAIL")
    allowed_group = os.getenv("ALLOWED_MAILBOX_GROUP")

    if not all([tenant_id, client_id, client_secret]):
        print("[ERROR] Missing required credentials:")
        print(f"   AZURE_TENANT_ID/MS_TENANT_ID: {'OK' if tenant_id else 'MISSING'}")
        print(f"   AZURE_CLIENT_ID/MS_CLIENT_ID: {'OK' if client_id else 'MISSING'}")
        print(f"   AZURE_CLIENT_SECRET/MS_CLIENT_SECRET: {'OK' if client_secret else 'MISSING'}")
        return 1

    # Test with sorum.crofts@rpck.com specifically
    test_user = "sorum.crofts@rpck.com"
    print(f"[TEST] Testing calendar read for: {test_user}")
    print(f"   Using tenant: {tenant_id}")
    print(f"   Using client: {client_id}")
    print()

    # Create adapter with test user
    adapter = MSGraphAdapter(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        user_email=test_user
    )

    # Test with today's date
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[FETCH] Fetching events for {today}...")

    try:
        events = adapter.fetch_events(today)
        print(f"[SUCCESS] Successfully fetched {len(events)} events")
        print()

        if events:
            print("Events found:")
            for i, event in enumerate(events[:5], 1):  # Show first 5
                print(f"   {i}. {event.subject}")
                print(f"      Time: {event.start_time} - {event.end_time}")
                if event.location:
                    print(f"      Location: {event.location}")
                if event.attendees:
                    attendee_names = [a.name or a.email for a in event.attendees[:3]]
                    print(f"      Attendees: {', '.join(attendee_names)}")
                    if len(event.attendees) > 3:
                        print(f"      ... and {len(event.attendees) - 3} more")
                print()
        else:
            print("   No events found for today")

        print("[SUCCESS] Calendar read test completed successfully!")
        return 0

    except Exception as e:
        print(f"[ERROR] Error reading calendar: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

