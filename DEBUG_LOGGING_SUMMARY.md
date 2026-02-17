# Debug Logging Implementation Summary

## Logging Points Added

### 1. Graph Request Logging (`fetch_events_between`)
**Location:** Before `client.get()` call

Logs:
- `GRAPH REQUEST:` header
- `user_email`
- `url` (full Graph API URL)
- `params` (query parameters)
- `headers` (with Authorization token redacted as `<REDACTED>`)
- `start_utc` and `end_utc` (UTC ISO format)
- `start_et` and `end_et` (ET ISO format)
- Page number for paginated requests

**Example:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH REQUEST:
INFO:app.calendar.ms_graph_adapter:  user_email: sorum.crofts@rpck.com
INFO:app.calendar.ms_graph_adapter:  url: https://graph.microsoft.com/v1.0/users/sorum.crofts@rpck.com/calendarView
INFO:app.calendar.ms_graph_adapter:  params: {'startDateTime': '...', 'endDateTime': '...', '$select': '...', '$orderby': '...'}
INFO:app.calendar.ms_graph_adapter:  headers: {'Authorization': 'Bearer <REDACTED>', 'Content-Type': 'application/json', 'Prefer': 'outlook.timezone="America/New_York"'}
INFO:app.calendar.ms_graph_adapter:  start_utc: 2026-02-17T05:00:00+00:00
INFO:app.calendar.ms_graph_adapter:  end_utc: 2026-02-18T04:59:59+00:00
INFO:app.calendar.ms_graph_adapter:  start_et: 2026-02-17T00:00:00-05:00
INFO:app.calendar.ms_graph_adapter:  end_et: 2026-02-17T23:59:59-05:00
```

### 2. Graph Response Status Logging
**Location:** Immediately after receiving response

Logs:
- `GRAPH RESPONSE STATUS: {status_code}`
- `GRAPH RAW EVENT COUNT: {count}`

**Example:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH RESPONSE STATUS: 200
INFO:app.calendar.ms_graph_adapter:GRAPH RAW EVENT COUNT: 10
```

### 3. Raw Event Logging (First 5 Events)
**Location:** Before any filtering, logs first 5 events from Graph response

Logs for each event:
- `GRAPH RAW EVENT {idx}:`
- `subject`
- `start.dateTime` and `start.timeZone`
- `end.dateTime` and `end.timeZone`
- `organizer.emailAddress.address`
- `isCancelled`
- `type`

**Example:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH RAW EVENT 1:
INFO:app.calendar.ms_graph_adapter:  subject: Call with Stephen Mimbs
INFO:app.calendar.ms_graph_adapter:  start.dateTime: 2026-02-17T18:00:00.0000000
INFO:app.calendar.ms_graph_adapter:  start.timeZone: America/New_York
INFO:app.calendar.ms_graph_adapter:  end.dateTime: 2026-02-17T18:30:00.0000000
INFO:app.calendar.ms_graph_adapter:  end.timeZone: America/New_York
INFO:app.calendar.ms_graph_adapter:  organizer.emailAddress.address: sorum.crofts@rpck.com
INFO:app.calendar.ms_graph_adapter:  isCancelled: False
INFO:app.calendar.ms_graph_adapter:  type: singleInstance
```

### 4. Filtering Decision Logging
**Location:** In `_fetch_events_for_user` during filtering

For skipped events:
- `GRAPH FILTER SKIP:`
- `subject`
- `start`
- `reason` (detailed explanation)

For accepted events:
- `GRAPH FILTER ACCEPT:`
- `subject`
- `start`

**Example Skip:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH FILTER SKIP:
INFO:app.calendar.ms_graph_adapter:  subject: Old Meeting
INFO:app.calendar.ms_graph_adapter:  start: 2026-02-16T10:00:00-05:00
INFO:app.calendar.ms_graph_adapter:  reason: Event starts on 2026-02-16, but requested date is 2026-02-17
```

**Example Accept:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH FILTER ACCEPT:
INFO:app.calendar.ms_graph_adapter:  subject: Call with Stephen Mimbs
INFO:app.calendar.ms_graph_adapter:  start: 2026-02-17T18:00:00-05:00
```

### 5. Final Event Count Logging
**Location:** Before returning filtered events

Logs:
- `GRAPH FINAL EVENT COUNT: {count}` (in `_fetch_events_for_user`)
- `GRAPH FINAL EVENT COUNT (from fetch_events_between): {count}` (in `fetch_events_between`)

**Example:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH FINAL EVENT COUNT: 1
```

### 6. Mailbox Query Logging
**Location:** At start of `_fetch_events_for_user`

Logs:
- `GRAPH MAILBOX QUERY: {user_email}`

**Example:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH MAILBOX QUERY: sorum.crofts@rpck.com
```

### 7. Date Filter Logging
**Location:** In `_fetch_events_for_user` before calling `fetch_events_between`

Logs:
- `GRAPH DATE FILTER: Requested date={date}, start_of_day={start}, end_of_day={end}`
- `GRAPH FILTERING: Starting with {count} events from Graph, filtering for date={date} and user={user}`

**Example:**
```
INFO:app.calendar.ms_graph_adapter:GRAPH DATE FILTER: Requested date=2026-02-17, start_of_day=2026-02-17T00:00:00-05:00, end_of_day=2026-02-17T23:59:59-05:00
INFO:app.calendar.ms_graph_adapter:GRAPH FILTERING: Starting with 10 events from Graph, filtering for date=2026-02-17 and user=sorum.crofts@rpck.com
```

## Security

- Authorization token is redacted in logs: `Bearer <REDACTED>`
- All logging uses Python `logging` module (no `print()` statements)
- Uses `logger.info()` for visibility (not `logger.debug()`)

## Benefits

This logging allows full traceability of:
1. What Graph API is being called with what parameters
2. What Graph API returns (raw events)
3. Which events are filtered out and why
4. Which events are accepted
5. Final event counts at each stage

This will help diagnose issues with recurring events and filtering logic.
