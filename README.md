# Calsync

FastAPI backend for the Calsync email coordination agent.

## Setup (Windows PowerShell)

1. Create virtual environment:

   ```powershell
   py -m venv .venv
   ```

2. Activate virtual environment:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

## Run locally

```bash
uvicorn app.main:app --reload
```

## API Docs (Swagger)

After server startup:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## IMAP ingestion (new primary path)

Set these in `.env` before polling:

- `IMAP_HOST` (example: `imap.gmail.com`)
- `IMAP_PORT` (default: `993`)
- `IMAP_USERNAME` (dedicated mailbox)
- `IMAP_APP_PASSWORD` (app password, not your normal login password)
- `IMAP_MAILBOX` (default: `INBOX`)
- `IMAP_SEARCH_CRITERIA` (default: `UNSEEN`)
- `IMAP_AUTO_POLL_ENABLED` (default: `true`)
- `IMAP_POLL_INTERVAL_SECONDS` (default: `10`)
- `IMAP_POLL_BATCH_SIZE` (default: `20`)

When auto polling is enabled, the server checks IMAP every 10 seconds in the background.

Trigger poll:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/imap/poll?limit=20"
```

## Dedup backend (flexible)

Set `DEDUP_BACKEND` to one of:

- `auto` (default): uses Redis if configured, else Supabase if configured, else in-memory
- `redis`
- `supabase`
- `memory`

### Redis mode

- `DEDUP_BACKEND=redis`
- `REDIS_URL=redis://localhost:6379/0`

### Supabase mode

- `DEDUP_BACKEND=supabase`
- `SUPABASE_URL=https://<project-ref>.supabase.co`
- `SUPABASE_SERVICE_KEY=<service-role-key>`
- `SUPABASE_DEDUP_TABLE=idempotency_keys`

Expected Supabase table columns:

- `email_hash` (text, unique or primary key)
- `expires_at` (timestamptz)

## Webhook endpoints

- `GET /api/v1/webhook/health`
- `POST /api/v1/webhook/email`

The webhook accepts SendGrid-style multipart form data, performs SHA-256 deduplication on `from + message_id`, runs a fast keyword edge filter, and returns an immediate accepted response while the background task handles downstream processing.
