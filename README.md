# Gary-Asst (Research Gary MVP)

Research Gary scans the daily calendar, builds quick dossiers for external meetings, and emails a single morning briefing.

## 📚 Documentation

- **[Architecture Guide](ARCHITECTURE.md)** - System architecture, design decisions, and component overview
- **[API Design](docs/API_DESIGN.md)** - API endpoints, patterns, and conventions
- **[Code Examples](docs/EXAMPLES.md)** - Sanitized examples of key modules and patterns
- **[Integration Examples](docs/INTEGRATION_EXAMPLE.md)** - Mocked integration layer examples
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Quick reference guide for common tasks

## 🏗️ System Architecture

### High-Level Flow

```
┌─────────┐
│  User   │
└────┬────┘
     │
     ▼
┌─────────────────┐
│  Web Interface  │  Preview & Management UI
└────┬────────────┘
     │ HTTP Requests
     ▼
┌─────────────────┐
│  Backend API    │  FastAPI Application
│  (FastAPI)      │  • Route Handling
└────┬────────────┘  • Request Validation
     │                • Context Building
     ▼
┌─────────────────┐
│ Microsoft Graph │  Calendar & Mail API
│  (OAuth2)       │  • Fetch Events
└────┬────────────┘  • Filter by Date/User
     │
     ▼
┌─────────────────┐
│Processing       │  Data Enrichment Pipeline
│Pipeline         │  • Company Data
└────┬────────────┘  • News Articles
     │                • LLM Generation
     │                • People Resolution
     ▼
┌─────────────────┐
│ Email Delivery  │  SendGrid/SMTP
│  (SendGrid)     │  • HTML & Plaintext
└────┬────────────┘  • Recipient Management
     │
     ▼
┌─────────┐
│  User   │  Receives Digest Email
└─────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation, component descriptions, and design decisions.

---

## ✅ What's in this repo at project start

- `app/main.py` — FastAPI entrypoint with a basic scheduler and healthcheck route.
- `tests/test_smoke.py` — smoke test (`assert 1 + 1 == 2`).
- `tests/test_endpoints.py` — endpoint tests for `/` and `/digest/send`.
- `.pre-commit-config.yaml` — hooks: pre-commit hygiene, black, ruff, mypy.
- `requirements.txt` — runtime deps.
- `.env.example` — template for environment variables.

## 📅 Calendar Integration

The app supports multiple calendar providers through a pluggable architecture:

- **Mock Provider** (default): Uses sample data from `app/data/sample_calendar.json`
- **Microsoft Graph**: Live calendar integration with OAuth2 client credentials

### Microsoft Graph Setup

1. Set environment variables:
   ```bash
   CALENDAR_PROVIDER=ms_graph
   MS_TENANT_ID=your-tenant-id
   MS_CLIENT_ID=your-client-id
   MS_CLIENT_SECRET=your-client-secret
   MS_USER_EMAIL=user@yourdomain.com
   ```

2. The app will automatically fall back to sample data if:
   - MS Graph credentials are missing
   - API calls fail
   - No events are found for the requested date

### Preview Endpoints

- `GET /digest/preview` — HTML preview (default)
- `GET /digest/preview.json` — JSON preview
- `GET /digest/preview?source=live` — Use live calendar data
- `GET /digest/preview?source=sample` — Use sample data (default)

---

## 🚀 Quickstart

Get the project running locally in 5 steps:

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd gary-asst

# 2. Create & activate virtual environment (if not already active)

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements-all.txt   # or requirements.txt if that's the file present

# 4. Copy environment variables template

# macOS / Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env

# then open .env and fill in your keys

# 5. Run the server and tests
uvicorn app.main:app --reload
python -m pytest -q
```

## 🎯 MVP goal (short)

At 7:30am ET, read today’s external meetings → enrich (company + news) → generate **3 talking points + 3 smart questions** → email a **single digest**.

---

## 🚦 Sanity Check (Manual Quickstart Test)

To confirm the project is wired up correctly:

1. **Boot the server**
   ```bash
   uvicorn app.main:app --reload
   ```
   → Console should show: `Uvicorn running on http://127.0.0.1:8000`

2. **Check the health endpoint**
   Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in a browser.
   → Should return:
   ```json
   {"status": "ok"}
   ```

