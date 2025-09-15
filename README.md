# Gary-Asst (Research Gary MVP)

Research Gary scans the daily calendar, builds quick dossiers for external meetings, and emails a single morning briefing. This README reflects **the repo state at its start** (single `app/main.py` and a smoke test) and shows how to **upgrade to the FastAPI skeleton** we planned.

References: Product Spec and Tech Plan.

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

## 📂 Target project structure

```
gary-asst/
  app/
    __init__.py
    main.py
    routes/
      digest.py
    integrations/
      graph_calendar.py
      graph_mail.py
      bing.py
    core/
      models.py
      llm.py
      renderer.py
      flags.py
      log.py
    templates/
      digest.html
  tests/
    test_smoke.py
    test_endpoints.py
```

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
