# Calendar Refactor Summary

## Changes Made

### 1. Added `fetch_events_between` method
- New method in `MSGraphAdapter` that accepts timezone-aware datetime objects
- Uses `calendarView` endpoint with proper UTC ISO strings
- Includes `Prefer: outlook.timezone="America/New_York"` header
- Handles paging via `@odata.nextLink`
- Returns events with ISO datetime strings in ET timezone

### 2. Refactored `_fetch_events_for_user`
- Now uses `fetch_events_between` internally
- Creates start/end of day in ET timezone
- Filters events by date and attendee/organizer

### 3. Fixed Timezone Handling
- New `_parse_graph_datetime` method respects Graph's `timeZone` field
- Properly converts to America/New_York timezone
- Returns ISO datetime strings with correct timezone offset

### 4. Updated Event Model
- `start_time` and `end_time` now store ISO 8601 datetime strings in ET
- Format: `"2025-01-15T09:30:00-05:00"` (example)

### 5. Updated Debug Endpoint
- `/debug/calendar` now supports:
  - Single date: `?date=YYYY-MM-DD`
  - Date range: `?start=ISO&end=ISO`
- Returns events with ISO datetime strings

### 6. Error Handling
- No silent fallback when `CALENDAR_PROVIDER=ms_graph`
- Errors are raised/logged clearly
- HTTPException raised for auth/permission errors

### 7. Paging Support
- Handles `@odata.nextLink` for large result sets
- Fetches all pages automatically

## API Changes

### Before:
- `start_time`: `"9:30 AM ET"` (string format)
- No support for datetime ranges
- Silent fallback on errors

### After:
- `start_time`: `"2025-01-15T09:30:00-05:00"` (ISO 8601 in ET)
- `fetch_events_between(user_email, start_dt, end_dt)` method
- Errors raised instead of silent fallback

## Testing

All tests updated and passing:
- `test_fetch_events_success_normalizes_data` - Updated for ISO format
- `test_parse_graph_datetime_handles_various_formats` - New test
- `test_preview_live_with_ms_graph_error_raises` - Updated for no-fallback behavior
- All 13 tests passing
