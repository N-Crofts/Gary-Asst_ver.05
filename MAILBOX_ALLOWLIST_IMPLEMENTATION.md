# Mailbox Allowlist Implementation Summary

## Changes Made

### 1. Configuration (`app/core/config.py`)
- Added `allowed_mailboxes: list[str]` to `AppConfig`
- Parses `ALLOWED_MAILBOXES` environment variable (comma-separated)
- Normalizes all mailboxes to lowercase

### 2. MS Graph Adapter (`app/calendar/ms_graph_adapter.py`)
- Added `allowed_mailboxes` parameter to `__init__`
- Added `_validate_mailbox_access()` method that:
  - Normalizes mailbox to lowercase
  - Checks against allowlist
  - Raises `ValueError` with clear message if denied
- Updated `fetch_events_between()` to validate mailbox before Graph request
- Updated `fetch_events()` to validate mailbox (including default fallback)
- Added startup logging: "Allowed mailboxes: [...]"
- Added per-request logging: "Fetching calendar for mailbox: {user_email}"

### 3. Debug Endpoint (`app/routes/debug.py`)
- Added `mailbox` query parameter
- Falls back to `MAILBOX_ADDRESS` or `MS_USER_EMAIL` if not provided
- Returns mailbox information in debug response

### 4. Tests (`tests/test_mailbox_allowlist.py`)
- 9 comprehensive tests covering:
  - Allowed mailbox succeeds
  - Disallowed mailbox raises exception
  - Case-insensitive comparison
  - Empty mailbox handling
  - No allowlist configured
  - Validation in fetch_events
  - Validation in fetch_events_between
  - Config loading
  - Normalization

## Usage

### Environment Variable
```bash
ALLOWED_MAILBOXES=sorum.crofts@rpck.com,chintan.panchal@rpck.com
```

### Debug Endpoint
```bash
# Use default mailbox
GET /debug/calendar?date=2026-02-17

# Use specific mailbox
GET /debug/calendar?date=2026-02-17&mailbox=chintan.panchal@rpck.com
```

## Security

- All mailbox access is validated against allowlist
- No silent fallback - errors are raised clearly
- Case-insensitive comparison prevents bypass attempts
- Validation happens before any Graph API calls
