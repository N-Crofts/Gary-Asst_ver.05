# Mailbox Allowlist - Example Output

## Configuration

Add to `.env`:
```bash
ALLOWED_MAILBOXES=sorum.crofts@rpck.com,chintan.panchal@rpck.com
```

## Startup Logging

When the adapter is created, you'll see:
```
INFO:app.calendar.ms_graph_adapter:Allowed mailboxes: ['sorum.crofts@rpck.com', 'chintan.panchal@rpck.com']
```

## Debug Endpoint Examples

### 1. Default Mailbox (sorum.crofts@rpck.com)

```bash
GET /debug/calendar?date=2026-02-17
```

**Response:**
```json
{
  "calendar_provider": "ms_graph",
  "mailbox_requested": "sorum.crofts@rpck.com",
  "adapter_allowed_mailboxes": ["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"],
  "event_count": 1,
  "events": [
    {
      "subject": "Call with Stephen Mimbs",
      "start_time": "2026-02-17T18:00:00-05:00",
      "end_time": "2026-02-17T18:30:00-05:00",
      "location": "",
      "attendee_count": 1,
      "attendees": [
        {
          "name": "Sorum Crofts",
          "email": "sorum.crofts@rpck.com"
        }
      ]
    }
  ],
  "error": null
}
```

### 2. Explicit Mailbox (chintan.panchal@rpck.com)

```bash
GET /debug/calendar?date=2026-02-17&mailbox=chintan.panchal@rpck.com
```

**Response:**
```json
{
  "calendar_provider": "ms_graph",
  "mailbox_requested": "chintan.panchal@rpck.com",
  "adapter_allowed_mailboxes": ["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"],
  "event_count": 0,
  "events": [],
  "error": null
}
```

### 3. Unauthorized Mailbox (should be denied)

```bash
GET /debug/calendar?date=2026-02-17&mailbox=unauthorized@example.com
```

**Response:**
```json
{
  "calendar_provider": "ms_graph",
  "mailbox_requested": "unauthorized@example.com",
  "adapter_allowed_mailboxes": ["sorum.crofts@rpck.com", "chintan.panchal@rpck.com"],
  "event_count": 0,
  "events": [],
  "error": "Mailbox access denied: unauthorized@example.com is not in allowlist. Allowed: ['sorum.crofts@rpck.com', 'chintan.panchal@rpck.com']",
  "error_type": "ValueError"
}
```

## Per-Request Logging

When accessing a mailbox, you'll see:
```
INFO:app.calendar.ms_graph_adapter:Fetching calendar for mailbox: sorum.crofts@rpck.com
```

## Case-Insensitive Matching

All mailbox comparisons are case-insensitive:
- `SORUM.CROFTS@RPCK.COM` ✅ (allowed)
- `SorUm.CrOfTs@RpCk.CoM` ✅ (allowed)
- `sorum.crofts@rpck.com` ✅ (allowed)
