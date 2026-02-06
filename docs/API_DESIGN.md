# API Design Guide

## Overview

This document describes the API design patterns and conventions used in Gary-Asst.

## Base URL

```
http://localhost:8000
```

## Authentication

Optional API key authentication via header:
```
X-API-Key: your-api-key-here
```

Set `API_KEY` in `.env` to enable. If not set, endpoints are publicly accessible.

## Common Patterns

### Source Parameter

Most endpoints support a `source` parameter to choose between live and sample data:

- `source=live` - Use real calendar data from Microsoft Graph
- `source=sample` - Use mock/sample data for testing

**Example**:
```
GET /digest/preview?source=live&date=2026-01-17&mailbox=user@domain.com
```

### Date Format

All dates use ISO 8601 format: `YYYY-MM-DD`

**Examples**:
- `2026-01-17` - January 17, 2026
- `2026-12-25` - December 25, 2026

### Error Responses

Standard error format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

Common status codes:
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (missing/invalid API key)
- `404` - Not Found
- `422` - Unprocessable Entity (validation error)
- `503` - Service Unavailable (external service error)

## Endpoints

### Health & Status

#### `GET /`
Health check endpoint.

**Response**:
```json
{
  "status": "ok"
}
```

#### `GET /health`
Detailed health check with system status.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-17T10:30:00Z",
  "version": "0.5.0",
  "services": {
    "calendar": "ok",
    "email": "ok"
  }
}
```

### Preview Endpoints

#### `GET /digest/preview`
Preview digest as HTML.

**Query Parameters**:
- `source` (optional): `live` or `sample` (default: `sample`)
- `date` (optional): Date in `YYYY-MM-DD` format (default: today)
- `mailbox` (optional): User email for profile lookup
- `exec_name` (optional): Override executive name
- `format` (optional): `json` to return JSON instead of HTML

**Example**:
```
GET /digest/preview?source=live&date=2026-01-17&mailbox=user@domain.com
```

**Response**: HTML page with digest preview

#### `GET /digest/preview.json`
Preview digest as JSON.

**Query Parameters**: Same as `/digest/preview`

**Response**:
```json
{
  "ok": true,
  "source": "live",
  "date_human": "Monday, January 17, 2026",
  "exec_name": "John Doe",
  "meetings": [
    {
      "subject": "Meeting with Acme Corp",
      "start_time": "9:00 AM ET",
      "location": "Conference Room A",
      "attendees": [
        {
          "name": "Jane Smith",
          "title": "CEO",
          "company": "Acme Corp"
        }
      ],
      "company": {
        "name": "Acme Corp",
        "one_liner": "Leading technology company"
      },
      "news": [
        {
          "title": "Acme Corp Announces New Product",
          "url": "https://example.com/news/1"
        }
      ],
      "talking_points": [
        "Discuss partnership opportunities",
        "Review Q1 performance"
      ],
      "smart_questions": [
        "What are your top priorities for this quarter?",
        "How do you see the market evolving?"
      ]
    }
  ]
}
```

#### `GET /digest/preview/latest`
Get the latest cached preview for today.

**Query Parameters**:
- `mailbox` (optional): User email for profile lookup
- `format` (optional): `json` to return JSON

**Response**: Cached HTML or JSON (same format as preview endpoints)

**Status Codes**:
- `200` - Cached preview available
- `404` - No cached preview available

### Digest Sending

#### `POST /digest/send`
Send digest email.

**Request Body**:
```json
{
  "send": true,
  "source": "live",
  "date": "2026-01-17",
  "mailbox": "user@domain.com",
  "recipients": ["recipient@domain.com"]
}
```

**Response**:
```json
{
  "ok": true,
  "message": "Digest sent successfully",
  "subject": "Morning Briefing - Monday, January 17, 2026",
  "recipients": ["recipient@domain.com"],
  "html": "<html>...</html>"
}
```

### Search Endpoints

#### `GET /digest/search`
Search for meetings with specific attendees across a date range.

**Query Parameters**:
- `start` (required): Start date in `YYYY-MM-DD` format
- `end` (required): End date in `YYYY-MM-DD` format
- `email` (optional): Exact email match
- `domain` (optional): Domain match (e.g., `company.com`)
- `name` (optional): Name match (case-insensitive contains)
- `source` (optional): `live` or `sample` (default: `live`)

**Example**:
```
GET /digest/search?start=2026-01-01&end=2026-01-31&email=jane@acme.com
```

**Response**:
```json
{
  "ok": true,
  "matches": [
    {
      "event_id": "2026-01-17-Meeting with Acme",
      "date": "2026-01-17",
      "start_time": "9:00 AM ET",
      "subject": "Meeting with Acme Corp",
      "attendees": [...],
      "location": "Conference Room A"
    }
  ],
  "count": 1
}
```

### Scheduler Endpoints

#### `GET /scheduler/status`
Get scheduler status.

**Response**:
```json
{
  "enabled": false,
  "next_run": "2026-01-19T08:00:00-05:00",
  "timezone": "America/New_York",
  "cron": "0 8 * * 1-5"
}
```

#### `POST /scheduler/start`
Start the scheduler.

**Response**:
```json
{
  "ok": true,
  "message": "Scheduler started"
}
```

#### `POST /scheduler/stop`
Stop the scheduler.

**Response**:
```json
{
  "ok": true,
  "message": "Scheduler stopped"
}
```

### Debug Endpoints

#### `GET /debug/calendar`
Debug calendar provider (requires API key if configured).

**Query Parameters**:
- `date` (optional): Date in `YYYY-MM-DD` format (default: today)

**Response**:
```json
{
  "provider": "ms_graph",
  "date": "2026-01-17",
  "events_count": 5,
  "events": [...],
  "config": {
    "calendar_provider": "ms_graph",
    "ms_user_email": "user@domain.com"
  }
}
```

## Response Format Conventions

### Success Responses

All successful responses include:
- `ok: true` (for JSON responses)
- Relevant data fields
- Consistent structure

### Error Responses

All error responses include:
- `detail`: Human-readable error message
- Appropriate HTTP status code

### Pagination

Currently not implemented, but future endpoints should use:
```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 100,
    "pages": 5
  }
}
```

## Rate Limiting

Currently not implemented. Future consideration:
- Rate limit by IP address
- Rate limit by API key
- Different limits for different endpoints

## Versioning

Currently no versioning. Future consideration:
- URL versioning: `/v1/digest/preview`
- Header versioning: `Accept: application/vnd.gary.v1+json`

## Best Practices

1. **Always validate input**: Use Pydantic models for request/response validation
2. **Provide clear error messages**: Help users understand what went wrong
3. **Use appropriate HTTP methods**: GET for reads, POST for writes
4. **Document query parameters**: Include descriptions in FastAPI Query()
5. **Handle errors gracefully**: Return appropriate status codes and messages
6. **Support both HTML and JSON**: Use `format` parameter or `Accept` header
7. **Cache when appropriate**: Use preview cache for frequently accessed data
8. **Log important operations**: Log API calls, errors, and external service calls
