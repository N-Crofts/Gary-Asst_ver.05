# Fly.io Diagnostic Guide

## Problem
Fly deployment shows "No meetings for this date" while localhost works correctly.

## Step-by-Step Diagnosis

### Step 1: Get Fly Logs

In your terminal, run:

```bash
fly logs -a gary-asst --since 60m
```

Then reload the Fly preview URL once in your browser:
```
https://gary-asst.fly.dev/digest/preview?source=live&date=2026-02-18&mailbox=chintan.panchal@rpck.com
```

**Look for these log lines in the output:**

1. **Preview request received:**
   ```
   Preview request received: source=live, date=2026-02-18, mailbox=chintan.panchal@rpck.com
   ```

2. **Calendar provider selection (CRITICAL):**
   ```
   Selecting calendar provider: mock (from CALENDAR_PROVIDER env var)
   ```
   OR
   ```
   Selecting calendar provider: ms_graph (from CALENDAR_PROVIDER env var)
   ```

3. **Provider type:**
   ```
   Using calendar provider: MockCalendarProvider
   ```
   OR
   ```
   Using calendar provider: MSGraphAdapter
   ```

4. **If MS Graph is used, look for:**
   ```
   MS Graph token request...
   GRAPH REQUEST PAGE 1: ...
   GRAPH RESPONSE STATUS: 200
   Received X events from provider MSGraphAdapter...
   Mapped to X meetings
   ```

5. **Any errors:**
   ```
   ERROR: ...
   GRAPH RESPONSE STATUS: 401
   GRAPH RESPONSE STATUS: 403
   ```

**Paste the relevant log lines here.**

---

### Step 2: Verify Fly Secrets

Run:

```bash
fly secrets list -a gary-asst
```

**Expected secrets:**
- `CALENDAR_PROVIDER=ms_graph` (must be set!)
- `AZURE_CLIENT_ID=...`
- `AZURE_CLIENT_SECRET=...`
- `AZURE_TENANT_ID=...`
- `ALLOWED_MAILBOXES=chintan.panchal@rpck.com,...` (optional but recommended)

**Paste the output (redact secret values if needed).**

---

### Step 3: Check Fly Status

```bash
fly status -a gary-asst
```

**Paste the output.**

---

### Step 4: Fix Based on Findings

#### If `CALENDAR_PROVIDER` is missing or set to `mock`:

```bash
fly secrets set -a gary-asst CALENDAR_PROVIDER=ms_graph
fly deploy -a gary-asst
```

Then re-test the preview URL.

#### If Azure secrets are missing:

```bash
fly secrets set -a gary-asst AZURE_CLIENT_ID=your-client-id
fly secrets set -a gary-asst AZURE_CLIENT_SECRET=your-secret
fly secrets set -a gary-asst AZURE_TENANT_ID=your-tenant-id
fly deploy -a gary-asst
```

Then re-test the preview URL.

#### If logs show 401/403 errors:

- Verify Azure secrets match your local `.env` file
- Check that `ALLOWED_MAILBOXES` includes `chintan.panchal@rpck.com`
- Re-set secrets if needed and redeploy

#### If Graph returns 200 with events but UI shows none:

- Force deploy latest code:
  ```bash
  fly deploy -a gary-asst
  ```
- Check logs for "Mapped to X meetings" - if this shows 0, there's a filtering issue
- Check logs for "Context built: meeting_count=X" - this shows final count

---

## Enhanced Logging

The code now includes enhanced logging that will show:
- Which calendar provider is selected
- How many events are received from Graph
- How many meetings are mapped
- Final meeting count in context

These logs will help pinpoint exactly where the pipeline fails on Fly.
