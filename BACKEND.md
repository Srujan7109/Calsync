# Calsync Backend Documentation

**Tech Stack:** FastAPI, Gemini API, Gmail MCP, Calendar MCP, Redis/Supabase, IMAP  
**Language:** Python 3.10+

---

## Overview

Calsync backend is an event ingestion and coordination engine designed to:

- **Receive** inbound scheduling emails via webhooks
- **Poll** IMAP mailboxes for meeting coordination messages
- **Deduplicate** emails using configurable backends (Redis, Supabase, or in-memory)
- **Filter** non-scheduling-related emails using keyword matching
- **Queue** accepted emails for async Gemini agent processing

---

## Core Responsibilities

### 1. Email Ingestion Layer

- **Webhook Endpoint:** `POST /api/v1/webhook/email`
  - Accepts SendGrid-style multipart form data
  - Fields: `from`, `to`, `subject`, `text`, `html`, `message_id`, `headers`, `spam_score`, `attachments`
  - Returns immediate response while background processing runs
- **IMAP Polling:** `POST /api/v1/imap/poll`
  - Manually trigger inbox fetch from configured IMAP account
  - Query param: `limit` (1-100, default 20)
  - Runs on configurable interval (default: every 10 seconds in background)
- **Gmail Push Webhook:** `POST /api/v1/webhook/gmail/push`
  - Accepts Google Pub/Sub push notifications from Gmail watch
  - Debounces burst notifications and triggers immediate Gmail fetch
  - Designed for near-instant processing without interval wait

### 2. Deduplication Layer

- **Idempotency Hash:** SHA-256(sender_email + message_id)
- **Supported Backends:**
  - `memory`: In-process dict (development only)
  - `redis`: Distributed cache with TTL
  - `supabase`: Postgres-backed with automatic cleanup
  - `auto`: Intelligent fallback (Redis → Supabase → memory)
- **Service:** `app/services/dedup_service.py`

### 3. Async Processing with Gemini

- **Background Task Queue:** Fastapi `BackgroundTasks`
- **Gemini + MCP Orchestration:**
  - Accept emails for agent processing
  - Use Gemini for scheduling intent and slot extraction
  - Use Gmail MCP server to send follow-up and confirmation emails
  - Use Calendar MCP server to create meeting bookings
- **Payload Structure:** `AgentProcessPayload` (Pydantic model)
  - Includes: email hash, sender, subject, body, timestamp, thread info

---

## Project Structure

```
ingestion/
└── app/
├── main.py                      # FastAPI app setup, lifespan management
├── config.py                    # Settings & environment loading
├── models/
│   ├── __init__.py
│   └── email_models.py          # Pydantic request/response schemas
├── routers/
│   ├── imap.py                  # IMAP polling endpoints
│   ├── webhook.py               # Email webhook endpoints
│   └── __init__.py
└── services/
    ├── background_tasks.py      # Async task handlers
    ├── dedup_service.py         # Deduplication logic
    ├── imap_ingestion.py        # IMAP email collection
    ├── imap_poller.py           # Background polling loop
    ├── imap_service.py          # IMAP client wrapper
    └── __init__.py
```

---

## Configuration (Environment Variables)

### IMAP Setup

```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your-email@gmail.com
IMAP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
IMAP_MAILBOX=INBOX
IMAP_SEARCH_CRITERIA=UNSEEN
IMAP_AUTO_POLL_ENABLED=true
IMAP_POLL_INTERVAL_SECONDS=10
IMAP_POLL_BATCH_SIZE=20
```

### Gmail Push (Low Latency)

```
USE_GMAIL_API_POLLING=true
GMAIL_PUSH_ENABLED=true
GMAIL_PUSH_FETCH_LIMIT=20
GMAIL_PUSH_DEBOUNCE_MS=400
IMAP_AUTO_POLL_ENABLED=false
```

Also configure Gmail watch on the Gmail MCP service and route Pub/Sub push
notifications to `/api/v1/webhook/gmail/push`.

### Deduplication Backend

```
DEDUP_BACKEND=auto  # Options: auto, redis, supabase, memory
REDIS_URL=redis://localhost:6379/0
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_DEDUP_TABLE=idempotency_keys
```

### Scheduling Keywords Filter

```
ACCEPTED_KEYWORDS=schedule,meeting,call,sync,standup,discuss,touch base
```

---

## Key Features (Current & In-Progress)

✅ **Implemented:**

- Email webhook ingestion (SendGrid-compatible)
- IMAP polling with batch collection
- SHA-256 deduplication layer
- Keyword edge filtering
- Background task queueing
- Multi-backend dedup support
- Health check endpoint
- Auto-polling background service

🚀 **In-Progress / Planned:**

- Gemini prompt tuning for more reliable slot extraction
- Meeting detail extraction (date/time/attendees)
- Calendar integration hardening
- Response generation quality improvements
- Multi-turn conversation tracking
- Monitoring & logging dashboard

---

## API Endpoints

### Webhook

| Method | Endpoint                 | Purpose                 |
| ------ | ------------------------ | ----------------------- |
| GET    | `/api/v1/webhook/health` | Service health check    |
| POST   | `/api/v1/webhook/email`  | Ingest scheduling email |
| POST   | `/api/v1/webhook/gmail/push`  | Pub/Sub trigger for instant Gmail ingest |

### IMAP

| Method | Endpoint                     | Purpose             |
| ------ | ---------------------------- | ------------------- |
| POST   | `/api/v1/imap/poll?limit=20` | Manually poll inbox |

---

## Response Models

### Webhook Email Responses

```json
{
  "accepted": { "status": "accepted", "task_id": "bg_task_abc123" },
  "duplicate": { "status": "duplicate_discarded" },
  "filtered": { "status": "not_scheduling_related" }
}
```

### IMAP Poll Response

```json
{
  "status": "ok",
  "fetched": 20,
  "accepted": 3,
  "duplicates": 14,
  "filtered_out": 3
}
```

---

## Development Workflow

### Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ingestion/requirements.txt
```

### Run Locally

```powershell
uvicorn ingestion.app.main:app --reload --port 8000
```

### Access Documentation

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

### Testing Email Webhook

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/webhook/email" \
  -F "from=alice@example.com" \
  -F "to=calsync@yourdomain.com" \
  -F "subject=Schedule a team sync" \
  -F "text=Can we schedule a call next Tuesday?" \
  -F "message_id=<CABc123@mail.gmail.com>"
```

### Testing IMAP Poll

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/imap/poll?limit=20"
```

---

## Dependencies

See `requirements.txt`, but key packages:

- **FastAPI:** Web framework
- **Pydantic:** Data validation
- **python-dotenv:** Environment config
- **aioredis:** Redis async client
- **supabase:** Postgres backend
- **imaplib:** Standard IMAP protocol
- **google-genai:** Gemini model client

---

## Next Steps

1. **Gemini + MCP Stabilization:**

- Tighten JSON response guarantees from Gemini
- Add robust fallback handling for malformed model output
- Expand booking and follow-up decision coverage

2. **Response Generation:**
   - Template for auto-replies
   - Calendar availability checking
   - Alternative proposal generation

3. **Monitoring & Logging:**
   - Structured logging for debugging
   - Metrics dashboard (processed/accepted/failed counts)

4. **Testing:**
   - Unit tests for dedup service
   - Integration tests for email workflows
   - Mock IMAP server for testing
