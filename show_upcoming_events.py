#!/usr/bin/env python3
"""
Show upcoming calendar events for sorum.crofts@rpck.com.
"""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.WARNING)  # Reduce noise

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.calendar.provider import select_calendar_provider, fetch_events_range

def main():
    user_email = "sorum.crofts@rpck.com"
    today = datetime.now()
    start_date = today.strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=14)).strftime("%Y-%m-%d")
    
    print("=" * 80)
    print(f"UPCOMING EVENTS: {user_email}")
    print("=" * 80)
    print(f"Date range: {start_date} to {end_date}")
    print()
    
    try:
        provider = select_calendar_provider()
        events = fetch_events_range(provider, start_date, end_date, user=user_email)
        
        print(f"Found {len(events)} events in the next 14 days")
        print()
        
        if not events:
            print("No upcoming events found.")
            return
        
        # Group by date
        events_by_date = {}
        for event in events:
            # Extract date from start_time
            date_str = event.start_time.split("T")[0] if "T" in event.start_time else event.start_time.split(" ")[0]
            if date_str not in events_by_date:
                events_by_date[date_str] = []
            events_by_date[date_str].append(event)
        
        # Display
        for date_str in sorted(events_by_date.keys()):
            date_events = events_by_date[date_str]
            print(f"\n{date_str} ({len(date_events)} event{'s' if len(date_events) != 1 else ''})")
            print("-" * 80)
            
            for event in date_events:
                print(f"\n  {event.subject}")
                print(f"    Time: {event.start_time} - {event.end_time}")
                if event.location:
                    print(f"    Location: {event.location}")
                if event.attendees:
                    attendee_names = [a.name for a in event.attendees[:3]]
                    print(f"    Attendees: {', '.join(attendee_names)}" + 
                          (f" (+{len(event.attendees)-3} more)" if len(event.attendees) > 3 else ""))
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
