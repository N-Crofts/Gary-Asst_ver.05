# Roadmap (next 2–6 weeks)

**Phase A — Pilot Launch & Accuracy (ship first)**
**A1. Single-meeting preview deep link**
**A2. People intel (metadata-only resolver + confidence scoring)**
**A3. Partial-data mode (no more sample fallback)**
**A4. SMTP production send from `gary-asst@rpck.com` (pilot inbox)**

**Phase B — Personalization & Channel Delivery**
**B1. Slack daily post (optional)**
**B2. Branding polish (logo/theme tokens) + mini style snapshot tests**

**Phase C — Multi-User Pilot & Ops**
**C1. Group-scoped calendar access (mail-enabled security group)**
**C2. Per-user exec profiles + recipient routing**
**C3. Lightweight persistence (store latest render for re-open)**

**Phase D — Advanced Accuracy (optional flags)**
**D1. LLM re-ranker for people intel (flagged)**
**D2. Embedding similarity boost (flagged)**

---

## Phase A — Cursor Tickets (copy/paste prompts)

### A1 — Single-Meeting Preview Deep Link

**Goal:** View one event by ID (great for Slack threads and late-added meetings).

**Acceptance Criteria**

1. `GET /digest/preview/event/{event_id}` → **HTML** card for that event.
2. `GET /digest/preview/event/{event_id}.json` → **JSON** model of that card.
3. Uses the **same** composer/template; gentle “not available” labels for empty enrichment.

**Files**

* `app/routes/preview.py` (+new handlers)
* `app/rendering/context_builder.py` (add `build_single_event_context(event_id, …)`)
* `tests/test_preview_single_event.py`

**Cursor Prompt**

> Implement **Single-Meeting Preview**:
>
> * Add `GET /digest/preview/event/{event_id}` (HTML) and `.json` (JSON).
> * Fetch event via the calendar provider; build context with the same composer/template used today.
> * If enrichment is missing, show real basics (time/location/attendees/join link) with gentle “not available” notes.
> * Add tests asserting: status 200, presence of headings, and safe empty states.

---

### A2 — People Intel (Metadata-Only Resolver + Confidence Scoring)

**Goal:** Show person-level headlines for *the right attendee*, using only meeting metadata (name + email domain + company/aliases).

**Acceptance Criteria**

1. Build a `PersonHint` from attendee + meeting (name, email, domain, co-attendee domains, keywords).
2. Query strategy: Pass A `site:<domain>`; Pass B name + (domain OR company); **no LLM required**.
3. Score each result (0–1): +domain/company hits; −famous-mismatch signals; clamp; **accept ≥0.75**; allow 0.5–0.75 only if no highs.
4. Deduplicate; cache lookups `(name, domain)`; graceful provider errors.
5. Template: show **People intel** with 2–3 links per attendee when available, else “No recent articles found.”

**Files**

* `app/people/normalizer.py`, `app/people/resolver.py`
* `app/enrichment/service.py` (integrate people intel)
* `tests/test_people_resolver.py`
* Optional: `app/profile/overrides.json` (neg/pos keywords per person)

**Env**

```
PEOPLE_NEWS_ENABLED=true
PEOPLE_STRICT_MODE=true
PEOPLE_CONFIDENCE_MIN=0.75
PEOPLE_CONFIDENCE_SHOW_MEDIUM=true
PEOPLE_CACHE_TTL_MIN=120
```

**Cursor Prompt**

> Implement **People Intel (metadata-only)**:
>
> * Create `PersonHint` from attendee + meeting.
> * Build two queries (site:<domain>, then name + (domain OR company)) and score results using domain/company anchors and negative keywords.
> * Accept only results meeting `PEOPLE_CONFIDENCE_MIN` (allow medium if no highs and flag enabled).
> * Integrate into enrichment; render “People intel” per external attendee.
> * Add deterministic tests (provider mocked) for ambiguous names (e.g., sports vs. finance), caching, and thresholds.

---

### A3 — Partial-Data Mode (Replace Sample Fallback)

**Goal:** Never render the old sample card; always show *whatever real details we have* with clear labels for missing enrichment.

**Acceptance Criteria**