3. **Test the digest endpoint**
   In another terminal (with venv activated):

   **macOS / Linux**
   ```bash
   curl -X POST http://127.0.0.1:8000/digest/send
   ```

   **Windows PowerShell**
   ```powershell
   Invoke-WebRequest -Uri "http://127.0.0.1:8000/digest/send" -Method POST
   # or, if curl.exe is installed:
   curl.exe -X POST http://127.0.0.1:8000/digest/send
   ```

   → Should return JSON with `"ok": true` and an `"html"` field containing the sample digest (Acme Capital, Jane Doe, etc.).

If all three succeed, the skeleton app is running end-to-end.

---

## 🐳 Docker Verification

You can also run Gary-Asst in a Docker container for local testing or deployment:

### Build Container

```bash
docker build -t gary-asst .
```

### Run Container

```bash
docker run -p 8000:8000 --env-file .env gary-asst
```

**Note:** Ensure your `.env` file exists with required environment variables before running the container.

### Verify Health Endpoint

Once the container is running, test the health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

### Docker Notes

- The container exposes port 8000 by default
- Environment variables are loaded from `.env` file via `--env-file`
- The container uses Python 3.11 slim base image
- Health endpoint is available at `/health` for container orchestration

For production deployment to Fly.io, see [deploy/fly/README.md](deploy/fly/README.md).

---

## ✅ Sanity Test (Automated with Pytest)

We added `tests/test_endpoints.py` to automatically check both endpoints.

Run:
```bash
python -m pytest -q
```

Expected:
```
..                                                                   [100%]
2 passed in 0.50s
```

---

## 🔑 Environment variables

Copy `.env.example` to `.env` at the repo root and fill in the values.
Without this file, integrations (OpenAI, Bing, Graph) won’t work — but the skeleton app will still boot and return the sample digest.

```env
OPENAI_API_KEY=sk-xxxx
BING_API_KEY=xxxx
AZURE_CLIENT_ID=xxxx
AZURE_TENANT_ID=xxxx
AZURE_CLIENT_SECRET=xxxx
MAILBOX_ADDRESS=sorum.crofts@rpck.com
# Optional, for later:
# DATABASE_URL=postgresql://user:pass@localhost:5432/gary
```

Load them in Python with `python-dotenv`:
```python
from dotenv import load_dotenv; load_dotenv()
```

---

## Required Environment Variables for ms_graph Preview (Fly Deployment)

**Note:** Fly.io deployment uses the account `gary.asst.project@gmail.com` for authentication and credentials.

When deploying to Fly.io with `CALENDAR_PROVIDER=ms_graph`, the following environment variables must be set as Fly secrets:

### Required:

- **`CALENDAR_PROVIDER=ms_graph`** - Enables Microsoft Graph calendar provider
- **`AZURE_TENANT_ID`** (or `MS_TENANT_ID`) - Azure AD tenant ID
- **`AZURE_CLIENT_ID`** (or `MS_CLIENT_ID`) - Azure AD application client ID
- **`AZURE_CLIENT_SECRET`** (or `MS_CLIENT_SECRET`) - Azure AD application client secret
- **`MS_USER_EMAIL`** - Default user email for calendar access
- **`ALLOWED_MAILBOXES`** - Comma-separated list of mailbox addresses (lowercase, e.g., `user1@domain.com,user2@domain.com`)

### Optional (depending on usage):

- **`ALLOWED_MAILBOX_GROUP`** - Only if using group expansion mode (fetches calendars for all members of a security group)

### Setting Fly Secrets:

```bash
fly secrets set -a gary-asst CALENDAR_PROVIDER=ms_graph
fly secrets set -a gary-asst AZURE_TENANT_ID=your-tenant-id
fly secrets set -a gary-asst AZURE_CLIENT_ID=your-client-id
fly secrets set -a gary-asst AZURE_CLIENT_SECRET=your-client-secret
fly secrets set -a gary-asst MS_USER_EMAIL=default-user@domain.com
fly secrets set -a gary-asst ALLOWED_MAILBOXES=user1@domain.com,user2@domain.com
```

### Verification Checklist:

After deployment:

1. **Verify secrets are set:**
   ```bash
   fly secrets list -a gary-asst
   ```
   Confirm `ALLOWED_MAILBOXES` is present and contains mailbox addresses.

