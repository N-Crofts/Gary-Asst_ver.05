# Quick Reference Guide

## System Overview

Gary-Asst is a calendar intelligence system that:
1. Fetches calendar events from Microsoft Graph
2. Enriches them with company data, news, and AI-generated content
3. Generates personalized morning briefings
4. Delivers digest emails to executives

## Key Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Backend API** | FastAPI application handling requests | `app/main.py`, `app/routes/` |
| **Calendar Provider** | Abstract calendar access | `app/calendar/provider.py` |
| **Enrichment Service** | Add company/news/LLM data | `app/enrichment/service.py` |
| **Rendering** | Generate HTML/plaintext digests | `app/rendering/` |
| **Email Service** | Send digest emails | `app/services/emailer.py` |
| **Profile Store** | Executive profile management | `app/profile/store.py` |

## Common Tasks

### Start the Server
```bash
python -m uvicorn app.main:app --reload --port 8000
```

### Preview Digest (Live Data)
```bash
# HTML preview
http://127.0.0.1:8000/digest/preview?source=live&date=2026-01-17&mailbox=user@domain.com

# JSON preview
http://127.0.0.1:8000/digest/preview.json?source=live&date=2026-01-17&mailbox=user@domain.com
```

### Send Digest Email
```bash
curl -X POST http://127.0.0.1:8000/digest/send \
  -H "Content-Type: application/json" \
  -d '{"send": true, "source": "live", "date": "2026-01-17", "mailbox": "user@domain.com"}'
```

### Search Calendar Events
```bash
http://127.0.0.1:8000/digest/search?start=2026-01-01&end=2026-01-31&email=jane@company.com&source=live
```

## Environment Variables

### Required for Live Calendar
```env
CALENDAR_PROVIDER=ms_graph
MS_TENANT_ID=your-tenant-id
MS_CLIENT_ID=your-client-id
MS_CLIENT_SECRET=your-client-secret
MS_USER_EMAIL=user@domain.com
```

### Optional Features
```env
# News enrichment
NEWS_ENABLED=true
NEWS_PROVIDER=newsapi
NEWS_API_KEY=your-api-key

# LLM generation
LLM_ENABLED=true
OPENAI_API_KEY=your-api-key

# Email delivery
MAIL_DRIVER=sendgrid
SENDGRID_API_KEY=your-api-key
```

## Architecture Patterns

### Provider Pattern
All external services use a provider pattern:
- Define a protocol/interface
- Implement mock and real versions
- Use factory function to select implementation

### Source Parameter
Most endpoints support `source=live|sample`:
- `live` - Use real data from external APIs
- `sample` - Use mock/sample data

### Profile-Based Configuration
- Profiles stored in `app/data/exec_profiles.json`
- Lookup by mailbox address
- Customize max items, sections order, company aliases

## File Locations

| File Type | Location |
|-----------|----------|
| API Routes | `app/routes/*.py` |
| Calendar Providers | `app/calendar/*.py` |
| Enrichment | `app/enrichment/*.py` |
| LLM Integration | `app/llm/*.py` |
| Email Services | `app/services/*.py` |
| Templates | `app/templates/*.html` |
| Sample Data | `app/data/*.json` |
| Tests | `tests/test_*.py` |

## Testing

### Run All Tests
```bash
python -m pytest -q
```

### Run Specific Test File
```bash
python -m pytest tests/test_preview.py -v
```

### Run with Coverage
```bash
python -m pytest --cov=app tests/
```

## Debugging

### Check Calendar Provider
```bash
http://127.0.0.1:8000/debug/calendar?date=2026-01-17
```

### View Health Status
```bash
http://127.0.0.1:8000/health
```

### Check Scheduler Status
```bash
http://127.0.0.1:8000/scheduler/status
```

## Common Issues

### No Events Showing
1. Check `CALENDAR_PROVIDER` is set to `ms_graph`
2. Verify Microsoft Graph credentials are correct
3. Ensure `source=live` parameter is used
4. Check date format is `YYYY-MM-DD`
5. Verify user email matches calendar owner

### Events from Wrong Date/User
1. Ensure `date` parameter matches requested date
2. Verify `mailbox` parameter matches user
3. Check profile has correct `mailbox` field
4. Review server logs for filtering messages

### Email Not Sending
1. Check `MAIL_DRIVER` configuration
2. Verify email service credentials
3. Check `DEFAULT_RECIPIENTS` is set
4. Review email service logs

## Documentation Links

- [Architecture Guide](../ARCHITECTURE.md) - System design and components
- [API Design](API_DESIGN.md) - API endpoints and patterns
- [Code Examples](EXAMPLES.md) - Example implementations
- [Integration Examples](INTEGRATION_EXAMPLE.md) - Mock integration layer