1. If events exist but enrichment is empty/disabled/unavailable → show real subject/time/location/attendees/join link + gentle “not available” for enrichment sections.
2. If **no events** for the day → single empty-state block (“No meetings for this date.”).
3. Tests cover both paths.

**Files**

* `app/rendering/context_builder.py` (fallback logic)
* `app/templates/digest.html` (tiny conditional tweaks)
* `tests/test_partial_data.py`

**Cursor Prompt**

> Implement **Partial-Data Mode**: remove sample fallback; render real basics and gentle empty states instead. Update template conditionals and add tests for both “no enrichment” and “no events” days.

---

### A4 — SMTP Production Send From `gary-asst@rpck.com`

**Goal:** Deliver the digest to the pilot’s inbox via Exchange Online SMTP (or SendGrid alternative).

**Acceptance Criteria**

1. With SMTP creds set, `POST /digest/send` `{send:true, source:'live'}` sends multipart email to `DEFAULT_RECIPIENTS`.
2. Console driver keeps `[Preview]` suffix; SMTP/SendGrid do **not**.
3. Retry/backoff keeps behavior (already implemented).

**Files**

* Configuration only (code paths already exist)
* `tests/test_email_smtp_config.py` (skip or mock if secrets absent)

**Cursor Prompt**

> Add a minimal config check/test for the SMTP path—confirm that send uses multipart and omits the preview suffix for real drivers. Keep tests deterministic by mocking the transport.

---

## Phase B — Cursor Tickets

### B1 — Slack Daily Post (Optional Channel)

**Goal:** Post the digest (HTML link + short TL;DR) to a Slack channel each morning.

**Acceptance Criteria**

1. If `SLACK_ENABLED=true`, scheduler posts to `SLACK_CHANNEL_ID` with: subject line, count of meetings, and link to `/digest/preview?source=live`.
2. Button or link to “Send to inbox now”.

**Files**

* `app/channels/slack_client.py`
* `app/routes/actions.py` (optional “send now” action)
* `tests/test_slack.py`

**Env**

```
SLACK_ENABLED=false
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=...
```

**Cursor Prompt**

> Implement Slack posting: small client wrapper, post on schedule with preview link + quick action. Add tests mocking Slack API.

---

### B2 — Branding & Theme Tokens + CSS Markers

**Goal:** Add logo + brand colors, and lock a few CSS markers so visual regressions are caught lightly.

**Acceptance Criteria**

1. Inline logo URL (env or asset) and 2–3 theme tokens (primary, accent, muted).
2. Tests assert presence of specific CSS markers and header/logo block.

**Files**

* `app/templates/digest.html`
* `tests/test_branding.py`

**Env**

```
BRAND_LOGO_URL=https://...
BRAND_PRIMARY=#0C4A6E
BRAND_ACCENT=#16A34A
```

**Cursor Prompt**

> Add branding tokens + optional logo, update template, and add simple marker tests that won’t be brittle.

---

## Phase C — Cursor Tickets

### C1 — Group-Scoped Calendar Access

**Goal:** Support multiple pilot users via a mail-enabled security group that the Application Access Policy targets.

**Acceptance Criteria**

1. Read calendars for any mailbox in the allowed group (provided by IT).
2. `MS_USER_EMAIL` becomes optional; add `ALLOWED_MAILBOX_GROUP` lookups if provided.

**Files**

* `app/calendar/provider.py` (selection logic)
* `app/config.py`
* `tests/test_calendar_group_scope.py` (mocked)

**Env**

```
ALLOWED_MAILBOX_GROUP=GaryAsst-AllowedMailboxes
```

**Cursor Prompt**

> Update provider/config to support a group-based allowlist (still read-only). Add tests that simulate multiple users.

---

### C2 — Per-User Exec Profiles & Routing

**Goal:** Apply the correct exec profile and recipient route per mailbox.

**Acceptance Criteria**

1. Load a profile keyed by mailbox (`sorum.crofts@rpck.com`).
2. Use that profile’s `exec_name`, section limits, and default recipients, overridable by query/body.

**Files**

* `app/profile/store.py` (+ per-user map)
* `app/data/exec_profiles.json` (add mailbox keys)
* `tests/test_profile_multi.py`

**Cursor Prompt**

> Extend profile store to support mailbox-keyed profiles; route recipients and labels accordingly. Add tests for two users.

---