2. **Check health endpoint:**
   ```bash
   curl https://gary-asst.fly.dev/health
   ```
   Should return: `{"status":"ok"}`

3. **Test preview endpoint:**
   ```bash
   curl "https://gary-asst.fly.dev/digest/preview?source=live&date=2026-02-18&mailbox=user1@domain.com"
   ```
   Should render meetings (not "No meetings for this date" or 500 errors).

**Note:** If `ALLOWED_MAILBOXES` is missing or empty, the adapter will fail fast with a clear 503 error: "MS Graph configuration missing: ALLOWED_MAILBOXES must be set in production."

---

## 🧹 Pre-commit status

Your `.pre-commit-config.yaml` currently has:
- `pre-commit-hooks`: hygiene
- `black`
- `ruff`
- `mypy`

No `pytest` hook is present. If you want tests to run on every commit, add:

```yaml
- repo: https://github.com/pytest-dev/pytest
  rev: 8.2.2
  hooks:
    - id: pytest
      args: ["-q", "--disable-warnings"]
```

Then run:
```bash
pre-commit install
```

---

## 📂 Project Structure

```
gary-asst/
  app/
    __init__.py
    main.py                    # FastAPI application entrypoint
    routes/                    # API route handlers
      digest.py               # Digest sending endpoints
      preview.py              # Preview endpoints
      search.py               # Search endpoints
      health.py               # Health check endpoints
      scheduler.py            # Scheduler management
      actions.py              # External action handlers
      debug.py                # Debug endpoints
    calendar/                 # Calendar provider abstraction
      provider.py             # Provider protocol and factory
      mock_provider.py        # Mock implementation
      ms_graph_adapter.py     # Microsoft Graph implementation
      types.py                # Calendar data models
    enrichment/               # Data enrichment services
      service.py              # Main enrichment orchestrator
      news_provider.py        # News provider abstraction
      news_newsapi.py         # NewsAPI implementation
      news_bing.py            # Bing News implementation
    llm/                      # LLM integration
      service.py              # LLM client abstraction
    rendering/                # Digest rendering
      digest_renderer.py      # HTML renderer
      context_builder.py      # Context assembly
    services/                 # External service integrations
      emailer.py              # Email provider abstraction
    profile/                  # Executive profile management
      store.py                # Profile storage
      models.py               # Profile data models
    core/                     # Core configuration
      config.py               # Application configuration
    storage/                  # Caching and storage
      cache.py                # Preview cache implementation
    data/                     # Sample data files
      sample_calendar.json    # Mock calendar data
      exec_profiles.json      # Executive profiles
    templates/                # HTML templates
      digest.html             # Digest email template
  tests/                      # Test suite
    test_*.py                 # Unit and integration tests
  docs/                       # Documentation
    API_DESIGN.md            # API design guide
    EXAMPLES.md              # Code examples
    INTEGRATION_EXAMPLE.md   # Integration examples
  ARCHITECTURE.md            # System architecture
  README.md                  # This file
```

## 🎨 Design Principles

### 1. Pluggable Architecture
- **Calendar Providers**: Abstract calendar access behind a protocol
- **News Providers**: Swappable news API implementations
- **Email Providers**: Multiple email delivery options
- **LLM Providers**: Pluggable LLM service integration

### 2. Graceful Degradation
- Fallback to sample data when live data unavailable
- Feature flags for optional services (news, LLM)
- Stub implementations for testing

### 3. Configuration-Driven
- Environment variables for all settings
- Profile-based customization
- Feature flags for optional features

### 4. Testability
- Mock providers for all external services
- Sample data for consistent testing
- Clear separation of concerns

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design decisions and rationale.

---

## 🐳 Dockerfile / CI

**Not required for MVP.** Add later when you want cloud deploy or PR checks.

---

## 🗺️ Roadmap (high-level)
- Integrate Microsoft Graph API (calendar + mail).
- Add Bing enrichment (company + news).
- Use OpenAI for talking points + smart questions.
- Deliver digest emails end-to-end.
---

## 🧭 Commands recap

```bash
# Run API server
uvicorn app.main:app --reload

# Pre-commit
pip install pre-commit && pre-commit install

# Tests
python -m pytest -q
```