### C3 — Lightweight Persistence (Latest Render)

**Goal:** Store the latest HTML render per user for quick re-open (no re-fetch needed).

**Acceptance Criteria**

1. Save last HTML + JSON context for the day in a temp store (filesystem or in-memory with TTL).
2. Endpoint `GET /digest/preview/latest` serves the cached copy if < N minutes old.

**Files**

* `app/storage/cache.py` (TTL store)
* `app/routes/preview.py` (latest endpoint)
* `tests/test_preview_cache.py`

**Env**

```
PREVIEW_CACHE_TTL_MIN=10
```

**Cursor Prompt**

> Add a TTL cache for the latest daily render and a `/digest/preview/latest` endpoint. Tests for cache hit/miss logic.

---

## Phase D — (Optional) Advanced Accuracy

### D1 — LLM Re-Ranker (Flagged)

**Goal:** Re-rank the top N person-news results with a short LLM call to boost precision; fallback to metadata score.

**Acceptance Criteria**

1. With `PEOPLE_RERANK_LLM=true`, sort accepted candidates by LLM score; on timeout/error, keep metadata order.
2. Deterministic tests monkeypatch the LLM to return fixed ranks.

**Files**

* `app/people/reranker.py`
* `tests/test_people_rerank.py`

**Env**

```
PEOPLE_RERANK_LLM=false
OPENAI_API_KEY=...
```

**Cursor Prompt**

> Implement an optional LLM re-ranking step that operates on already-accepted person-news. Keep tests deterministic via stubs.

---

### D2 — Embedding Similarity Boost (Flagged)

**Goal:** Boost person-news that semantically matches a company/person blurb (e.g., pulled from the company site bio).

**Acceptance Criteria**

1. With `PEOPLE_EMBEDDINGS=true`, compute a simple cosine similarity between the article snippet and a brief profile blurb; add a small bonus to the metadata score.
2. Tests use tiny fake vectors; deterministic.

**Files**

* `app/people/embeddings.py`
* `tests/test_people_embeddings.py`

**Env**

```
PEOPLE_EMBEDDINGS=false
EMBEDDINGS_PROVIDER=openai
OPENAI_API_KEY=...
```

**Cursor Prompt**

> Add an optional embeddings similarity bonus to person-news scoring. Keep deterministic tests with fixed vectors.

---

# Access / Keys Checklist (what to request up front)

**Microsoft 365 / Azure (from Tabush)**

* Tenant ID, Client ID, Client Secret (for “Gary-Asst” app)
* Graph **Calendars.Read (Application)** with admin consent
* **Exchange Application Access Policy** restricting to `sorum.crofts@rpck.com` (Phase C: group `GaryAsst-AllowedMailboxes`)
* Optional: Graph **Mail.Send (Application)** if you prefer Graph sending later

**Email (one path)**

* **SMTP**: host, port 587, username/password for `gary-asst@rpck.com`, TLS, **SMTP AUTH enabled**
* or **SendGrid**: API key, verified sender/domain

**News Provider**

* API key for **Bing News** or **NewsAPI**; outbound allowed to provider API domains

**Slack (optional)**

* Slack **Bot token** (`SLACK_BOT_TOKEN`) and **Channel ID** for posting

**LLM / Embeddings (optional)**

* `OPENAI_API_KEY` (or Azure OpenAI) if you want D1/D2 enabled later

**Observability (optional)**

* `SENTRY_DSN` if you want error reporting; otherwise logging to stdout is already set

**Branding**

* `BRAND_LOGO_URL` and hex colors

**Storage (optional)**

* If you want cross-instance caching/persistence: credentials for S3/Azure Blob (phase C3 could remain in-memory for pilot)

---

# How to run this with Cursor (operational cadence)

**Step 1 — Pin this roadmap** in Cursor (or add to `docs/roadmap-next.md`).
**Step 2 — Feed tickets A1 → A4 one at a time**, reviewing diffs and running `pytest -q` after each.
**Step 3 — Pilot verification**: share the single-meeting link and daily preview with Sorum; send one SMTP email.
**Step 4 — If time permits**: run B1 (Slack) and B2 (Branding).
**Step 5 — If pilot expands**: run C1–C3.
\*\*Step 6 — Consider D1/D2 later if stakeholders want “even smarter” results.
